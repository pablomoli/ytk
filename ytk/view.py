"""The exam packet (#212): one evidence view per bundle, cut once by the
proctor and handed to the student, the spell-checker and the teacher as the
same bytes.

`rendered` is the one prompt block both model roles receive. `grounding_text`
is the one string the deterministic checks tokenize. `shown` and `openable`
carry the unit ids a claim or a finding may cite (`t:<seconds>`, `frame:NNN`,
`sheet`); anything else is `not_shown`, which is unverifiable here and never
ungrounded. The view is immutable on disk and named by its hash in every
enrich and grade row, so a grade that read a different packet than its draft
is a query away.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .enrich import description_block, fmt_ts
from .evidence import EvidenceBundle, evidence_dir, load_bundle

# Names the word rule behind "findable": grader.content_tokens (ASCII words of
# four letters and up, accents folded, hyphens split). A grade row that says
# which tokenizer judged it can be re-run when the rule changes.
TOKENIZER = "ascii-words-folded-v1"


@dataclass(frozen=True)
class Budget:
    """How thick the packet is. Data on the view, never a constant in a
    reader: the two caps below used to live in the enricher and the grader
    separately and disagreed (items 215, 489, 534)."""

    # e501375: four reel frames fail structured output 3 of 3; two pass.
    frames_shown: int = 2
    # Item 215: an 80k cap cut a lecture at 1:08 and the judge bounced the
    # back half as ungrounded. 400k chars is about 100k tokens.
    evidence_cap_chars: int = 400_000
    # none | openable | shown. The dense tier lives beside the sheet, so
    # opening the box for the sheet opens it for the dense frames too.
    sheet: str = "none"


DEFAULT_BUDGET = Budget()

_CITE = re.compile(r"\s*\[(frame:\d{3}|sheet|t:\d+)\]")


def split_cites(text: str) -> tuple[str, list[str]]:
    """A claim may end with the packet units it rests on: `[frame:002]`."""
    return _CITE.sub("", text).strip(), _CITE.findall(text)


def strip_cites(text: str) -> str:
    return _CITE.sub("", text).strip()


def views_dir() -> Path:
    return evidence_dir() / "views"


@dataclass
class View:
    item_id: int
    bundle_path: str
    bundle_hash: str
    source: str
    transcript_origin: str
    duration: float | None
    budget: dict[str, Any]
    shown: list[dict[str, Any]]
    openable: list[dict[str, Any]]
    not_shown: list[str]
    gaps: list[str]
    mounts: list[str]
    transcript: list[dict[str, Any]]
    grounding_text: str
    rendered: str
    tokenizer: str = TOKENIZER
    view_hash: str = ""

    @property
    def path(self) -> Path:
        return views_dir() / f"{self.item_id}-{self.bundle_hash}.json"

    def transcript_span(self) -> tuple[float, float] | None:
        for u in self.shown:
            if u["kind"] == "transcript":
                return float(u["t"]), float(u["t_end"])
        return None

    def has_unit(self, uid: str) -> bool:
        if uid.startswith("t:"):
            span = self.transcript_span()
            if span is None or not uid[2:].isdigit():
                return False
            return span[0] <= int(uid[2:]) <= span[1]
        return any(u["id"] == uid for u in (*self.shown, *self.openable))

    def unit_ids(self) -> list[str]:
        return [u["id"] for u in (*self.shown, *self.openable)]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=1)


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:12]


def _frame_units(
    bundle: EvidenceBundle, budget: Budget
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], list[str]]:
    """One numbering across the sparse set and the dense tier; the first
    `frames_shown` are shown, the rest are in the box or not in the packet
    depending on whether the box is open."""
    sparse = [p for p in bundle.frames if Path(p).is_file()]
    dense = [d for d in bundle.dense_frames if Path(str(d.get("path", ""))).is_file()]
    sheet = bundle.sheet if bundle.sheet and Path(bundle.sheet).is_file() else None
    ordered: list[tuple[str, float | None]] = [(p, None) for p in sparse]
    ordered += [(str(d["path"]), d.get("t")) for d in dense]
    units: list[dict[str, Any]] = [
        {"id": f"frame:{i:03d}", "kind": "frame", "path": p, "t": t}
        for i, (p, t) in enumerate(ordered, start=1)
    ]
    shown = units[: budget.frames_shown]
    rest = units[budget.frames_shown :]
    mounts = {str(Path(u["path"]).parent) for u in shown}
    openable: list[dict[str, Any]] = []
    not_shown: list[str] = []
    box_open = budget.sheet != "none" and sheet is not None
    if box_open:
        assert sheet is not None
        mounts.add(str(Path(sheet).parent))
        sheet_unit = {"id": "sheet", "kind": "sheet", "path": sheet, "t": None}
        if budget.sheet == "shown":
            shown = [*shown, sheet_unit]
        else:
            openable.append(sheet_unit)
        openable += rest
    else:
        if rest:
            lo, hi = budget.frames_shown + 1, len(units)
            not_shown.append(f"frames {lo} to {hi} ({len(rest)} frames)")
        if sheet:
            not_shown.append("contact sheet")
    return shown, openable, not_shown, sorted(mounts)


def _head(bundle: EvidenceBundle) -> tuple[list[str], list[str]]:
    """The cover pages: what every reader gets before the transcript. Returns
    the rendered parts and the plain texts that count as grounding."""
    parts: list[str] = [f"Title: {bundle.title or ''}"]
    ground: list[str] = [bundle.title or ""]
    if bundle.uploader:
        parts.append(f"Uploader: {bundle.uploader}")
    if bundle.duration:
        parts.append(f"Duration: {int(bundle.duration)}s")
    if bundle.chapters:
        rows = "\n".join(
            f"  {fmt_ts(float(c.get('start_time') or 0))} {c.get('title', '')}"
            for c in bundle.chapters
        )
        parts.append(f"Chapters:\n{rows}")
    if bundle.description:
        block = description_block(bundle.description).strip()
        parts.append(block)
        ground.append(block)
    if bundle.caption:
        parts.append(f"Caption:\n{bundle.caption}")
        ground.append(bundle.caption)
    if bundle.text:
        parts.append(f"Body:\n{bundle.text}")
        ground.append(bundle.text)
    return parts, ground


def _transcript(
    bundle: EvidenceBundle, budget: Budget, used: int
) -> tuple[str, list[dict[str, Any]], str | None]:
    """Render lines until the cap; a cut is said inside the packet so both
    readers know where the record stops."""
    if not bundle.transcript:
        return f"Transcript: none (status {bundle.transcript_status})", [], None
    total = len(bundle.transcript)
    header = (
        f"Transcript (origin {bundle.transcript_origin}; {total} lines; a line's unit "
        f"id is t:<seconds>, so [6:40] is t:400):"
    )
    kept: list[dict[str, Any]] = []
    lines: list[str] = []
    size = used + len(header)
    for seg in bundle.transcript:
        line = f"[{fmt_ts(float(seg.get('start', 0)))}] {seg.get('text', '')}"
        if size + len(line) + 1 > budget.evidence_cap_chars:
            break
        size += len(line) + 1
        lines.append(line)
        kept.append({"start": float(seg.get("start", 0)), "text": str(seg.get("text", ""))})
    cut: str | None = None
    if len(kept) < total:
        nxt = int(float(bundle.transcript[len(kept)].get("start", 0)))
        cut = (
            f"transcript lines {len(kept) + 1} to {total} (t:{nxt} onward), "
            f"cap {budget.evidence_cap_chars} characters"
        )
        lines.append(
            f"[Transcript cut after line {len(kept)} of {total}: t:{nxt} onward is not in "
            "this packet. Claims about it cannot be checked here: neither cite nor bounce them.]"
        )
    return header + "\n" + "\n".join(lines), kept, cut


def build_view(item_id: int, bundle_path: str | Path, budget: Budget = DEFAULT_BUDGET) -> View:
    bundle_path = Path(bundle_path)
    bundle = load_bundle(bundle_path)
    bundle_hash = _hash_bytes(bundle_path.read_bytes())
    parts, ground = _head(bundle)
    shown_frames, openable, not_shown, mounts = _frame_units(bundle, budget)
    used = sum(len(p) + 2 for p in parts)
    transcript_block, kept, cut = _transcript(bundle, budget, used)
    parts.append(transcript_block)
    shown: list[dict[str, Any]] = []
    if kept:
        shown.append(
            {
                "id": f"t:{int(kept[0]['start'])}-{int(kept[-1]['start'])}",
                "kind": "transcript",
                "t": kept[0]["start"],
                "t_end": kept[-1]["start"],
                "lines": len(kept),
            }
        )
    shown += shown_frames
    if cut:
        not_shown = [cut, *not_shown]
    if shown_frames:
        rows = "\n".join(f"  {u['id']} {u['path']}" for u in shown_frames)
        parts.append(f"Frames shown (open each; cite one as its id):\n{rows}")
    if openable:
        rows = "\n".join(f"  {u['id']} {u['path']}" for u in openable)
        parts.append(
            "In the box (open by path when the record needs it; cite one as its id):\n" + rows
        )
    if not_shown:
        parts.append("Not in this packet:\n" + "\n".join(f"- {s}" for s in not_shown))
    if bundle.gaps:
        parts.append("Not seen at capture:\n" + "\n".join(f"- {g}" for g in bundle.gaps))
    rendered = "\n\n".join(p for p in parts if p)
    ground += [seg["text"] for seg in kept]
    v = View(
        item_id=item_id,
        bundle_path=str(bundle_path),
        bundle_hash=bundle_hash,
        source=bundle.source,
        transcript_origin=bundle.transcript_origin,
        duration=bundle.duration,
        budget=asdict(budget),
        shown=shown,
        openable=openable,
        not_shown=not_shown,
        gaps=list(bundle.gaps),
        mounts=mounts,
        transcript=kept,
        grounding_text="\n".join(g for g in ground if g),
        rendered=rendered,
    )
    v.view_hash = _hash_bytes(json.dumps(asdict(v), sort_keys=True).encode())
    return v


def load_view(path: str | Path) -> View:
    return View(**json.loads(Path(path).read_text()))


def ensure_view(item_id: int, bundle_path: str | Path, budget: Budget = DEFAULT_BUDGET) -> View:
    """One view per bundle: the file on disk wins over a rebuild, so retries
    read what the first round read even if the budget default moved."""
    bundle_hash = _hash_bytes(Path(bundle_path).read_bytes())
    path = views_dir() / f"{item_id}-{bundle_hash}.json"
    if path.exists():
        return load_view(path)
    v = build_view(item_id, bundle_path, budget)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(v.to_json())
    return v


def latest_view(item_id: int) -> View | None:
    paths = sorted(views_dir().glob(f"{item_id}-*.json"), key=lambda p: p.stat().st_mtime)
    return load_view(paths[-1]) if paths else None


def view_by_hash(item_id: int, view_hash: str) -> View | None:
    for p in views_dir().glob(f"{item_id}-*.json"):
        v = load_view(p)
        if v.view_hash == view_hash:
            return v
    return None
