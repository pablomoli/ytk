"""Rung 3 of #183: bin the frozen map into cells and give each a latent identity.

Cells are a GRID x GRID lattice over the frozen Phase-12 layout. Per cell:
excess latent profile (rung-1 primitive, null built in), a label from the top
excess latent's name, the seed-stability gate (is the labeling concept the
same direction under seeds 1 and 2?), and the two disclosures #183 demands —
head-explained activation mass and OOD fraction. Ships atlas.json to the
section and to ~/.ytk (pattern: continents.json, galaxy.json, channels.json).
Read-only against the store; production search untouched.

    YTK_VISUAL_INDEX=off uv run --with torch --with matplotlib \
        python experiments/sae_qwen/atlas_bin.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "scripts"))
DATA = HERE / "data"

GRID = 12
MIN_CELL = 15
STABLE_COS = 0.5
PROT = 1597
PROT_VIDEO = "UZDiGooFs54"


def load_decoder(seed: int) -> np.ndarray:
    import torch

    blob = torch.load(HERE / "checkpoints" / f"final_d2048_k32_s{seed}.pt", map_location="cpu")
    W = blob["state"]["W_dec"].numpy()
    return W / np.maximum(np.linalg.norm(W, axis=1, keepdims=True), 1e-9)


def join_points(points: list[dict], docs: list[dict]) -> list[int | None]:
    def rel(p: str) -> str:
        i = p.find("second-brain/")
        return (p[i:] if i >= 0 else p).removesuffix(".md")

    paths, byvid = {}, {}
    for i, r in enumerate(docs):
        if r["source_path"]:
            paths.setdefault(rel(r["source_path"]), i)
        if r["kind"] == "video":
            byvid[r["id"]] = i
    out = []
    for q in points:
        p = (q.get("p") or "").removesuffix(".md")
        if p in paths:
            out.append(paths[p])
            continue
        m = re.search(r"v=([\w-]+)", q.get("u") or "")
        out.append(byvid.get(m.group(1)) if m else None)
    return out


def mass_per_latent(idx, val, row_ids: np.ndarray, d_sae: int = 2048) -> np.ndarray:
    sel_idx = idx[row_ids].ravel()
    sel_val = val[row_ids].ravel()
    keep = sel_val > 0
    return np.bincount(sel_idx[keep], weights=sel_val[keep], minlength=d_sae) / max(len(row_ids), 1)


def main() -> None:
    from plot_assets import excess_profile

    rows = [json.loads(x) for x in (DATA / "rows.jsonl").read_text().splitlines()]
    docs = [r for r in rows if r["kind"] != "segment"]
    doc_rows = [i for i, r in enumerate(rows) if r["kind"] != "segment"]
    mp = json.loads((Path.home() / ".ytk" / "map.json").read_text())
    points = mp["points"]
    galaxy = json.loads((Path.home() / ".ytk" / "e32-galaxy.json").read_text())
    theme_label = {p["theme"]: p["label"] for p in galaxy["planets"]}
    features = json.loads((HERE / "features.json").read_text())
    named = {f["feature"]: f.get("name") for f in features["features"]}
    head = {f["feature"] for f in sorted(features["features"], key=lambda t: -t["freq"])[:100]}

    acts = {s: np.load(DATA / f"acts_final_d2048_k32_s{s}.npz") for s in (0, 1, 2)}
    dec = {s: load_decoder(s) for s in (0, 1, 2)}

    joined = join_points(points, docs)  # index into docs
    # map doc index -> row index in the full acts arrays
    doc2act = np.asarray(doc_rows)

    xs = np.array([q["x"] for q in points])
    ys = np.array([q["y"] for q in points])
    x_edges = np.linspace(xs.min(), xs.max() + 1e-9, GRID + 1)
    y_edges = np.linspace(ys.min(), ys.max() + 1e-9, GRID + 1)
    cx = np.clip(np.digitize(xs, x_edges) - 1, 0, GRID - 1)
    cy = np.clip(np.digitize(ys, y_edges) - 1, 0, GRID - 1)

    # The protagonist is NOT on the frozen layout (map generated 2026-08-11,
    # note captured 08-14). Its cell is estimated by a 10-NN vote among joined
    # notes in Qwen space and shipped as an estimate, never as a position.
    prot_cell, prot_exact = None, False
    for q, a, b in zip(points, cx, cy):
        if PROT_VIDEO in (q.get("u") or ""):
            prot_cell, prot_exact = [int(a), int(b)], True
    if prot_cell is None:
        from ytk import store

        got = store._videos_collection().get(where={"video_id": PROT_VIDEO}, include=["embeddings"])
        if got["ids"]:
            v = np.asarray(got["embeddings"][0], np.float32)
            v /= np.linalg.norm(v)
            X = np.load(DATA / "vectors.npz")["X"]
            j_idx = [(i, j) for i, j in enumerate(joined) if j is not None]
            sims = X[doc2act[[j for _, j in j_idx]]] @ v
            nn = np.argsort(-sims)[:10]
            votes = Counter((int(cx[j_idx[k][0]]), int(cy[j_idx[k][0]])) for k in nn)
            prot_cell = list(votes.most_common(1)[0][0])

    idx0, val0 = acts[0]["idx"], acts[0]["val"]
    n_acts = len(idx0)
    cells = []
    gate = {"stable_05": 0, "stable_08": 0, "strict_05": 0, "n": 0}
    for a in range(GRID):
        for b in range(GRID):
            in_cell = (cx == a) & (cy == b)
            n_pts = int(in_cell.sum())
            if n_pts == 0:
                continue
            act_rows = [doc2act[joined[i]] for i in np.where(in_cell)[0] if joined[i] is not None]
            act_rows = np.asarray(sorted(set(act_rows)), dtype=int)
            ood = 1 - len(act_rows) / n_pts
            if len(act_rows) < MIN_CELL:
                continue

            member = np.zeros(n_acts, bool)
            member[act_rows] = True
            prof = excess_profile(idx0, val0, member, 2048, n_null=200, seed=44)
            exc = prof["excess"]
            outside = np.abs(exc) > np.maximum(np.abs(prof["null_lo"]), prof["null_hi"])
            order = np.argsort(-exc)[:5]
            top0 = int(order[0])

            # gate: is the concept labeling this cell recovered under seeds 1/2?
            # strict = the seed's own top-1 matches s0's direction; relaxed = any
            # of the seed's top-5 does (near-ties in excess reorder freely)
            tops, cos_top1, cos_top5 = [], [], []
            for s in (1, 2):
                m_s = mass_per_latent(acts[s]["idx"], acts[s]["val"], act_rows)
                base_s = mass_per_latent(
                    acts[s]["idx"], acts[s]["val"], np.arange(len(acts[s]["idx"]))
                )
                exc_s = m_s - base_s
                top5_s = np.argsort(-exc_s)[:5]
                tops.append(int(top5_s[0]))
                cos_top1.append(float(dec[0][top0] @ dec[s][top5_s[0]]))
                cos_top5.append(float(max(dec[0][top0] @ dec[s][t] for t in top5_s)))
            stable05 = all(c >= STABLE_COS for c in cos_top5)
            stable08 = all(c >= 0.8 for c in cos_top5)
            strict05 = all(c >= STABLE_COS for c in cos_top1)
            gate["n"] += 1
            gate["stable_05"] += stable05
            gate["stable_08"] += stable08
            gate["strict_05"] += strict05

            cell_mass = mass_per_latent(idx0, val0, act_rows)
            head_mass = float(sum(cell_mass[f] for f in head) / max(cell_mass.sum(), 1e-9))
            themes = Counter(
                q.get("th") for q, m_ in zip(points, in_cell) if m_ and q.get("th") is not None
            )
            theme = themes.most_common(1)[0][0] if themes else None

            cells.append(
                {
                    "cell": [a, b],
                    "x0": round(float(x_edges[a]), 4),
                    "y0": round(float(y_edges[b]), 4),
                    "x1": round(float(x_edges[a + 1]), 4),
                    "y1": round(float(y_edges[b + 1]), 4),
                    "n_points": n_pts,
                    "n_scored": len(act_rows),
                    "ood_frac": round(float(ood), 4),
                    "head_mass": round(head_mass, 4),
                    "label_latent": top0,
                    "label": named.get(top0),
                    "label_excess": round(float(exc[top0]), 5),
                    "label_outside_null": bool(outside[top0]),
                    "top5": [
                        {
                            "latent": int(f),
                            "name": named.get(int(f)),
                            "excess": round(float(exc[f]), 5),
                            "outside_null": bool(outside[f]),
                        }
                        for f in order
                    ],
                    "seed_tops": tops,
                    "seed_cos_top1": [round(c, 4) for c in cos_top1],
                    "seed_cos_top5": [round(c, 4) for c in cos_top5],
                    "stable_05": stable05,
                    "stable_08": stable08,
                    "strict_05": strict05,
                    "theme": theme,
                    "theme_label": theme_label.get(theme),
                    "protagonist_excess": round(float(exc[PROT]), 5),
                    "protagonist_outside_null": bool(outside[PROT]),
                }
            )

    out = {
        "grid": GRID,
        "min_cell_scored": MIN_CELL,
        "stable_cos": STABLE_COS,
        "x_edges": [round(float(v), 4) for v in x_edges],
        "y_edges": [round(float(v), 4) for v in y_edges],
        "n_map_points": len(points),
        "n_joined": sum(1 for j in joined if j is not None),
        "gate": gate,
        "protagonist": {
            "latent": PROT,
            "cell": prot_cell,
            "on_frozen_layout": prot_exact,
            "cell_method": "map position"
            if prot_exact
            else "10-NN vote estimate (note postdates the frozen layout)",
        },
        "excess_null": "200 size-matched random doc subsets per cell (excess_profile)",
        "cells": cells,
    }
    (HERE / "atlas.json").write_text(json.dumps(out, indent=1))
    (Path.home() / ".ytk" / "atlas.json").write_text(json.dumps(out))
    print(
        f"cells kept: {len(cells)} of {GRID * GRID} | joined {out['n_joined']}/{len(points)} | "
        f"gate: {gate['stable_05']}/{gate['n']} stable at cos {STABLE_COS} (top-5 match), "
        f"{gate['stable_08']} at 0.8, strict top-1: {gate['strict_05']} | "
        f"protagonist cell: {prot_cell} (exact: {prot_exact})"
    )
    lab = Counter(c["label_latent"] for c in cells)
    print("distinct cell labels:", len(lab), "| most common:", lab.most_common(3))


if __name__ == "__main__":
    main()
