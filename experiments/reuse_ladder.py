"""Reuse evidence for #96 rung 2 — does captured knowledge ever feed work? (section 40)

Section 39 counted what goes in and what comes back out through search. This
rung climbs the evidence ladder the issue sketched: served results (weakest),
elective source-note reads inside work sessions, source-reading sessions that
modified something outside the vault (knowledge -> work), and session-brief
citations (the issue's hoped-for strongest rung).

Two granularity corrections drive the numbers: observation-level joins
undercount (a session reads a note in one observation and edits code in
another), and vault reads mandated by the session-start ritual (wiki/, inbox/
memories/, projects/) are context loading, not retrieval — the elective signal
is a read under second-brain/sources/.

Privacy: no user prompts or query text are written to the results file — only
dates, projects, and flags. Examples are paraphrased in the section README.

Run: uv run python experiments/reuse_ladder.py
Writes experiments/reuse_ladder_results.json.
"""

from __future__ import annotations

import json
import re
import sqlite3
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

HOME = Path.home()
MEM_DB = HOME / ".claude-mem" / "claude-mem.db"
BRIEFS = (
    HOME / "Library/Mobile Documents/iCloud~md~obsidian/Documents/Vault/second-brain/projects/ytk"
)
OUT = Path(__file__).with_name("reuse_ladder_results.json")

# wikilinks that document the wikilink syntax itself, not cite a note
_FORMAT_ARTIFACTS = {"...", "name", "wikilinks", "their-name"}

_WORK_EXISTS = (
    "EXISTS (SELECT 1 FROM observations o2 WHERE o2.memory_session_id=o1.memory_session_id "
    "AND o2.files_modified IS NOT NULL AND o2.files_modified NOT IN ('','[]') "
    "AND o2.files_modified NOT LIKE '%second-brain%')"
)


def q(con, sql):
    return con.execute(sql).fetchall()


def brief_citations() -> dict:
    wikilinks: Counter = Counter()
    paths: Counter = Counter()
    briefs = sorted(BRIEFS.glob("session-*.md"))
    for p in briefs:
        text = p.read_text(encoding="utf-8")
        for m in re.finditer(r"\[\[([^\]|]+?)(?:\|[^\]]*)?\]\]", text):
            name = m.group(1).strip()
            if name.lower() not in _FORMAT_ARTIFACTS:
                wikilinks[name] += 1
        for m in re.finditer(
            r"\b(?:sources|inbox|wiki|me|notes|decisions|tools|debugging)/[A-Za-z0-9._/ -]+?\.md",
            text,
        ):
            paths[m.group(0)] += 1
    return {
        "briefs_scanned": len(briefs),
        "genuine_wikilinks": sum(wikilinks.values()),
        "distinct_wikilink_targets": len(wikilinks),
        "path_refs": sum(paths.values()),
        "distinct_path_targets": len(paths),
        "source_note_refs": sum(c for pth, c in paths.items() if pth.startswith("sources/")),
    }


def main() -> None:
    con = sqlite3.connect(f"file:{MEM_DB}?mode=ro", uri=True)

    ladder = {
        "vault_read_sessions": q(
            con,
            "SELECT count(DISTINCT memory_session_id) FROM observations "
            "WHERE files_read LIKE '%second-brain%'",
        )[0][0],
        "vault_read_sessions_with_work": q(
            con,
            "SELECT count(DISTINCT o1.memory_session_id) FROM observations o1 "
            f"WHERE o1.files_read LIKE '%second-brain%' AND {_WORK_EXISTS}",
        )[0][0],
        "source_read_sessions": q(
            con,
            "SELECT count(DISTINCT memory_session_id) FROM observations "
            "WHERE files_read LIKE '%second-brain/sources%'",
        )[0][0],
        "source_read_sessions_with_work": q(
            con,
            "SELECT count(DISTINCT o1.memory_session_id) FROM observations o1 "
            f"WHERE o1.files_read LIKE '%second-brain/sources%' AND {_WORK_EXISTS}",
        )[0][0],
        "obs_read_and_modified": q(
            con,
            "SELECT count(*) FROM observations WHERE files_read LIKE '%second-brain%' "
            "AND files_modified IS NOT NULL AND files_modified NOT IN ('','[]')",
        )[0][0],
        "obs_modified_vault_only": q(
            con,
            "SELECT count(*) FROM observations WHERE files_read LIKE '%second-brain%' "
            "AND files_modified LIKE '%second-brain%'",
        )[0][0],
    }

    # distinct elective source notes ever read (explicit paths; globs excluded)
    notes: set[str] = set()
    for (fr,) in q(
        con, "SELECT files_read FROM observations WHERE files_read LIKE '%second-brain/sources%'"
    ):
        for m in re.finditer(r"second-brain/(sources/[^\"',\\]+?\.md)", fr or ""):
            if "*" not in m.group(1):
                notes.add(m.group(1))
    ladder["distinct_source_notes_read"] = len(notes)

    # every source-reading session: date, project, produced-work flag (no prompt
    # text). Dates come from the observations themselves — not every
    # memory_session_id has an sdk_sessions row (23 of 45 here).
    rows = q(
        con,
        "SELECT o1.project, MIN(o1.created_at), "
        f"MAX(CASE WHEN {_WORK_EXISTS} THEN 1 ELSE 0 END) "
        "FROM observations o1 WHERE o1.memory_session_id IN "
        "(SELECT DISTINCT memory_session_id FROM observations "
        "WHERE files_read LIKE '%second-brain/sources%') "
        "GROUP BY o1.memory_session_id ORDER BY 2",
    )
    sessions = [{"project": p, "date": ts[:10], "produced_work": bool(w)} for p, ts, w in rows]
    con.close()

    OUT.write_text(
        json.dumps(
            {
                "commit": subprocess.run(
                    ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True
                ).stdout.strip(),
                "generated": datetime.now(UTC).isoformat(timespec="seconds"),
                "ladder": ladder,
                "briefs": brief_citations(),
                "source_read_sessions": sessions,
            },
            indent=1,
        )
    )
    print(json.dumps(ladder, indent=1))
    print(json.dumps(brief_citations(), indent=1))
    print(
        f"{len(sessions)} source-read sessions, "
        f"{sum(s['produced_work'] for s in sessions)} produced work; wrote {OUT}"
    )


if __name__ == "__main__":
    main()
