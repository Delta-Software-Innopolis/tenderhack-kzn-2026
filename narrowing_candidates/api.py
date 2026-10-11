import requests
from fastapi import FastAPI, HTTPException
from typing import Any, Literal
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware   # <-- add

from repo import load_positions
from analyze import analyze

app = FastAPI()
app.add_middleware(                                   # <-- add
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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

# ── общие куски ──────────────────────────────────────────────

class Fact(BaseModel):
    name: str
    type: Literal["string", "number", "boolean"]
    value: str | bool | float
    unit: str | None = None          # в hints у ambiguous-опций unit может отсутствовать


class FunnelStep(BaseModel):
    step: str
    before: int
    after: int


# ── hints ────────────────────────────────────────────────────

class HintOption(BaseModel):
    label: str
    fact: Fact
    remaining: int


class AmbiguousHint(BaseModel):
    name: str
    required: bool
    avg: float
    options: list[HintOption]


class DropInfo(BaseModel):
    remaining: int


class ConflictFix(BaseModel):
    fact: Fact
    label: str
    drop: DropInfo
    options: list[dict[str, Any]]    # в примерах пустой, форма неизвестна
    blocked_by_other_conflict: bool


class ConflictHint(BaseModel):
    kind: Literal["conflict"]
    facts: list[Fact]
    message: str
    suggestions: list[Any]
    fixes: list[ConflictFix]


# ── attributes (копия схемы экстрактора) ─────────────────────

class OkeiUnit(BaseModel):
    okei_code: str
    name: str


class OriginalValue(BaseModel):
    type: Literal["string", "number", "boolean"]
    value: str | bool | float
    unit: str | None = None


class NormalizedValue(BaseModel):
    type: Literal["string", "number", "boolean"]
    value: str | bool | float
    unit: OkeiUnit | None = None


class CharacteristicOption(BaseModel):
    characteristic_id: str
    name: str
    product_name: str | None = None
    unit_names: list[str] = []


class SourceSpan(BaseModel):
    start: int
    end: int


class Attribute(BaseModel):
    id: str
    source_text: str
    source_span: SourceSpan
    mention_type: Literal["explicit", "implicit"]
    status: Literal["resolved", "unknown", "needs_clarification"]
    original_value: OriginalValue
    characteristic_id: str | None = None
    characteristic_name: str | None = None
    normalized_value: NormalizedValue | None = None
    extracted_name: str | None = None
    message: str | None = None
    resolution_source: Literal["model", "user"] = "model"
    characteristic_options: list[CharacteristicOption] = []


# ── ответ ────────────────────────────────────────────────────

class AnalyzeResponse(BaseModel):
    funnel: list[FunnelStep]
    candidates: list[str]
    status: Literal["resolved", "ambiguous", "conflict"]
    result_code: str | None
    culprit: str | None
    hints: list[ConflictHint | AmbiguousHint | dict[str, Any]]
    attributes: list[Attribute]


@app.post("/analyze", response_model=AnalyzeResponse)
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
