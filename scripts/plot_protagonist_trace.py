"""Section 46 — atlas rung 5 (#183): the protagonist trace, end to end.

The A1 series: one real note through every representation the system holds.
Figure 01: text -> vector image -> SAE code, reshape shown, pixels inked.
Figure 02: the note on the atlas and among its neighbors under both lenses.
Figure 03: the journey — the note slerped into an EpicMap note, re-encoded
at every step, the handover drawn.

Data: experiments/sae_qwen/trace.json (trace_protagonist.py) + atlas.json.
Figure 03 needs torch (re-encoding along the path):

    YTK_VISUAL_INDEX=off uv run --with torch --with matplotlib \
        python scripts/plot_protagonist_trace.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plot_assets import (
    BG,
    CYAN,
    DIM,
    DPI,
    FRAME,
    GOLD,
    MUTED,
    PANEL,
    figure,
    frame_panels,
    panel_title,
    style_axes,
    vector_image,
    verdict,
)

REPO = Path(__file__).resolve().parents[1]
SAE = REPO / "experiments" / "sae_qwen"
OUTDIR = REPO / "docs" / "assets" / "46-protagonist-trace"
PROT = 1597

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


def fig01(tr: dict) -> None:
    v = np.asarray(tr["vector"], np.float32)
    code = np.zeros(2048, np.float32)
    for f, a in tr["code"].items():
        code[int(f)] = a
    fig, top = figure(
        16.5,
        7.6,
        1,
        "protagonist trace — the reshape, shown",
        "One note becomes an addressable picture",
        f"'{tr['title']}' | text -> Qwen 1024d (first values "
        f"{', '.join(str(x) for x in tr['vector_sample'][:4])}, ...) -> 32x32 | SAE: "
        f"{tr['code_active']} of 2,048 latents live -> 64x32, #{PROT} inked | {SHA}",
    )
    gs = fig.add_gridspec(
        1,
        3,
        width_ratios=[1.35, 1, 1.05],
        left=0.045,
        right=0.975,
        top=top,
        bottom=0.10,
        wspace=0.18,
    )

    ax = fig.add_subplot(gs[0, 0])
    ax.axis("off")
    ax.set_facecolor(PANEL)
    body = textwrap.fill(tr["text_head"][:430].replace("\n", " "), 52)
    ax.text(0.02, 0.97, body, color=MUTED, fontsize=7.6, va="top", linespacing=1.5)
    ax.text(
        0.02,
        0.10,
        f"-> [ {', '.join(str(x) for x in tr['vector_sample'])}, ... ]  (1024 values)",
        color=GOLD,
        fontsize=8.2,
    )
    panel_title(ax, "the note, as embedded")

    ax = fig.add_subplot(gs[0, 1])
    info = vector_image(ax, v)
    ax.set_xlabel(info["meta"], color=MUTED, fontsize=7.5)
    panel_title(ax, "its Qwen vector, reshaped")

    ax = fig.add_subplot(gs[0, 2])
    info = vector_image(ax, code, annotate=[(PROT, "#1597")])
    ax.set_xlabel(info["meta"], color=MUTED, fontsize=7.5)
    top3 = tr["top_latents"][:3]
    ax.text(
        0.0,
        -0.16,
        "\n".join(f"#{t['latent']}  {(t['name'] or '')[:36]}  {t['act']:.2f}" for t in top3),
        transform=ax.transAxes,
        color=MUTED,
        fontsize=7.2,
        va="top",
    )
    panel_title(ax, "its SAE code — sparsity as darkness")
    verdict(
        fig, f"{tr['named_mass_frac']:.0%} of this note's code mass has a name — the rest is dark"
    )
    save(fig, "01-the-reshape.png")


def fig02(tr: dict) -> None:
    atlas = json.loads((SAE / "atlas.json").read_text())
    mp = json.loads((Path.home() / ".ytk" / "map.json").read_text())
    points = mp["points"]
    fig, top = figure(
        16.5,
        7.0,
        2,
        "protagonist trace — place and company",
        "Where the note lives, and who it lives with, under both lenses",
        f"left: the frozen map, atlas cells faint, the note's estimated cell CYAN (10-NN vote — "
        f"it postdates the layout) | right: top-5 neighbors by Qwen cosine vs SAE-code cosine, "
        f"{tr['neighbor_overlap']}/5 shared (section 37 corpus median: 3/10) | {SHA}",
    )
    gs = fig.add_gridspec(
        1, 3, width_ratios=[1.5, 1, 1], left=0.04, right=0.975, top=top, bottom=0.10, wspace=0.14
    )

    ax = fig.add_subplot(gs[0, 0])
    ax.set_facecolor("#000000")
    for s in ax.spines.values():
        s.set_color(FRAME)
    ax.set_xticks([])
    ax.set_yticks([])
    xs = [q["x"] for q in points]
    ys = [q["y"] for q in points]
    ax.scatter(xs, ys, s=2.5, color=DIM, alpha=0.5, linewidths=0)
    from matplotlib.patches import Rectangle

    for c in atlas["cells"]:
        ax.add_patch(
            Rectangle(
                (c["x0"], c["y0"]),
                c["x1"] - c["x0"],
                c["y1"] - c["y0"],
                facecolor="none",
                edgecolor=FRAME,
                linewidth=0.5,
            )
        )
    pc = atlas["protagonist"]["cell"]
    xe, ye = atlas["x_edges"], atlas["y_edges"]
    ax.add_patch(
        Rectangle(
            (xe[pc[0]], ye[pc[1]]),
            xe[pc[0] + 1] - xe[pc[0]],
            ye[pc[1] + 1] - ye[pc[1]],
            facecolor=CYAN,
            alpha=0.25,
            edgecolor=CYAN,
            linewidth=1.6,
            linestyle="--",
        )
    )
    cell = next(c for c in atlas["cells"] if c["cell"] == pc)
    ax.text(
        xe[pc[0]] + 0.01,
        ye[pc[1]] - 0.035,
        f"cell label: #{cell['label_latent']} {cell['label'][:30]}",
        color=CYAN,
        fontsize=7.5,
    )
    ax.set_xlim(min(xs) - 0.02, max(xs) + 0.02)
    ax.set_ylim(min(ys) - 0.02, max(ys) + 0.02)
    panel_title(ax, "the estimated home cell")

    shared = {n["title"] for n in tr["neighbors_qwen"]} & {n["title"] for n in tr["neighbors_sae"]}
    for k, (key, lens) in enumerate(
        (("neighbors_qwen", "Qwen cosine"), ("neighbors_sae", "SAE-code cosine"))
    ):
        ax = fig.add_subplot(gs[0, k + 1])
        style_axes(ax)
        ns = tr[key]
        ys_ = np.arange(len(ns))[::-1]
        for y, n in zip(ys_, ns):
            c = GOLD if n["title"] in shared else MUTED
            ax.barh(y, n["sim"], color=c, height=0.6)
            ax.text(0.012, y, n["title"][:34], color=BG, fontsize=7.2, va="center")
        ax.set_yticks([])
        ax.set_xlim(0, max(n["sim"] for n in ns) * 1.05)
        ax.set_xlabel(lens)
        if k == 0:
            panel_title(ax, "gold = shared between the lenses", width=40)
        else:
            panel_title(ax, "the SAE family", width=40)
    verdict(fig, "the two lenses agree on this note more than the corpus usually allows")
    save(fig, "02-place-and-company.png")


def fig03(tr: dict) -> None:
    import torch

    sys.path.insert(0, str(SAE))
    import train_sae as T

    feats = json.loads((SAE / "features.json").read_text())
    named = {f["feature"]: f.get("name") for f in feats["features"]}
    rows = [json.loads(x) for x in (SAE / "data" / "rows.jsonl").read_text().splitlines()]
    X = np.load(SAE / "data" / "vectors.npz")["X"]
    id2row = {}
    for i, r in enumerate(rows):
        id2row.setdefault(r["id"], i)

    a = np.asarray(tr["vector"], np.float32)
    tgt = next(f for f in feats["features"] if f["feature"] == 977)
    e0 = tgt["exemplars"][0]
    b = X[id2row[e0["id"]]]
    end_title = e0["title"] or "an EpicMap developer note"

    m = T.TopKSAE(1024, 2048, 32)
    m.load_state_dict(
        torch.load(SAE / "checkpoints" / "final_d2048_k32_s0.pt", map_location="cpu")["state"]
    )
    m.eval()

    def slerp(a, b, t):
        om = np.arccos(np.clip(a @ b, -1, 1))
        so = np.sin(om)
        v = (np.sin((1 - t) * om) * a + np.sin(t * om) * b) / so
        return v / np.linalg.norm(v)

    STEPS = 7
    ts = np.linspace(0, 1, STEPS)
    codes, tops = [], []
    with torch.no_grad():
        for t in ts:
            v = slerp(a, b, float(t))
            pre = m.pre_acts(torch.as_tensor(v[None]))
            zc, _ = m.topk(pre, 32)
            codes.append(zc[0].numpy())
            tops.append(int(codes[-1].argmax()))

    fig, top = figure(
        16.5,
        8.6,
        3,
        "protagonist trace — the journey",
        "The note slerped into another world, its code re-drawn at every step",
        f"start: {tr['title'][:44]} | end: {end_title[:44]} | {STEPS} steps on the great "
        f"circle, k=32 re-encoded per step | 2048d -> 64x32 | {SHA}",
    )
    gs = fig.add_gridspec(
        2,
        STEPS,
        height_ratios=[1.25, 1],
        left=0.05,
        right=0.975,
        top=top,
        bottom=0.11,
        wspace=0.14,
        hspace=0.34,
    )
    for i, (t, code) in enumerate(zip(ts, codes)):
        ax = fig.add_subplot(gs[0, i])
        marks = []
        if code[PROT] > 0:
            marks.append((PROT, ""))
        if code[977] > 0:
            marks.append((977, ""))
        vector_image(ax, code, annotate=marks)
        f = tops[i]
        ax.set_title(f"t={t:.2f}", color=MUTED, fontsize=8, pad=3)
        ax.set_xlabel(
            f"#{f}\n{(named.get(f) or 'unnamed')[:20]}",
            color=CYAN if f == PROT else (GOLD if f == 977 else MUTED),
            fontsize=6.6,
        )

    ax = fig.add_subplot(gs[1, :])
    ap = [c[PROT] for c in codes]
    at = [c[977] for c in codes]
    ax.plot(ts, ap, color=CYAN, lw=2.0, marker="o", ms=4, label=f"#{PROT} {named.get(PROT)[:38]}")
    ax.plot(ts, at, color=GOLD, lw=2.0, marker="o", ms=4, label=f"#977 {named.get(977)[:38]}")
    leg = ax.legend(frameon=False, fontsize=8.5)
    for t_ in leg.get_texts():
        t_.set_color(MUTED)
    style_axes(ax)
    ax.set_xlabel("position on the great circle between the two notes")
    ax.set_ylabel("latent activation")
    cross = next((i for i in range(1, STEPS) if at[i] > ap[i]), None)
    panel_title(
        ax,
        f"the handover: #977 overtakes #{PROT} at t~{ts[cross]:.2f}"
        if cross is not None
        else "no crossing on this path",
    )
    verdict(fig, "interpolation is a feature handover, not a fade")
    save(fig, "03-the-journey.png")


def main() -> None:
    tr = json.loads((SAE / "trace.json").read_text())
    fig01(tr)
    fig02(tr)
    fig03(tr)
    slim = {k: v for k, v in tr.items() if k != "vector"}
    (OUTDIR / "trace.json").write_text(json.dumps(slim, indent=1))
    print("copied trace.json sidecar (vector dropped)")


if __name__ == "__main__":
    main()
