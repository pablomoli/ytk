"""iMessage conversation ingestion — export and enrich iMessage threads."""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from .enrich import Enrichment
from .sdk import run_structured

# Marker a self-note can carry to bypass the inbox pick and ingest immediately.
# Chosen as "$$" because it is one symbol-layer tap away on the iOS keyboard,
# and (unlike a leading "/") never trips parse_txt's attachment filter.
MARKER = "$$"


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


# imessage-exporter timestamp, e.g. "Apr 19, 2026  7:46:49 PM" (spacing varies).
_EXPORT_TS_FMT = "%b %d, %Y %I:%M:%S %p"

# Bare http(s) links pasted into a self-note. Trailing punctuation is trimmed so
# "see https://x.com/a." doesn't capture the sentence period.
_URL_RE = re.compile(r"https?://[^\s<>\"']+")


def split_urls(text: str) -> tuple[list[str], str]:
    """Split note text into (urls, remaining prose with urls removed)."""
    urls = [u.rstrip(".,);]") for u in _URL_RE.findall(text)]
    remaining = _URL_RE.sub("", text)
    remaining = re.sub(r"[ \t]+\n", "\n", remaining).strip()
    return urls, remaining


def _parse_ts(timestamp: str) -> datetime | None:
    """Parse an export timestamp to a datetime; None if it doesn't match."""
    normalized = re.sub(r"\s+", " ", timestamp).strip()
    try:
        return datetime.strptime(normalized, _EXPORT_TS_FMT)
    except ValueError:
        return None


@dataclass
class Session:
    """A run of self-notes with no gap larger than the session window.

    A session is the inbox's unit of capture: one node per coherent sitting,
    with boundaries drawn by silence rather than by day or by message.
    """

    contact: str
    start: datetime
    end: datetime
    messages: list[MessageEntry] = field(default_factory=list)
    override: bool = False  # a message carried MARKER -> auto-ingest

    @property
    def note_id(self) -> str:
        """URL-shaped, content-derived id so it flows through the URL-keyed
        pending queue and dedupes deterministically across pulls."""
        raw = "|".join(m.timestamp for m in self.messages)
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
        return f"imessage:session:{digest}"

    @property
    def date(self) -> str:
        return self.start.strftime("%b %d, %Y")

    @property
    def suffix(self) -> str:
        """HHMM of the session start — disambiguates same-day note filenames."""
        return self.start.strftime("%H%M")

    def preview(self, limit: int = 140) -> str:
        text = " ".join(m.text for m in self.messages).strip()
        return text[: limit - 1] + "…" if len(text) > limit else text

    def as_thread(self) -> MessageThread:
        return MessageThread(contact=self.contact, date=self.date, messages=self.messages)


def _make_session(contact: str, pairs: list[tuple[datetime, MessageEntry]]) -> Session:
    """Build a Session from (datetime, entry) pairs, stripping the marker."""
    messages: list[MessageEntry] = []
    override = False
    for _, entry in pairs:
        text = entry.text
        if MARKER in text:
            override = True
            text = text.replace(MARKER, "").strip()
        if text:  # a marker-only message contributes override but no content
            messages.append(MessageEntry(sender=entry.sender, timestamp=entry.timestamp, text=text))
    return Session(
        contact=contact,
        start=pairs[0][0],
        end=pairs[-1][0],
        messages=messages,
        override=override,
    )


def sessionize(
    thread: MessageThread,
    gap_minutes: int = 20,
    now: datetime | None = None,
) -> list[Session]:
    """Group a thread's messages into sessions by inactivity timeout.

    Single sorted pass: a silence longer than `gap_minutes` between consecutive
    messages closes a session and opens the next. A session is only returned
    once it has gone quiet — its last message must be at least `gap_minutes`
    before `now` — so a still-warm session you may still be writing is withheld.
    A session containing MARKER overrides that hold and is always returned.
    """
    pairs = sorted(
        ((dt, m) for m in thread.messages if (dt := _parse_ts(m.timestamp))),
        key=lambda p: p[0],
    )
    if not pairs:
        return []

    gap = timedelta(minutes=gap_minutes)
    sessions: list[Session] = []
    current: list[tuple[datetime, MessageEntry]] = []
    prev: datetime | None = None
    for dt, entry in pairs:
        if prev is not None and dt - prev > gap:
            sessions.append(_make_session(thread.contact, current))
            current = []
        current.append((dt, entry))
        prev = dt
    if current:
        sessions.append(_make_session(thread.contact, current))

    if now is not None:
        sessions = [s for s in sessions if s.override or now - s.end >= gap]
    return [s for s in sessions if s.messages]


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
