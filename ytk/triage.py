"""Action item extraction from vault notes using Claude Haiku."""

from __future__ import annotations

from typing import Literal

import anthropic
from pydantic import BaseModel


_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


_SYSTEM_TRIAGE = """\
You are extracting concrete, actionable tasks from a personal knowledge note.
The note may be a journal entry, article summary, or video note.

Return a JSON object with a single field:

items: A list of action items. Each item has:
  title: Short imperative phrase under 70 chars. Examples: "Fix X", "Build Y", "Investigate Z".
  description: 1-2 sentences with enough context to act on without re-reading the note.
  priority: "high", "medium", or "low" based on urgency signals in the note.
  suggested_route: One of:
    "gh-issue"    — a concrete software feature, bug, or task for a specific project
    "idea"        — a loose idea, exploration, or thing to try later
    "investigate" — something to research or evaluate before deciding

Only extract items that are genuinely actionable. Skip vague aspirations or wishful thinking.
If there are no action items, return {"items": []}.
"""


class ActionItem(BaseModel):
    title: str
    description: str
    priority: Literal["high", "medium", "low"]
    suggested_route: Literal["gh-issue", "idea", "investigate"]


class TriageResult(BaseModel):
    items: list[ActionItem]


def extract_action_items(note_text: str) -> list[ActionItem]:
    """Extract structured action items from a vault note using Claude Haiku."""
    client = _get_client()
    response = client.messages.parse(
        model="claude-haiku-4-5",
        max_tokens=2048,
        system=[{"type": "text", "text": _SYSTEM_TRIAGE, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": note_text[:20_000]}],
        output_format=TriageResult,
    )
    return response.parsed_output.items
