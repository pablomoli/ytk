"""Figures for section 39 — the trace inventory (#96).

Two claims, one figure each. Figure 01: the only retrieval trace on disk is
almost entirely the system examining itself; the interactive residue is 33
events. Figure 02: the capture-retrieval loop is one-sided — capture outruns
genuine retrieval ~17:1, and what retrieval exists runs through the agent.

Run: uv run --with matplotlib python scripts/plot_trace_inventory.py [--out DIR]
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plot_assets import (
    BG,
    BLUE,
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
RESULTS = ROOT / "experiments" / "trace_inventory_results.json"
OUT = (
    Path(sys.argv[sys.argv.index("--out") + 1])
    if "--out" in sys.argv
    else (ROOT / "docs" / "assets" / "39-trace-inventory")
)


def day_range(days: list[str]) -> list[str]:
    lo, hi = date.fromisoformat(min(days)), date.fromisoformat(max(days))
    return [(lo + timedelta(d)).isoformat() for d in range((hi - lo).days + 1)]


def fig01(R: dict) -> None:
    r = R["retrieval"]
    per_class = r["events_per_day_by_class"]
    machine = {}
    for cls in ("eval-replay", "test-suite", "burst", "fixture"):
        for d, n in per_class.get(cls, {}).items():
            machine[d] = machine.get(d, 0) + n
    inter = per_class["interactive"]
    days = day_range(list(machine) + list(inter))
    x = np.arange(len(days))
    m = np.array([machine.get(d, 0) for d in days])
    i = np.array([inter.get(d, 0) for d in days])

    total = r["search_events"]
    meta = (
        f"{r['rows']} served-result rows, {total} search events, {r['span'][0][:10]} to "
        f"{r['span'][1][:10]}  |  eval-replay {r['by_class']['eval-replay']}, burst "
        f"{r['by_class']['burst']}, test-suite {r['by_class']['test-suite']}, fixture "
        f"{r['by_class']['fixture']} = {100 * (1 - r['interactive_events'] / total):.1f}% instrument"
        f"  |  interactive {r['interactive_events']} ({r['by_actor'].get('agent-likely', 0)} in-session,"
        f" {r['by_actor'].get('user-hub', 0)} from the hub)  |  commit {R['commit']}"
    )
    fig, top = figure(
        15,
        6.2,
        1,
        "what the retrieval log actually holds",
        "The only retrieval trace on disk is the system examining itself",
        meta,
    )
    axes = fig.subplots(1, 2)
    fig.subplots_adjust(
        left=MARGIN + 0.012, right=1 - MARGIN, top=top - 0.05, bottom=0.15, wspace=0.18
    )

    ax = axes[0]
    ax.bar(x, m, color=DIM, width=0.8, label="instrument")
    ax.bar(x, i, bottom=m, color=GOLD, width=0.8, label="interactive")
    ax.set_xticks(x[::2], [d[5:] for d in days[::2]], rotation=45)
    ax.set_ylabel("search events / day")
    peak = int(m.max())
    ax.text(
        x[int(np.argmax(m))],
        peak * 0.99,
        "eval-gate replays",
        color=MUTED,
        fontsize=8.5,
        ha="center",
        va="top",
        rotation=90,
    )
    # the gold band is invisible at this scale — that absence is the claim
    ax.annotate(
        "interactive demand:\ninvisible at this scale",
        xy=(x[-4], i[-4] + m[-4] + 8),
        xytext=(x[-6], peak * 0.55),
        color=TEXT,
        fontsize=9,
        ha="center",
        arrowprops={"arrowstyle": "-", "color": MUTED, "linewidth": 0.8},
    )
    panel_title(ax, "all 2302 events, by day")

    ax = axes[1]
    agent = np.zeros(len(days))
    ambig = np.zeros(len(days))
    for e in r["interactive_events_list"]:
        idx = days.index(e["ts"][:10])
        if e["actor"] == "agent-likely":
            agent[idx] += 1
        else:
            ambig[idx] += 1
    ax.bar(x, agent, color=BLUE, width=0.8, label="agent (in-session)")
    ax.bar(x, ambig, bottom=agent, color=PURPLE, width=0.8, label="ambiguous")
    ax.set_xticks(x[::2], [d[5:] for d in days[::2]], rotation=45)
    ax.set_ylabel("interactive searches / day")
    leg = ax.legend(loc="upper right", frameon=False, fontsize=8.5)
    for t in leg.get_texts():
        t.set_color(MUTED)
    panel_title(ax, "the residue: 33 genuine searches, hub: zero")

    for ax in axes:
        style_axes(ax)
    verdict(
        fig,
        "98.6% instrument traffic; real demand is 33 searches in 15 days, and every one of them bypassed the hub",
    )
    frame_panels(fig)
    fig.savefig(OUT / "01-log-composition.png", dpi=DPI, facecolor=BG)
    print("wrote 01-log-composition.png")


def fig02(R: dict) -> None:
    r = R["retrieval"]
    caps = R["capture"]["per_day"]
    inter = r["events_per_day_by_class"]["interactive"]
    days = day_range(list(caps) + list(inter))
    x = np.arange(len(days))
    c = np.array([caps.get(d, 0) for d in days])
    i = np.array([inter.get(d, 0) for d in days])
    ratio = c.sum() / max(i.sum(), 1)

    mem = R["claude_mem"]
    meta = (
        f"captures {R['capture']['rows']} ({R['capture']['by_surface'].get('hub', 0)} hub) vs "
        f"{r['interactive_events']} genuine searches in the same window — {ratio:.0f}:1  |  "
        f"corpus {R['store']['embedded_notes']} notes: {int(r['corpus_served_coverage'] * R['store']['embedded_notes'])} "
        f"ever served to genuine search, {mem['distinct_vault_notes_read']} read inside Claude sessions "
        f"(all time)  |  commit {R['commit']}"
    )
    fig, top = figure(
        15,
        6.2,
        2,
        "the one-sided loop",
        "Capture runs daily; genuine retrieval barely exists — and it belongs to the agent",
        meta,
    )
    axes = fig.subplots(1, 2)
    fig.subplots_adjust(
        left=MARGIN + 0.012, right=1 - MARGIN, top=top - 0.05, bottom=0.15, wspace=0.18
    )

    ax = axes[0]
    ax.bar(x, c, color=GOLD, width=0.8)
    ax.bar(x, -i * 4, color=BLUE, width=0.8)
    ax.axhline(0, color=MUTED, linewidth=0.8)
    ax.set_xticks(x[::2], [d[5:] for d in days[::2]], rotation=45)
    up = [0, 100, 200, 300]
    down = [-20, -40]
    ax.set_yticks(up + down, [str(v) for v in up] + [str(abs(v) // 4) for v in down])
    ax.set_ylabel("captures in  /  searches out")
    ax.text(0.02, 0.95, "captured", color=GOLD, fontsize=9, transform=ax.transAxes, va="top")
    ax.text(
        0.02,
        0.06,
        "searched (4x scale)",
        color=BLUE,
        fontsize=9,
        transform=ax.transAxes,
        va="bottom",
    )
    panel_title(ax, f"in vs out, per day — {ratio:.0f}:1 over the window")

    ax = axes[1]
    total = R["store"]["embedded_notes"]
    served = int(r["corpus_served_coverage"] * total)
    read = mem["distinct_vault_notes_read"]
    bars = [
        ("embedded corpus", total, DIM),
        ("read inside Claude sessions (all time)", read, BLUE),
        ("served to a genuine search (15 d)", served, GOLD),
    ]
    y = np.arange(len(bars))[::-1]
    for yy, (label, val, color) in zip(y, bars):
        ax.barh(yy, val, color=color, height=0.55)
        ax.text(val + 8, yy, f"{val}", color=TEXT, fontsize=10, va="center")
        ax.text(4, yy + 0.42, label, color=MUTED, fontsize=8.5, va="bottom")
    ax.set_yticks([])
    ax.set_ylim(-0.55, len(bars) - 1 + 1.05)
    ax.set_xlim(0, total * 1.12)
    ax.set_xlabel("notes")
    panel_title(ax, "how much of the corpus ever comes back out")

    for ax in axes:
        style_axes(ax)
    verdict(
        fig,
        f"{ratio:.0f} captures per genuine search; {total - served} of {total} notes never served to real demand",
    )
    frame_panels(fig)
    fig.savefig(OUT / "02-one-sided-loop.png", dpi=DPI, facecolor=BG)
    print("wrote 02-one-sided-loop.png")


def main() -> None:
    R = json.loads(RESULTS.read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    fig01(R)
    fig02(R)


if __name__ == "__main__":
    main()
