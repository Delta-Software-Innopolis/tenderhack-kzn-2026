import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from repo import load_positions
from analyze import analyze

app = FastAPI()

DB = "../ktru.db"

def convert_facts(api_result):
    facts = []

    for attribute in api_result["attributes"]:
        if attribute.get("status") != "resolved":
            continue

        value = attribute.get("normalized_value")
        name = attribute.get("characteristic_name")

        if not value or not name:
            continue

        facts.append({
            "name": name,
            "type": value["type"],
            "value": value["value"],
            "unit": value.get("unit"),
        })

    return facts

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
            "http://100.106.102.97:8002/extract",
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

    candidate_codes = [
        candidate["ktru_code"]
        for candidate in search_result["candidates"]
    ]

    candidates = load_positions(DB, codes=candidate_codes)
    facts = convert_facts(api_result)

    result = analyze(candidates, facts)

    return {
        **result,
        "attributes": api_result["attributes"],
    }
