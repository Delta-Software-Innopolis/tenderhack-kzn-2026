import requests

def search_and_extract(query: str):
    response = requests.post(
        "http://localhost:8003/search",
        json={"query": query, "limit": 10},
    )
    response.raise_for_status()

    search_result = response.json()

    response = requests.post(
        "http://localhost:8001/extract/from-search",
        json=search_result,
    )
    response.raise_for_status()

    return response.json()
