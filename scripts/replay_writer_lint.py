"""Replay the house-rule lint (writer_rules.lint) over every stored draft,
read-only, against what the grader and the owner said about that draft.

Usage:
    sqlite3 ~/.ytk/ledger.db ".backup /path/to/copy.db"
    uv run python scripts/replay_writer_lint.py --ledger /path/to/copy.db [--show-misses]

A draft is the output_ref of an enrich row. Its verdict is the first grade
row after it (before the item's next enrich), plus the text of any bounce
ask answered in that window. A draft is "observed" for a rule when a model
grade or an owner answer read it; a code-layer bounce alone stops before the
model reads the prose, so it observes only the code checks. Writes nothing.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from ytk.enricher import EnrichmentV2
from ytk.writer_rules import lint

# Labels: a rule is "said" about a draft when a finding or an answer on it
# matches. Hand-written from reading the 253 bounces and the bounce answers.
SAID: dict[str, re.Pattern[str]] = {
    "open on the claim": re.compile(
        r"openings like|start with the claim|on the claim|^banned phrasing: .*opening|"
        r"opening clause|the same opener",
        re.IGNORECASE | re.MULTILINE,
    ),
    "the argument, not the running order": re.compile(
        r"running order|play-by-play|walks? the|in sequence|walkthrough", re.IGNORECASE
    ),
    "banned words": re.compile(
        r"(?:banned phrasing|what i do not want).*\b(?:explores|delves|dives into|journey|landscape)\b",
        re.IGNORECASE,
    ),
    "summary length": re.compile(
        r"\b(?:six|seven|eight|two) sentences|sentences where three to five|cut to five",
        re.IGNORECASE,
    ),
    "mark inference from frames": re.compile(r"inferen|as a guess|marked as", re.IGNORECASE),
    "near-synonym tags": re.compile(r"near-synonym", re.IGNORECASE),
    "prose only, no process": re.compile(
        r"mention(?:s|ing)? the rubric|grader flagged|grading process|json-encoded|serialized|"
        r"<parameter|malformed",
        re.IGNORECASE,
    ),
}


@dataclass
class Draft:
    path: Path
    item_id: int
    mode: str
    layer: str | None = None
    said: list[str] = field(default_factory=list[str])  # "check: detail" lines and owner answers

    @property
    def observed(self) -> bool:
        return self.layer == "model" or any(s.startswith("owner: ") for s in self.said)


def _bounce_lines(detail: str | None) -> tuple[str | None, list[str]]:
    try:
        d: object = json.loads(detail or "{}")
    except ValueError:
        return None, []
    if not isinstance(d, dict):
        return None, []
    dd = cast("dict[str, Any]", d)
    lines: list[str] = []
    for b in cast("list[object]", dd.get("bounces") or []):
        if isinstance(b, dict):
            bd = cast("dict[str, object]", b)
            lines.append(f"{bd.get('check', '')}: {bd.get('detail', '')}")
    return cast("str | None", dd.get("layer")), lines


def load(conn: sqlite3.Connection) -> list[Draft]:
    rows = conn.execute(
        "SELECT id, item_id, action, inputs, output_ref, detail FROM activity "
        "WHERE action IN ('enrich', 'grade') ORDER BY item_id, id"
    ).fetchall()
    answers = conn.execute(
        "SELECT a.item_id, w.id, w.text, a.created_at FROM asks a JOIN answers w ON w.ask_id = a.id "
        "WHERE a.kind = 'grader bounce, twice' AND coalesce(trim(w.text), '') != ''"
    ).fetchall()
    out: list[Draft] = []
    current: Draft | None = None
    graded = False
    for r in rows:
        if r["action"] == "enrich":
            current, graded = None, False
            ref = r["output_ref"]
            if ref and Path(ref).exists():
                mode = json.loads(r["inputs"] or "{}").get("mode") or "?"
                current = Draft(Path(ref), r["item_id"], mode)
                current.said = []
                out.append(current)
        elif current is not None and not graded:
            current.layer, current.said = _bounce_lines(r["detail"])
            graded = True
    # An answer reads the item's last draft before the ask; attach it there.
    by_item: dict[int, list[Draft]] = {}
    for d in out:
        by_item.setdefault(d.item_id, []).append(d)
    enrich_at = {
        r["output_ref"]: r["at"]
        for r in conn.execute("SELECT output_ref, at FROM activity WHERE action = 'enrich'")
    }
    for a in answers:
        before = [
            d for d in by_item.get(a["item_id"], []) if enrich_at[str(d.path)] <= a["created_at"]
        ]
        if before:
            before[-1].said.append("owner: " + a["text"])
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--ledger", type=Path, required=True, help="a .backup copy of the ledger")
    ap.add_argument("--show-misses", action="store_true", help="print false alarms and misses")
    args = ap.parse_args()
    conn = sqlite3.connect(args.ledger)
    conn.row_factory = sqlite3.Row
    drafts = load(conn)

    flagged: dict[str, set[int]] = {r: set() for r in SAID}
    said: dict[str, set[int]] = {r: set() for r in SAID}
    hits_by: dict[tuple[str, int], list[str]] = {}
    for i, d in enumerate(drafts):
        draft = EnrichmentV2.model_validate_json(d.path.read_text())
        for h in lint(draft):
            flagged[h.rule].add(i)
            hits_by.setdefault((h.rule, i), []).append(f"{h.where}: {h.detail}")
        for rule, pat in SAID.items():
            if any(pat.search(s) for s in d.said):
                said[rule].add(i)

    observed = {i for i, d in enumerate(drafts) if d.observed}
    print(
        f"{len(drafts)} drafts ({Counter(d.mode for d in drafts)}), {len(observed)} observed "
        "by a model grade or an owner answer"
    )
    head = f"{'rule':<38}{'flagged':>8}{'1st':>5}{'observed':>9}{'said':>6}{'precision':>11}{'recall':>8}"
    print(head)
    for rule in SAID:
        f_obs = flagged[rule] & observed
        s_obs = said[rule] & observed if rule != "banned words" else said[rule]
        tp = len(f_obs & s_obs)
        prec = f"{tp}/{len(f_obs)}" if f_obs else "-"
        rec = f"{tp}/{len(s_obs)}" if s_obs else "-"
        first = sum(1 for i in flagged[rule] if drafts[i].mode == "draft")
        print(
            f"{rule:<38}{len(flagged[rule]):>8}{first:>5}{len(f_obs):>9}{len(s_obs):>6}{prec:>11}{rec:>8}"
        )
        if args.show_misses:
            for i in sorted(f_obs - s_obs):
                print(f"   false alarm {drafts[i].path.name}: {hits_by[(rule, i)]}")
            for i in sorted(s_obs - flagged[rule]):
                line = next(s for s in drafts[i].said if SAID[rule].search(s))
                print(f"   miss {drafts[i].path.name}: {line[:160]}")


if __name__ == "__main__":
    main()
