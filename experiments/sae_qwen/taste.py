"""HypotheSAEs-style taste regression on note-level SAE activations.

Two targets, because the prescribed one is confounded:

  A  deliberate  r>=1 vs r=0 over the profile's content notes. In this vault
     r>=1 is 100% non-YouTube and r=0 is 100% YouTube save for 7 notes, so A
     is a medium classifier wearing a taste label. Reported with that stated.
  B  thought     r>=2 vs r==1 within the deliberate saves only. "He saved it
     AND wrote something" with the medium roughly held fixed. 27 positives.

L1 logistic regression on standardized note activations, repeated stratified
5-fold CV. A feature is reported only if its coefficient keeps one sign in
every fold of every seed and is nonzero in most of them.

    uv run --with scikit-learn python experiments/sae_qwen/taste.py --ckpt <p>
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"


def note_activations(acts_path: Path, rows: list[dict], keys: list[str]):
    z = np.load(acts_path)
    idx, val, d = z["idx"], z["val"], int(z["d_sae"])
    pos = {k: i for i, k in enumerate(keys)}
    A = np.zeros((len(keys), d), dtype=np.float32)
    cnt = np.zeros(len(keys), dtype=np.float32)
    for r, row in enumerate(rows):
        p = pos.get(row["note_key"])
        if p is None:
            continue
        A[p, idx[r]] += val[r]
        cnt[p] += 1
    return A / np.maximum(cnt[:, None], 1.0), cnt


def note_embeddings(rows, keys, X):
    pos = {k: i for i, k in enumerate(keys)}
    E = np.zeros((len(keys), X.shape[1]), dtype=np.float32)
    cnt = np.zeros(len(keys), dtype=np.float32)
    for r, row in enumerate(rows):
        p = pos.get(row["note_key"])
        if p is None:
            continue
        E[p] += X[r]
        cnt[p] += 1
    E /= np.maximum(cnt[:, None], 1.0)
    return E / np.maximum(np.linalg.norm(E, axis=1, keepdims=True), 1e-9)


def run(A, y, names, seeds=5, C=0.15):
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import StratifiedKFold
    from sklearn.preprocessing import StandardScaler

    aucs, coefs = [], []
    for s in range(seeds):
        skf = StratifiedKFold(5, shuffle=True, random_state=s)
        for tr, te in skf.split(A, y):
            sc = StandardScaler().fit(A[tr])
            m = LogisticRegression(
                l1_ratio=1.0, C=C, solver="liblinear", max_iter=4000, class_weight="balanced"
            ).fit(sc.transform(A[tr]), y[tr])
            p = m.predict_proba(sc.transform(A[te]))[:, 1]
            if len(set(y[te])) > 1:
                aucs.append(roc_auc_score(y[te], p))
            coefs.append(m.coef_[0])
    Cf = np.array(coefs)
    nz = (Cf != 0).mean(0)
    signs = np.sign(Cf)
    stable = ((signs > 0).all(0) | (signs < 0).all(0)) & (nz >= 0.8)
    order = np.argsort(-np.abs(Cf.mean(0)))
    survivors = [
        {
            "feature": int(f),
            "name": names.get(int(f)),
            "coef_mean": float(Cf[:, f].mean()),
            "coef_sd": float(Cf[:, f].std()),
            "sign": "+" if Cf[:, f].mean() > 0 else "-",
            "nonzero_frac": float(nz[f]),
        }
        for f in order
        if stable[f]
    ]
    null = []
    rng = np.random.default_rng(0)
    for s in range(3):
        yp = rng.permutation(y)
        skf = StratifiedKFold(5, shuffle=True, random_state=100 + s)
        for tr, te in skf.split(A, yp):
            sc = StandardScaler().fit(A[tr])
            m = LogisticRegression(
                l1_ratio=1.0, C=C, solver="liblinear", max_iter=4000, class_weight="balanced"
            ).fit(sc.transform(A[tr]), yp[tr])
            p = m.predict_proba(sc.transform(A[te]))[:, 1]
            if len(set(yp[te])) > 1:
                null.append(roc_auc_score(yp[te], p))

    return {
        "n": len(y),
        "n_pos": int(y.sum()),
        "auc_mean": float(np.mean(aucs)),
        "auc_null_mean": float(np.mean(null)),
        "auc_null_sd": float(np.std(null)),
        "auc_all": [round(float(x), 4) for x in aucs],
        "auc_sd": float(np.std(aucs)),
        "auc_folds": len(aucs),
        "n_stable": int(stable.sum()),
        "survivors": survivors[:25],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--C", type=float, default=0.15)
    a = ap.parse_args()

    rows = [json.loads(x) for x in (DATA / "rows.jsonl").read_text().splitlines()]
    lab = json.loads((DATA / "labels.json").read_text())
    feats = json.loads((HERE / "features.json").read_text())["features"]
    names = {f["feature"]: f.get("name") for f in feats}

    keys = [k for k, v in lab.items() if v["in_dist"]]
    A, cnt = note_activations(DATA / f"acts_{Path(a.ckpt).stem}.npz", rows, keys)
    r = np.array([lab[k]["r"] for k in keys])
    src = np.array([lab[k]["source"] for k in keys])

    out = {"checkpoint": Path(a.ckpt).name, "C": a.C, "n_notes": len(keys)}
    out["A_deliberate"] = run(A, (r >= 1).astype(int), names)
    out["A_deliberate"]["confound"] = (
        "r>=1 is non-YouTube for "
        f"{int(((r >= 1) & (src != 'youtube')).sum())}/{int((r >= 1).sum())} notes; "
        f"r==0 is YouTube for {int(((r == 0) & (src == 'youtube')).sum())}/{int((r == 0).sum())}. "
        "This target is ~equivalent to predicting the medium."
    )
    keep = r >= 1
    out["B_thought"] = run(A[keep], (r[keep] >= 2).astype(int), names)
    out["B_thought"]["note"] = "within deliberate saves only; medium roughly held fixed"

    ig = keep & (src == "instagram")
    out["C_thought_instagram"] = run(A[ig], (r[ig] >= 2).astype(int), names)
    out["C_thought_instagram"]["note"] = "Instagram only — medium fully held fixed"

    # Same folds on the raw 1024-d note embedding: does the sparse code cost
    # predictive signal relative to the space it was trained on?
    X = np.load(DATA / "vectors.npz")["X"]
    E = note_embeddings(rows, keys, X)
    out["raw_baseline"] = {
        "A_deliberate": run(E, (r >= 1).astype(int), {})["auc_mean"],
        "B_thought": run(E[keep], (r[keep] >= 2).astype(int), {})["auc_mean"],
        "C_thought_instagram": run(E[ig], (r[ig] >= 2).astype(int), {})["auc_mean"],
        "note": "L1 logistic on mean-pooled raw Qwen note vectors, identical folds",
    }

    (HERE / "taste.json").write_text(json.dumps(out, indent=1))
    print("raw-embedding baseline AUC:", json.dumps(out["raw_baseline"]))
    for k in ("A_deliberate", "B_thought", "C_thought_instagram"):
        v = out[k]
        print(
            f"{k}: n={v['n']} pos={v['n_pos']} auc={v['auc_mean']:.3f}"
            f"+-{v['auc_sd']:.3f} null={v['auc_null_mean']:.3f} stable={v['n_stable']}"
        )
    print("wrote", HERE / "taste.json")


if __name__ == "__main__":
    main()
