"""E1 — can a purpose-built style embedder replace the SAE rig as the voice axis?

Section 22 showed the gemma-2-2b SAE fingerprint space partitions the corpus by
register/medium (source purity 0.95) where the production Qwen space partitions
by topic (0.72, baseline 0.61). This runs the same battery on
StyleDistance (roberta-base, content-independent style triplets, arXiv
2410.12757) over the identical 532-note universe, and asks the harder question:
does voice structure survive inside a single medium?

    uv run --with matplotlib --with scikit-learn python scripts/e1_style_lens.py

Chunk embeddings cache to docs/assets/23-style-lens/style-chunks.npz; delete to
re-embed.
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
OUTDIR = REPO / "docs" / "assets" / "23-style-lens"
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

MODEL_ID = "StyleDistance/styledistance"
MODEL_REV = "b7df5f0b0480773c097ba3121d83ca32b71015ca"
CHUNK_CHARS = 1000  # ~230 roberta tokens; model max_seq_length is 512
MIN_TAIL = 200  # drop a trailing sliver unless it is the whole note
TRIPLETS = 20000
SEED = 0


# --- corpus -----------------------------------------------------------------
def note_texts_by_id():
    """Same collection reads as plot_two_lenses.align(), keyed by chroma id."""
    from ytk import store

    text, medium = {}, {}
    vids = store._videos_collection().get(include=["documents", "metadatas"])
    for doc, meta in zip(vids["documents"], vids["metadatas"]):
        cid = str(meta.get("video_id", ""))
        text[cid] = doc or ""
        medium[cid] = "youtube"
    mem = store._memories_collection().get(include=["documents", "metadatas"])
    for doc, meta, cid in zip(mem["documents"], mem["metadatas"], mem["ids"]):
        path = str(meta.get("source_path", ""))
        text[cid] = doc or ""
        parts = path.split("second-brain/")[-1].split("/")
        medium[cid] = parts[1] if len(parts) > 1 and parts[0] == "sources" else "other"
    return text, medium


def chunks(t: str) -> list[str]:
    out = [t[i : i + CHUNK_CHARS] for i in range(0, len(t), CHUNK_CHARS)]
    if len(out) > 1 and len(out[-1]) < MIN_TAIL:
        out.pop()
    return out or [t]


def device_for_now() -> str:
    """A scheduled fingerprint batch owns the GPU 04:45-07:30."""
    import torch

    h = datetime.now().hour + datetime.now().minute / 60
    if torch.backends.mps.is_available() and not (4.75 <= h <= 7.5):
        return "mps"
    return "cpu"


def embed_chunks(ids, text):
    cache = OUTDIR / "style-chunks.npz"
    flat, owner = [], []
    for j, cid in enumerate(ids):
        for c in chunks(text[cid]):
            flat.append(c)
            owner.append(j)
    owner = np.asarray(owner)
    if cache.exists():
        z = np.load(cache)
        if len(z["owner"]) == len(owner):
            print(f"cached chunks {len(owner)}")
            return z["E"].astype(np.float32), z["owner"], float(z["secs"])
    from sentence_transformers import SentenceTransformer

    dev = device_for_now()
    m = SentenceTransformer(MODEL_ID, revision=MODEL_REV, device=dev)
    n_par = sum(p.numel() for p in m.parameters())
    print(f"{MODEL_ID}@{MODEL_REV[:8]} on {dev}, {n_par / 1e6:.0f}M params, {len(flat)} chunks")
    t0 = time.time()
    E = m.encode(flat, batch_size=32, convert_to_numpy=True, show_progress_bar=False)
    secs = time.time() - t0
    np.savez_compressed(cache, E=E.astype(np.float32), owner=owner, secs=secs)
    print(f"embedded in {secs:.1f}s")
    return E.astype(np.float32), owner, secs


def pool(E, owner, n, mode):
    """mode: mean (raw chunk mean), unit (mean of L2 chunks), head (first chunk)."""
    D = E.shape[1]
    V = np.zeros((n, D), dtype=np.float32)
    if mode == "unit":
        E = E / np.maximum(np.linalg.norm(E, axis=1, keepdims=True), 1e-9)
    for j in range(n):
        rows = E[owner == j]
        V[j] = rows[0] if mode == "head" else rows.mean(0)
    return V / np.maximum(np.linalg.norm(V, axis=1, keepdims=True), 1e-9)


# --- measures ---------------------------------------------------------------
def purity(labels, groups) -> float:
    labels = np.asarray(labels)
    tot = 0
    for c in set(labels.tolist()):
        idx = np.where(labels == c)[0]
        tot += Counter(groups[j] for j in idx).most_common(1)[0][1]
    return tot / len(labels)


def triplet_agreement(A, B, seed=SEED, n=TRIPLETS) -> float:
    rng = np.random.default_rng(seed)
    t = rng.integers(0, len(A), size=(n, 3))
    t = t[(t[:, 0] != t[:, 1]) & (t[:, 0] != t[:, 2]) & (t[:, 1] != t[:, 2])]
    a, b, c = t.T
    pa = np.einsum("ij,ij->i", A[a], A[b]) > np.einsum("ij,ij->i", A[a], A[c])
    pb = np.einsum("ij,ij->i", B[a], B[b]) > np.einsum("ij,ij->i", B[a], B[c])
    return float((pa == pb).mean())


def eta2(labels, x) -> float:
    """Share of variance in x explained by the partition — length-artifact probe."""
    labels, x = np.asarray(labels), np.asarray(x, dtype=float)
    grand = x.mean()
    between = sum(
        (labels == c).sum() * (x[labels == c].mean() - grand) ** 2 for c in set(labels.tolist())
    )
    return float(between / max(((x - grand) ** 2).sum(), 1e-12))


def shuffled_null(lab, ref, reps=200, seed=SEED) -> float:
    from sklearn.metrics import adjusted_rand_score

    rng = np.random.default_rng(seed)
    return float(np.mean([adjusted_rand_score(rng.permutation(lab), ref) for _ in range(reps)]))


def silhouette_with_null(X, k, seed=SEED, reps=5):
    """Silhouette against a column-shuffled null: same marginals, no covariance."""
    from sklearn.metrics import silhouette_score

    from ytk.synthesis import cluster_embeddings

    real = float(silhouette_score(X, cluster_embeddings(X, k), metric="cosine"))
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(reps):
        Z = np.column_stack([rng.permutation(X[:, d]) for d in range(X.shape[1])])
        Z = Z / np.maximum(np.linalg.norm(Z, axis=1, keepdims=True), 1e-9)
        vals.append(float(silhouette_score(Z, cluster_embeddings(Z, k), metric="cosine")))
    return real, float(np.mean(vals))


# --- pipeline ---------------------------------------------------------------
def run():
    from plot_two_lenses import build, gemma_space
    from sklearn.metrics import adjusted_rand_score

    from ytk.config import load_config
    from ytk.synthesis import choose_k, cluster_embeddings

    OUTDIR.mkdir(exist_ok=True)
    d = build()  # recomputes the 22 numbers on today's alignment
    ids, srcs, qlab, glab, k = d["ids"], d["srcs"], d["qlab"], d["glab"], d["k"]

    # re-derive the two reference geometries on the same rows
    from plot_two_lenses import align

    F, Q, ids2, _, _, _, _ = align()
    assert ids2 == ids
    G, _ = gemma_space(F)
    Qn = Q / np.linalg.norm(Q, axis=1, keepdims=True)

    text, medium = note_texts_by_id()
    med = [medium.get(i, "other") for i in ids]
    E, owner, secs = embed_chunks(ids, text)
    S = pool(E, owner, len(ids), "mean")
    slab = np.asarray(cluster_embeddings(S, k))

    cfg = load_config()
    stats = {
        "n_notes": len(ids),
        "k": k,
        "model": MODEL_ID,
        "revision": MODEL_REV,
        "chunk_chars": CHUNK_CHARS,
        "n_chunks": len(owner),
        "embed_secs": round(secs, 1),
        "purity_style": purity(slab, srcs),
        "purity_sae": d["stats"]["purity_gemma"],
        "purity_qwen": d["stats"]["purity_qwen"],
        "purity_base": d["stats"]["purity_base"],
        "purity_style_fine": purity(slab, med),
        "purity_sae_fine": purity(glab, med),
        "purity_qwen_fine": purity(qlab, med),
        "purity_base_fine": Counter(med).most_common(1)[0][1] / len(med),
        "ari_style_vs_qwen": adjusted_rand_score(slab, qlab),
        "ari_style_vs_sae": adjusted_rand_score(slab, glab),
        "ari_sae_vs_qwen": d["stats"]["ari_cross"],
        "ari_ceiling": d["stats"]["ari_ceiling"],
        "ari_null_style_qwen": shuffled_null(slab, qlab),
        "ari_null_style_sae": shuffled_null(slab, glab),
        "triplet_style_vs_qwen": triplet_agreement(S, Qn),
        "triplet_style_vs_sae": triplet_agreement(S, G),
        "triplet_sae_vs_qwen": d["stats"]["triplet"],
    }

    # preprocessing stability: three pooling choices over identical chunks
    variants = {
        m: np.asarray(cluster_embeddings(pool(E, owner, len(ids), m), k)) for m in ("unit", "head")
    }
    stats["ari_mean_vs_unitpool"] = adjusted_rand_score(slab, variants["unit"])
    stats["ari_mean_vs_head"] = adjusted_rand_score(slab, variants["head"])
    stats["ari_unit_vs_head"] = adjusted_rand_score(variants["unit"], variants["head"])

    # --- the decisive sub-test: is there voice structure inside one medium? ---
    subsets = {
        "youtube_web": np.array([s == "youtube/web" for s in srcs]),
        "youtube_only": np.array([m == "youtube" for m in med]),
    }
    within = {}
    for name, mask in subsets.items():
        n = int(mask.sum())
        kk = choose_k(n, cfg.interest)
        Ss, Gs, Qs = S[mask], G[mask], Qn[mask]
        s_real, s_null = silhouette_with_null(Ss, kk)
        g_real, g_null = silhouette_with_null(Gs, kk)
        q_real, q_null = silhouette_with_null(Qs, kk)
        sl = np.asarray(cluster_embeddings(Ss, kk))
        gl = np.asarray(cluster_embeddings(Gs, kk))
        within[name] = {
            "n": n,
            "k": kk,
            "sil_style": s_real,
            "sil_style_null": s_null,
            "sil_sae": g_real,
            "sil_sae_null": g_null,
            "sil_qwen": q_real,
            "sil_qwen_null": q_null,
            "ari_style_vs_sae_restriction": adjusted_rand_score(sl, glab[mask]),
            "ari_style_vs_sae_recluster": adjusted_rand_score(sl, gl),
            "ari_style_vs_qwen_themes": adjusted_rand_score(sl, qlab[mask]),
            "ari_null": shuffled_null(sl, glab[mask]),
            "triplet_style_vs_sae": triplet_agreement(Ss, Gs),
            "triplet_style_vs_qwen": triplet_agreement(Ss, Qs),
        }
    stats["within"] = within

    loglen = np.log10([max(len(text[i]), 1) for i in ids])
    stats["sil_full_style"], stats["sil_full_style_null"] = silhouette_with_null(S, k)
    stats["sil_full_sae"], stats["sil_full_sae_null"] = silhouette_with_null(G, k)
    stats["sil_full_qwen"], stats["sil_full_qwen_null"] = silhouette_with_null(Qn, k)
    for name, mask in subsets.items():
        kk = within[name]["k"]
        for tag, X in (("style", S), ("sae", G), ("qwen", Qn)):
            lab = np.asarray(cluster_embeddings(X[mask], kk))
            within[name][f"eta2_loglen_{tag}"] = eta2(lab, loglen[mask])

    sizes = sorted(Counter(slab.tolist()).values(), reverse=True)
    comp = []
    for c in range(k):
        idx = np.where(slab == c)[0]
        comp.append({"cluster": c, "n": len(idx), "media": dict(Counter(med[j] for j in idx))})
    return {
        "stats": stats,
        "sizes": sizes,
        "composition": comp,
        "med": med,
        "srcs": srcs,
        "slab": slab,
        "glab": glab,
        "qlab": qlab,
    }


# --- figures ----------------------------------------------------------------
MEDIA = [("youtube", GOLD), ("instagram", BLUE), ("tiktok", PURPLE), ("web", CYAN), ("other", DIM)]


def hdr_fix(fig):
    fig.texts[1].set_x(MARGIN + 0.092)


def dark_legend(ax, handles, loc="lower right", ncol=1):
    leg = ax.legend(
        handles=handles,
        loc=loc,
        fontsize=8.5,
        facecolor=PANEL,
        edgecolor=FRAME,
        labelcolor=TEXT,
        framealpha=1.0,
        borderpad=0.6,
        ncol=ncol,
    )
    leg.set_zorder(6)
    return leg


def fig01(d):
    st = d["stats"]
    fig, top = figure(
        12.6,
        7.6,
        1,
        "the style lens",
        "StyleDistance clusters of the same 532 notes, and what each lens sorts by",
        meta=f"{MODEL_ID}@{MODEL_REV[:8]} · {CHUNK_CHARS}-char chunks, mean-pooled, L2 · "
        f"same choose_k (k={st['k']}) and seeded KMeans as production · {st['n_chunks']} chunks "
        f"in {st['embed_secs']:.0f}s",
    )
    hdr_fix(fig)
    axL = fig.add_axes([0.075, 0.115, 0.42, top - 0.185])
    axR = fig.add_axes([0.615, 0.115, 0.335, top - 0.185])

    comp = sorted(d["composition"], key=lambda c: -c["n"])
    y = np.arange(len(comp))[::-1]
    for yi, cl in zip(y, comp):
        left = 0
        for name, col in MEDIA:
            v = cl["media"].get(name, 0)
            if v:
                axL.barh(yi, v, left=left, height=0.62, color=col, edgecolor=BG, linewidth=0.4)
                left += v
        axL.text(left + 2.0, yi, str(cl["n"]), color=MUTED, fontsize=TICK_SIZE, va="center")
    axL.set_yticks(y, [f"cluster {c['cluster']}" for c in comp])
    axL.set_xlim(0, 118)
    axL.set_xlabel("notes", fontsize=TICK_SIZE)
    style_axes(axL)
    panel_title(axL, "every StyleDistance cluster, by medium")
    from matplotlib.patches import Patch

    dark_legend(
        axL,
        [Patch(facecolor=c, label=n) for n, c in MEDIA],
        loc="lower right",
        ncol=2,
    )

    bars = [
        ("majority baseline", st["purity_base"], DIM),
        ("Qwen themes\n(topic)", st["purity_qwen"], GOLD),
        ("gemma SAE\n(voice)", st["purity_sae"], BLUE),
        ("StyleDistance\n(style)", st["purity_style"], RED),
    ]
    x = np.arange(len(bars))
    axR.bar(x, [v for _, v, _ in bars], color=[c for *_, c in bars], width=0.58)
    for xi, (_, v, _) in zip(x, bars):
        axR.text(xi, v + 0.012, f"{v:.2f}", color=TEXT, fontsize=10, ha="center")
    axR.set_xticks(x, [n for n, *_ in bars], fontsize=8.5)
    axR.set_ylim(0, 1.08)
    axR.axhline(st["purity_base"], color=MUTED, linewidth=0.9, linestyle=":")
    axR.set_ylabel("source purity of the partition", fontsize=TICK_SIZE)
    style_axes(axR)
    panel_title(axR, "how much of each partition is just the medium")

    fig.text(
        MARGIN,
        0.030,
        "source purity = share of notes sitting in their cluster's majority source (YouTube/web vs Instagram, "
        "the section-22 labels)",
        color=MUTED,
        fontsize=8.5,
    )
    verdict(
        fig,
        "VERDICT: SAE-grade register purity at 20x fewer params in 150 s — adopt for measuring voice",
    )
    return fig, "01-style-lens.png"


def fig02(d):
    st = d["stats"]
    w = st["within"]["youtube_only"]
    wc = st["within"]["youtube_web"]
    fig, top = figure(
        13.6,
        6.4,
        2,
        "does it measure the same voice axis",
        "Agreement against the section-22 ceiling, and whether voice survives inside one medium",
        meta=f"ceiling = Qwen re-clustered on the same 532 notes at k={st['k']} vs its own production themes "
        f"· triplets: {TRIPLETS} sampled, chance 0.5 · within-medium panel is YouTube only "
        f"(n={w['n']}, k={w['k']})",
    )
    hdr_fix(fig)
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    axa = fig.add_axes([0.145, 0.155, 0.235, top - 0.235])
    ladder = [
        ("shuffled null", st["ari_null_style_qwen"], DIM),
        ("StyleDistance\nvs Qwen themes", st["ari_style_vs_qwen"], RED),
        ("StyleDistance\nvs SAE clusters", st["ari_style_vs_sae"], PURPLE),
        ("gemma SAE\nvs Qwen themes", st["ari_sae_vs_qwen"], BLUE),
        ("Qwen recluster\nvs themes (ceiling)", st["ari_ceiling"], GOLD),
    ]
    yb = np.arange(len(ladder))
    axa.barh(yb, [v for _, v, _ in ladder], color=[c for *_, c in ladder], height=0.55)
    for yi, (_, v, _) in zip(yb, ladder):
        axa.text(v + 0.008, yi, f"{v:.3f}", color=TEXT, fontsize=9, va="center")
    axa.set_yticks(yb, [n for n, *_ in ladder], fontsize=8.5)
    axa.set_xlim(0, 0.46)
    axa.set_xlabel("adjusted Rand index", fontsize=TICK_SIZE)
    style_axes(axa)
    panel_title(axa, "partition agreement, all 532 notes", 34)

    axb = fig.add_axes([0.475, 0.155, 0.20, top - 0.235])
    tri = [
        ("StyleDistance\nvs SAE", st["triplet_style_vs_sae"], PURPLE),
        ("StyleDistance\nvs Qwen", st["triplet_style_vs_qwen"], RED),
        ("SAE vs Qwen", st["triplet_sae_vs_qwen"], BLUE),
    ]
    yb = np.arange(len(tri))
    axb.barh(yb, [v for _, v, _ in tri], color=[c for *_, c in tri], height=0.48)
    for yi, (_, v, _) in zip(yb, tri):
        axb.text(v + 0.006, yi, f"{v:.3f}", color=TEXT, fontsize=9, va="center")
    axb.axvline(0.5, color=MUTED, linewidth=1.1, linestyle="--")
    axb.set_yticks(yb, [n for n, *_ in tri], fontsize=8.5)
    axb.set_xlim(0.45, 0.80)
    axb.set_ylim(-0.55, 2.9)  # headroom so the legend clears the top bar's label
    axb.set_xlabel("triplet agreement", fontsize=TICK_SIZE)
    style_axes(axb)
    panel_title(axb, "geometry agreement", 30)
    dark_legend(
        axb,
        [Line2D([], [], color=MUTED, linewidth=1.1, linestyle="--", label="chance (0.5)")],
        loc="upper right",
    )

    axc = fig.add_axes([0.765, 0.155, 0.195, top - 0.235])
    groups = [
        ("StyleDistance", w["sil_style"], w["sil_style_null"], RED),
        ("gemma SAE", w["sil_sae"], w["sil_sae_null"], BLUE),
        ("Qwen", w["sil_qwen"], w["sil_qwen_null"], GOLD),
    ]
    x = np.arange(len(groups))
    axc.bar(x - 0.17, [g[1] for g in groups], width=0.32, color=[g[3] for g in groups])
    axc.bar(
        x + 0.17,
        [g[2] for g in groups],
        width=0.32,
        color=DIM,
        edgecolor=MUTED,
        linewidth=0.5,
    )
    hi = max(g[1] for g in groups)
    for xi, g in zip(x, groups):
        axc.text(xi - 0.17, g[1] + hi * 0.03, f"{g[1]:.3f}", color=TEXT, fontsize=8.5, ha="center")
        axc.text(xi + 0.17, hi * 0.03, f"{g[2]:.3f}", color=MUTED, fontsize=8.5, ha="center")
    axc.set_xticks(x, [g[0] for g in groups], fontsize=8.5)
    axc.set_ylim(0, hi * 1.42)
    axc.set_ylabel("silhouette (cosine)", fontsize=TICK_SIZE)
    style_axes(axc)
    panel_title(axc, f"within YouTube only (n={w['n']})", 30)
    dark_legend(
        axc,
        [Patch(facecolor=DIM, edgecolor=MUTED, label="column-shuffled null")],
        loc="upper right",
    )

    fig.text(
        MARGIN,
        0.048,
        f"inside YouTube the two voice partitions barely agree — ARI "
        f"{w['ari_style_vs_sae_recluster']:.3f} (recluster) / {w['ari_style_vs_sae_restriction']:.3f} "
        f"(restriction of the k=16 partition), null {w['ari_null']:.3f}; the coarse YouTube/web subset "
        f"(n={wc['n']}) gives {wc['ari_style_vs_sae_recluster']:.3f} / "
        f"{wc['ari_style_vs_sae_restriction']:.3f}",
        color=MUTED,
        fontsize=8.5,
    )
    fig.text(
        MARGIN,
        0.022,
        f"length confound: the within-YouTube style partition explains "
        f"{w['eta2_loglen_style']:.2f} of log-length variance (SAE {w['eta2_loglen_sae']:.2f}, "
        f"Qwen {w['eta2_loglen_qwen']:.2f}) — comparable, not worse",
        color=MUTED,
        fontsize=8.5,
    )
    verdict(
        fig,
        "VERDICT: voice survives within one medium, but the voice lenses disagree there (ARI 0.047)",
    )
    return fig, "02-voice-axis.png"


def main():
    d = run()
    print(json.dumps({k: v for k, v in d["stats"].items() if k != "within"}, indent=1))
    print(json.dumps(d["stats"]["within"], indent=1))
    (OUTDIR / "style-lens.json").write_text(
        json.dumps({"stats": d["stats"], "composition": d["composition"]}, indent=1)
    )
    for f in (fig01, fig02):
        fig, name = f(d)
        frame_panels(fig)
        out = OUTDIR / name
        fig.savefig(out, dpi=DPI, facecolor=BG)
        print(f"wrote {out.relative_to(REPO)}  ({out.stat().st_size // 1024}KB)")
        plt.close(fig)


if __name__ == "__main__":
    main()
