"""Section 52: regrow the compass and run its registered gates.

Pre-registered in docs/assets/52-compass-regrow/README.md, committed before
this ran. Three axes keep section 48's contrast-of-means recipe unchanged and
are imported from its runner so they cannot drift. Two are rebuilt:

  spoken-written  paired within video — a video's transcript segments against
                  that same video's note, split BY VIDEO so no video appears
                  on both sides of the fit.
  code-prose      Haiku code_bearing labels over full document text,
                  confidence-filtered, from a stratified sample.

G1 per axis: held-out AUC >= 0.80 and permutation p < 0.05 over 200 shuffles.
Compass: >= 4 of 5. G2: signature stability mean cosine >= 0.90.

    YTK_VISUAL_INDEX=off uv run python \
        experiments/sae_qwen/semantic_axes_regrow.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from paths import DATA
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_score

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from semantic_axes import auc, pole_masks  # noqa: E402

SEED = 52
N_PERM = 200
C_GRID = [0.01, 0.1, 1.0, 10.0, 100.0]
AXES = ["spoken-written", "scroll-sit", "mine-world", "fresh-settled", "code-prose"]
CONTRAST_AXES = ["scroll-sit", "mine-world", "fresh-settled"]


def unit(v: np.ndarray) -> np.ndarray:
    return v / (np.linalg.norm(v) + 1e-12)


def balance(pos: np.ndarray, neg: np.ndarray, rng) -> tuple[np.ndarray, np.ndarray]:
    """Subsample the majority pole to the minority size (registered)."""
    n = min(len(pos), len(neg))
    return (
        rng.choice(pos, n, replace=False) if len(pos) > n else pos,
        rng.choice(neg, n, replace=False) if len(neg) > n else neg,
    )


def pick_c(Xf: np.ndarray, y: np.ndarray) -> float:
    """Ridge strength by 5-fold CV on the fit half only (registered)."""
    cv = StratifiedKFold(5, shuffle=True, random_state=SEED)
    scores = [
        cross_val_score(
            LogisticRegression(C=c, max_iter=3000), Xf, y, cv=cv, scoring="roc_auc"
        ).mean()
        for c in C_GRID
    ]
    return C_GRID[int(np.argmax(scores))]


def probe(X: np.ndarray, pos: np.ndarray, neg: np.ndarray, rng, c: float | None):
    """Ridge logistic probe; axis vector = unit(coefficients)."""
    p, n = balance(pos, neg, rng)
    Xf = np.concatenate([X[p], X[n]])
    y = np.concatenate([np.ones(len(p)), np.zeros(len(n))])
    if c is None:
        c = pick_c(Xf, y)
    clf = LogisticRegression(C=c, max_iter=3000).fit(Xf, y)
    return unit(clf.coef_[0]), c


def contrast(X: np.ndarray, pos: np.ndarray, neg: np.ndarray, rng, c=None):
    return unit(X[pos].mean(0) - X[neg].mean(0)), None


def make_split(y: np.ndarray, groups: np.ndarray | None, rng) -> np.ndarray:
    """Boolean fit-half mask. Grouped axes split by group, never by item."""
    if groups is None:
        a = np.zeros(len(y), bool)
        for lab in (0, 1):
            ii = np.where(y == lab)[0]
            rng.shuffle(ii)
            a[ii[: len(ii) // 2]] = True
        return a
    keys = np.unique(groups)
    rng.shuffle(keys)
    half = set(keys[: len(keys) // 2].tolist())
    # dtype pinned: an empty selection would otherwise come back float64 and
    # the caller's `~mask` raises instead of yielding an empty mask.
    return np.array([g in half for g in groups], dtype=bool)


def run_axis(name, X, pool, y, groups, rng):
    """Fit on half, score the other half, permute labels for the null."""
    fit = probe if name not in CONTRAST_AXES else contrast
    a = make_split(y, groups, rng)
    b = ~a

    def score(mask_fit, mask_ev, labels, c):
        v, c_used = fit(X, pool[mask_fit & (labels == 1)], pool[mask_fit & (labels == 0)], rng, c)
        s_pos = X[pool[mask_ev & (labels == 1)]] @ v
        s_neg = X[pool[mask_ev & (labels == 0)]] @ v
        return v, c_used, auc(s_pos, s_neg)

    v_a, c_used, real = score(a, b, y, None)
    v_b, _, _ = score(b, a, y, c_used)

    nulls = []
    for _ in range(N_PERM):
        yp = rng.permutation(y)
        if len(np.unique(yp[a])) < 2 or len(np.unique(yp[b])) < 2:
            continue
        nulls.append(score(a, b, yp, c_used)[2])
    nulls = np.asarray(nulls)
    p = (1 + int((nulls >= real).sum())) / (1 + len(nulls))

    v_full, _ = fit(X, pool[y == 1], pool[y == 0], rng, c_used)
    return {
        "method": "contrast-of-means" if name in CONTRAST_AXES else "ridge probe",
        "grouped_split": groups is not None,
        "n_pole_a": int((y == 1).sum()),
        "n_pole_b": int((y == 0).sum()),
        "ridge_C": c_used,
        "auc": round(float(real), 4),
        "null_auc_mean": round(float(nulls.mean()), 4),
        "null_auc_p95": round(float(np.percentile(nulls, 95)), 4),
        "n_perm": len(nulls),
        "p_value": round(p, 5),
        "pass": bool(real >= 0.80 and p < 0.05),
    }, (v_full, v_a, v_b, nulls)


def register_pools(rows: list[dict]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Paired within-video: a video's segments vs that same video's note."""
    seg_by_key: dict[str, list[int]] = defaultdict(list)
    note_by_key: dict[str, int] = {}
    for i, r in enumerate(rows):
        if r["kind"] == "segment":
            seg_by_key[r["note_key"]].append(i)
        elif r["kind"] == "video":
            note_by_key[r["note_key"]] = i
    keys = sorted(set(seg_by_key) & set(note_by_key))
    pool, y, groups = [], [], []
    for k in keys:
        for i in seg_by_key[k]:
            pool.append(i)
            y.append(1)
            groups.append(k)
        pool.append(note_by_key[k])
        y.append(0)
        groups.append(k)
    return np.array(pool), np.array(y), np.array(groups)


def code_pools(rows, doc_idx, labels) -> tuple[np.ndarray, np.ndarray]:
    """Confidence-filtered Haiku code_bearing labels over doc notes."""
    pool, y = [], []
    for i in doc_idx:
        lab = labels.get(rows[i]["id"])
        # confidence is free text, not an enum: Haiku returned medium-high and
        # low-medium alongside the three asked for. The registered rule drops
        # low confidence, so match the family, not the exact string.
        conf = str((lab or {}).get("code_confidence", "")).lower()
        if not lab or "error" in lab or conf.startswith("low"):
            continue
        pool.append(i)
        y.append(1 if lab["code_bearing"] else 0)
    return np.array(pool), np.array(y)


def main() -> None:
    rows = [json.loads(x) for x in (DATA / "rows.jsonl").read_text().splitlines()]
    X = np.load(DATA / "vectors.npz")["X"].astype(np.float32)
    X /= np.maximum(np.linalg.norm(X, axis=1, keepdims=True), 1e-9)
    doc_idx = [i for i, r in enumerate(rows) if r["kind"] != "segment"]
    labels = json.loads((DATA / "register_labels.json").read_text())
    rng = np.random.default_rng(SEED)

    # three unchanged axes, recipes imported from section 48's runner
    masks = pole_masks(rows, doc_idx)
    doc_arr = np.array(doc_idx)

    specs = {}
    for name in CONTRAST_AXES:
        a, b = masks[name]
        pool = np.concatenate([doc_arr[a], doc_arr[b]])
        y = np.concatenate([np.ones(a.sum()), np.zeros(b.sum())]).astype(int)
        specs[name] = (pool, y, None)

    pool, y, groups = register_pools(rows)
    specs["spoken-written"] = (pool, y, groups)

    cpool, cy = code_pools(rows, doc_idx, labels)
    specs["code-prose"] = (cpool, cy, None)

    gate1, vecs = {}, {}
    for name in AXES:
        pool, y, groups = specs[name]
        if len(np.unique(y)) < 2 or min((y == 1).sum(), (y == 0).sum()) < 5:
            gate1[name] = {"error": "pole too small", "n_pole_a": int((y == 1).sum())}
            continue
        gate1[name], vecs[name] = run_axis(name, X, pool, y, groups, rng)
        print(name, gate1[name]["auc"], "p=", gate1[name]["p_value"], gate1[name]["pass"])

    kept = [a for a in AXES if gate1.get(a, {}).get("pass")]
    A = np.stack([vecs[a][0] for a in kept])
    AA = np.stack([vecs[a][1] for a in kept])
    AB = np.stack([vecs[a][2] for a in kept])

    pick = rng.choice(doc_arr, 200, replace=False)
    sa, sb = X[pick] @ AA.T, X[pick] @ AB.T
    cos = np.sum(sa * sb, axis=1) / (
        np.linalg.norm(sa, axis=1) * np.linalg.norm(sb, axis=1) + 1e-12
    )
    g2 = {
        "mean_cos": round(float(cos.mean()), 4),
        "p10_cos": round(float(np.percentile(cos, 10)), 4),
        "pass": bool(cos.mean() >= 0.90),
    }

    ok = [v for v in labels.values() if "error" not in v]
    indep = np.abs(A @ A.T)
    result = {
        "registered": (
            "G1 per axis: held-out AUC >= 0.80 and permutation p < 0.05 (200 shuffles); "
            "compass >= 4 of 5; G2 mean signature cos >= 0.90"
        ),
        "gate1": gate1,
        "axes_kept": kept,
        "gate2": g2,
        "axis_abs_cos": {
            f"{kept[i]}|{kept[j]}": round(float(indep[i, j]), 3)
            for i in range(len(kept))
            for j in range(i + 1, len(kept))
        },
        "labels": {
            "n": len(ok),
            "speech_register": dict(Counter(v["speech_register"] for v in ok)),
            "register_confidence": dict(Counter(v["register_confidence"] for v in ok)),
            "code_bearing": {str(k): v for k, v in Counter(v["code_bearing"] for v in ok).items()},
            "code_confidence": dict(Counter(v["code_confidence"] for v in ok)),
        },
        "verdict": "PASS" if (len(kept) >= 4 and g2["pass"]) else "FAIL",
        "register_axis_kept": "spoken-written" in kept,
        "seed": SEED,
    }
    np.savez_compressed(
        DATA / "semantic_axes_regrow.npz",
        axes=A,
        names=np.array(kept),
        half_a=AA,
        half_b=AB,
        stab_cos=cos,
        # the permutation samples themselves: the house style draws the null as
        # a distribution the observation sits inside, which a mean and a p95
        # cannot reconstruct.
        **{f"null_{a}": vecs[a][3] for a in AXES if a in vecs},
    )
    (HERE / "axes_regrow.json").write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
