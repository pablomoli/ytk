"""Section 64, figure 3: can a check that never asks the describer catch what the owner marked wrong?

Three checks, each scored against the owner's marks on the describer's terms:
the image-text model's own opinion of the term, the frame's pixels for color
claims, and how common the term is. No model calls. Reads ~/.ytk/describer.

    uv run --with matplotlib python scripts/grounding_checks.py
"""

import colorsys
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image
from plot_assets import (
    BG,
    CYAN,
    DIM,
    GOLD,
    MUTED,
    PURPLE,
    TEXT,
    figure,
    frame_panels,
    panel_title,
    style_axes,
    verdict,
)

from ytk import visual

D = Path.home() / ".ytk" / "describer"
OUT = Path(__file__).resolve().parents[1] / "docs" / "assets" / "64-moments-and-describer"
COLOR = {"right": GOLD, "generic": CYAN, "wrong": PURPLE}
NAME = {"right": "marked right", "generic": "marked true but too generic", "wrong": "marked wrong"}

frames = [
    json.loads(line.rstrip(",\n"))
    for line in (D / "review" / "frames.json").read_text().splitlines()
    if line.startswith("{")
]
by_id = {f["id"]: k for k, f in enumerate(frames)}
vocab = json.loads((D / "vocabulary.json").read_text())
marks = []  # (frame index, term, verdict)
for p in sorted((D / "review-answers" / "reviews").glob("*.json")):
    d = json.loads(p.read_text())
    if p.stem not in by_id:
        continue
    marks += [(by_id[p.stem], t, v) for t, v in (d.get("terms") or {}).items() if v in COLOR]
print(
    len(marks),
    "marked terms on",
    len({m[0] for m in marks}),
    "frames",
    {v: sum(m[2] == v for m in marks) for v in COLOR},
)


def auc(pos: list[float], neg: list[float]) -> float:
    """Share of (pos, neg) pairs where pos scores higher; ties count half."""
    if not pos or not neg:
        return float("nan")
    return float(np.mean([(a > b) + 0.5 * (a == b) for a in pos for b in neg]))


# Check 1: does the image-text model, shown the term, rank this frame high among all frames?
def phrase(term: str) -> str:
    facet, _, words = term.partition(":")
    text = (vocab.get(term, {}).get("definition") or "").strip()
    return text or f"{words.replace('-', ' ')} {facet}"


img = np.asarray(visual.embed_images([D / "review" / f["img"] for f in frames]), float)
img /= np.linalg.norm(img, axis=1, keepdims=True)
terms = sorted({m[1] for m in marks})
txt = np.asarray(visual.embed_texts([phrase(t) for t in terms]), float)
txt /= np.linalg.norm(txt, axis=1, keepdims=True)
sim = txt @ img.T
rank = {t: (np.argsort(np.argsort(sim[k])) / (len(frames) - 1)) for k, t in enumerate(terms)}
pct = [float(rank[t][i]) for i, t, _ in marks]

# Check 2: for a color claim, how much of the frame is actually that color?
FAMILY = {
    "red": lambda h, s, v: ((h < 15) | (h >= 345)) & (s > 0.25) & (v > 0.2),
    "crimson": lambda h, s, v: ((h < 15) | (h >= 345)) & (s > 0.25) & (v > 0.2),
    "orange": lambda h, s, v: (h >= 15) & (h < 45) & (s > 0.25) & (v > 0.2),
    "brown": lambda h, s, v: (h >= 10) & (h < 45) & (s > 0.25) & (v > 0.15) & (v < 0.65),
    "yellow": lambda h, s, v: (h >= 45) & (h < 70) & (s > 0.25) & (v > 0.2),
    "green": lambda h, s, v: (h >= 70) & (h < 165) & (s > 0.25) & (v > 0.2),
    "teal": lambda h, s, v: (h >= 165) & (h < 200) & (s > 0.25) & (v > 0.2),
    "cyan": lambda h, s, v: (h >= 165) & (h < 200) & (s > 0.25) & (v > 0.2),
    "blue": lambda h, s, v: (h >= 200) & (h < 255) & (s > 0.25) & (v > 0.2),
    "violet": lambda h, s, v: (h >= 255) & (h < 295) & (s > 0.25) & (v > 0.2),
    "purple": lambda h, s, v: (h >= 255) & (h < 295) & (s > 0.25) & (v > 0.2),
    "magenta": lambda h, s, v: (h >= 295) & (h < 345) & (s > 0.25) & (v > 0.2),
    "pink": lambda h, s, v: (h >= 295) & (h < 345) & (s > 0.25) & (v > 0.2),
    "white": lambda h, s, v: (s < 0.12) & (v > 0.82),
    "black": lambda h, s, v: v < 0.12,
    "cream": lambda h, s, v: (h >= 25) & (h < 65) & (s >= 0.05) & (s < 0.3) & (v > 0.8),
}
to_hsv = np.vectorize(colorsys.rgb_to_hsv)
hsv = []
for f in frames:
    with Image.open(D / "review" / f["img"]) as im:
        a = np.asarray(im.convert("RGB").resize((160, 90)), float) / 255
    h, s, v = to_hsv(a[..., 0], a[..., 1], a[..., 2])
    hsv.append((h * 360, s, v))


def share(i: int, words: list[str]) -> float:
    h, s, v = hsv[i]
    hit = np.zeros(h.shape, bool)
    for w in words:
        hit |= FAMILY[w](h, s, v)
    return float(hit.mean())


claims = []
for i, t, verdict_ in marks:
    words = [w for w in t.partition(":")[2].split("-") if w in FAMILY]
    if t.startswith("palette:") and words:
        everywhere = np.array([share(k, words) for k in range(len(frames))])
        claims.append(
            {
                "term": t,
                "verdict": verdict_,
                "share": share(i, words),
                "median": float(np.median(everywhere)),
                "q1": float(np.percentile(everywhere, 25)),
                "q3": float(np.percentile(everywhere, 75)),
                "pct": float((everywhere < share(i, words)).mean()),
            }
        )

# Check 3: is "too generic" just "common"?
count = {t: sum(t in f["terms"] for f in frames) for t in {x for f in frames for x in f["terms"]}}
freq = [count[t] for _, t, _ in marks]

by = lambda vals, v: [x for x, m in zip(vals, marks, strict=True) if m[2] == v]
res = {
    "marks": {v: sum(m[2] == v for m in marks) for v in COLOR},
    "frames_marked": len({m[0] for m in marks}),
    "image_text": {
        "auc_true_over_wrong": auc(by(pct, "right") + by(pct, "generic"), by(pct, "wrong")),
        "median_percentile": {v: float(np.median(by(pct, v))) for v in COLOR if by(pct, v)},
    },
    "pixels": {
        "claims": claims,
        "auc_true_over_wrong": auc(
            [c["pct"] for c in claims if c["verdict"] != "wrong"],
            [c["pct"] for c in claims if c["verdict"] == "wrong"],
        ),
    },
    "frequency": {
        "auc_generic_over_right": auc(by(freq, "generic"), by(freq, "right")),
        "median_frames": {v: float(np.median(by(freq, v))) for v in COLOR if by(freq, v)},
    },
}
(OUT / "checks.json").write_text(json.dumps(res, indent=1))
print(json.dumps({k: v for k, v in res.items() if k != "pixels"}, indent=1))
for c in claims:
    print(
        f"  {c['verdict']:8s} {c['term']:38s} share {c['share']:.3f}  corpus median {c['median']:.3f}  pct {c['pct']:.2f}"
    )

plt.style.use("dark_background")
n_true = res["marks"]["right"] + res["marks"]["generic"]
fig, top = figure(
    19,
    7.4,
    64,
    "GROUNDING CHECKS  ·  THE OWNER'S FIRST MARKS AS THE ANSWER KEY",
    "Can a check that never asks the describer catch what was marked wrong?",
    f"{len(marks)} terms marked on {res['frames_marked']} frames: {res['marks']['right']} right, {res['marks']['generic']} too generic, {res['marks']['wrong']} wrong  ·  "
    f"image-text model ranks true terms above wrong ones in {res['image_text']['auc_true_over_wrong']:.0%} of pairs  ·  "
    f"pixels, {len(claims)} color claims: {res['pixels']['auc_true_over_wrong']:.0%}  ·  commonness separates generic from right in {res['frequency']['auc_generic_over_right']:.0%}",
)
gs = fig.add_gridspec(
    1, 3, left=0.05, right=0.975, bottom=0.13, top=top - 0.1, wspace=0.27, width_ratios=[1, 1.1, 1]
)
rows = ["right", "generic", "wrong"]


def strip(ax, vals, xlabel, log=False):
    for y, v in enumerate(rows[::-1]):
        xs = by(vals, v)
        jit = (np.random.default_rng(3).random(len(xs)) - 0.5) * 0.42
        ax.scatter(xs, y + jit, s=95, color=COLOR[v], alpha=0.9, linewidths=0, label=NAME[v])
        if xs:
            ax.plot([np.median(xs)] * 2, [y - 0.36, y + 0.36], color=COLOR[v], lw=2.4)
    ax.set_yticks(range(3))
    ax.set_yticklabels(
        [r if r != "generic" else "too generic" for r in rows[::-1]], color=TEXT, fontsize=10
    )
    ax.set_ylim(-2.7, 2.6)
    ax.set_xlabel(xlabel)
    if log:
        ax.set_xscale("log")


ax = fig.add_subplot(gs[0])
style_axes(ax)
ax.barh(
    -0.75,
    1,
    left=0,
    height=0.22,
    color=DIM,
    label="a frame picked at random lands anywhere along here",
)
ax.axvline(0.5, color=MUTED, lw=1, ls="--", label="chance, the middle frame")
strip(ax, pct, "where the marked frame ranks among all frames for that term (1 = best match)")
ax.set_xlim(-0.03, 1.03)
ax.legend(frameon=False, fontsize=8.5, labelcolor=TEXT, loc="lower left", ncol=1)
panel_title(ax, "The image-text model's opinion of each term (bar = median)", width=44)

ax = fig.add_subplot(gs[1])
style_axes(ax)
order = sorted(
    range(len(claims)),
    key=lambda k: (rows.index(claims[k]["verdict"]), -claims[k]["share"]),
    reverse=True,
)
for y, k in enumerate(order):
    c = claims[k]
    ax.plot([c["q1"], c["q3"]], [y, y], color=DIM, lw=9, solid_capstyle="butt")
    ax.plot([c["median"], c["share"]], [y, y], color=MUTED, lw=0.8)
    ax.scatter([c["share"]], [y], s=120, color=COLOR[c["verdict"]], zorder=4)
ax.set_yticks([])
for y, k in enumerate(order):
    c = claims[k]
    far = c["share"] > 0.3
    name = c["term"].partition(":")[2].replace("-", " ")
    ax.text(
        c["share"] + (-0.02 if far else 0.02),
        y,
        name,
        color=TEXT,
        fontsize=9.5,
        va="center",
        ha="right" if far else "left",
    )
ax.set_ylim(-3.2, len(order) - 0.4)
ax.set_xlim(-0.02, max(c["share"] for c in claims) * 1.12 + 0.02)
ax.set_xlabel("share of the frame's pixels that are the claimed color")
for v in rows:
    ax.scatter([], [], s=120, color=COLOR[v], label=NAME[v])
ax.plot([], [], color=DIM, lw=9, label="the same color in the middle half of all frames")
ax.legend(frameon=False, fontsize=8.5, labelcolor=TEXT, loc="lower right")
panel_title(ax, "Color claims against the frame's own pixels", width=44)

ax = fig.add_subplot(gs[2])
style_axes(ax)
allc = np.array(sorted(count.values()))
ax.hist(
    allc,
    bins=np.geomspace(1, allc.max() + 1, 14),
    color=DIM,
    weights=np.full(len(allc), 1.2 / len(allc)),
    bottom=-2.6,
    label="every term in the vocabulary (share of terms)",
)
strip(ax, freq, "frames that carry the term, of " + str(len(frames)) + " (log)", log=True)
ax.legend(frameon=False, fontsize=8.5, labelcolor=TEXT, loc="lower right")
panel_title(ax, "Is too generic the same as common?", width=40)
verdict(
    fig,
    f"wrong terms sit lower than true ones for the image-text model in {res['image_text']['auc_true_over_wrong']:.0%} of pairs, on {res['marks']['wrong']} wrong against {n_true} true",
)
frame_panels(fig)
fig.savefig(OUT / "03-grounding-checks.png", dpi=300, facecolor=BG)
print("saved")
