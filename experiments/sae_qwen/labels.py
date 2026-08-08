"""Join r-levels (ytk.signals) onto the pulled note keys.

YTK_VISUAL_INDEX=off uv run python experiments/sae_qwen/labels.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
DATA = HERE / "data"


def build() -> dict:
    from ytk import signals

    smap = signals.signal_map()
    rows = [json.loads(x) for x in (DATA / "rows.jsonl").read_text().splitlines()]
    out: dict[str, dict] = {}
    for r in rows:
        nk = r["note_key"]
        if nk in out:
            continue
        rl = None
        if nk.startswith("vid::"):
            rl = smap.get(nk[5:])
        elif r["source_path"]:
            rl = smap.get(r["source_path"])
        if rl is None:
            continue
        out[nk] = {"r": rl, "source": r["source"], "in_dist": r["in_dist"]}
    return out


def main() -> None:
    lab = build()
    (DATA / "labels.json").write_text(json.dumps(lab, indent=0))
    print("labeled notes:", len(lab))
    print("r overall:", Counter(v["r"] for v in lab.values()))
    print("r in-dist:", Counter(v["r"] for v in lab.values() if v["in_dist"]))
    print("source x r:", Counter((v["source"], v["r"]) for v in lab.values() if v["in_dist"]))


if __name__ == "__main__":
    main()
