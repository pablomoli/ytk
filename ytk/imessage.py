"""iMessage conversation ingestion — export and enrich iMessage threads."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .enrich import Enrichment
from .sdk import run_structured


_SYSTEM_JOURNAL = """\
You are helping someone process and retrieve their own personal notes captured as iMessage self-chat.
The input is a stream of thoughts, ideas, observations, and questions written during a walk or reflection session.
Return a JSON object with these fields:

thesis
  One sentence capturing the central theme or dominant concern of this session.
  Be specific — name the actual topic, project, or question on their mind.

summary
  3-5 sentences distilling what was on their mind. Preserve the texture of their thinking —
  what problems were they chewing on, what ideas emerged, what questions were unresolved.
  Name specific things (projects, people, tools, ideas) rather than staying abstract.

key_concepts
  Ideas, questions, observations, or recurring themes. Format each as "concept: brief note on
  how it appeared in this session". Max 8 items.

insights
  2-3 concrete things worth remembering or acting on — decisions implied, patterns noticed,
  something they seemed to land on. These should be the most retrievable, durable thoughts.

interest_tags
  3-8 lowercase hyphenated topic labels (e.g. "product-thinking", "ai", "personal").

key_moments
  Up to 5 notable lines or thoughts worth anchoring — specific enough to be findable later.
  Use "note N" as the timestamp field, and quote or closely paraphrase the thought.
"""


@dataclass
class MessageEntry:
    sender: str
    timestamp: str
    text: str


@dataclass
class MessageThread:
    contact: str
    date: str
    messages: list[MessageEntry] = field(default_factory=list)

    def as_text(self) -> str:
        return "\n".join(f"[{m.timestamp}] {m.text}" for m in self.messages)


def export_conversation(
    contact: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> Path:
    """Run imessage-exporter for a contact and return the export directory path."""
    export_dir = Path(tempfile.mkdtemp(prefix="ytk_imessage_"))
    cmd = ["imessage-exporter", "-f", "txt", "-o", str(export_dir), "-t", contact]
    if start_date:
        cmd += ["-s", start_date]
    if end_date:
        cmd += ["-e", end_date]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        shutil.rmtree(export_dir, ignore_errors=True)
        raise ValueError(f"imessage-exporter failed: {result.stderr.strip()}")
    return export_dir


def find_exported_file(export_dir: Path, contact: str) -> Path:
    """Find the exported txt file for a contact within the export directory."""
    txt_files = list(export_dir.rglob("*.txt"))
    if not txt_files:
        raise ValueError(
            f"No conversations found for '{contact}'. "
            "Verify the contact identifier and that Full Disk Access is granted to your terminal."
        )
    if len(txt_files) == 1:
        return txt_files[0]
    contact_part = re.sub(r"[\s+\-()]", "", contact).lower()
    for f in txt_files:
        if contact_part in re.sub(r"[\s+\-()]", "", f.stem).lower():
            return f
    # Fall back to the largest file
    return max(txt_files, key=lambda f: f.stat().st_size)


# imessage-exporter txt block format:
#   Apr 19, 2026  7:46:49 PM (Read by you after ...)
#   Me
#   message text here
#   (blank line separates blocks)
_TS_RE = re.compile(r"^(\w+ \d+, \d{4}\s+\d+:\d+:\d+ [AP]M)")


def parse_txt(txt_path: Path) -> MessageThread:
    """Parse an imessage-exporter txt export into a MessageThread.

    Self-chat messages appear twice (sent + received copy); deduplicated by
    (timestamp, text). Attachment paths are skipped.
    """
    content = txt_path.read_text(encoding="utf-8", errors="replace")
    contact = txt_path.stem
    date = ""
    messages: list[MessageEntry] = []
    seen: set[tuple[str, str]] = set()

    for block in re.split(r"\n\s*\n", content.strip()):
        lines = block.strip().splitlines()
        if len(lines) < 3:
            continue

        ts_match = _TS_RE.match(lines[0])
        if not ts_match:
            continue

        timestamp = ts_match.group(1)
        sender = lines[1].strip()
        text = "\n".join(lines[2:]).strip()

        if not text or text.startswith("/"):  # skip attachments (file paths)
            continue

        if not date:
            # Extract "Apr 19, 2026" from the timestamp
            date = re.sub(r"\s+\d+:\d+:\d+.*", "", timestamp).strip()

        dedup_key = (timestamp, text)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        messages.append(MessageEntry(sender=sender, timestamp=timestamp, text=text))

    return MessageThread(contact=contact, date=date, messages=messages)


def enrich_journal(thread: MessageThread) -> Enrichment:
    """Enrich an iMessage self-chat thread as a journal entry via Claude Code."""
    user_prompt = f"Date: {thread.date}\n\n{thread.as_text()}"
    data = run_structured(_SYSTEM_JOURNAL, user_prompt, Enrichment.model_json_schema())
    return Enrichment.model_validate(data)
