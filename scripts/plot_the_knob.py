#!/usr/bin/env python
"""35 — the knob: causal steering on the production space (remix of 18/21/24).

Section 34 rendered the objects; this section turns the dials. The native
top-k SAE from 24 (checkpoints survived in experiments/sae_qwen/) makes the
video's intervention loop runnable on retrieval itself: encode a real gate
query, clamp one named latent, decode, retrieve, compare.

01  the knob        — clamp latent 977 into a philosophy query, dose-response
02  not the concept — ablate the same latent from an EpicMap query: nothing
03  opposite knobs  — 21's antipodal decoder pairs, finally visible as images

    uv run --with matplotlib --with torch python scripts/plot_the_knob.py [1|2|3]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plot_assets import (
    BG,
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
    saturated_magma,
    style_axes,
    verdict,
)

REPO = Path(__file__).resolve().parents[1]
ASSETS = REPO / "docs" / "assets"
OUTDIR = ASSETS / "35-the-knob"
SAE_DIR = REPO / "experiments" / "sae_qwen"
LAT = 977  # "EpicMap field service SaaS platform", freq 0.096
MAXA = 0.504  # latent 977's observed max activation over the 16,483 vectors
Q_UP = 80  # "philosophical question about how we comprehend images ..."
Q_DOWN = 105  # "when we debated whether EpicMap needed in-browser PDF viewing ..."


def save(fig, name: str) -> None:
    frame_panels(fig)
    OUTDIR.mkdir(exist_ok=True)
    out = OUTDIR / name
    fig.savefig(out, dpi=DPI, facecolor=BG)
    print(f"wrote {out.name}  ({out.stat().st_size // 1024}KB)")
    plt.close(fig)


def short(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 2].rstrip() + ".."


def pretty(row: dict) -> str:
    if row.get("title"):
        return row["title"]
    nk = row["note_key"]
    nk = re.sub(r"^mem::(note_|memory_)?", "memory: ", nk)
    return nk.replace("_", " ")


def sq_axes(fig, x, y_top, w, aspect=1.0):
    W, H = fig.get_figwidth(), fig.get_figheight()
    h = w * W / H * aspect
    ax = fig.add_axes([x, y_top - h, w, h])
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color(FRAME)
    return ax, h


def load():
    import torch

    sys.path.insert(0, str(SAE_DIR))
    import train_sae as T

    D = SAE_DIR / "data"
    X = np.load(D / "vectors.npz")["X"].astype(np.float32)
    rows = [json.loads(line) for line in open(D / "rows.jsonl")]
    q = np.load(D / "queries.npz", allow_pickle=True)
    feats = {
        f["feature"]: f.get("name", "?")
        for f in json.loads((SAE_DIR / "features.json").read_text())["features"]
    }
    m = T.TopKSAE(1024, 2048, 32)
    blob = torch.load(
        SAE_DIR / "checkpoints" / "final_d2048_k32_s0.pt", map_location="cpu", weights_only=False
    )
    m.load_state_dict(blob["state"])
    m.eval()
    epic = np.array(
        [
            bool(
                re.search(
                    r"epicmap|epic map", (r.get("title") or "") + " " + r["note_key"], re.IGNORECASE
                )
            )
            for r in rows
        ]
    )
    return m, X, rows, q, feats, epic


class Rig:
    def __init__(self):
        import torch

        self.torch = torch
        self.m, self.X, self.rows, self.q, self.feats, self.epic = load()
        self.Xn = self.X / np.linalg.norm(self.X, axis=1, keepdims=True)

    def code(self, v: np.ndarray):
        t = self.torch
        with t.no_grad():
            pre = t.relu(self.m.enc(t.from_numpy(v) - self.m.b_pre))
            vals, idx = pre.topk(32, dim=-1)
            z = t.zeros(2048)
            z.scatter_(-1, idx, vals)
        return z, idx.tolist()

    def decode(self, z) -> np.ndarray:
        with self.torch.no_grad():
            return self.m.decode(z).numpy()

    def top_notes(self, v: np.ndarray, k: int = 10):
        sims = self.Xn @ (v / np.linalg.norm(v))
        order = np.argsort(-sims)
        seen, out = set(), []
        for i in order:
            nk = self.rows[i]["note_key"]
            if nk in seen:
                continue
            seen.add(nk)
            out.append((i, float(sims[i])))
            if len(out) == k:
                break
        return out

    def epic_share(self, v: np.ndarray, k: int = 10) -> float:
        return sum(self.epic[i] for i, _ in self.top_notes(v, k)) / k


def code_strip(z) -> np.ndarray:
    """The 2048-latent code as a 16x128 image; sparsity visible as darkness."""
    return z.numpy().reshape(16, 128)


def draw_list(fig, x, y, items, rig, width=34, gold_epic=True):
    for r, (i, s) in enumerate(items):
        row = rig.rows[i]
        col = GOLD if (gold_epic and rig.epic[i]) else TEXT
        title = short(pretty(row), width)
        fig.text(x, y - r * 0.046, f"{s:.3f}", color=MUTED, fontsize=7, family="monospace")
        fig.text(x + 0.035, y - r * 0.046, title, color=col, fontsize=8)


# ---------------------------------------------------------------- figure 01


def fig01(rig):
    qv = rig.q["Q"][Q_UP].astype(np.float32)
    qtext = str(rig.q["query"][Q_UP])
    z0, _ = rig.code(qv)
    assert float(z0[LAT]) == 0.0

    cs = np.linspace(0, 20, 41)
    curve = (
        [rig.epic_share(rig.decode(rig._clamp(z0, c * MAXA))) for c in cs]
        if hasattr(rig, "_clamp")
        else None
    )
    # inline clamp helper (kept local so the loop above reads plainly)

    def clamp(c):
        z = z0.clone()
        z[LAT] = c * MAXA
        return rig.decode(z)

    curve = [rig.epic_share(clamp(c)) for c in cs]

    meta = (
        f'query: "{short(qtext, 66)}"  ·  latent {LAT} "EpicMap field service SaaS platform", '
        f"natural act on this query 0.000, corpus max {MAXA}  ·  retrieval: cosine over 16,483 vectors, top-10 notes"
    )
    fig, top = figure(16.5, 8.4, 1, "the knob", "Steering a philosophy query into EpicMap", meta)

    y_top = top - 0.10
    a1, h1 = sq_axes(fig, MARGIN, y_top, 0.11)
    a1.imshow(
        qv.reshape(32, 32), cmap=saturated_magma(), vmin=-0.09, vmax=0.09, interpolation="nearest"
    )
    panel_title(a1, "the query vector", 22)

    a2, h2 = sq_axes(fig, MARGIN + 0.135, y_top, 0.20, aspect=16 / 128)
    a2.imshow(
        code_strip(z0),
        cmap=saturated_magma(),
        vmin=0,
        vmax=float(z0.max()),
        interpolation="nearest",
    )
    panel_title(a2, "its code: 32 of 2,048 latents on", 40)
    r, c = divmod(LAT, 128)
    a2.annotate(
        f"latent {LAT} is OFF — the clamp switches it on",
        xy=(c, r),
        xycoords="data",
        xytext=(0.02, -0.9),
        textcoords="axes fraction",
        color=GOLD,
        fontsize=7.5,
        annotation_clip=False,
        arrowprops={"arrowstyle": "->", "color": GOLD, "lw": 0.9},
    )

    Wrow = rig.m.W_dec[LAT].detach().numpy()
    a3, _ = sq_axes(fig, MARGIN + 0.365, y_top, 0.11)
    a3.imshow(
        Wrow.reshape(32, 32),
        cmap=saturated_magma(),
        vmin=-np.abs(Wrow).max(),
        vmax=np.abs(Wrow).max(),
        interpolation="nearest",
    )
    panel_title(a3, f"what the knob adds: decoder row {LAT}", 44)

    axc = fig.add_axes([MARGIN + 0.53, y_top - h1 - 0.06, 0.40, h1 + 0.06])
    style_axes(axc)
    axc.axvspan(0, 1, color=DIM, alpha=0.9, lw=0)
    axc.plot(cs, curve, color=GOLD, lw=2.0)
    axc.set_xlim(0, 20)
    axc.set_ylim(-0.03, 1.05)
    axc.set_xlabel(
        f"clamp value, in multiples of the latent's corpus max ({MAXA})", color=MUTED, fontsize=8
    )
    axc.set_ylabel("EpicMap share of top-10", color=MUTED, fontsize=8)
    panel_title(axc, "the dose-response readout  ·  grey band: the latent's natural range", 70)
    axc.annotate(
        "0.5x: a third of the results",
        xy=(0.5, 0.3),
        xytext=(2.2, 0.38),
        color=TEXT,
        fontsize=7.5,
        arrowprops={"arrowstyle": "->", "color": MUTED, "lw": 0.8},
    )
    axc.annotate(
        "2x: saturated — every stop is EpicMap,\nand the top result is one attractor note",
        xy=(2.0, 1.0),
        xytext=(5.5, 0.80),
        color=TEXT,
        fontsize=7.5,
        arrowprops={"arrowstyle": "->", "color": MUTED, "lw": 0.8},
    )

    y_l = y_top - h1 - 0.16
    fig.text(
        MARGIN,
        y_l + 0.045,
        "top-5 notes as the knob turns (gold = EpicMap):",
        color=TEXT,
        fontsize=9,
    )
    for j, c in enumerate([0.0, 0.5, 1.0, 2.0]):
        x = MARGIN + j * 0.24
        fig.text(x, y_l, f"clamp {c:g}x", color=GOLD if c else TEXT, fontsize=9.5)
        draw_list(fig, x, y_l - 0.045, rig.top_notes(clamp(c), 5), rig, width=30)

    verdict(
        fig,
        "one latent steers an unrelated query into EpicMap; past 2x the map has one destination",
    )
    save(fig, "01-the-knob.png")


# ---------------------------------------------------------------- figure 02


def fig02(rig):
    qv = rig.q["Q"][Q_DOWN].astype(np.float32)
    qtext = str(rig.q["query"][Q_DOWN])
    z0, idx = rig.code(qv)
    act = float(z0[LAT])

    fam = [
        i
        for i in idx
        if i in rig.feats
        and re.search(
            r"epicmap|parcel|survey|county|plat|field service", rig.feats[i], re.IGNORECASE
        )
    ]
    ladder = [
        ("baseline (roundtrip)", []),
        (f"kill {LAT} (its loudest latent)", [LAT]),
        (f"kill the EpicMap family ({len(fam)})", fam),
        ("kill the 8 loudest latents", sorted(idx, key=lambda i: -float(z0[i]))[:8]),
    ]

    def killed(kill):
        z = z0.clone()
        for i in kill:
            z[i] = 0.0
        return rig.decode(z)

    shares = [rig.epic_share(killed(kill)) for _, kill in ladder]

    meta = (
        f'query: "{short(qtext, 62)}"  ·  latent {LAT} fires at {act:.3f} — '
        f"the loudest of its 32  ·  same retrieval as figure 01"
    )
    fig, top = figure(16.5, 7.2, 2, "the knob", "The knob is not the concept", meta)

    y_top = top - 0.10
    a1, h1 = sq_axes(fig, MARGIN, y_top, 0.22, aspect=16 / 128)
    a1.imshow(
        code_strip(z0),
        cmap=saturated_magma(),
        vmin=0,
        vmax=float(z0.max()),
        interpolation="nearest",
    )
    panel_title(a1, "the EpicMap query's code — its loudest latent IS the knob", 52)
    r, c = divmod(LAT, 128)
    a1.annotate(
        f"latent {LAT} at {act:.3f}",
        xy=(c, r),
        xycoords="data",
        xytext=(0.03, -0.75),
        textcoords="axes fraction",
        color=GOLD,
        fontsize=7.5,
        annotation_clip=False,
        arrowprops={"arrowstyle": "->", "color": GOLD, "lw": 0.9},
    )

    axb = fig.add_axes([MARGIN + 0.30, y_top - 0.30, 0.28, 0.30])
    style_axes(axb)
    ys = np.arange(len(ladder))[::-1]
    axb.barh(ys, shares, height=0.55, color=[DIM, GOLD, GOLD, GOLD])
    axb.axvline(shares[0], color=RED, lw=1.2, ls="--")
    for y, (label, _), s in zip(ys, ladder, shares):
        axb.text(0.02, y, label, color=TEXT, fontsize=8.8, va="center")
        axb.text(s + 0.02, y, f"{s:.1f}", color=MUTED, fontsize=8, va="center")
    axb.set_yticks([])
    axb.set_xlim(0, 1.12)
    axb.set_xlabel("EpicMap share of top-10 after the cut", color=MUTED, fontsize=8)
    panel_title(axb, "the ablation ladder", 40)

    x0 = MARGIN + 0.655
    fig.text(
        x0,
        y_top,
        "top-5 after killing all 8 loudest latents — still EpicMap:",
        color=TEXT,
        fontsize=9,
    )
    draw_list(fig, x0, y_top - 0.05, rig.top_notes(killed(ladder[3][1]), 5), rig, width=38)

    fig.text(
        MARGIN,
        0.30,
        "figure 01 showed this latent dragging an unrelated query into EpicMap. here the same latent is the\n"
        "loudest thing in a genuine EpicMap query — and deleting it changes nothing. deleting its whole family\n"
        "changes nothing. the query's remaining code still points at the same territory: the concept is a\n"
        "direction the code redundantly encodes, not a single address you can remove. steering is asymmetric.",
        color=MUTED,
        fontsize=9.5,
        linespacing=1.7,
    )

    verdict(fig, "adding the concept takes one knob; removing it survives losing all eight loudest")
    save(fig, "02-not-the-concept.png")


# ---------------------------------------------------------------- figure 03


def fig03(rig):
    d = np.load(ASSETS / "21-geometry" / "cone-decoder.npz")
    W, idx = d["W"].astype(np.float32), d["indices"]
    cone_names = {
        f["index"]: f["name"].strip()
        for f in json.loads((ASSETS / "18-sae-fingerprints" / "cone-features.json").read_text())[
            "top"
        ]
    }
    Wn = W / np.linalg.norm(W, axis=1, keepdims=True)
    C = Wn @ Wn.T
    np.fill_diagonal(C, 0)
    pairs = sorted(
        {(min(a, int(np.argmin(C[a]))), max(a, int(np.argmin(C[a])))) for a in range(len(idx))},
        key=lambda ab: C[ab[0], ab[1]],
    )[:2]

    import textwrap

    meta = (
        "decoder rows of the 31 always-on Gemma-Scope cone features (21-geometry/cone-decoder.npz), 2304-dim as 48x48  ·  "
        "pixel order per pair: dims sorted by the first row's values  ·  scatter: one dot per dimension  ·  shared colour scale"
    )
    fig, top = figure(16.5, 10.4, 3, "the knob", "Opposite knobs, finally visible", meta)

    def name_of(j) -> str:
        return cone_names.get(int(idx[j]), "?").rstrip(". \n")

    lim = float(np.percentile(np.abs(W[[j for p in pairs for j in p]]), 99.5))
    y_top = top - 0.05
    cmap = saturated_magma()
    im = None
    for row, (a, b) in enumerate(pairs):
        cval = float(C[a, b])
        order = np.argsort(-W[a])
        y = y_top - row * 0.45
        header = f'{idx[a]} "{name_of(a)}"   vs   {idx[b]} "{name_of(b)}"   ·   cos = {cval:.3f}'
        fig.text(MARGIN, y + 0.012, header, color=TEXT, fontsize=10.5)
        for col, j in ((0, a), (1, b)):
            ax, h = sq_axes(fig, MARGIN + col * 0.165, y - 0.03, 0.145)
            im = ax.imshow(
                W[j][order].reshape(48, 48),
                cmap=cmap,
                vmin=-lim,
                vmax=lim,
                interpolation="nearest",
            )
            ax.set_title(f"decoder row {idx[j]}", color=MUTED, fontsize=8.5, pad=5)
        side = h * fig.get_figheight() / fig.get_figwidth()
        axs = fig.add_axes([MARGIN + 0.375, y - 0.03 - h, side, h])
        style_axes(axs)
        rng = float(np.abs(W[[a, b]]).max()) * 1.05
        axs.plot([-rng, rng], [rng, -rng], color=MUTED, lw=0.9, ls="--", zorder=1)
        axs.scatter(W[a], W[b], s=3, color=GOLD, alpha=0.55, lw=0, zorder=2)
        axs.axhline(0, color=FRAME, lw=0.7)
        axs.axvline(0, color=FRAME, lw=0.7)
        axs.set_xlim(-rng, rng)
        axs.set_ylim(-rng, rng)
        axs.tick_params(labelsize=7)
        axs.set_xlabel(f"the dimension's weight in {idx[a]}", color=MUTED, fontsize=8.5)
        axs.set_ylabel(f"its weight in {idx[b]}", color=MUTED, fontsize=8.5)
        axs.set_title(
            "one dot per dimension  ·  dashed: exact opposition (y = -x)",
            color=MUTED,
            fontsize=8.5,
            pad=5,
        )
        story = (
            f'every dimension that pushes toward "{name_of(a)}" pulls away from '
            f'"{name_of(b)}" by the same amount — one direction in the space, two names '
            "at its two ends. this is the digon geometry from Toy Models of Superposition, "
            "sitting in a production dictionary."
        )
        fig.text(
            MARGIN + 0.60,
            y - 0.045,
            "\n".join(textwrap.wrap(story, 52)),
            color=MUTED,
            fontsize=9.5,
            linespacing=1.7,
            va="top",
        )

    cax = fig.add_axes([MARGIN, y_top - 0.03 - h - 0.045, 0.31, 0.011])
    cax._is_colorbar = True
    cb = fig.colorbar(im, cax=cax, orientation="horizontal")
    cb.outline.set_edgecolor(FRAME)
    cax.tick_params(colors=MUTED, labelsize=6.5)
    cax.set_xlabel(
        "decoder weight (shared scale, all four images)", color=MUTED, fontsize=7.5, labelpad=2
    )

    verdict(fig, "cos -0.99: the dictionary spends one direction on two opposite concepts")
    save(fig, "03-opposite-knobs.png")


def main() -> None:
    which = set(sys.argv[1:]) or {"1", "2", "3"}
    rig = Rig()
    if "1" in which:
        fig01(rig)
    if "2" in which:
        fig02(rig)
    if "3" in which:
        fig03(rig)


if __name__ == "__main__":
    main()
