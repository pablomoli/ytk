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
    panel_title,
    saturated_magma,
    style_axes,
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


def cohesion(V: np.ndarray) -> float:
    """Mean pairwise cosine of a set of unit vectors — how much one topic it is."""
    S = V @ V.T
    n = len(V)
    return float((S.sum() - np.trace(S)) / (n * (n - 1)))


def fig02(head: list[dict], rng: np.random.Generator) -> dict:
    X = np.load(SAE / "data" / "vectors.npz")["X"]
    rows = [json.loads(x) for x in (SAE / "data" / "rows.jsonl").read_text().splitlines()]
    id2row = {}
    for i, r in enumerate(rows):
        id2row.setdefault(r["id"], i)

    named = {t["feature"]: t for t in head}
    sets = {}
    for t in head:
        idxs = [id2row[e["id"]] for e in t["exemplars"][:8] if e["id"] in id2row]
        if len(idxs) >= 4:
            sets[t["feature"]] = idxs
    real = {f: cohesion(X[idxs]) for f, idxs in sets.items()}
    pool = sorted({i for idxs in sets.values() for i in idxs})
    null = np.array([cohesion(X[rng.choice(pool, 8, replace=False)]) for _ in range(500)])

    head_vals = np.array([v for f, v in real.items() if f != PROT])
    overlap = int((head_vals <= null.max()).sum())
    fig, top = figure(
        16.5,
        7.2,
        2,
        "atlas rung 2 — coherence null",
        "Do a latent's exemplars actually belong together? Measured, against chance",
        f"cohesion = mean pairwise cosine of a latent's top-8 exemplar vectors (Qwen space) | "
        f"null (grey) = 500 sets of 8 drawn at random from the same exemplar pool | "
        f"real median {np.median(head_vals):.3f} vs null median {np.median(null):.3f} | {SHA}",
    )
    gs = fig.add_gridspec(
        1, 2, width_ratios=[1.45, 1], left=0.055, right=0.975, top=top, bottom=0.11, wspace=0.16
    )

    # Panel A: the geometry — two distributions on one axis
    ax = fig.add_subplot(gs[0, 0])
    lo = min(float(null.min()), float(head_vals.min())) - 0.02
    hi = max(float(null.max()), float(head_vals.max())) + 0.02
    bins = np.linspace(lo, hi, 40)
    ax.hist(null, bins=bins, density=True, color=DIM, label="shuffled sets (null)")
    ax.hist(
        head_vals,
        bins=bins,
        density=True,
        histtype="step",
        linewidth=2.0,
        color=GOLD,
        label="each head latent's own exemplars",
    )
    pv = real.get(PROT)
    if pv is not None:
        ax.axvline(pv, color=CYAN, linewidth=1.6)
        ax.text(
            pv + 0.004,
            ax.get_ylim()[1] * 0.92,
            f"#{PROT}  {pv:.3f}",
            color=CYAN,
            fontsize=8.5,
        )
    leg = ax.legend(frameon=False, fontsize=8.5, loc="upper left")
    for t_ in leg.get_texts():
        t_.set_color(MUTED)
    style_axes(ax)
    ax.set_xlabel("exemplar-set cohesion (mean pairwise cosine)")
    ax.set_ylabel("density")
    panel_title(ax, f"{overlap}/{len(head_vals)} head latents overlap the null's reach")

    # Panel B: one worked example — what a cohesion number reads like as text
    gsr = gs[0, 1].subgridspec(2, 1, hspace=0.24)
    t = named[PROT]
    ax = fig.add_subplot(gsr[0])
    text_tile(ax, f"#{PROT} {t.get('name') or ''}  ·  {pv:.3f}", t["exemplars"], CYAN)
    pool_ex = [e for tt in head for e in tt["exemplars"]]
    sh = [pool_ex[i] for i in rng.choice(len(pool_ex), 4, replace=False)]
    sh_idxs = [id2row[e["id"]] for e in sh if e["id"] in id2row]
    ax = fig.add_subplot(gsr[1])
    text_tile(ax, f"a null draw  ·  {cohesion(X[sh_idxs]):.3f}", sh, MUTED)
    verdict(
        fig,
        f"median cohesion {np.median(head_vals):.2f} vs chance {np.median(null):.2f} — "
        "the names have something to name",
    )
    frame_panels(fig)
    out = OUTDIR / "02-coherence-null.png"
    fig.savefig(out, dpi=DPI, facecolor=BG)
    print(f"wrote {out.relative_to(REPO)}  ({out.stat().st_size // 1024}KB)")
    plt.close(fig)
    return {
        "real_median": round(float(np.median(head_vals)), 4),
        "null_median": round(float(np.median(null)), 4),
        "null_max": round(float(null.max()), 4),
        "overlap_null_reach": overlap,
        "protagonist_cohesion": round(pv, 4) if pv is not None else None,
    }


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
    coh = fig02(head + prot, rng)

    sidecar = {
        "commit": SHA,
        "mosaic": {
            "cells": stats["cells"],
            "with_image": stats["img"],
            "img_frac": round(stats["img"] / stats["cells"], 4),
        },
        "badges": {"ge_08": stats["badge_ge_08"], "ge_05": stats["badge_ge_05"]},
        "coherence": coh,
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
