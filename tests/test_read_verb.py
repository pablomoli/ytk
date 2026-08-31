"""The read verb (#197 P2): item -> evidence bundle; the quality gate may
raise an ask. Corpus untouched.

Ask kinds and triggers are the spec's Asks table: "transcript junk" (no
captions; auto-captions with a garble score; language not en; whisper
no_speech) and "blind item" (visual-heavy source with frames failed or no
transcript).
"""

from __future__ import annotations

import json

import pytest

from ytk import evidence, ledger


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("YTK_LEDGER", str(tmp_path / "ledger.db"))
    monkeypatch.setenv("YTK_EVIDENCE", str(tmp_path / "evidence"))
    monkeypatch.setenv("YTK_CAPTURE_LOG", "off")
    return tmp_path


def bundle(**over) -> evidence.EvidenceBundle:
    base: dict = {
        "source": "youtube",
        "url": "https://y/1",
        "title": "T",
        "transcript": [{"start": 0, "duration": 2, "text": "hello there"}],
        "transcript_origin": "api-manual",
        "transcript_language": "en",
        "transcript_status": "ok",
        "description": "d",
        "caption": None,
        "text": None,
        "frames": [],
        "gaps": [],
    }
    base.update(over)
    return evidence.EvidenceBundle(**base)


# ---------------------------------------------------------------- gate, pure


def test_clean_manual_transcript_raises_nothing():
    assert evidence.quality_asks(bundle()) == []


def test_missing_transcript_is_junk():
    asks = evidence.quality_asks(
        bundle(transcript=[], transcript_origin="none", transcript_status="none")
    )
    assert [a["kind"] for a in asks] == ["transcript junk"]


def test_no_speech_is_junk():
    asks = evidence.quality_asks(
        bundle(transcript=[], transcript_origin="whisper", transcript_status="no_speech")
    )
    assert [a["kind"] for a in asks] == ["transcript junk"]


def test_wrong_language_is_junk():
    asks = evidence.quality_asks(bundle(transcript_language="pt"))
    assert [a["kind"] for a in asks] == ["transcript junk"]


def test_garbled_auto_captions_are_junk():
    garbage = [{"start": i, "duration": 1, "text": "foreign music playing"} for i in range(40)]
    asks = evidence.quality_asks(bundle(transcript=garbage, transcript_origin="api-auto"))
    assert [a["kind"] for a in asks] == ["transcript junk"]


def test_clean_auto_captions_pass():
    lines = [
        {"start": i, "duration": 1, "text": f"sentence number {i} about a distinct topic"}
        for i in range(40)
    ]
    assert evidence.quality_asks(bundle(transcript=lines, transcript_origin="api-auto")) == []


def test_visual_source_with_no_frames_and_no_transcript_is_blind():
    asks = evidence.quality_asks(
        bundle(
            source="instagram",
            transcript=[],
            transcript_origin="none",
            transcript_status="no_speech",
            frames=[],
        )
    )
    # One ask per item at a time, quality order: junk outranks blind only when
    # a transcript was expected and garbled; a silent visual item is blind.
    assert [a["kind"] for a in asks] == ["blind item"]


def test_web_text_needs_no_transcript():
    b = bundle(
        source="web",
        transcript=[],
        transcript_origin="none",
        transcript_status="none",
        text="an article body",
    )
    assert evidence.quality_asks(b) == []


def test_garble_score_high_on_repetition():
    garbage = [{"text": "foreign music playing"}] * 30
    clean = [{"text": f"a different line {i}"} for i in range(30)]
    assert evidence.garble_score(garbage) > evidence.GARBLE_THRESHOLD
    assert evidence.garble_score(clean) < evidence.GARBLE_THRESHOLD


def test_boilerplate_strip_drops_known_chrome():
    text = (
        "Accept all cookies\nReal paragraph one.\nSubscribe to our newsletter\nReal paragraph two."
    )
    stripped, dropped = evidence.strip_boilerplate(text)
    assert "cookies" not in stripped
    assert "newsletter" not in stripped
    assert "Real paragraph one." in stripped and "Real paragraph two." in stripped
    assert len(dropped) == 2


# ---------------------------------------------------------------- read_item


def test_read_writes_bundle_and_advances_state(env, monkeypatch):
    conn = ledger.connect()
    item = ledger.insert_item(conn, source="youtube", url="https://y/1", provenance="hub")
    ledger.insert_activity(conn, item, actor="owner", action="capture", to_state="captured")
    # A take, or P3's intent-missing ask fires (tests/test_asks.py covers that).
    ledger.insert_take(conn, item, kind="intent", text="why I captured it")
    monkeypatch.setitem(evidence.GATHERERS, "youtube", lambda url, title: bundle())
    result = evidence.read_item(conn, item)
    assert result.ask_id is None
    assert ledger.item_state(conn, item) == "read"
    saved = json.loads(result.bundle_path.read_text())
    assert saved["transcript_origin"] == "api-manual"
    row = conn.execute("SELECT payload_ref FROM items WHERE id = ?", (item,)).fetchone()
    assert row["payload_ref"] == str(result.bundle_path)


def test_read_raises_one_ask_and_parks_in_asking(env, monkeypatch):
    conn = ledger.connect()
    item = ledger.insert_item(conn, source="youtube", url="https://y/1", provenance="hub")
    ledger.insert_activity(conn, item, actor="owner", action="capture", to_state="captured")
    monkeypatch.setitem(
        evidence.GATHERERS,
        "youtube",
        lambda url, title: bundle(
            transcript=[], transcript_origin="none", transcript_status="none"
        ),
    )
    result = evidence.read_item(conn, item)
    assert result.ask_id is not None
    assert ledger.item_state(conn, item) == "asking"
    ask = conn.execute("SELECT * FROM asks WHERE id = ?", (result.ask_id,)).fetchone()
    assert ask["kind"] == "transcript junk"
    proposal = json.loads(ask["proposal"])
    assert proposal["options"]  # accept / retry / drop choices exist


def test_read_failure_records_activity_without_transition(env, monkeypatch):
    conn = ledger.connect()
    item = ledger.insert_item(conn, source="youtube", url="https://y/1", provenance="hub")
    ledger.insert_activity(conn, item, actor="owner", action="capture", to_state="captured")

    def boom(url, title):
        raise RuntimeError("network down")

    monkeypatch.setitem(evidence.GATHERERS, "youtube", boom)
    result = evidence.read_item(conn, item)
    assert result.error == "network down"
    assert ledger.item_state(conn, item) == "captured"
    row = conn.execute(
        "SELECT action, to_state, reason FROM activity WHERE item_id = ? ORDER BY id DESC LIMIT 1",
        (item,),
    ).fetchone()
    assert row["action"] == "read"
    assert row["to_state"] is None
    assert "network down" in row["reason"]


def test_read_backfills_missing_item_title(env, monkeypatch):
    # #200: a hub Add-box capture has title NULL; the read learns it and the
    # digest card must not show a raw URL.
    conn = ledger.connect()
    item = ledger.insert_item(conn, source="youtube", url="https://y/1", provenance="hub")
    ledger.insert_activity(conn, item, actor="owner", action="capture", to_state="captured")
    ledger.insert_take(conn, item, kind="intent", text="why")
    monkeypatch.setitem(evidence.GATHERERS, "youtube", lambda url, title: bundle(title="Learned"))
    evidence.read_item(conn, item)
    row = conn.execute("SELECT title FROM items WHERE id = ?", (item,)).fetchone()
    assert row["title"] == "Learned"
