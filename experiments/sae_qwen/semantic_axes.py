"""Section 48: build the five semantic axes and run their registered gates.

Pre-registered in docs/assets/48-semantic-compass/README.md (committed
before this ran). Axes are contrast-of-means over cached doc unit vectors;
G1 = per-axis held-out AUC >= 0.80 (shuffle null < 0.60), G2 = split-half
signature stability mean cosine >= 0.90 over 200 random notes.

    YTK_VISUAL_INDEX=off uv run --with torch python \
        experiments/sae_qwen/semantic_axes.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
from paths import DATA

HERE = Path(__file__).resolve().parent
SEED = 48
CODE_RE = re.compile(r"```|\bdef |\(\) \{|=>")

AXES = ["spoken-written", "scroll-sit", "mine-world", "fresh-settled", "code-prose"]


def auc(pos: np.ndarray, neg: np.ndarray) -> float:
    """Rank-based ROC AUC, no sklearn."""
    scores = np.concatenate([pos, neg])
    ranks = scores.argsort().argsort().astype(float) + 1
    r_pos = ranks[: len(pos)].sum()
    return float((r_pos - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def map_dates(rows: list[dict], doc_idx: list[int]) -> dict[int, str]:
    """doc row index -> ISO date, via the same join atlas_bin uses."""
    mp = json.loads((Path.home() / ".ytk" / "map.json").read_text())

    def rel(p: str) -> str:
        i = p.find("second-brain/")
        return (p[i:] if i >= 0 else p).removesuffix(".md")

    paths, byvid = {}, {}
    for i in doc_idx:
        r = rows[i]
        if r["source_path"]:
            paths.setdefault(rel(r["source_path"]), i)
        if r["kind"] == "video":
            byvid[r["id"]] = i
    out: dict[int, str] = {}
    for q in mp["points"]:
        d = q.get("d")
        if not d:
            continue
        p = (q.get("p") or "").removesuffix(".md")
        if p in paths:
            out.setdefault(paths[p], d)
            continue
        m = re.search(r"v=([\w-]+)", q.get("u") or "")
        if m and m.group(1) in byvid:
            out.setdefault(byvid[m.group(1)], d)
    return out


def pole_masks(rows: list[dict], doc_idx: list[int]) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    src = np.array([rows[i]["source"] for i in doc_idx])
    kind = np.array([rows[i]["kind"] for i in doc_idx])
    text_code = np.array([bool(CODE_RE.search(rows[i]["text"])) for i in doc_idx])
    dates = map_dates(rows, doc_idx)
    date_arr = np.array([dates.get(i, "") for i in doc_idx])
    dated = date_arr != ""
    d_sorted = np.sort(date_arr[dated])
    q20, q80 = d_sorted[int(len(d_sorted) * 0.2)], d_sorted[int(len(d_sorted) * 0.8)]

    ingested = np.isin(src, ["youtube", "web", "instagram", "tiktok"])
    return {
        "spoken-written": ((src == "youtube") & (kind == "video"), src == "web"),
        "scroll-sit": (np.isin(src, ["instagram", "tiktok"]), np.isin(src, ["youtube", "web"])),
        "mine-world": ((src == "vault") & (kind == "memory"), ingested),
        "fresh-settled": (dated & (date_arr >= q80), dated & (date_arr <= q20)),
        "code-prose": (text_code, ~text_code),
    }


def contrast(X: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    v = X[a].mean(0) - X[b].mean(0)
    return v / (np.linalg.norm(v) + 1e-12)


def main() -> None:
    rows = [json.loads(x) for x in (DATA / "rows.jsonl").read_text().splitlines()]
    doc_idx = [i for i, r in enumerate(rows) if r["kind"] != "segment"]
    X = np.load(DATA / "vectors.npz")["X"].astype(np.float32)[doc_idx]
    X /= np.maximum(np.linalg.norm(X, axis=1, keepdims=True), 1e-9)

    masks = pole_masks(rows, doc_idx)
    rng = np.random.default_rng(SEED)
    n = len(X)

    axes_full, gate1, half_axes = {}, {}, {"A": {}, "B": {}}
    for name, (a, b) in masks.items():
        ia, ib = np.where(a)[0], np.where(b)[0]
        rng.shuffle(ia)
        rng.shuffle(ib)
        ha, hb = len(ia) // 2, len(ib) // 2
        v_fit = contrast(X, ia[:ha], ib[:hb])
        pos, neg = X[ia[ha:]] @ v_fit, X[ib[hb:]] @ v_fit
        real_auc = auc(pos, neg)
        # shuffle null: same fit/eval sizes, labels permuted
        pool = np.concatenate([ia, ib])
        nulls = []
        for _ in range(50):
            perm = rng.permutation(pool)
            pa, pb = perm[: len(ia)], perm[len(ia) :]
            v0 = contrast(X, pa[: len(pa) // 2], pb[: len(pb) // 2])
            nulls.append(auc(X[pa[len(pa) // 2 :]] @ v0, X[pb[len(pb) // 2 :]] @ v0))
        gate1[name] = {
            "n_pole_a": len(ia),
            "n_pole_b": len(ib),
            "auc": round(real_auc, 4),
            "null_auc_mean": round(float(np.mean(nulls)), 4),
            "null_auc_p95": round(float(np.percentile(nulls, 95)), 4),
            "pass": bool(real_auc >= 0.80 and np.percentile(nulls, 95) < 0.60),
        }
        axes_full[name] = contrast(X, ia, ib)
        half_axes["A"][name] = contrast(X, ia[:ha], ib[:hb])
        half_axes["B"][name] = contrast(X, ia[ha:], ib[hb:])

    kept = [a for a in AXES if gate1[a]["pass"]]
    A = np.stack([axes_full[a] for a in kept])
    AA = np.stack([half_axes["A"][a] for a in kept])
    AB = np.stack([half_axes["B"][a] for a in kept])

    # G2: signature stability on 200 random notes
    pick = rng.choice(n, 200, replace=False)
    sa, sb = X[pick] @ AA.T, X[pick] @ AB.T
    cos = np.sum(sa * sb, axis=1) / (
        np.linalg.norm(sa, axis=1) * np.linalg.norm(sb, axis=1) + 1e-12
    )
    g2 = {
        "mean_cos": round(float(cos.mean()), 4),
        "p10_cos": round(float(np.percentile(cos, 10)), 4),
        "pass": bool(cos.mean() >= 0.90),
    }

    indep = np.abs(A @ A.T)
    result = {
        "registered": "G1 per-axis AUC >= 0.80 (null p95 < 0.60); G2 mean signature cos >= 0.90",
        "gate1": gate1,
        "axes_kept": kept,
        "gate2": g2,
        "axis_abs_cos": {
            f"{kept[i]}|{kept[j]}": round(float(indep[i, j]), 3)
            for i in range(len(kept))
            for j in range(i + 1, len(kept))
        },
        "verdict": "PASS" if (len(kept) >= 4 and g2["pass"]) else "FAIL",
        "seed": SEED,
    }
    np.savez_compressed(
        DATA / "semantic_axes.npz",
        axes=A,
        names=np.array(kept),
        half_a=AA,
        half_b=AB,
        stab_cos=cos,
    )
    (HERE / "axes.json").write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
