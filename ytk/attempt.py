"""The attempt record (#212): one round's memory, written by the proctor.

Opened before the student writes, with the previous draft and the findings
that round is meant to fix; closed when the verdict is in. Both roles read
the same header, so the teacher sees what it asked for last round and cannot
bounce a change it requested (item 759).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from . import ledger
from .evidence import evidence_dir
from .view import View


def attempts_dir() -> Path:
    return evidence_dir() / "attempts"


@dataclass
class Attempt:
    item_id: int
    n: int
    view_hash: str
    take: dict[str, Any] | None
    previous_draft: dict[str, Any] | None
    findings_in: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    draft_out: str | None = None
    verdict_out: dict[str, Any] | None = None
    opened_at: str = ""
    closed_at: str | None = None

    @property
    def path(self) -> Path:
        return attempts_dir() / f"{self.item_id}-{self.n}.json"

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(asdict(self), indent=1))

    def record_draft(self, draft_path: str | Path) -> None:
        self.draft_out = str(draft_path)
        self.save()

    def close(self, verdict: dict[str, Any]) -> None:
        self.verdict_out = verdict
        self.closed_at = ledger.now()
        self.save()

    def rendered(self) -> str:
        """The header both roles receive after the packet."""
        parts = [
            f"Attempt {self.n} for item {self.item_id}. Packet {self.view_hash}: the evidence "
            "above is the whole record; nothing outside it can be cited or checked."
        ]
        if self.take and self.take.get("text"):
            parts.append(
                f"The owner's take (kind: {self.take.get('kind') or 'intent'}), the reason "
                f"this item is in the library:\n{self.take['text']}"
            )
        if self.findings_in:
            rows = "\n".join(
                f"- {f.get('check', '')}: {f.get('detail', '')}"
                + (f" (where: {f['where']})" if f.get("where") else "")
                for f in self.findings_in
            )
            parts.append(
                "Findings requested last round, in order. Each is to be addressed in this "
                "attempt; a change that was asked for here is not a new objection:\n" + rows
            )
        if self.previous_draft is not None:
            parts.append("Previous draft:\n" + json.dumps(self.previous_draft, indent=1))
        else:
            parts.append("No previous draft: this is the first attempt.")
        return "\n\n".join(parts)


def open_attempt(
    item_id: int,
    n: int,
    view: View,
    *,
    take: dict[str, Any] | None,
    previous: dict[str, Any] | None,
    findings_in: list[dict[str, Any]],
) -> Attempt:
    a = Attempt(
        item_id=item_id,
        n=n,
        view_hash=view.view_hash,
        take=take,
        previous_draft=previous,
        findings_in=list(findings_in),
        opened_at=ledger.now(),
    )
    a.save()
    return a


def load_attempt(item_id: int, n: int) -> Attempt | None:
    p = attempts_dir() / f"{item_id}-{n}.json"
    if not p.exists():
        return None
    return Attempt(**json.loads(p.read_text()))


def attempts_for(item_id: int) -> list[Attempt]:
    out: list[Attempt] = []
    for p in attempts_dir().glob(f"{item_id}-*.json"):
        out.append(Attempt(**json.loads(p.read_text())))
    return sorted(out, key=lambda a: a.n)
