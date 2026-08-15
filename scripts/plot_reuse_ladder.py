"""Figure for section 40 — the reuse ladder (#96 rung 2).

One claim: reuse of captured knowledge is real and runs through elective
source-note reads inside work sessions — while the citation channel the issue
expected to be the strongest evidence is nearly empty.

Run: uv run --with matplotlib python scripts/plot_reuse_ladder.py [--out DIR]
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plot_assets import (
    BG,
    BLUE,
    CYAN,
    DIM,
    DPI,
    GOLD,
    MARGIN,
    MUTED,
    PURPLE,
    TEXT,
    figure,
    frame_panels,
    panel_title,
    style_axes,
    verdict,
)

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "experiments" / "reuse_ladder_results.json"
OUT = (
    Path(sys.argv[sys.argv.index("--out") + 1])
    if "--out" in sys.argv
    else (ROOT / "docs" / "assets" / "40-reuse-ladder")
)


def main() -> None:
    R = json.loads(RESULTS.read_text())
    lad, briefs = R["ladder"], R["briefs"]

    meta = (
        f"{lad['vault_read_sessions']} vault-reading sessions, {lad['source_read_sessions']} "
        f"elective source-read sessions ({lad['source_read_sessions_with_work']} modified work "
        f"outside the vault)  |  {lad['distinct_source_notes_read']} distinct source notes read  |  "
        f"{briefs['briefs_scanned']} session briefs hold {briefs['genuine_wikilinks']} genuine "
        f"wikilinks and {briefs['source_note_refs']} source-note reference  |  commit {R['commit']}"
    )
    fig, top = figure(
        15,
        6.2,
        1,
        "the reuse ladder",
        "Knowledge does come back — through elective reads, not through citations",
        meta,
    )
    axes = fig.subplots(1, 2)
    fig.subplots_adjust(
        left=MARGIN + 0.012, right=1 - MARGIN, top=top - 0.05, bottom=0.15, wspace=0.18
    )

    # (a) the ladder, in notes — each rung a stronger claim about one note
    ax = axes[0]
    bars = [
        ("embedded corpus", 671, DIM),
        ("read inside sessions, any folder (all time)", 153, BLUE),
        ("elective source-note reads (all time)", lad["distinct_source_notes_read"], CYAN),
        ("served to a genuine search (15 d)", 55, GOLD),
        ("cited in a session brief (56 briefs)", briefs["source_note_refs"], PURPLE),
    ]
    y = np.arange(len(bars))[::-1]
    for yy, (label, val, color) in zip(y, bars):
        ax.barh(yy, val, color=color, height=0.5)
        ax.text(val + 8, yy, f"{val}", color=TEXT, fontsize=10, va="center")
        ax.text(4, yy + 0.38, label, color=MUTED, fontsize=8.5, va="bottom")
    ax.set_yticks([])
    ax.set_ylim(-0.55, len(bars) - 1 + 1.0)
    ax.set_xlim(0, 671 * 1.12)
    ax.set_xlabel("notes")
    panel_title(ax, "evidence per note, weakest claim to strongest")

    # (b) source-reading sessions per week, split by whether work followed
    ax = axes[1]

    def week(d: str) -> str:
        dt = date.fromisoformat(d)
        iso = dt.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"

    work = Counter(week(s["date"]) for s in R["source_read_sessions"] if s["produced_work"])
    readonly = Counter(week(s["date"]) for s in R["source_read_sessions"] if not s["produced_work"])
    # continuous week axis — skipping empty weeks would compress time
    from datetime import timedelta

    dates = [date.fromisoformat(s["date"]) for s in R["source_read_sessions"]]
    d, weeks = min(dates), []
    while d <= max(dates):
        if week(d.isoformat()) not in weeks:
            weeks.append(week(d.isoformat()))
        d += timedelta(days=7)
    x = np.arange(len(weeks))
    w = np.array([work.get(k, 0) for k in weeks])
    r = np.array([readonly.get(k, 0) for k in weeks])
    ax.bar(x, w, color=BLUE, width=0.8, label="session modified work outside the vault")
    ax.bar(x, r, bottom=w, color=DIM, width=0.8, label="read only")
    ax.set_xticks(x[::2], [k[5:] for k in weeks[::2]], rotation=45)
    ax.set_ylabel("source-reading sessions / week")
    leg = ax.legend(loc="upper left", frameon=False, fontsize=8.5)
    for t in leg.get_texts():
        t.set_color(MUTED)
    panel_title(ax, "when the loop closes, by week")

    for ax in axes:
        style_axes(ax)
    verdict(
        fig,
        f"{lad['source_read_sessions']} elective source-read sessions, "
        f"{lad['source_read_sessions_with_work']} fed work — and 56 briefs cite 1 source note",
    )
    frame_panels(fig)
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / "01-reuse-ladder.png", dpi=DPI, facecolor=BG)
    print("wrote 01-reuse-ladder.png")


if __name__ == "__main__":
    main()
