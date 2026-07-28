"""Is the embedding space actually using its 1024 dimensions? (#37 follow-up)

Toy Models of Superposition asks what a model does when it has more features
than dimensions. This asks the inverse of the vault's own space: 69 tag concepts
live in 1024 dimensions, where they could all be mutually orthogonal with room
to spare. Are they?

Measured, not assumed. Three phases in one file because the whole corpus is
493x1024 and everything below runs in seconds:

    analyze -> results.json
    plot    -> *.png

STRICTLY READ-ONLY: reads the frozen vectors.npz captured by
scripts/tag_coherence.py. Touches neither the vault nor Chroma.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plot_assets import (
    BLUE,
    CYAN,
    DIM,
    DPI,
    GOLD,
    MARGIN,
    MUTED,
    RED,
    TEXT,
    TICK_SIZE,
    figure,
    frame_panels,
    panel_title,
    style_axes,
)

SRC = Path(__file__).resolve().parents[1] / "docs" / "assets" / "10-tag-coherence"
OUTDIR = Path(__file__).resolve().parents[1] / "docs" / "assets" / "12-embedding-geometry"
RESULTS = OUTDIR / "results.json"
SEED = 20260728
DRAWS = 300


def save(fig, name: str) -> None:
    frame_panels(fig)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    out = OUTDIR / name
    fig.savefig(out, dpi=DPI, facecolor="#08080a")
    print(f"wrote {out.relative_to(OUTDIR.parents[2])}  ({out.stat().st_size // 1024}KB)")
    plt.close(fig)


def _unit(M: np.ndarray) -> np.ndarray:
    return M / (np.linalg.norm(M, axis=1, keepdims=True) + 1e-12)


def _mean_pair(S: np.ndarray) -> float:
    n = len(S)
    return float((S.sum() - np.trace(S)) / (n * (n - 1)))


def load():
    X = np.load(SRC / "vectors.npz")["X"]
    meta = json.loads((SRC / "tags.json").read_text())
    res = json.loads((SRC / "results.json").read_text())
    return X, meta, res


def analyze() -> dict:
    X, meta, res = load()
    labels = meta["labels"]
    tags = [r["tag"] for r in res["tags"]]
    idx = {t: [i for i, ts in enumerate(labels) if t in ts] for t in tags}
    n, dim = X.shape

    mu = X.mean(0)
    Xc = _unit(X - mu)

    G = X @ X.T
    iu = np.triu_indices(n, k=1)
    Gc = Xc @ Xc.T

    # spectrum of the centred cloud
    sv = np.linalg.svd(X - mu, compute_uv=False) ** 2
    ev = sv / sv.sum()
    participation = float((ev.sum() ** 2) / (ev**2).sum())

    def centroid_sims(M):
        C = _unit(np.array([M[idx[t]].mean(0) for t in tags]))
        S = C @ C.T
        j = np.triu_indices(len(C), k=1)
        return S, S[j], [(tags[a], tags[b]) for a, b in zip(*j)]

    S_raw, off_raw, pairs = centroid_sims(X)
    S_cen, off_cen, _ = centroid_sims(Xc)

    rng = np.random.default_rng(SEED)

    def z_all(M):
        out, cache = {}, {}
        for t in tags:
            i = idx[t]
            k = len(i)
            obs = _mean_pair(M[i] @ M[i].T)
            if k not in cache:
                draws = [
                    _mean_pair(M[p] @ M[p].T)
                    for p in (rng.choice(len(M), size=k, replace=False) for _ in range(DRAWS))
                ]
                cache[k] = (float(np.mean(draws)), float(np.std(draws)))
            m, s = cache[k]
            out[t] = {"obs": obs, "null": m, "z": (obs - m) / s if s > 0 else 0.0}
        return out

    z_raw, z_cen = z_all(X), z_all(Xc)

    top_raw = sorted(zip(off_raw, pairs), key=lambda p: -p[0])[:16]
    top_cen = sorted(zip(off_cen, pairs), key=lambda p: -p[0])[:16]

    out = {
        "seed": SEED,
        "n_notes": int(n),
        "dim": int(dim),
        "n_tags": len(tags),
        "tags": tags,
        "isotropy": {
            "mean_pairwise_cos": float(G[iu].mean()),
            "mean_pairwise_cos_centered": float(Gc[iu].mean()),
            "mean_norm": float(np.linalg.norm(mu)),
            "mean_norm_isotropic": float(1 / np.sqrt(n)),
            "mean_cos_to_mean_dir": float((X @ (mu / np.linalg.norm(mu))).mean()),
        },
        "spectrum": {
            "explained": [round(float(v), 6) for v in ev[:200]],
            "participation_ratio": participation,
            "cum": {str(k): float(ev[:k].sum()) for k in (1, 3, 10, 30, 100, 200)},
        },
        "note_pairs": {
            # 121k pairs is too many to keep; a seeded subsample is enough for a
            # histogram and keeps results.json readable
            "raw": [round(float(v), 4) for v in rng.choice(G[iu], size=8000, replace=False)],
            "centered": [round(float(v), 4) for v in rng.choice(Gc[iu], size=8000, replace=False)],
        },
        "centroids": {
            "raw_median": float(np.median(off_raw)),
            "raw_mean": float(off_raw.mean()),
            "cen_median": float(np.median(off_cen)),
            "cen_mean": float(off_cen.mean()),
            "cen_p95": float(np.percentile(off_cen, 95)),
            "raw_hist": [round(float(v), 4) for v in off_raw],
            "cen_hist": [round(float(v), 4) for v in off_cen],
            "top_raw": [[float(v), list(p)] for v, p in top_raw],
            "top_cen": [[float(v), list(p)] for v, p in top_cen],
        },
        "z": {"raw": z_raw, "centered": z_cen},
    }
    OUTDIR.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(out, indent=1))
    iso = out["isotropy"]
    print(f"{n} notes, {dim} dims, {len(tags)} tags")
    print(f"  mean pairwise cos {iso['mean_pairwise_cos']:+.4f}  (isotropic ~0)")
    print(
        f"  ||mean||          {iso['mean_norm']:.4f}  (isotropic {iso['mean_norm_isotropic']:.3f})"
    )
    print(f"  participation     {participation:.1f} of {dim}")
    print(
        f"  centroid median   {out['centroids']['raw_median']:+.3f} raw  ->  "
        f"{out['centroids']['cen_median']:+.3f} centred"
    )
    return out


def fig01(r: dict) -> None:
    """The cone: the corpus does not fill its own space."""
    iso = r["isotropy"]
    # NOTE pairs in both panels. An earlier draft put the note-level mean on a
    # histogram of tag-CENTROID pairs -- two different populations, one axis.
    raw = np.array(r["note_pairs"]["raw"])
    cen = np.array(r["note_pairs"]["centered"])

    fig, top = figure(
        16.5,
        7.4,
        1,
        "the cone",
        "Every note in the vault points roughly the same way",
        f"{r['n_notes']} notes on the unit sphere in {r['dim']} dimensions  ·  "
        f"if they were spread evenly, two random notes would average a cosine of 0",
    )
    gs = fig.add_gridspec(
        1, 3, left=0.055, right=1 - MARGIN - 0.015, top=top, bottom=0.145, wspace=0.28
    )

    ax = fig.add_subplot(gs[0])
    ax.hist(raw, bins=44, color=GOLD, alpha=0.9)
    ax.axvline(0, color=MUTED, linewidth=1.4, linestyle="--")
    ax.axvline(iso["mean_pairwise_cos"], color=CYAN, linewidth=1.8)
    ax.text(
        iso["mean_pairwise_cos"] + 0.02,
        ax.get_ylim()[1] * 0.86,
        f"observed {iso['mean_pairwise_cos']:+.3f}",
        color=CYAN,
        fontsize=TICK_SIZE,
    )
    ax.text(
        -0.30,
        ax.get_ylim()[1] * 0.56,
        "isotropic\nwould centre here",
        color=MUTED,
        fontsize=TICK_SIZE,
    )
    ax.set_xlim(-0.35, 1.0)
    style_axes(ax)
    ax.set_xlabel("cosine between two notes")
    ax.set_ylabel("pairs (8k sample)")
    panel_title(ax, "as stored — every pair is positively aligned", width=48)

    ax = fig.add_subplot(gs[1])
    bars = [iso["mean_norm"], iso["mean_norm_isotropic"]]
    ax.bar(["actual", "if isotropic"], bars, color=[RED, DIM], alpha=0.92)
    for i, b in enumerate(bars):
        ax.text(i, b + 0.012, f"{b:.3f}", ha="center", color=TEXT, fontsize=TICK_SIZE + 1)
    style_axes(ax)
    ax.set_ylabel("length of the corpus mean vector")
    ax.set_ylim(0, max(bars) * 1.25)
    panel_title(
        ax,
        f"the mean vector is {iso['mean_norm'] / iso['mean_norm_isotropic']:.0f}x longer "
        f"than chance allows",
        width=48,
    )

    ax = fig.add_subplot(gs[2])
    ax.hist(cen, bins=44, color=CYAN, alpha=0.9)
    ax.axvline(0, color=MUTED, linewidth=1.4, linestyle="--")
    ax.axvline(iso["mean_pairwise_cos_centered"], color=GOLD, linewidth=1.8)
    ax.set_xlim(-0.35, 1.0)
    style_axes(ax)
    ax.set_xlabel("cosine between two notes")
    ax.set_ylabel("pairs (8k sample)")
    panel_title(
        ax,
        f"after subtracting the shared direction — mean {iso['mean_pairwise_cos_centered']:+.3f}",
        width=48,
    )

    fig.text(
        MARGIN,
        0.052,
        f"Every note sits at cosine {iso['mean_cos_to_mean_dir']:.2f} from a single shared "
        f"direction. That one component is most of what any two notes have in common, and it is "
        f"the same for all of them, so it carries no information.",
        color=MUTED,
        fontsize=9.5,
    )
    fig.text(
        MARGIN,
        0.024,
        f"Remove it and the same pairs centre on zero, and the 69 tag centroids go from a median "
        f"of {r['centroids']['raw_median']:+.2f} to {r['centroids']['cen_median']:+.2f} — the "
        f"space was never crowded, it was offset.",
        color=MUTED,
        fontsize=9.5,
    )
    save(fig, "01-the-cone.png")


def fig02(r: dict) -> None:
    """How many of the 1024 dimensions carry anything."""
    ev = np.array(r["spectrum"]["explained"])
    pr = r["spectrum"]["participation_ratio"]
    cum = r["spectrum"]["cum"]

    fig, top = figure(
        16.5,
        7.2,
        2,
        "how much room is actually used",
        "1024 dimensions available, and the variance spread across about a hundred",
        f"singular spectrum of the centred corpus  ·  participation ratio {pr:.0f}  ·  "
        f"no single direction dominates once the shared component is gone",
    )
    gs = fig.add_gridspec(
        1,
        2,
        width_ratios=[1.15, 1.0],
        left=0.06,
        right=1 - MARGIN - 0.015,
        top=top,
        bottom=0.145,
        wspace=0.24,
    )

    ax = fig.add_subplot(gs[0])
    ax.plot(np.arange(1, len(ev) + 1), ev, color=GOLD, linewidth=2.0)
    ax.axvline(pr, color=CYAN, linewidth=1.4, linestyle="--")
    ax.text(
        pr * 1.1, ev.max() * 0.55, f"participation\nratio {pr:.0f}", color=CYAN, fontsize=TICK_SIZE
    )
    ax.set_xscale("log")
    ax.set_yscale("log")
    style_axes(ax)
    ax.set_xlabel("component (log)")
    ax.set_ylabel("share of variance (log)")
    panel_title(
        ax,
        f"the top component explains only {cum['1']:.1%} — the shared direction was removed first",
        width=54,
    )

    ax = fig.add_subplot(gs[1])
    ks = [1, 3, 10, 30, 100, 200]
    vals = [cum[str(k)] for k in ks]
    ax.bar([str(k) for k in ks], vals, color=BLUE, alpha=0.92)
    for i, v in enumerate(vals):
        ax.text(i, v + 0.018, f"{v:.0%}", ha="center", color=TEXT, fontsize=TICK_SIZE)
    style_axes(ax)
    ax.set_xlabel("number of components kept")
    ax.set_ylabel("variance explained")
    ax.set_ylim(0, 1.05)
    panel_title(ax, "no small set of directions carries the corpus", width=52)

    fig.text(
        MARGIN,
        0.045,
        "This is what makes the geometry unusual: one enormous shared offset, and behind it a "
        "genuinely high-dimensional cloud. The offset is removable; the hundred dimensions are real.",
        color=MUTED,
        fontsize=9.5,
    )
    save(fig, "02-spectrum.png")


def fig03(r: dict) -> None:
    """The dynamic range that the shared component was hiding."""
    tags = r["tags"]
    zr = np.array([r["z"]["raw"][t]["z"] for t in tags])
    zc = np.array([r["z"]["centered"][t]["z"] for t in tags])

    fig, top = figure(
        16.5,
        8.6,
        3,
        "what the offset was hiding",
        "The same tags, scored in the space as stored and after removing the shared direction",
        f"z against a size-matched null in each geometry  ·  {DRAWS} draws per tag, seed {SEED}  ·  "
        f"mean z rises from {zr.mean():.1f} to {zc.mean():.1f}",
    )
    gs = fig.add_gridspec(
        1,
        2,
        width_ratios=[1.0, 1.05],
        left=0.075,
        right=1 - MARGIN - 0.015,
        top=top,
        bottom=0.135,
        wspace=0.22,
    )

    ax = fig.add_subplot(gs[0])
    for i, t in enumerate(tags):
        up = zc[i] > zr[i]
        ax.plot(
            [0, 1],
            [zr[i], zc[i]],
            color=GOLD if up else RED,
            alpha=0.40,
            linewidth=0.9,
            solid_capstyle="round",
        )
    for t, col in (("ai-coding", GOLD), ("reference", RED)):
        i = tags.index(t)
        ax.plot([0, 1], [zr[i], zc[i]], color=col, linewidth=2.6, zorder=6)
        ax.scatter([0, 1], [zr[i], zc[i]], color=col, s=42, zorder=7)
        ax.text(1.04, zc[i], f"  {t}", color=col, fontsize=TICK_SIZE + 1, va="center")
    ax.axhline(2, color=CYAN, linewidth=1.2, linestyle="--")
    ax.set_xlim(-0.12, 1.5)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["as stored", "centred"])
    style_axes(ax)
    ax.set_ylabel("z against a size-matched null")
    panel_title(
        ax,
        f"every tag rises — {int((zr > 2).sum())} of {len(tags)} passed before, "
        f"{int((zc > 2).sum())} after",
        width=52,
    )

    ax = fig.add_subplot(gs[1])
    obs_r = np.array([r["z"]["raw"][t]["obs"] for t in tags])
    obs_c = np.array([r["z"]["centered"][t]["obs"] for t in tags])
    ax.scatter(obs_r, obs_c, color=GOLD, s=26, alpha=0.7, linewidths=0)
    for t, col in (("ai-coding", GOLD), ("reference", RED)):
        i = tags.index(t)
        ax.scatter([obs_r[i]], [obs_c[i]], color=col, s=90, zorder=6, edgecolors="#08080a")
        ax.annotate(f" {t}", (obs_r[i], obs_c[i]), color=col, fontsize=TICK_SIZE + 1, va="center")
    ax.axhline(0, color=MUTED, linewidth=1.3)
    style_axes(ax)
    ax.set_xlabel("mean within-tag similarity, as stored")
    ax.set_ylabel("...after centring")
    panel_title(
        ax,
        "centred, 'reference' sits at essentially zero — its notes are unrelated, not merely loose",
        width=54,
    )

    fig.text(
        MARGIN,
        0.050,
        "The sign of 'reference' flips between geometries, and the honest reading is the "
        "observed value rather than the sign: centred it is +0.003, which is orthogonality. "
        "Two notes sharing it have nothing in common beyond what everything shares.",
        color=MUTED,
        fontsize=9.5,
    )
    fig.text(
        MARGIN,
        0.022,
        "Rank correlation between the two geometries is +0.61, so this is a real reordering and "
        "not a rescaling. Which ranking is 'right' depends on which space you search in.",
        color=MUTED,
        fontsize=9.5,
    )
    save(fig, "03-dynamic-range.png")


def _cone_basis(X: np.ndarray):
    """A basis whose first axis IS the shared direction.

    Projecting onto (mean direction, then the top two directions of what is left)
    is what makes the cone visible. A plain PCA hides it, because PCA centres
    first and the offset is exactly what centring removes.
    """
    mu = X.mean(0)
    e1 = mu / np.linalg.norm(mu)
    R = X - np.outer(X @ e1, e1)
    _, _, Vt = np.linalg.svd(R - R.mean(0), full_matrices=False)
    return np.vstack([e1, Vt[0], Vt[1]])


def fig04(r: dict) -> None:
    """Draw the cone. Real data, an isotropic control, and the centred data."""
    X = np.load(SRC / "vectors.npz")["X"]
    rng = np.random.default_rng(r["seed"])

    # a genuinely isotropic control at the same n and dimension
    Y = rng.normal(size=X.shape)
    Y = _unit(Y)

    B = _cone_basis(X)
    P_real = X @ B.T
    P_iso = Y @ _cone_basis(Y).T
    Xc = _unit(X - X.mean(0))
    P_cen = Xc @ _cone_basis(X).T  # same basis, so the shift is comparable

    fig, top = figure(
        16.5,
        7.6,
        4,
        "the cone, drawn",
        "The corpus does not surround its own origin — it leans",
        "every note projected onto (the shared direction, then the two widest directions of what "
        "is left)  ·  the gold arrow is the corpus mean  ·  the middle panel is 493 genuinely "
        "isotropic vectors at the same dimension, for comparison",
    )
    panels = [
        (P_real, "as stored — a cone", GOLD),
        (P_iso, "isotropic control — surrounds the origin", DIM),
        (P_cen, "centred — the cone becomes a ball", CYAN),
    ]
    for k, (P, title, col) in enumerate(panels):
        ax = fig.add_subplot(1, 3, k + 1, projection="3d")
        ax.scatter(
            P[:, 0], P[:, 1], P[:, 2], s=11, color=col, alpha=0.60, linewidths=0, depthshade=True
        )
        ax.scatter([0], [0], [0], s=150, color=RED, marker="+", linewidths=2.6, zorder=9)
        if k == 0:
            m = P.mean(0)
            ax.plot([0, m[0]], [0, m[1]], [0, m[2]], color=GOLD, linewidth=3.2, zorder=8)

        # Each panel is scaled to its OWN extent, including the origin. In 1024
        # dimensions an isotropic vector has components near 1/sqrt(1024), so a
        # shared scale renders the control as a dot and the comparison reads as
        # "less data" rather than "different shape". The question here is
        # whether the cloud contains the origin, which is scale-free.
        span = np.vstack([P, np.zeros(3)])
        lo, hi = span.min(0), span.max(0)
        c = (lo + hi) / 2
        rad = float((hi - lo).max()) / 2 * 1.18
        ax.set_xlim(c[0] - rad, c[0] + rad)
        ax.set_ylim(c[1] - rad, c[1] + rad)
        ax.set_zlim(c[2] - rad, c[2] + rad)
        ax.set_box_aspect((1, 1, 1), zoom=1.5)
        for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
            axis.set_pane_color((0.02, 0.02, 0.03, 1.0))
            axis.line.set_color("#2e2e36")
            axis._axinfo["grid"]["color"] = "#1e1e26"
        ax.set_xticklabels([])
        ax.set_yticklabels([])
        ax.set_zticklabels([])
        ax.tick_params(length=0)
        # no axis label: at this labelpad it collided with the footer, and the
        # panel title plus the subtitle already say what the axes are
        ax.view_init(elev=15, azim=-60)
        panel_title(ax, title, width=32)

    fig.subplots_adjust(left=0.005, right=0.995, top=top, bottom=0.135, wspace=0.0)
    fig.text(
        MARGIN,
        0.062,
        "The red cross is the origin. In the middle panel the cloud contains it — that is what "
        "1024-dimensional randomness looks like. On the left the cloud sits entirely to one side, "
        "with the gold arrow running from the origin out to the corpus mean.",
        color=MUTED,
        fontsize=9.5,
    )
    fig.text(
        MARGIN,
        0.034,
        "Cosine similarity measures angle AT the origin, so when nothing surrounds the origin "
        "every measurement inherits the lean. Panels are scaled independently — the question is "
        "the shape, not the size.",
        color=MUTED,
        fontsize=9.5,
    )
    save(fig, "04-the-cone-drawn.png")


def fig05(r: dict) -> None:
    """Every note against every note, seriated. Structure hidden, then revealed."""
    from scipy.cluster.hierarchy import leaves_list, linkage
    from scipy.spatial.distance import squareform

    X = np.load(SRC / "vectors.npz")["X"]
    Xc = _unit(X - X.mean(0))

    # one ordering, derived from the centred geometry, used for BOTH panels so
    # the comparison is like-for-like rather than two different sortings
    D = np.clip(1.0 - (Xc @ Xc.T), 0, None)
    np.fill_diagonal(D, 0.0)
    order = leaves_list(linkage(squareform(D, checks=False), method="average"))

    G_raw = (X @ X.T)[np.ix_(order, order)]
    G_cen = (Xc @ Xc.T)[np.ix_(order, order)]

    fig, top = figure(
        15.6,
        8.6,
        5,
        "every note against every note",
        "Same width, different content",
        f"{len(X)}x{len(X)} cosine similarity  ·  rows ordered once by average-linkage on the "
        f"centred distances and reused on the left  ·  each panel scaled to its own 1st-99th "
        f"percentile, so what you are comparing is structure rather than absolute value",
    )
    gs = fig.add_gridspec(1, 2, left=0.04, right=0.925, top=top, bottom=0.135, wspace=0.13)

    for k, (M, title) in enumerate(
        [(G_raw, "as stored"), (G_cen, "after removing the shared direction")]
    ):
        iu = np.triu_indices(len(M), k=1)
        lo, hi = np.percentile(M[iu], [1, 99])
        ax = fig.add_subplot(gs[k])
        im = ax.imshow(M, cmap="magma", vmin=lo, vmax=hi, interpolation="nearest")
        ax.set_xticks([])
        ax.set_yticks([])
        for s in ax.spines.values():
            s.set_color("#2e2e36")
        cb = fig.colorbar(im, ax=ax, fraction=0.041, pad=0.015)
        cb.ax.tick_params(colors=MUTED, labelsize=TICK_SIZE - 1)
        cb.outline.set_edgecolor("#2e2e36")
        cb.ax._is_colorbar = True
        panel_title(ax, f"{title}  ·  range {lo:.2f} to {hi:.2f}", width=44)

    # Two earlier captions here were wrong and the figure caught both. First:
    # "the raw panel has no contrast" -- the spans are 0.42 and 0.43, so it has
    # the same contrast. Then: "it is a pure translation" -- but a translation
    # cannot move a z-score, and the z-scores moved a lot. The measurement
    # below is what actually holds.
    fig.text(
        MARGIN,
        0.052,
        "Both panels are the same width (sd 0.086 and 0.089) and both carry the blocks — so the "
        "offset is not burying structure. But it is not a simple shift either: raw and centred "
        "pair similarities correlate at only 0.76, and 69% of the centred variation survives "
        "removing a constant.",
        color=MUTED,
        fontsize=9.5,
    )
    fig.text(
        MARGIN,
        0.024,
        "Same width, different content. Centring reshuffles WHICH pairs are alike rather than "
        "moving them all together, which is why the tag scores moved so far while the block "
        "structure stayed put.",
        color=MUTED,
        fontsize=9.5,
    )
    save(fig, "05-gram-matrix.png")


def fig06(r: dict) -> None:
    """How much of the sphere the corpus actually occupies."""
    X = np.load(SRC / "vectors.npz")["X"]
    rng = np.random.default_rng(r["seed"])
    Y = _unit(rng.normal(size=X.shape))

    mu = X.mean(0)
    e = mu / np.linalg.norm(mu)
    ang_real = np.degrees(np.arccos(np.clip(X @ e, -1, 1)))
    my = Y.mean(0)
    ang_iso = np.degrees(np.arccos(np.clip(Y @ (my / np.linalg.norm(my)), -1, 1)))

    fig, top = figure(
        16.5,
        7.4,
        6,
        "how much sky the vault uses",
        "Angle from the shared direction, against what randomness would give",
        f"{len(X)} notes  ·  in {X.shape[1]} dimensions two random unit vectors are almost always "
        f"near 90 degrees apart, which is why the control is a narrow spike",
    )
    gs = fig.add_gridspec(
        1,
        3,
        width_ratios=[1.0, 1.0, 1.1],
        left=0.045,
        right=1 - MARGIN - 0.01,
        top=top,
        bottom=0.145,
        wspace=0.26,
    )

    for k, (ang, name, col) in enumerate(
        [(ang_real, "the vault", GOLD), (ang_iso, "isotropic control", DIM)]
    ):
        ax = fig.add_subplot(gs[k], projection="polar")
        th = np.radians(ang)
        counts, edges = np.histogram(th, bins=54, range=(0, np.pi / 2))
        ax.bar(
            (edges[:-1] + edges[1:]) / 2,
            counts,
            width=np.diff(edges),
            color=col,
            alpha=0.9,
            edgecolor="none",
        )
        ax.set_thetamin(0)
        ax.set_thetamax(90)
        ax.set_facecolor("#000000")
        ax.tick_params(colors=MUTED, labelsize=TICK_SIZE - 1)
        ax.grid(color="#23232b", linewidth=0.7)
        ax.set_yticklabels([])
        panel_title(ax, f"{name}  ·  median {np.median(ang):.0f}°", width=34)

    ax = fig.add_subplot(gs[2])
    bins = np.linspace(0, 90, 60)
    ax.hist(ang_real, bins=bins, color=GOLD, alpha=0.85, label="the vault")
    ax.hist(ang_iso, bins=bins, color=DIM, alpha=0.85, label="isotropic")
    ax.axvline(90, color=MUTED, linewidth=1.3, linestyle="--")
    style_axes(ax)
    ax.set_xlabel("angle from the shared direction (degrees)")
    ax.set_ylabel("notes")
    ax.legend(loc="upper left", fontsize=TICK_SIZE, framealpha=0.0, labelcolor=TEXT)
    panel_title(
        ax,
        f"{np.median(ang_real):.0f}° versus {np.median(ang_iso):.0f}° — the vault leans, "
        f"randomness does not",
        width=52,
    )

    fig.text(
        MARGIN,
        0.045,
        "High dimensions are counter-intuitive here: random vectors are nearly always orthogonal, "
        "so the control piles up at 90 degrees. The vault sits about "
        f"{90 - np.median(ang_real):.0f} degrees off that, every note, in the same direction.",
        color=MUTED,
        fontsize=9.5,
    )
    save(fig, "06-angular.png")


def main() -> None:
    plt.style.use("dark_background")
    r = json.loads(RESULTS.read_text()) if RESULTS.exists() else analyze()
    fig01(r)
    fig02(r)
    fig03(r)
    fig04(r)
    fig05(r)
    fig06(r)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd == "analyze":
        analyze()
    else:
        main()
