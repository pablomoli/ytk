"""Trace inventory for #96 — what the second brain already records (section 39).

Mines every trace that exists today, with zero new instrumentation: the served-
results log (store.py, #150 A4), the hub's typed-search log, the capture log,
claude-mem sessions/observations, the interest snapshots (with #83 lifecycle
events), and the live store. Produces the numbers behind the first acceptance
report: what was captured, what was retrieved and by whom, what was reused,
where retrieval evidence is missing.

Actor attribution is layered, weakest-last: hub search.jsonl rows are
user-certain; retrieval events inside a claude-mem session window are
agent-likely; everything else is ambiguous and reported as such.

Run: uv run python experiments/trace_inventory.py
Writes experiments/trace_inventory_results.json.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

os.environ["YTK_RETRIEVAL_LOG"] = "off"  # this script must never write the trace it reads

HOME = Path.home()
YTK = HOME / ".ytk"
MEM_DB = HOME / ".claude-mem" / "claude-mem.db"
OUT = Path(__file__).with_name("trace_inventory_results.json")

_FIXTURE = re.compile(r"^(vid|seg|doc|note)\d+$|^v\d$")


def _ts(s: str) -> float:
    return datetime.fromisoformat(s).timestamp()


def _tokens(q: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", q.lower()) if len(t) > 2}


def load_retrieval() -> list[dict]:
    rows = []
    for line in (YTK / "retrieval_log.jsonl").read_text().splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def search_events(rows: list[dict]) -> list[dict]:
    """Group served-result rows into search events keyed by (ts, surface, query)."""
    events: dict[tuple, dict] = {}
    for r in rows:
        key = (r["ts"], r["surface"], r["query"])
        ev = events.setdefault(
            key, {"ts": r["ts"], "surface": r["surface"], "query": r["query"], "docs": []}
        )
        ev["docs"].append(r["doc_id"])
    return sorted(events.values(), key=lambda e: e["ts"])


def session_windows() -> list[tuple[float, float]]:
    """(start, end) epochs of every claude-mem SDK session, all projects.

    Sessions without a completed stamp get last-observation + 15 min: an agent
    can retrieve at any point while its session is open.
    """
    con = sqlite3.connect(f"file:{MEM_DB}?mode=ro", uri=True)
    cur = con.execute(
        """SELECT s.started_at_epoch, s.completed_at_epoch,
                  (SELECT MAX(o.created_at_epoch) FROM observations o
                   WHERE o.memory_session_id = s.memory_session_id)
           FROM sdk_sessions s"""
    )
    win = []
    for start, done, last_obs in cur:
        end = done or (last_obs and last_obs + 900) or (start + 900)
        # epochs are stored in ms in some rows; normalize to seconds
        start = start / 1000 if start > 4e10 else start
        end = end / 1000 if end > 4e10 else end
        if end > start:
            win.append((float(start), float(end)))
    con.close()
    return sorted(win)


def in_any_window(ts: float, windows: list[tuple[float, float]]) -> bool:
    import bisect

    i = bisect.bisect_right(windows, (ts, float("inf")))
    for s, e in windows[max(0, i - 50) : i]:
        if s <= ts <= e:
            return True
    return False


def mem_stats() -> dict:
    con = sqlite3.connect(f"file:{MEM_DB}?mode=ro", uri=True)
    q = lambda sql: con.execute(sql).fetchall()
    out = {
        "sessions_total": q("SELECT count(*) FROM sdk_sessions")[0][0],
        "sessions_ytk": q("SELECT count(*) FROM sdk_sessions WHERE project='ytk'")[0][0],
        "observations_total": q("SELECT count(*) FROM observations")[0][0],
        "observations_ytk": q("SELECT count(*) FROM observations WHERE project='ytk'")[0][0],
        "obs_reading_vault": q(
            "SELECT count(*) FROM observations WHERE files_read LIKE '%second-brain%'"
        )[0][0],
        "obs_span": q("SELECT min(created_at), max(created_at) FROM observations")[0],
    }
    # distinct vault notes named in files_read (explicit paths only, globs excluded)
    notes: set[str] = set()
    for (fr,) in q("SELECT files_read FROM observations WHERE files_read LIKE '%second-brain%'"):
        for m in re.finditer(r"second-brain/([^\"',\\]+?\.md)", fr or ""):
            path = m.group(1)
            if "*" not in path:
                notes.add(path)
    out["distinct_vault_notes_read"] = len(notes)
    out["vault_notes_read_by_folder"] = dict(Counter(p.split("/")[0] for p in notes).most_common())
    con.close()
    return out


def main() -> None:
    from ytk.config import load_config
    from ytk.store import get_all_videos, get_content_memories

    cfg = load_config()
    notes = get_all_videos() + get_content_memories(cfg.interest.content_sources)
    store_ids = {n["id"] for n in notes}
    captured_at = {n["id"]: n.get("captured_at", "") for n in notes}

    rows = load_retrieval()
    events = search_events(rows)

    # Classification layers, checked in order. The log is dominated by the
    # system examining itself; each layer peels one instrument off:
    #   fixture     - unit-test doc ids (vid1, seg2, ...)
    #   eval-replay - a query from the frozen retrieval-gate set (#85)
    #   test-suite  - the recurring smoke block: non-eval queries recurring on
    #                 4+ distinct days are dev-suite probes, not demand
    #   burst       - programmatic sweeps (6+ events with 6+ distinct queries
    #                 inside 60s): recall harnesses, e2 sets, thesis pipelines
    #   interactive - the residue: genuine retrieval demand
    eval_qs = {
        json.loads(x)["query"].lower().strip()
        for x in (Path(__file__).resolve().parents[1] / "eval/retrieval/queries.jsonl")
        .read_text()
        .splitlines()
        if x.strip()
    }
    non_eval = [e for e in events if e["query"].lower().strip() not in eval_qs]
    qdays_all: dict[str, set[str]] = {}
    for e in non_eval:
        qdays_all.setdefault(e["query"].lower().strip(), set()).add(e["ts"][:10])
    suite_queries = {q for q, d in qdays_all.items() if len(d) >= 4}

    stamps = sorted(_ts(e["ts"]) for e in non_eval)

    def burst_score(ts: float) -> int:
        import bisect

        lo = bisect.bisect_left(stamps, ts - 30)
        hi = bisect.bisect_right(stamps, ts + 30)
        return hi - lo

    for e in events:
        q = e["query"].lower().strip()
        if all(_FIXTURE.match(d) for d in e["docs"]):
            e["class"] = "fixture"
        elif q in eval_qs:
            e["class"] = "eval-replay"
        elif q in suite_queries:
            e["class"] = "test-suite"
        elif burst_score(_ts(e["ts"])) >= 6:
            e["class"] = "burst"
        else:
            e["class"] = "interactive"
    interactive = [e for e in events if e["class"] == "interactive"]

    # actor layers on the interactive residue
    windows = session_windows()
    hub_log = [
        json.loads(x) for x in (YTK / "logs" / "search.jsonl").read_text().splitlines() if x.strip()
    ]
    hub_queries = {(h["ts"], h["q"]) for h in hub_log}
    for e in interactive:
        if (e["ts"], e["query"]) in hub_queries:
            e["actor"] = "user-hub"
        elif in_any_window(_ts(e["ts"]), windows):
            e["actor"] = "agent-likely"
        else:
            e["actor"] = "ambiguous"
    real_events = interactive

    # reformulation chains: successive events within 5 min sharing >= 30% tokens
    chains = 0
    chain_lens: list[int] = []
    cur_len = 1
    from itertools import pairwise

    for a, b in pairwise(real_events):
        ta, tb = _tokens(a["query"]), _tokens(b["query"])
        overlaps = ta and tb and len(ta & tb) / len(ta | tb) >= 0.3
        if _ts(b["ts"]) - _ts(a["ts"]) <= 300 and overlaps and a["query"] != b["query"]:
            cur_len += 1
        else:
            if cur_len > 1:
                chains += 1
                chain_lens.append(cur_len)
            cur_len = 1
    if cur_len > 1:
        chains += 1
        chain_lens.append(cur_len)

    # served-doc concentration and coverage
    served = Counter()
    for e in real_events:
        for d in e["docs"]:
            served[d.split("@")[0]] += 1
    served_note_ids = {d for d in served if d in store_ids}
    top10 = served.most_common(10)
    top10_share = sum(c for _, c in top10) / sum(served.values())

    # age at retrieval (days), for events with resolvable capture stamps
    ages = []
    for e in real_events:
        ets = _ts(e["ts"])
        for d in e["docs"]:
            ca = captured_at.get(d.split("@")[0], "")
            if ca:
                try:
                    ages.append((ets - _ts(ca)) / 86400)
                except ValueError:
                    pass
    ages = [a for a in ages if a >= 0]
    ages.sort()
    pct = lambda p: round(ages[int(p * (len(ages) - 1))], 1) if ages else None

    # recurring queries across distinct days
    qdays: dict[str, set[str]] = {}
    for e in real_events:
        qdays.setdefault(e["query"].lower().strip(), set()).add(e["ts"][:10])
    recurring = {q: len(d) for q, d in qdays.items() if len(d) >= 2}

    caps = [
        json.loads(x) for x in (YTK / "capture_log.jsonl").read_text().splitlines() if x.strip()
    ]

    # snapshot lifecycle events (#83 backfill)
    snap_events = Counter()
    snap_files = sorted((YTK / "interest").glob("snapshot-*.json"))
    for p in snap_files:
        s = json.loads(p.read_text())
        snap_events.update(e["kind"] for e in s.get("events", []))
    latest = json.loads((YTK / "interest" / "latest.json").read_text())

    events_by_day = Counter(e["ts"][:10] for e in real_events)
    result = {
        "commit": subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True
        ).stdout.strip(),
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
        "retrieval": {
            "rows": len(rows),
            "search_events": len(events),
            "by_class": dict(Counter(e["class"] for e in events)),
            "interactive_events": len(real_events),
            "span": [rows[0]["ts"], rows[-1]["ts"]],
            "by_surface": dict(Counter(e["surface"] for e in real_events)),
            "by_actor": dict(Counter(e["actor"] for e in real_events)),
            "events_per_day": dict(sorted(events_by_day.items())),
            "events_per_day_by_class": {
                c: dict(sorted(Counter(e["ts"][:10] for e in events if e["class"] == c).items()))
                for c in ("eval-replay", "test-suite", "burst", "fixture", "interactive")
            },
            # No query text in the persisted results: the repo is public and
            # interactive queries are the owner's. Dates, surfaces, actors only.
            "interactive_events_list": [
                {"ts": e["ts"], "surface": e["surface"], "actor": e["actor"]} for e in real_events
            ],
            "distinct_queries": len(qdays),
            "recurring_queries": len(recurring),
            "reformulation_chains": chains,
            "chain_length_max": max(chain_lens, default=1),
            "distinct_docs_served": len(served),
            "top10_doc_share": round(top10_share, 3),
            "top_docs": top10,
            "corpus_served_coverage": round(len(served_note_ids) / len(store_ids), 3),
            "never_served": len(store_ids) - len(served_note_ids),
            "age_at_retrieval_days": {
                "n": len(ages),
                "p50": pct(0.5),
                "p90": pct(0.9),
                "p10": pct(0.1),
            },
        },
        "hub_search_log": {"rows": len(hub_log), "entries": hub_log},
        "capture": {
            "rows": len(caps),
            "span": [caps[0]["ts"], caps[-1]["ts"]] if caps else None,
            "by_surface": dict(Counter(c.get("surface", "?") for c in caps)),
            "by_source": dict(Counter(c.get("source", "?") for c in caps)),
            "by_outcome": dict(Counter(c.get("outcome", "?") for c in caps)),
            "per_day": dict(sorted(Counter(c["ts"][:10] for c in caps).items())),
        },
        "claude_mem": mem_stats(),
        "store": {
            "embedded_notes": len(store_ids),
            "captured_at_coverage": round(
                sum(1 for v in captured_at.values() if v) / len(captured_at), 3
            ),
        },
        "snapshots": {
            "count": len(snap_files),
            "lifecycle_events": dict(snap_events),
            "themes_now": len(latest["themes"]),
            "signal_counts": latest.get("signal_counts", {}),
        },
    }
    OUT.write_text(json.dumps(result, indent=1))
    r = result["retrieval"]
    print(
        json.dumps(
            {k: v for k, v in r.items() if k not in ("events_per_day", "top_docs")},
            indent=1,
        )
    )
    print("actors:", r["by_actor"])
    print(
        "claude-mem:",
        {k: v for k, v in result["claude_mem"].items() if k != "vault_notes_read_by_folder"},
    )
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
