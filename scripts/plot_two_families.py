#!/usr/bin/env python
"""37 — one note, two families (remix of 22 through the individual lens).

Section 22 compared the Qwen and Gemma-SAE partitions in aggregate (ARI,
triplets, purity) and found one space sorts by topic, the other by sound.
Here we pick the note the two spaces disagree about hardest and meet both
of its families: its Qwen neighbours, its fingerprint neighbours, and the
named feature each fingerprint neighbour shares with it.

    uv run --with matplotlib python scripts/plot_two_families.py
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
from plot_two_lenses import align, gemma_space

ASSETS = Path(__file__).resolve().parents[1] / "docs" / "assets"
OUTDIR = ASSETS / "37-two-families"
K = 10


def save(fig, name: str) -> None:
    frame_panels(fig)
    OUTDIR.mkdir(exist_ok=True)
    out = OUTDIR / name
    fig.savefig(out, dpi=DPI, facecolor=BG)
    print(f"wrote {out.name}  ({out.stat().st_size // 1024}KB)")
    plt.close(fig)


def short(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 2].rstrip() + ".."


def neighbours(M: np.ndarray, i: int, k: int = K) -> list[int]:
    sims = M @ M[i]
    sims[i] = -np.inf
    return list(np.argsort(-sims)[:k])


def main() -> None:
    F, Q, ids, names, srcs, labels, snapshot = align()
    n = len(names)
    Qn = Q / np.linalg.norm(Q, axis=1, keepdims=True)
    G, L = gemma_space(F)
    feat_names = json.loads((ASSETS / "22-two-lenses" / "feature-names.json").read_text())

    # overlap of the two neighbourhoods, for every note
    overlaps = np.array([len(set(neighbours(Qn, i)) & set(neighbours(G, i))) for i in range(n)])
    # the boundary note: zero overlap, deterministic tiebreak by strongest
    # in-family cohesion (mean cosine to its Qwen top-5), titles preferred
    cands = [
        i for i in range(n) if overlaps[i] == 0 and " " in names[i] and "-2026" not in names[i]
    ]
    coh = {i: float(np.mean(sorted(Qn @ Qn[i])[-6:-1])) for i in cands}
    note = max(cands, key=lambda i: coh[i])

    qn = neighbours(Qn, note, 5)
    gn = neighbours(G, note, 5)

    def shared_feature(j: int) -> str:
        both = np.minimum(L[note], L[j])
        for f in np.argsort(-both):
            nm = feat_names.get(str(int(f)))
            if nm:
                return nm
        return "?"

    meta = (
        f'the note: "{short(names[note], 48)}"  ·  theme: {short(labels[note], 24)}  ·  '
        f"aligned corpus n={n}  ·  top-10 overlap between its two neighbourhoods: 0 (corpus median {int(np.median(overlaps))})"
    )
    fig, top = figure(16.5, 8.8, 1, "two families", "One note, two families", meta)

    y_top = top - 0.10
    cmap = saturated_magma()
    W, H = 16.5, 8.8

    # the note's two portraits, centre column
    xq, xg = 0.415, 0.545
    wq = 0.085
    hq = wq * W / H
    aq = fig.add_axes([xq, y_top - hq, wq, hq])
    aq.imshow(
        Q[note].reshape(32, 32),
        cmap=cmap,
        vmin=-np.abs(Q[note]).max(),
        vmax=np.abs(Q[note]).max(),
        interpolation="nearest",
    )
    panel_title(aq, "its Qwen vector", 20)
    ag = fig.add_axes([xg, y_top - hq, wq, hq])
    fp = punch(np.sqrt(F[note].reshape(128, 128)) / np.sqrt(F[note].max()))
    ag.imshow(fp, cmap=cmap, vmin=0, vmax=1, interpolation="nearest")
    panel_title(ag, "its SAE fingerprint", 20)
    for ax in (aq, ag):
        ax.set_xticks([])
        ax.set_yticks([])
        for s in ax.spines.values():
            s.set_color(FRAME)

    fig.text(
        0.5, y_top + 0.045, f'"{short(names[note], 60)}"', color=TEXT, fontsize=11, ha="center"
    )

    # left family: Qwen neighbours (topic)
    xl = MARGIN
    fig.text(xl, y_top, "the Qwen family — notes about the same thing", color=GOLD, fontsize=9.5)
    for r, j in enumerate(qn):
        y = y_top - 0.05 - r * 0.062
        same = labels[j] == labels[note]
        fig.text(xl, y, short(names[j], 40), color=TEXT, fontsize=8.2)
        fig.text(
            xl,
            y - 0.026,
            f"theme: {short(labels[j], 30)}" + ("  = the note's" if same else ""),
            color=GOLD if same else MUTED,
            fontsize=6.8,
        )

    # right family: fingerprint neighbours (register)
    xr = 0.665
    fig.text(xr, y_top, "the SAE family — notes that sound the same", color=BLUE, fontsize=9.5)
    for r, j in enumerate(gn):
        y = y_top - 0.05 - r * 0.062
        fig.text(xr, y, short(names[j], 40), color=TEXT, fontsize=8.2)
        fig.text(
            xr,
            y - 0.026,
            f"shares: {short(shared_feature(j), 44)}",
            color=BLUE,
            fontsize=6.8,
        )

    # population panel: overlap distribution
    axh = fig.add_axes([MARGIN, 0.09, 0.38, 0.20])
    style_axes(axh)
    axh.hist(overlaps, bins=np.arange(-0.5, overlaps.max() + 1.5), color=DIM, lw=0)
    axh.axvline(0, color=RED, lw=1.6)
    axh.set_xlabel("shared notes between the two top-10 neighbourhoods", color=MUTED, fontsize=8)
    axh.set_yticks([])
    panel_title(axh, "every note's two families, compared (red: this note)", 60)

    fig.text(
        MARGIN + 0.46,
        0.27,
        "the same note, embedded twice. the Qwen space files it with notes\n"
        "about its topic; the fingerprint space files it with notes that share\n"
        "its named vocabulary features — its register. the two top-10 lists\n"
        "share zero notes, and that is not an outlier: the corpus median\n"
        f"overlap is {int(np.median(overlaps))} of 10. section 22 measured this as ARI and triplets;\n"
        "this is what it looks like when it happens to one note you can read.",
        color=MUTED,
        fontsize=9.5,
        linespacing=1.7,
        va="top",
    )

    verdict(
        fig,
        f"zero shared neighbours; corpus median {int(np.median(overlaps))}/10 — topic and voice file the same note apart",
    )
    save(fig, "01-one-note-two-families.png")
    print(f"note: {names[note]!r}  theme={labels[note]!r}  overlap median={np.median(overlaps)}")


if __name__ == "__main__":
    main()
