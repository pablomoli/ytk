"""Section 44 — atlas rung 3 (#183): binning the frozen map into named cells.

Figure 01: the atlas — 62 grid cells over the frozen layout, each labeled by
its top excess latent, stability drawn into the label. Figure 02: the trust
panel — the same lattice colored by seed stability, head-explained mass, and
OOD fraction. Figure 03: the protagonist's excess field as terrain.

Data: experiments/sae_qwen/atlas.json (atlas_bin.py). Read-only.

    uv run --with matplotlib,scipy python scripts/plot_atlas_cells.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plot_assets import (
    BG,
    BLUE,
    CYAN,
    DIM,
    DPI,
    FRAME,
    GOLD,
    MUTED,
    RED,
    TEXT,
    figure,
    frame_panels,
    panel_title,
    punch,
    saturated_magma,
    verdict,
)

REPO = Path(__file__).resolve().parents[1]
OUTDIR = REPO / "docs" / "assets" / "44-atlas-binning"
ATLAS = REPO / "experiments" / "sae_qwen" / "atlas.json"

SHA = subprocess.run(
    ["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], capture_output=True, text=True
).stdout.strip()


def save(fig, name: str) -> None:
    frame_panels(fig)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    out = OUTDIR / name
    fig.savefig(out, dpi=DPI, facecolor=BG)
    print(f"wrote {out.relative_to(REPO)}  ({out.stat().st_size // 1024}KB)")
    plt.close(fig)


def load():
    atlas = json.loads(ATLAS.read_text())
    mp = json.loads((Path.home() / ".ytk" / "map.json").read_text())
    return atlas, mp["points"]


def cell_rect(c, **kw):
    return Rectangle((c["x0"], c["y0"]), c["x1"] - c["x0"], c["y1"] - c["y0"], **kw)


def fig01(atlas, points):
    cells = atlas["cells"]
    g = atlas["gate"]
    fig, top = figure(
        16.5,
        11.8,
        1,
        "atlas rung 3 — the named lattice",
        "The corpus map, read as cells with latent identities",
        f"{atlas['grid']}x{atlas['grid']} lattice over the frozen 08-11 layout, "
        f"{len(cells)} cells with >= {atlas['min_cell_scored']} scored notes | label = top "
        f"excess latent (excess_profile, 200-draw null per cell) | solid label = survives "
        f"seeds 1,2 at cos 0.5 ({g['stable_05']}/{g['n']}), faint = does not | {SHA}",
    )
    ax = fig.add_axes([0.045, 0.05, 0.91, top - 0.09])
    ax.set_facecolor("#000000")
    for s in ax.spines.values():
        s.set_color(FRAME)
    ax.set_xticks([])
    ax.set_yticks([])
    xs = [q["x"] for q in points]
    ys = [q["y"] for q in points]
    ax.scatter(xs, ys, s=3, color=DIM, alpha=0.55, linewidths=0)

    cmap = saturated_magma()
    emax = max(abs(c["label_excess"]) for c in cells)
    for c in cells:
        strength = punch(np.array([abs(c["label_excess"]) / emax]))[0]
        ax.add_patch(
            cell_rect(
                c,
                facecolor=cmap(0.15 + 0.55 * strength),
                alpha=0.34,
                edgecolor=FRAME,
                linewidth=0.7,
            )
        )
        name = (c["label"] or "").replace(" and ", " & ")
        col = TEXT if c["stable_05"] else MUTED
        alpha = 1.0 if c["stable_05"] else 0.55
        cxm, cym = (c["x0"] + c["x1"]) / 2, (c["y0"] + c["y1"]) / 2
        ax.text(
            cxm,
            cym + 0.013,
            f"#{c['label_latent']}",
            ha="center",
            va="center",
            color=col,
            alpha=alpha,
            fontsize=5.6,
            fontweight="bold",
        )
        ax.text(
            cxm,
            cym - 0.016,
            "\n".join([name[i : i + 16] for i in range(0, min(len(name), 32), 16)]),
            ha="center",
            va="center",
            color=col,
            alpha=alpha,
            fontsize=4.9,
        )
    pc = atlas["protagonist"]["cell"]
    if pc:
        xe, ye = atlas["x_edges"], atlas["y_edges"]
        ax.add_patch(
            Rectangle(
                (xe[pc[0]], ye[pc[1]]),
                xe[pc[0] + 1] - xe[pc[0]],
                ye[pc[1] + 1] - ye[pc[1]],
                facecolor="none",
                edgecolor=CYAN,
                linewidth=1.6,
                linestyle="--",
            )
        )
        ax.text(
            xe[pc[0]] + 0.01,
            ye[pc[1] + 1] - 0.028,
            "protagonist (est.)",
            color=CYAN,
            fontsize=6.4,
        )
    ax.set_xlim(min(xs) - 0.02, max(xs) + 0.02)
    ax.set_ylim(min(ys) - 0.02, max(ys) + 0.02)
    n_distinct = len({c["label_latent"] for c in cells})
    verdict(
        fig,
        f"{n_distinct} distinct identities across {len(cells)} cells — the map has local vocabulary",
    )
    save(fig, "01-named-lattice.png")


def fig02(atlas, points):
    cells = atlas["cells"]
    g = atlas["gate"]
    fig, top = figure(
        16.5,
        6.8,
        2,
        "atlas rung 3 — the trust panel",
        "What each cell asks you to believe, and how much of it is disclosed",
        f"left: label survives retraining (gold cos >= 0.8, blue >= 0.5, red = neither; top-5 "
        f"match vs seeds 1,2) | middle: activation mass the named head explains | right: notes "
        f"unseen by the Aug-8 checkpoint | {SHA}",
    )
    gs = fig.add_gridspec(1, 3, left=0.04, right=0.975, top=top, bottom=0.075, wspace=0.10)
    cmap = saturated_magma()
    xs = [q["x"] for q in points]
    ys = [q["y"] for q in points]

    def panel(k, title, painter):
        ax = fig.add_subplot(gs[0, k])
        ax.set_facecolor("#000000")
        for s in ax.spines.values():
            s.set_color(FRAME)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.scatter(xs, ys, s=1.5, color=DIM, alpha=0.4, linewidths=0)
        for c in cells:
            painter(ax, c)
        ax.set_xlim(min(xs) - 0.02, max(xs) + 0.02)
        ax.set_ylim(min(ys) - 0.02, max(ys) + 0.02)
        panel_title(ax, title, width=40)

    def p_stab(ax, c):
        if c["stable_08"]:
            ax.add_patch(cell_rect(c, facecolor=GOLD, alpha=0.75, edgecolor=FRAME, linewidth=0.5))
        elif c["stable_05"]:
            ax.add_patch(cell_rect(c, facecolor=BLUE, alpha=0.55, edgecolor=FRAME, linewidth=0.5))
        else:
            ax.add_patch(cell_rect(c, facecolor="none", edgecolor=RED, linewidth=0.9))

    def p_head(ax, c):
        ax.add_patch(
            cell_rect(
                c,
                facecolor=cmap(punch(np.array([c["head_mass"]]))[0]),
                alpha=0.9,
                edgecolor=FRAME,
                linewidth=0.5,
            )
        )
        ax.text(
            (c["x0"] + c["x1"]) / 2,
            (c["y0"] + c["y1"]) / 2,
            f"{c['head_mass'] * 100:.0f}",
            ha="center",
            va="center",
            color=BG,
            fontsize=5.4,
        )

    def p_ood(ax, c):
        ax.add_patch(
            cell_rect(
                c,
                facecolor=cmap(punch(np.array([min(c["ood_frac"] * 3, 1.0)]))[0]),
                alpha=0.9,
                edgecolor=FRAME,
                linewidth=0.5,
            )
        )
        ax.text(
            (c["x0"] + c["x1"]) / 2,
            (c["y0"] + c["y1"]) / 2,
            f"{c['ood_frac'] * 100:.0f}",
            ha="center",
            va="center",
            color=BG,
            fontsize=5.4,
        )

    hm = [c["head_mass"] for c in cells]
    om = [c["ood_frac"] for c in cells]
    panel(
        0,
        f"label stability: {g['stable_08']} gold, {g['stable_05'] - g['stable_08']} blue, "
        f"{g['n'] - g['stable_05']} red",
        p_stab,
    )
    panel(1, f"head-explained mass, % (median {np.median(hm) * 100:.0f}%)", p_head)
    panel(2, f"OOD fraction, % (median {np.median(om) * 100:.0f}%, x3 ramp)", p_ood)
    verdict(
        fig,
        f"{g['stable_05']}/{g['n']} labels survive retraining — the other {g['n'] - g['stable_05']} say so on the map",
    )
    save(fig, "02-trust-panel.png")


def fig03(atlas, points):
    from matplotlib.colors import LightSource
    from scipy.ndimage import zoom

    cells = atlas["cells"]
    G = atlas["grid"]
    Z = np.zeros((G, G))
    for c in cells:
        Z[c["cell"][1], c["cell"][0]] = c["protagonist_excess"]
    n_out = sum(1 for c in cells if c["protagonist_outside_null"])
    pc = atlas["protagonist"]["cell"]

    fig, top = figure(
        16.5,
        8.6,
        3,
        "atlas rung 3 — protagonist terrain",
        "Latent #1597 as landscape: where educational LM content lives",
        f"height = per-cell excess activation mass of #1597 over the corpus base rate | "
        f"empty cells at sea level 0 | surface: bilinear lerp between the {G}x{G} cell values, "
        f"8x | {n_out}/{len(cells)} cells outside their 200-draw null | cyan post = the "
        f"protagonist's estimated cell | {SHA}",
    )
    UP = 8
    Zf = zoom(Z, UP, order=1)
    zmax = float(np.abs(Z).max()) or 1.0
    # 0 sits at the ramp's floor, not its middle: the empty plain must read
    # dark so the ridge alone is bright — sparsity as darkness, in relief
    norm = plt.Normalize(float(Z.min()), zmax)
    ls = LightSource(azdeg=315, altdeg=45)
    rgb = ls.shade(Zf, cmap=saturated_magma(), norm=norm, vert_exag=40, blend_mode="soft")
    xxf, yyf = np.meshgrid(np.linspace(0, G - 1, G * UP), np.linspace(0, G - 1, G * UP))

    ax = fig.add_axes([0.06, 0.02, 0.88, top - 0.06], projection="3d")
    ax.set_facecolor(BG)
    ax.plot_surface(
        xxf,
        yyf,
        Zf,
        facecolors=rgb,
        rcount=G * UP // 2,
        ccount=G * UP // 2,
        linewidth=0,
        antialiased=True,
        shade=False,
    )
    if pc:
        ax.plot([pc[0], pc[0]], [pc[1], pc[1]], [0, zmax * 1.05], color=CYAN, lw=2.2, zorder=11)
        ax.text(pc[0], pc[1], zmax * 1.14, "#1597 home (est.)", color=CYAN, fontsize=8)
    ax.set_zlim(-zmax * 0.4, zmax * 1.1)
    ax.set_xlim(0, G - 1)
    ax.set_ylim(G - 1, 0)
    ax.view_init(elev=32, azim=-58)
    ax.set_box_aspect((1, 1, 0.40), zoom=1.28)
    for pane in (ax.xaxis, ax.yaxis, ax.zaxis):
        pane.set_pane_color((0, 0, 0, 0))
        pane.line.set_color(FRAME)
    ax.grid(False)
    ax.tick_params(colors=MUTED, labelsize=6, pad=-1)
    ax.set_xticks([0, G // 2, G - 1])
    ax.set_yticks([0, G // 2, G - 1])
    ax.set_xlabel("map cell x", color=MUTED, fontsize=7, labelpad=-4)
    ax.set_ylabel("map cell y", color=MUTED, fontsize=7, labelpad=-4)
    ax.set_zlabel("excess mass", color=MUTED, fontsize=7, labelpad=-2)
    verdict(
        fig,
        "one ridge, one home — the latent is geographically concentrated"
        if n_out
        else "no cell exceeds its null — the latent has no geography",
    )
    save(fig, "03-protagonist-terrain.png")


def main() -> None:
    atlas, points = load()
    fig01(atlas, points)
    fig02(atlas, points)
    fig03(atlas, points)
    (OUTDIR / "atlas.json").write_text(json.dumps(atlas, indent=1))
    print("copied atlas.json sidecar")


if __name__ == "__main__":
    main()
