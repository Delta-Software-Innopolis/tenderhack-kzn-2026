import requests

URL = "http://100.116.124.13:8003/search"

GOOD = ["молоток слесарный", "стол офисный", "перчатки рабочие", "стул", "куртка зимняя"]
BAD = ["asdfgh", "квантовый борщ", "ноутбук", "картофель", "рыба на луне"]

for label, queries in (("GOOD", GOOD), ("BAD", BAD)):
    print(label)
    for q in queries:
        r = requests.post(URL, json={"query": q, "limit": 100}, timeout=60)
        r.raise_for_status()
        cands = r.json()["candidates"]
        cos = sorted((c["cosine"] for c in cands if c.get("cosine") is not None), reverse=True)
        print(f"  {q!r:24} total={len(cands):3}  top cosines={[round(x, 3) for x in cos[:5]]}")
