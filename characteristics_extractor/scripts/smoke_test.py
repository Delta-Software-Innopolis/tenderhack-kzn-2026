"""Small live HTTP check. Requires the extractor and LM Studio to be running.

Does not run as part of unit tests. Candidate fixture is deliberately mixed;
this checks behavior on that supplied dictionary, not product search quality.
"""
import argparse
import asyncio
import json
from pathlib import Path
from time import monotonic

import httpx


async def main(url: str, only: list[str]):
    fixture = json.loads((Path(__file__).resolve().parents[1] / "examples/search_response.json").read_text())
    cases = [
        ("explicit", "Молоток с деревянной ручкой 15 см"),
        ("implicit", "Молоток 15 см"),
        ("mass", "Молоток массой 500 г"),
        ("unknown", "Молоток с гравировкой дракона"),
        ("unsupported", "Молоток массой не больше 500 г"),
        ("ambiguous", "Лопата длина 15 см"),
    ]
    failed = False
    async with httpx.AsyncClient(base_url=url, timeout=150, trust_env=False) as client:
        for label, query in cases:
            if only and label not in only:
                continue
            started = monotonic()
            request = fixture | {"query": query, "canonical_query": query, "lemmatized_query": query.lower()}
            response = await client.post("/extract", json=request)
            result = response.json()
            checks = {"http_200": response.status_code == 200}
            if response.status_code == 200:
                checks["candidates_preserved"] = result["candidates"] == fixture["candidates"]
                checks["search_target"] = result["search_target"] == ("Лопата" if label == "ambiguous" else "Молоток")
                attributes = result["attributes"]
                if label in {"explicit", "implicit", "mass"}:
                    target = "Масса молотка" if label == "mass" else "Длина рукоятки"
                    expected = 0.5 if label == "mass" else 150
                    checks["normalized"] = any(a["characteristic_name"] == target and a["normalized_value"]
                                                and a["normalized_value"]["value"] == expected for a in attributes)
                    if label == "implicit":
                        checks["implicit"] = any(a["mention_type"] == "implicit" for a in attributes)
                if label in {"explicit", "unknown"}:
                    checks["unknown"] = any(a["status"] == "unknown" and a["message"] == "Неизвестная характеристика"
                                            for a in attributes)
                if label == "unsupported":
                    checks["constraint_not_equality"] = not attributes and any(i["code"] == "unsupported_constraint" for i in result["issues"])
                if label == "ambiguous":
                    questions = [q for q in result["clarifications"] if q["kind"] == "choose_characteristic"]
                    checks["has_choice"] = bool(questions)
                    if questions:
                        continuation = json.loads(json.dumps(result))
                        continuation["clarifications"] = []
                        repeated = await client.post("/extract", json=continuation)
                        checks["unanswered_repeated"] = repeated.status_code == 200 and repeated.json()["clarifications"] == result["clarifications"]
                        for question in questions:
                            attribute = next(a for a in continuation["attributes"] if a["id"] == question["attribute_id"])
                            attribute["characteristic_id"] = question["options"][0]["characteristic_id"]
                            attribute["resolution_source"] = "user"
                        completed = await client.post("/extract", json=continuation)
                        checks["choice_completed"] = completed.status_code == 200 and completed.json()["status"] == "completed"
            failed |= not all(checks.values())
            print(json.dumps({"case": label, "seconds": round(monotonic() - started, 2), "checks": checks,
                              "result": {key: result[key] for key in ("query", "search_target", "status", "attributes", "clarifications", "issues", "detail") if key in result}},
                             ensure_ascii=False), flush=True)
    return int(failed)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8002")
    parser.add_argument("--case", action="append", default=[], choices=["explicit", "implicit", "mass", "unknown", "unsupported", "ambiguous"])
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.url, args.case)))
