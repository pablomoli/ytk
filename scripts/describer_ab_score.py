"""Section 65: score the describer prompt variants against the owner's marks and two independent checks.

uv run --with matplotlib python scripts/describer_ab_score.py
"""

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from plot_assets import (
    BG,
    CYAN,
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

from ytk import store, visual

D = Path.home() / ".ytk" / "describer"
AB = D / "ab"
OUT = Path(__file__).resolve().parents[1] / "docs" / "assets" / "65-describer-prompts"
OUT.mkdir(parents=True, exist_ok=True)
FIGHTS = {"urKKrMlhgwI", "45ZZAQvYQfo", "B2V5qoJVHAo", "5E-R7K2d7iU", "mhLzU1kSDd8"}

pk = json.loads((AB / "packets.json").read_text())
variants = json.loads((AB / "variants.json").read_text())
keys = ["control"] + [v["key"] for v in variants]
label = {"control": "the pilot's prompt"} | {v["key"]: v["name"] for v in variants}
color = dict(zip(keys, [MUTED, GOLD, CYAN, PURPLE], strict=False))
marks = {
    p.stem: json.loads(p.read_text()) for p in (D / "review-answers" / "reviews").glob("*.json")
}


def load(key: str, p: dict) -> dict | None:
    if key == "control":
        if not (D / "aware" / f"{p['video']}.json").exists():
            return None
        d = json.loads((D / "aware" / f"{p['video']}.json").read_text())
        fr = d["frames"][ord(p["letter"]) - 65]
        return {
            "content": fr["shown"],
            "look": fr["look"],
            "lineage": fr["lineage"],
            "vibe": fr["feel"],
            "terms": fr["terms"],
            "named": [],
            "come_back_for": [],
        }
    f = AB / key / f"{p['id']}.json"
    return json.loads(f.read_text()) if f.exists() else None


out = {k: [load(k, p) for p in pk] for k in keys}
print({k: sum(x is not None for x in v) for k, v in out.items()}, "of", len(pk))
words = lambda s: len((s or "").split())
info = [i for i, p in enumerate(pk) if (marks.get(p["id"], {}).get("back") or []) == ["info"]]
# Two frames whose look he marked right, and, apart, the frames of the video he said he
# saved for content, execution and looks at once: most of its frames are a person talking.
looky = [i for i, p in enumerate(pk) if p["id"] in ("VcvhiDV_t3c_D", "ztkh1r1ioZo_I")]
essay = [i for i, p in enumerate(pk) if p["video"] == "LQoFN1K1dZ8"]
reels = [i for i, p in enumerate(pk) if p.get("source") == "instagram"]
rest = [i for i in range(len(pk)) if i not in info + looky + essay + reels]
GROUPS = [
    ("he wants\nthe info", info),
    ("look he\nmarked right", looky),
    ("video saved\nfor looks too", essay),
    ("Instagram\nreels", reels),
    ("everything\nelse", rest),
]
mine = [i for i, p in enumerate(pk) if (marks.get(p["id"], {}).get("mine") or "").strip()]
fights = [i for i, p in enumerate(pk) if p["video"] in FIGHTS]

# The image-text model's opinion of each term, as the frame's rank among the test frames.
img = np.asarray(visual.embed_images([Path(p["path"]) for p in pk]), float)
img /= np.linalg.norm(img, axis=1, keepdims=True)
phrase = lambda t: (t.partition(":")[2] or t).replace("-", " ") + " " + t.partition(":")[0]
all_terms = sorted({t for k in keys for x in out[k] if x for t in x["terms"]})
tx = np.asarray(visual.embed_texts([phrase(t) for t in all_terms]), float)
tx /= np.linalg.norm(tx, axis=1, keepdims=True)
rank = np.argsort(np.argsort(tx @ img.T, axis=1), axis=1) / (len(pk) - 1)
trow = {t: k for k, t in enumerate(all_terms)}

ef = store._get_ef()


def unit(texts):
    x = np.asarray(ef(texts), float)
    return x / np.linalg.norm(x, axis=1, keepdims=True)


his = unit([marks[pk[i]["id"]]["mine"] for i in mine]) if mine else None
res, per = {}, {}
for k in keys:
    o = out[k]
    have = [i for i in range(len(pk)) if o[i]]
    light = [
        np.mean([t.split(":")[0] in ("light", "palette") for t in o[i]["terms"]])
        for i in have
        if o[i]["terms"]
    ]
    look_info = [words(o[i]["look"]) for i in info if o[i]]
    look_look = [words(o[i]["look"]) for i in looky if o[i]]
    trank = [
        float(np.mean([rank[trow[t], i] for t in o[i]["terms"]])) for i in have if o[i]["terms"]
    ]
    close = []
    if mine:
        ours = unit([(o[i]["content"] + " " + o[i]["look"]) if o[i] else "none" for i in mine])
        close = [float(a @ b) for a, b in zip(his, ours, strict=True)]
    names = [(n, pk[i]["user"].lower()) for i in fights if o[i] for n in o[i]["named"]]
    textual = [(n, u) for n, u in names if n["source"] != "on screen"]
    found = [n["name"].lower().split()[-1] in u for n, u in textual]
    back = []
    for i in info:
        if o[i] and k != "control":
            got = set(o[i]["come_back_for"])
            back.append(len(got & {"info"}) / max(len(got | {"info"}), 1))
    wrote = [
        float(np.mean([bool(o[i]["look"].strip()) for i in g if o[i]]))
        if any(o[i] for i in g)
        else np.nan
        for _, g in GROUPS
    ]
    per[k] = {
        "wrote": wrote,
        "light": light,
        "look_info": look_info,
        "look_look": look_look,
        "trank": trank,
        "close": close,
    }
    res[k] = {
        "frames": len(have),
        "light_or_palette_share_of_terms": float(np.mean(light)) if light else None,
        "look_words_where_he_wants_info_median": float(np.median(look_info)) if look_info else None,
        "look_words_on_look_frames_median": float(np.median(look_look)) if look_look else None,
        "lineage_named_on_look_frames": sum(bool(o[i]["lineage"].strip()) for i in looky if o[i]),
        "closeness_to_his_words_mean": float(np.mean(close)) if close else None,
        "image_text_rank_of_terms_mean": float(np.mean(trank)) if trank else None,
        "names_per_fight_frame": len(names) / max(len([i for i in fights if o[i]]), 1),
        "names_from_text_found_in_evidence": (sum(found), len(found)),
        "names_read_on_screen": len(names) - len(textual),
        "come_back_for_agreement": float(np.mean(back)) if back else None,
        "terms_per_frame": float(np.mean([len(o[i]["terms"]) for i in have])),
        "share_of_frames_with_look_text": dict(
            zip([n.replace("\n", " ") for n, _ in GROUPS], wrote, strict=True)
        ),
        "look_weight_mean": {
            n.replace("\n", " "): float(np.mean([o[i]["weight"]["look"] for i in g if o[i]]))
            for n, g in GROUPS
            if k != "control" and any(o[i] for i in g)
        },
    }
res["n"] = {
    "frames": len(pk),
    "info_frames": len(info),
    "look_frames": len(looky),
    "frames_with_his_words": len(mine),
    "fight_frames": len(fights),
}
(OUT / "results.json").write_text(json.dumps(res, indent=1))
print(json.dumps(res, indent=1))

plt.style.use("dark_background")
best = min(
    (k for k in keys if k != "control"),
    key=lambda k: res[k]["look_words_where_he_wants_info_median"],
)
fig, top = figure(
    20,
    7.6,
    65,
    "DESCRIBER PROMPTS  ·  THREE STRATEGIES AGAINST THE PILOT, SAME FRAMES",
    "Which instructions stop the describer writing about venue lighting, and what does it cost?",
    f"{len(pk)} frames, one per call, each with its caption lines, title, channel and measured colors  ·  {len(info)} frames the owner wants for the info, "
    f"{len(looky)} he marked as a look worth describing, {len(mine)} with his own words  ·  dots are frames, bars are medians",
)
gs = fig.add_gridspec(1, 4, left=0.045, right=0.98, bottom=0.2, top=top - 0.09, wspace=0.26)
rng = np.random.default_rng(5)


def dots(ax, field, ylabel, title, second=None):
    for x, k in enumerate(keys):
        for vals, dx, mk in (
            (per[k][field], -0.17 if second else 0, "o"),
            (per[k][second] if second else [], 0.17, "D"),
        ):
            if not len(vals):
                continue
            ax.scatter(
                x + dx + (rng.random(len(vals)) - 0.5) * 0.2,
                vals,
                s=42,
                color=color[k],
                alpha=0.75,
                linewidths=0,
                marker=mk,
            )
            ax.plot([x + dx - 0.15, x + dx + 0.15], [np.median(vals)] * 2, color=TEXT, lw=2.2)
    ax.set_xticks(range(len(keys)))
    ax.set_xticklabels([label[k].replace(" ", "\n", 1) for k in keys], color=TEXT, fontsize=8.5)
    ax.set_ylabel(ylabel)
    panel_title(ax, title, width=34)


ax = fig.add_subplot(gs[0])
style_axes(ax)
dots(
    ax,
    "look_info",
    "words in the look field",
    "Look text written: where he wants the info, and where the look is the point",
    second="look_look",
)
ax.scatter(
    [], [], s=42, color=TEXT, marker="o", label=f"frames he wants for the info ({len(info)})"
)
ax.scatter(
    [], [], s=42, color=TEXT, marker="D", label=f"frames whose look he marked right ({len(looky)})"
)
ax.plot([], [], color=TEXT, lw=2.2, label="median")
ax.legend(frameon=False, fontsize=8.5, labelcolor=TEXT, loc="upper right")
ax = fig.add_subplot(gs[1])
style_axes(ax)
width = 0.8 / len(keys)
for j, k in enumerate(keys):
    ax.bar(
        np.arange(len(GROUPS)) - 0.4 + width * (j + 0.5),
        np.nan_to_num(per[k]["wrote"]),
        width * 0.9,
        color=color[k],
    )
ax.set_xticks(range(len(GROUPS)))
ax.set_xticklabels([f"{n}\n({len(g)})" for n, g in GROUPS], color=TEXT, fontsize=8.5)
ax.set_ylim(0, 1.05)
ax.set_ylabel("share of frames given any look text")
panel_title(
    ax, "Does it write a look only where one is wanted? (colors as in the key below)", width=38
)
ax = fig.add_subplot(gs[2])
style_axes(ax)
dots(
    ax,
    "close",
    "cosine between his note and the describer's text",
    "Closeness to what he wrote himself",
)
ax = fig.add_subplot(gs[3])
style_axes(ax)
dots(
    ax,
    "trank",
    "mean rank of the frame for its own terms (1 = best)",
    "An image-text model's opinion of the terms",
)
ax.axhline(0.5, color=MUTED, lw=1, ls="--", label="chance")
ax.legend(frameon=False, fontsize=8.5, labelcolor=TEXT, loc="lower right")
from matplotlib.lines import Line2D

fig.legend(
    handles=[
        Line2D([0], [0], marker="o", ls="", color=color[k], markersize=9, label=label[k])
        for k in keys
    ],
    loc="lower center",
    ncol=len(keys),
    frameon=False,
    labelcolor=TEXT,
    fontsize=10,
    bbox_to_anchor=(0.5, 0.035),
)
c, b = res["control"], res[best]
verdict(
    fig,
    f"look text where he wants the info: {c['look_words_where_he_wants_info_median']:.0f} words in the pilot, {b['look_words_where_he_wants_info_median']:.0f} with {label[best]}",
)
frame_panels(fig)
fig.savefig(OUT / "01-prompts.png", dpi=300, facecolor=BG)
print("saved")
