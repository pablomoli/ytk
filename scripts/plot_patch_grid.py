"""Figures for section 53 (#218), from patch_grid.json and the per-image cache.

uv run --with matplotlib python scripts/plot_patch_grid.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "experiments" / "patch_grid"))
import run as R
from plot_assets import (
    BG,
    BLUE,
    DIM,
    DPI,
    GOLD,
    MUTED,
    RED,
    figure,
    frame_panels,
    panel_title,
    punch,
    saturated_magma,
    style_axes,
    verdict,
)

OUT = R.OUT.parent
NAMES = {"lens1": "probe attention", "lens2": "patch alone", "lens4": "gradient through the head"}


def overlay(ax, img: Image.Image, m: np.ndarray, vmax: float | None = None) -> None:
    g = np.asarray(img.convert("L"), dtype=float) / 255.0
    ax.imshow(np.dstack([g * 0.55] * 3), extent=(0, 1, 1, 0), aspect="auto")
    m = np.clip(m, 0, None)
    m = m / vmax if vmax else (m - m.min()) / (np.ptp(m) + 1e-12)
    ax.imshow(
        saturated_magma()(punch(np.clip(m, 0, 1))),
        extent=(0, 1, 1, 0),
        aspect="auto",
        alpha=0.62,
        interpolation="nearest",
    )
    ax.set_xticks([])
    ax.set_yticks([])


def load():
    res = json.loads(R.OUT.read_text())
    rows = R.sample()
    maps = [dict(np.load(R.CACHE / f"{i.replace(':', '_')}.npz")) for i, _ in rows]
    imgs = [Image.open(os.path.expanduser(m["image_path"])).convert("RGB") for _, m in rows]
    return res, maps, imgs


def fig_gate(res) -> None:
    lo = min(min(res[k]["per_image"]) for k in NAMES) - 0.05
    hi = max(max(max(res[k]["per_image"]) for k in NAMES), res["pass_mark"]) + 0.05
    meta = "  |  ".join(
        f"{NAMES[k]}: mean {res[k]['mean']:.2f}, null p95 {res[k]['null_p95']:.2f}" for k in NAMES
    )
    fig, top = figure(
        15,
        8.6,
        1,
        "SECTION 53  THE GATE",
        "Do the cheap maps agree with covering a block and looking",
        f"n = {res['n']} thumbnails, Spearman over 36 blocks  |  {meta}  |  {res['commit']}",
    )
    gs = fig.add_gridspec(3, 1, left=0.05, right=0.965, top=top - 0.03, bottom=0.08, hspace=0.42)
    for r, k in enumerate(NAMES):
        ax = fig.add_subplot(gs[r, 0])
        ax.hist(res[k]["null_means"], bins=40, color=DIM)
        ymax = ax.get_ylim()[1]
        ax.vlines(res[k]["per_image"], 0, ymax * 0.10, color=GOLD, alpha=0.55, lw=1.1)
        ax.axvline(res[k]["mean"], color=GOLD, lw=2.6)
        ax.axvline(res["pass_mark"], color=RED, lw=1.4, ls=(0, (4, 3)))
        ax.set_xlim(lo, hi)
        ax.set_yticks([])
        style_axes(ax)
        panel_title(ax, f"{NAMES[k]}  (grey: what thumbnail layout alone scores)")
        if r == 2:
            ax.set_xlabel("rank correlation with the occlusion map", color=MUTED)
    passed = [NAMES[k] for k in NAMES if res[k]["passes"]]
    verdict(
        fig,
        f"PASS: {', '.join(passed)}"
        if passed
        else f"FAIL: no cheap lens reaches {res['pass_mark']:.2f}",
    )
    frame_panels(fig)
    fig.savefig(OUT / "01-the-gate.png", dpi=DPI, facecolor=BG)


def fig_lenses(
    res, maps, imgs, order: list[int], number: int, name: str, kicker: str, title: str
) -> None:
    share = [m["lens3"][..., 0] / max(m["base"][0], 1e-9) for m in maps]
    vmax = max(float(share[i].max()) for i in order)
    fig, top = figure(
        16,
        3.05 * len(order) + 1.6,
        number,
        kicker,
        title,
        f"all maps at the referee's 6 x 6 blocks  |  occlusion column on one scale, 0 to {vmax:.0%} of the image-title match"
        f"  |  cheap lenses scaled per panel  |  corner: rank correlation with occlusion  |  {res['commit']}",
    )
    gs = fig.add_gridspec(
        len(order), 4, left=0.035, right=0.965, top=top - 0.03, bottom=0.03, wspace=0.05, hspace=0.1
    )
    heads = ["thumbnail", "patch alone", "gradient through the head", "cover a block (the referee)"]
    for r, i in enumerate(order):
        m = maps[i]
        cells = [
            None,
            R.blocks(m["lens2"][..., 0], "mean").reshape(R.G, R.G),
            R.blocks(m["lens4"][..., 0], "sum").reshape(R.G, R.G),
            share[i],
        ]
        for c, cell in enumerate(cells):
            ax = fig.add_subplot(gs[r, c])
            if cell is None:
                ax.imshow(imgs[i], extent=(0, 1, 1, 0), aspect="auto")
                ax.set_xticks([])
                ax.set_yticks([])
            else:
                overlay(ax, imgs[i], cell, vmax if c == 3 else None)
            if r == 0:
                panel_title(ax, heads[c])
            if c in (1, 2):
                k = "lens2" if c == 1 else "lens4"
                ax.text(
                    0.02,
                    0.96,
                    f"{res[k]['per_image'][i]:+.2f}",
                    color="white",
                    fontsize=9,
                    va="top",
                    transform=ax.transAxes,
                )
            if c == 3:
                ax.text(
                    0.02,
                    0.96,
                    f"max {share[i].max():.0%}",
                    color="white",
                    fontsize=9,
                    va="top",
                    transform=ax.transAxes,
                )
    frame_panels(fig)
    fig.savefig(OUT / name, dpi=DPI, facecolor=BG)


def fig_referee(res) -> None:
    ref = res["referee"]
    t = np.array(ref["max_drop_true"]) / np.array(ref["base_true"])
    w = np.array(ref["max_drop_wrong"]) / np.maximum(np.abs(ref["base_wrong"]), 1e-9)
    w = np.clip(w, -1, 2)
    fig, top = figure(
        9.5,
        9.6,
        3,
        "SECTION 53  THE REFEREE",
        "How much of a match one block carries, right title against wrong",
        f"n = {res['n']}  |  median largest drop {np.median(t):.0%} of the match under the true title, {np.median(w):.0%} under another image's title  |  {res['commit']}",
    )
    ax = fig.add_axes([0.11, 0.09, 0.84, top - 0.14])
    lim = float(max(t.max(), w.max()) * 1.08)
    ax.plot([0, lim], [0, lim], color=DIM, lw=1.4)
    ax.scatter(w, t, s=70, color=GOLD, alpha=0.85, edgecolor="none")
    ax.set_xlim(min(0, w.min()) - 0.01, lim)
    ax.set_ylim(0, lim)
    ax.set_xlabel("largest drop, wrong title (share of that match)", color=MUTED)
    ax.set_ylabel("largest drop, true title (share of that match)", color=MUTED)
    style_axes(ax)
    panel_title(ax, "above the line: covering one block costs the true title more")
    verdict(fig, f"{int((t > w).sum())} of {len(t)} above the line")
    frame_panels(fig)
    fig.savefig(OUT / "03-the-referee.png", dpi=DPI, facecolor=BG)


def fig_text(res) -> None:
    fig, top = figure(
        12,
        8.2,
        4,
        "SECTION 53  DOES THE LENS READ THE QUERY",
        "Agreement with the referee under the true title and under a wrong one",
        "  |  ".join(
            f"{NAMES[k]}: true minus wrong {res[k]['true_minus_wrong']:+.2f}, 95% interval "
            f"[{res[k]['true_minus_wrong_ci95'][0]:+.2f}, {res[k]['true_minus_wrong_ci95'][1]:+.2f}]"
            for k in ("lens2", "lens4")
        )
        + f"  |  {res['commit']}",
    )
    gs = fig.add_gridspec(1, 2, left=0.07, right=0.965, top=top - 0.05, bottom=0.09, wspace=0.12)
    allv = [
        v
        for k in ("lens2", "lens4")
        for key in ("per_image", "wrong_title_per_image")
        for v in res[k][key]
    ]
    for c, k in enumerate(("lens2", "lens4")):
        ax = fig.add_subplot(gs[0, c])
        tr, wr = np.array(res[k]["per_image"]), np.array(res[k]["wrong_title_per_image"])
        for a, b in zip(wr, tr):
            ax.plot([0, 1], [a, b], color=GOLD if b > a else BLUE, alpha=0.5, lw=1.2)
        ax.plot([0, 1], [wr.mean(), tr.mean()], color="white", lw=3)
        ax.set_xlim(-0.15, 1.15)
        ax.set_ylim(min(allv) - 0.05, max(allv) + 0.05)
        ax.set_xticks([0, 1], ["wrong title", "true title"])
        style_axes(ax)
        panel_title(ax, f"{NAMES[k]}  (gold rises, blue falls, white is the mean)")
        if c == 0:
            ax.set_ylabel("rank correlation with the occlusion map", color=MUTED)
    reads = [NAMES[k] for k in ("lens2", "lens4") if res[k]["reads_text"]]
    verdict(
        fig, f"reads the query: {', '.join(reads)}" if reads else "neither lens reads the query"
    )
    frame_panels(fig)
    fig.savefig(OUT / "04-does-it-read-the-query.png", dpi=DPI, facecolor=BG)


def main() -> None:
    res, maps, imgs = load()
    fig_gate(res)
    by = np.argsort(res["lens4"]["per_image"])
    fig_lenses(
        res,
        maps,
        imgs,
        [int(by[-1]), int(by[-2]), int(by[len(by) // 2]), int(by[len(by) // 2 - 1])],
        2,
        "02-three-lenses.png",
        "SECTION 53  THE LENSES",
        "Two best and two median thumbnails by the gradient lens's agreement",
    )
    fig_referee(res)
    fig_text(res)
    fig_lenses(
        res,
        maps,
        imgs,
        [int(i) for i in by[:4]],
        5,
        "05-where-they-disagree.png",
        "SECTION 53  THE PANEL THAT KILLS IT",
        "The four thumbnails where the gradient lens and the referee disagree most",
    )
    print("wrote 5 figures to", OUT)


if __name__ == "__main__":
    main()
