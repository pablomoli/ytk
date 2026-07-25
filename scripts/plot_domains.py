"""Ground-truth figures for semantic domains (#106).

The witness for the label axis, in the same role matplotlib plays for the fog
and picking series: an independent count of what each candidate grouping rule
actually places, so the decision is made on measured mass rather than on how
the bucket names read.

The claim under test is that the map's grouping axis is a directory axis
wearing two semantic labels. Rung 01 counts it.

Rungs:
  01  before/after — the shipped hybrid axis against the bucket axis

House style is imported from plot_assets rather than restated, so these can
never drift from docs/assets/fog/.

Usage: uv run --with matplotlib --with numpy python scripts/plot_domains.py
       --refresh recomputes the corpus assignment (slow: reads chroma).
Figures land in docs/assets/semantic-domains/.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from plot_assets import BG as FIG_BG
from plot_assets import (
    BLUE,
    DIM,
    DPI,
    GOLD,
    MUTED,
    TEXT,
    figure,
    frame_panels,
    panel_title,
    style_axes,
)

OUTDIR = ROOT / "docs" / "assets" / "semantic-domains"
PROPOSAL = ROOT / "docs" / "plans" / "106-buckets-proposal.yaml"
MAP = Path(os.path.expanduser("~/.ytk/map.json"))
SNAPSHOT_PATH = Path(os.path.expanduser("~/.ytk/interest/latest.json"))
CACHE = OUTDIR / "counts.json"

# Excluded from the grove by name; the map still has to place every point, so
# the question is only whether they form a bucket or render as `unplaced`.
HACKATHONS = ["niloc", "usf", "hacklytics-goldenbyte"]

UNPLACED = "unplaced"


def save(fig, name: str) -> None:
    frame_panels(fig)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    out = OUTDIR / name
    fig.savefig(out, dpi=DPI, facecolor=FIG_BG)
    print(f"wrote {out.relative_to(ROOT)}  ({out.stat().st_size // 1024}KB)")
    plt.close(fig)


def live_theme_labels() -> set[str]:
    snap = json.loads(SNAPSHOT_PATH.read_text())
    return {t["label"].lower() for t in snap["themes"]}


def before_counts() -> list[dict]:
    """The shipped axis, straight out of the payload the legend renders."""
    payload = json.loads(MAP.read_text())
    themes = live_theme_labels()
    out = []
    for d in payload["all"]["domains"]:
        label = d["label"]
        kind = "other" if label == "other" else ("theme" if label.lower() in themes else "path")
        out.append({"label": label, "n": d["n"], "kind": kind})
    return sorted(out, key=lambda d: -d["n"])


def after_counts(with_hackathons: bool) -> list[dict]:
    """The bucket axis under the proposed remap, counted over the live corpus."""
    import yaml

    from scripts.grove_lab.buckets import Bucket, BucketConfig, assign, resolve_notes

    raw = yaml.safe_load(PROPOSAL.read_text())
    buckets = [
        Bucket(
            name=b["name"],
            projects=list(b.get("projects", [])),
            themes=list(b.get("themes", [])),
            paths=list(b.get("paths", [])),
            seed=b.get("seed"),
        )
        for b in raw["buckets"]
    ]
    if with_hackathons:
        buckets.append(Bucket(name="hackathons", projects=list(HACKATHONS)))
    cfg = BucketConfig(buckets=buckets, seed_floor=float(raw["seed_floor"]), version=1)

    _vecs, meta, notes = resolve_notes()
    labels = assign(notes, cfg)
    counts = Counter(labels)

    out = []
    for i, b in enumerate(cfg.buckets):
        # A bucket carried only by project/path rules is still a directory cut;
        # the figure has to be able to say which is which.
        idx = [k for k, x in enumerate(labels) if x == i]
        by_theme = sum(1 for k in idx if notes[k].theme and notes[k].theme in b.themes)
        kind = "theme" if by_theme > len(idx) / 2 else "path"
        out.append({"label": b.name, "n": counts.get(i, 0), "kind": kind})
    out.sort(key=lambda d: -d["n"])
    out.append({"label": UNPLACED, "n": counts.get(-1, 0), "kind": "other"})
    return out


def _unit(a):
    import numpy as np

    return a / np.linalg.norm(a, axis=-1, keepdims=True)


def _null_arm(cv, cents, pool, sizes, repeats=60, seed=0):
    """Real vs null max-cosine for one (centring, pool) choice.

    The null builds centroids from random notes at the real theme sizes, so it
    asks the only question that matters: would a centroid that knows nothing
    about this note score as well?
    """
    import numpy as np

    rng = np.random.default_rng(seed)
    real = (cv @ cents.T).max(axis=1)
    null = []
    for _ in range(repeats):
        rc = [pool[rng.choice(len(pool), size=s, replace=False)].mean(axis=0) for s in sizes]
        null.append((cv @ _unit(np.array(rc)).T).max(axis=1))
    null = np.concatenate(null)
    return real, null


def _separation(real, null) -> float:
    import numpy as np

    return float((np.median(real) - np.median(null)) / null.std())


def null_study() -> dict:
    """Is the theme axis better than chance, and where should the floor sit?

    Four arms, because the answer flips with the null's pool and centring —
    the disagreement is the finding, not an inconvenience. The matched arm
    (centre on the content mean, draw the null from content) is the one that
    isolates within-content discriminative signal. A partition known to be
    real — source platform, which is metadata rather than inferred — is run
    through the identical test to give the separation scale a meaning.
    """
    import numpy as np

    from scripts.build_map import CONTENT_CATS
    from scripts.grove_lab.buckets import resolve_notes

    snap = json.loads(SNAPSHOT_PATH.read_text())
    themes = [t for t in snap["themes"] if t.get("centroid")]
    sizes = [len(t["note_ids"]) for t in themes]
    cents = np.array([t["centroid"] for t in themes])

    vecs, meta, _ = resolve_notes()
    cidx = [i for i, m in enumerate(meta) if m["cat"] in CONTENT_CATS]
    cvr = vecs[cidx]
    corpus_mu, content_mu = vecs.mean(axis=0), cvr.mean(axis=0)

    arms = {}
    for tag, cv, ce, pool in [
        ("raw / corpus null", _unit(cvr), _unit(cents), _unit(vecs)),
        ("raw / content null", _unit(cvr), _unit(cents), _unit(cvr)),
        (
            "corpus-centred / corpus null",
            _unit(cvr - corpus_mu),
            _unit(cents - corpus_mu),
            _unit(vecs - corpus_mu),
        ),
        (
            "content-centred / content null",
            _unit(cvr - content_mu),
            _unit(cents - content_mu),
            _unit(cvr - content_mu),
        ),
    ]:
        real, null = _null_arm(cv, ce, pool, sizes)
        arms[tag] = {"sep": _separation(real, null)}
        if tag.startswith("content-centred"):
            arms[tag]["real"] = real.tolist()
            arms[tag]["null"] = null[:: max(1, len(null) // 6000)].tolist()
            arms[tag]["null_p95"] = float(np.percentile(null, 95))
            arms[tag]["null_p99"] = float(np.percentile(null, 99))

    # The scale anchor: source platform is ground truth, not inference.
    cats = [meta[i]["cat"] for i in cidx]
    keep = [c for c, n in Counter(cats).items() if n >= 10]
    gcent = np.array(
        [cvr[[j for j, c in enumerate(cats) if c == k]].mean(axis=0) - content_mu for k in keep]
    )
    gsizes = [sum(1 for c in cats if c == k) for k in keep]
    greal, gnull = _null_arm(_unit(cvr - content_mu), _unit(gcent), _unit(cvr - content_mu), gsizes)

    raw_conf = (_unit(cvr) @ _unit(cents).T).max(axis=1)
    return {
        "arms": arms,
        "anchor": {"groups": keep, "sep": _separation(greal, gnull)},
        "n_content": len(cidx),
        "live_floor": float(np.percentile(raw_conf, 25)),
        "raw_conf": raw_conf.tolist(),
    }


def frozen_before() -> list[dict]:
    """The provenance axis as it shipped, read once and then frozen.

    before_counts() reads the live ~/.ytk/map.json, which after this issue
    lands *is* the bucket axis — so a later --refresh would quietly redraw
    the "before" panel as the after state and the figure would claim the
    change did nothing. The first run captures it; every run after that
    reuses the captured copy. Delete the key in counts.json to recapture.
    """
    if CACHE.exists():
        cached = json.loads(CACHE.read_text()).get("before")
        if cached:
            return cached
    return before_counts()


def compute() -> dict:
    from scripts.grove_lab.buckets import resolve_notes

    _vecs, meta, notes = resolve_notes()
    return {
        "total": len(notes),
        "themed": sum(1 for n in notes if n.theme),
        "cats": dict(Counter(m["cat"] for m in meta).most_common()),
        "before": frozen_before(),
        "after_excluded": after_counts(with_hackathons=False),
        "after_bucketed": after_counts(with_hackathons=True),
        "null": null_study(),
    }


def load(refresh: bool) -> dict:
    if not refresh and CACHE.exists():
        return json.loads(CACHE.read_text())
    data = compute()
    OUTDIR.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(data, indent=1))
    print(f"cached {CACHE.relative_to(ROOT)}")
    return data


COLOR = {"theme": GOLD, "path": BLUE, "other": DIM}


def bars(ax, rows: list[dict], total: int) -> None:
    labels = [r["label"] for r in rows]
    vals = [r["n"] for r in rows]
    ys = range(len(rows))
    ax.barh(list(ys), vals, color=[COLOR[r["kind"]] for r in rows], height=0.68)
    ax.set_yticks(list(ys))
    # Theme labels run to ~30 characters and would clip against the figure
    # edge; wrapping costs a line of height instead of a margin of width.
    ax.set_yticklabels([textwrap.fill(label, 19) for label in labels], fontsize=8.5)
    ax.invert_yaxis()
    # Headroom for the value label, which is drawn inside the axes so it
    # cannot run off the panel frame the way it does at a tighter limit.
    ax.set_xlim(0, total * 0.72)
    ax.set_xlabel("notes")
    style_axes(ax)
    for y, r in zip(ys, rows):
        pct = 100 * r["n"] / total
        ax.text(
            r["n"] + total * 0.008,
            y,
            f"{r['n']}  ({pct:.0f}%)",
            color=TEXT if r["n"] else MUTED,
            fontsize=8,
            va="center",
        )


def fig01(data: dict) -> None:
    total = data["total"]
    fig, top = figure(
        17.0,
        7.1,
        1,
        "semantic domains",
        "The map groups by directory, not by topic — and the bucket axis only half-fixes it",
        f"{total} notes  ·  {data['themed']} carry a live interest theme  ·  "
        f"gold = grouped by topic, blue = grouped by path or project slug, "
        f"grey = other/unplaced",
    )
    axes = fig.subplots(1, 3)
    fig.subplots_adjust(left=0.105, right=0.972, top=top - 0.055, bottom=0.10, wspace=0.60)

    bars(axes[0], data["before"], total)
    panel_title(
        axes[0],
        "before — the shipped legend: 7 directory slugs, "
        "2 themes, and a quarter of the map in `other`",
    )
    bars(axes[1], data["after_excluded"], total)
    panel_title(
        axes[1],
        "after — buckets, hackathons left unplaced: every theme "
        "wakes up, but a third of the map goes grey",
    )
    bars(axes[2], data["after_bucketed"], total)
    panel_title(
        axes[2],
        "after — hackathons as their own bucket: 84% placed, and `epicmap` still owns half the map",
    )
    save(fig, "01-before-after-histogram.png")


def fig02(data: dict) -> None:
    import numpy as np

    ns = data["null"]
    matched = ns["arms"]["content-centred / content null"]
    fig, top = figure(
        13.6,
        6.5,
        2,
        "semantic domains",
        "The theme floor is unstable, not stingy — and the null you pick decides the verdict",
        f"{ns['n_content']} content notes  ·  null centroids built from random "
        f"notes at the real theme sizes, 60 draws",
    )
    axes = fig.subplots(1, 2)
    fig.subplots_adjust(left=0.20, right=0.975, top=top - 0.055, bottom=0.115, wspace=0.30)

    ax = axes[0]
    tags = list(ns["arms"])
    seps = [ns["arms"][t]["sep"] for t in tags]
    ys = range(len(tags))
    ax.barh(list(ys), seps, color=[GOLD if abs(s) >= 1 else BLUE for s in seps], height=0.6)
    ax.set_yticks(list(ys))
    ax.set_yticklabels([textwrap.fill(t, 20) for t in tags], fontsize=8.5)
    ax.invert_yaxis()
    ax.axvline(0, color=MUTED, linewidth=0.8)
    anchor = ns["anchor"]["sep"]
    ax.axvline(anchor, color=DIM, linestyle="--", linewidth=1.2)
    ax.text(
        anchor + 0.10,
        -0.78,
        f"{anchor:.2f} sd — where a KNOWN-real partition\n(source platform) lands on this same test",
        color=MUTED,
        fontsize=7.6,
        va="center",
    )
    # Headroom above the first bar for that annotation, on an inverted axis.
    ax.set_ylim(len(tags) - 0.45, -1.15)
    for y, s in zip(ys, seps):
        ax.text(
            s + (0.08 if s >= 0 else -0.08),
            y,
            f"{s:.2f}",
            color=TEXT,
            fontsize=8,
            va="center",
            ha="left" if s >= 0 else "right",
        )
    ax.set_xlabel("separation, (real median − null median) / null sd")
    ax.set_xlim(-0.9, 5.2)
    style_axes(ax)
    panel_title(ax, "same data, four nulls: the disagreement is the finding")

    ax = axes[1]
    real, null = np.array(matched["real"]), np.array(matched["null"])
    bins = np.linspace(0, max(real.max(), null.max()), 46)
    ax.hist(null, bins=bins, color=DIM, alpha=0.95, label="null (chance centroids)", density=True)
    ax.hist(real, bins=bins, color=GOLD, alpha=0.72, label="assigned theme", density=True)
    # Staggered heights: the two markers sit close enough to collide.
    for (val, lab), h in zip(
        [(matched["null_p95"], "null p95"), (matched["null_p99"], "null p99")], (0.62, 0.50)
    ):
        ax.axvline(val, color=BLUE, linestyle="--", linewidth=1.1)
        ax.text(val, ax.get_ylim()[1] * h, f" {lab}", color=BLUE, fontsize=7.6, va="top")
    ax.set_xlabel("max cosine to best centroid (content-centred)")
    ax.set_ylabel("density")
    style_axes(ax)
    legend(ax)
    panel_title(
        ax,
        "the matched arm: themes do beat chance, but a null-derived "
        "floor would place 120/393, not 295",
    )
    save(fig, "02-theme-floor-null.png")


def legend(ax, **kw):
    leg = ax.legend(frameon=False, fontsize=8, **kw)
    for text in leg.get_texts():
        text.set_color(MUTED)
    return leg


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="recompute from chroma")
    args = ap.parse_args()
    data = load(args.refresh)
    fig01(data)
    fig02(data)


if __name__ == "__main__":
    main()
