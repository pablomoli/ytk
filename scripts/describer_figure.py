"""Section 64, figures 2 and 3: what the describer pilot wrote, and whether seeing the corpus helped.

uv run --with matplotlib python scripts/describer_figure.py
"""

import json
import sys
import textwrap
from itertools import combinations, pairwise
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
    TEXT,
    figure,
    frame_panels,
    panel_title,
    style_axes,
    verdict,
)

from ytk import store

D, SPRITES = Path.home() / ".ytk" / "describer", Path.home() / ".ytk" / "sprites"
OUT = Path(__file__).resolve().parents[1] / "docs" / "assets" / "64-moments-and-describer"
K, NULLS = 10, 300
rng = np.random.default_rng(7)
mo = np.load(SPRITES / "moments.npz")
order = json.loads((D / "videos.json").read_text())


def load(arm: str) -> list[dict]:
    rows = []
    for vid in order[arm]:
        p = D / arm / f"{vid}.json"
        if not p.exists():
            continue
        d = json.loads(p.read_text())
        look_rows = np.where(mo["look_video"] == vid)[0]
        for k, fr in enumerate(d["frames"][: len(d["reps"])]):
            if fr["usable"]:
                rows.append(
                    fr
                    | {
                        "video": vid,
                        "file": min((D / "frames" / vid).glob(f"{chr(65 + k)}*.jpg")).name,
                        "vec": mo["look_vec"][look_rows[k]],
                    }
                )
    return rows


aware, blind = load("aware"), load("blind")
blind_vids = set(order["blind"])
aware_10 = [r for r in aware if r["video"] in blind_vids]
print(
    f"aware {len(aware)} frames over {len({r['video'] for r in aware})} videos, blind {len(blind)}"
)


def growth(rows: list[dict]) -> np.ndarray:
    seen, out = set(), []
    for r in rows:
        seen |= set(r["terms"])
        out.append(len(seen))
    return np.array(out)


def pair_agreement(rows: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    """Image similarity and shared-term share for every pair of frames from different videos."""
    sim, jac = [], []
    for a, b in combinations(rows, 2):
        if a["video"] == b["video"]:
            continue
        ta, tb = set(a["terms"]), set(b["terms"])
        sim.append(float(a["vec"] @ b["vec"]))
        jac.append(len(ta & tb) / max(len(ta | tb), 1))
    return np.array(sim), np.array(jac)


def binned(sim, jac, edges):
    return np.array(
        [
            jac[(sim >= lo) & (sim < hi)].mean()
            if ((sim >= lo) & (sim < hi)).sum() >= 5
            else np.nan
            for lo, hi in pairwise(edges)
        ]
    )


sa, ja = pair_agreement(aware_10)
sb, jb = pair_agreement(blind)
edges = np.quantile(np.concatenate([sa, sb]), np.linspace(0, 1, 7))
edges[-1] += 1e-6
mid = (edges[:-1] + edges[1:]) / 2
top = sa >= edges[-2]
top_b = sb >= edges[-2]

ef = store._get_ef()


def embed(texts: list[str]) -> np.ndarray:
    x = np.asarray(ef(texts), float)
    return x / np.linalg.norm(x, axis=1, keepdims=True)


spaces = {
    "look text": embed([r["look"] for r in aware]),
    "shown text": embed([r["shown"] for r in aware]),
    "frame (image model)": np.stack([r["vec"] for r in aware]),
}
vid_of = np.array([r["video"] for r in aware])
n = len(aware)


def knn(x):
    s = x @ x.T
    np.fill_diagonal(s, -9)
    s[vid_of[:, None] == vid_of[None, :]] = -9  # neighbors must come from another video
    return np.argsort(-s, axis=1)[:, :K]


def overlap(a, b):
    return float(np.mean([len(set(x) & set(y)) for x, y in zip(a, b, strict=True)]) / K)


nn = {k: knn(v) for k, v in spaces.items()}
pairs = [
    ("look text", "shown text"),
    ("look text", "frame (image model)"),
    ("shown text", "frame (image model)"),
]
res = {}
for a, b in pairs:
    null = []
    for _ in range(NULLS):
        p = rng.permutation(n)
        inv = np.empty(n, int)
        inv[p] = np.arange(n)
        null.append(overlap(nn[a], inv[nn[b][p]]))
    res[f"{a}|{b}"] = {"observed": overlap(nn[a], nn[b]), "null": null}
    print(a, "|", b, round(res[f"{a}|{b}"]["observed"], 3), "null", round(float(np.mean(null)), 3))

ga, gb, gall = growth(aware_10), growth(blind), growth(aware)
facet = lambda rows: {
    f: len({t for r in rows for t in r["terms"] if t.startswith(f + ":")})
    for f in ("medium", "palette", "light", "texture", "composition", "style")
}
summary = {
    "frames": {"aware": len(aware), "aware_same_10_videos": len(aware_10), "blind": len(blind)},
    "distinct_terms": {
        "aware_same_10_videos": int(ga[-1]),
        "blind": int(gb[-1]),
        "aware_all_20": int(gall[-1]),
    },
    "terms_per_frame": {
        "aware": float(np.mean([len(r["terms"]) for r in aware_10])),
        "blind": float(np.mean([len(r["terms"]) for r in blind])),
    },
    "shared_term_share_most_alike_pairs": {
        "aware": float(ja[top].mean()),
        "blind": float(jb[top_b].mean()),
    },
    "shared_term_share_all_pairs": {"aware": float(ja.mean()), "blind": float(jb.mean())},
    "distinct_terms_by_facet": {"aware": facet(aware_10), "blind": facet(blind)},
    "space_agreement": res,
    "sprite_stand_ins": sum("sprite" in r["file"] for r in aware),
}
(OUT / "results.json").write_text(json.dumps(summary, indent=1))
print(json.dumps({k: v for k, v in summary.items() if k != "space_agreement"}, indent=1))

plt.style.use("dark_background")
fig, top_y = figure(
    19,
    7.6,
    64,
    "THE DESCRIBER PILOT  ·  REAL FRAMES, WITH AND WITHOUT THE CORPUS IN VIEW",
    "Does a describer that sees what was already described reuse its words?",
    f"{len(aware)} frames from 20 videos described with the vocabulary and nearest described frames in view; the first 10 videos "
    f"({len(blind)} frames) described again blind  ·  distinct terms on those 10: aware {ga[-1]}, blind {gb[-1]}  ·  "
    f"shared-term share among the most alike frame pairs: aware {ja[top].mean():.2f}, blind {jb[top_b].mean():.2f}",
)
gs = fig.add_gridspec(
    1,
    3,
    left=0.05,
    right=0.975,
    bottom=0.13,
    top=top_y - 0.09,
    wspace=0.24,
    width_ratios=[1, 1, 1.05],
)
ax = fig.add_subplot(gs[0])
style_axes(ax)
ax.plot(
    np.arange(1, len(gb) + 1), gb, color=CYAN, lw=2.2, label="blind: no vocabulary, no neighbors"
)
ax.plot(np.arange(1, len(ga) + 1), ga, color=GOLD, lw=2.2, label="aware: same 10 videos")
ax.plot(
    np.arange(len(ga) + 1, len(gall) + 1),
    gall[len(ga) :],
    color=GOLD,
    lw=1.4,
    ls=":",
    label="aware: the 10 further videos",
)
ax.plot(
    [0, max(len(gb), 1)],
    [0, np.mean([len(r["terms"]) for r in blind]) * max(len(gb), 1)],
    color=DIM,
    lw=1.4,
    label="if every term were new",
)
ax.set_ylim(0, max(gb.max(), gall.max()) * 1.15)
ax.set_xlabel("frames described so far")
ax.set_ylabel("distinct terms in use")
ax.legend(frameon=False, fontsize=9, labelcolor=TEXT, loc="upper left")
panel_title(ax, "How fast the vocabulary grows", width=40)
ax = fig.add_subplot(gs[1])
style_axes(ax)
shuffled = [binned(sb, rng.permutation(jb), edges) for _ in range(NULLS)]
ax.fill_between(
    mid,
    np.nanpercentile(shuffled, 0.5, axis=0),
    np.nanpercentile(shuffled, 99.5, axis=0),
    color=DIM,
    label="terms dealt to pairs at random",
)
ax.plot(mid, binned(sb, jb, edges), color=CYAN, lw=2.2, marker="o", label="blind")
ax.plot(mid, binned(sa, ja, edges), color=GOLD, lw=2.2, marker="o", label="aware")
ax.set_xlabel("how alike two frames are to the image model (cosine)")
ax.set_ylabel("share of their terms the two frames share")
ax.legend(frameon=False, fontsize=9, labelcolor=TEXT, loc="upper left")
panel_title(
    ax, "Do frames that look alike get the same terms? Pairs from different videos", width=44
)
ax = fig.add_subplot(gs[2])
style_axes(ax)
for y, (a, b) in enumerate(pairs[::-1]):
    q = res[f"{a}|{b}"]
    lo, hi = np.percentile(q["null"], [0.5, 99.5])
    ax.barh(y, hi - lo, left=lo, height=0.42, color=DIM)
    ax.plot([np.mean(q["null"]), q["observed"]], [y, y], color=MUTED, lw=0.8)
    ax.scatter([q["observed"]], [y], s=120, color=GOLD, zorder=4)
ax.set_yticks(range(len(pairs)))
ax.set_yticklabels([f"{a}\n· {b}" for a, b in pairs[::-1]], color=TEXT, fontsize=9)
ax.set_ylim(-1.3, len(pairs) - 0.4)
ax.set_xlim(0, None)
ax.set_xlabel(f"share of {K} nearest frames (other videos) two readings agree on")
ax.scatter([], [], s=120, color=GOLD, label="the pilot's frames")
ax.barh([0], [0], color=DIM, label="pairing shuffled")
ax.legend(frameon=False, fontsize=9, labelcolor=TEXT, loc="lower right")
panel_title(ax, "Is the look text the subject again? Neighbors by each reading", width=44)
q = res["look text|shown text"]
verdict(
    fig,
    f"aware used {ga[-1]} terms where blind used {gb[-1]}; look text shares {q['observed']:.0%} of neighbors with shown text",
)
frame_panels(fig)
fig.savefig(OUT / "02-describer.png", dpi=300, facecolor=BG)

# Figure 04: frames next to what was written about them.
pick = [r for r in aware if "sprite" not in r["file"]]
step = max(len(pick) // 12, 1)
pick = pick[::step][:12]
fig, axes = plt.subplots(
    len(pick),
    2,
    figsize=(17, 2.5 * len(pick)),
    facecolor=BG,
    gridspec_kw={"width_ratios": [1, 2.6]},
)
for (ai, at), r in zip(axes, pick, strict=True):
    ai.imshow(Image.open(D / "frames" / r["video"] / r["file"]))
    ai.set_axis_off()
    at.set_axis_off()
    at.set_facecolor(BG)
    at.text(
        0,
        1.0,
        textwrap.fill("LOOK  " + r["look"], 118),
        color=TEXT,
        fontsize=9.2,
        va="top",
        transform=at.transAxes,
    )
    at.text(
        0,
        0.42,
        textwrap.fill("LINEAGE  " + (r["lineage"] or "none named"), 118),
        color=GOLD,
        fontsize=9,
        va="top",
        transform=at.transAxes,
    )
    at.text(
        0,
        0.2,
        textwrap.fill("TERMS  " + "   ".join(r["terms"]), 118),
        color=CYAN,
        fontsize=9,
        va="top",
        transform=at.transAxes,
    )
    at.text(
        0, 0.02, "FEEL  " + r["feel"], color=MUTED, fontsize=9, va="top", transform=at.transAxes
    )
from matplotlib.lines import Line2D

fig.legend(
    handles=[
        Line2D([0], [0], color=c, lw=6, label=t)
        for t, c in (
            ("how it looks, subject removed", TEXT),
            ("named styles it descends from", GOLD),
            ("reusable terms", CYAN),
            ("how it lands", MUTED),
        )
    ],
    loc="upper left",
    bbox_to_anchor=(0.01, 0.999),
    ncol=4,
    frameon=False,
    labelcolor=TEXT,
    fontsize=10,
)
fig.subplots_adjust(left=0.01, right=0.99, top=0.975, bottom=0.01, hspace=0.12, wspace=0.03)
sheet = OUT / "04-described-frames.png"
fig.savefig(sheet, dpi=200, facecolor=BG)
print("saved", OUT / "02-describer.png", sheet)
