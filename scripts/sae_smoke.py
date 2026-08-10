#!/usr/bin/env python
"""18.0 — Neuronpedia API smoke test (pre-registered in 18-sae-fingerprints/README.md).

One known coding-topic note through POST /api/search-all on the named SAE
(gemma-2-2b, layer 20 res 16k), then names for its top-10 features via
POST /api/features. Raw request/response JSON lands in
docs/assets/18-sae-fingerprints/smoke/ for the record.

Prediction under test: >= 6 of the top 10 features have names recognizably
related to the note's content. Kill: < 3.

    uv run python scripts/sae_smoke.py
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

OUTDIR = Path(__file__).resolve().parents[1] / "docs" / "assets" / "18-sae-fingerprints" / "smoke"
NOTE_TITLE = "How To De-Slop A Codebase Ruined By AI (with one skill)"
MODEL = "gemma-2-2b"
LAYER = "20-gemmascope-res-16k"
SOURCE_SET = "gemmascope-res-16k"


def post(url: str, body: dict | list) -> dict | list:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


def main() -> None:
    from ytk import store

    vids = store._videos_collection().get(include=["documents", "metadatas"])
    text = next(
        doc
        for doc, meta in zip(vids["documents"], vids["metadatas"])
        if str(meta.get("title", "")).startswith(NOTE_TITLE[:40])
    )
    text = text[:2000]

    OUTDIR.mkdir(parents=True, exist_ok=True)
    search_body = {
        "modelId": MODEL,
        "sourceSet": SOURCE_SET,
        "selectedLayers": [LAYER],
        "sortIndexes": [],  # required — omitting it is a 500, not a validation message
        "text": text,
        "ignoreBos": True,
        "densityThreshold": -1,
        "numResults": 50,
    }
    search = post("https://www.neuronpedia.org/api/search-all", search_body)
    (OUTDIR / "search-all.json").write_text(
        json.dumps({"request": search_body, "response": search}, indent=1)
    )

    result = search["result"] if "result" in search else search["results"][0]["result"]
    top = sorted(result, key=lambda r: -float(r["maxValue"]))[:10]

    feat_body = [{"modelId": MODEL, "layer": LAYER, "index": int(r["index"])} for r in top]
    feats = post("https://www.neuronpedia.org/api/features", feat_body)
    (OUTDIR / "features.json").write_text(json.dumps(feats, indent=1))

    by_index = {str(f.get("index")): f for f in feats}
    print(f"note: {NOTE_TITLE}")
    print(f"text sent: {len(text)} chars\n")
    for r in top:
        f = by_index.get(str(r["index"]), {})
        exps = f.get("explanations") or []
        name = exps[0].get("description", "(no explanation)") if exps else "(no explanation)"
        print(f"  {float(r['maxValue']):7.2f}  #{r['index']:>6}  {name}")


if __name__ == "__main__":
    main()
