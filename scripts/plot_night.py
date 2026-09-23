"""Figures for the patch-grid night (#218, sections 54-58).

uv run --with matplotlib python scripts/plot_night.py ten      # the reference sheet
uv run --with matplotlib python scripts/plot_night.py 54       # section 54's figures
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "experiments" / "patch_grid"))
import night as N
from plot_assets import (
    BG,
    BLUE,
    CYAN,
    DIM,
    DPI,
    GOLD,
    MUTED,
    PURPLE,
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

SERIES = [GOLD, BLUE, CYAN, PURPLE, RED]


def sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=N.ROOT
    ).stdout.strip()


def image(name: str) -> Image.Image:
    return Image.open(N.image_path(name)).convert("RGB")


def show(ax, img: Image.Image, dim: float = 1.0) -> None:
    a = np.asarray(img, dtype=float) / 255.0
    ax.imshow(a * dim, extent=(0, 1, 1, 0), aspect="auto", interpolation="lanczos")
    ax.set_xticks([])
    ax.set_yticks([])


def outline(ax, mask: np.ndarray, color: str, lw: float = 1.6) -> None:
    """The real pixel outline of a region, in image-fraction coordinates."""
    h, w = mask.shape
    ys = (np.arange(h) + 0.5) / h
    xs = (np.arange(w) + 0.5) / w
    ax.contour(xs, ys, mask.astype(float), levels=[0.5], colors=[color], linewidths=lw)


def region_fill(ax, masks: np.ndarray, values: np.ndarray, vmax: float, alpha: float = 0.7) -> None:
    """Paint every region with its value on the shared magma ramp; a pixel in
    several regions takes the largest value, so nested parts stay visible."""
    h, w = masks.shape[1:]
    best = np.zeros((h, w))
    for m, v in zip(masks, values):
        best = np.where(m & (v > best), v, best)
    rgba = saturated_magma()(punch(np.clip(best / max(vmax, 1e-9), 0, 1)))
    rgba[..., 3] = alpha * (best > 0)
    ax.imshow(rgba, extent=(0, 1, 1, 0), aspect="auto", interpolation="nearest")


def grid_map(ax, m: np.ndarray, vmax: float | None = None, alpha: float = 0.66) -> None:
    """A 24 x 24 (or any) per-patch map at its own resolution, on the ramp."""
    m = np.clip(m, 0, None)
    m = m / vmax if vmax else (m - m.min()) / (np.ptp(m) + 1e-12)
    ax.imshow(
        saturated_magma()(punch(np.clip(m, 0, 1))),
        extent=(0, 1, 1, 0),
        aspect="auto",
        alpha=alpha,
        interpolation="nearest",
    )


def mask_colors(n: int) -> np.ndarray:
    return plt.get_cmap("hsv")(np.linspace(0, 1, n, endpoint=False))


def fig_ten(out: Path) -> None:
    """The reference sheet: the ten images, their SAM regions, their queries."""
    qs = N.queries()
    names = list(N.IMAGES)
    data = {n: N.load(n) for n in names}
    counts = [len(data[n]["masks"]) for n in names]
    lost = [int((data[n]["grids"].sum(axis=(1, 2)) == 0).sum()) for n in names]
    fig, top = figure(
        22,
        13.2,
        0,
        "THE NIGHT'S TEN IMAGES",
        "Ten pictures with something to point at, cut into regions by SAM, three questions each",
        f"sam-vit-base, pred_iou 0.80, stability 0.85, area 0.15% to 85% of the frame  |  regions per image {', '.join(map(str, counts))}  |  "
        f"regions too small to own one 16 px patch at half coverage {', '.join(map(str, lost))}  |  under each: small object, frame-filling object, absent object in red  |  {sha()}",
    )
    gs = fig.add_gridspec(
        2, 5, left=0.03, right=0.97, top=top - 0.02, bottom=0.11, wspace=0.06, hspace=0.42
    )
    for k, n in enumerate(names):
        ax = fig.add_subplot(gs[k // 5, k % 5])
        img = image(n)
        show(ax, img, dim=0.75)
        masks = data[n]["masks"]
        cols = mask_colors(len(masks))
        rng = np.random.default_rng(k)
        cols = cols[rng.permutation(len(masks))]
        h, w = masks.shape[1:]
        fill = np.zeros((h, w, 4))
        for m, c in zip(masks, cols):  # large first, so small regions paint on top
            fill[m] = (*c[:3], 0.42)
        ax.imshow(fill, extent=(0, 1, 1, 0), aspect="auto", interpolation="nearest")
        for m, c in zip(masks, cols):
            outline(ax, m, c, lw=0.7)
        panel_title(ax, f"{n}  ({len(masks)} regions)")
        small, big, absent = qs[n]
        ax.text(0.0, -0.035, small, color=TEXT, fontsize=9.5, transform=ax.transAxes, va="top")
        ax.text(0.0, -0.105, big, color=TEXT, fontsize=9.5, transform=ax.transAxes, va="top")
        ax.text(
            0.0,
            -0.175,
            f"{absent}  (absent)",
            color=RED,
            fontsize=9.5,
            transform=ax.transAxes,
            va="top",
        )
    frame_panels(fig)
    fig.savefig(out, dpi=DPI, facecolor=BG)
    plt.close(fig)
    print("wrote", out)


def softmax(x: np.ndarray, axis: int = 0) -> np.ndarray:
    e = np.exp(x - x.max(axis=axis, keepdims=True))
    return e / e.sum(axis=axis, keepdims=True)


def vote_share(cos: np.ndarray, scale: float) -> np.ndarray:
    """Regions compete by softmax(cosine x logit_scale); each region's share
    of the vote relative to the winner, so the winner is 1."""
    v = softmax(cos * scale, axis=0)
    return v / v.max(axis=0, keepdims=True), v.max(axis=0)


def absent_ceiling(all54: dict) -> float:
    """The largest whole-image cosine any absent query reached: below it a
    query is not answered by the picture and no map is drawn for it."""
    return max(float(all54[f"{n}/base"][2]) for n in N.IMAGES)


def occlusion_winner(heat: np.ndarray, grids: np.ndarray) -> int:
    """The region whose patches the sliding cover hurt most, on average."""
    return int(np.argmax([heat[g].mean() if g.any() else -np.inf for g in grids]))


def no_map(ax, text: str) -> None:
    import textwrap

    ax.text(
        0.5,
        0.5,
        textwrap.fill(text, 30),
        color=TEXT,
        fontsize=9.5,
        ha="center",
        va="center",
        transform=ax.transAxes,
    )


def fig54_woman(out: Path, all54: dict) -> None:
    w = dict(np.load(N.CACHE / "54_woman.npz", allow_pickle=True))
    scale = float(w["scale"])
    ceiling = absent_ceiling(all54)
    img = image("woman-river")
    masks, grids = w["masks"], w["grids"]
    qs = [str(q) for q in w["qs"]]
    slide_qs = [str(q) for q in w["slide_qs"]]
    rows = [qs.index(q) for q in slide_qs]  # the four the sliding cover was run for
    share_head, top_head = vote_share(w["cos_head"], scale)
    share_crop, top_crop = vote_share(w["cos_crop"], scale)
    fig, top = figure(
        17,
        4.05 * len(rows) + 1.9,
        1,
        "SECTION 54  ONE IMAGE, THREE WAYS TO LOCATE A MATCH",
        "Crop-on-grey, the region-masked head, and a sliding grey cover, on the same 46 SAM regions",
        f"46 regions  |  brightness: a region's share of the softmax(cosine x {scale:.0f}) vote relative to the winner; gold outline: the winner  |  "
        f"occlusion: mean drop in image-text cosine over every 64 px cover touching a patch, 441 positions, own scale per row; gold: region the cover hurt most  |  "
        f"a whole-image cosine at or under {ceiling:.3f}, the highest any absent query reached, gets no map  |  {w['fixed']} regions too small for a patch given their best one  |  {sha()}",
    )
    heads = [
        "the picture",
        "crop-on-grey (46 encoder passes)",
        "region-masked head (one pass)",
        "sliding occlusion (441 passes)",
    ]
    gs = fig.add_gridspec(
        len(rows), 4, left=0.03, right=0.97, top=top - 0.02, bottom=0.02, wspace=0.04, hspace=0.16
    )
    disagreements = 0
    for r, j in enumerate(rows):
        base = float(w["base"][j])
        answered = base > ceiling
        heat = w["slide_heat"][..., slide_qs.index(qs[j])]
        winners = {
            "crop": int(w["cos_crop"][:, j].argmax()),
            "head": int(w["cos_head"][:, j].argmax()),
            "occ": occlusion_winner(heat, grids),
        }
        for c in range(4):
            ax = fig.add_subplot(gs[r, c])
            if c == 0:
                show(ax, img)
                ax.text(
                    0.02,
                    0.97,
                    f"“{qs[j]}”",
                    color=TEXT,
                    fontsize=11,
                    va="top",
                    transform=ax.transAxes,
                    bbox={"facecolor": BG, "alpha": 0.7, "edgecolor": "none", "pad": 3},
                )
                ax.text(
                    0.02,
                    0.05,
                    f"whole image cosine {base:.3f}" + ("" if answered else "  (absent range)"),
                    color=GOLD if answered else RED,
                    fontsize=9.5,
                    va="bottom",
                    transform=ax.transAxes,
                    bbox={"facecolor": BG, "alpha": 0.7, "edgecolor": "none", "pad": 3},
                )
            elif not answered:
                show(ax, img, dim=0.25)
                no_map(
                    ax,
                    f"whole-image match {base:.3f} is inside the absent-query range (up to {ceiling:.3f}): nothing to locate",
                )
            elif c in (1, 2):
                sh, tp, key = (
                    (share_crop, top_crop, "crop") if c == 1 else (share_head, top_head, "head")
                )
                show(ax, img, dim=0.5)
                region_fill(ax, masks, sh[:, j], 1.0)
                outline(ax, masks[winners[key]], GOLD, lw=2.0)
                ax.text(
                    0.02,
                    0.05,
                    f"winner takes {tp[j]:.0%} of the vote, {masks[winners[key]].mean():.1%} of the frame",
                    color=TEXT,
                    fontsize=9.5,
                    va="bottom",
                    transform=ax.transAxes,
                    bbox={"facecolor": BG, "alpha": 0.7, "edgecolor": "none", "pad": 3},
                )
            else:
                show(ax, img, dim=0.5)
                grid_map(ax, heat, vmax=float(heat.max()))
                outline(ax, masks[winners["occ"]], GOLD, lw=2.0)
                ax.text(
                    0.02,
                    0.05,
                    f"largest drop {heat.max():.3f} of {base:.3f}",
                    color=TEXT,
                    fontsize=9.5,
                    va="bottom",
                    transform=ax.transAxes,
                    bbox={"facecolor": BG, "alpha": 0.7, "edgecolor": "none", "pad": 3},
                )
            if r == 0:
                panel_title(ax, heads[c])
        if answered and winners["crop"] != winners["head"]:
            disagreements += 1
    n_ans = sum(float(w["base"][j]) > ceiling for j in rows)
    verdict(
        fig,
        f"{n_ans} of {len(rows)} queries answered by the picture; crop and head pick different winners on {disagreements}",
    )
    frame_panels(fig)
    fig.savefig(out, dpi=DPI, facecolor=BG)
    plt.close(fig)
    print("wrote", out)


def label(ax, text: str, y: float, color: str = TEXT, size: float = 9.5) -> None:
    ax.text(
        0.02,
        y,
        text,
        color=color,
        fontsize=size,
        va="top" if y > 0.5 else "bottom",
        transform=ax.transAxes,
        bbox={"facecolor": BG, "alpha": 0.7, "edgecolor": "none", "pad": 3},
    )


def fig54_all(out: Path, all54: dict) -> None:
    """All ten images, all thirty queries: crop-on-grey beside the masked head."""
    scale = float(all54["scale"])
    ceiling = absent_ceiling(all54)
    qs = N.queries()
    names = list(N.IMAGES)
    agree = answered = 0
    fig, top = figure(
        24,
        3.3 * len(names) + 2.0,
        2,
        "SECTION 54  ALL TEN, ALL THIRTY QUESTIONS",
        "For each question, crop-on-grey (left) beside the region-masked head (right); the absent question last",
        f"brightness: share of the softmax(cosine x {scale:.0f}) vote relative to the winner; gold outline: the winner  |  "
        f"whole-image cosine at or under {ceiling:.3f} (the highest an absent query reached) gets no map  |  crop-on-grey costs one encoder pass per region, the head one pass per image  |  {sha()}",
    )
    gs = fig.add_gridspec(
        len(names), 7, left=0.02, right=0.98, top=top - 0.02, bottom=0.015, wspace=0.03, hspace=0.12
    )
    for r, n in enumerate(names):
        d = N.load(n)
        img = image(n)
        masks = d["masks"]
        sh_c, tp_c = vote_share(all54[f"{n}/cos_crop"], scale)
        sh_h, tp_h = vote_share(all54[f"{n}/cos_head"], scale)
        ax = fig.add_subplot(gs[r, 0])
        show(ax, img)
        label(ax, n, 0.97, size=10.5)
        if r == 0:
            panel_title(ax, "the picture")
        for j in range(3):
            base = float(all54[f"{n}/base"][j])
            ok = base > ceiling
            wc, wh = (
                int(all54[f"{n}/cos_crop"][:, j].argmax()),
                int(all54[f"{n}/cos_head"][:, j].argmax()),
            )
            if ok:
                answered += 1
                agree += int(wc == wh)
            for k, (sh, tp, win) in enumerate(((sh_c, tp_c, wc), (sh_h, tp_h, wh))):
                ax = fig.add_subplot(gs[r, 1 + 2 * j + k])
                if ok:
                    show(ax, img, dim=0.5)
                    region_fill(ax, masks, sh[:, j], 1.0)
                    outline(ax, masks[win], GOLD, lw=1.8)
                    label(
                        ax, f"{tp[j]:.0%} of the vote, {masks[win].mean():.1%} of the frame", 0.04
                    )
                else:
                    show(ax, img, dim=0.25)
                    no_map(ax, f"whole-image match {base:.3f}\nin the absent range")
                if k == 0:
                    label(
                        ax,
                        f"“{qs[n][j]}”  {base:.3f}",
                        0.97,
                        color=RED if j == 2 else TEXT,
                        size=10,
                    )
                if r == 0:
                    panel_title(
                        ax,
                        ["crop-on-grey", "masked head"][k]
                        + ["  (small object)", "  (fills the frame)", "  (absent)"][j],
                    )
    verdict(
        fig,
        f"{answered} of 30 questions answered by their picture; crop and head agree on the winner in {agree} of them",
    )
    frame_panels(fig)
    fig.savefig(out, dpi=DPI, facecolor=BG)
    plt.close(fig)
    print("wrote", out)


def fig54_disagree(out: Path, all54: dict) -> None:
    """Only the pairs where the two methods pick different winners, with the
    covering tiebreaker: each candidate painted with the drop its cover cost."""
    t = dict(np.load(N.CACHE / "54_tiebreak.npz", allow_pickle=True))
    qs = N.queries()
    n = len(t["name"])
    sides_head = int((t["drop_head"] > t["drop_crop"]).sum())
    vmax = float(max(t["drop_head"].max(), t["drop_crop"].max(), 1e-6))
    cols = 4
    rows = int(np.ceil(n / cols))
    fig, top = figure(
        20,
        5.4 * rows + 2.0,
        3,
        "SECTION 54  WHERE THEY DISAGREE",
        "Crop-on-grey's winner in blue, the masked head's in gold; each painted with what covering it cost the match",
        f"{n} of the answered questions have different winners  |  paint: drop in whole-image cosine when that region is greyed and the image re-encoded, one scale 0 to {vmax:.3f}  |  "
        f"occlusion sides with the head on {sides_head}, with crop-on-grey on {n - sides_head}  |  {sha()}",
    )
    gs = fig.add_gridspec(
        rows, cols, left=0.02, right=0.98, top=top - 0.02, bottom=0.02, wspace=0.04, hspace=0.2
    )
    for i in range(n):
        name, j = str(t["name"][i]), int(t["q"][i])
        d = N.load(name)
        img = image(name)
        wc, wh = int(t["crop"][i]), int(t["head"][i])
        dc, dh = float(t["drop_crop"][i]), float(t["drop_head"][i])
        ax = fig.add_subplot(gs[i // cols, i % cols])
        show(ax, img, dim=0.5)
        region_fill(ax, d["masks"][[wc, wh]], np.array([dc, dh]), vmax, alpha=0.8)
        outline(ax, d["masks"][wc], BLUE, lw=2.2)
        outline(ax, d["masks"][wh], GOLD, lw=2.2)
        label(ax, f"“{qs[name][j]}”", 0.97, size=10.5)
        label(
            ax,
            f"cover crop's {dc:+.3f}   cover head's {dh:+.3f}   of {float(t['base'][i]):.3f}",
            0.04,
            color=GOLD if dh > dc else BLUE,
        )
        panel_title(ax, f"{name}: occlusion sides with the {'head' if dh > dc else 'crop'}")
    verdict(fig, f"occlusion sides with the masked head {sides_head} to {n - sides_head}")
    frame_panels(fig)
    fig.savefig(out, dpi=DPI, facecolor=BG)
    plt.close(fig)
    print("wrote", out)


def fig54_attention(out: Path) -> None:
    """The mechanism: the probe's attention confined to each region of the woman image."""
    a = dict(np.load(N.CACHE / "54_attention.npz"))
    w = dict(np.load(N.CACHE / "54_woman.npz", allow_pickle=True))
    img = image("woman-river")
    masks, grids = w["masks"], w["grids"]
    att, full = a["att"], a["full"]
    n = len(att)
    tops = att.reshape(n, -1).max(1)
    cols = 8
    rows = int(np.ceil((n + 1) / cols))
    fig, top = figure(
        22,
        2.9 * rows + 2.0,
        4,
        "SECTION 54  WHAT THE PROBE LOOKS AT INSIDE EACH REGION",
        "The pooling probe's attention over the 24 x 24 patches, unconfined (first) and confined to each of the 46 regions",
        f"each tile on its own scale, brightest patch = 1  |  share of a region's attention on its single top patch: median {np.median(tops):.2f}, range {tops.min():.2f} to {tops.max():.2f}  |  "
        f"unconfined, the top patch takes {full.max():.3f} and the top ten {np.sort(full.ravel())[-10:].sum():.0%}  |  {sha()}",
    )
    gs = fig.add_gridspec(
        rows, cols, left=0.02, right=0.98, top=top - 0.02, bottom=0.015, wspace=0.03, hspace=0.1
    )
    ax = fig.add_subplot(gs[0, 0])
    show(ax, img, dim=0.45)
    grid_map(ax, full, vmax=float(full.max()), alpha=0.8)
    label(ax, "unconfined: the long tokens", 0.97, color=GOLD, size=10)
    for i in range(n):
        ax = fig.add_subplot(gs[(i + 1) // cols, (i + 1) % cols])
        show(ax, img, dim=0.45)
        grid_map(ax, att[i], vmax=float(att[i].max()), alpha=0.8)
        outline(ax, masks[i], GOLD, lw=1.2)
        label(ax, f"region {i}: {int(grids[i].sum())} patches, top {tops[i]:.0%}", 0.97, size=9)
    frame_panels(fig)
    fig.savefig(out, dpi=DPI, facecolor=BG)
    plt.close(fig)
    print("wrote", out)


def ring_patches(ax, idx: np.ndarray, color: str = GOLD, lw: float = 1.8) -> None:
    """Ring 24 x 24 patch cells on an image drawn in fraction coordinates."""
    from matplotlib.patches import Rectangle

    for i in np.atleast_1d(idx):
        r, c = divmod(int(i), N.SIDE)
        ax.add_patch(
            Rectangle(
                (c / N.SIDE, r / N.SIDE),
                1 / N.SIDE,
                1 / N.SIDE,
                fill=False,
                edgecolor=color,
                linewidth=lw,
            )
        )


def depth_axis(ax, n_layers: int) -> None:
    ax.set_xlim(0.5, n_layers + 0.5)
    ax.set_xticks([1, 5, 10, 15, 20, 25, n_layers])
    ax.set_xlabel("encoder layer", color=MUTED)
    style_axes(ax)


def fig55_depth(out: Path) -> None:
    d = dict(np.load(N.CACHE / "55_norms.npz", allow_pickle=True))
    pl, thr = d["per_layer"], float(d["threshold"])
    n_img, L, _ = pl.shape
    x = np.arange(1, L + 1)
    count = (pl > thr).sum(2)
    first = int(np.argmax(count.mean(0) > 0)) + 1
    fig, top = figure(
        16,
        9.2,
        1,
        "SECTION 55  WHERE THE LONG TOKENS EMERGE",
        "Token norms along the 27 encoder layers, one line per image, fifty images",
        f"{n_img} images (the night's ten and the 40 gate thumbnails)  |  threshold {thr:.0f} (Darcet et al.)  |  first layer with a token above it: {first} of {L} = {first / L:.0%} depth; the paper reports 37%, CLIP ViT-B/16 layer 6 of 12  |  "
        f"count above threshold at the last layer: {int(count[:, -1].min())} to {int(count[:, -1].max())} per image  |  long-token norm at the last layer median {np.median(pl[:, -1][pl[:, -1] > thr]):.0f}, the rest {np.median(pl[:, -1][pl[:, -1] <= thr]):.0f}  |  {sha()}",
    )
    gs = fig.add_gridspec(1, 2, left=0.06, right=0.975, top=top - 0.06, bottom=0.11, wspace=0.16)
    ax = fig.add_subplot(gs[0, 0])
    for k in range(n_img):
        ax.plot(x, pl[k].max(1), color=DIM, lw=0.9, alpha=0.9)
        ax.plot(x, np.median(pl[k], axis=1), color=DIM, lw=0.9, alpha=0.9)
    ax.plot(x, pl.max(2).mean(0), color=GOLD, lw=2.4, label="longest token, mean over images")
    ax.plot(
        x, np.median(pl, axis=2).mean(0), color=CYAN, lw=2.0, label="median token, mean over images"
    )
    ax.axhline(thr, color=RED, lw=1.2, ls=(0, (4, 3)))
    ax.axvline(first, color=RED, lw=1.0, ls=(0, (2, 3)))
    ax.set_yscale("log")
    ax.set_ylabel("token norm at the layer's output", color=MUTED)
    depth_axis(ax, L)
    ax.legend(loc="center left", frameon=False, labelcolor=TEXT, fontsize=9)
    panel_title(ax, "the longest and the median token, every image in grey")
    ax = fig.add_subplot(gs[0, 1])
    rng = np.random.default_rng(0)
    for k in range(n_img):
        ax.plot(x, count[k] + rng.uniform(-0.08, 0.08), color=DIM, lw=0.9, alpha=0.9)
    ax.plot(x, count.mean(0), color=GOLD, lw=2.4)
    ax.axvline(first, color=RED, lw=1.0, ls=(0, (2, 3)))
    ax.set_ylabel(f"tokens above {thr:.0f}", color=MUTED)
    ax.set_yticks(range(int(count.max()) + 2))
    depth_axis(ax, L)
    panel_title(ax, "how many tokens are long, per image; every image overlaps")
    verdict(
        fig,
        f"two tokens jump from ~10 to ~2100 at layer {first}; a third joins at layer {L}; no image differs",
    )
    frame_panels(fig)
    fig.savefig(out, dpi=DPI, facecolor=BG)
    plt.close(fig)
    print("wrote", out)


def fig55_where(out: Path) -> None:
    d = dict(np.load(N.CACHE / "55_norms.npz", allow_pickle=True))
    high, pl = d["high"], d["per_layer"]
    n_img = len(high)
    count = high.sum(0).reshape(N.SIDE, N.SIDE)
    mean_norm = pl[:, -1].mean(0).reshape(N.SIDE, N.SIDE)
    used = np.where(high.any(0))[0]
    fig, top = figure(
        15,
        8.6,
        2,
        "SECTION 55  WHERE THEY SIT",
        "The long tokens' positions on the 24 x 24 grid, accumulated over fifty images",
        f"{n_img} images  |  {len(used)} distinct positions ever used: {', '.join(f'(row {i // N.SIDE}, col {i % N.SIDE})' for i in used)}, each in {', '.join(str(int(high[:, i].sum())) for i in used)} of {n_img} images  |  "
        f"all on the border  |  right: the mean norm of every position at the last layer, log scale  |  {sha()}",
    )
    gs = fig.add_gridspec(1, 2, left=0.04, right=0.96, top=top - 0.05, bottom=0.05, wspace=0.1)
    ax = fig.add_subplot(gs[0, 0])
    grid_map(ax, count.astype(float), vmax=float(n_img), alpha=1.0)
    for i in used:
        r, c = divmod(int(i), N.SIDE)
        ax.text(
            (c + 0.5) / N.SIDE,
            (r + 0.5) / N.SIDE,
            str(int(count[r, c])),
            color=BG,
            fontsize=9,
            ha="center",
            va="center",
            fontweight="bold",
        )
    ax.set_xticks([])
    ax.set_yticks([])
    panel_title(ax, f"images with a long token at each patch, 0 to {n_img}")
    ax = fig.add_subplot(gs[0, 1])
    lg = np.log10(mean_norm)
    grid_map(ax, lg - lg.min(), vmax=float(np.ptp(lg)), alpha=1.0)
    ax.set_xticks([])
    ax.set_yticks([])
    panel_title(
        ax,
        f"mean norm at the last layer per position, log, {mean_norm.min():.0f} to {mean_norm.max():.0f}",
    )
    verdict(fig, "the same three border patches in every image; the picture does not choose them")
    frame_panels(fig)
    fig.savefig(out, dpi=DPI, facecolor=BG)
    plt.close(fig)
    print("wrote", out)


def fig55_hide(out: Path) -> None:
    d = dict(np.load(N.CACHE / "55_norms.npz", allow_pickle=True))
    h = dict(np.load(N.CACHE / "55_hide.npz"))
    cos, cos_r = h["cos"], h["cos_random"]
    high = d["high"]
    pick = [list(N.IMAGES).index("woman-river"), list(N.IMAGES).index("goat")]
    fig, top = figure(
        17,
        9.6,
        3,
        "SECTION 55  WHAT HIDING THEM DOES",
        "The pooled vector with and without the three long tokens, fifty images; the probe's attention before and after on two",
        f"cosine between the production vector and the vector pooled with the long tokens masked out of the probe: median {np.median(cos):.4f}, min {cos.min():.4f}, {int((cos < 0.99).sum())} of {len(cos)} move by more than 0.01  |  "
        f"grey: the same count of random tokens hidden instead, median {np.median(cos_r):.4f}, min {cos_r.min():.4f}  |  share of the probe's attention on the three: {', '.join(f'{v:.0%}' for v in [h['att_full'][k][high[k].reshape(N.SIDE, N.SIDE)].sum() for k in range(10)])} on the ten  |  {sha()}",
    )
    gs = fig.add_gridspec(
        2,
        3,
        left=0.05,
        right=0.97,
        top=top - 0.05,
        bottom=0.08,
        wspace=0.08,
        hspace=0.3,
        width_ratios=[1.6, 1, 1],
    )
    ax = fig.add_subplot(gs[:, 0])
    lo = min(cos.min(), cos_r.min()) - 0.005
    bins = np.linspace(lo, 1.0005, 40)
    ax.hist(cos_r, bins=bins, color=DIM)
    ax.hist(cos, bins=bins, color=GOLD, alpha=0.9)
    ymax = ax.get_ylim()[1]
    ax.vlines(cos, 0, ymax * 0.06, color=GOLD, lw=1.0)
    ax.axvline(0.99, color=RED, lw=1.2, ls=(0, (4, 3)))
    ax.set_xlabel("cosine with the production vector", color=MUTED)
    ax.set_yticks([])
    style_axes(ax)
    panel_title(
        ax, "gold: the three long tokens hidden; grey: three random tokens hidden; red: 0.99"
    )
    for row, k in enumerate(pick):
        img = image(list(N.IMAGES)[k])
        for col, (att, name) in enumerate(
            (
                (h["att_full"][k], "probe attention, all tokens"),
                (h["att_hidden"][k], "probe attention, long tokens hidden"),
            )
        ):
            ax = fig.add_subplot(gs[row, 1 + col])
            show(ax, img, dim=0.45)
            grid_map(ax, att, vmax=float(att.max()), alpha=0.8)
            ring_patches(ax, np.where(high[k])[0], color=CYAN, lw=1.4)
            label(
                ax,
                f"top patch {att.max():.1%}, top ten {np.sort(att.ravel())[-10:].sum():.0%}",
                0.04,
            )
            if row == 0:
                panel_title(ax, name)
    verdict(fig, "three of 576 tokens move every production vector; random three move none")
    frame_panels(fig)
    fig.savefig(out, dpi=DPI, facecolor=BG)
    plt.close(fig)
    print("wrote", out)


def fig55_tokens(out: Path) -> None:
    d = dict(np.load(N.CACHE / "55_norms.npz", allow_pickle=True))
    high, pl = d["high"], d["per_layer"]
    names = list(N.IMAGES)
    fig, top = figure(
        22,
        11.4,
        5,
        "SECTION 55  THE TOKENS THEMSELVES",
        "The three long tokens ringed on each of the ten images, with their norms at the last layer",
        f"the same three patches on every image: (row 0, col 20), (row 16, col 0), (row 17, col 0)  |  norms printed beside each ring  |  ordinary tokens have norm about {np.median(pl[:, -1][~high]):.0f}  |  {sha()}",
    )
    gs = fig.add_gridspec(
        2, 5, left=0.03, right=0.97, top=top - 0.02, bottom=0.03, wspace=0.06, hspace=0.18
    )
    for k, n in enumerate(names):
        ax = fig.add_subplot(gs[k // 5, k % 5])
        show(ax, image(n))
        idx = np.where(high[k])[0]
        ring_patches(ax, idx, color=GOLD, lw=2.2)
        for i in idx:
            r, c = divmod(int(i), N.SIDE)
            ax.text(
                min((c + 1.2) / N.SIDE, 0.8),
                (r + 0.5) / N.SIDE,
                f"{pl[k, -1, i]:.0f}",
                color=GOLD,
                fontsize=9.5,
                va="center",
                bbox={"facecolor": BG, "alpha": 0.7, "edgecolor": "none", "pad": 2},
            )
        panel_title(ax, n)
    frame_panels(fig)
    fig.savefig(out, dpi=DPI, facecolor=BG)
    plt.close(fig)
    print("wrote", out)


def fig55_registers(out: Path) -> None:
    """Test-time registers (arXiv 2506.08010) on this checkpoint: before and after."""
    r = dict(np.load(N.CACHE / "55_registers.npz", allow_pickle=True))
    a = dict(np.load(N.CACHE / "55_attention.npz"))
    d = dict(np.load(N.CACHE / "55_norms.npz", allow_pickle=True))
    orig = d["per_layer"][:10]
    abl, sh = r["ablate10/norms"], r["shift30/norms"]
    L = orig.shape[1]
    x = np.arange(1, L + 1)
    score = r["score"]
    top = r["top"]
    n_l9 = int(sum(1 for t in top[:10] if int(t[0]) == 9))
    fig, top_y = figure(
        22,
        13.6,
        4,
        "SECTION 55  A TEST-TIME REGISTER FOR SIGLIP-2",
        "Score every MLP neuron by its activation at the three positions; zero the top ones, or move them onto one appended zero token",
        f"top ten neurons: {n_l9} in layer 10, scores {', '.join(f'{float(t[2]):.0f}' for t in top[:10])}  |  ablate the top 10: image tokens above 150 per image {(abl[:, -1] > 150).sum(1).mean():.1f}, cosine to production median {np.median(r['ablate10/cos']):.3f}  |  "
        f"shift the top 30 onto a register: image tokens above 150 {(sh[:, -1, :-1] > 150).sum(1).mean():.1f}, register norm {sh[:, -1, -1].mean():.0f}, cosine to production median {np.median(r['shift30/cos']):.3f}, min {r['shift30/cos'].min():.3f}, probe attention on the register {a['shift30/register_share'].mean():.0%}  |  {sha()}",
    )
    gs = fig.add_gridspec(
        2,
        6,
        left=0.045,
        right=0.975,
        top=top_y - 0.05,
        bottom=0.05,
        wspace=0.12,
        hspace=0.32,
        height_ratios=[1, 1.15],
    )
    ax = fig.add_subplot(gs[0, 0:2])
    for k in range(10):
        ax.plot(x, orig[k].max(1), color=GOLD, lw=0.9, alpha=0.5)
        ax.plot(x, abl[k].max(1), color=BLUE, lw=0.9, alpha=0.5)
        ax.plot(x, sh[k, :, :-1].max(1), color=CYAN, lw=0.9, alpha=0.5)
        ax.plot(x, sh[k, :, -1], color=CYAN, lw=0.9, alpha=0.5, ls=(0, (2, 2)))
    ax.plot([], [], color=GOLD, lw=2, label="production: longest image token")
    ax.plot([], [], color=BLUE, lw=2, label="top 10 neurons zeroed")
    ax.plot([], [], color=CYAN, lw=2, label="top 30 shifted: longest image token")
    ax.plot([], [], color=CYAN, lw=2, ls=(0, (2, 2)), label="top 30 shifted: the register token")
    ax.axhline(150, color=RED, lw=1.2, ls=(0, (4, 3)))
    ax.set_yscale("log")
    ax.set_ylabel("token norm", color=MUTED)
    depth_axis(ax, L)
    ax.legend(loc="lower right", frameon=False, labelcolor=TEXT, fontsize=8.5)
    panel_title(ax, "the longest token along depth, ten images, three conditions")
    ax = fig.add_subplot(gs[0, 2:4])
    ax.plot(x, score.max(1), color=GOLD, lw=2.2)
    ax.scatter(
        [int(t[0]) + 1 for t in top[:10]],
        [float(t[2]) for t in top[:10]],
        color=RED,
        s=28,
        zorder=5,
    )
    ax.set_ylabel(
        "neuron score",
        color=MUTED,
    )
    depth_axis(ax, L)
    panel_title(ax, f"the best neuron in each layer; red: the top ten ({n_l9} of them in layer 10)")
    ax = fig.add_subplot(gs[0, 4:6])
    for y, (key, col, name) in enumerate(
        (("ablate10/cos", BLUE, "top 10 zeroed"), ("shift30/cos", CYAN, "top 30 shifted"))
    ):
        v = r[key]
        ax.scatter(
            v, np.full(10, y) + np.random.default_rng(1).uniform(-0.12, 0.12, 10), color=col, s=40
        )
        ax.text(v.max(), y + 0.3, name, color=col, fontsize=9.5, ha="right")
    hide = dict(np.load(N.CACHE / "55_hide.npz"))["cos"][:10]
    ax.scatter(
        hide, np.full(10, 2) + np.random.default_rng(2).uniform(-0.12, 0.12, 10), color=GOLD, s=40
    )
    ax.text(
        hide.max(),
        2.3,
        "the three simply hidden from the probe",
        color=GOLD,
        fontsize=9.5,
        ha="right",
    )
    ax.axvline(0.99, color=RED, lw=1.2, ls=(0, (4, 3)))
    ax.set_ylim(-0.6, 2.9)
    ax.set_yticks([])
    ax.set_xlabel("cosine with the production vector, ten images", color=MUTED)
    style_axes(ax)
    panel_title(ax, "how far each fix moves the vector ytk would search with")
    names = list(N.IMAGES)
    for row, name in enumerate(("goat", "woman-river")):
        k = names.index(name)
        img = image(name)
        for col, (key, title) in enumerate(
            (
                ("original", "production"),
                ("ablate10", "top 10 zeroed"),
                ("shift30", "top 30 shifted to a register"),
            )
        ):
            ax = fig.add_subplot(gs[1, row * 3 + col])
            show(ax, img, dim=0.45)
            m = a[f"{key}/att"][k]
            grid_map(ax, m, vmax=float(m.max()), alpha=0.8)
            if key == "original":
                ring_patches(ax, np.where(d["high"][k])[0], color=CYAN, lw=1.4)
            reg = float(a[f"{key}/register_share"][k])
            label(
                ax,
                f"top patch {m.max():.1%}, top ten {np.sort(m.ravel())[-10:].sum():.0%}"
                + (f", register {reg:.0%}" if key == "shift30" else ""),
                0.04,
            )
            panel_title(ax, f"{name}: {title}")
    verdict(
        fig,
        "nine neurons in layer 10 make the long tokens; a register removes them at cosine 0.98, the attention map is still speckle",
    )
    frame_panels(fig)
    fig.savefig(out, dpi=DPI, facecolor=BG)
    plt.close(fig)
    print("wrote", out)


def main() -> None:
    what = sys.argv[1] if len(sys.argv) > 1 else "ten"
    if what == "ten":
        d = N.SECTION_ROOT / "54-region-head"
        d.mkdir(exist_ok=True)
        fig_ten(d / "00-the-ten.png")
    elif what == "54":
        d = N.SECTION_ROOT / "54-region-head"
        all54 = dict(np.load(N.CACHE / "54_all.npz", allow_pickle=True))
        which = sys.argv[2] if len(sys.argv) > 2 else "all"
        if which in ("woman", "all"):
            fig54_woman(d / "01-the-woman-three-ways.png", all54)
        if which in ("sheet", "all"):
            fig54_all(d / "02-all-ten-all-thirty.png", all54)
        if which in ("disagree", "all"):
            fig54_disagree(d / "03-where-they-disagree.png", all54)
        if which in ("attention", "all"):
            fig54_attention(d / "04-attention-inside-each-region.png")
    elif what == "55":
        d = N.SECTION_ROOT / "55-long-tokens"
        d.mkdir(exist_ok=True)
        which = sys.argv[2] if len(sys.argv) > 2 else "all"
        if which in ("depth", "all"):
            fig55_depth(d / "01-where-they-emerge.png")
        if which in ("where", "all"):
            fig55_where(d / "02-where-they-sit.png")
        if which in ("hide", "all"):
            fig55_hide(d / "03-what-hiding-them-does.png")
        if which in ("tokens", "all"):
            fig55_tokens(d / "05-the-tokens-themselves.png")
        if which in ("registers", "all"):
            fig55_registers(d / "04-a-test-time-register.png")
    else:
        raise SystemExit(f"unknown figure set {what}")


if __name__ == "__main__":
    main()
