"""Step 0 of the curator engine (#197): what actually lands, when, and how much
of it passes the owner. No model calls; reads the vault, the capture log and
the reels queue state.

    uv run python scripts/measure_intake.py
"""

from __future__ import annotations

import collections
import datetime as dt
import glob
import json
import os
import re
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib
import numpy as np

matplotlib.use("Agg")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import matplotlib.pyplot as plt
from plot_assets import (
    BG,
    BLUE,
    CYAN,
    DPI,
    GOLD,
    MUTED,
    PURPLE,
    figure,
    frame_panels,
    panel_title,
    style_axes,
    verdict,
)

plt.style.use("dark_background")

LOCAL = ZoneInfo("America/New_York")
OUT_DIR = Path("docs/research/figures")
SOURCES = ("youtube", "instagram", "web", "tiktok")
COLORS = {"youtube": GOLD, "instagram": BLUE, "web": CYAN, "tiktok": PURPLE}
# Fixture URLs written by the test suite land in the real capture log (E5
# baseline autopsy); they are recognisable by placeholder ids.
FIXTURE = re.compile(r"/(abc|bad|xyz|test|example|fake|foo|bar)\b|example\.com|shorts/x")


def vault_root() -> Path:
    for line in Path(".env").read_text().splitlines():
        if line.startswith("OBSIDIAN_VAULT_PATH"):
            return Path(line.split("=", 1)[1].strip().strip('"')) / "second-brain"
    raise SystemExit("OBSIDIAN_VAULT_PATH not in .env")


def captured_at(path: str) -> dt.datetime:
    head = open(path).read(1500)
    m = re.search(r"^captured: (\d{4}-\d{2}-\d{2})", head, re.MULTILINE)
    if m:
        return dt.datetime.fromisoformat(m.group(1)).replace(tzinfo=dt.UTC)
    # Older notes predate the stamp; birth time is the reliable fallback on macOS.
    return dt.datetime.fromtimestamp(os.stat(path).st_birthtime, tz=dt.UTC)


def week_key(t: dt.datetime) -> dt.date:
    d = t.astimezone(LOCAL).date()
    return d - dt.timedelta(days=d.weekday())


def main() -> None:
    root = vault_root()
    notes: dict[str, list[dt.datetime]] = {s: [] for s in SOURCES}
    takes = 0
    ig_ingested_urls: set[str] = set()
    for s in SOURCES:
        for f in glob.glob(str(root / "sources" / s / "*.md")):
            notes[s].append(captured_at(f))
            body = open(f).read()
            if "\n## My take" in body:
                takes += 1
            if s == "instagram":
                m = re.search(r"^url: .*?/(?:reel|p)/([A-Za-z0-9_-]+)", body, re.MULTILINE)
                if m:
                    ig_ingested_urls.add(m.group(1))
    total = sum(len(v) for v in notes.values())

    # Weekly landings by source, full history.
    weeks: dict[dt.date, collections.Counter] = collections.defaultdict(collections.Counter)
    for s, ts in notes.items():
        for t in ts:
            weeks[week_key(t)][s] += 1
    wk = sorted(weeks)
    first, last = wk[0], wk[-1]
    all_weeks = [first + dt.timedelta(days=7 * i) for i in range(((last - first).days // 7) + 1)]
    recent = [w for w in all_weeks if w >= last - dt.timedelta(days=7 * 12)]
    rate_recent = {s: np.mean([weeks[w][s] for w in recent]) for s in SOURCES}

    # Capture log: human hours vs machine hours, fixture rows excluded.
    rows = [json.loads(l) for l in open(os.path.expanduser("~/.ytk/capture_log.jsonl"))]
    real = [r for r in rows if not FIXTURE.search(r["url"])]
    hours = {"hub": np.zeros(24), "sync": np.zeros(24)}
    for r in real:
        h = dt.datetime.fromisoformat(r["ts"]).astimezone(LOCAL).hour
        hours["hub" if r["surface"] in ("hub", "feed") else "sync"][h] += 1

    # Instagram: what landed in the DM thread vs what was ever ingested.
    state = json.load(open(os.path.expanduser("~/.ytk/reels_state.json")))
    pending = [p for p in state["pending"] if p.get("shared_at")]
    landed = collections.Counter(p["shared_at"][:7] for p in pending)
    ingested = collections.Counter(
        t.astimezone(LOCAL).strftime("%Y-%m") for t in notes["instagram"]
    )
    for m in ingested:
        landed[m] += ingested[m]
    months = sorted(landed)
    pass_through = len(notes["instagram"]) / (len(pending) + len(notes["instagram"]))

    # ---------------------------------------------------------------- figure
    meta = (
        f"{total} source notes, {takes} with a take · last 12 weeks: "
        + " · ".join(f"{s} {rate_recent[s]:.1f}/wk" for s in SOURCES)
        + f" · capture log {len(real)}/{len(rows)} rows real · instagram queue {len(pending)} pending"
    )
    fig, top = figure(
        16, 9.5, 1, "STEP 0 · CURATOR ENGINE", "What lands, when, and how much passes me", meta
    )
    gs = fig.add_gridspec(
        2, 2, left=0.055, right=0.975, top=top, bottom=0.075, hspace=0.42, wspace=0.14
    )

    ax = fig.add_subplot(gs[0, :])
    bottom = np.zeros(len(all_weeks))
    x = np.arange(len(all_weeks))
    for s in SOURCES:
        vals = np.array([weeks[w][s] for w in all_weeks], dtype=float)
        ax.bar(x, vals, bottom=bottom, color=COLORS[s], width=0.86, linewidth=0)
        bottom += vals
    ax.set_xlim(-0.6, len(all_weeks) - 0.4)
    ticks = [i for i, w in enumerate(all_weeks) if w.day <= 7]
    ax.set_xticks(ticks)
    ax.set_xticklabels([all_weeks[i].strftime("%b %y") for i in ticks], color=MUTED)
    ax.set_ylabel("notes landed per week", color=MUTED)
    for s in SOURCES:
        ax.plot([], [], color=COLORS[s], lw=6, label=s)
    ax.legend(frameon=False, loc="upper left", labelcolor=MUTED, ncol=4)
    panel_title(ax, "Landings by week, every source note ever written")
    style_axes(ax)

    ax = fig.add_subplot(gs[1, 0])
    hx = np.arange(24)
    ax.bar(hx - 0.2, hours["hub"], width=0.4, color=GOLD, linewidth=0, label="me (hub, feed)")
    ax.bar(hx + 0.2, hours["sync"], width=0.4, color=MUTED, linewidth=0, label="machine (sync)")
    ax.set_xticks(range(0, 24, 3))
    ax.set_xticklabels([f"{h:02d}" for h in range(0, 24, 3)], color=MUTED)
    ax.set_xlabel("hour of day, local", color=MUTED)
    ax.set_ylabel("captures", color=MUTED)
    ax.legend(frameon=False, labelcolor=MUTED)
    panel_title(ax, "When captures happen: my hours vs the machine's")
    style_axes(ax)

    ax = fig.add_subplot(gs[1, 1])
    mx = np.arange(len(months))
    ax.bar(
        mx,
        [landed[m] for m in months],
        color=BLUE,
        alpha=0.35,
        width=0.8,
        linewidth=0,
        label="landed in the DM thread",
    )
    ax.bar(
        mx,
        [ingested.get(m, 0) for m in months],
        color=BLUE,
        width=0.8,
        linewidth=0,
        label="ingested",
    )
    ax.set_xticks(mx)
    ax.set_xticklabels(
        [dt.date.fromisoformat(m + "-01").strftime("%b %y") for m in months],
        color=MUTED,
        rotation=45,
        ha="right",
    )
    ax.set_ylabel("instagram items per month", color=MUTED)
    ax.legend(frameon=False, labelcolor=MUTED)
    panel_title(ax, f"Instagram: {pass_through:.0%} of what lands is ever ingested")
    style_axes(ax)

    verdict(
        fig, f"{sum(rate_recent.values()):.0f} notes/wk land · answer latency has no instrument yet"
    )
    frame_panels(fig)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "step0-intake.png"
    fig.savefig(out, dpi=DPI, facecolor=BG)

    sidecar = {
        "generated": dt.datetime.now(tz=dt.UTC).isoformat(timespec="seconds"),
        "total_notes": total,
        "notes_with_take": takes,
        "weekly_rate_last_12w": {s: round(float(rate_recent[s]), 2) for s in SOURCES},
        "weekly_by_source": {w.isoformat(): dict(weeks[w]) for w in all_weeks},
        "capture_log_rows": len(rows),
        "capture_log_real_rows": len(real),
        "hub_hours_local": hours["hub"].astype(int).tolist(),
        "sync_hours_local": hours["sync"].astype(int).tolist(),
        "instagram_pending": len(pending),
        "instagram_ingested": len(notes["instagram"]),
        "instagram_pass_through": round(pass_through, 4),
        "instagram_by_month": {
            m: {"landed": landed[m], "ingested": ingested.get(m, 0)} for m in months
        },
        "answer_latency": "unmeasured: ingested items leave the pending queue and no timestamp survives",
    }
    (OUT_DIR / "step0-intake.json").write_text(json.dumps(sidecar, indent=1))
    print(
        json.dumps(
            {
                k: v
                for k, v in sidecar.items()
                if k not in ("weekly_by_source", "instagram_by_month")
            },
            indent=1,
        )
    )
    print(out)


if __name__ == "__main__":
    main()
