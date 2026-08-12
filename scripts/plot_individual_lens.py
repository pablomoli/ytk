#!/usr/bin/env python
"""34 — the individual lens: three record findings re-shot Welch Labs style.

Remixes after studying "The Dark Matter of AI" (docs/research/
2026-08-12-welch-labs-visual-grammar.md): render the vector itself as an
image, follow one real note end-to-end, keep a readout on screen — each
paired with the house null so the individual and the population share a panel.

01  the cone as an object   (remix of 16/17: mean direction shown, not scored)
02  one note, whole system  (remix of 12/18: the dark-matter note traced)
03  the road, watched       (remix of 20: retrieval readout at every stop)

    uv run --with matplotlib python scripts/plot_individual_lens.py [1|2|3]

Inputs are frozen artifacts: 17-corpus-growth/{vectors-fresh.npz,tags-fresh
.json}, 18-sae-fingerprints/{manifest.json,fingerprints.npz,cone-features
.json}, and this section's darkmatter-fingerprint.npz (rendered by
scripts/fingerprint_one_note.py on the 18.2 rig, same MAX_CHARS=2000 cut).
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
    BG,
    BLUE,
    DIM,
    DPI,
    FRAME,
    GOLD,
    MARGIN,
    MUTED,
    RED,
    TEXT,
    figure,
    frame_panels,
    panel_title,
    punch,
    saturated_magma,
    style_axes,
    verdict,
)

ASSETS = Path(__file__).resolve().parents[1] / "docs" / "assets"
OUTDIR = ASSETS / "34-individual-lens"
SIDE = 32  # 1024 = 32 x 32
NOTE_TITLE = "The Dark Matter of AI [Mechanistic Interpretability]"


def save(fig, name: str) -> None:
    frame_panels(fig)
    out = OUTDIR / name
    fig.savefig(out, dpi=DPI, facecolor=BG)
    print(f"wrote {out.name}  ({out.stat().st_size // 1024}KB)")
    plt.close(fig)


def unit(M: np.ndarray) -> np.ndarray:
    return M / np.linalg.norm(M, axis=-1, keepdims=True)


def short(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 2].rstrip() + ".."


def load():
    X = np.load(ASSETS / "17-corpus-growth" / "vectors-fresh.npz")["X"].astype(np.float32)
    tags = json.loads((ASSETS / "17-corpus-growth" / "tags-fresh.json").read_text())
    man = json.loads((ASSETS / "18-sae-fingerprints" / "manifest.json").read_text())
    names = [n["name"] for n in man["notes"]]
    fp = np.load(ASSETS / "18-sae-fingerprints" / "fingerprints.npz")["sum"].astype(np.float32)
    cone = json.loads((ASSETS / "18-sae-fingerprints" / "cone-features.json").read_text())
    note = np.load(OUTDIR / "darkmatter-fingerprint.npz")
    feat_names = json.loads((OUTDIR / "feature-names.json").read_text())
    return X, tags, names, fp, cone, note, feat_names


# ---------------------------------------------------------------- seriation


def seriate(mean: np.ndarray):
    """Pixel order for every vector image in this section: dims sorted by the
    corpus mean's coordinate magnitude, values sign-aligned to the mean, so
    the shared direction concentrates in the top rows. Stated in every meta
    line — the readout is the finding's instrument, never hidden."""
    order = np.argsort(-np.abs(mean))
    sgn = np.sign(mean)[order]
    sgn[sgn == 0] = 1.0

    def view(v: np.ndarray) -> np.ndarray:
        return (v[order] * sgn).reshape(SIDE, SIDE)

    return order, sgn, view


def row_profile(img: np.ndarray) -> np.ndarray:
    return img.mean(axis=1)


def null_profiles(v: np.ndarray, mean: np.ndarray, n: int = 300, seed: int = 34) -> np.ndarray:
    """Row profiles under random pixel order (the same sign-alignment rule,
    applied to a shuffled order) — the top band if seriation carried nothing."""
    rng = np.random.default_rng(seed)
    out = np.empty((n, SIDE), dtype=np.float32)
    sgn_full = np.sign(mean)
    sgn_full[sgn_full == 0] = 1.0
    for k in range(n):
        p = rng.permutation(v.size)
        out[k] = (v[p] * sgn_full[p]).reshape(SIDE, SIDE).mean(axis=1)
    return out


def sq_axes(fig, x, y_top, w):
    """Square image axes anchored by its TOP edge — frame matches the image."""
    W, H = fig.get_figwidth(), fig.get_figheight()
    h = w * W / H
    ax = fig.add_axes([x, y_top - h, w, h])
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color(FRAME)
    return ax, h


def imshow_vec(ax, img, lim, cmap):
    ax.imshow(img, cmap=cmap, vmin=-lim, vmax=lim, interpolation="nearest")


# ---------------------------------------------------------------- figure 01


def fig01(X, note, cmap):
    mean = X.mean(0)
    order, sgn, view = seriate(mean)
    q = unit(note["qwen"].astype(np.float32))
    qc = q - mean

    lim = float(np.percentile(np.abs(X), 99))
    prof_raw = row_profile(view(q))
    prof_cen = row_profile(view(qc))
    nulls = null_profiles(q, mean)
    lo, hi = np.percentile(nulls, [5, 95], axis=0)

    P_raw = np.stack([row_profile(view(x)) for x in X])
    P_cen = np.stack([row_profile(view(x - mean)) for x in X])

    meta = (
        "n=568 notes, 1024-dim Qwen3, unit norm  ·  |mean|=0.511, median cos(note,mean)=0.513  ·  "
        "pixel order: dims sorted by corpus |mean|, sign-aligned  ·  null: 300 random orders, 5-95%"
    )
    fig, top = figure(16.5, 5.9, 1, "individual lens", "The cone, held up to the light", meta)

    y_top = top - 0.085
    w = 0.125
    xs = [MARGIN + k * 0.147 for k in range(4)]
    a0, h = sq_axes(fig, xs[0], y_top, w)
    imshow_vec(a0, view(mean), lim, cmap)
    panel_title(a0, "the corpus mean, seriated", 26)
    a0.annotate(
        "row 0 = its 32 loudest dims",
        xy=(2.0, 0.5),
        xytext=(4.5, 38.5),
        color=GOLD,
        fontsize=8,
        annotation_clip=False,
        arrowprops={"arrowstyle": "->", "color": GOLD, "lw": 0.9},
    )
    a1, _ = sq_axes(fig, xs[1], y_top, w)
    imshow_vec(a1, q.reshape(SIDE, SIDE), lim, cmap)
    panel_title(a1, "one note, native order", 26)
    a2, _ = sq_axes(fig, xs[2], y_top, w)
    imshow_vec(a2, view(q), lim, cmap)
    panel_title(a2, "same note, seriated", 26)
    a3, _ = sq_axes(fig, xs[3], y_top, w)
    imshow_vec(a3, view(qc), lim, cmap)
    panel_title(a3, "seriated, centered", 26)

    rows = np.arange(SIDE)
    for j, (title, kind) in enumerate(
        [("this note's row profile", "one"), ("all 568 notes (median, IQR)", "all")]
    ):
        ax = fig.add_axes([MARGIN + 0.60 + j * 0.185, y_top - h, 0.155, h])
        style_axes(ax)
        ax.fill_between(rows, lo, hi, color=DIM, alpha=0.9, lw=0, label="random order")
        if kind == "one":
            ax.plot(rows, prof_raw, color=GOLD, lw=1.8, label="raw")
            ax.plot(rows, prof_cen, color=BLUE, lw=1.4, label="centered")
            ax.legend(
                frameon=False, fontsize=7, labelcolor=TEXT, loc="upper right", borderaxespad=0.2
            )
            ax.set_ylabel("row mean value", color=MUTED, fontsize=8)
        else:
            lo_r, med_r, hi_r = (np.percentile(P_raw, p, axis=0) for p in (25, 50, 75))
            ax.fill_between(rows, lo_r, hi_r, color=GOLD, alpha=0.25, lw=0)
            ax.plot(rows, med_r, color=GOLD, lw=1.8)
            ax.plot(rows, np.percentile(P_cen, 50, axis=0), color=BLUE, lw=1.4)
        ax.set_xlim(0, SIDE - 1)
        ax.set_xlabel("image row", color=MUTED, fontsize=8)
        panel_title(ax, title, 34)

    fig.text(
        MARGIN,
        y_top - h - 0.10,
        "the strongest geometric fact about this corpus is invisible in the raw object (panel 2) — "
        "26% of every vector's length is a shared direction no eye can find until the pixels are sorted by it.",
        color=MUTED,
        fontsize=9,
    )
    verdict(fig, "invisible in the raw image; seriated, one note is enough to see the cone")
    save(fig, "01-cone-held-up.png")


# ---------------------------------------------------------------- figure 02


def fig02(X, names, fp, cone, note, feat_names, cmap):
    mean = X.mean(0)
    _, _, view = seriate(mean)
    q = unit(note["qwen"].astype(np.float32))
    s = note["sum"].astype(np.float32)

    sims = X @ q
    top5 = np.argsort(-sims)[:5]
    l0 = int((s > 0).sum())
    l0s = (fp > 0).sum(1)
    cone_idx = np.array([f["index"] for f in cone["top"]])
    cmass = float(s[cone_idx].sum() / s.sum())
    pop_cmass = fp[:, cone_idx].sum(1) / fp.sum(1)

    meta = (
        "stored doc 1639 chars -> 424 tokens  ·  SAE gemma-scope-2b-pt-res L20/16k  ·  "
        f"L0={l0}/16384 (pop median {int(np.median(l0s))})  ·  cone mass {cmass:.3f} (pop median {np.median(pop_cmass):.3f})"
    )
    fig, top = figure(16.5, 8.0, 2, "individual lens", "One note through the whole system", meta)

    vals = ", ".join(f"{v:+.3f}" for v in q[:4])
    fig.text(MARGIN, top - 0.045, f'"{NOTE_TITLE}"', color=TEXT, fontsize=10.5)
    fig.text(
        MARGIN,
        top - 0.078,
        f"qwen3 embedding  [ {vals}, ... ] x 1024   ->   reshape 32 x 32, seriated",
        color=MUTED,
        fontsize=8.5,
    )

    y_top = top - 0.115
    lim = float(np.percentile(np.abs(X), 99))
    a1, h1 = sq_axes(fig, MARGIN, y_top, 0.135)
    imshow_vec(a1, view(q), lim, cmap)
    panel_title(a1, "the vector, as an image", 26)

    axn = fig.add_axes([MARGIN + 0.175, y_top - h1, 0.285, h1])
    axn.set_xlim(0, 1)
    axn.set_ylim(0, 1)
    axn.axis("off")
    panel_title(axn, "retrieval readout: nearest of the 568 frozen notes", 52)
    for k, i in enumerate(top5):
        yy = 0.91 - k * 0.20
        side = 0.16 * float(sims[i])
        axn.add_patch(plt.Rectangle((0.01, yy - side / 2), side * 0.62, side, color=GOLD, lw=0))
        axn.text(
            0.13, yy, f"{sims[i]:.3f}", color=GOLD, fontsize=9, va="center", family="monospace"
        )
        axn.text(0.235, yy, short(names[i], 44), color=TEXT, fontsize=9, va="center")

    aw = 0.205
    a2, h2 = sq_axes(fig, MARGIN + 0.50, y_top, aw)
    img = punch(np.sqrt(s.reshape(128, 128)) / np.sqrt(s.max()))
    im = a2.imshow(img, cmap=cmap, vmin=0, vmax=1, interpolation="nearest")
    panel_title(a2, "SAE fingerprint: 16,384 features as 128 x 128  ·  dark = silent", 52)
    for idx, tx, ty in ((9622, 0.02, -0.075), (6631, 0.52, -0.135)):
        r, c = divmod(idx, 128)
        label = short(feat_names[str(idx)], 40)
        a2.annotate(
            f"{idx}: {label}",
            xy=(c, r),
            xycoords="data",
            xytext=(tx, ty),
            textcoords="axes fraction",
            color=GOLD,
            fontsize=7.5,
            annotation_clip=False,
            arrowprops={"arrowstyle": "->", "color": GOLD, "lw": 0.8},
        )
    cax = fig.add_axes([MARGIN + 0.50 + aw + 0.006, y_top - h2, 0.007, h2])
    cax._is_colorbar = True
    cb = fig.colorbar(im, cax=cax)
    cb.outline.set_edgecolor(FRAME)
    cax.tick_params(colors=MUTED, labelsize=6)

    axt = fig.add_axes([MARGIN + 0.775, y_top - h2, 0.16, h2])
    axt.axis("off")
    axt.text(
        0,
        0.97,
        "the note about SAE\nfeatures, read by an SAE:\n\nits loudest feature is\n9622 'CNN capabilities';\nits runner-up is the cone\n(6631 'proper nouns',\non 100% of notes).\n\nnearest neighbors are\nits own reference list —\nthe papers the video\ncites were ingested\nweeks earlier.",
        color=MUTED,
        fontsize=8.5,
        va="top",
        linespacing=1.55,
    )

    y2 = 0.135
    for j, (data, mark, label, title) in enumerate(
        [
            (l0s, l0, "active features (L0)", "this note (red) among the 568"),
            (pop_cmass, cmass, "cone share of summed activation", ""),
        ]
    ):
        ax = fig.add_axes([MARGIN + j * 0.175, y2, 0.145, 0.16])
        style_axes(ax)
        ax.hist(data, bins=24, color=DIM, lw=0)
        ax.axvline(mark, color=RED, lw=1.6)
        ax.set_yticks([])
        ax.set_xlabel(label, color=MUTED, fontsize=7.5)
        if title:
            panel_title(ax, title, 40)

    verdict(fig, "a typical citizen: median L0, median cone mass, one loud on-topic feature")
    save(fig, "02-one-note-through.png")


# ---------------------------------------------------------------- figure 03


def fig03(X, tags, names, cmap):
    mean = X.mean(0)
    _, _, view = seriate(mean)
    Xu = unit(X)
    labels = tags["labels"]

    def centroid(tag: str):
        idx = [i for i, ls in enumerate(labels) if tag in ls]
        return unit(Xu[idx].mean(axis=0)), len(idx)

    ca, na = centroid("ai-agents")
    cb, nb = centroid("machine-learning")
    omega = float(np.arccos(np.clip(ca @ cb, -1, 1)))

    ts = np.linspace(0, 1, 7)
    stops = unit(
        np.stack(
            [(np.sin((1 - t) * omega) * ca + np.sin(t * omega) * cb) / np.sin(omega) for t in ts]
        )
    )
    sims = stops @ Xu.T
    top3 = np.argsort(-sims, axis=1)[:, :3]
    handover = [k for k in range(1, len(ts)) if top3[k, 0] != top3[k - 1, 0]]

    meta = (
        f"road: ai-agents (n={na}) -> machine-learning (n={nb}), slerp, 7 stops  ·  centroid cos={ca @ cb:.3f}  ·  "
        "strip: each stop minus the start, seriated (change is what is drawn)  ·  retrieval: cosine, 568 frozen notes"
    )
    fig, top = figure(16.5, 8.4, 3, "individual lens", "The road, watched instead of scored", meta)

    w = 0.117
    gap = (1 - 2 * MARGIN - 7 * w) / 6
    y_top = top - 0.075
    deltas = stops - stops[0]
    limd = float(np.percentile(np.abs(deltas[1:]), 99.5))
    lim0 = float(np.percentile(np.abs(X), 99))
    for k, t in enumerate(ts):
        x = MARGIN + k * (w + gap)
        ax, h = sq_axes(fig, x, y_top, w)
        if k == 0:
            imshow_vec(ax, view(stops[0] - mean), lim0, cmap)
            ax.set_title("t=0.00 (the start, centered)", color=TEXT, fontsize=8.5, pad=6)
        else:
            imshow_vec(ax, view(deltas[k]), limd, cmap)
            ax.set_title(
                f"t={t:.2f}  (change since t=0)",
                color=GOLD if k in handover else TEXT,
                fontsize=8.5,
                pad=6,
            )

    y_list = y_top - h - 0.045
    for k in range(7):
        x = MARGIN + k * (w + gap)
        for r in range(3):
            i = top3[k, r]
            first = r == 0
            col = (GOLD if k in handover else TEXT) if first else MUTED
            fig.text(x, y_list - r * 0.055, short(names[i], 26), color=col, fontsize=7)
            fig.text(
                x,
                y_list - r * 0.055 - 0.021,
                f"{sims[k, top3[k, r]]:.3f}",
                color=MUTED,
                fontsize=6.3,
                family="monospace",
            )

    axc = fig.add_axes([MARGIN, 0.072, 1 - 2 * MARGIN, 0.155])
    style_axes(axc)
    axc.plot(ts, stops @ ca, color=GOLD, lw=1.8, label="cos to ai-agents")
    axc.plot(ts, stops @ cb, color=BLUE, lw=1.8, label="cos to machine-learning")
    axc.plot(ts, sims.max(axis=1), color=MUTED, lw=1.2, ls=":", label="cos to nearest note")
    for k in handover:
        axc.axvline(ts[k], color=RED, lw=1.2, ls="--")
    axc.set_xlim(0, 1)
    axc.set_ylim(0.70, 1.005)
    axc.set_xlabel("t along the road", color=MUTED, fontsize=8)
    axc.legend(frameon=False, fontsize=7.5, labelcolor=TEXT, ncol=3, loc="lower left")
    panel_title(
        axc, "the readout under the film strip  ·  red dashes: the top note changes hands", 110
    )

    verdict(fig, f"top-1 changes hands {len(handover)}x; the walk is a handover, not a fade")
    save(fig, "03-road-watched.png")


# ---------------------------------------------------------------- figure 04


def fig04(X, note, cmap):
    """The same field as terrain: a 32x32 vector image is a scalar field, so
    height can carry the value instead of brightness. The field is bilinearly
    interpolated between grid points for rendering (values at the 32x32 nodes
    are exact; the surface lerps between them), lit with a soft hillshade.
    The gold ridge on the back wall is the row profile (fig 01's readout, now
    a silhouette); the DIM rails are the random-order null."""
    from matplotlib.colors import LightSource
    from matplotlib.lines import Line2D
    from scipy.ndimage import zoom

    mean = X.mean(0)
    _, _, view = seriate(mean)
    q = unit(note["qwen"].astype(np.float32))
    qc = q - mean
    nulls = null_profiles(q, mean)
    lo, hi = np.percentile(nulls, [5, 95], axis=0)

    meta = (
        "same seriation as figure 01 (dims sorted by corpus |mean|, sign-aligned)  ·  height = value, shared z-limits ±0.10  ·  "
        "surface: bilinear lerp between the 32x32 grid values, 8x  ·  null: 5-95% of 300 random orders"
    )
    fig, top = figure(16.5, 7.0, 4, "individual lens", "The cone as terrain", meta)

    UP = 8
    zlim = 0.10
    norm = plt.Normalize(-zlim, zlim)
    ls = LightSource(azdeg=315, altdeg=45)
    r = np.arange(SIDE)
    rf = np.linspace(0, SIDE - 1, SIDE * UP)
    xxf, yyf = np.meshgrid(rf, rf)
    panels = [
        ("the corpus mean — the landform", view(mean)),
        ("one note — weather on the landform", view(q)),
        ("the note centered — the weather alone", view(qc)),
    ]
    for k, (title, Z) in enumerate(panels):
        Zf = zoom(Z, UP, order=1)  # lerp between grid points; node values exact
        rgb = ls.shade(Zf, cmap=cmap, norm=norm, vert_exag=40, blend_mode="soft")
        ax = fig.add_axes([MARGIN + k * 0.315, 0.065, 0.295, top - 0.15], projection="3d")
        ax.set_facecolor(BG)
        ax.plot_surface(
            xxf,
            yyf,
            Zf,
            facecolors=rgb,
            rcount=SIDE * UP // 2,
            ccount=SIDE * UP // 2,
            linewidth=0,
            antialiased=True,
            shade=False,
        )
        # row profile + null rails on the back wall (x = 0 plane)
        wall = np.zeros(SIDE)
        ax.plot(wall, r, Z.mean(axis=1), color=GOLD, lw=2.4, zorder=10)
        ax.plot(wall, r, lo, color=DIM, lw=1.3, zorder=9)
        ax.plot(wall, r, hi, color=DIM, lw=1.3, zorder=9)

        ax.set_zlim(-zlim, zlim)
        ax.set_xlim(0, SIDE - 1)
        ax.set_ylim(SIDE - 1, 0)  # row 0 toward the camera — the ridge faces the viewer
        ax.view_init(elev=28, azim=-55)
        ax.set_box_aspect((1, 1, 0.42), zoom=1.22)
        for pane in (ax.xaxis, ax.yaxis, ax.zaxis):
            pane.set_pane_color((0, 0, 0, 0))
            pane.line.set_color(FRAME)
        ax.grid(False)
        ax.tick_params(colors=MUTED, labelsize=6, pad=-1)
        ax.set_xticks([0, 16, 31])
        ax.set_yticks([0, 16, 31])
        ax.set_zticks([-0.1, 0, 0.1])
        ax.set_xlabel("image col", color=MUTED, fontsize=7, labelpad=-4)
        ax.set_ylabel("image row", color=MUTED, fontsize=7, labelpad=-4)
        if k == 0:
            ax.set_zlabel("value", color=MUTED, fontsize=7, labelpad=-2)
        else:
            ax.set_zticklabels([])
        fig.text(
            MARGIN + k * 0.315 + 0.1475, top - 0.045, title, color=TEXT, fontsize=10, ha="center"
        )

    fig.legend(
        handles=[
            Line2D([], [], color=GOLD, lw=2.4, label="row profile (back wall)"),
            Line2D([], [], color=DIM, lw=1.3, label="random-order null, 5-95%"),
        ],
        loc="lower center",
        bbox_to_anchor=(0.5, 0.012),
        ncol=2,
        frameon=False,
        labelcolor=TEXT,
        fontsize=8,
    )

    verdict(
        fig,
        "the mean is a ramp; the note carries the ramp under its noise; centering removes the ramp, not the weather",
    )
    save(fig, "04-cone-terrain.png")


def main() -> None:
    which = set(sys.argv[1:]) or {"1", "2", "3", "4"}
    X, tags, names, fp, cone, note, feat_names = load()
    cmap = saturated_magma()
    if "1" in which:
        fig01(X, note, cmap)
    if "2" in which:
        fig02(X, names, fp, cone, note, feat_names, cmap)
    if "3" in which:
        fig03(X, tags, names, cmap)
    if "4" in which:
        fig04(X, note, cmap)


if __name__ == "__main__":
    main()
