"""Spike helper: copy ~/.ytk/map.json to ~/.ytk/orb-spike with a `knn` list
added to content.sphere (k nearest content points by cosine on the live
store vectors). The live map is stale against the store, so points match
store rows by url, then title, not by index. Live map.json untouched."""

import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))
from build_map import load_points

K = int(sys.argv[1]) if len(sys.argv) > 1 else 6
src = Path.home() / ".ytk" / "map.json"
out = Path.home() / ".ytk" / "orb-spike" / "map.json"

data = json.loads(src.read_text())
vecs, meta, _ = load_points()
by_url = {m["url"]: i for i, m in enumerate(meta) if m.get("url")}
by_title = {m["title"]: i for i, m in enumerate(meta) if m.get("title")}
cpts = [p for p in data["points"] if "c3" in p]
rows = []
miss = 0
for p in cpts:
    i = by_url.get(p.get("u") or "") if p.get("u") else None
    if i is None:
        i = by_title.get(p.get("t") or "")
    if i is None:
        miss += 1
    rows.append(i)
have = [j for j, i in enumerate(rows) if i is not None]
v = np.zeros((len(cpts), vecs.shape[1]))
for j in have:
    v[j] = vecs[rows[j]]
v /= np.linalg.norm(v, axis=1, keepdims=True) + 1e-12
sim = v @ v.T
np.fill_diagonal(sim, -np.inf)
missing = np.array([i is None for i in rows])
sim[missing, :] = -np.inf
sim[:, missing] = -np.inf
order = np.argsort(-sim, axis=1)[:, :K]
sims = np.take_along_axis(sim, order, axis=1)
knn = [[] if missing[j] else order[j].tolist() for j in range(len(cpts))]
data["content"]["sphere"]["knn"] = knn
data["content"]["sphere"]["knn_sim"] = [
    [] if missing[j] else np.round(sims[j], 3).tolist() for j in range(len(cpts))
]
# each thumbnail's aspect, so the atlas can pack shapes before any image loads
from PIL import Image

vault = Path.home() / "Library/Mobile Documents/iCloud~md~obsidian/Documents/Vault/second-brain"
n_ar = 0
for p in cpts:
    t = p.get("thumb")
    if not t or not (vault / t).exists():
        p["ar"] = None
        continue
    w, h = Image.open(vault / t).size
    p["ar"] = round(w / h, 3)
    n_ar += 1
print(f"aspect known for {n_ar} points")
out.write_text(json.dumps(data))
good = sims[~missing]
print(f"{len(cpts)} content points, {miss} without a store vector, k={K}")
print(
    f"neighbor cosine: median {np.median(good):.3f}, p10 {np.percentile(good, 10):.3f}, p90 {np.percentile(good, 90):.3f}"
)
for name in ("radial", "lattice"):
    pos = np.array(data["content"]["sphere"][name])
    d = np.degrees(np.arccos(np.clip(np.einsum("ij,ikj->ik", pos, pos[order]), -1, 1)))[~missing]
    print(
        f"{name}: embedding-neighbor angular distance median {np.median(d):.1f} deg, p90 {np.percentile(d, 90):.1f} deg"
    )
print(f"wrote {out}")
