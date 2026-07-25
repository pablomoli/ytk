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


def compute() -> dict:
    from scripts.grove_lab.buckets import resolve_notes

    _vecs, meta, notes = resolve_notes()
    return {
        "total": len(notes),
        "themed": sum(1 for n in notes if n.theme),
        "cats": dict(Counter(m["cat"] for m in meta).most_common()),
        "before": before_counts(),
        "after_excluded": after_counts(with_hackathons=False),
        "after_bucketed": after_counts(with_hackathons=True),
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="recompute from chroma")
    args = ap.parse_args()
    fig01(load(args.refresh))


if __name__ == "__main__":
    main()
