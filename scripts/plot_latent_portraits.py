"""Section 49 — latent portraits: a pass that was an artifact, on camera.

Figure 01: the collapse — the identifiability gate before and after deduping
exemplars by note, one shared axis. Figure 02: the mechanism — one latent's
exemplar strip raw vs deduped. Figure 03: the passport, rebuilt without the
claim the gate refused (the face panel is a real exemplar, labeled as such).

    YTK_VISUAL_INDEX=off uv run --with torch --with matplotlib \
        python scripts/plot_latent_portraits.py
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
    GOLD,
    MUTED,
    RED,
    TEXT,
    figure,
    frame_panels,
    panel_title,
    semantic_rose,
    style_axes,
    vector_image,
    verdict,
)

REPO = Path(__file__).resolve().parents[1]
SAE = REPO / "experiments" / "sae_qwen"
OUTDIR = REPO / "docs" / "assets" / "49-latent-portraits"
VAULT = Path.home() / (
    "Library/Mobile Documents/iCloud~md~obsidian/Documents/Vault/second-brain/sources"
)
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


def fig01(z, res) -> None:
    fig, top = figure(
        13.4,
        7.4,
        1,
        "the collapse",
        "The gate passed, the owner saw repeated thumbnails, the pass was the bug",
        f"same measurement twice | top: as first run (segments repeat their video's thumbnail; "
        f"mean duplication 40% of top-24) | bottom: one exemplar per note | AUC "
        f"{res['contaminated_auc']:.2f} -> {res['auc']:.2f} against the registered "
        f"{0.80:.2f} | n={res['n_qualifying']} | {SHA}",
    )
    gs = fig.add_gridspec(2, 1, left=0.07, right=0.96, top=top, bottom=0.11, hspace=0.34)
    bins = np.linspace(-0.4, 1.0, 50)
    panels = [
        (
            "contaminated: both halves often hold the same image",
            z["same_raw"],
            z["cross_raw"],
            res["contaminated_auc"],
        ),
        ("deduplicated: the identity evaporates", z["same"], z["cross"], res["auc"]),
    ]
    for k, (title, same, cross, a) in enumerate(panels):
        ax = fig.add_subplot(gs[k, 0])
        ax.hist(cross, bins=bins, density=True, color=DIM, label="different latents")
        ax.hist(
            same,
            bins=bins,
            density=True,
            histtype="step",
            linewidth=2.0,
            color=GOLD,
            label="same latent, disjoint halves",
        )
        ax.axvline(float(np.median(same)), color=GOLD, lw=1.2, ls="--")
        style_axes(ax)
        panel_title(ax, f"{title} — AUC {a:.2f}", width=74)
        if k == 0:
            leg = ax.legend(frameon=False, fontsize=8.5)
            for t_ in leg.get_texts():
                t_.set_color(MUTED)
            ax.set_xticklabels([])
        else:
            ax.set_xlabel("pixel correlation between two portraits")
    verdict(fig, "FAIL at 0.43 — the 0.97 was duplicate thumbnails; the fifth registered loss")
    save(fig, "01-the-collapse.png")


def fig02(res) -> None:
    """One latent's evidence, raw vs deduped: the mechanism as pictures."""
    rows = [json.loads(x) for x in (SAE / "data" / "rows.jsonl").read_text().splitlines()]
    z = np.load(SAE / "data" / "acts_final_d2048_k32_s0.npz")
    idx, val = z["idx"], z["val"]
    per = []
    r_, j_ = np.nonzero((idx == 272) & (val > 0))
    for r, j in zip(r_, j_):
        per.append((float(val[r, j]), int(r)))
    per.sort(reverse=True)

    def thumb(r):
        row = rows[r]
        if row["kind"] in ("video", "segment"):
            vid = row["id"] if row["kind"] == "video" else row["id"].rsplit("_", 1)[0]
            p = VAULT / "youtube" / "thumbnails" / f"{vid}-thumb.jpg"
            if p.exists():
                im = Image.open(p).convert("RGB")
                side = min(im.size)
                left, up = (im.width - side) // 2, (im.height - side) // 2
                return (
                    np.asarray(
                        im.crop((left, up, left + side, up + side)).resize((128, 128)), float
                    )
                    / 255.0
                )
        return None

    def vid_of(r):
        row = rows[r]
        return row["id"].rsplit("_", 1)[0] if row["kind"] == "segment" else row["id"]

    raw, seen, dedup = [], set(), []
    for a, r in per:
        img = thumb(r)
        if img is None:
            continue
        if len(raw) < 8:
            raw.append(img)
        if vid_of(r) not in seen and len(dedup) < 8:
            seen.add(vid_of(r))
            dedup.append(img)
        if len(raw) == 8 and len(dedup) == 8:
            break

    fig, top = figure(
        13.4,
        6.2,
        2,
        "the mechanism",
        "Latent #272's top evidence, before and after one-per-note",
        "top row: top-8 exemplars by activation — segments of one video repeat its thumbnail | "
        f"bottom row: top-8 with one exemplar per note | {SHA}",
    )
    gs = fig.add_gridspec(
        2, 8, left=0.04, right=0.965, top=top, bottom=0.07, wspace=0.08, hspace=0.22
    )
    for k, strip in enumerate((raw, dedup)):
        for i, img in enumerate(strip):
            ax = fig.add_subplot(gs[k, i])
            ax.imshow(img)
            ax.set_xticks([])
            ax.set_yticks([])
            for s in ax.spines.values():
                s.set_color(RED if k == 0 else DIM)
    verdict(fig, "the gate scored the top row — agreement between copies of one image")
    save(fig, "02-the-mechanism.png")


def fig03(z, res, feats) -> None:
    tr = json.loads((SAE / "trace.json").read_text())
    az = np.load(SAE / "data" / "semantic_axes.npz", allow_pickle=True)
    A, kept = az["axes"], [str(s) for s in az["names"]]
    pole_a = {"scroll-sit": "SCROLL", "mine-world": "MINE", "fresh-settled": "FRESH"}
    pole_b = {"scroll-sit": "SIT", "mine-world": "WORLD", "fresh-settled": "SETTLED"}
    poles = [pole_a[k] for k in kept] + [pole_b[k] for k in kept]
    v = np.asarray(tr["vector"], np.float32)
    code = np.zeros(2048, np.float32)
    for f, a in tr["code"].items():
        code[int(f)] = a

    fig, top = figure(
        13.4,
        6.8,
        3,
        "the passport",
        "One note's papers — only stamps that survived their gates",
        f"'{tr['title']}' | face: #{PROT}'s most central real exemplar (a thumbnail, not a "
        f"composite — the composite gate FAILED, fig 01) | rose: 48's surviving axes | code: "
        f"rung 1 | {tr['named_mass_frac']:.0%} of code mass named | {SHA}",
    )
    gs = fig.add_gridspec(
        1,
        4,
        width_ratios=[1.1, 1, 0.72, 1.15],
        left=0.045,
        right=0.965,
        top=top,
        bottom=0.09,
        wspace=0.2,
    )

    ax = fig.add_subplot(gs[0, 0])
    ax.imshow(z["medoids"][feats[PROT]], interpolation="bilinear")
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color(CYAN)
        s.set_linewidth(1.6)
    panel_title(ax, "most central exemplar (real)", width=28)

    ax = fig.add_subplot(gs[0, 1])
    semantic_rose(ax, (v / np.linalg.norm(v)) @ A.T, poles, color=CYAN)
    panel_title(ax, "compass", width=20)

    ax = fig.add_subplot(gs[0, 2])
    vector_image(ax, code, annotate=[(PROT, "#1597")])
    panel_title(ax, "code", width=16)

    ax = fig.add_subplot(gs[0, 3])
    ax.axis("off")
    top3 = tr["top_latents"][:3]
    shared = {n["title"] for n in tr["neighbors_qwen"]} & {n["title"] for n in tr["neighbors_sae"]}
    txt = (
        "\n".join(f"#{t['latent']} {(t['name'] or '')[:26]}  {t['act']:.2f}" for t in top3)
        + f"\n\ncell {','.join(map(str, tr['atlas_cell']['cell']))} (10-NN est.)"
        + f"\nlens-shared neighbors {tr['neighbor_overlap']}/5"
    )
    ax.text(
        0.0,
        0.95,
        "speaks / resides / keeps company",
        color=TEXT,
        fontsize=9,
        va="top",
        weight="bold",
    )
    ax.text(0.0, 0.82, txt, color=MUTED, fontsize=8, va="top", linespacing=1.7)
    ax.text(
        0.0,
        0.30,
        "\n".join(f"* {t[:34]}" for t in sorted(shared)),
        color=MUTED,
        fontsize=7.6,
        va="top",
        linespacing=1.7,
    )
    verdict(fig, "the face is evidence, not a derivation — that is all the gate allows")
    save(fig, "03-the-passport.png")


def main() -> None:
    z = np.load(SAE / "data" / "portraits.npz")
    res = json.loads((SAE / "portraits.json").read_text())
    feats = {int(f): k for k, f in enumerate(z["feats"])}
    fig01(z, res)
    fig02(res)
    fig03(z, res, feats)
    slim = {k: v for k, v in res.items() if k != "latents"}
    (OUTDIR / "portraits.json").write_text(json.dumps(slim, indent=1))
    for stale in ("01-the-wall.png", "02-the-gate.png"):
        p = OUTDIR / stale
        if p.exists():
            p.unlink()
            print(f"removed {stale}")
    print("copied portraits.json sidecar")


if __name__ == "__main__":
    main()
