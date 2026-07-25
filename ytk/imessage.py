# pyright: basic
# Not strict-clean yet (#122). Delete these two lines once the module
# passes strict — the list of files carrying them only shrinks.
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

from .enrich import Enrichment, enrich_content

# Marker a self-note can carry to bypass the inbox pick and ingest immediately.
# Chosen as "$$" because it is one symbol-layer tap away on the iOS keyboard,
# and (unlike a leading "/") never trips parse_txt's attachment filter.
MARKER = "$$"


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


# ---------------------------------------------------------------------------
# Direct chat.db read — replaces the imessage-exporter subprocess. Messages are
# stored as serialized NSAttributedString objects (Apple's `streamtyped`
# archive); the plain `text` column is filled for <1% of messages, so the body
# almost always has to be decoded out of the `attributedBody` blob.
# ---------------------------------------------------------------------------

_APPLE_EPOCH = 978307200  # unix seconds at 2001-01-01, the Core Data reference date


def chatdb_path() -> Path:
    return Path.home() / "Library" / "Messages" / "chat.db"


def _read_ts_int(data: bytes, p: int) -> tuple[int, int]:
    """Read a typedstream-encoded integer at offset p; return (value, next_p).

    Values < 0x81 are a single byte; 0x81/0x82 introduce a little-endian 2- or
    4-byte length (how streamtyped stores string byte-counts >= 128).
    """
    b = data[p]
    if b == 0x81:
        return int.from_bytes(data[p + 1 : p + 3], "little"), p + 3
    if b == 0x82:
        return int.from_bytes(data[p + 1 : p + 5], "little"), p + 5
    return b, p + 1


def decode_attributed_body(data: bytes) -> str:
    """Extract the message text from a `streamtyped` attributedBody blob.

    The text is stored right after the NSString class marker as a length-prefixed
    UTF-8 byte run (typedstream `+` type). Validated to match the `text` column
    exactly on every message that populates both.
    """
    if not data:
        return ""
    idx = data.find(b"NSString")
    if idx == -1:
        idx = data.find(b"NSMutableString")
    if idx == -1:
        return ""
    plus = data.find(b"\x2b", idx)  # '+' typedstream C-string marker
    if plus == -1:
        return ""
    length, start = _read_ts_int(data, plus + 1)
    return data[start : start + length].decode("utf-8", errors="replace")


def read_recent(
    days: int = 3,
    now: datetime | None = None,
    self_id: str | None = None,
    db_path: Path | None = None,
) -> MessageThread:
    """Read self-chat messages from the last `days` straight from chat.db.

    Reads the live DB read-only (WAL-aware, so it sees the newest message) and
    isolates the self-chat by chat_identifier. Apple's UTC nanosecond timestamps
    are converted to local time so they line up with a local `now` in sessionize.
    """
    import os
    import sqlite3

    now = now or datetime.now()
    self_id = self_id if self_id is not None else os.environ.get("IMESSAGE_SELF", "")
    db = Path(db_path) if db_path else chatdb_path()
    if not self_id or not db.exists():
        return MessageThread(contact=self_id or "me", date="", messages=[])

    since_apple = int((now - timedelta(days=days)).timestamp() - _APPLE_EPOCH) * 1_000_000_000
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
    try:
        rows = con.execute(
            "SELECT m.date, m.text, m.attributedBody FROM message m "
            "JOIN chat_message_join cmj ON cmj.message_id = m.ROWID "
            "JOIN chat c ON c.ROWID = cmj.chat_id "
            "WHERE c.chat_identifier = ? AND m.is_from_me = 1 AND m.date > ? "
            "ORDER BY m.date ASC",
            (self_id, since_apple),
        ).fetchall()
    finally:
        con.close()

    messages: list[MessageEntry] = []
    for date, text, blob in rows:
        body = text if (text and text.strip()) else decode_attributed_body(blob or b"")
        body = (body or "").replace("￼", "").strip()  # drop attachment placeholders
        if not body:
            continue
        dt = datetime.fromtimestamp(date / 1e9 + _APPLE_EPOCH)
        messages.append(MessageEntry(sender="Me", timestamp=dt.strftime(_EXPORT_TS_FMT), text=body))

    date0 = messages[0].timestamp.rsplit(" ", 2)[0] if messages else ""
    return MessageThread(contact=self_id, date=date0, messages=messages)


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
        digest = hashlib.sha1(raw.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]
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
    content_block = f"Date: {thread.date}\n\n{thread.as_text()}"
    return enrich_content(content_block, "journal")
