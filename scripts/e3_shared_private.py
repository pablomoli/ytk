"""E3 — shared / private decomposition of the two lenses.

Sections 22-24 established that the Qwen production space groups this corpus by
topic and the gemma-2-2b + gemma-scope SAE fingerprint space groups it by
voice/register. E3 asks the formal version of "derive something from both":
regularized linear CCA on the paired 532-note universe, split into a SHARED
subspace and two private residuals, with a permutation null deciding how many
shared dimensions are real. Reference: SPLICE (arXiv 2408.12091), linear first.

    uv run --with matplotlib --with scikit-learn python scripts/e3_shared_private.py
    uv run --with matplotlib --with scikit-learn python scripts/e3_shared_private.py --figs-only

Analysis lands in docs/assets/25-shared-private/shared-private.json; --figs-only
re-renders the figures from it without touching Chroma.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
SAE = REPO / "docs" / "assets" / "18-sae-fingerprints"
LENS22 = REPO / "docs" / "assets" / "22-two-lenses"
OUTDIR = REPO / "docs" / "assets" / "25-shared-private"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from plot_assets import (
    BG,
    BLUE,
    CYAN,
    DIM,
    DPI,
    FRAME,
    GOLD,
    MARGIN,
    MUTED,
    PANEL,
    PURPLE,
    RED,
    TEXT,
    TICK_SIZE,
    figure,
    frame_panels,
    panel_title,
    style_axes,
    verdict,
)

PCA_SWEEP = (30, 50, 100)
PRIMARY_D = 50
ALPHAS = (1e-4, 1e-3, 1e-2, 3e-2, 0.1, 0.3, 1.0)
N_FOLDS = 5
N_PERM = 200
N_REPORT = 25  # canonical dimensions carried through the null
MSWEEP = (1, 2, 5, 10, 25)  # shared directions removed in the payoff sweep
SEED = 0


# --- corpus -----------------------------------------------------------------
def corpus_meta():
    """One extra Chroma read: document length and fine-grained medium per id."""
    from ytk import store

    length, medium = {}, {}
    vids = store._videos_collection().get(include=["documents", "metadatas"])
    for doc, meta in zip(vids["documents"], vids["metadatas"]):
        cid = str(meta.get("video_id", ""))
        length[cid] = len(doc or "")
        medium[cid] = "youtube"
    mem = store._memories_collection().get(include=["documents", "metadatas"])
    for doc, meta, cid in zip(mem["documents"], mem["metadatas"], mem["ids"]):
        length[cid] = len(doc or "")
        parts = str(meta.get("source_path", "")).split("second-brain/")[-1].split("/")
        medium[cid] = parts[1] if len(parts) > 1 and parts[0] == "sources" else "other"
    return length, medium


# --- regularized CCA --------------------------------------------------------
def inv_sqrt(C, floor=1e-10):
    w, V = np.linalg.eigh(C)
    w = np.maximum(w, floor)
    return (V / np.sqrt(w)) @ V.T


def rcca(Xa, Ya, alpha):
    """Classical CCA with shrinkage toward a scaled identity on both covariances."""
    n = len(Xa)
    Cxx = Xa.T @ Xa / n
    Cyy = Ya.T @ Ya / n
    Cxy = Xa.T @ Ya / n
    Cxx = Cxx + alpha * (np.trace(Cxx) / len(Cxx)) * np.eye(len(Cxx))
    Cyy = Cyy + alpha * (np.trace(Cyy) / len(Cyy)) * np.eye(len(Cyy))
    ix, iy = inv_sqrt(Cxx), inv_sqrt(Cyy)
    U, S, Vt = np.linalg.svd(ix @ Cxy @ iy)
    return ix @ U, iy @ Vt.T, S


def corr(a, b):
    a = a - a.mean()
    b = b - b.mean()
    d = np.linalg.norm(a) * np.linalg.norm(b)
    return float(a @ b / d) if d > 0 else 0.0


def colcorr(A, B):
    """Column-wise Pearson correlation of two equally shaped matrices."""
    A = A - A.mean(0)
    B = B - B.mean(0)
    den = np.linalg.norm(A, axis=0) * np.linalg.norm(B, axis=0)
    return np.where(den > 0, (A * B).sum(0) / np.maximum(den, 1e-12), 0.0)


def cv_spectrum(Xp, Yp, folds, alpha, m):
    """Mean over folds of the per-dimension held-out canonical correlation."""
    out = np.zeros((len(folds), m))
    for f, (tr, te) in enumerate(folds):
        Xt, Yt = Xp[tr], Yp[tr]
        mx, my = Xt.mean(0), Yt.mean(0)
        Wx, Wy, _ = rcca(Xt - mx, Yt - my, alpha)
        out[f] = colcorr((Xp[te] - mx) @ Wx[:, :m], (Yp[te] - my) @ Wy[:, :m])
    return out.mean(0)


def fit_with_selection(Xp, Yp, folds, m):
    """Pick alpha by CV, return (alpha, held-out spectrum, per-alpha criterion)."""
    grid = {}
    for a in ALPHAS:
        grid[a] = cv_spectrum(Xp, Yp, folds, a, m)
    best = max(ALPHAS, key=lambda a: grid[a][:5].mean())
    return best, grid[best], {str(a): grid[a].tolist() for a in ALPHAS}


# --- label statistics -------------------------------------------------------
def eta2(score, labels, rng=None, n_shuf=200):
    """Between-group share of variance, with the shuffled expectation for the
    same number of groups (eta2 is biased upward by group count)."""
    score = np.asarray(score, float)
    groups = [np.where(np.asarray(labels) == g)[0] for g in sorted(set(labels))]
    tot = float(((score - score.mean()) ** 2).sum())

    def raw(s):
        return float(sum(len(g) * (s[g].mean() - s.mean()) ** 2 for g in groups)) / tot

    val = raw(score)
    if rng is None:
        return val, None
    null = float(np.mean([raw(rng.permutation(score)) for _ in range(n_shuf)]))
    return val, null


def auc(score, positive):
    """Rank AUC of score separating positive from the rest."""
    score = np.asarray(score, float)
    pos = np.asarray(positive, bool)
    order = np.argsort(score)
    ranks = np.empty(len(score))
    ranks[order] = np.arange(1, len(score) + 1)
    np_, nn = int(pos.sum()), int((~pos).sum())
    if np_ == 0 or nn == 0:
        return 0.5
    return float((ranks[pos].sum() - np_ * (np_ + 1) / 2) / (np_ * nn))


def orthonormal(dirs):
    return np.linalg.qr(dirs)[0]


def var_share(V, B):
    """Fraction of V's total (centered) variance living in the span of B."""
    Vc = V - V.mean(0)
    tot = float((Vc**2).sum())
    return float((np.linalg.norm(Vc @ B) ** 2) / tot) if tot > 0 else 0.0


def purity(labels, srcs):
    tot = 0
    for c in set(labels):
        idx = np.where(np.asarray(labels) == c)[0]
        tot += Counter(srcs[j] for j in idx).most_common(1)[0][1]
    return tot / len(labels)


# --- SAE feature names ------------------------------------------------------
def feature_names(want):
    """18.x token-probed names first, then 22's cache, then Neuronpedia for gaps."""
    cached: dict[int, dict] = {}

    def harvest(obj):
        if isinstance(obj, dict):
            if "index" in obj and obj.get("name"):
                try:
                    cached.setdefault(int(obj["index"]), {"name": str(obj["name"]).strip()})
                except (TypeError, ValueError):
                    pass
            for v in obj.values():
                harvest(v)
        elif isinstance(obj, list):
            for v in obj:
                harvest(v)

    for f in ["tag-regions.json", "cone-features.json", "road-diffs.json"]:
        harvest(json.loads((SAE / f).read_text()))
    for k, v in json.loads((LENS22 / "feature-names.json").read_text()).items():
        cached.setdefault(int(k), {"name": v, "auto": True})

    cache_path = OUTDIR / "feature-names.json"
    local = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    for k, v in local.items():
        cached.setdefault(int(k), {"name": v, "auto": True})

    gaps = sorted({int(i) for i in want if int(i) not in cached})
    if gaps:
        import time
        import urllib.request

        fetched = {}
        for i in range(0, len(gaps), 40):
            body = json.dumps(
                [
                    {"modelId": "gemma-2-2b", "layer": "20-gemmascope-res-16k", "index": str(ix)}
                    for ix in gaps[i : i + 40]
                ]
            ).encode()
            req = urllib.request.Request(
                "https://www.neuronpedia.org/api/features",
                data=body,
                headers={"Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    for row in json.loads(r.read()):
                        expl = row.get("explanations") or []
                        if expl:
                            fetched[int(row["index"])] = str(expl[0].get("description", "")).strip()
            except Exception as e:  # names are decoration, not data
                print("neuronpedia chunk failed:", e)
            time.sleep(1.0)
        local.update({str(k): v for k, v in fetched.items()})
        cache_path.write_text(json.dumps(local, indent=1))
        for k, v in fetched.items():
            cached.setdefault(k, {"name": v, "auto": True})
    return cached


# --- analysis ---------------------------------------------------------------
def analyse():
    from plot_two_lenses import align, gemma_space
    from sklearn.decomposition import PCA
    from sklearn.metrics import adjusted_rand_score
    from sklearn.model_selection import KFold

    from ytk.config import load_config
    from ytk.synthesis import choose_k, cluster_embeddings

    OUTDIR.mkdir(exist_ok=True)
    F, Q, ids, names, srcs, qwen_theme, snapshot = align()
    X, L = gemma_space(F)
    Qn = Q / np.linalg.norm(Q, axis=1, keepdims=True)
    n = len(ids)
    cfg = load_config()
    k = choose_k(n, cfg.interest)
    rng = np.random.default_rng(SEED)

    length, medium_map = corpus_meta()
    loglen = np.log1p(np.array([length[i] for i in ids], dtype=float))
    medium = [medium_map.get(i, "other") for i in ids]
    is_ig = np.array([s == "instagram" for s in srcs])

    qorder = sorted(set(qwen_theme))
    qlab = np.array([qorder.index(t) for t in qwen_theme])
    glab = np.array(cluster_embeddings(X, k))
    relab = np.array(cluster_embeddings(Qn, k))
    ceiling = adjusted_rand_score(relab, qlab)
    ari_null = float(
        np.mean([adjusted_rand_score(rng.permutation(glab), qlab) for _ in range(200)])
    )

    folds = list(KFold(n_splits=N_FOLDS, shuffle=True, random_state=SEED).split(np.arange(n)))
    sweep = {}
    for d in PCA_SWEEP:
        m = min(N_REPORT, d)
        # PCA is fit on all 532 and shared by the observed run and every
        # permutation, so the null is calibrated on identical footing.
        px = PCA(n_components=d, random_state=SEED).fit(Qn)
        py = PCA(n_components=d, random_state=SEED).fit(X)
        Xp, Yp = px.transform(Qn), py.transform(X)
        alpha, obs, grid = fit_with_selection(Xp, Yp, folds, m)
        print(f"d={d} alpha={alpha} heldout[:4]={np.round(obs[:4], 3)}")

        perm = np.zeros((N_PERM, m))
        for p in range(N_PERM):
            idx = rng.permutation(n)
            a_p, s_p, _ = fit_with_selection(Xp, Yp[idx], folds, m)
            perm[p] = s_p
        p95 = np.percentile(perm, 95, axis=0)
        pvals = [(1 + int((perm[:, j] >= obs[j]).sum())) / (N_PERM + 1) for j in range(m)]
        survive = int(np.argmax(~(obs > p95))) if not np.all(obs > p95) else m

        Wx, Wy, S = rcca(Xp - Xp.mean(0), Yp - Yp.mean(0), alpha)
        sweep[str(d)] = {
            "alpha": alpha,
            "alpha_grid": grid,
            "in_sample": S[:m].tolist(),
            "heldout": obs.tolist(),
            "perm_mean": perm.mean(0).tolist(),
            "perm_p95": p95.tolist(),
            "perm_max": perm.max(0).tolist(),
            "p_values": pvals,
            "n_survive": survive,
            "explained_var": [
                float(px.explained_variance_ratio_.sum()),
                float(py.explained_variance_ratio_.sum()),
            ],
        }
        if d == PRIMARY_D:
            # Stratified null: shuffle the pairing only within a medium. If the
            # shared subspace were medium, this null would stay high.
            groups = [np.where(np.array(medium) == g)[0] for g in sorted(set(medium))]
            strat = np.zeros((N_PERM, m))
            for p in range(N_PERM):
                idx = np.arange(n)
                for g in groups:
                    idx[g] = rng.permutation(g)
                _, s_p, _ = fit_with_selection(Xp, Yp[idx], folds, m)
                strat[p] = s_p
            sweep[str(d)]["strat_perm_mean"] = strat.mean(0).tolist()
            sweep[str(d)]["strat_perm_p95"] = np.percentile(strat, 95, axis=0).tolist()
            sweep[str(d)]["strat_perm_max"] = strat.max(0).tolist()
            primary = {
                "px": px,
                "py": py,
                "Xp": Xp,
                "Yp": Yp,
                "Wx": Wx,
                "Wy": Wy,
                "alpha": alpha,
                "m": survive,
            }

    # per-fold PCA control: is the shared-PCA shortcut inflating the spectrum?
    m = min(N_REPORT, PRIMARY_D)
    inner = np.zeros((N_FOLDS, m))
    for f, (tr, te) in enumerate(folds):
        px = PCA(n_components=PRIMARY_D, random_state=SEED).fit(Qn[tr])
        py = PCA(n_components=PRIMARY_D, random_state=SEED).fit(X[tr])
        A, B = px.transform(Qn), py.transform(X)
        mx, my = A[tr].mean(0), B[tr].mean(0)
        Wx, Wy, _ = rcca(A[tr] - mx, B[tr] - my, primary["alpha"])
        P = (A[te] - mx) @ Wx[:, :m]
        R = (B[te] - my) @ Wy[:, :m]
        inner[f] = [corr(P[:, j], R[:, j]) for j in range(m)]
    sweep[str(PRIMARY_D)]["heldout_foldwise_pca"] = inner.mean(0).tolist()

    # --- interpret the surviving shared dimensions --------------------------
    msur = max(primary["m"], 1)
    Xc = primary["Xp"] - primary["Xp"].mean(0)
    Yc = primary["Yp"] - primary["Yp"].mean(0)
    Sq = Xc @ primary["Wx"][:, :msur]
    Sg = Yc @ primary["Wy"][:, :msur]
    Sq /= Sq.std(0)
    Sg /= Sg.std(0)
    shared = (Sq + Sg) / 2

    # SAE-space direction of each shared dim, for the loadings readout
    Dg = primary["py"].components_.T @ primary["Wy"][:, :msur]  # 16384 x msur
    Lz = (L - L.mean(0)) / (L.std(0) + 1e-9)

    dims, want = [], set()
    for j in range(msur):
        # orient by medium so the sign of every other correlation is readable
        sign = 1.0 if corr(shared[:, j], is_ig.astype(float)) >= 0 else -1.0
        sc = shared[:, j] * sign
        e_med, e_med0 = eta2(sc, medium, rng)
        e_th, e_th0 = eta2(sc, qwen_theme, rng)
        # Lz columns carry population std, so their norm is sqrt(n).
        r_feat = (Lz * (sc - sc.mean())[:, None]).sum(0) / (
            np.sqrt(((sc - sc.mean()) ** 2).sum()) * np.sqrt(len(sc)) + 1e-12
        )
        top = np.argsort(-np.abs(r_feat))[:10]
        want.update(int(i) for i in top)
        dims.append(
            {
                "dim": j + 1,
                "heldout_r": sweep[str(PRIMARY_D)]["heldout"][j],
                "in_sample_r": sweep[str(PRIMARY_D)]["in_sample"][j],
                "r_instagram": corr(sc, is_ig.astype(float)),
                "auc_instagram": auc(sc, is_ig),
                "r_loglen": corr(sc, loglen),
                "r_loglen_qwen_side": corr(Sq[:, j] * sign, loglen),
                "r_loglen_sae_side": corr(Sg[:, j] * sign, loglen),
                "eta2_medium": e_med,
                "eta2_medium_shuffled": e_med0,
                "eta2_theme": e_th,
                "eta2_theme_shuffled": e_th0,
                "sae_loadings": [
                    {
                        "index": int(i),
                        "r": round(float(r_feat[i]), 3),
                        "w": round(float(Dg[i, j] * sign), 4),
                    }
                    for i in top
                ],
            }
        )
    fname = feature_names(want)
    for drec in dims:
        for f in drec["sae_loadings"]:
            rec = fname.get(f["index"])
            f["name"] = rec["name"] if rec else None
            f["auto"] = bool(rec and rec.get("auto"))

    # medium/length baselines for context
    base = {
        "eta2_medium_of_loglen": eta2(loglen, medium)[0],
        "auc_instagram_of_loglen": auc(loglen, is_ig),
        "medium_counts": dict(Counter(medium)),
        "src_counts": dict(Counter(srcs)),
    }

    # --- how much of each space does the shared subspace occupy? ------------
    Dq_all = primary["px"].components_.T @ primary["Wx"]  # 1024 x d
    Dg_all = primary["py"].components_.T @ primary["Wy"]  # 16384 x d
    vshare = {"qwen": [], "sae": [], "qwen_pca": [], "sae_pca": [], "random": []}
    evx = primary["px"].explained_variance_ratio_
    evy = primary["py"].explained_variance_ratio_
    grand = np.random.default_rng(7)
    for mm in range(1, N_REPORT + 1):
        vshare["qwen"].append(var_share(Qn, orthonormal(Dq_all[:, :mm])))
        vshare["sae"].append(var_share(X, orthonormal(Dg_all[:, :mm])))
        vshare["qwen_pca"].append(float(evx[:mm].sum()))
        vshare["sae_pca"].append(float(evy[:mm].sum()))
        vshare["random"].append(
            float(
                np.mean(
                    [
                        var_share(Qn, orthonormal(grand.normal(size=(Qn.shape[1], mm))))
                        for _ in range(3)
                    ]
                )
            )
        )

    # --- payoff: re-cluster the private residuals ---------------------------
    def residual(V, dirs):
        B = orthonormal(dirs)
        R = V - (V @ B) @ B.T
        return R / np.maximum(np.linalg.norm(R, axis=1, keepdims=True), 1e-9)

    def battery(lab):
        return {
            "purity": purity(lab, srcs),
            "purity_medium5": purity(lab, medium),
            "ari_themes": adjusted_rand_score(lab, qlab),
            "ari_recluster": adjusted_rand_score(lab, relab),
            "ari_sae": adjusted_rand_score(lab, glab),
            "eta2_loglen": eta2(loglen, lab)[0],
        }

    msweep = {}
    for mm in MSWEEP:
        qlab_p = np.array(cluster_embeddings(residual(Qn, Dq_all[:, :mm]), k))
        xlab_p = np.array(cluster_embeddings(residual(X, Dg_all[:, :mm]), k))
        ctrl = []
        for s in range(5):
            g = np.random.default_rng(100 + s).normal(size=(Qn.shape[1], mm))
            ctrl.append(battery(np.array(cluster_embeddings(residual(Qn, g), k))))
        msweep[str(mm)] = {
            "qwen_private": battery(qlab_p),
            "sae_private": battery(xlab_p),
            "random_control": ctrl,
            "var_share_qwen": vshare["qwen"][mm - 1],
            "var_share_sae": vshare["sae"][mm - 1],
        }

    Dq = Dq_all[:, :msur]
    qp_lab = np.array(cluster_embeddings(residual(Qn, Dq), k))
    xp_lab = np.array(cluster_embeddings(residual(X, Dg), k))
    if str(msur) not in msweep:
        msweep[str(msur)] = {
            "qwen_private": battery(qp_lab),
            "sae_private": battery(xp_lab),
            "random_control": [
                battery(
                    np.array(
                        cluster_embeddings(
                            residual(
                                Qn, np.random.default_rng(100 + s).normal(size=(Qn.shape[1], msur))
                            ),
                            k,
                        )
                    )
                )
                for s in range(5)
            ],
            "var_share_qwen": vshare["qwen"][msur - 1],
            "var_share_sae": vshare["sae"][msur - 1],
        }
    ctrl = msweep[str(msur)]["random_control"]

    payoff = {
        "k": k,
        "n_removed": msur,
        "var_share": vshare,
        "m_sweep": msweep,
        "qwen_private": battery(qp_lab),
        "sae_private": battery(xp_lab),
        "random_direction_control": ctrl,
        "reference": {
            "purity_qwen_themes": purity(qlab, srcs),
            "purity_qwen_recluster": purity(relab, srcs),
            "purity_sae": purity(glab, srcs),
            "purity_baseline": Counter(srcs).most_common(1)[0][1] / n,
            "purity_medium5_qwen_themes": purity(qlab, medium),
            "purity_medium5_sae": purity(glab, medium),
            "purity_medium5_baseline": Counter(medium).most_common(1)[0][1] / n,
            "ari_cross": adjusted_rand_score(glab, qlab),
            "ari_ceiling": ceiling,
            "ari_null": ari_null,
            "eta2_loglen_qwen_themes": eta2(loglen, qlab)[0],
            "eta2_loglen_sae": eta2(loglen, glab)[0],
        },
    }

    ex_med = [x["eta2_medium"] - x["eta2_medium_shuffled"] for x in dims]
    ex_thm = [x["eta2_theme"] - x["eta2_theme_shuffled"] for x in dims]
    prediction = {
        "n_dims": len(dims),
        "mean_excess_eta2_medium": float(np.mean(ex_med)),
        "mean_excess_eta2_theme": float(np.mean(ex_thm)),
        "n_medium_dominant": int(sum(a > b for a, b in zip(ex_med, ex_thm))),
        "max_excess_eta2_medium": float(np.max(ex_med)),
        "argmax_medium_dim": int(np.argmax(ex_med) + 1),
        "max_abs_r_loglen": float(np.max([abs(x["r_loglen"]) for x in dims])),
    }

    out = {
        "n_notes": n,
        "k": k,
        "snapshot_at": snapshot["generated_at"][:10],
        "primary_d": PRIMARY_D,
        "n_perm": N_PERM,
        "n_folds": N_FOLDS,
        "alphas": list(ALPHAS),
        "sweep": sweep,
        "shared_dims": dims,
        "e2_prediction": prediction,
        "baselines": base,
        "payoff": payoff,
    }
    (OUTDIR / "shared-private.json").write_text(json.dumps(out, indent=1))
    return out


# --- figures ----------------------------------------------------------------
def hdr_fix(fig):
    """This render env falls back past CMU widths — nudge the kicker clear."""
    fig.texts[1].set_x(MARGIN + 0.092)


def dark_legend(ax, handles, loc="upper right", ncol=1, fontsize=9, anchor=None):
    leg = ax.legend(
        handles=handles,
        loc=loc,
        ncol=ncol,
        fontsize=fontsize,
        facecolor=PANEL,
        edgecolor=FRAME,
        labelcolor=TEXT,
        framealpha=1.0,
        borderpad=0.6,
        **({"bbox_to_anchor": anchor} if anchor else {}),
    )
    leg.set_zorder(8)
    return leg


def short(t, n=44):
    t = " ".join(str(t).split())
    return t if len(t) <= n else t[: n - 1] + "…"


def fig01(d):
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    pri = d["sweep"][str(d["primary_d"])]
    m = len(pri["heldout"])
    xs = np.arange(1, m + 1)
    fig, top = figure(
        16.6,
        6.9,
        1,
        "how much is genuinely shared",
        "Canonical correlations between the topic space and the voice space, "
        "against a permutation null",
        meta=f"{d['n_notes']} paired notes · PCA {d['primary_d']}+{d['primary_d']} · ridge CCA, "
        f"alpha picked by the same 5-fold CV · {d['n_perm']} pairing permutations, each "
        f"re-selecting alpha and re-running the whole CV",
    )
    hdr_fix(fig)
    axa = fig.add_axes([0.065, 0.150, 0.430, top - 0.230])
    axa.fill_between(xs, pri["perm_mean"], pri["perm_p95"], color=DIM, alpha=0.65, zorder=1)
    axa.plot(xs, pri["perm_max"], color=MUTED, linewidth=0.9, linestyle=":", zorder=2)
    axa.plot(xs, pri["strat_perm_max"], color=RED, linewidth=1.1, linestyle="-.", zorder=3)
    axa.plot(
        xs,
        pri["in_sample"],
        color=PURPLE,
        linewidth=1.4,
        linestyle="--",
        marker="s",
        markersize=3.6,
        zorder=3,
    )
    axa.plot(xs, pri["heldout"], color=GOLD, linewidth=1.8, marker="o", markersize=4.6, zorder=4)
    ns = pri["n_survive"]
    if ns:
        axa.axvspan(0.5, ns + 0.5, color=GOLD, alpha=0.07, zorder=0)
        axa.text(
            ns / 2 + 0.5,
            0.36,
            f"all {ns} tested dimensions clear the null",
            color=GOLD,
            fontsize=10.5,
            ha="center",
            va="center",
        )
    axa.set_xticks(np.arange(1, m + 1, 2))
    axa.set_xlim(0.5, m + 0.5)
    axa.set_ylim(-0.05, 1.46)
    axa.axhline(0, color=FRAME, linewidth=0.8)
    style_axes(axa)
    axa.set_xlabel("canonical dimension", fontsize=TICK_SIZE)
    axa.set_ylabel("canonical correlation", fontsize=TICK_SIZE)
    axa.annotate(
        f"medium alone buys {pri['strat_perm_mean'][0]:.2f} here —\nand nothing after it",
        xy=(1.15, pri["strat_perm_max"][0]),
        xytext=(3.4, 0.60),
        color=RED,
        fontsize=9,
        va="center",
        arrowprops={"arrowstyle": "-", "color": RED, "linewidth": 0.8},
    )
    panel_title(axa, "the spectrum — the held-out line is the real one", width=60)
    dark_legend(
        axa,
        [
            Line2D(
                [],
                [],
                color=GOLD,
                linewidth=1.8,
                marker="o",
                markersize=4.6,
                label="5-fold held-out (the real number)",
            ),
            Line2D(
                [],
                [],
                color=PURPLE,
                linewidth=1.4,
                linestyle="--",
                marker="s",
                markersize=3.6,
                label="in-sample, all 532",
            ),
            Patch(facecolor=DIM, alpha=0.65, label="permutation null, mean to 95th pct"),
            Line2D(
                [],
                [],
                color=MUTED,
                linewidth=0.9,
                linestyle=":",
                label="permutation null, maximum of 200",
            ),
            Line2D(
                [],
                [],
                color=RED,
                linewidth=1.1,
                linestyle="-.",
                label="within-medium permutation, maximum of 200",
            ),
        ],
        loc="upper left",
        ncol=2,
        fontsize=8.5,
    )

    hues = {30: CYAN, 50: GOLD, 100: RED}
    axb = fig.add_axes([0.555, 0.150, 0.170, top - 0.230])
    for dd in PCA_SWEEP:
        s = d["sweep"][str(dd)]
        mm = len(s["heldout"])
        axb.plot(np.arange(1, mm + 1), s["heldout"], color=hues[dd], linewidth=1.5, zorder=4)
        axb.plot(
            np.arange(1, mm + 1),
            s["perm_p95"],
            color=hues[dd],
            linewidth=1.0,
            linestyle=":",
            alpha=0.85,
            zorder=2,
        )
    axb.set_xlim(0.5, m + 0.5)
    axb.set_ylim(-0.05, 1.46)
    axb.axhline(0, color=FRAME, linewidth=0.8)
    style_axes(axb)
    axb.set_xlabel("canonical dimension", fontsize=TICK_SIZE)
    axb.set_ylabel("held-out canonical correlation", fontsize=TICK_SIZE)
    panel_title(axb, "sensitivity to the PCA width", width=28)
    dark_legend(
        axb,
        [
            Line2D(
                [],
                [],
                color=hues[dd],
                linewidth=1.5,
                label=f"PCA {dd} (alpha {d['sweep'][str(dd)]['alpha']:g})",
            )
            for dd in PCA_SWEEP
        ]
        + [Line2D([], [], color=MUTED, linewidth=1.0, linestyle=":", label="its own null p95")],
        loc="upper left",
        fontsize=8,
    )

    v = d["payoff"]["var_share"]
    axc = fig.add_axes([0.790, 0.150, 0.165, top - 0.230])
    axc.plot(xs, v["qwen_pca"][:m], color=MUTED, linewidth=1.2, linestyle="--", zorder=2)
    axc.plot(xs, v["qwen"][:m], color=GOLD, linewidth=1.8, zorder=4)
    axc.plot(xs, v["sae"][:m], color=BLUE, linewidth=1.8, zorder=4)
    axc.plot(xs, v["random"][:m], color=DIM, linewidth=1.2, zorder=3)
    axc.set_xlim(0.5, m + 0.5)
    axc.set_ylim(0, 0.62)
    style_axes(axc)
    axc.set_xlabel("shared dimensions kept", fontsize=TICK_SIZE)
    axc.set_ylabel("share of the view's variance", fontsize=TICK_SIZE)
    panel_title(axc, "and how big is that subspace?", width=28)
    dark_legend(
        axc,
        [
            Line2D([], [], color=MUTED, linewidth=1.2, linestyle="--", label="top-m Qwen PCA"),
            Line2D([], [], color=GOLD, linewidth=1.8, label="Qwen topic space"),
            Line2D([], [], color=BLUE, linewidth=1.8, label="SAE voice space"),
            Line2D([], [], color=DIM, linewidth=1.2, label="m random directions"),
        ],
        loc="upper left",
        fontsize=8,
    )
    fig.text(
        MARGIN,
        0.038,
        "held-out correlation near 0.95 against a null whose 200-permutation maximum never "
        "reaches 0.23: the two encoders share a large, real linear subspace",
        color=MUTED,
        fontsize=8.5,
    )
    verdict(
        fig,
        "VERDICT: 25/25 dims beat the null — the shared subspace is nearly each view's principal subspace",
    )
    return fig, "01-shared-spectrum.png"


def loading_panel(ax, rec, hue_pos, hue_neg, n=8):
    """Named SAE features of one shared dimension, names set inside the bars."""
    feats = rec["sae_loadings"][:n]
    ys = np.arange(len(feats))[::-1]
    for y, f in zip(ys, feats):
        r = f["r"]
        ax.barh(
            y,
            abs(r),
            height=0.72,
            color=hue_pos if r >= 0 else hue_neg,
            alpha=0.30,
            edgecolor=hue_pos if r >= 0 else hue_neg,
            linewidth=0.8,
        )
        star = "*" if f.get("auto") else ""
        ax.text(
            0.012,
            y,
            f"#{f['index']} {short(f['name'] or 'unnamed', 46)}{star}",
            color=TEXT,
            fontsize=8.2,
            va="center",
        )
        ax.text(abs(r) + 0.012, y, f"{r:+.2f}", color=MUTED, fontsize=8.2, va="center")
    from matplotlib.patches import Patch

    ax.set_yticks([])
    ax.set_ylim(-0.7, len(feats) - 0.3)
    ax.set_xlim(0, 1.0)
    style_axes(ax)
    ax.tick_params(axis="y", length=0)
    dark_legend(
        ax,
        [
            Patch(facecolor=hue_pos, alpha=0.30, edgecolor=hue_pos, label="fires with the axis"),
            Patch(facecolor=hue_neg, alpha=0.30, edgecolor=hue_neg, label="fires against it"),
        ],
        loc="lower right",
        fontsize=8,
    )


def fig02(d):
    from matplotlib.patches import Patch

    dims = d["shared_dims"][:10]
    fig, top = figure(
        16.6,
        8.0,
        2,
        "what the shared axis is made of",
        "The E2 prediction: shared structure should be medium, not subject matter",
        meta="eta-squared = share of the shared score's variance explained by the label, minus the "
        "shuffled expectation for the same group count · medium has 5 levels, themes 17 · "
        "signs oriented so Instagram is positive",
    )
    hdr_fix(fig)
    axa = fig.add_axes([MARGIN + 0.032, 0.150, 0.415, top - 0.230])
    xs = np.arange(len(dims))
    w = 0.27
    med = [x["eta2_medium"] - x["eta2_medium_shuffled"] for x in dims]
    thm = [x["eta2_theme"] - x["eta2_theme_shuffled"] for x in dims]
    lng = [x["r_loglen"] ** 2 for x in dims]
    axa.bar(xs - w, thm, w, color=GOLD)
    axa.bar(xs, med, w, color=BLUE)
    axa.bar(xs + w, lng, w, color=CYAN)
    for xo, vals, hue in ((-w, thm, GOLD), (0, med, BLUE), (w, lng, CYAN)):
        for x, v in zip(xs, vals):
            if v >= 0.02:
                axa.text(
                    x + xo,
                    v + 0.014,
                    f"{v:.2f}",
                    color=hue,
                    fontsize=7.6,
                    ha="center",
                    rotation=90,
                    va="bottom",
                )
    axa.set_xticks(xs, [str(x["dim"]) for x in dims])
    axa.set_ylim(0, 1.06)
    style_axes(axa)
    axa.set_xlabel("shared canonical dimension", fontsize=TICK_SIZE)
    axa.set_ylabel("variance of the shared score explained", fontsize=TICK_SIZE)
    panel_title(axa, "is each shared dimension topic, medium, or length?", width=60)
    dark_legend(
        axa,
        [
            Patch(facecolor=GOLD, label="Qwen theme, 17-way — excess eta-squared"),
            Patch(facecolor=BLUE, label="capture medium, 5-way — excess eta-squared"),
            Patch(facecolor=CYAN, label="log note length — r-squared"),
        ],
        loc="upper right",
        fontsize=8.5,
    )

    # the cleanest topic axis is the largest theme-minus-medium contrast, not
    # simply the largest theme eta-squared
    top_thm = max(dims, key=lambda x: x["eta2_theme"] - x["eta2_medium"])
    top_med = max(dims, key=lambda x: x["eta2_medium"] - x["eta2_medium_shuffled"])
    h = (top - 0.230 - 0.075) / 2
    axb = fig.add_axes([0.545, 0.150 + h + 0.075, 0.410, h])
    axc = fig.add_axes([0.545, 0.150, 0.410, h])
    loading_panel(axb, top_thm, GOLD, RED)
    loading_panel(axc, top_med, BLUE, RED)
    axc.set_xlabel(
        "|correlation| of the SAE feature's log-activation with the shared score",
        fontsize=TICK_SIZE,
    )
    axb.tick_params(axis="x", labelbottom=False)
    panel_title(
        axb,
        f"shared {top_thm['dim']} — the purest topic axis (theme eta-squared "
        f"{top_thm['eta2_theme']:.2f}, medium {top_thm['eta2_medium']:.2f})",
        width=72,
    )
    panel_title(
        axc,
        f"shared {top_med['dim']} — most medium-loaded (medium eta-squared "
        f"{top_med['eta2_medium']:.2f}, length r {top_med['r_loglen']:+.2f})",
        width=72,
    )
    fig.text(
        MARGIN,
        0.038,
        f"* auto-named from Neuronpedia, unprobed hypotheses (18.x) · context: log length alone "
        f"separates Instagram from the rest at AUC "
        f"{d['baselines']['auc_instagram_of_loglen']:.2f} and carries eta-squared "
        f"{d['baselines']['eta2_medium_of_loglen']:.2f} across the five media, so medium and "
        f"length are not independent regressors here",
        color=MUTED,
        fontsize=8.5,
    )
    verdict(
        fig, "VERDICT: shared is topic, not medium — E2's prediction refuted (eta2 0.25 vs 0.05)"
    )
    return fig, "02-medium-or-topic.png"


def fig03(d):
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    p = d["payoff"]
    ref = p["reference"]
    ctrl = p["random_direction_control"]
    fig, top = figure(
        16.6,
        6.9,
        3,
        "the payoff test",
        "Strip the shared subspace out of the topic space — does the topic axis get cleaner?",
        meta=f"identical choose_k (k={p['k']}) and seeded KMeans everywhere · "
        f"{p['n_removed']} surviving shared directions removed, carrying "
        f"{p['var_share']['qwen'][p['n_removed'] - 1]:.0%} of the Qwen variance · control removes "
        f"the same number of random directions (5 seeds)",
    )
    hdr_fix(fig)
    cm = float(np.mean([c["purity"] for c in ctrl]))
    clo = float(min(c["purity"] for c in ctrl))
    chi = float(max(c["purity"] for c in ctrl))
    rows = [
        ("majority baseline", ref["purity_baseline"], DIM),
        ("Qwen production themes", ref["purity_qwen_themes"], GOLD),
        ("Qwen re-clustered", ref["purity_qwen_recluster"], GOLD),
        (f"Qwen minus {p['n_removed']} random dirs", cm, PURPLE),
        ("Qwen-PRIVATE (shared removed)", p["qwen_private"]["purity"], CYAN),
        ("SAE-PRIVATE (shared removed)", p["sae_private"]["purity"], BLUE),
        ("SAE voice clusters", ref["purity_sae"], BLUE),
    ]
    axa = fig.add_axes([MARGIN + 0.145, 0.155, 0.245, top - 0.235])
    ys = np.arange(len(rows))[::-1]
    axa.barh(ys, [v for _, v, _ in rows], color=[c for *_, c in rows], height=0.6)
    for y, (_, v, _) in zip(ys, rows):
        axa.text(
            v + (0.038 if v == cm else 0.010), y, f"{v:.3f}", color=TEXT, fontsize=9, va="center"
        )
    axa.plot([clo, chi], [ys[3], ys[3]], color=TEXT, linewidth=1.4, zorder=5)
    axa.axvline(ref["purity_baseline"], color=RED, linewidth=1.0, linestyle="--", zorder=1)
    axa.set_yticks(ys, [r[0] for r in rows])
    axa.set_xlim(0, 1.44)
    style_axes(axa)
    axa.set_xticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    axa.set_xlabel("source purity (Instagram vs YouTube/web)", fontsize=TICK_SIZE)
    panel_title(axa, "does removing the shared axis de-bias the themes?", width=46)
    dark_legend(
        axa,
        [
            Line2D([], [], color=TEXT, linewidth=1.4, label="control range, 5 seeds"),
            Line2D([], [], color=RED, linewidth=1.0, linestyle="--", label="majority baseline"),
        ],
        loc="upper right",
        fontsize=8,
    )

    axb = fig.add_axes([0.575, 0.155, 0.165, top - 0.235])
    bars = [
        ("shuffled null", ref["ari_null"], DIM),
        ("SAE voice", ref["ari_cross"], BLUE),
        (f"minus {p['n_removed']} random", float(np.mean([c["ari_themes"] for c in ctrl])), PURPLE),
        ("Qwen-PRIVATE", p["qwen_private"]["ari_themes"], CYAN),
        ("Qwen re-cluster\n(measured ceiling)", ref["ari_ceiling"], GOLD),
    ]
    ys = np.arange(len(bars))[::-1]
    axb.barh(ys, [v for _, v, _ in bars], color=[c for *_, c in bars], height=0.55)
    for y, (_, v, _) in zip(ys, bars):
        axb.text(v + 0.008, y, f"{v:.3f}", color=TEXT, fontsize=8.5, va="center")
    lo = min(c["ari_themes"] for c in ctrl)
    hi = max(c["ari_themes"] for c in ctrl)
    axb.plot([lo, hi], [ys[2], ys[2]], color=TEXT, linewidth=1.4, zorder=5)
    axb.axvline(ref["ari_ceiling"], color=GOLD, linewidth=1.0, linestyle=":", zorder=1)
    axb.set_yticks(ys, [b[0] for b in bars])
    axb.set_xlim(0, 0.62)
    style_axes(axb)
    axb.set_xlabel("ARI vs the production themes", fontsize=TICK_SIZE)
    panel_title(axb, "what it costs in topical agreement", width=30)
    dark_legend(
        axb,
        [
            Line2D([], [], color=TEXT, linewidth=1.4, label="control range, 5 seeds"),
            Line2D([], [], color=GOLD, linewidth=1.0, linestyle=":", label="measured ceiling"),
            Patch(facecolor=DIM, label="label-shuffled null"),
        ],
        loc="upper right",
        fontsize=7.5,
    )

    axc = fig.add_axes([0.795, 0.155, 0.160, top - 0.235])
    ms = [int(m) for m in sorted(p["m_sweep"], key=int)]
    qp = [p["m_sweep"][str(m)]["qwen_private"]["ari_themes"] for m in ms]
    cm = [
        float(np.mean([c["ari_themes"] for c in p["m_sweep"][str(m)]["random_control"]]))
        for m in ms
    ]
    clo = [min(c["ari_themes"] for c in p["m_sweep"][str(m)]["random_control"]) for m in ms]
    chi = [max(c["ari_themes"] for c in p["m_sweep"][str(m)]["random_control"]) for m in ms]
    axc.fill_between(ms, clo, chi, color=PURPLE, alpha=0.25, zorder=1)
    axc.plot(ms, cm, color=PURPLE, linewidth=1.5, marker="s", markersize=4.5, zorder=3)
    axc.plot(ms, qp, color=CYAN, linewidth=1.8, marker="o", markersize=5, zorder=4)
    axc.axhline(ref["ari_ceiling"], color=GOLD, linewidth=1.0, linestyle=":", zorder=2)
    axc.set_xscale("log")
    axc.set_xticks(ms, [str(m) for m in ms])
    axc.set_ylim(0, 0.62)
    style_axes(axc)
    axc.set_xlabel("shared directions removed", fontsize=TICK_SIZE)
    axc.set_ylabel("ARI vs the production themes", fontsize=TICK_SIZE)
    panel_title(axc, "the damage starts at the first direction", width=30)
    dark_legend(
        axc,
        [
            Line2D(
                [], [], color=CYAN, linewidth=1.8, marker="o", markersize=5, label="Qwen-private"
            ),
            Line2D(
                [],
                [],
                color=PURPLE,
                linewidth=1.5,
                marker="s",
                markersize=4.5,
                label="random directions (mean, range)",
            ),
            Line2D([], [], color=GOLD, linewidth=1.0, linestyle=":", label="measured ceiling"),
        ],
        loc="upper right",
        fontsize=7.5,
    )
    lo_all = min(min(c["ari_themes"] for c in p["m_sweep"][str(m)]["random_control"]) for m in ms)
    hi_all = max(max(c["ari_themes"] for c in p["m_sweep"][str(m)]["random_control"]) for m in ms)
    fig.text(
        MARGIN,
        0.038,
        "the random-direction control also exposes how loose the ceiling is: removing arbitrary "
        f"directions from a 1024-d space leaves ARI against the production themes anywhere in a "
        f"{lo_all:.2f}-{hi_all:.2f} band, so 0.335 is one draw, not a fixed bar",
        color=MUTED,
        fontsize=8.5,
    )
    verdict(
        fig,
        "VERDICT: stripping shared destroys topic with no de-bias — the derivation door is closed",
    )
    return fig, "03-payoff.png"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--figs-only", action="store_true")
    args = ap.parse_args()
    if args.figs_only:
        d = json.loads((OUTDIR / "shared-private.json").read_text())
    else:
        d = analyse()
        print(
            json.dumps(
                {
                    "survive": {k: v["n_survive"] for k, v in d["sweep"].items()},
                    "payoff": d["payoff"]["qwen_private"],
                },
                indent=1,
            )
        )
    for f in (fig01, fig02, fig03):
        fig, name = f(d)
        frame_panels(fig)
        out = OUTDIR / name
        fig.savefig(out, dpi=DPI, facecolor=BG)
        print(f"wrote {out.relative_to(REPO)}  ({out.stat().st_size // 1024}KB)")
        plt.close(fig)


if __name__ == "__main__":
    main()
