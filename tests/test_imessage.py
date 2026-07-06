"""Tests for ytk.imessage sessionization — inactivity-timeout grouping."""

from datetime import datetime, timedelta

from ytk.imessage import (
    MARKER,
    MessageEntry,
    MessageThread,
    decode_attributed_body,
    read_recent,
    sessionize,
    split_urls,
)


def _blob(text: str) -> bytes:
    """Build a minimal streamtyped attributedBody carrying `text`."""
    tb = text.encode("utf-8")
    if len(tb) < 0x81:
        length = bytes([len(tb)])
    else:
        length = b"\x81" + len(tb).to_bytes(2, "little")
    return b"\x04\x0bstreamtyped\x81\xe8\x03NSString\x01\x94\x84\x01+" + length + tb + b"\x86\x84"


def test_decode_short_text():
    assert decode_attributed_body(_blob("hello world")) == "hello world"


def test_decode_long_text_two_byte_length():
    long = "x" * 300
    assert decode_attributed_body(_blob(long)) == long


def test_decode_unicode_and_emoji():
    s = "café — done 🎉"
    assert decode_attributed_body(_blob(s)) == s


def test_decode_empty_or_garbage():
    assert decode_attributed_body(b"") == ""
    assert decode_attributed_body(b"no marker here") == ""


def _make_chatdb(path, rows, self_id="+1555"):
    """rows: list of (chat_identifier, apple_date, text, blob, is_from_me)."""
    import sqlite3
    con = sqlite3.connect(path)
    con.executescript(
        "CREATE TABLE message (ROWID INTEGER PRIMARY KEY, date INTEGER, text TEXT, "
        "attributedBody BLOB, is_from_me INTEGER);"
        "CREATE TABLE chat (ROWID INTEGER PRIMARY KEY, chat_identifier TEXT);"
        "CREATE TABLE chat_message_join (chat_id INTEGER, message_id INTEGER);"
    )
    chats = {}
    for i, (chat_id, date, text, blob, mine) in enumerate(rows, 1):
        if chat_id not in chats:
            chats[chat_id] = len(chats) + 1
            con.execute("INSERT INTO chat VALUES (?, ?)", (chats[chat_id], chat_id))
        con.execute("INSERT INTO message (ROWID, date, text, attributedBody, is_from_me) VALUES (?,?,?,?,?)",
                    (i, date, text, blob, mine))
        con.execute("INSERT INTO chat_message_join VALUES (?, ?)", (chats[chat_id], i))
    con.commit()
    con.close()


def test_read_recent_decodes_and_isolates_self_chat(tmp_path):
    from ytk.imessage import _APPLE_EPOCH
    now = datetime(2026, 4, 19, 20, 0, 0)

    def apple(mins_ago):
        return int((now - timedelta(minutes=mins_ago)).timestamp() - _APPLE_EPOCH) * 1_000_000_000

    db = tmp_path / "chat.db"
    _make_chatdb(db, [
        ("+1555", apple(30), "plain note", None, 1),          # text column
        ("+1555", apple(20), None, _blob("blob note"), 1),    # decoded from blob
        ("+1555", apple(10), None, _blob("￼"), 1),            # attachment-only -> skipped
        ("+1999", apple(15), "someone else", None, 1),        # different chat -> excluded
        ("+1555", apple(9999), "too old", None, 1),           # outside window -> excluded
    ])
    thread = read_recent(days=3, now=now, self_id="+1555", db_path=db)
    assert [m.text for m in thread.messages] == ["plain note", "blob note"]


def test_read_recent_missing_db_or_self_is_empty(tmp_path):
    assert read_recent(self_id="", db_path=tmp_path / "nope.db").messages == []
    assert read_recent(self_id="+1555", db_path=tmp_path / "nope.db").messages == []


def test_split_urls_separates_links_from_prose():
    urls, prose = split_urls("check this https://youtu.be/abc it's great")
    assert urls == ["https://youtu.be/abc"]
    assert prose == "check this  it's great" or "great" in prose


def test_split_urls_trims_trailing_punctuation():
    urls, _ = split_urls("see https://example.com/x.")
    assert urls == ["https://example.com/x"]


def test_split_urls_link_only_leaves_no_prose():
    urls, prose = split_urls("https://instagram.com/reel/xyz/")
    assert urls == ["https://instagram.com/reel/xyz/"]
    assert prose == ""


def test_split_urls_multiple_links():
    urls, _ = split_urls("https://a.com and https://b.com")
    assert urls == ["https://a.com", "https://b.com"]


def _entry(ts: str, text: str) -> MessageEntry:
    """Build a MessageEntry with an export-format timestamp."""
    return MessageEntry(sender="Me", timestamp=ts, text=text)


def _thread(*entries: MessageEntry) -> MessageThread:
    return MessageThread(contact="+15551234567", date="Apr 19, 2026", messages=list(entries))


# A fixed "now" far in the future so every session is considered closed unless
# a test overrides it.
FAR_FUTURE = datetime(2030, 1, 1, 0, 0, 0)


def test_single_burst_is_one_session():
    thread = _thread(
        _entry("Apr 19, 2026 7:46:00 PM", "first thought"),
        _entry("Apr 19, 2026 7:50:00 PM", "still going"),
        _entry("Apr 19, 2026 7:59:00 PM", "one more"),
    )
    sessions = sessionize(thread, gap_minutes=20, now=FAR_FUTURE)
    assert len(sessions) == 1
    assert len(sessions[0].messages) == 3


def test_gap_over_window_splits():
    thread = _thread(
        _entry("Apr 19, 2026 7:46:00 PM", "morning idea"),
        _entry("Apr 19, 2026 8:30:00 PM", "afternoon idea"),  # 44 min gap
    )
    sessions = sessionize(thread, gap_minutes=20, now=FAR_FUTURE)
    assert len(sessions) == 2
    assert sessions[0].messages[0].text == "morning idea"
    assert sessions[1].messages[0].text == "afternoon idea"


def test_gap_exactly_at_window_stays_together():
    thread = _thread(
        _entry("Apr 19, 2026 7:00:00 PM", "a"),
        _entry("Apr 19, 2026 7:20:00 PM", "b"),  # exactly 20 min: not > window
    )
    sessions = sessionize(thread, gap_minutes=20, now=FAR_FUTURE)
    assert len(sessions) == 1


def test_warm_session_is_withheld():
    """A session whose last message is within the window of `now` is not closed."""
    thread = _thread(_entry("Apr 19, 2026 7:46:00 PM", "just jotted this"))
    now = datetime(2026, 4, 19, 19, 50, 0)  # 4 min after the note
    assert sessionize(thread, gap_minutes=20, now=now) == []
    # Once the window elapses, it appears.
    later = datetime(2026, 4, 19, 20, 10, 0)  # 24 min after
    assert len(sessionize(thread, gap_minutes=20, now=later)) == 1


def test_marker_forces_override_even_when_warm():
    thread = _thread(_entry("Apr 19, 2026 7:46:00 PM", f"ingest this now {MARKER}"))
    now = datetime(2026, 4, 19, 19, 47, 0)  # 1 min after: still warm
    sessions = sessionize(thread, gap_minutes=20, now=now)
    assert len(sessions) == 1
    assert sessions[0].override is True
    # Marker is stripped from the stored text.
    assert MARKER not in sessions[0].messages[0].text
    assert sessions[0].messages[0].text == "ingest this now"


def test_marker_only_message_marks_override_and_is_dropped():
    thread = _thread(
        _entry("Apr 19, 2026 7:46:00 PM", "the real thought"),
        _entry("Apr 19, 2026 7:47:00 PM", MARKER),
    )
    sessions = sessionize(thread, gap_minutes=20, now=FAR_FUTURE)
    assert len(sessions) == 1
    assert sessions[0].override is True
    assert [m.text for m in sessions[0].messages] == ["the real thought"]


def test_out_of_order_timestamps_are_sorted():
    thread = _thread(
        _entry("Apr 19, 2026 8:00:00 PM", "second"),
        _entry("Apr 19, 2026 7:00:00 PM", "first"),
    )
    sessions = sessionize(thread, gap_minutes=20, now=FAR_FUTURE)
    assert len(sessions) == 2
    assert sessions[0].messages[0].text == "first"


def test_note_id_is_stable_and_unique():
    thread = _thread(
        _entry("Apr 19, 2026 7:00:00 PM", "a"),
        _entry("Apr 19, 2026 8:00:00 PM", "b"),
    )
    s1 = sessionize(thread, gap_minutes=20, now=FAR_FUTURE)
    s2 = sessionize(thread, gap_minutes=20, now=FAR_FUTURE)
    # deterministic across runs
    assert [s.note_id for s in s1] == [s.note_id for s in s2]
    # distinct sessions get distinct ids
    assert s1[0].note_id != s1[1].note_id
    # URL-shaped so it flows through the URL-keyed queue
    assert s1[0].note_id.startswith("imessage:session:")


def test_as_thread_carries_session_date_and_text():
    thread = _thread(
        _entry("Apr 19, 2026 7:46:00 PM", "one"),
        _entry("Apr 19, 2026 7:47:00 PM", "two"),
    )
    session = sessionize(thread, gap_minutes=20, now=FAR_FUTURE)[0]
    sub = session.as_thread()
    assert sub.date == "Apr 19, 2026"
    assert [m.text for m in sub.messages] == ["one", "two"]
