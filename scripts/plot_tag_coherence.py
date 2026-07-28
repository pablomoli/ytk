"""Figures: do interest_tags carve real regions of embedding space? (#37)

Rungs:
  01  the verdict — every scorable tag against a size-matched null
  02  the mechanism — intra-tag similarity distributions, best three vs worst three
  03  the vocabulary — 974 tags for 493 notes, and which ones are near-duplicates

Data from scripts/tag_coherence.py (harvest -> analyze), read-only on the vault.

Usage: uv run --with matplotlib --with numpy python scripts/plot_tag_coherence.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
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
    fit3d,
    frame_panels,
    panel_title,
    saturated_magma,
    style_axes,
)

OUTDIR = Path(__file__).resolve().parents[1] / "docs" / "assets" / "10-tag-coherence"
Z_PASS = 2.0


def save(fig, name: str) -> None:
    frame_panels(fig)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    out = OUTDIR / name
    fig.savefig(out, dpi=DPI, facecolor="#08080a")
    print(f"wrote {out.relative_to(OUTDIR.parents[2])}  ({out.stat().st_size // 1024}KB)")
    plt.close(fig)


def fig01(res: dict) -> None:
    """Every scorable tag, ranked by how far it beats its own null."""
    rows = res["tags"]
    z = np.array([r["z"] for r in rows])
    names = [f"{r['tag']}  ({r['n']})" for r in rows]
    y = np.arange(len(rows))[::-1]  # best at top

    fig, top = figure(
        14.6,  # narrower than this and the FIGURE 01 kicker collides with its label
        16.5,
        1,
        "the verdict",
        "Which tags name a real neighbourhood, and which are sprayed across the corpus?",
        f"{res['n_tags_scored']} tags with at least {res['min_notes']} notes  ·  "
        f"{res['n_notes']} notes  ·  null = {res['null_draws']} size-matched random sets per tag, "
        f"seed {res['seed']}  ·  z is distance from that tag's own null, in null standard deviations",
    )
    ax = fig.add_subplot(1, 1, 1)
    colors = [GOLD if v >= Z_PASS else RED for v in z]
    ax.hlines(y, 0, z, color=colors, linewidth=1.6, alpha=0.85)
    ax.scatter(z, y, color=colors, s=26, zorder=5, linewidths=0)
    ax.axvspan(-2, Z_PASS, color=DIM, alpha=0.30, zorder=0)
    ax.axvline(0, color=MUTED, linewidth=1.2)
    ax.axvline(Z_PASS, color=CYAN, linewidth=1.2, linestyle="--")
    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=TICK_SIZE - 0.5)
    ax.set_ylim(-1, len(rows))
    style_axes(ax)
    ax.set_xlabel("z vs size-matched null  (shaded band = indistinguishable from random)")
    n_fail = int((z < Z_PASS).sum())
    panel_title(
        ax,
        f"{len(rows) - n_fail} of {len(rows)} tags cohere beyond z={Z_PASS:g}  ·  "
        f"{n_fail} do not  ·  'reference' is anti-coherent at z={z.min():.1f}",
        width=96,
    )
    fig.subplots_adjust(left=0.175, right=1 - MARGIN - 0.01, top=top, bottom=0.062)
    fig.text(
        MARGIN,
        0.024,
        "Size matching is the whole trick: a 6-note tag looks cohesive by accident far more "
        "easily than a 125-note tag, so raw similarity is not comparable across tags and z is.",
        color=MUTED,
        fontsize=9.5,
    )
    save(fig, "01-tag-verdict.png")


def fig02(res: dict) -> None:
    """The mechanism: what a passing and a failing tag actually look like."""
    X = np.load(OUTDIR / "vectors.npz")["X"]
    meta = json.loads((OUTDIR / "tags.json").read_text())
    labels = meta["labels"]
    rng = np.random.default_rng(res["seed"])

    rows = res["tags"]
    picks = rows[:3] + rows[-3:]

    fig, top = figure(
        16.5,
        9.0,
        2,
        "the mechanism",
        "A tag that works is a tight neighbourhood; a tag that fails is the whole corpus",
        "each panel: the distribution of pairwise cosine similarity between notes carrying that "
        "tag, against the same statistic for random notes of the same count",
    )
    gs = fig.add_gridspec(
        2, 3, left=0.055, right=1 - MARGIN - 0.015, top=top, bottom=0.155, wspace=0.24, hspace=0.55
    )

    for k, r in enumerate(picks):
        idx = [i for i, ts in enumerate(labels) if r["tag"] in ts]
        sub = X[idx]
        gram = sub @ sub.T
        iu = np.triu_indices(len(sub), k=1)
        within = gram[iu]

        rnd = X[rng.choice(len(X), size=len(sub), replace=False)]
        g2 = rnd @ rnd.T
        null = g2[np.triu_indices(len(rnd), k=1)]

        ok = r["z"] >= Z_PASS
        ax = fig.add_subplot(gs[k])
        bins = np.linspace(0.0, 0.85, 44)
        ax.hist(null, bins=bins, color=DIM, alpha=0.95, density=True, label="random pairs")
        ax.hist(
            within,
            bins=bins,
            color=GOLD if ok else RED,
            alpha=0.62,
            density=True,
            label="same-tag pairs",
        )
        ax.axvline(float(null.mean()), color=DIM, linewidth=1.3, linestyle="--")
        ax.axvline(float(within.mean()), color=GOLD if ok else RED, linewidth=1.6, linestyle="--")
        style_axes(ax)
        ax.set_xlabel("cosine similarity")
        if k % 3 == 0:
            ax.set_ylabel("density")
        if k == 0:
            ax.legend(loc="upper right", fontsize=TICK_SIZE - 1, framealpha=0.0, labelcolor=TEXT)
        panel_title(
            ax,
            f"{r['tag']}  ·  n={r['n']}  ·  z={r['z']:+.1f}",
            width=34,
        )

    fig.text(
        MARGIN,
        0.052,
        "Top row: the three most coherent tags. Bottom row: the three least. The failing tags do "
        "not merely fail to cluster — 'reference' sits BELOW its null, meaning two notes that "
        "share it are less alike than two notes drawn at random.",
        color=MUTED,
        fontsize=9.5,
    )
    fig.text(
        MARGIN,
        0.022,
        "It spans the corpus more evenly than chance because it labels a judgment about the note "
        "('I might come back to this') rather than its subject, and embeddings encode subject.",
        color=MUTED,
        fontsize=9.5,
    )
    save(fig, "02-mechanism.png")


def fig03(res: dict) -> None:
    """The vocabulary itself: sprawl, and which labels are near-duplicates."""
    meta = json.loads((OUTDIR / "tags.json").read_text())
    counts = Counter(t for ts in meta["labels"] for t in ts)
    freq = Counter(counts.values())

    fig, top = figure(
        16.5,
        8.2,
        3,
        "the vocabulary",
        "974 distinct tags across 493 notes, and most of them appear exactly once",
        "a tag used once cannot be a category — it is a caption. And several of the tags that do "
        "recur point at the same region of the space, so they are one category wearing four names.",
    )
    gs = fig.add_gridspec(
        1,
        2,
        width_ratios=[1.0, 1.35],
        left=0.06,
        right=1 - MARGIN - 0.02,
        top=top,
        bottom=0.14,
        wspace=0.20,
    )

    # rank-frequency, so the largest tags stay on the panel instead of being
    # clipped by an x-limit
    ax = fig.add_subplot(gs[0])
    once = freq[1]
    ranked = sorted(counts.values(), reverse=True)
    ax.plot(np.arange(1, len(ranked) + 1), ranked, color=GOLD, linewidth=1.9)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.axhline(res["min_notes"], color=CYAN, linewidth=1.3, linestyle="--")
    ax.text(
        1.3,
        res["min_notes"] * 1.3,
        f"cutoff {res['min_notes']} notes -> {res['n_tags_scored']} tags scored",
        color=CYAN,
        fontsize=TICK_SIZE,
    )
    ax.axvline(len(counts) - once, color=RED, linewidth=1.3, linestyle=":")
    ax.text(
        (len(counts) - once) * 0.30,
        1.35,
        f"{once} tags used once ({once / len(counts):.0%})",
        color=RED,
        fontsize=TICK_SIZE,
    )
    style_axes(ax)
    ax.set_xlabel("tag rank (log)")
    ax.set_ylabel("notes carrying it (log)")
    panel_title(
        ax,
        f"{len(counts)} tags, {np.mean([len(t) for t in meta['labels']]):.1f} per note  ·  "
        "a tag used once is a caption, not a category",
        width=58,
    )

    # This panel used to be a 69x69 heatmap. It was unreadable -- labels at 4pt,
    # and centroid similarity runs 0.34-0.98 so nearly every cell saturated. The
    # pairs are what it was trying to say, and they are directly actionable.
    ax = fig.add_subplot(gs[1])
    M = np.array(res["overlap"])
    order = res["overlap_order"]
    iu = np.triu_indices(len(M), k=1)
    pairs = sorted(zip(M[iu], [(order[i], order[j]) for i, j in zip(*iu)]), key=lambda p: -p[0])[
        :16
    ][::-1]
    y = np.arange(len(pairs))
    ax.barh(y, [p[0] for p in pairs], color=GOLD, alpha=0.9, height=0.72)
    ax.set_yticks(y)
    ax.set_yticklabels([f"{a}  +  {b}" for _, (a, b) in pairs], fontsize=TICK_SIZE)
    ax.set_xlim(0.9, 1.0)
    style_axes(ax)
    ax.set_xlabel(
        f"centroid cosine similarity   (median between any two tags: {np.median(M[iu]):.2f})"
    )
    panel_title(ax, "the 16 most redundant label pairs — candidates to merge", width=58)

    fig.text(
        MARGIN,
        0.045,
        "Four labels for one region: ai-coding, ai-agents, claude-code and developer-tools all sit "
        "above 0.97 with each other. mma/combat-sports and neuroscience/cognitive-science are the "
        "same story outside AI.",
        color=MUTED,
        fontsize=9.5,
    )
    save(fig, "03-vocabulary.png")


def fig04(res: dict) -> None:
    """The same matrix as before, seriated — order is what makes it legible."""
    from scipy.cluster.hierarchy import dendrogram, leaves_list, linkage
    from scipy.spatial.distance import squareform

    M = np.array(res["overlap"])
    order0 = res["overlap_order"]
    zmap = {r["tag"]: r["z"] for r in res["tags"]}

    # cluster on distance = 1 - similarity; the leaf order is the seriation
    D = np.clip(1.0 - M, 0, None)
    np.fill_diagonal(D, 0.0)
    Z = linkage(squareform(D, checks=False), method="average")
    leaves = leaves_list(Z)
    order = [order0[i] for i in leaves]
    Ms = M[np.ix_(leaves, leaves)]

    iu = np.triu_indices(len(M), k=1)
    lo, hi = np.percentile(M[iu], [2, 98])

    fig, top = figure(
        15.0,
        14.4,
        4,
        "the structure",
        "The same similarity matrix, ordered by clustering instead of by rank",
        f"{len(order)} tag centroids  ·  colour scaled to the 2nd-98th percentile "
        f"({lo:.2f}-{hi:.2f}), because every pair sits above 0.33 and a 0-1 ramp renders the "
        f"whole matrix bright  ·  average-linkage on 1 - cosine",
    )
    gs = fig.add_gridspec(
        1, 2, width_ratios=[0.17, 1.0], left=0.030, right=0.885, top=top, bottom=0.135, wspace=0.012
    )

    axd = fig.add_subplot(gs[0])
    with plt.rc_context({"lines.linewidth": 0.9}):
        dendrogram(
            Z,
            orientation="left",
            no_labels=True,
            color_threshold=0.30,
            above_threshold_color=DIM,
            ax=axd,
        )
    axd.invert_yaxis()
    axd.set_facecolor("#000000")
    axd.set_xticks([])
    axd.set_yticks([])
    for s in axd.spines.values():
        s.set_visible(False)

    ax = fig.add_subplot(gs[1])
    im = ax.imshow(Ms, cmap="magma", vmin=lo, vmax=hi, interpolation="nearest")
    ax.set_xticks(range(len(order)))
    ax.set_yticks(range(len(order)))
    ax.set_xticklabels(order, rotation=90, fontsize=5.4)
    # labels on the right: the left edge belongs to the dendrogram, and drawing
    # them there put the tag names on top of the tree
    ax.yaxis.tick_right()
    ax.set_yticklabels(order, fontsize=5.4)
    for lbl, tag in zip(ax.get_yticklabels(), order):
        lbl.set_color(GOLD if zmap[tag] >= Z_PASS else RED)
    for lbl, tag in zip(ax.get_xticklabels(), order):
        lbl.set_color(GOLD if zmap[tag] >= Z_PASS else RED)
    ax.tick_params(colors=MUTED, length=0)
    for s in ax.spines.values():
        s.set_color("#2e2e36")
    cb = fig.colorbar(im, ax=ax, fraction=0.030, pad=0.085)
    cb.set_label("centroid cosine similarity", color=MUTED, fontsize=TICK_SIZE)
    cb.ax.tick_params(colors=MUTED, labelsize=TICK_SIZE - 1)
    cb.ax._is_colorbar = True
    panel_title(ax, "gold = coheres, red = does not", width=80)

    fig.text(
        MARGIN,
        0.048,
        "Seriation is the whole difference. Ranked by z the matrix looked uniform; clustered, the "
        "blocks are obvious — an AI/tooling block, a making/hardware block, a mind block.",
        color=MUTED,
        fontsize=9.5,
    )
    fig.text(
        MARGIN,
        0.020,
        "The red labels do not form their own block. They are scattered through every cluster, "
        "which is the same fact figure 02 measured: they have no region of their own.",
        color=MUTED,
        fontsize=9.5,
    )
    save(fig, "04-structure.png")


def fig05(res: dict) -> None:
    """Tags placed by their actual similarity, not by a force simulation.

    A spring layout on a thresholded graph collapsed the connected core into an
    unreadable hairball and flung the isolates to random corners -- position
    carried no meaning. MDS on the centroid distances puts every tag where its
    similarities say it belongs.
    """
    from sklearn.manifold import MDS

    M = np.array(res["overlap"])
    order = res["overlap_order"]
    zmap = {r["tag"]: r["z"] for r in res["tags"]}
    nmap = {r["tag"]: r["n"] for r in res["tags"]}

    D = np.clip(1.0 - M, 0, None)
    np.fill_diagonal(D, 0.0)
    P = MDS(
        n_components=2,
        metric=True,
        dissimilarity="precomputed",
        random_state=res["seed"],
        n_init=8,
        max_iter=600,
        normalized_stress="auto",
    ).fit_transform(D)
    P -= P.mean(0)

    z = np.array([zmap[t] for t in order])
    n = np.array([nmap[t] for t in order])
    rad = np.linalg.norm(P, axis=1)
    fail = z < Z_PASS
    iu = np.triu_indices(len(M), k=1)
    thresh = float(np.percentile(M[iu], 92))

    fig, top = figure(
        14.4,
        13.4,
        5,
        "the neighbourhood",
        "Every tag placed by how similar it actually is to every other tag",
        f"{len(order)} tags positioned by MDS on 1 - centroid cosine  ·  "
        f"lines join the top 8% most similar pairs (above {thresh:.2f})  ·  "
        f"node size = notes carrying it  ·  colour = z  ·  seed {res['seed']}",
    )
    ax = fig.add_subplot(1, 1, 1)
    ax.set_facecolor("#000000")

    for i, j in zip(*iu):
        if M[i, j] >= thresh:
            s = (M[i, j] - thresh) / (1.0 - thresh + 1e-9)
            ax.plot(
                [P[i, 0], P[j, 0]],
                [P[i, 1], P[j, 1]],
                color=DIM,
                alpha=0.18 + 0.50 * s,
                linewidth=0.4 + 1.7 * s,
                zorder=1,
            )

    sc = ax.scatter(
        P[:, 0],
        P[:, 1],
        s=40 + 11 * n,
        c=z,
        cmap="magma",
        vmin=-4,
        vmax=18,
        alpha=0.95,
        linewidths=0,
        zorder=5,
    )
    for k, tag in enumerate(order):
        ax.annotate(
            tag,
            (P[k, 0], P[k, 1]),
            fontsize=6.2 + 2.4 * (n[k] > 45),
            color=TEXT if z[k] >= Z_PASS else RED,
            ha="center",
            va="center",
            zorder=6,
        )
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_aspect("equal")
    for s_ in ax.spines.values():
        s_.set_color("#2e2e36")
    cb = fig.colorbar(sc, ax=ax, fraction=0.028, pad=0.014)
    cb.set_label("z vs size-matched null", color=MUTED, fontsize=TICK_SIZE)
    cb.ax.tick_params(colors=MUTED, labelsize=TICK_SIZE - 1)
    cb.ax._is_colorbar = True

    inner = ", ".join(order[i] for i in np.argsort(rad)[:6])
    outer = ", ".join(order[i] for i in np.argsort(rad)[-5:])
    panel_title(
        ax,
        f"most central: {inner}  ·  most peripheral: {outer}",
        width=110,
    )

    fig.subplots_adjust(left=MARGIN, right=1 - MARGIN, top=top, bottom=0.078)
    fig.text(
        MARGIN,
        0.046,
        f"The centre is generic and the rim is specific. Failing tags average {rad[fail].mean():.3f} "
        f"from the middle against {rad[~fail].mean():.3f} for passing ones — but centrality does not "
        f"track z (r = {np.corrcoef(rad, z)[0, 1]:+.2f}),",
        color=MUTED,
        fontsize=9.5,
    )
    fig.text(
        MARGIN,
        0.020,
        "because a small tag can land anywhere. The big failures sit centrally because they touch "
        "everything; 'mma', 'blender' and 'reading' sit at the rim because they touch one thing.",
        color=MUTED,
        fontsize=9.5,
    )
    save(fig, "05-neighbourhood.png")


def fig06(res: dict) -> None:
    """The proof of z=-3.4, as a picture rather than a number."""
    import umap

    X = np.load(OUTDIR / "vectors.npz")["X"]
    meta = json.loads((OUTDIR / "tags.json").read_text())
    labels = meta["labels"]

    emb = umap.UMAP(
        n_neighbors=15, min_dist=0.22, metric="cosine", random_state=res["seed"]
    ).fit_transform(X)

    rows = res["tags"]
    best, worst = rows[0], rows[-1]

    fig, top = figure(
        16.5,
        9.2,
        6,
        "sprayed or clustered",
        "The same 493 notes twice, with one tag lit up in each",
        f"UMAP on cosine, n_neighbors=15, min_dist=0.22, seed {res['seed']}  ·  "
        f"the layout is identical in both panels — only the highlight changes",
    )
    gs = fig.add_gridspec(
        1, 2, left=0.04, right=1 - MARGIN - 0.01, top=top, bottom=0.115, wspace=0.06
    )

    for k, r in enumerate([best, worst]):
        ok = r["z"] >= Z_PASS
        hit = np.array([r["tag"] in ts for ts in labels])
        ax = fig.add_subplot(gs[k])
        ax.scatter(emb[~hit, 0], emb[~hit, 1], s=13, color=DIM, alpha=0.55, linewidths=0, zorder=1)
        ax.scatter(
            emb[hit, 0],
            emb[hit, 1],
            s=34,
            color=GOLD if ok else RED,
            alpha=0.92,
            linewidths=0,
            zorder=3,
        )
        # convex-hull-ish spread readout: mean distance from the tag's own centroid
        c = emb[hit].mean(0)
        spread = float(np.linalg.norm(emb[hit] - c, axis=1).mean())
        allspread = float(np.linalg.norm(emb - emb.mean(0), axis=1).mean())
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_aspect("equal")
        for s_ in ax.spines.values():
            s_.set_color("#2e2e36")
        panel_title(
            ax,
            f"{r['tag']}  ·  n={r['n']}  ·  z={r['z']:+.1f}  ·  "
            f"spread {spread:.1f} vs {allspread:.1f} for the whole corpus",
            width=62,
        )

    fig.text(
        MARGIN,
        0.050,
        "Left: a tag that names a place. Right: a tag that names a feeling about the note. Both "
        "are applied consistently and neither is wrong — but only one of them is findable by "
        "similarity search, which is the only way this vault retrieves anything.",
        color=MUTED,
        fontsize=9.5,
    )
    fig.text(
        MARGIN,
        0.022,
        "The spread number is the giveaway: the failing tag's notes are scattered as widely as the "
        "entire corpus is.",
        color=MUTED,
        fontsize=9.5,
    )
    save(fig, "06-sprayed-or-clustered.png")


def fig07(res: dict) -> None:
    """Retrieval-flavoured restatement: do a note's neighbours share its tags?"""
    X = np.load(OUTDIR / "vectors.npz")["X"]
    meta = json.loads((OUTDIR / "tags.json").read_text())
    labels = meta["labels"]
    K = 10

    S = X @ X.T
    np.fill_diagonal(S, -np.inf)
    nn = np.argsort(-S, axis=1)[:, :K]

    rows = []
    for r in res["tags"]:
        tag = r["tag"]
        hit = np.array([tag in ts for ts in labels])
        idx = np.flatnonzero(hit)
        # of this note's K nearest neighbours, how many also carry the tag?
        purity = float(np.mean([hit[nn[i]].mean() for i in idx]))
        base = float(hit.mean())  # what you would get by drawing neighbours at random
        rows.append({"tag": tag, "n": r["n"], "z": r["z"], "purity": purity, "base": base})

    rows.sort(key=lambda x: -(x["purity"] - x["base"]))
    lift = np.array([x["purity"] - x["base"] for x in rows])
    zs = np.array([x["z"] for x in rows])

    fig, top = figure(
        16.5,
        7.6,
        7,
        "does it help retrieval",
        "If a tag is real, a note's nearest neighbours should carry it too",
        f"for every note carrying a tag: what fraction of its {K} nearest neighbours also carry it, "
        f"minus the fraction you would get from random neighbours  ·  cosine, full corpus",
    )
    gs = fig.add_gridspec(
        1,
        2,
        width_ratios=[1.25, 1.0],
        left=0.125,
        right=1 - MARGIN - 0.015,
        top=top,
        bottom=0.135,
        wspace=0.20,
    )

    ax = fig.add_subplot(gs[0])
    show = rows[:14] + rows[-8:]
    y = np.arange(len(show))[::-1]
    ax.barh(
        y,
        [x["purity"] - x["base"] for x in show],
        color=[GOLD if x["z"] >= Z_PASS else RED for x in show],
        alpha=0.9,
        height=0.74,
    )
    ax.set_yticks(y)
    ax.set_yticklabels([f"{x['tag']} ({x['n']})" for x in show], fontsize=TICK_SIZE - 0.5)
    ax.axvline(0, color=MUTED, linewidth=1.2)
    style_axes(ax)
    ax.set_xlabel(f"neighbour purity above chance (top {K})")
    panel_title(ax, "best 14 and worst 8", width=56)

    ax = fig.add_subplot(gs[1])
    ax.scatter(zs, lift, color=GOLD, s=26, alpha=0.7, linewidths=0)
    ax.axhline(0, color=MUTED, linewidth=1.2)
    ax.axvline(Z_PASS, color=CYAN, linewidth=1.2, linestyle="--")
    r = float(np.corrcoef(zs, lift)[0, 1])
    style_axes(ax)
    ax.set_xlabel("z from figure 01 (centroid cohesion)")
    ax.set_ylabel("neighbour purity above chance")
    panel_title(
        ax,
        f"the two measures agree — r = {r:+.2f}",
        width=52,
    )

    fig.text(
        MARGIN,
        0.045,
        "Two independent statistics, one conclusion: cohesion measured on centroids and purity "
        "measured on nearest neighbours rank the tags the same way.",
        color=MUTED,
        fontsize=9.5,
    )
    save(fig, "07-retrieval.png")


def fig08(res: dict) -> None:
    """Mosaic: does each source get the same vocabulary?

    Tile width is the source's share of all tag applications, tile height is
    that tag's share within the source, so every tile's AREA is its cell count.
    Colour is the standardized Pearson residual against independence -- how
    surprised a chi-square test is by that cell.
    """
    import matplotlib.colors as mcolors

    meta = json.loads((OUTDIR / "tags.json").read_text())
    labels, sources = meta["labels"], meta["sources"]

    # the small sources are real but too thin to read as columns of their own
    grouped = [s if s in ("youtube", "instagram") else "other" for s in sources]
    src_order = ["youtube", "instagram", "other"]
    tag_order = [r["tag"] for r in sorted(res["tags"], key=lambda r: -r["n"])[:14]]

    T = np.zeros((len(tag_order), len(src_order)))
    for ts, s in zip(labels, grouped):
        j = src_order.index(s)
        for tag in ts:
            if tag in tag_order:
                T[tag_order.index(tag), j] += 1

    total = T.sum()
    exp = T.sum(1, keepdims=True) @ T.sum(0, keepdims=True) / total
    resid = (T - exp) / np.sqrt(exp)
    chi2 = float((resid**2).sum())
    dof = (T.shape[0] - 1) * (T.shape[1] - 1)

    cmap = mcolors.LinearSegmentedColormap.from_list(
        "resid", [CYAN, "#12121a", "#12121a", RED], N=256
    )
    lim = float(np.abs(resid).max())

    fig, top = figure(
        15.4,
        10.4,
        8,
        "one vocabulary, three sources",
        "Does a YouTube video get tagged like an Instagram post?",
        f"mosaic over {int(total)} tag applications on the 14 most common tags  ·  "
        f"tile area = cell count  ·  colour = standardized residual vs independence  ·  "
        f"chi-square {chi2:.0f} on {dof} dof",
    )
    ax = fig.add_subplot(1, 1, 1)
    ax.set_facecolor("#000000")

    colw = T.sum(0) / total
    gap = 0.006
    x = 0.0
    for j, s in enumerate(src_order):
        w = colw[j] - gap
        share = T[:, j] / T[:, j].sum()
        y = 0.0
        for i, tag in enumerate(tag_order):
            h = share[i]
            ax.add_patch(
                plt.Rectangle(
                    (x, y),
                    w,
                    h - 0.004,
                    facecolor=cmap((resid[i, j] + lim) / (2 * lim)),
                    edgecolor="#2e2e36",
                    linewidth=0.5,
                )
            )
            if h > 0.045 and w > 0.10:
                ax.text(
                    x + w / 2,
                    y + h / 2,
                    f"{tag}\n{int(T[i, j])}",
                    ha="center",
                    va="center",
                    fontsize=TICK_SIZE - 1.4,
                    color=TEXT,
                )
            y += h
        ax.text(
            x + w / 2,
            1.028,
            f"{s}  ({int(T[:, j].sum())})",
            ha="center",
            color=GOLD,
            fontsize=TICK_SIZE + 2,
        )
        x += colw[j]

    ax.set_xlim(-0.004, 1.004)
    ax.set_ylim(0, 1.075)
    ax.set_xticks([])
    ax.set_yticks([])
    for s_ in ax.spines.values():
        s_.set_color("#2e2e36")

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=mcolors.Normalize(-lim, lim))
    cb = fig.colorbar(sm, ax=ax, fraction=0.026, pad=0.014)
    cb.set_label("standardized residual  (red = over-used here)", color=MUTED, fontsize=TICK_SIZE)
    cb.ax.tick_params(colors=MUTED, labelsize=TICK_SIZE - 1)
    cb.ax._is_colorbar = True

    top_over = [
        (resid[i, j], tag_order[i], src_order[j])
        for i in range(len(tag_order))
        for j in range(len(src_order))
    ]
    top_over.sort(reverse=True)
    hi = ", ".join(f"{t} in {s}" for _, t, s in top_over[:3])

    fig.subplots_adjust(left=0.035, right=0.93, top=top, bottom=0.10)
    fig.text(
        MARGIN,
        0.058,
        f"The columns are not the same shape, so the vocabulary is not source-neutral. "
        f"Most over-used: {hi}.",
        color=MUTED,
        fontsize=9.5,
    )
    fig.text(
        MARGIN,
        0.028,
        "This is the shape of issue #37 — but a tagger assigning topics purely from content would "
        "still differ by source, because the sources genuinely differ. The mosaic does not prove "
        "mis-tagging; it localizes where to look.",
        color=MUTED,
        fontsize=9.5,
    )
    save(fig, "08-mosaic.png")


def _umap3(X: np.ndarray, seed: int) -> np.ndarray:
    import umap

    return umap.UMAP(
        n_components=3, n_neighbors=15, min_dist=0.10, metric="cosine", random_state=seed
    ).fit_transform(X)


def fig09(res: dict) -> None:
    """The corpus as a solid, from four angles."""
    X = np.load(OUTDIR / "vectors.npz")["X"]
    meta = json.loads((OUTDIR / "tags.json").read_text())
    sources = np.array(meta["sources"])
    labels = meta["labels"]
    P = _umap3(X, res["seed"])

    ntags = np.array([len(t) for t in labels], float)
    palette = {
        "youtube": GOLD,
        "instagram": CYAN,
        "web": RED,
        "tiktok": BLUE,
        "pinterest": "#9159ff",
        "reddit": "#ff9f43",
        "journal": TEXT,
    }
    colors = np.array([palette.get(s, DIM) for s in sources])

    fig, top = figure(
        13.4,
        13.8,
        9,
        "the corpus as a solid",
        "493 notes in three dimensions, coloured by where they came from",
        f"UMAP n_components=3, n_neighbors=15, min_dist=0.10, cosine, seed {res['seed']}  ·  "
        f"point size = how many tags the note carries  ·  four viewing angles of one embedding",
    )
    views = [(18, 35), (18, 125), (62, 35), (62, 215)]
    for k, (elev, azim) in enumerate(views):
        ax = fig.add_subplot(2, 2, k + 1, projection="3d")
        ax.scatter(
            P[:, 0],
            P[:, 1],
            P[:, 2],
            c=colors,
            s=6 + 2.6 * ntags,
            alpha=0.72,
            linewidths=0,
            depthshade=True,
        )
        fit3d(ax, P, zoom=1.55)
        ax.view_init(elev=elev, azim=azim)
        panel_title(ax, f"elev {elev}°, azim {azim}°")
    fig.subplots_adjust(
        left=MARGIN, right=1 - MARGIN, top=top, bottom=0.062, wspace=0.03, hspace=0.10
    )

    counts = {s: int((sources == s).sum()) for s in palette if (sources == s).sum()}
    legend = "   ".join(f"{s} {n}" for s, n in sorted(counts.items(), key=lambda kv: -kv[1]))
    fig.text(MARGIN, 0.030, legend, color=MUTED, fontsize=9.5)
    fig.text(
        MARGIN,
        0.008,
        "YouTube and Instagram interleave rather than separating, which is the point: the space is "
        "organized by subject, not by where a note came from.",
        color=MUTED,
        fontsize=9.5,
    )
    save(fig, "09-corpus-3d.png")


def fig10(res: dict) -> None:
    """Five dimensions: position (3), colour (4), size (5).

    The question this exists for: tagging quality is not uniform across the
    corpus, so WHERE is it weak? Give every note a score -- the mean z of the
    tags it carries -- and paint the solid with it.
    """
    X = np.load(OUTDIR / "vectors.npz")["X"]
    meta = json.loads((OUTDIR / "tags.json").read_text())
    labels, sources = meta["labels"], np.array(meta["sources"])
    zmap = {r["tag"]: r["z"] for r in res["tags"]}
    P = _umap3(X, res["seed"])

    # a note's tag quality: mean z over its scorable tags. Notes whose tags are
    # all rare get no score and are drawn as the dim background.
    scored, quality = [], []
    for i, ts in enumerate(labels):
        zs = [zmap[t] for t in ts if t in zmap]
        if zs:
            scored.append(i)
            quality.append(float(np.mean(zs)))
    scored = np.array(scored)
    quality = np.array(quality)
    ntags = np.array([len([t for t in labels[i] if t in zmap]) for i in scored], float)
    cmap = saturated_magma()

    fig, top = figure(
        16.5,
        9.6,
        10,
        "where the tagging is weak",
        "The same solid, painted by how informative each note's tags are",
        f"{len(scored)} of {len(labels)} notes carry at least one scorable tag  ·  "
        f"colour = mean z of a note's tags  ·  size = how many scorable tags it has  ·  "
        f"the two right-hand panels split the same points by source",
    )

    # explicit grid: mixing add_subplot(1,2,1) with add_subplot(2,4,k) put the
    # instagram panel underneath the big one
    gs = fig.add_gridspec(
        2,
        4,
        width_ratios=[1.0, 1.0, 0.78, 0.92],
        left=0.015,
        right=1 - MARGIN,
        top=top,
        bottom=0.215,
        wspace=0.14,
        hspace=0.26,
    )

    ax = fig.add_subplot(gs[:, 0:2], projection="3d")
    ax.scatter(
        P[:, 0], P[:, 1], P[:, 2], color=DIM, s=5, alpha=0.30, linewidths=0, depthshade=False
    )
    sc = ax.scatter(
        P[scored, 0],
        P[scored, 1],
        P[scored, 2],
        c=quality,
        cmap=cmap,
        vmin=0,
        vmax=10,
        s=8 + 4.2 * ntags,
        alpha=0.88,
        linewidths=0,
        depthshade=True,
    )
    fit3d(ax, P, zoom=1.5)
    ax.view_init(elev=22, azim=48)
    panel_title(ax, "bright = its tags are informative; dark = its tags are generic", width=64)
    box = ax.get_position()
    cax = fig.add_axes([box.x0 + 0.06, 0.145, box.width - 0.12, 0.018])
    cb = fig.colorbar(sc, cax=cax, orientation="horizontal")
    cb.set_label("mean tag z for the note", color=MUTED, fontsize=TICK_SIZE)
    cb.ax.tick_params(colors=MUTED, labelsize=TICK_SIZE - 1)
    cb.outline.set_edgecolor("#2e2e36")
    cb.ax._is_colorbar = True

    for k, src in enumerate(["youtube", "instagram"]):
        ax = fig.add_subplot(gs[k, 2], projection="3d")
        m = sources[scored] == src
        ax.scatter(
            P[:, 0], P[:, 1], P[:, 2], color=DIM, s=3, alpha=0.22, linewidths=0, depthshade=False
        )
        ax.scatter(
            P[scored[m], 0],
            P[scored[m], 1],
            P[scored[m], 2],
            c=quality[m],
            cmap=cmap,
            vmin=0,
            vmax=10,
            s=11,
            alpha=0.92,
            linewidths=0,
        )
        fit3d(ax, P, zoom=1.72)
        ax.view_init(elev=22, azim=48)
        panel_title(ax, f"{src}  ·  mean z {quality[m].mean():.1f}", width=34)

    ax = fig.add_subplot(gs[:, 3])
    for src, col in [("youtube", GOLD), ("instagram", CYAN)]:
        m = sources[scored] == src
        ax.hist(
            quality[m], bins=np.linspace(-2, 14, 34), color=col, alpha=0.62, density=True, label=src
        )
    ax.axvline(float(np.median(quality)), color=MUTED, linewidth=1.2, linestyle="--")
    style_axes(ax)
    ax.set_xlabel("mean tag z for the note")
    ax.set_ylabel("density")
    ax.legend(loc="upper right", fontsize=TICK_SIZE - 1, framealpha=0.0, labelcolor=TEXT)
    yt = quality[sources[scored] == "youtube"]
    ig = quality[sources[scored] == "instagram"]
    panel_title(ax, f"youtube {yt.mean():.1f}  vs  instagram {ig.mean():.1f}", width=34)

    fig.text(
        MARGIN,
        0.062,
        f"Tag quality is not uniform. YouTube notes average {yt.mean():.1f} against "
        f"{ig.mean():.1f} for Instagram — the longer the source text, the more specific the tags "
        f"the model can justify.",
        color=MUTED,
        fontsize=9.5,
    )
    fig.text(
        MARGIN,
        0.034,
        "Only YouTube has the bright tail above z=10. The dark regions are where the vault is "
        "labelled 'reference' and 'learning' and nothing sharper — where a tag-driven search "
        "would fail to reach.",
        color=MUTED,
        fontsize=9.5,
    )
    save(fig, "10-tag-quality-3d.png")


def main() -> None:
    res = json.loads((OUTDIR / "results.json").read_text())
    plt.style.use("dark_background")
    fig01(res)
    fig02(res)
    fig03(res)
    fig04(res)
    fig05(res)
    fig06(res)
    fig07(res)
    fig08(res)
    fig09(res)
    fig10(res)


if __name__ == "__main__":
    main()
