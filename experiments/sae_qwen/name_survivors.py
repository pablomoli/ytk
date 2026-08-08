"""Name the regression's surviving latents and merge them into features.json.

YTK_VISUAL_INDEX=off uv run python experiments/sae_qwen/name_survivors.py --ckpt <p>
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))

import numpy as np  # noqa: E402
from features import NAME_SYSTEM, Name, feature_table  # noqa: E402

DATA = HERE / "data"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    a = ap.parse_args()

    from ytk.sdk import structured

    rows = [json.loads(x) for x in (DATA / "rows.jsonl").read_text().splitlines()]
    blob = json.loads((HERE / "features.json").read_text())
    have = {f["feature"] for f in blob["features"]}
    taste = json.loads((HERE / "taste.json").read_text())
    want = {
        s["feature"]
        for key in ("A_deliberate", "B_thought", "C_thought_instagram")
        for s in taste[key]["survivors"]
    } - have
    if not want:
        print("nothing to name")
        return

    z = np.load(DATA / f"acts_{Path(a.ckpt).stem}.npz")
    full = feature_table(DATA / f"acts_{Path(a.ckpt).stem}.npz", rows, int(z["d_sae"]))
    table = [t for t in full if t["feature"] in want]

    def name_one(t):
        body = "\n\n".join(
            f"[{e['kind']}/{e['source']}] {e['title'][:80]}\n{e['text'][:380]}"
            for e in t["exemplars"]
        )
        try:
            res = structured(
                NAME_SYSTEM,
                f"Latent #{t['feature']} fires on {t['freq'] * 100:.2f}% of documents.\n"
                f"Its 8 strongest activating excerpts:\n\n{body}\n\n"
                "Name the concept in at most 6 words. confidence: high|medium|low "
                "(low if the excerpts look unrelated).",
                Name,
                max_tokens=300,
            )
            t["name"] = res.name
            t["name_confidence"] = res.confidence
            t["name_rationale"] = res.rationale
        except Exception as e:
            t["name"] = None
            t["name_error"] = str(e)[:200]
        return t

    with ThreadPoolExecutor(max_workers=5) as ex:
        list(ex.map(name_one, table))

    blob["features"].extend(table)
    blob["survivor_features_appended"] = sorted(want)
    (HERE / "features.json").write_text(json.dumps(blob, indent=1))
    for t in table:
        print(t["feature"], t.get("name_confidence"), t.get("name"))


if __name__ == "__main__":
    main()
