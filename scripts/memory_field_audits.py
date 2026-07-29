"""Rung 0 of #150 — the free audits: three baseline figures, no builds.

    uv run --with matplotlib python scripts/memory_field_audits.py           # all
    uv run --with matplotlib python scripts/memory_field_audits.py --only a1

A1 duplicate density   — pairwise cosine over ytk_memories (gates R1, #151 D1)
A2 timestamp integrity — mtime vs best-known capture date (gates R5)
A3 memo bursts         — inter-memo gaps, launch-day test traffic excluded (gates R8)

Figures land in docs/assets/memory-field/, commit + date stamped in the
footer. Confounds are named in the caption, not discovered by a reader.
"""

from __future__ import annotations

import argparse
import itertools
import re
import subprocess
import sys
import textwrap
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plot_assets import (
    BG,
    BLUE,
    FRAME,
    GOLD,
    MARGIN,
    MUTED,
    RED,
    TEXT,
    frame_panels,
    panel_title,
    style_axes,
)

OUTDIR = Path(__file__).resolve().parents[1] / "docs" / "assets" / "memory-field"

# Launch-day memo traffic was feature testing, not real capture; the workflow
# critic caught that the obvious "burst" was this window (#150 A3).
LAUNCH_DAY = "2026-07-05"
LAUNCH_DAY_CUTOFF_HOUR = 18

DATE_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2})")
MEMO_STAMP = re.compile(r"^(\d{4}-\d{2}-\d{2})-(\d{2})(\d{2})-")
FRONTMATTER_DATE = re.compile(r"^date:\s*['\"]?(\d{4}-\d{2}-\d{2})", re.MULTILINE)


def stamp() -> str:
    sha = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return f"{sha} · {datetime.now():%Y-%m-%d}"


def figure(w: float, ht: float, number: int, kicker: str, title: str, meta: str = ""):
    """plot_assets.figure() tuned for this script's narrower canvas: the fog
    figures are wide enough that the kicker's fixed offset clears "FIGURE NN";
    at 10.5in it collides. Same header anatomy, offsets in inches."""
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    fig = plt.figure(figsize=(w, ht), facecolor=BG)
    inch = lambda v: 1 - v / ht
    fig.text(
        MARGIN,
        inch(0.40),
        f"FIGURE {number:02d}",
        color=GOLD,
        fontsize=10,
        fontweight="bold",
        va="baseline",
    )
    fig.text(
        MARGIN + 1.15 / w, inch(0.40), kicker.upper(), color=MUTED, fontsize=9.5, va="baseline"
    )
    fig.text(MARGIN, inch(0.82), title, color=TEXT, fontsize=16, va="baseline")
    fig.add_artist(
        Line2D(
            [MARGIN, 1 - MARGIN],
            [inch(1.02)] * 2,
            transform=fig.transFigure,
            color=FRAME,
            linewidth=1.0,
        )
    )
    y = 1.30
    for line in textwrap.wrap(meta, 118):
        fig.text(MARGIN, inch(y), line, color=MUTED, fontsize=9.5, va="baseline")
        y += 0.24
    # panel_title() draws above the axes, so leave it headroom below the meta
    return fig, inch(y + 0.34)


def footer(fig, text: str) -> None:
    import textwrap as tw

    fig.text(
        MARGIN + 0.01, 0.035, "\n".join(tw.wrap(text, 165)), color=MUTED, fontsize=7.5, va="bottom"
    )


def save(fig, name: str) -> None:
    import matplotlib.pyplot as plt

    frame_panels(fig)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    out = OUTDIR / name
    fig.savefig(out, dpi=200, facecolor=fig.get_facecolor())
    print(f"wrote {out}")
    plt.close(fig)


# --- A1: duplicate density --------------------------------------------------


def memory_embeddings() -> tuple[list[str], np.ndarray]:
    """Base-doc embeddings from ytk_memories (v2 epoch). Chunk tails (`id#i`)
    are excluded so one long memory is one point, not several near-identical
    ones — counting those would inflate duplicate density by construction."""
    from ytk.store import _memories_collection, chroma_field

    col = _memories_collection()
    got = col.get(include=["embeddings"])
    ids = got["ids"]
    embs = np.asarray(chroma_field(got.get("embeddings"), "embeddings"))
    keep = [i for i, doc_id in enumerate(ids) if "#" not in doc_id]
    return [ids[i] for i in keep], embs[keep]


def pair_similarities(embs: np.ndarray) -> np.ndarray:
    normed = embs / np.linalg.norm(embs, axis=1, keepdims=True)
    sims = normed @ normed.T
    return sims[np.triu_indices(len(sims), k=1)]


def is_imported(doc_id: str) -> bool:
    """Bulk-imported claude-mem observation summaries and the April recovery
    dump are one provenance class; organic ytk memories are the other. R1's
    gate reads the organic number — the imports were near-duplicated at
    import time, before neighbor-aware writes could have existed."""
    return "claude-mem" in doc_id or "recovered-2026-04" in doc_id


def a1() -> None:
    ids, embs = memory_embeddings()
    organic_idx = [i for i, d in enumerate(ids) if not is_imported(d)]
    imported_idx = [i for i, d in enumerate(ids) if is_imported(d)]
    strata = {
        "organic": pair_similarities(embs[organic_idx]) if len(organic_idx) > 1 else np.array([]),
        "imported": pair_similarities(embs[imported_idx])
        if len(imported_idx) > 1
        else np.array([]),
    }
    counts = {"organic": len(organic_idx), "imported": len(imported_idx)}

    thresholds = [0.80, 0.85, 0.90]
    per100 = {
        name: {t: float((s >= t).sum()) / max(counts[name], 1) * 100 for t in thresholds}
        for name, s in strata.items()
    }
    meta = (
        f"{len(ids)} memories ({counts['organic']} organic, {counts['imported']} imported) · "
        "near-dup pairs per 100, within-stratum: organic "
        + " / ".join(f"{per100['organic'][t]:.1f}@{t:.2f}" for t in thresholds)
        + " · imported "
        + " / ".join(f"{per100['imported'][t]:.1f}@{t:.2f}" for t in thresholds)
    )

    fig, top = figure(
        10.5,
        6.6,
        1,
        "memory-field rung 0 — gates R1 and #151 D1",
        "Duplicate density in ytk_memories, by provenance",
        meta,
    )
    ax = fig.add_axes([MARGIN + 0.04, 0.16, 1 - 2 * MARGIN - 0.07, top - 0.20])
    style_axes(ax)
    bins = np.linspace(-0.1, 1.0, 120)
    ax.hist(
        strata["imported"],
        bins=bins,
        color=RED,
        alpha=0.55,
        log=True,
        label="imported (claude-mem + recovery)",
    )
    ax.hist(
        strata["organic"], bins=bins, color=BLUE, alpha=0.7, log=True, label="organic ytk memories"
    )
    for t in thresholds:
        ax.axvline(t, color=GOLD, linewidth=0.9, linestyle="--")
        ax.text(
            t, ax.get_ylim()[1] * 0.5, f" {t:.2f}", color=GOLD, fontsize=8.5, rotation=90, va="top"
        )
    ax.legend(loc="upper left", frameon=False, labelcolor=TEXT, fontsize=9)
    ax.set_xlabel("pairwise cosine similarity (within stratum)")
    ax.set_ylabel("pair count (log)")
    panel_title(ax, "Within-stratum pair similarities, candidate thresholds marked")
    footer(
        fig,
        f"{stamp()} · encoder epoch v2 (Qwen3/1024d), embeddings read from the store, not re-embedded · "
        "confound: top raw pairs are adjacent-ID imported summaries, so the R1 gate must read the organic stratum only",
    )
    save(fig, "a1-dup-density.png")

    # measurement over illustration: the organic top pairs are what calibrates
    # the R1 threshold, so surface those for eyeballing, not the import noise
    org_ids = [ids[i] for i in organic_idx]
    org = embs[organic_idx]
    normed = org / np.linalg.norm(org, axis=1, keepdims=True)
    full = normed @ normed.T
    iu = np.triu_indices(len(org_ids), k=1)
    order = np.argsort(full[iu])[::-1][:12]
    print("\ntop organic pairs by similarity:")
    for k in order:
        i, j = iu[0][k], iu[1][k]
        print(f"  {full[i, j]:.3f}  {org_ids[i]}  <->  {org_ids[j]}")


# --- A2: timestamp integrity ------------------------------------------------


def capture_date(path: Path, text: str) -> datetime | None:
    """Best-known capture date: dated filename first, frontmatter `date:` second.
    Notes with neither are unknowns, reported separately — R5's whole point is
    that most source notes carry no capture stamp at all."""
    m = DATE_PREFIX.match(path.name)
    if not m:
        m = FRONTMATTER_DATE.search(text[:2000])
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d")
    except ValueError:
        return None


def a2() -> None:
    from ytk.vault import _get_vault_path

    root = Path(_get_vault_path()) / "second-brain" / "inbox" / "memories"
    known: list[tuple[float, float, datetime]] = []  # (age_days, divergence_days, mtime)
    unknown = 0
    now = datetime.now()
    for path in sorted(root.rglob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        captured = capture_date(path, text)
        if captured is None:
            unknown += 1
            continue
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        known.append(((now - captured).days, abs((mtime - captured).days), mtime))

    ages = np.array([a for a, _, _ in known], dtype=float)
    div = np.array([d for _, d, _ in known], dtype=float)
    mtimes = [m for _, _, m in known]
    frac = float((div > 7).mean()) if len(div) else 0.0
    old = div[ages > 90]
    frac_old = float((old > 7).mean()) if len(old) else 0.0
    # A perfectly linear divergence-vs-age band means one event stamped a
    # constant mtime across the corpus; name the date rather than leave a
    # mystery diagonal in the figure.
    mdays = Counter(m.date().isoformat() for m in mtimes)
    touch_day, touch_n = mdays.most_common(1)[0]
    meta = (
        f"{len(known)} dated notes · {unknown} with no capture stamp · diverging >7d: {frac:.0%} overall, "
        f"{frac_old:.0%} of notes older than 90d (registered prediction: >20%) · "
        f"largest mtime cluster: {touch_n} notes on {touch_day}"
    )

    fig, top = figure(
        10.5, 6.6, 2, "memory-field rung 0 — gates R5", "mtime vs best-known capture date", meta
    )
    w = (1 - 2 * MARGIN - 0.14) / 2
    ax1 = fig.add_axes([MARGIN + 0.05, 0.16, w, top - 0.20])
    ax2 = fig.add_axes([MARGIN + 0.12 + w, 0.16, w, top - 0.20])
    for ax in (ax1, ax2):
        style_axes(ax)
    ax1.hist(np.clip(div, 0, 400), bins=60, color=BLUE, alpha=0.85, log=True)
    ax1.axvline(7, color=GOLD, linewidth=1.0, linestyle="--")
    ax1.set_xlabel("abs(mtime - capture date), days, clipped at 400")
    ax1.set_ylabel("notes (log)")
    panel_title(ax1, "Divergence distribution, 7-day line marked")
    ax2.scatter(ages, div, s=8, color=RED, alpha=0.45, edgecolors="none")
    ax2.axhline(7, color=GOLD, linewidth=1.0, linestyle="--")
    ax2.set_xlabel("note age (days since capture)")
    ax2.set_ylabel("divergence (days)")
    panel_title(ax2, "Divergence vs age: the diagonal is one mass-touch event")
    footer(
        fig,
        f"{stamp()} · scope: inbox/memories only — source notes mostly carry no capture stamp (that gap is R5's target) · "
        f"confound: divergence is dominated by the {touch_day} mass rewrite, not gradual iCloud churn",
    )
    save(fig, "a2-mtime-divergence.png")


# --- A3: memo bursts --------------------------------------------------------


def memo_times(names: list[str]) -> list[datetime]:
    """Parse memo timestamps from filenames, excluding launch-day daytime
    test traffic (before 18:00 on 2026-07-05)."""
    out = []
    for name in names:
        m = MEMO_STAMP.match(name)
        if not m:
            continue
        t = datetime.strptime(f"{m.group(1)} {m.group(2)}:{m.group(3)}", "%Y-%m-%d %H:%M")
        if m.group(1) == LAUNCH_DAY and t.hour < LAUNCH_DAY_CUTOFF_HOUR:
            continue
        out.append(t)
    return sorted(out)


def a3() -> None:
    from ytk.vault import _get_vault_path

    root = Path(_get_vault_path()) / "second-brain" / "inbox" / "memos"
    times = memo_times([p.name for p in root.glob("*.md")])
    gaps_min = np.array(
        [(b - a).total_seconds() / 60 for a, b in itertools.pairwise(times)], dtype=float
    )
    burst_gap = 10.0
    in_burst = int((gaps_min < burst_gap).sum())
    frac = in_burst / len(gaps_min) if len(gaps_min) else 0.0
    span_days = (times[-1] - times[0]).days if times else 0
    meta = (
        f"{len(times)} memos over {span_days} days (launch-day daytime excluded) · "
        f"gaps <{burst_gap:.0f} min: {in_burst}/{len(gaps_min)} ({frac:.0%}) "
        f"(registered prediction: <15%)"
    )

    fig, top = figure(
        10.5, 6.4, 3, "memory-field rung 0 — gates R8", "Inter-memo gap distribution", meta
    )
    ax = fig.add_axes([MARGIN + 0.04, 0.16, 1 - 2 * MARGIN - 0.08, top - 0.20])
    style_axes(ax)
    if len(gaps_min):
        bins = np.logspace(0, np.log10(max(gaps_min.max(), 10)), 40)
        ax.hist(gaps_min, bins=bins, color=BLUE, alpha=0.85)
        ax.set_xscale("log")
        ax.axvline(burst_gap, color=GOLD, linewidth=1.0, linestyle="--")
        ax.text(burst_gap, ax.get_ylim()[1] * 0.9, " 10 min burst line", color=GOLD, fontsize=9)
    ax.set_xlabel("gap to next memo (minutes, log)")
    ax.set_ylabel("gap count")
    panel_title(ax, "Gaps between consecutive memos, post-launch traffic")
    footer(
        fig,
        f"{stamp()} · exclusion: {LAUNCH_DAY} before {LAUNCH_DAY_CUTOFF_HOUR}:00 (feature-test traffic) · "
        "confound: ~small n — R8 is justified on fragment coherence only, never call volume",
    )
    save(fig, "a3-memo-bursts.png")


# --- R5: gc dry-run diff ----------------------------------------------------


def r5() -> None:
    """What mtime-gc would have decided vs date-aware gc, on gc's own scope
    (top-level inbox/memories/*.md), across candidate prune thresholds."""
    from ytk.vault import _get_vault_path, note_capture_date

    mem_dir = Path(_get_vault_path()) / "second-brain" / "inbox" / "memories"
    now = datetime.now()
    notes = list(mem_dir.glob("*.md"))
    ages = {
        p: (
            (now - datetime.fromtimestamp(p.stat().st_mtime)).days,
            (now - note_capture_date(p)).days,
        )
        for p in notes
    }

    thresholds = [30, 60, 90, 180]
    rows = []
    for t in thresholds:
        mtime_prune = {p for p, (m, _) in ages.items() if m > t}
        date_prune = {p for p, (_, d) in ages.items() if d > t}
        rows.append(
            {
                "t": t,
                "agree": len(mtime_prune & date_prune),
                "wrongly_kept": len(date_prune - mtime_prune),  # stale, mtime hid it
                "wrongly_pruned": len(mtime_prune - date_prune),  # fresh, mtime aged it
            }
        )
    meta = f"{len(notes)} memory notes in gc scope · " + "  ".join(
        f"{r['t']}d: {r['wrongly_kept']} hidden-stale / {r['wrongly_pruned']} false-stale"
        for r in rows
    )

    fig, top = figure(
        10.5,
        6.4,
        4,
        "memory-field R5 — the consumer fix, measured",
        "gc dry-run: mtime vs capture-date decisions",
        meta,
    )
    ax = fig.add_axes([MARGIN + 0.05, 0.16, 1 - 2 * MARGIN - 0.09, top - 0.20])
    style_axes(ax)
    x = np.arange(len(thresholds))
    width = 0.28
    ax.bar(
        x - width,
        [r["agree"] for r in rows],
        width,
        color=BLUE,
        alpha=0.8,
        label="both agree: prune",
    )
    ax.bar(
        x,
        [r["wrongly_kept"] for r in rows],
        width,
        color=GOLD,
        alpha=0.9,
        label="hidden stale (mtime would keep)",
    )
    ax.bar(
        x + width,
        [r["wrongly_pruned"] for r in rows],
        width,
        color=RED,
        alpha=0.9,
        label="false stale (mtime would prune)",
    )
    ax.set_xticks(x, [f"{t}d" for t in thresholds])
    ax.set_xlabel("prune threshold")
    ax.set_ylabel("notes")
    ax.legend(loc="upper left", frameon=False, labelcolor=TEXT, fontsize=9)
    panel_title(ax, "Prune decisions per threshold: agreement and both disagreement classes")
    footer(
        fig,
        f"{stamp()} · scope matches gc exactly: top-level inbox/memories/*.md · capture date per note_capture_date "
        "(captured: > dated filename > frontmatter date: > mtime) · confound: notes with no stamp at all fall back to "
        "mtime in both arms and can only agree",
    )
    save(fig, "r5-timestamp-fix.png")


# --- R3 design checkpoint -----------------------------------------------------


def r3sim() -> None:
    """Pre-implementation design sim: state.md write pattern (directives 3+2+1
    pointer-writes/week, seeder rewrite Sundays) under naive prepend-per-write
    vs same-day-merge, cap 10 sections, overflow to archive."""
    weeks, cap = 8, 10

    def simulate(same_day_merge: bool):
        sections: list[tuple[int, str]] = []
        archive = 0
        rows = []
        for w in range(weeks):
            for dow, writes in [(0, 3), (2, 2), (4, 1), (6, 1)]:
                d = w * 7 + dow
                for _ in range(writes):
                    if same_day_merge and sections and sections[0][0] == d:
                        sections[0] = (d, "merged")
                    else:
                        sections.insert(0, (d, "new"))
                while len(sections) > cap:
                    sections.pop()
                    archive += 1
            rows.append((w + 1, len(sections), archive))
        return rows

    naive = simulate(False)
    merged = simulate(True)
    meta = (
        f"write pattern: 3+2+1 directive pointer-writes + 1 seeder rewrite per week · cap {cap} · "
        f"after {weeks} weeks: naive archives {naive[-1][2]} sections (same-day churn), "
        f"same-day-merge archives {merged[-1][2]} (one per active day)"
    )

    fig, top = figure(
        10.5,
        6.4,
        5,
        "memory-field R3 — design checkpoint, simulated before code",
        "state.md history growth: naive prepend vs same-day merge",
        meta,
    )
    ax = fig.add_axes([MARGIN + 0.05, 0.16, 1 - 2 * MARGIN - 0.09, top - 0.20])
    style_axes(ax)
    wk = [r[0] for r in naive]
    ax.plot(wk, [r[2] for r in naive], color=RED, marker="o", label="naive: sections archived")
    ax.plot(
        wk,
        [r[2] for r in merged],
        color=BLUE,
        marker="o",
        label="same-day merge: sections archived",
    )
    ax.plot(
        wk,
        [r[1] for r in merged],
        color=GOLD,
        marker="s",
        linestyle="--",
        label="in-file sections (both cap at 10)",
    )
    ax.set_xlabel("week")
    ax.set_ylabel("sections")
    ax.legend(loc="upper left", frameon=False, labelcolor=TEXT, fontsize=9)
    panel_title(
        ax, "Same-day merge keeps one section per active day; naive archives triplicate churn"
    )
    footer(
        fig,
        f"{stamp()} · decision this figure locked: a second write on the same day replaces that day's section "
        "(within-day granularity is churn, not history) · cap 10 holds ~2.5 weeks in-file, older days grep in the archive",
    )
    save(fig, "r3-design-sim.png")


AUDITS = {"a1": a1, "a2": a2, "a3": a3, "r5": r5, "r3sim": r3sim}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=sorted(AUDITS), default=None)
    args = parser.parse_args()
    for name, fn in AUDITS.items():
        if args.only in (None, name):
            fn()


if __name__ == "__main__":
    main()
