import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from repo import load_positions
from analyze import analyze

app = FastAPI()

DB = "../ktru.db"

def convert_candidates(api_candidates):
    result = []

    for candidate in api_candidates:
        chars = {}

        for char in candidate["characteristics"]:
            values = []

            for value in char["values"]:
                if value["type"] == "string":
                    values.append({
                        "kind": "text",
                        "text": value["value"],
                    })
                elif value["type"] == "number":
                    values.append({
                        "kind": "number",
                        "number": value["value"],
                    })
                elif value["type"] == "interval":
                    values.append({
                        "kind": "interval",
                        **value["value"],
                    })

            chars[char["name"]] = {"values": values}

        result.append({
            "code": candidate["code"],
            "name": candidate["name"],
            "chars": chars,
        })

    return result

def convert_facts(api_result):
    result = []

    for char in api_result["chars"]:
        for value in char["values"]:
            result.append({
                "name": char["name"],
                "type": value["type"],
                "value": value["value"],
                "unit": value["unit"],
            })

    return result

class AnalyzeRequest(BaseModel):
    query: str

@app.post("/analyze")
def analyze_query(request: AnalyzeRequest):
    try:
        search_response = requests.post(
            "http://100.116.124.13:8003/search",
            json={"query": request.query, "limit": 10},
            timeout=60,
        )
        search_response.raise_for_status()
        search_result = search_response.json()
        extract_response = requests.post(
            "http://100.106.102.97:8001/extract/from-search",
            json=search_result,
            timeout=60,
        )
        extract_response.raise_for_status()
        api_result = extract_response.json()
    except requests.RequestException as e:
        raise HTTPException(
            status_code=502,
            detail=f"Ошибка при обращении к другому сервису: {e}",
        )

    candidates = convert_candidates(api_result["candidates"])
    facts = convert_facts(api_result)

    return analyze(candidates, facts)
