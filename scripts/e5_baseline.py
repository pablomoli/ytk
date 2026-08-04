"""E5 (#149): capture-outcome baseline — the instrument measured its own tests.

Reads ~/.ytk/capture_log.jsonl (live since 16ce972, 2026-07-29). The headline
is not a loss rate: 92% of records are pytest fixtures, because the test suite
never sets YTK_CAPTURE_LOG=off. After decontamination, 17 genuine captures
remain — and the feed surface (the bulk path #148 moves overnight) logs
note_found=None, so the silent-loss class is unmeasured exactly where it
matters. Both defects are the baseline: the current pipeline cannot see its
own losses.

Writes e5-capture-baseline.png and e5-capture-baseline.json.

    uv run --with matplotlib python scripts/e5_baseline.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from memory_field_audits import OUTDIR, figure, footer, save, stamp
from plot_assets import BLUE, GOLD, MARGIN, MUTED, RED, TEXT, panel_title, style_axes

LOG = Path.home() / ".ytk" / "capture_log.jsonl"

# Fixture vocabulary of the polluting test suites: short placeholder codes plus
# the one session hash their imessage fixture reuses. A record is test-born
# when its content id is one of these, never by duration or date.
_FIXTURE_CODES = frozenset(
    ["abc", "bad", "poison", "steer", "def", "one", "two", "three", "a", "b", "c", "ok"]
)
_FIXTURE_SESSIONS = frozenset(["imessage:session:a5cbc5878a2101a6"])
_CODE = re.compile(r"(?:reel|reels|p|tv)/([\w-]+)|youtu\.be/([\w-]+)|watch\?v=([\w-]+)")


def content_code(url: str) -> str | None:
    match = _CODE.search(url)
    if not match:
        return None
    return next((g for g in match.groups() if g), None)


def is_fixture(record: dict) -> bool:
    if record["url"] in _FIXTURE_SESSIONS or "example.com" in record["url"]:
        return True
    return content_code(record["url"]) in _FIXTURE_CODES


def main() -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.style.use("dark_background")

    records = [json.loads(line) for line in LOG.read_text().splitlines() if line.strip()]
    genuine = [r for r in records if not is_fixture(r)]
    polluted = len(records) - len(genuine)

    verified = [r for r in genuine if r.get("note_found") is True]
    unverifiable = [r for r in genuine if r["outcome"] == "ok" and r.get("note_found") is None]
    silent = [r for r in genuine if r["outcome"] == "ok" and r.get("note_found") is False]
    errors = [r for r in genuine if r["outcome"] != "ok"]

    days = sorted({r["ts"][:10] for r in records})
    per_day = {
        d: {
            "test fixtures": sum(1 for r in records if is_fixture(r) and r["ts"][:10] == d),
            "genuine": sum(1 for r in genuine if r["ts"][:10] == d),
        }
        for d in days
    }

    results = {
        "stamp": stamp(),
        "log": str(LOG),
        "records": len(records),
        "test_pollution": polluted,
        "genuine": len(genuine),
        "genuine_records": genuine,
        "verified_ok": len(verified),
        "ok_unverifiable": len(unverifiable),
        "silent_partials": len(silent),
        "errors": len(errors),
        "error_reasons": dict(Counter((r.get("error") or "?")[:60] for r in errors)),
        "per_day": per_day,
        "instrument_defects": [
            "test suites append to the production log: YTK_CAPTURE_LOG is never "
            "set to 'off' under pytest, so 195/212 records are fixtures",
            "the feed surface logs note_found=None: the silent-loss class is "
            "unmeasured on the bulk path #148 targets",
        ],
    }
    (OUTDIR / "e5-capture-baseline.json").write_text(json.dumps(results, indent=2))
    print(
        json.dumps(
            {
                k: results[k]
                for k in (
                    "records",
                    "test_pollution",
                    "genuine",
                    "verified_ok",
                    "ok_unverifiable",
                    "silent_partials",
                    "errors",
                )
            },
            indent=2,
        )
    )

    fig, top = figure(
        15,
        7.6,
        5,
        "e5 · capture baseline",
        "The baseline instrument spent six days measuring its own test suite",
        f"{len(records)} log records since 2026-07-29  ·  {polluted} pytest fixtures "
        f"({100 * polluted // len(records)}%)  ·  {len(genuine)} genuine: {len(verified)} "
        f"verified, {len(unverifiable)} unverifiable, {len(errors)} error",
    )
    gs = fig.add_gridspec(
        1,
        3,
        width_ratios=[1.2, 1.0, 1.0],
        left=MARGIN + 0.025,
        right=1 - MARGIN - 0.01,
        top=top,
        bottom=0.215,
        wspace=0.34,
    )

    ax = fig.add_subplot(gs[0])
    xs = range(len(days))
    test_vals = [per_day[d]["test fixtures"] for d in days]
    real_vals = [per_day[d]["genuine"] for d in days]
    ax.bar(xs, test_vals, color=MUTED, width=0.62, alpha=0.55, label="test fixtures")
    ax.bar(xs, real_vals, bottom=test_vals, color=GOLD, width=0.62, label="genuine")
    ax.set_xticks(list(xs), [d[5:] for d in days])
    ax.set_ylim(0, max(t + r for t, r in zip(test_vals, real_vals)) * 1.12)
    style_axes(ax)
    ax.legend(fontsize=8.5, framealpha=0.0, labelcolor=TEXT)
    panel_title(ax, "log records per day — pollution vs signal")

    ax = fig.add_subplot(gs[1])
    cats = [
        ("verified\n(note found)", len(verified), GOLD),
        ("ok, never\nverified (feed)", len(unverifiable), BLUE),
        ("silent partial\n(ok, no note)", len(silent), MUTED),
        ("hard error", len(errors), RED),
    ]
    bars = ax.barh([c[0] for c in cats], [c[1] for c in cats], color=[c[2] for c in cats])
    peak = max(c[1] for c in cats)
    for bar, (_, v, _) in zip(bars, cats):
        ax.text(
            bar.get_width() + peak * 0.03,
            bar.get_y() + bar.get_height() / 2,
            str(v),
            color=TEXT,
            fontsize=10,
            va="center",
        )
    ax.set_xlim(0, peak * 1.2)
    ax.invert_yaxis()
    style_axes(ax)
    panel_title(ax, f"the {len(genuine)} genuine captures, by what we can say")

    ax = fig.add_subplot(gs[2])
    surfaces = ["hub", "feed"]
    know = [
        sum(1 for r in genuine if r["surface"] == s and r.get("note_found") is not None)
        for s in surfaces
    ]
    blind = [
        sum(
            1
            for r in genuine
            if r["surface"] == s and r["outcome"] == "ok" and r.get("note_found") is None
        )
        for s in surfaces
    ]
    err = [sum(1 for r in genuine if r["surface"] == s and r["outcome"] != "ok") for s in surfaces]
    xs2 = range(len(surfaces))
    ax.bar(xs2, know, color=GOLD, width=0.5, label="note verified")
    ax.bar(xs2, blind, bottom=know, color=RED, width=0.5, label="note never checked")
    ax.bar(
        xs2,
        err,
        bottom=[a + b for a, b in zip(know, blind)],
        color="#8f2740",
        width=0.5,
        label="error",
    )
    ax.set_xticks(list(xs2), surfaces)
    ax.set_ylim(0, max(k + b + e for k, b, e in zip(know, blind, err)) * 1.45)
    style_axes(ax)
    ax.legend(fontsize=8.5, framealpha=0.0, labelcolor=TEXT, loc="upper center", ncols=1)
    panel_title(ax, "loss visibility by surface — feed is blind")

    footer(
        fig,
        f"{stamp()}  ·  registered amendment: the two-week window (07-29 to 08-12) closed at day "
        f"6 — not because the signal saturated, but because the instrument is defective twice "
        f"over (pytest pollutes the log; feed never verifies notes) and genuine traffic is ~3 "
        f"items/day, which no fortnight can power. The fault-injection matrix, not the calendar, "
        f"carries E5's before/after comparison. Confounds: fixture detection is by placeholder "
        f"content id, so a real capture using a short id would be miscounted; the one hard error "
        f"(tiktok add, exit 1 after 192s) is visible only because the instrumentation exists.",
    )
    save(fig, "e5-capture-baseline.png")


if __name__ == "__main__":
    main()
