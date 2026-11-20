"""Spike helper: one store vector per orb tile, in /api/orb order, for the
spike search route. Same url-then-title matching as knn_attach.py."""

import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
from build_map import load_points

here = Path.home() / ".ytk" / "orb-spike"
data = json.loads((here / "map.json").read_text())
vecs, meta, _ = load_points()
by_url = {m["url"]: i for i, m in enumerate(meta) if m.get("url")}
by_title = {m["title"]: i for i, m in enumerate(meta) if m.get("title")}
cpts = [p for p in data["points"] if "c3" in p]
out = np.zeros((len(cpts), vecs.shape[1]), dtype=np.float32)
miss = 0
for j, p in enumerate(cpts):
    i = by_url.get(p.get("u") or "") if p.get("u") else None
    if i is None:
        i = by_title.get(p.get("t") or "")
    if i is None:
        miss += 1
        continue
    out[j] = vecs[i] / (np.linalg.norm(vecs[i]) + 1e-12)
np.save(here / "orb_vecs.npy", out)
print(f"{len(cpts)} tiles, {miss} without a store vector, dim {out.shape[1]}")
