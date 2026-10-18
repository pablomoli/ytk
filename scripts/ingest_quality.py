"""Corpus-quality instrument for ingestion step 3 (docs/design/ingestion).

Read-only over the curator ledger. Run once before a change to stamp the
baseline, then again with --since <ship date> to compare the cohort that
entered after it. Cohorts split on the item's first take: words (intent or
reaction), reflex with no words, none.

    uv run python scripts/ingest_quality.py
    uv run python scripts/ingest_quality.py --since 2026-10-19
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

from ytk.ledger import ledger_path
from ytk.reels import canonical_url


def _cohort(take: sqlite3.Row | None) -> str:
    if take is None:
        return "no take"
    if take["kind"] == "reflex" and not (take["text"] or "").strip():
        return "reflex, no words"
    return "words"


def measure(conn: sqlite3.Connection, since: str) -> dict[str, Any]:
    items = conn.execute(
        "SELECT id, source, url, provenance FROM items WHERE captured_at >= ? "
        "AND provenance != 'grandfathered'",
        (since,),
    ).fetchall()
    ids = [r["id"] for r in items]
    cohorts: dict[str, dict[str, Any]] = {}
    checks: Counter[str] = Counter()
    for item_id in ids:
        take = conn.execute(
            "SELECT kind, text FROM takes WHERE item_id = ? ORDER BY id LIMIT 1", (item_id,)
        ).fetchone()
        c = cohorts.setdefault(
            _cohort(take),
            {
                "items": 0,
                "enriched": 0,
                "first_round_pass": 0,
                "enrich_calls": 0,
                "bounce_asks": 0,
                "landed_by_grader": 0,
                "landed_by_owner_override": 0,
            },
        )
        c["items"] += 1
        grades = conn.execute(
            "SELECT to_state, detail FROM activity WHERE item_id = ? AND action = 'grade' "
            "ORDER BY id",
            (item_id,),
        ).fetchall()
        enrich_calls = conn.execute(
            "SELECT count(*) FROM activity WHERE item_id = ? AND action = 'enrich'", (item_id,)
        ).fetchone()[0]
        if not enrich_calls:
            continue
        c["enriched"] += 1
        c["enrich_calls"] += enrich_calls
        if grades and grades[0]["to_state"] == "enriched":
            c["first_round_pass"] += 1
        for g in grades:
            try:
                detail = json.loads(g["detail"] or "{}")
            except ValueError:
                continue
            if isinstance(detail, dict):
                for b in detail.get("bounces") or []:
                    if isinstance(b, dict) and b.get("check"):
                        checks[str(b["check"])[:40]] += 1
        c["bounce_asks"] += conn.execute(
            "SELECT count(*) FROM asks WHERE item_id = ? AND kind = 'grader bounce, twice'",
            (item_id,),
        ).fetchone()[0]
        for (reason,) in conn.execute(
            "SELECT reason FROM activity WHERE item_id = ? AND action = 'keep'", (item_id,)
        ):
            if reason == "grader pass":
                c["landed_by_grader"] += 1
            elif reason == "owner accepted as is":
                c["landed_by_owner_override"] += 1

    def count(sql: str) -> int:
        return conn.execute(sql, (since,)).fetchone()[0]

    asks_by_surface = {
        r["provenance"]: r["n"]
        for r in conn.execute(
            "SELECT i.provenance, count(*) n FROM asks a JOIN items i ON i.id = a.item_id "
            "WHERE a.kind = 'intent missing' AND a.created_at >= ? GROUP BY 1",
            (since,),
        )
    }
    seen: Counter[tuple[str, str]] = Counter(
        (r["source"], canonical_url(r["url"]))
        for r in conn.execute("SELECT source, url FROM items")
    )
    connections = conn.execute(
        "SELECT w.choice, count(*) n FROM asks a JOIN answers w ON w.ask_id = a.id "
        "WHERE a.kind = 'connections' AND a.created_at >= ? GROUP BY 1",
        (since,),
    ).fetchall()
    return {
        "since": since,
        "cohorts": cohorts,
        "top_bounce_checks": checks.most_common(8),
        "intent_asks_by_surface": asks_by_surface,
        "intent_expiries": count(
            "SELECT count(*) FROM activity WHERE action = 'expire' AND at >= ?"
        ),
        "expiries_never_presented": count(
            "SELECT count(*) FROM activity x JOIN asks a ON a.item_id = x.item_id "
            "AND a.kind = 'intent missing' JOIN outbox o ON o.ask_id = a.id "
            "WHERE x.action = 'expire' AND o.presented_at IS NULL AND x.at >= ?"
        ),
        "revivals": count("SELECT count(*) FROM activity WHERE action = 'revive' AND at >= ?"),
        "stuck_parks": count(
            "SELECT count(*) FROM activity WHERE action = 'park' AND reason = 'stuck' AND at >= ?"
        ),
        "agent_captures": count(
            "SELECT count(*) FROM activity WHERE action = 'capture' AND actor = 'agent' AND at >= ?"
        ),
        "duplicate_identities_all_time": sum(1 for n in seen.values() if n > 1),
        "connections_answers": {r["choice"]: r["n"] for r in connections},
    }


def _print(report: dict[str, Any]) -> None:
    print(f"since {report['since']}")
    print(
        f"{'cohort':<18}{'items':>6}{'enriched':>9}{'1st pass':>9}"
        f"{'enrich/it':>10}{'bounce asks':>12}{'grader':>8}{'override':>9}"
    )
    for name, c in sorted(report["cohorts"].items()):
        e = c["enriched"] or 1
        print(
            f"{name:<18}{c['items']:>6}{c['enriched']:>9}"
            f"{c['first_round_pass'] / e:>8.0%} {c['enrich_calls'] / e:>9.1f}"
            f"{c['bounce_asks'] / e:>12.2f}{c['landed_by_grader']:>8}"
            f"{c['landed_by_owner_override']:>9}"
        )
    for key in (
        "top_bounce_checks",
        "intent_asks_by_surface",
        "intent_expiries",
        "expiries_never_presented",
        "revivals",
        "stuck_parks",
        "agent_captures",
        "duplicate_identities_all_time",
        "connections_answers",
    ):
        print(f"{key}: {report[key]}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--since", default="0000", help="ISO date; items captured from then on")
    ap.add_argument("--db", type=Path, default=None, help="ledger path (default: the live one)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    path = args.db or ledger_path()
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    report = measure(conn, args.since)
    if args.json:
        print(json.dumps(report, indent=1))
    else:
        _print(report)


if __name__ == "__main__":
    main()
