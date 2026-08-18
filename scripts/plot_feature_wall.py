"""Section 43 — atlas rung 2 (#183): the static feature wall.

Figure 01: the top-100 head as a wall — tile = decoder-row image (1024d ->
32x32) + top-9 exemplar mosaic, [T] provenance fallback for imageless notes,
per-tile seed-agreement badge. Figure 02: the coherence null — the same tiles
in TEXT mode against shuffled exemplar assignment, protagonist outlined.

Needs torch (decoder rows) and the vault (thumbnails):

    YTK_VISUAL_INDEX=off uv run --with torch --with matplotlib \
        python scripts/plot_feature_wall.py
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
from PIL import Image

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
    RED,
    TEXT,
    figure,
    frame_panels,
    saturated_magma,
    vector_image,
    verdict,
)

REPO = Path(__file__).resolve().parents[1]
SAE = REPO / "experiments" / "sae_qwen"
OUTDIR = REPO / "docs" / "assets" / "43-feature-wall"
VAULT = Path.home() / (
    "Library/Mobile Documents/iCloud~md~obsidian/Documents/Vault/second-brain/sources"
)
CELL = 56  # mosaic cell pixels; 3x3 cells per tile
PROT = 1597

SHA = subprocess.run(
    ["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], capture_output=True, text=True
).stdout.strip()


def thumb_path(e: dict) -> Path | None:
    if e["kind"] in ("video", "segment"):
        vid = e["id"] if e["kind"] == "video" else e["id"].rsplit("_", 1)[0]
        return VAULT / "youtube" / "thumbnails" / f"{vid}-thumb.jpg"
    if e["source"] in ("instagram", "tiktok"):
        slug = e["id"].split(f"note_sources_{e['source']}_", 1)[-1]
        code = slug.rsplit("-", 1)[-1]
        return VAULT / e["source"] / "thumbnails" / f"{code}-thumb.jpg"
    return None


_MAGMA_T = None


def t_cell(source: str) -> np.ndarray:
    """[T] fallback cell: provenance initial on dark magma."""
    global _MAGMA_T
    if _MAGMA_T is None:
        ramp = saturated_magma()(np.linspace(0.04, 0.22, CELL))[:, :3]
        _MAGMA_T = np.repeat(ramp[:, None, :], CELL, axis=1)
    return _MAGMA_T.copy(), source[:1].upper()


_thumbs: dict[Path, np.ndarray | None] = {}


def load_thumb(p: Path | None) -> np.ndarray | None:
    if p is None:
        return None
    if p not in _thumbs:
        try:
            im = Image.open(p).convert("RGB")
            side = min(im.size)
            left = (im.width - side) // 2
            up = (im.height - side) // 2
            im = im.crop((left, up, left + side, up + side)).resize((CELL, CELL))
            _thumbs[p] = np.asarray(im, float) / 255.0
        except Exception:
            _thumbs[p] = None
    return _thumbs[p]


def mosaic(exemplars: list[dict]) -> tuple[np.ndarray, list, int]:
    """3x3 composite; returns (rgb array, [T]-glyph positions, n_img)."""
    gap = 2
    side = 3 * CELL + 2 * gap
    out = np.zeros((side, side, 3))
    out[:] = np.array([0.03, 0.03, 0.04])
    glyphs, n_img = [], 0
    for i in range(9):
        r, c = divmod(i, 3)
        y, x = r * (CELL + gap), c * (CELL + gap)
        if i < len(exemplars):
            img = load_thumb(thumb_path(exemplars[i]))
            if img is not None:
                out[y : y + CELL, x : x + CELL] = img
                n_img += 1
            else:
                cell, ch = t_cell(exemplars[i]["source"])
                out[y : y + CELL, x : x + CELL] = cell
                glyphs.append((x + CELL / 2, y + CELL / 2, ch))
    return out, glyphs, n_img


def badge_color(b: float) -> str:
    return GOLD if b >= 0.8 else (MUTED if b >= 0.5 else RED)


def fig01(head: list[dict], W_dec: np.ndarray, badges: list[float]) -> dict:
    fig, top = figure(
        21.0,
        14.2,
        1,
        "atlas rung 2 — the feature wall",
        "The top-100 head, each latent shown twice: its direction and its evidence",
        f"tile = decoder row 1024d -> 32x32 + top-9 exemplar mosaic ([T] = imageless, letter = "
        f"provenance: Vault/Web/Instagram/Tiktok) | badge = min max-cos vs seeds 1,2 "
        f"(gold >= 0.8, grey >= 0.5, red below) | ranked by firing frequency | {SHA}",
    )
    gs = fig.add_gridspec(
        10, 20, left=0.022, right=0.985, top=top, bottom=0.045, wspace=0.10, hspace=0.42
    )
    stats = {"img": 0, "cells": 0, "badge_ge_08": 0, "badge_ge_05": 0}
    for k, t in enumerate(head):
        r, c = divmod(k, 10)
        f = t["feature"]
        b = badges[f]
        axd = fig.add_subplot(gs[r, 2 * c])
        vector_image(axd, W_dec[f])
        axm = fig.add_subplot(gs[r, 2 * c + 1])
        m, glyphs, n_img = mosaic(t["exemplars"])
        axm.imshow(m, interpolation="nearest")
        for x, y, ch in glyphs:
            axm.text(x, y, ch, color=MUTED, fontsize=5.5, ha="center", va="center")
        axm.set_xticks([])
        axm.set_yticks([])
        for spine in axm.spines.values():
            spine.set_color(FRAME)
        name = t.get("name") or f"#{f}"
        axd.set_title(
            f"#{f} {name[:24]}",
            color=TEXT,
            fontsize=5.6,
            loc="left",
            pad=2.2,
        )
        axm.set_title(
            f"{t['freq'] * 100:.1f}%  ·  {b:.2f}",
            color=badge_color(b),
            fontsize=5.4,
            loc="right",
            pad=2.2,
        )
        stats["img"] += n_img
        stats["cells"] += min(len(t["exemplars"]), 9)
        stats["badge_ge_08"] += b >= 0.8
        stats["badge_ge_05"] += b >= 0.5
    verdict(
        fig,
        f"{stats['badge_ge_08']}/100 head latents survive retraining at cos 0.8, "
        f"{stats['badge_ge_05']}/100 at 0.5 — corpus-wide: 7% and 20%",
    )
    frame_panels(fig, pad=0.004)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    out = OUTDIR / "01-wall.png"
    fig.savefig(out, dpi=DPI, facecolor=BG)
    print(f"wrote {out.relative_to(REPO)}  ({out.stat().st_size // 1024}KB)")
    plt.close(fig)
    return stats


def text_tile(ax, name: str, exemplars: list[dict], color: str) -> None:
    ax.axis("off")
    ax.set_facecolor(PANEL)
    lines = [f"{e['title'] or e['text'][:34]}"[:34] for e in exemplars[:4]]
    ax.text(0.03, 0.96, name[:26], color=color, fontsize=7.6, va="top", weight="bold")
    ax.text(
        0.03,
        0.72,
        "\n".join(lines),
        color=MUTED,
        fontsize=6.8,
        va="top",
        linespacing=1.55,
    )


def fig02(head: list[dict], rng: np.random.Generator) -> None:
    named = {t["feature"]: t for t in head}
    picks = [PROT] + [t["feature"] for t in head[:5]]
    pool = [e for t in head for e in t["exemplars"]]
    fig, top = figure(
        16.5,
        7.0,
        2,
        "atlas rung 2 — coherence null",
        "Real exemplars against shuffled assignment: coherence is visible, not asserted",
        "top row: each latent's own top-4 exemplars (TEXT mode) | bottom row: 4 exemplars drawn "
        f"at random from the head's pooled exemplar set, same layout | protagonist #{PROT} "
        f"outlined | {SHA}",
    )
    gs = fig.add_gridspec(
        2, 6, left=0.03, right=0.98, top=top, bottom=0.10, wspace=0.10, hspace=0.30
    )
    for c, f in enumerate(picks):
        t = named[f]
        color = CYAN if f == PROT else TEXT
        ax = fig.add_subplot(gs[0, c])
        text_tile(ax, f"#{f} {t.get('name') or ''}", t["exemplars"], color)
        if f == PROT:
            from matplotlib.patches import Rectangle

            ax.add_patch(
                Rectangle(
                    (0.004, 0.004),
                    0.992,
                    0.992,
                    transform=ax.transAxes,
                    facecolor="none",
                    edgecolor=CYAN,
                    linewidth=1.6,
                    clip_on=False,
                )
            )
        sh = [pool[i] for i in rng.choice(len(pool), 4, replace=False)]
        ax = fig.add_subplot(gs[1, c])
        text_tile(ax, f"#{f} shuffled", sh, DIM)
    fig.text(
        0.03,
        0.055,
        "bottom row = the null: what the wall would look like if names were decoration",
        color=MUTED,
        fontsize=9,
    )
    verdict(fig, "every real tile reads as one topic; every shuffled tile reads as the corpus")
    frame_panels(fig)
    out = OUTDIR / "02-coherence-null.png"
    fig.savefig(out, dpi=DPI, facecolor=BG)
    print(f"wrote {out.relative_to(REPO)}  ({out.stat().st_size // 1024}KB)")
    plt.close(fig)


def main() -> None:
    import torch

    features = json.loads((SAE / "features.json").read_text())
    table = features["features"]
    head = sorted(table, key=lambda t: -t["freq"])[:100]
    prot = [t for t in table if t["feature"] == PROT]
    agree = json.loads((SAE / "seed_agreement.json").read_text())["badge"]

    blob = torch.load(SAE / "checkpoints" / "final_d2048_k32_s0.pt", map_location="cpu")
    W = blob["state"]["W_dec"].numpy()
    W = W / np.maximum(np.linalg.norm(W, axis=1, keepdims=True), 1e-9)

    stats = fig01(head, W, agree)
    rng = np.random.default_rng(43)
    fig02(head + prot, rng)

    sidecar = {
        "commit": SHA,
        "mosaic": {
            "cells": stats["cells"],
            "with_image": stats["img"],
            "img_frac": round(stats["img"] / stats["cells"], 4),
        },
        "badges": {"ge_08": stats["badge_ge_08"], "ge_05": stats["badge_ge_05"]},
        "protagonist_badge": agree[PROT],
        "tiles": [
            {
                "feature": t["feature"],
                "name": t.get("name"),
                "freq": round(t["freq"], 5),
                "badge": agree[t["feature"]],
            }
            for t in head
        ],
    }
    (OUTDIR / "wall.json").write_text(json.dumps(sidecar, indent=1))
    print("badges >=0.8:", stats["badge_ge_08"], " >=0.5:", stats["badge_ge_05"])
    print("mosaic img frac:", sidecar["mosaic"]["img_frac"], " protagonist badge:", agree[PROT])


if __name__ == "__main__":
    main()
