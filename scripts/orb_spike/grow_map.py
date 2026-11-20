"""Spike: seat the library notes that have no tile onto the served sphere.
Reads map.656.json + orb_vecs.656.npy (the snapshot), writes map.json +
orb_vecs.npy (the grown sphere). The live map and the vault are only read.

  python grow_map.py --measure   holdout + displacement table, writes nothing
  python grow_map.py             grow and write"""

import json
import sys
import urllib.request
from collections import Counter
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))
from build_map import CONTENT_CATS, load_points

from ytk.spheremap import GROW_ITERS, GROW_K, OCCL_DEG, grow, lattice, score, seat

HERE = Path.home() / ".ytk" / "orb-spike"
VAULT = Path.home() / "Library/Mobile Documents/iCloud~md~obsidian/Documents/Vault/second-brain"
measure = "--measure" in sys.argv

data = json.loads((HERE / "map.656.json").read_text())
old_vecs = np.load(HERE / "orb_vecs.656.npy").astype(float)
cpts = [p for p in data["points"] if "c3" in p]
sphere = data["content"]["sphere"]
pos = np.array(sphere["radial"], dtype=float)
n0 = len(cpts)
assert pos.shape[0] == n0 == old_vecs.shape[0]
vecless = np.linalg.norm(old_vecs, axis=1) < 0.5
print(f"snapshot: {n0} tiles, {int(vecless.sum())} without a store vector")


def ang(a, b):
    return np.degrees(np.arccos(np.clip(np.einsum("ij,ij->i", a, b), -1, 1)))


def nn_deg(p):
    d = np.clip(p @ p.T, -1, 1)
    np.fill_diagonal(d, -1)
    return np.degrees(np.arccos(d.max(axis=1)))


def neighbor_deg(p, v, rows, k=6):
    """Median angle from each row's tile to its k nearest notes by meaning."""
    sim = v @ v.T
    np.fill_diagonal(sim, -np.inf)
    order = np.argsort(-sim, axis=1)[:, :k]
    d = np.degrees(np.arccos(np.clip(np.einsum("ij,ikj->ik", p, p[order]), -1, 1)))
    return d[rows]


if measure:
    rng = np.random.default_rng(7)
    ok = np.flatnonzero(~vecless)
    print(
        "\nholdout: pull tiles out of the snapshot, seat them again, compare with their fitted place"
    )
    for label, held in (
        ("random 146", rng.choice(ok, 146, replace=False)),
        ("newest 146 by publish date", ok[np.argsort([cpts[i].get("d") or "" for i in ok])[-146:]]),
    ):
        keep = np.setdiff1d(np.arange(n0), held)
        p, v = pos[keep], old_vecs[keep]
        seeded = []
        for i in held:
            s = seat(p, v, old_vecs[i])
            seeded.append(s)
            p, v = np.vstack([p, s]), np.vstack([v, old_vecs[i]])
        err = ang(np.array(seeded), pos[held])
        near = ang(pos[keep][np.argmax(old_vecs[keep] @ old_vecs[held].T, axis=0)], pos[held])
        rand = ang(rng.normal(size=(len(held), 3)) / 1, pos[held]) if False else None
        r = rng.normal(size=(len(held), 3))
        r /= np.linalg.norm(r, axis=1, keepdims=True)
        print(
            f"  {label}: seat error median {np.median(err):.1f} deg, p90 {np.percentile(err, 90):.1f}"
            f" | nearest-note-only {np.median(near):.1f} / {np.percentile(near, 90):.1f}"
            f" | random {np.median(ang(r, pos[held])):.1f} / {np.percentile(ang(r, pos[held]), 90):.1f}"
        )
    print(f"  (tile spacing in the snapshot: median nearest tile {np.median(nn_deg(pos)):.1f} deg)")

# --- the notes to seat: library notes with no tile, in the order they were added
lib = json.loads(urllib.request.urlopen("http://localhost:6969/api/library?n=5000").read())["items"]
have = {p["p"] for p in cpts}
added_of = {it["path"]: it["added"] for it in lib}
SRC = {
    "youtube": "youtube",
    "instagram": "instagram",
    "tiktok": "tiktok",
    "web": "web",
    "screenshot": "screenshots",
}
missing = [it for it in lib if it["path"] not in have]
print(
    f"\nlibrary {len(lib)} notes, {len(missing)} without a tile: {dict(Counter(it['source'] for it in missing))}"
)
todo = [it for it in missing if SRC.get(it["source"]) in CONTENT_CATS]
todo.reverse()  # the library lists newest first
todo.sort(key=lambda it: it["added"])

vecs, meta, _ = load_points()
by_path, by_url, by_title = {}, {}, {}
vault_root = VAULT.parent
for i, m in enumerate(meta):
    sp = m.get("path") or ""
    if sp:
        rel = sp[sp.find("second-brain/") :] if "second-brain/" in sp else sp
        by_path.setdefault(rel, i)
    if m.get("url"):
        by_url.setdefault(m["url"], i)
    if m.get("title"):
        by_title.setdefault(m["title"], i)
new, lost = [], []
for it in todo:
    i = by_path.get(it["path"])
    if i is None and it.get("url"):
        i = by_url.get(it["url"])
    if i is None:
        i = by_title.get(it["title"])
    (new if i is not None else lost).append((it, i))
print(f"content notes to seat: {len(todo)}, found in the store: {len(new)}, not found: {len(lost)}")
for it, _ in lost[:8]:
    print("   not in store:", it["source"], it["title"][:70])
new_vecs = np.array([vecs[i] / (np.linalg.norm(vecs[i]) + 1e-12) for _, i in new])

if measure:
    print(f"\ngrowth: {n0} + {len(new)} tiles; how far the old tiles move, by relaxation length")
    width = 2 * OCCL_DEG
    for iters in (0, 20, 40, 60, 100, 200, 600):
        g = grow(pos, old_vecs, new_vecs, iters=iters)
        mv = ang(g[:n0], pos)
        nn = nn_deg(g)
        print(
            f"  iters {iters:3d}: old tiles moved median {np.median(mv):.2f} deg, p90 {np.percentile(mv, 90):.2f}, max {mv.max():.1f}"
            f" | nearest tile under one width ({width:.1f} deg): {100 * (nn < width).mean():.0f}%, under half: {int((nn < width / 2).sum())}"
        )
    g = grow(pos, old_vecs, new_vecs)
    allv = np.vstack([old_vecs, new_vecs])
    rows_old = np.flatnonzero(~vecless)
    rows_new = np.arange(n0, len(g))
    d_old0 = neighbor_deg(pos[rows_old], old_vecs[rows_old], np.arange(len(rows_old)))
    keep = np.concatenate([rows_old, rows_new])
    d_all = neighbor_deg(g[keep], allv[keep], np.arange(len(keep)))
    rng = np.random.default_rng(3)
    r = rng.normal(size=(len(rows_new), 3))
    r /= np.linalg.norm(r, axis=1, keepdims=True)
    gr = g.copy()
    gr[rows_new] = r
    d_rand = neighbor_deg(gr[keep], allv[keep], np.arange(len(keep)))
    print(
        f"\nangle from a tile to its 6 nearest notes by meaning (iters {GROW_ITERS}, k {GROW_K}):"
    )
    print(
        f"  snapshot, old tiles:        median {np.median(d_old0):.1f} deg, p90 {np.percentile(d_old0, 90):.1f}"
    )
    print(
        f"  grown, old tiles:           median {np.median(d_all[: len(rows_old)]):.1f} deg, p90 {np.percentile(d_all[: len(rows_old)], 90):.1f}"
    )
    print(
        f"  grown, new tiles:           median {np.median(d_all[len(rows_old) :]):.1f} deg, p90 {np.percentile(d_all[len(rows_old) :], 90):.1f}"
    )
    print(
        f"  new tiles placed at random: median {np.median(d_rand[len(rows_old) :]):.1f} deg, p90 {np.percentile(d_rand[len(rows_old) :], 90):.1f}"
    )
    sys.exit(0)

# --- grow and write
from PIL import Image

g = grow(pos, old_vecs, new_vecs)
allv = np.vstack([old_vecs, new_vecs])
c3_old = np.array([p["c3"] for p in cpts], dtype=float)
themes = [p.get("th", -1) for p in cpts]
c3s = list(c3_old)
placed_v = old_vecs.copy()
n_thumb = 0
for (it, _), nv in zip(new, new_vecs):
    sim = placed_v @ nv
    top = np.argsort(-sim)[:GROW_K]
    votes = Counter()
    for j in top:
        votes[themes[j]] += float(sim[j])
    th = votes.most_common(1)[0][0]
    w = np.maximum(sim[top], 1e-6)
    c3 = (w[:, None] * np.array([c3s[j] for j in top])).sum(axis=0) / w.sum()
    pt = {
        "t": it["title"],
        "c": SRC[it["source"]],
        "u": it.get("url") or "",
        "d": it.get("date") or "",
        "p": it["path"],
        "th": int(th),
        "c3": [round(float(x), 4) for x in c3],
    }
    t = it.get("thumbnail")
    if t and (VAULT / t).exists():
        w_, h_ = Image.open(VAULT / t).size
        pt["thumb"], pt["ar"] = t, round(w_ / h_, 3)
        n_thumb += 1
    data["points"].append(pt)
    themes.append(int(th))
    c3s.append(c3)
    placed_v = np.vstack([placed_v, nv])
for p in data["points"]:
    if "c3" in p:
        p["a"] = added_of.get(p["p"]) or p.get("d") or ""
n = len(g)
sim = allv @ allv.T
np.fill_diagonal(sim, -np.inf)
dead = np.linalg.norm(allv, axis=1) < 0.5
sim[dead, :] = -np.inf
sim[:, dead] = -np.inf
order = np.argsort(-sim, axis=1)[:, :6]
sims = np.take_along_axis(sim, order, axis=1)
rnd = lambda a: [[round(float(x), 4) for x in row] for row in a]
sphere["radial"] = rnd(g)
sphere["lattice"] = rnd(lattice(themes, g))
sphere["knn"] = [[] if dead[j] else order[j].tolist() for j in range(n)]
sphere["knn_sim"] = [[] if dead[j] else np.round(sims[j], 3).tolist() for j in range(n)]
live = ~dead
sphere["scores"] = {
    "radial": score(allv[live], g[live]),
    "lattice": score(allv[live], np.array(sphere["lattice"])[live]),
}
(HERE / "map.json").write_text(json.dumps(data))
np.save(HERE / "orb_vecs.npy", allv.astype(np.float32))
print(
    f"wrote {n} tiles ({n - n0} new, {n_thumb} with a cover); themes of the new: {dict(Counter(themes[n0:]).most_common(6))}"
)
print("scores:", {k: round(v["trustworthiness"], 4) for k, v in sphere["scores"].items()})
