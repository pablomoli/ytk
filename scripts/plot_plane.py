"""What a 2D plane through 1024-d embeddings actually shows (#12 follow-up).

Two documents span a plane. The plane is exact for those two documents and
misleading about everything else, and the reason is the cone measured in
docs/assets/12-embedding-geometry: an arbitrary pair-plane inherits the shared
offset direction, so unrelated notes cast a shadow eight times longer than
chance and look near-coplanar when they are not.

Measured, not asserted. Three questions in one file:

    01  what does the plane of two notes show, against an isotropic control
    02  which basis you pick changes the answer more than which points you draw
    03  choosing the plane from a neighborhood is what makes it informative

    analyze -> results.json + plane3d.json (manim sidecar)
    plot    -> *.png

STRICTLY READ-ONLY: reads the frozen vectors.npz captured by
scripts/tag_coherence.py. Touches neither the vault nor Chroma.

    uv run --with matplotlib python scripts/plot_plane.py
"""

from __future__ import annotations

import json
import sys
import textwrap
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
OUTDIR = Path(__file__).resolve().parents[1] / "docs" / "assets" / "15-plane-geometry"
RESULTS = OUTDIR / "results.json"
SIDECAR = Path(__file__).resolve().parent / "manim" / "plane3d.json"
SEED = 20260802

# The pair drawn throughout. Index 0 is a coding-interview video and 250 an
# Instagram heatmap capture: unrelated on purpose, so any apparent structure in
# their plane is the geometry talking, not the topic.
PAIR = (0, 250)
K_NEIGHBORS = 24


def save(fig, name: str) -> None:
    frame_panels(fig)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    out = OUTDIR / name
    fig.savefig(out, dpi=DPI, facecolor="#08080a")
    print(f"wrote {out.relative_to(OUTDIR.parents[2])}  ({out.stat().st_size // 1024}KB)")
    plt.close(fig)


def _unit(M: np.ndarray) -> np.ndarray:
    return M / (np.linalg.norm(M, axis=1, keepdims=True) + 1e-12)


def plane_basis(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Orthonormal basis of span(a, b) by Gram-Schmidt.

    Row 0 is a's direction, so a always lands on the x-axis: the coordinates
    depend on argument order even though the plane does not.
    """
    e1 = a / np.linalg.norm(a)
    r = b - (b @ e1) * e1
    n = float(np.linalg.norm(r))
    if n < 1e-9:
        raise ValueError("collinear vectors span a line, not a plane")
    return np.vstack([e1, r / n])


def retained(M: np.ndarray, B: np.ndarray) -> np.ndarray:
    """Fraction of each unit row's length that survives projection onto B."""
    return np.linalg.norm(_unit(M) @ B.T, axis=1)


def analyze() -> dict:
    X = np.load(SRC / "vectors.npz")["X"].astype(np.float64)
    meta = json.loads((SRC / "tags.json").read_text())
    names = meta["names"]
    n, dim = X.shape
    i, j = PAIR

    mu = X.mean(0)
    Xc = _unit(X - mu)
    rng = np.random.default_rng(SEED)

    # isotropic control: same n, same dimension, no structure
    Y = _unit(rng.normal(size=X.shape))

    B_pair = plane_basis(X[i], X[j])
    B_pair_cen = plane_basis(Xc[i], Xc[j])
    B_iso = plane_basis(Y[0], Y[1])

    # global bases
    sv = np.linalg.svd(X - mu, full_matrices=False)
    B_svd = sv[2][:2]
    e1 = mu / np.linalg.norm(mu)
    R = X - np.outer(X @ e1, e1)
    B_cone = np.vstack([e1, np.linalg.svd(R - R.mean(0), full_matrices=False)[2][0]])

    # a neighborhood, and a plane fitted to it
    sims = X @ X[i]
    order = np.argsort(-sims)
    nb = order[:K_NEIGHBORS]
    rest = np.setdiff1d(np.arange(n), nb)
    B_simpair = plane_basis(X[i], X[order[1]])
    N = Xc[nb]
    B_local = np.linalg.svd(N - N.mean(0), full_matrices=False)[2][:2]

    def stats(M, B):
        r = retained(M, B)
        return {
            "median": float(np.median(r)),
            "p95": float(np.percentile(r, 95)),
            "neighbors": float(np.median(r[nb])),
            "rest": float(np.median(r[rest])),
        }

    bases = {
        "pair_raw": stats(X, B_pair),
        "pair_centered": stats(Xc, B_pair_cen),
        "isotropic": stats(Y, B_iso),
        "svd_top2": stats(Xc, B_svd),
        "cone": stats(X, B_cone),
        "similar_pair": stats(X, B_simpair),
        "local_pca": stats(Xc, B_local),
    }

    ev = sv[1] ** 2
    ev = ev / ev.sum()

    out = {
        "seed": SEED,
        "n_notes": int(n),
        "dim": int(dim),
        "pair": {
            "i": i,
            "j": j,
            "a": names[i],
            "b": names[j],
            "cos_raw": float(X[i] @ X[j]),
            "cos_centered": float(Xc[i] @ Xc[j]),
        },
        "chance_retained": float(np.sqrt(2 / dim)),
        "top2_variance": float(ev[:2].sum()),
        "k_neighbors": K_NEIGHBORS,
        "neighbor_names": [names[k] for k in order[1:6]],
        "neighbor_sims": [float(sims[k]) for k in order[1:6]],
        "bases": bases,
        "coords": {
            "pair_raw": (X @ B_pair.T).round(4).tolist(),
            "pair_centered": (Xc @ B_pair_cen.T).round(4).tolist(),
            "isotropic": (Y @ B_iso.T).round(4).tolist(),
            "svd_top2": (Xc @ B_svd.T).round(4).tolist(),
            "cone": (X @ B_cone.T).round(4).tolist(),
            "similar_pair": (X @ B_simpair.T).round(4).tolist(),
            "local_pca": (Xc @ B_local.T).round(4).tolist(),
        },
        "retained": {
            k: retained(M, B).round(4).tolist()
            for k, M, B in [
                ("pair_raw", X, B_pair),
                ("pair_centered", Xc, B_pair_cen),
                ("isotropic", Y, B_iso),
                ("svd_top2", Xc, B_svd),
                ("cone", X, B_cone),
                ("similar_pair", X, B_simpair),
                ("local_pca", Xc, B_local),
            ]
        },
        "neighbor_idx": nb.tolist(),
    }
    OUTDIR.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(out, indent=1))
    _write_sidecar(X, Xc, B_cone, B_pair, nb, out)

    print(f"{n} notes, {dim} dims — chance retained {out['chance_retained']:.4f}")
    for k, v in bases.items():
        print(
            f"  {k:16s} median {v['median']:.3f}   neighbors {v['neighbors']:.3f}   rest {v['rest']:.3f}"
        )
    return out


def _write_sidecar(X, Xc, B_cone, B_pair, nb, out) -> None:
    """3D coordinates for the manim scene: the cone basis, one extra axis.

    manim needs a 3D scene to show a 2D plane inside a bigger space, so the
    'ambient' space is the 3-axis cone basis (mean direction + two residual
    directions) and the drawn plane is the pair plane expressed in it.
    """
    e1 = B_cone[0]
    R = X - np.outer(X @ e1, e1)
    V = np.linalg.svd(R - R.mean(0), full_matrices=False)[2][:2]
    B3 = np.vstack([e1, V[0], V[1]])
    P = X @ B3.T
    Pc = Xc @ B3.T
    SIDECAR.write_text(
        json.dumps(
            {
                "seed": SEED,
                "cone": P.round(4).tolist(),
                "centred": Pc.round(4).tolist(),
                # pair plane axes expressed in the 3D cone basis
                "plane_u": (B_pair[0] @ B3.T).round(4).tolist(),
                "plane_v": (B_pair[1] @ B3.T).round(4).tolist(),
                "pair": [out["pair"]["i"], out["pair"]["j"]],
                "neighbors": nb.tolist(),
                "retained_raw": out["retained"]["pair_raw"],
                "retained_centred": out["retained"]["pair_centered"],
            }
        )
    )
    print(f"wrote {SIDECAR.relative_to(SIDECAR.parents[2])}")


def _footer(fig, y: float, text: str, width: int = 132) -> None:
    """Wrapped footer. The figure is 16.5in wide; unwrapped prose at this size
    runs past the frame and gets clipped by savefig."""
    fig.text(MARGIN, y, textwrap.fill(text, width), color=MUTED, fontsize=9.5, linespacing=1.6)


def _share_limits(axes, pad: float = 0.06) -> None:
    """One square window across a row of panels.

    Distance from the origin is the quantity these panels are about, so
    per-panel autoscaling would rescale away the exact thing being compared.
    """
    lo = min(min(ax.get_xlim()[0], ax.get_ylim()[0]) for ax in axes) - pad
    hi = max(max(ax.get_xlim()[1], ax.get_ylim()[1]) for ax in axes) + pad
    for ax in axes:
        ax.set_xlim(lo, hi)
        ax.set_ylim(lo, hi)


def _scatter(ax, P, retained_vals, hi=None, hi_color=RED, s=9):
    ax.scatter(P[:, 0], P[:, 1], s=s, c=DIM, alpha=0.75, linewidths=0)
    if hi is not None:
        ax.scatter(P[hi, 0], P[hi, 1], s=s * 2.4, c=hi_color, alpha=0.95, linewidths=0)
    ax.axhline(0, color="#1e1e26", linewidth=0.8, zorder=-2)
    ax.axvline(0, color="#1e1e26", linewidth=0.8, zorder=-2)
    ax.scatter([0], [0], s=42, marker="+", c=CYAN, linewidths=1.4, zorder=5)
    ax.set_aspect("equal")
    style_axes(ax)


def fig01(r: dict) -> None:
    """The plane of two notes, against a control and against centring."""
    C = r["coords"]
    b = r["bases"]
    i, j = r["pair"]["i"], r["pair"]["j"]
    chance = r["chance_retained"]

    fig, top = figure(
        16.5,
        8.2,
        1,
        "two documents, one plane",
        "Exact for the two notes that made it, misleading about every other note",
        f"493 notes projected onto span(A, B)  ·  chance retention for 2 of 1024 dimensions is "
        f"{chance:.3f}  ·  read the numbers under each panel, not the shapes",
    )
    gs = fig.add_gridspec(
        1, 3, left=0.045, right=1 - MARGIN - 0.015, top=top, bottom=0.26, wspace=0.16
    )

    panels = [
        ("pair_raw", "the vault, as stored", GOLD),
        ("isotropic", "493 random vectors, same dimension", DIM),
        ("pair_centered", "the vault, shared direction removed", BLUE),
    ]
    for col, (key, title, color) in enumerate(panels):
        ax = fig.add_subplot(gs[col])
        P = np.array(C[key])
        _scatter(ax, P, r["retained"][key], hi=[i, j] if key != "isotropic" else [0, 1])
        med = b[key]["median"]
        ax.set_xlabel(f"median length retained  {med:.3f}   ({med / chance:.1f}x chance)")
        panel_title(ax, title, width=40)
        for spine in ax.spines.values():
            spine.set_color(color if key != "isotropic" else "#2e2e36")

    _share_limits(fig.axes)
    ax = fig.axes[0]
    ax.annotate(
        "A",
        xy=(np.array(C["pair_raw"])[i]),
        color=RED,
        fontsize=11,
        xytext=(6, 6),
        textcoords="offset points",
    )
    ax.annotate(
        "B",
        xy=(np.array(C["pair_raw"])[j]),
        color=RED,
        fontsize=11,
        xytext=(6, 6),
        textcoords="offset points",
    )

    fig.text(
        MARGIN,
        0.145,
        f"A  {r['pair']['a'][:66]}\nB  {r['pair']['b'][:66]}",
        color=TEXT,
        fontsize=9.0,
        linespacing=1.6,
    )
    _footer(
        fig,
        0.035,
        f"cos(A, B) = {r['pair']['cos_raw']:+.3f} as stored, {r['pair']['cos_centered']:+.3f} centred. "
        "The left panel looks like a corpus with structure. It is the same cloud as the middle panel "
        "plus one shared direction that every note carries, and that direction lies inside almost any "
        "plane you can build from two raw vectors.",
    )
    save(fig, "01-the-plane.png")


def fig02(r: dict) -> None:
    """Which basis you pick changes the picture more than which points."""
    C, b = r["coords"], r["bases"]
    chance = r["chance_retained"]

    fig, top = figure(
        16.5,
        8.4,
        2,
        "the axes are a choice",
        "Same 493 notes, three different planes — and none of them is the corpus",
        f"top two components of the centred corpus carry only {r['top2_variance']:.1%} of its "
        f"variance  ·  participation ratio 104 of 1024 (fig 02, 12-embedding-geometry)",
    )
    gs = fig.add_gridspec(
        2,
        3,
        height_ratios=[1.0, 0.42],
        left=0.045,
        right=1 - MARGIN - 0.015,
        top=top,
        bottom=0.145,
        wspace=0.16,
        hspace=0.42,
    )

    panels = [
        ("pair_raw", "span(A, B) — two arbitrary notes", GOLD),
        ("svd_top2", "top two SVD directions of the centred corpus", BLUE),
        ("cone", "the cone basis: mean direction, then residual", CYAN),
    ]
    tops = []
    for col, (key, title, color) in enumerate(panels):
        ax = fig.add_subplot(gs[0, col])
        tops.append(ax)
        _scatter(ax, np.array(C[key]), r["retained"][key])
        panel_title(ax, title, width=40)
        med = b[key]["median"]
        ax.set_xlabel(f"median retained {med:.3f}  ({med / chance:.1f}x chance)")

        axh = fig.add_subplot(gs[1, col])
        vals = np.array(r["retained"][key])
        axh.hist(vals, bins=44, range=(0, 0.8), color=color, alpha=0.9)
        axh.axvline(chance, color=RED, linewidth=1.2, linestyle="--")
        axh.text(chance + 0.012, axh.get_ylim()[1] * 0.62, "chance", color=RED, fontsize=TICK_SIZE)
        style_axes(axh)
        axh.set_xlabel("fraction of length retained")

    _share_limits(tops)
    _footer(
        fig,
        0.035,
        "The cone basis retains the most because its first axis IS the shared direction — it is the "
        "honest way to see the offset, and the worst way to see anything else. The SVD plane is the "
        "best 2D fit in the least-squares sense and still keeps only a quarter of a typical note: "
        "that is not a flaw in the projection, it is the participation ratio being real.",
    )
    save(fig, "02-choosing-the-axes.png")


def fig03(r: dict) -> None:
    """Fit the plane to a neighborhood instead of to two arbitrary points."""
    C, b = r["coords"], r["bases"]
    nb = np.array(r["neighbor_idx"])
    chance = r["chance_retained"]

    fig, top = figure(
        16.5,
        8.0,
        3,
        "project similar items",
        "A plane fitted to a neighborhood separates that neighborhood from the rest — an arbitrary plane does not",
        f"query: {r['pair']['a'][:58]}  ·  k = {r['k_neighbors']} nearest by cosine  ·  "
        f"local plane is the top two SVD directions of the centred neighborhood",
    )
    gs = fig.add_gridspec(
        1,
        3,
        width_ratios=[1.0, 1.0, 1.06],
        left=0.045,
        right=1 - MARGIN - 0.015,
        top=top,
        bottom=0.175,
        wspace=0.2,
    )

    for col, (key, title) in enumerate(
        [
            ("pair_raw", "arbitrary plane: neighbors sit where everyone sits"),
            ("local_pca", "local plane: neighbors keep their length, the rest collapse"),
        ]
    ):
        ax = fig.add_subplot(gs[col])
        _scatter(ax, np.array(C[key]), r["retained"][key], hi=nb, hi_color=GOLD)
        panel_title(ax, title, width=42)
        s = b[key]
        ax.set_xlabel(
            f"neighbors {s['neighbors']:.3f}   rest {s['rest']:.3f}   "
            f"separation {s['neighbors'] / s['rest']:.1f}x"
        )

    ax = fig.add_subplot(gs[2])
    keys = ["pair_raw", "similar_pair", "svd_top2", "local_pca"]
    labels = ["arbitrary\npair", "similar\npair", "global\nSVD", "local\nPCA"]
    xs = np.arange(len(keys))
    ax.bar(xs - 0.19, [b[k]["neighbors"] for k in keys], width=0.36, color=GOLD, label="neighbors")
    ax.bar(xs + 0.19, [b[k]["rest"] for k in keys], width=0.36, color=DIM, label="everything else")
    ax.axhline(chance, color=RED, linewidth=1.2, linestyle="--")
    ax.text(len(keys) - 0.7, chance + 0.012, "chance", color=RED, fontsize=TICK_SIZE)
    ax.set_xticks(xs)
    ax.set_xticklabels(labels, color=MUTED, fontsize=TICK_SIZE)
    style_axes(ax)
    ax.set_ylabel("median fraction of length retained")
    leg = ax.legend(frameon=False, fontsize=TICK_SIZE, loc="upper left")
    for t in leg.get_texts():
        t.set_color(MUTED)
    panel_title(ax, "how well each plane tells the two groups apart", width=44)

    _footer(
        fig,
        0.035,
        "This is the answer to 'can we project similar items instead': the useful knob is not which "
        "points you draw, it is which plane you fit. Centre first, fit the axes to the neighborhood, "
        "and the plane becomes a local instrument — faithful inside the neighborhood and honestly "
        "uninformative outside it, which is exactly what a 2D view of a 104-dimensional cloud should be.",
    )
    save(fig, "03-project-similar.png")


def _load_xnames() -> tuple[np.ndarray, list[str]]:
    X = np.load(SRC / "vectors.npz")["X"].astype(np.float64)
    names = json.loads((SRC / "tags.json").read_text())["names"]
    return X, names


def slerp(a: np.ndarray, b: np.ndarray, t: float) -> np.ndarray:
    """Walk along the sphere from a to b; stays unit-length and inside
    span(a, b) the whole way, so the pair plane shows the path exactly."""
    om = float(np.arccos(np.clip(a @ b, -1.0, 1.0)))
    return (np.sin((1 - t) * om) * a + np.sin(t * om) * b) / np.sin(om)


def fig04(r: dict) -> None:
    """More of the dimensionality: the same cloud through four orthogonal
    windows, and how slowly the variance accumulates."""
    X, _ = _load_xnames()
    Xc = _unit(X - X.mean(0))
    V = np.linalg.svd(Xc - Xc.mean(0), full_matrices=False)[2]
    ev = np.linalg.svd(Xc - Xc.mean(0), compute_uv=False) ** 2
    ev = ev / ev.sum()

    fig, top = figure(
        16.5,
        7.8,
        4,
        "more of the dimensionality",
        "Four orthogonal windows onto the same cloud — and none of them is emptier than the last",
        "centred corpus through spread-sorted axis pairs  ·  every window is perpendicular to "
        "every other  ·  a low-dimensional cloud would go dark by the second window",
    )
    gs = fig.add_gridspec(
        1,
        5,
        width_ratios=[1, 1, 1, 1, 1.25],
        left=0.045,
        right=1 - MARGIN - 0.015,
        top=top,
        bottom=0.20,
        wspace=0.22,
    )

    panels = []
    for w in range(4):
        B = V[2 * w : 2 * w + 2]
        P = Xc @ B.T
        med = float(np.median(np.linalg.norm(P, axis=1)))
        var = float(ev[2 * w : 2 * w + 2].sum())
        ax = fig.add_subplot(gs[w])
        panels.append(ax)
        _scatter(ax, P, None, s=7)
        panel_title(ax, f"axes {2 * w + 1} and {2 * w + 2}", width=30)
        ax.set_xlabel(f"retains {med:.2f} · {var:.1%} of variance")
    _share_limits(panels)

    ax = fig.add_subplot(gs[4])
    ks = np.arange(1, len(ev) + 1)
    ax.plot(ks, np.cumsum(ev), color=GOLD, linewidth=2.0)
    ax.set_xscale("log")
    for k, lab in [(2, "one window"), (8, "these four"), (104, "participation\nratio")]:
        c = float(np.cumsum(ev)[k - 1])
        ax.plot([k], [c], "o", color=CYAN, markersize=5)
        ax.annotate(
            f"{lab}\n{c:.0%}",
            (k, c),
            textcoords="offset points",
            xytext=(8, -26),
            color=CYAN,
            fontsize=TICK_SIZE,
        )
    style_axes(ax)
    ax.set_xlabel("axes kept (log)")
    ax.set_ylabel("share of variance seen")
    ax.set_ylim(0, 1.02)
    panel_title(ax, "how slowly the cloud gives itself up", width=40)

    _footer(
        fig,
        0.045,
        "Each window keeps roughly the same fraction of a typical note — that is what 104 effective "
        "dimensions looks like from inside. No 2D picture of this cloud can be faithful; the choice "
        "is only WHICH unfaithful window is useful for the question at hand.",
    )
    save(fig, "04-more-windows.png")


def fig05(r: dict) -> None:
    """Interpolation, decoded by retrieval: the slerp arc lives exactly in
    the pair plane, and the corpus is the codebook."""
    X, names = _load_xnames()

    def pair_panel(ax, i, j, title):
        a, b = X[i], X[j]
        B = plane_basis(a, b)
        P = X @ B.T
        om = float(np.arccos(np.clip(a @ b, -1, 1)))
        ax.scatter(P[:, 0], P[:, 1], s=8, c=DIM, alpha=0.7, linewidths=0)
        th = np.linspace(0, om, 60)
        ax.plot(np.cos(th), np.sin(th), color=CYAN, linewidth=1.8)
        ax.plot([1, np.cos(om)], [0, np.sin(om)], color=RED, linewidth=1.1, linestyle="--")
        mid = (a + b) / 2
        ax.annotate(
            f"straight line: length {np.linalg.norm(mid):.2f}",
            (np.cos(om / 2) * 0.78, np.sin(om / 2) * 0.78),
            color=RED,
            fontsize=TICK_SIZE,
            ha="center",
        )
        for t in (0.25, 0.5, 0.75):
            v = slerp(a, b, t)
            s = X @ v
            s[[i, j]] = -1
            k = int(np.argmax(s))
            th_t = t * om
            x, y = np.cos(th_t), np.sin(th_t)
            ax.scatter([x], [y], s=34, c=GOLD, zorder=6, linewidths=0)
            ax.annotate(
                f"{names[k][:26]}  {s[k]:+.2f}",
                (x, y),
                textcoords="offset points",
                xytext=(7, 5),
                color=GOLD,
                fontsize=8.2,
            )
        for p, lab in ((np.array([1.0, 0.0]), "A"), (np.array([np.cos(om), np.sin(om)]), "B")):
            ax.scatter(*p, s=46, c=RED, zorder=6, linewidths=0)
            ax.annotate(lab, p, textcoords="offset points", xytext=(6, -12), color=RED, fontsize=11)
        ax.scatter([0], [0], s=42, marker="+", c=CYAN, linewidths=1.4, zorder=5)
        ax.set_aspect("equal")
        style_axes(ax)
        panel_title(ax, title, width=44)
        ax.set_xlabel(f"angle A to B: {np.degrees(om):.0f} deg")

    fig, top = figure(
        16.5,
        8.2,
        5,
        "interpolation, decoded by retrieval",
        "The walk between two notes lives in their plane — and the corpus is the codebook",
        "arc: slerp (constant length 1)  ·  dashed: the straight line, which sinks below the "
        "sphere  ·  gold stops: nearest note in the full 1024 dimensions, not in the picture",
    )
    gs = fig.add_gridspec(
        1,
        3,
        width_ratios=[1.15, 1.15, 0.9],
        left=0.045,
        right=1 - MARGIN - 0.015,
        top=top,
        bottom=0.185,
        wspace=0.2,
    )

    sims0 = X @ X[0]
    nn = int(np.argsort(-sims0)[1])
    ax1 = fig.add_subplot(gs[0])
    pair_panel(ax1, 0, nn, "related pair: interview video to its nearest neighbor")
    ax2 = fig.add_subplot(gs[1])
    pair_panel(ax2, 0, 250, "unrelated pair: interview video to instagram heatmap")

    ax = fig.add_subplot(gs[2])
    ts = np.linspace(0, 1, 41)
    for (i, j), color, lab in [((0, nn), GOLD, "related"), ((0, 250), BLUE, "unrelated")]:
        sup = []
        for t in ts:
            s = X @ slerp(X[i], X[j], float(t))
            s[[i, j]] = -1
            sup.append(float(s.max()))
        ax.plot(ts, sup, color=color, linewidth=1.9, label=lab)
    ax.axhline(0.26, color=RED, linewidth=1.1, linestyle="--")
    ax.text(0.02, 0.27, "corpus background +0.26", color=RED, fontsize=TICK_SIZE)
    style_axes(ax)
    ax.set_xlabel("position along the walk")
    ax.set_ylabel("similarity of the nearest real note")
    ax.set_ylim(0.2, 0.8)
    leg = ax.legend(frameon=False, fontsize=TICK_SIZE, loc="upper center")
    for t in leg.get_texts():
        t.set_color(MUTED)
    panel_title(ax, "is anyone living along the path?", width=40)

    _footer(
        fig,
        0.045,
        "Every stop on either walk has a real note within 0.50 — the corpus is dense enough that "
        "interpolation decodes to something everywhere on these paths. The unrelated walk's midpoint "
        "retrieves a genuine blend: one coding note and one instagram note, nearly tied. Decoding is "
        "done by lookup in the full space; the plane only draws the walk, it never measures it.",
    )
    save(fig, "05-interpolation.png")


if __name__ == "__main__":
    res = analyze() if "--plot-only" not in sys.argv else json.loads(RESULTS.read_text())
    plt.style.use("dark_background")
    fig01(res)
    fig02(res)
    fig03(res)
    fig04(res)
    fig05(res)
