import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from repo import load_positions
from analyze import analyze

app = FastAPI()

DB = "../ktru.db"


class AnalyzeRequest(BaseModel):
    query: str


@app.post("/analyze")
def analyze_query(request: AnalyzeRequest):
    try:
        search_response = requests.post(
            "http://localhost:8003/search",
            json={"query": request.query, "limit": 10},
            timeout=60,
        )
        search_response.raise_for_status()
        search_result = search_response.json()

        extract_response = requests.post(
            "http://localhost:8001/extract/from-search",
            json=search_result,
            timeout=60,
        )
        extract_response.raise_for_status()
        facts = extract_response.json()

    except requests.RequestException as e:
        raise HTTPException(
            status_code=502,
            detail=f"Ошибка при обращении к другому сервису: {e}",
        )

    candidates = load_positions(DB)

    return analyze(candidates, facts)
