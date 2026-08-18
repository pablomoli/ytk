"""Export per-latent card data for the hub /atlas page (#183 rung 6).

~/.ytk/atlas_features.json: every latent the atlas or the wall can surface —
name, firing frequency, seed badge, and its top exemplars with enough
provenance for the page to render TEXT mode (titles) and IMG mode
(YouTube video ids resolve to thumbnails). Annotation layer only.

    uv run python experiments/sae_qwen/export_hub_features.py
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = Path.home() / ".ytk"


def video_id(e: dict) -> str | None:
    if e["kind"] == "video":
        return e["id"]
    if e["kind"] == "segment":
        return e["id"].rsplit("_", 1)[0]
    return None


def main() -> None:
    features = json.loads((HERE / "features.json").read_text())
    atlas = json.loads((HERE / "atlas.json").read_text())
    badge = json.loads((HERE / "seed_agreement.json").read_text())["badge"]

    want = {t["latent"] for c in atlas["cells"] for t in c["top5"]}
    head = sorted(features["features"], key=lambda t: -t["freq"])[:100]
    want |= {t["feature"] for t in head}
    want.add(atlas["protagonist"]["latent"])

    cards = {}
    for t in features["features"]:
        f = t["feature"]
        if f not in want or f in cards:
            continue
        cards[f] = {
            "name": t.get("name"),
            "confidence": t.get("name_confidence"),
            "freq": round(t["freq"], 5),
            "badge": badge[f],
            "exemplars": [
                {
                    "title": e["title"] or e["text"][:70],
                    "kind": e["kind"],
                    "source": e["source"],
                    "video_id": video_id(e),
                    "act": e["act"],
                }
                for e in t["exemplars"][:6]
            ],
        }
    out = {
        "checkpoint": features["checkpoint"],
        "naming": features["naming"],
        "protagonist": atlas["protagonist"]["latent"],
        "cards": cards,
    }
    (OUT / "atlas_features.json").write_text(json.dumps(out))
    print(f"wrote {OUT / 'atlas_features.json'}: {len(cards)} cards")


if __name__ == "__main__":
    main()
