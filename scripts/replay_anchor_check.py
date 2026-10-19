"""Replay the anchor check (moments.check_anchors) over every stored draft,
read-only, against the anchors the owner and the grader corrected.

Usage:
    sqlite3 ~/.ytk/ledger.db ".backup /path/to/copy.db"
    uv run python scripts/replay_anchor_check.py --ledger /path/to/copy.db

Reads drafts and views under ~/.ytk/evidence; drafts graded before views
existed (#212) get an in-memory view at the 80k cap they were read under.
Writes nothing.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ytk.enricher import EnrichmentV2
from ytk.evidence import evidence_dir
from ytk.moments import Anchor, check_anchors, snap_key_moments
from ytk.view import Budget, build_view, view_by_hash

# Pre-#212 drafts read a transcript cut at 80k characters (view.py, item 215).
LEGACY_CAP = 80_000
# A move lands "in the right place" within this slack of the labelled span.
TARGET_SLACK_S = 5.0


@dataclass(frozen=True)
class Label:
    draft: str  # drafts/<draft>.json
    cited: str  # as written in the draft
    target: tuple[str, str] | None  # labelled span; None = not in the record
    source: str  # owner | endorsed | grader
    ref: str  # ledger row the label was read from
    match: str | None = None  # description substring when two cites share a time


# Hand-read from answers.text (asks) and grade rows' bounce prose. "owner":
# the owner's own words; "endorsed": grader findings the owner pasted into a
# "say what is wrong" answer; "grader": model- or code-layer bounces only.
LABELS: list[Label] = [
    Label("761-2", "34:53", ("54:06", "54:06"), "owner", "ask 18"),
    Label("774-4", "0:18", ("0:20", "0:20"), "owner", "ask 85, hand-fixed in the note"),
    Label("770-2", "0:20", ("0:16", "0:16"), "owner", "ask 73", match="booth"),
    Label("770-2", "0:20", ("0:22", "0:22"), "owner", "ask 73", match="handwritten"),
    Label("759-3", "5:48", ("5:43", "5:46"), "endorsed", "ask 19 / grade 853"),
    Label("761-4", "57:03", ("55:35", "56:00"), "endorsed", "ask 20 / grade 859"),
    Label("761-4", "4:23", ("4:03", "4:03"), "endorsed", "ask 20 / grade 859"),
    Label("761-4", "8:38", ("8:22", "8:22"), "endorsed", "ask 20 / grade 859"),
    Label("762-2", "47:00", ("47:41", "48:57"), "endorsed", "ask 21 / grade 864"),
    Label("762-2", "1:25:06", None, "endorsed", "ask 21 / grade 864"),
    Label("762-4", "1:14:30", None, "endorsed", "ask 24 / grade 882"),
    Label("761-1", "1:56", ("1:02", "1:52"), "grader", "grade 842"),
    Label("761-5", "0:00", ("1:02", "1:11"), "grader", "grade 875"),
    Label("761-6", "34:44", ("54:06", "54:06"), "grader", "grade 877 (code layer)"),
    Label("757-2", "7:44", None, "grader", "grade 790 (code layer)"),
    Label("759-2", "7:00", ("7:19", "7:32"), "grader", "grade 851"),
    Label("759-2", "5:56", ("8:09", "8:18"), "grader", "grade 851"),
    Label("759-12", "5:56", ("7:01", "7:01"), "grader", "grade 911"),
    Label("762-1", "1:28:23", None, "grader", "grade 862"),
    Label("762-1", "1:38:10", None, "grader", "grade 862"),
    Label("762-1", "1:53:04", None, "grader", "grade 862"),
    Label("762-1", "2:15:58", None, "grader", "grade 862"),
    Label("762-5", "1:28:23", None, "grader", "grade 901"),
    Label("762-5", "2:15:58", None, "grader", "grade 901"),
    Label("762-6", "1:29:37", None, "grader", "grade 903"),
    Label("762-6", "2:16:05", None, "grader", "grade 903"),
    Label("762-7", "1:28:23", None, "grader", "grade 919"),
    Label("762-7", "2:15:58", None, "grader", "grade 919"),
    Label("762-8", "6:45", ("10:17", "11:45"), "grader", "grade 921"),
    Label("762-8", "23:27", ("25:16", "27:30"), "grader", "grade 921"),
    Label("762-8", "38:00", ("37:27", "37:27"), "grader", "grade 921"),
    Label("215-2", "5:50", ("8:17", "8:17"), "grader", "grade 973"),
    Label("215-2", "1:59:00", None, "grader", "grade 973"),
    Label("215-2", "2:08:21", None, "grader", "grade 973"),
    Label("763-2", "9:24", ("10:27", "10:51"), "grader", "grade 1134"),
    Label("763-2", "t:134", ("4:14", "4:44"), "grader", "grade 1134"),
    Label("763-2", "t:564", ("10:27", "10:27"), "grader", "grade 1134"),
    Label("765-1", "2:36", ("3:09", "3:18"), "grader", "grade 1142"),
    Label("765-1", "10:21", ("11:14", "11:14"), "grader", "grade 1142"),
    Label("765-1", "18:36", ("19:42", "20:04"), "grader", "grade 1142"),
    Label("766-2", "31:04", ("32:03", "32:03"), "grader", "grade 1149"),
    Label("766-2", "9:38", ("11:14", "11:43"), "grader", "grade 1149"),
    Label("774-3", "0:18", ("0:20", "0:20"), "grader", "grade 1282"),
    Label("808-2", "0:26", ("2:06", "2:29"), "grader", "grade 1469"),
    Label("808-2", "2:33", ("5:23", "5:23"), "grader", "grade 1469"),
    Label("808-2", "13:04", ("13:38", "13:43"), "grader", "grade 1469"),
    Label("808-2", "20:45", ("22:49", "23:37"), "grader", "grade 1469"),
    Label("808-2", "28:14", ("29:46", "29:46"), "grader", "grade 1469"),
    Label("808-2", "30:21", ("30:54", "31:19"), "grader", "grade 1469"),
]

# Owner corrections the check cannot see, counted so the table is honest.
UNCHECKABLE_OWNER = [
    "ask 80 / item 773: '(sheet tile, t:81)' -> t:86-88, a parenthetical, not a [t:N] cite, "
    "and an on-screen claim",
    "asks 70, 71, 73(1), 74, 77, 82(3), 85, 86 / items 769-776: frame and sheet re-anchors",
]


def _secs(cited: str) -> float:
    if cited.startswith("t:"):
        return float(cited[2:])
    nums = [int(p) for p in cited.split(":")]
    return float(sum(n * 60**i for i, n in enumerate(reversed(nums))))


def _transcript(conn: sqlite3.Connection, draft_name: str) -> list[dict[str, Any]]:
    item_id = int(draft_name.split("-")[0])
    ref = str(evidence_dir() / "drafts" / f"{draft_name}.json")
    row = conn.execute(
        "SELECT inputs FROM activity WHERE action = 'enrich' AND output_ref = ?", (ref,)
    ).fetchone()
    vh = json.loads(row["inputs"]).get("view_hash") if row and row["inputs"] else None
    if vh:
        v = view_by_hash(item_id, vh)
        if v is not None:
            return v.transcript
    item = conn.execute("SELECT payload_ref FROM items WHERE id = ?", (item_id,)).fetchone()
    return build_view(
        item_id, item["payload_ref"], Budget(evidence_cap_chars=LEGACY_CAP)
    ).transcript


def _load(name: str) -> EnrichmentV2:
    return EnrichmentV2.model_validate_json(
        (evidence_dir() / "drafts" / f"{name}.json").read_text()
    )


def _find(anchors: list[Anchor], draft: EnrichmentV2, label: Label) -> Anchor | None:
    for a in anchors:
        if a.cited != label.cited:
            continue
        if label.match and label.match not in a.claim:
            continue
        return a
    return None


def _right_place(after: str | None, target: tuple[str, str] | None) -> bool:
    if after is None or target is None:
        return False
    s = _secs(after)
    return _secs(target[0]) - TARGET_SLACK_S <= s <= _secs(target[1]) + TARGET_SLACK_S


def _class(lab: Label, transcript: list[dict[str, Any]]) -> str:
    """Where the right anchor is, relative to what the check can reach."""
    c = _secs(lab.cited)
    end = float(transcript[-1]["start"]) if transcript else 0.0
    if lab.target is None:
        return "past the packet" if c > end + 90 else "not in the record"
    if min(abs(_secs(t) - c) for t in lab.target) <= 90:
        return "inside +/-90 s"
    return "beyond +/-90 s"


def replay(ledger: Path, verbose: bool) -> dict[str, Any]:
    conn = sqlite3.connect(ledger)
    conn.row_factory = sqlite3.Row
    cache: dict[str, tuple[EnrichmentV2, list[dict[str, Any]]]] = {}

    def get(name: str) -> tuple[EnrichmentV2, list[dict[str, Any]]]:
        if name not in cache:
            cache[name] = (_load(name), _transcript(conn, name))
        return cache[name]

    # 1. Labelled anchor errors.
    rows: list[dict[str, Any]] = []
    for lab in LABELS:
        draft, tr = get(lab.draft)
        rep = check_anchors(draft, tr)
        a = _find(rep.anchors, draft, lab)
        snapped = None
        if lab.cited[0].isdigit():
            _, moves = snap_key_moments(draft, tr)
            for m in moves:
                if m.before == lab.cited and (not lab.match or lab.match in m.description):
                    snapped = m.after
        rows.append(
            {
                "draft": lab.draft,
                "cited": lab.cited,
                "source": lab.source,
                "ref": lab.ref,
                "target": lab.target,
                "class": _class(lab, tr),
                "cited_shared": a.cited_shared if a else None,
                "best_shared": a.best_shared if a else None,
                "cited_score": a.cited_score if a else None,
                "best_score": a.best_score if a else None,
                "verdict": a.verdict if a else "not found",
                "after": a.after if a else None,
                "right": _right_place(a.after if a else None, lab.target),
                "snap": snapped,
                "snap_right": _right_place(snapped, lab.target),
            }
        )

    # 2. Anchors on landed drafts the owner let stand.
    labelled = {(lab.draft, lab.cited) for lab in LABELS}
    stand: list[dict[str, Any]] = []
    for k in conn.execute("SELECT id, item_id FROM activity WHERE action = 'keep' ORDER BY id"):
        d = conn.execute(
            "SELECT output_ref FROM activity WHERE item_id = ? AND action = 'enrich' AND id < ? "
            "ORDER BY id DESC LIMIT 1",
            (k["item_id"], k["id"]),
        ).fetchone()
        if d is None:
            continue
        name = Path(d["output_ref"]).stem
        draft, tr = get(name)
        named = _grader_named(conn, d["output_ref"])
        for a in check_anchors(draft, tr).anchors:
            if (name, a.cited) in labelled:
                continue
            stand.append(
                {
                    "draft": name,
                    "cited": a.cited,
                    "verdict": a.verdict,
                    "after": a.after,
                    "grader": _mentions(named, a.cited),
                    "cited_shared": a.cited_shared,
                    "best_shared": a.best_shared,
                    "cited_score": a.cited_score,
                    "best_score": a.best_score,
                    "claim": a.claim,
                }
            )

    # 3. Agreement with the grader over every model-layer grade.
    agree: Counter[tuple[bool, bool]] = Counter()
    frames = 0
    for g in conn.execute(
        "SELECT id, item_id, output_ref, detail FROM activity WHERE action = 'grade'"
    ):
        detail = json.loads(g["detail"] or "{}")
        if detail.get("layer") != "model":
            continue
        d = conn.execute(
            "SELECT output_ref FROM activity WHERE item_id = ? AND action = 'enrich' AND id < ? "
            "ORDER BY id DESC LIMIT 1",
            (g["item_id"], g["id"]),
        ).fetchone()
        name = Path(d["output_ref"]).stem
        draft, tr = get(name)
        text = _bounce_text(detail)
        rep = check_anchors(draft, tr)
        frames += rep.frame_cites
        for a in rep.anchors:
            agree[(a.verdict != "ok", _mentions(text, a.cited))] += 1

    # 4. Every stored draft: how often the check would act at all.
    every: Counter[str] = Counter()
    every_frames = 0
    for p in sorted((evidence_dir() / "drafts").glob("*.json")):
        draft, tr = get(p.stem)
        rep = check_anchors(draft, tr)
        every_frames += rep.frame_cites
        every.update(a.verdict for a in rep.anchors)

    out = {
        "labelled": rows,
        "stand": stand,
        "agreement": {f"check={k[0]} grader={k[1]}": v for k, v in agree.items()},
        "agreement_frame_cites_skipped": frames,
        "every_draft": dict(every),
        "every_draft_frame_cites_skipped": every_frames,
        "uncheckable_owner": UNCHECKABLE_OWNER,
    }
    if verbose:
        for r in rows:
            print(r)
    return out


_GROUNDING = ("Key moments", "Grounding", "key moment adjacency")


def _bounce_text(detail: dict[str, Any]) -> str:
    raw: list[Any] = detail.get("bounces") or []
    bounces: list[dict[str, Any]] = [b for b in raw if isinstance(b, dict)]
    return " ".join(
        f"{b.get('detail', '')} {b.get('where', '')}"
        for b in bounces
        if b.get("check") in _GROUNDING
    )


def _mentions(text: str, cited: str) -> bool:
    return re.search(rf"(?<![\d:]){re.escape(cited)}(?![\d])", text) is not None


def _grader_named(conn: sqlite3.Connection, draft_ref: str) -> str:
    text = ""
    for g in conn.execute(
        "SELECT g.detail FROM activity g WHERE g.action = 'grade' AND g.item_id = "
        "(SELECT item_id FROM activity WHERE output_ref = ? AND action = 'enrich') "
        "AND g.id > (SELECT id FROM activity WHERE output_ref = ? AND action = 'enrich') "
        "ORDER BY g.id LIMIT 1",
        (draft_ref, draft_ref),
    ):
        text += _bounce_text(json.loads(g["detail"] or "{}"))
    return text


_CLASSES = ("inside +/-90 s", "beyond +/-90 s", "not in the record", "past the packet")

# Rule variants scored from the same anchors, for the sensitivity table.
_RULES: dict[str, Callable[[dict[str, Any]], bool]] = {
    "shipped: cited span shares 0 words, best >= 2": lambda r: (
        r["cited_shared"] == 0 and r["best_shared"] >= 2
    ),
    "best >= 2x cited (IDF), best >= 2": lambda r: (
        r["best_shared"] >= 2
        and r["best_score"] >= 2 * r["cited_score"]
        and r["best_score"] > r["cited_score"]
    ),
    "cited shares <= 1, best >= 6x cited, best >= 2": lambda r: (
        r["cited_shared"] <= 1
        and r["best_shared"] >= 2
        and r["best_score"] >= 6 * max(r["cited_score"], 1e-9)
    ),
}


def _summary(out: dict[str, Any]) -> str:
    rows: list[dict[str, Any]] = out["labelled"]
    stand: list[dict[str, Any]] = out["stand"]
    lines = ["Labelled anchor errors (source x where the right anchor is):"]
    lines.append(
        f"  {'source':9} {'class':18} {'n':>3} {'moved':>5} {'right':>5} {'unsup':>5} {'ok':>3} {'snap':>4} {'snapR':>5}"
    )
    for src in ("owner", "endorsed", "grader"):
        for cls in _CLASSES:
            rs = [r for r in rows if r["source"] == src and r["class"] == cls]
            if not rs:
                continue
            c = Counter(r["verdict"] for r in rs)
            lines.append(
                f"  {src:9} {cls:18} {len(rs):>3} {c['moved']:>5} {sum(r['right'] for r in rs):>5} "
                f"{c['unsupported']:>5} {c['ok']:>3} {sum(r['snap'] is not None for r in rs):>4} "
                f"{sum(r['snap_right'] for r in rs):>5}"
            )
    for g in (False, True):
        ss = [s for s in stand if s["grader"] is g]
        c = Counter(s["verdict"] for s in ss)
        lines.append(
            f"Let stand on landed drafts, grader {'named it' if g else 'silent'}: {len(ss)}; "
            f"moved {c['moved']}, unsupported {c['unsupported']}, ok {c['ok']}"
        )
    lines.append("Rule sensitivity (flag = would move; inside-window labels vs let-stand):")
    inside = [r for r in rows if r["class"] == "inside +/-90 s" and r["cited_shared"] is not None]
    for name, rule in _RULES.items():
        lines.append(
            f"  {name}: labels {sum(rule(r) for r in inside)}/{len(inside)}, "
            f"let stand {sum(rule(s) for s in stand)}/{len(stand)}"
        )
    lines.append(f"Agreement with model-layer grades (per anchor): {out['agreement']}")
    lines.append(f"  frame/sheet cites skipped there: {out['agreement_frame_cites_skipped']}")
    lines.append(
        f"Every stored draft: {out['every_draft']}; frame/sheet cites skipped "
        f"{out['every_draft_frame_cites_skipped']}"
    )
    lines.append("Owner corrections the check cannot see:")
    lines += [f"  {u}" for u in UNCHECKABLE_OWNER]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ledger", type=Path, required=True, help="a COPY of ~/.ytk/ledger.db")
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    if args.ledger.resolve() == (Path.home() / ".ytk" / "ledger.db").resolve():
        raise SystemExit("pass a copy of the ledger, never the live file")
    out = replay(args.ledger, args.verbose)
    print(_summary(out))
    if args.json:
        args.json.write_text(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
