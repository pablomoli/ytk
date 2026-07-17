"""Tests for the ingest-hub backend (ytk/ui/hub.py) — no network, no SDK."""

from __future__ import annotations

import time

import pytest

from ytk import reels


NOTE_TEMPLATE = """---
url: {url}
title: A note
tags:
  - existing
type: instagram
image_paths:
  - sources/instagram/cover.jpg
---

Body.
"""


@pytest.fixture
def hub(tmp_path, monkeypatch):
    import ytk.ui.hub as hub_mod

    brain = tmp_path / "brain"
    (brain / "sources" / "instagram").mkdir(parents=True)
    (brain / "sources" / "instagram" / "cover.jpg").write_bytes(b"jpg")
    monkeypatch.setattr("ytk.vault._get_brain_path", lambda: brain)
    monkeypatch.setattr(hub_mod, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(hub_mod, "JOB_PATH", tmp_path / "ingest-job.json")
    monkeypatch.setattr(hub_mod, "PACING_SECONDS", 0.0)
    monkeypatch.setattr(hub_mod, "REINDEX", lambda: 0)
    # reset job state between tests
    hub_mod._JOB.update(running=False, total=0, done=0, current=None,
                        current_started=None, queued=[], failures=[],
                        annotated=0, linked=[])
    hub_mod._QUEUE.clear()
    hub_mod._ATTEMPTS.clear()
    hub_mod.brain = brain
    return hub_mod


def _simulate_restart(hub_mod):
    """Drop every scrap of in-memory job state, as a killed hub process would.

    The queue file on disk is all a fresh process inherits.
    """
    hub_mod._QUEUE.clear()
    hub_mod._ATTEMPTS.clear()
    hub_mod._JOB.update(running=False, total=0, done=0, current=None,
                        current_started=None, queued=[], failures=[],
                        annotated=0, linked=[])


def _wait_done(hub_mod, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not hub_mod.job_status()["running"]:
            return hub_mod.job_status()
        time.sleep(0.02)
    raise TimeoutError("ingest job never finished")


def _wait_current(hub_mod, url, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if hub_mod.job_status()["current"] == url:
            return hub_mod.job_status()
        time.sleep(0.02)
    raise TimeoutError(f"{url} never went in flight")


def test_queue_add_classifies_dedupes_persists(hub):
    n = hub.queue_add(["https://youtu.be/abc", "https://youtu.be/abc", ""])
    assert n == 1
    items = hub.queue_items()
    assert [i.source for i in items] == ["youtube"]
    # persisted
    assert reels.load_state(hub.STATE_PATH).pending[0].url == "https://youtu.be/abc"


def test_ingest_annotates_digests_and_dequeues(hub):
    url = "https://www.instagram.com/reel/abc/"
    hub.queue_add([url])

    def fake_ingest(u, note=""):
        p = hub.brain / "sources" / "instagram" / "someone-abc.md"
        p.write_text(NOTE_TEMPLATE.format(url=u), encoding="utf-8")

    hub.INGEST = fake_ingest
    started = hub.start_ingest([url], tags=["build-idea"], thought="I want one.")
    assert started == 1
    status = _wait_done(hub)

    assert status["done"] == 1
    assert status["annotated"] == 1
    assert status["failures"] == []
    assert hub.queue_items() == []

    note_text = (hub.brain / "sources" / "instagram" / "someone-abc.md").read_text()
    assert "- build-idea" in note_text
    assert "## My take" in note_text
    digests = list((hub.brain / "inbox").glob("review-*.md"))
    assert len(digests) == 1
    assert "[[someone-abc]]" in digests[0].read_text()


def test_ingest_failure_keeps_item_queued(hub):
    url = "https://www.instagram.com/reel/bad/"
    hub.queue_add([url])

    def exploding(u, note=""):
        raise RuntimeError("fetch failed")

    hub.INGEST = exploding
    hub.start_ingest([url], tags=[], thought="")
    status = _wait_done(hub)

    assert status["failures"][0]["url"] == url
    assert [i.url for i in hub.queue_items()] == [url]


def test_ingest_rejects_bad_urls_and_appends_while_running(hub):
    hub.queue_add(["https://youtu.be/abc", "https://youtu.be/def"])
    with pytest.raises(ValueError):
        hub.start_ingest(["https://youtu.be/nope"], tags=[], thought="")
    with pytest.raises(ValueError):
        hub.start_ingest([], tags=[], thought="")

    import threading

    gate = threading.Event()

    def slow(u, note=""):
        gate.wait(timeout=5)

    hub.INGEST = slow
    hub.start_ingest(["https://youtu.be/abc"], tags=[], thought="")
    # re-queuing the in-flight url is a no-op; a new url appends to the job
    assert hub.start_ingest(["https://youtu.be/abc"], tags=[], thought="") == 0
    assert hub.start_ingest(["https://youtu.be/def"], tags=[], thought="") == 1
    status = hub.job_status()
    assert status["total"] == 2
    # abc is either in-flight or still queued depending on worker timing,
    # but def is queued exactly once and abc was not duplicated
    assert status["queued"].count("https://youtu.be/def") == 1
    assert status["queued"].count("https://youtu.be/abc") <= 1
    gate.set()
    status = _wait_done(hub)
    assert status["done"] == 2


def test_inflight_item_stays_on_the_persisted_queue(hub):
    """The item being worked stays on disk for the whole ~2 minutes it takes, so
    a hub killed mid-video (uv reinstall, launchd restart) can resume it."""
    import threading

    urls = ["https://youtu.be/one", "https://youtu.be/two"]
    hub.queue_add(urls)
    gate = threading.Event()

    def slow(u, note=""):
        gate.wait(timeout=5)

    hub.INGEST = slow
    hub.start_ingest(urls, tags=["learning"], thought="watch later")
    _wait_current(hub, urls[0])

    entries = hub._load_persisted()
    assert [e["url"] for e in entries] == urls, "in-flight item is still on disk"
    assert entries[0]["tags"] == ["learning"]
    assert entries[0]["thought"] == "watch later"
    assert entries[0]["attempts"] == 1

    gate.set()
    _wait_done(hub)
    assert hub._load_persisted() == [], "a drained queue leaves nothing behind"


def test_restart_mid_batch_resumes_the_unfinished_items(hub):
    """A hub killed mid-batch must not silently drop the rest of the queue."""
    urls = [f"https://youtu.be/{k}" for k in ("one", "two", "three")]
    hub.queue_add(urls)
    hub.INGEST = lambda u, note="": None
    hub.start_ingest(urls[:1], tags=[], thought="")  # the first one got through
    _wait_done(hub)

    # the file the killed process left behind: two videos still owed
    hub._write_persisted([
        {"url": u, "tags": ["learning"], "thought": "watch later", "attempts": 1}
        for u in urls[1:]
    ])
    _simulate_restart(hub)
    assert hub.job_status()["running"] is False

    ingested: list[str] = []
    hub.INGEST = lambda u, note="": ingested.append(u)

    assert hub.resume_ingest() == 2, "the two unfinished videos come back"
    status = _wait_done(hub)
    assert status["done"] == 2
    assert ingested == urls[1:], "each resumed video ingests exactly once"
    assert hub.queue_items() == []
    assert hub._load_persisted() == []


def test_resume_skips_items_that_already_landed(hub):
    """An item removed from pending made it into the vault before the restart."""
    urls = ["https://youtu.be/a", "https://youtu.be/b"]
    hub.queue_add(urls)
    hub.INGEST = lambda u, note="": None
    hub.start_ingest(urls, tags=[], thought="")
    _wait_done(hub)

    _simulate_restart(hub)
    assert hub.resume_ingest() == 0


def test_resume_abandons_an_item_that_keeps_killing_the_hub(hub):
    """A poison-pill video must not crash-loop forever against launchd KeepAlive."""
    url = "https://youtu.be/poison"
    hub.queue_add([url])
    hub.INGEST = lambda u, note="": None

    hub.start_ingest([url], tags=[], thought="")
    _wait_done(hub)
    # rewrite the file as if the hub had died on this item MAX_ATTEMPTS times
    hub._write_persisted([
        {"url": url, "tags": [], "thought": "", "attempts": hub.MAX_ATTEMPTS}
    ])
    _simulate_restart(hub)
    hub.queue_add([url])

    assert hub.resume_ingest() == 0
    assert hub._load_persisted() == []


def test_fresh_notes_lists_recent_with_thumbnails(hub):
    note = hub.brain / "sources" / "instagram" / "someone-abc.md"
    note.write_text(
        NOTE_TEMPLATE.format(url="https://www.instagram.com/reel/abc/"),
        encoding="utf-8",
    )
    older = hub.brain / "sources" / "instagram" / "older.md"
    older.write_text("---\nurl: https://x/\ntitle: Old\ntype: instagram\n---\n")
    import os

    os.utime(older, (1, 1))

    notes = hub.fresh_notes(n=10)
    assert notes[0]["stem"] == "someone-abc"
    assert notes[0]["source"] == "instagram"
    assert notes[0]["thumbnail"] == "sources/instagram/cover.jpg"
    assert notes[0]["tags"] == ["existing"]
    assert notes[0]["has_take"] is False
    assert notes[-1]["stem"] == "older"
    # 'added' reflects ingestion time (mtime) — the ordering key shown on cards
    import datetime
    assert notes[0]["added"] == datetime.date.today().isoformat()
    assert notes[-1]["added"] == datetime.date.fromtimestamp(1).isoformat()


# --- API endpoints ---------------------------------------------------------------


@pytest.fixture
def client(hub):
    from fastapi.testclient import TestClient

    from ytk.ui.server import app

    return TestClient(app)


def test_imessage_warm_returns_only_open_sessions(hub, monkeypatch):
    from datetime import datetime, timedelta
    from ytk.imessage import MessageEntry, MessageThread

    now = datetime.now()
    def ts(mins):
        return (now - timedelta(minutes=mins)).strftime("%b %d, %Y %I:%M:%S %p")

    thread = MessageThread(contact="+1555", date="", messages=[
        MessageEntry("Me", ts(120), "old closed note"),  # 2h ago -> closed session
        MessageEntry("Me", ts(5), "fresh warm note"),    # 5 min ago -> still warm
    ])
    monkeypatch.setattr("ytk.imessage.read_recent", lambda **k: thread)
    # pin the silence window: imessage_warm reads the user's real config,
    # and a gap of 0 there closes every session instantly
    from ytk.config import Config
    monkeypatch.setattr("ytk.ui.hub.load_config", lambda: Config())

    warm = hub.imessage_warm()
    assert len(warm) == 1
    assert "fresh warm note" in warm[0]["text"]
    assert "old closed note" not in warm[0]["text"]
    assert warm[0]["minutes_left"] > 0


def test_imessage_warm_endpoint(client, hub, monkeypatch):
    monkeypatch.setattr("ytk.imessage.read_recent",
                        lambda **k: __import__("ytk.imessage", fromlist=["MessageThread"]).MessageThread("+1", "", []))
    assert client.get("/api/imessage-warm").json() == {"warm": []}


def test_ready_endpoint_reflects_search_flag(client, hub):
    import ytk.ui.hub as hm
    prev = hm._READY["search"]
    try:
        hm._READY["search"] = False
        body = client.get("/api/ready").json()
        assert body["search"] is False
        assert isinstance(body["capture_problems"], list)
        hm._READY["search"] = True
        assert client.get("/api/ready").json()["search"] is True
    finally:
        hm._READY["search"] = prev


def test_warm_search_noop_when_already_ready(hub):
    import ytk.ui.hub as hm
    prev = hm._READY["search"]
    try:
        hm._READY["search"] = True
        assert hm.warm_search() is False  # already warm -> no thread spawned
    finally:
        hm._READY["search"] = prev


def test_api_queue_add_and_list(client, hub):
    r = client.post("/api/queue/add", json={"urls": ["https://youtu.be/abc"]})
    assert r.status_code == 200
    assert r.json()["added"] == 1
    r = client.get("/api/queue")
    items = r.json()["items"]
    assert items[0]["url"] == "https://youtu.be/abc"
    assert items[0]["source"] == "youtube"
    assert items[0]["n"] == 1


def test_api_ingest_flow_and_status(client, hub):
    url = "https://www.instagram.com/reel/abc/"
    hub.queue_add([url])

    def fake_ingest(u, note=""):
        p = hub.brain / "sources" / "instagram" / "someone-abc.md"
        p.write_text(NOTE_TEMPLATE.format(url=u), encoding="utf-8")

    hub.INGEST = fake_ingest
    r = client.post(
        "/api/ingest", json={"urls": [url], "tags": ["design"], "thought": "nice"}
    )
    assert r.status_code == 200
    assert r.json()["started"] == 1
    _wait_done(hub)
    status = client.get("/api/ingest/status").json()
    assert status["done"] == 1 and status["running"] is False


def test_api_ingest_bad_urls_400(client, hub):
    r = client.post("/api/ingest", json={"urls": ["https://x/nope"], "tags": [], "thought": ""})
    assert r.status_code == 400


def test_api_fresh(client, hub):
    (hub.brain / "sources" / "instagram" / "someone-abc.md").write_text(
        NOTE_TEMPLATE.format(url="https://x/"), encoding="utf-8"
    )
    r = client.get("/api/fresh")
    assert r.status_code == 200
    assert r.json()[0]["stem"] == "someone-abc"


def test_vault_media_serves_images_and_blocks_traversal(client, hub):
    r = client.get("/vault-media/sources/instagram/cover.jpg")
    assert r.status_code == 200
    r = client.get("/vault-media/../../etc/passwd")
    assert r.status_code in (400, 404)


def test_fresh_notes_flags_my_take(hub):
    note = hub.brain / "sources" / "instagram" / "taken.md"
    note.write_text(
        NOTE_TEMPLATE.format(url="https://x/") + "\n## My take\n\nmine\n",
        encoding="utf-8",
    )
    assert hub.fresh_notes(n=5)[0]["has_take"] is True


# --- source pulls + buckets -------------------------------------------------------


def test_refresh_sources_pulls_instagram_and_youtube(hub, monkeypatch):
    monkeypatch.setenv("INSTAGRAM_SESSIONID", "sess")
    ig_item = reels.ReelItem(url="https://www.instagram.com/reel/x/", source="instagram")

    def fake_ig_pull(state):
        state.pending.append(ig_item)
        return 1

    monkeypatch.setattr(hub, "IG_PULL", fake_ig_pull)
    monkeypatch.setattr(
        hub, "YT_FETCH",
        lambda: [
            {"video_id": "new1", "title": "A new video", "added_at": "2026-07-04T01:00:00Z"},
            {"video_id": "old1", "title": "Old", "added_at": "2026-07-01T01:00:00Z"},
        ],
    )
    monkeypatch.setattr(hub, "YT_IS_PROCESSED", lambda vid: vid == "old1")
    monkeypatch.setattr(hub, "PIN_FETCH", lambda: [])

    result = hub.refresh_sources()

    assert result["instagram"] == 1
    assert result["youtube"] == 1
    urls = [i.url for i in hub.queue_items()]
    assert "https://www.youtube.com/watch?v=new1" in urls
    yt = [i for i in hub.queue_items() if i.source == "youtube"][0]
    assert yt.author == "A new video"
    assert yt.preview_url == "https://i.ytimg.com/vi/new1/hqdefault.jpg"
    assert yt.shared_at == "2026-07-04"


def _quiet_other_sources(hub, monkeypatch):
    monkeypatch.setattr(hub, "IG_PULL", lambda state: 0)
    monkeypatch.setattr(hub, "YT_FETCH", lambda: [])
    monkeypatch.setattr(hub, "YT_IS_PROCESSED", lambda vid: False)
    monkeypatch.setattr(hub, "PIN_FETCH", lambda: [])


def test_refresh_sources_queues_imessage_sessions(hub, monkeypatch):
    from ytk.imessage import MessageEntry, MessageThread, sessionize
    from datetime import datetime

    _quiet_other_sources(hub, monkeypatch)
    thread = MessageThread(
        contact="+1555", date="Apr 19, 2026",
        messages=[MessageEntry("Me", "Apr 19, 2026 7:00:00 PM", "a walk thought")],
    )
    sessions = sessionize(thread, gap_minutes=20, now=datetime(2030, 1, 1))
    monkeypatch.setattr(hub, "IM_FETCH", lambda: sessions)

    result = hub.refresh_sources()
    assert result["imessage"] == 1
    item = [i for i in hub.queue_items() if i.source == "imessage"][0]
    assert item.text == "a walk thought"
    assert item.url.startswith("imessage:session:")

    # A second pull must not re-queue the same session (imessage_seen persists).
    monkeypatch.setattr(hub, "IM_FETCH", lambda: sessions)
    result2 = hub.refresh_sources(force=True)
    assert result2["imessage"] == 0


def _im_session(hub, monkeypatch, text, now=None):
    from ytk.imessage import MessageEntry, MessageThread, sessionize
    from datetime import datetime

    _quiet_other_sources(hub, monkeypatch)
    thread = MessageThread(
        contact="+1555", date="Apr 19, 2026",
        messages=[MessageEntry("Me", "Apr 19, 2026 7:00:00 PM", text)],
    )
    sessions = sessionize(thread, gap_minutes=20, now=now or datetime(2030, 1, 1))
    monkeypatch.setattr(hub, "IM_FETCH", lambda: sessions)
    return sessions


def test_link_with_prose_stays_one_note_with_link_embedded(hub, monkeypatch):
    _im_session(hub, monkeypatch, "loved this https://youtu.be/abc watch later")
    hub.refresh_sources()
    items = hub.queue_items()
    # no standalone fetch item — the pairing is kept together
    assert not [i for i in items if i.url == "https://youtu.be/abc"]
    im = [i for i in items if i.source == "imessage"]
    assert len(im) == 1
    assert "https://youtu.be/abc" in im[0].text and "watch later" in im[0].text


def test_imessage_ingest_pairs_link_via_add(hub, monkeypatch):
    called = {}
    def fake_ingest(url, note=""):
        called["url"] = url
        called["note"] = note
        p = hub.brain / "sources" / "youtube" / "vid.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"---\nurl: {url}\n---\nbody", encoding="utf-8")
    monkeypatch.setattr(hub, "INGEST", fake_ingest)

    item = reels.ReelItem(
        url="imessage:session:x", source="imessage", author="Apr 19, 2026",
        text="must watch https://youtu.be/abc great point",
    )
    note = hub.ingest_imessage_item(item, "inbox thought")

    # reused the add pipeline; prose + inbox thought both steer enrichment
    assert called["url"] == "https://youtu.be/abc"
    assert "great point" in called["note"] and "inbox thought" in called["note"]
    # returns the fetched source note (the pairing), not a separate journal note
    assert note and note.name == "vid.md"


def test_imessage_ingest_routes_like_a_memo(hub, monkeypatch):
    calls = {}
    def fake_write(transcript, audio, source="voice"):
        calls["write"] = (transcript, audio, source)
        p = hub.brain / "inbox" / "memos" / "note.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("---\nroute: pending\n---\nbody", encoding="utf-8")
        return p
    class R:  # minimal MemoResult stand-in
        kind = "thought"
    monkeypatch.setattr(hub, "memo_write_note", fake_write)
    monkeypatch.setattr(hub, "memo_route", lambda t, repos=None: calls.setdefault("route", t) and R or R)
    monkeypatch.setattr(hub, "memo_execute", lambda r, t, repos: [])
    monkeypatch.setattr(hub, "memo_finalize", lambda p, k, lines: calls.setdefault("finalize", k))
    monkeypatch.setattr(hub, "memo_index", lambda p, t, k: calls.setdefault("index", k))

    item = reels.ReelItem(url="imessage:session:x", source="imessage",
                          text="just a thought\n\nsecond note")
    path = hub.ingest_imessage_item(item, "picked note")

    assert path and path.name == "note.md"
    transcript, audio, source = calls["write"]
    assert audio is None and source == "imessage"
    assert "second note" in transcript and "[inbox note] picked note" in transcript
    assert calls["finalize"] == "thought" and calls["index"] == "thought"


def test_fresh_notes_includes_memos(hub):
    memo_dir = hub.brain / "inbox" / "memos"
    memo_dir.mkdir(parents=True, exist_ok=True)
    (memo_dir / "2026-07-05-1512-test.md").write_text(
        "---\ncaptured: 2026-07-05T15:12:01\nsource: voice\n"
        "audio: /Users/x/.ytk/audio/memos/rec.wav\nroute: thought\n---\n\n"
        "And it starts listening to me.\n", encoding="utf-8")
    notes = hub.fresh_notes()
    memos = [n for n in notes if n["source"] == "memo"]
    assert len(memos) == 1
    m = memos[0]
    assert m["audio"] == "rec.wav"
    assert m["kind"] == "thought"
    assert m["channel"] == "voice"
    assert "listening" in m["preview"]
    assert m["title"].startswith("And it starts")

    (memo_dir / "2026-07-05-2318-texted.md").write_text(
        "---\ncaptured: 2026-07-05T23:18:00\nsource: imessage\nroute: action\n---\n\n"
        "make rae an emulator game\n", encoding="utf-8")
    texted = [n for n in hub.fresh_notes() if n["source"] == "memo"
              and n["channel"] == "imessage"]
    assert len(texted) == 1
    assert texted[0]["audio"] is None


def test_memo_audio_endpoint_serves_and_guards(client, hub, monkeypatch, tmp_path):
    audio_root = tmp_path / "memo-audio"
    audio_root.mkdir()
    (audio_root / "rec.wav").write_bytes(b"RIFFxxxx")
    monkeypatch.setattr("ytk.memo.AUDIO_DIR", audio_root)
    assert client.get("/api/memo-audio/rec.wav").status_code == 200
    assert client.get("/api/memo-audio/nope.wav").status_code == 404
    assert client.get("/api/memo-audio/..%2Frec.wav").status_code in (404, 422)


def test_bare_link_becomes_fetch_item(hub, monkeypatch):
    _im_session(hub, monkeypatch, "https://youtu.be/abc")
    hub.refresh_sources()
    items = hub.queue_items()
    yt = [i for i in items if i.url == "https://youtu.be/abc"]
    assert yt and yt[0].source == "youtube"
    assert not [i for i in items if i.source == "imessage"]


def test_refresh_sources_autoingests_marked_session(hub, monkeypatch):
    from ytk.imessage import MARKER, MessageEntry, MessageThread, sessionize
    from datetime import datetime

    _quiet_other_sources(hub, monkeypatch)
    thread = MessageThread(
        contact="+1555", date="Apr 19, 2026",
        messages=[MessageEntry("Me", "Apr 19, 2026 7:00:00 PM", f"ship it {MARKER}")],
    )
    # Warm (now == last message) but MARKER forces the session through.
    sessions = sessionize(thread, gap_minutes=20, now=datetime(2026, 4, 19, 19, 0, 0))
    assert sessions and sessions[0].override
    monkeypatch.setattr(hub, "IM_FETCH", lambda: sessions)

    ingested = []
    def fake_text_ingest(item, note=""):
        p = hub.brain / "sources" / "journal" / "note.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("---\ntype: journal\n---\nbody", encoding="utf-8")
        ingested.append(item.url)
        return p
    monkeypatch.setattr(hub, "INGEST_TEXT", fake_text_ingest)

    hub.refresh_sources()
    _wait_done(hub)
    assert ingested and ingested[0].startswith("imessage:session:")
    # auto-ingested item is removed from the queue after success
    assert not [i for i in hub.queue_items() if i.source == "imessage"]


def test_refresh_sources_only_filter_pulls_single_source(hub, monkeypatch):
    from ytk.imessage import MessageEntry, MessageThread, sessionize
    from datetime import datetime

    ig_called = []
    monkeypatch.setattr(hub, "IG_PULL", lambda state: ig_called.append(1) or 0)
    monkeypatch.setattr(hub, "YT_FETCH", lambda: (_ for _ in ()).throw(AssertionError("yt pulled")))
    monkeypatch.setattr(hub, "PIN_FETCH", lambda: [])
    thread = MessageThread(contact="+1555", date="Apr 19, 2026",
                           messages=[MessageEntry("Me", "Apr 19, 2026 7:00:00 PM", "note")])
    monkeypatch.setattr(hub, "IM_FETCH",
                        lambda: sessionize(thread, gap_minutes=20, now=datetime(2030, 1, 1)))

    result = hub.refresh_sources(force=True, only={"imessage"})
    assert result["imessage"] == 1
    assert not ig_called  # other sources skipped entirely
    assert set(result["skipped_sources"]) == {"instagram", "youtube", "pinterest"}


def test_refresh_prunes_already_ingested_urls(hub, monkeypatch):
    _quiet_other_sources(hub, monkeypatch)
    monkeypatch.setattr(hub, "IM_FETCH", lambda: [])
    hub.queue_add(["https://youtu.be/done", "https://youtu.be/fresh"])
    monkeypatch.setattr(hub, "INGESTED_URLS", lambda: {"https://youtu.be/done"})

    result = hub.refresh_sources(force=True)
    assert result["dropped_ingested"] == 1
    assert [i.url for i in hub.queue_items()] == ["https://youtu.be/fresh"]


def test_refresh_sources_survives_one_source_failing(hub, monkeypatch):
    monkeypatch.setenv("INSTAGRAM_SESSIONID", "sess")

    def broken(state):
        raise RuntimeError("login dead")

    monkeypatch.setattr(hub, "IG_PULL", broken)
    monkeypatch.setattr(hub, "YT_FETCH", lambda: [])
    monkeypatch.setattr(hub, "YT_IS_PROCESSED", lambda vid: False)
    monkeypatch.setattr(hub, "PIN_FETCH", lambda: [])

    result = hub.refresh_sources()
    assert result["youtube"] == 0
    assert "instagram" in result["errors"][0].lower() or "login" in result["errors"][0]


def test_api_refresh_and_buckets(client, hub, monkeypatch):
    monkeypatch.setattr(hub, "IG_PULL", lambda state: 0)
    monkeypatch.setattr(hub, "YT_FETCH", lambda: [])
    monkeypatch.setattr(hub, "YT_IS_PROCESSED", lambda vid: False)
    monkeypatch.setattr(hub, "PIN_FETCH", lambda: [])
    monkeypatch.delenv("INSTAGRAM_SESSIONID", raising=False)

    r = client.post("/api/queue/refresh")
    assert r.status_code == 200

    r = client.get("/api/tags")
    assert r.status_code == 200
    assert "design" in r.json()["tags"]


# --- auto-pull throttle + custom buckets ------------------------------------------


def test_refresh_sources_throttled_by_ttl(hub, monkeypatch):
    import time as _time

    monkeypatch.setattr(hub, "IG_PULL", lambda state: 1)
    monkeypatch.setattr(hub, "YT_FETCH", lambda: [])
    monkeypatch.setattr(hub, "YT_IS_PROCESSED", lambda vid: False)
    monkeypatch.setattr(hub, "PIN_FETCH", lambda: [])

    first = hub.refresh_sources()
    assert first.get("skipped") is not True

    second = hub.refresh_sources()          # immediately after: throttled
    assert second["skipped"] is True
    assert second["instagram"] == 0

    third = hub.refresh_sources(force=True) # force bypasses the TTL
    assert third.get("skipped") is not True

    st = reels.load_state(hub.STATE_PATH)
    assert st.last_pull_at is not None
    assert _time.time() - st.last_pull_at < 10


def test_custom_tags_persist_and_merge(client, hub):
    r = client.post("/api/tags", json={"name": "Anime Recs"})
    assert r.status_code == 200
    st = reels.load_state(hub.STATE_PATH)
    assert "anime-recs" in st.custom_tags

    r = client.get("/api/tags")
    tags = r.json()["tags"]
    assert "design" in tags              # config-defined
    assert "anime-recs" in tags          # UI-created
    # re-adding is a no-op, not a duplicate
    client.post("/api/tags", json={"name": "anime-recs"})
    assert reels.load_state(hub.STATE_PATH).custom_tags.count("anime-recs") == 1


def test_refresh_sources_pulls_pinterest_feeds(hub, monkeypatch):
    monkeypatch.setattr(hub, "IG_PULL", lambda state: 0)
    monkeypatch.setattr(hub, "YT_FETCH", lambda: [])
    monkeypatch.setattr(hub, "YT_IS_PROCESSED", lambda vid: False)
    monkeypatch.setattr(
        hub, "PIN_FETCH",
        lambda: [{
            "url": "https://www.pinterest.com/pin/12345/",
            "title": "A cool pin",
            "image": "https://i.pinimg.com/x.jpg",
            "date": "2026-07-04",
        }],
    )
    result = hub.refresh_sources(force=True)
    assert result["pinterest"] == 1
    pin = [i for i in hub.queue_items() if i.source == "pinterest"][0]
    assert pin.author == "A cool pin"
    assert pin.preview_url == "https://i.pinimg.com/x.jpg"


def test_ingest_forwards_thought_to_pipeline(hub):
    url = "https://www.instagram.com/reel/steer/"
    hub.queue_add([url])
    received = {}

    def fake_ingest(u, note=""):
        received["note"] = note
        (hub.brain / "sources" / "instagram" / "steer.md").write_text(
            NOTE_TEMPLATE.format(url=u), encoding="utf-8"
        )

    hub.INGEST = fake_ingest
    hub.start_ingest([url], tags=[], thought="make this about touchdesigner")
    _wait_done(hub)
    assert received["note"] == "make this about touchdesigner"


# --- local cover cache (Instagram CDN is hostile to hotlinking) -------------------


def test_cover_for_downloads_once_then_serves_cache(hub, monkeypatch, tmp_path):
    covers = tmp_path / "covers"
    monkeypatch.setattr(hub, "COVERS_DIR", covers)
    downloads = []

    def fake_download(url, dest):
        downloads.append(url)
        dest.write_bytes(b"jpegbytes")

    monkeypatch.setattr(hub, "DOWNLOAD_COVER", fake_download)
    hub.queue_add(["https://www.instagram.com/reel/abc/"])
    state = reels.load_state(hub.STATE_PATH)
    state.pending[0].preview_url = "https://scontent.cdninstagram.com/x.jpg"
    reels.save_state(state, hub.STATE_PATH)

    p1 = hub.cover_for("https://www.instagram.com/reel/abc/")
    p2 = hub.cover_for("https://www.instagram.com/reel/abc/")
    assert p1 is not None and p1 == p2
    assert p1.read_bytes() == b"jpegbytes"
    assert downloads == ["https://scontent.cdninstagram.com/x.jpg"]


def test_cover_for_unknown_url_returns_none(hub, monkeypatch, tmp_path):
    monkeypatch.setattr(hub, "COVERS_DIR", tmp_path / "covers")
    assert hub.cover_for("https://www.instagram.com/reel/nope/") is None


def test_api_cover_serves_and_404s(client, hub, monkeypatch, tmp_path):
    covers = tmp_path / "covers"
    monkeypatch.setattr(hub, "COVERS_DIR", covers)
    monkeypatch.setattr(hub, "DOWNLOAD_COVER", lambda url, dest: dest.write_bytes(b"img"))
    hub.queue_add(["https://www.instagram.com/reel/abc/"])
    state = reels.load_state(hub.STATE_PATH)
    state.pending[0].preview_url = "https://scontent.cdninstagram.com/x.jpg"
    reels.save_state(state, hub.STATE_PATH)

    r = client.get("/api/cover", params={"u": "https://www.instagram.com/reel/abc/"})
    assert r.status_code == 200
    assert r.content == b"img"
    assert "max-age" in r.headers.get("cache-control", "")

    r = client.get("/api/cover", params={"u": "https://x/unknown"})
    assert r.status_code == 404


# --- note deletion ----------------------------------------------------------------


@pytest.fixture
def spy_store(monkeypatch):
    """Record store deletions without touching ChromaDB."""
    calls = {"docs": [], "videos": [], "visual": []}
    import ytk.store as store
    monkeypatch.setattr(store, "delete_doc", lambda d: calls["docs"].append(d))
    monkeypatch.setattr(store, "delete_video", lambda v: calls["videos"].append(v))
    monkeypatch.setattr(store, "delete_visual", lambda ids: calls["visual"].append(list(ids)))
    return calls


def _rel(hub, path):
    """Card `path` field: note path relative to the vault root (brain.parent)."""
    return str(path.relative_to(hub.brain.parent))


def test_delete_note_removes_memo_file_and_vector(hub, spy_store):
    memos = hub.brain / "inbox" / "memos"
    memos.mkdir(parents=True)
    note = memos / "2026-07-06-0106-a-memo-abc.md"
    note.write_text("---\nsource: imessage\nroute: action\n---\n\nhi there\n", encoding="utf-8")

    result = hub.delete_note(_rel(hub, note))

    assert not note.exists()
    assert "memo_2026-07-06-0106-a-memo-abc" in spy_store["docs"]
    assert result["file"].endswith("2026-07-06-0106-a-memo-abc.md")


def test_delete_note_removes_youtube_video_and_visual(hub, spy_store):
    yt = hub.brain / "sources" / "youtube"
    yt.mkdir(parents=True)
    note = yt / "some-video.md"
    note.write_text(
        "---\nurl: https://www.youtube.com/watch?v=dQw4w9WgXcQ\ntitle: V\ntype: youtube\n---\n\nbody\n",
        encoding="utf-8",
    )

    hub.delete_note(_rel(hub, note))

    assert not note.exists()
    assert "dQw4w9WgXcQ" in spy_store["videos"]
    assert ["yt:dQw4w9WgXcQ"] == spy_store["visual"][0]


def test_delete_note_removes_instagram_doc_and_visual(hub, spy_store):
    note = hub.brain / "sources" / "instagram" / "someone-abc.md"
    note.write_text(
        NOTE_TEMPLATE.format(url="https://www.instagram.com/reel/abc123/"), encoding="utf-8"
    )

    hub.delete_note(_rel(hub, note))

    assert not note.exists()
    assert "note_sources_instagram_someone-abc" in spy_store["docs"]
    assert ["ig:abc123"] == spy_store["visual"][0]


def test_delete_note_prefers_frontmatter_id(hub, spy_store):
    mem = hub.brain / "inbox" / "memories" / "ytk"
    mem.mkdir(parents=True)
    note = mem / "state.md"
    note.write_text("---\nid: memory_2026_ytk_state_ab12\ntype: memory\n---\n\nstate\n", encoding="utf-8")

    hub.delete_note(_rel(hub, note))

    assert "memory_2026_ytk_state_ab12" in spy_store["docs"]


def test_delete_note_refuses_path_outside_vault(hub, spy_store):
    with pytest.raises(ValueError):
        hub.delete_note("../../../etc/passwd")
    with pytest.raises(ValueError):
        hub.delete_note("/etc/passwd")
    assert spy_store["docs"] == []


def test_delete_note_missing_file_raises(hub, spy_store):
    with pytest.raises(FileNotFoundError):
        hub.delete_note("brain/sources/instagram/ghost.md")


def test_api_delete_note(client, hub, spy_store):
    note = hub.brain / "sources" / "instagram" / "someone-abc.md"
    note.write_text(NOTE_TEMPLATE.format(url="https://x/"), encoding="utf-8")

    r = client.post("/api/note/delete", json={"path": _rel(hub, note)})
    assert r.status_code == 200
    assert r.json()["deleted"] is True
    assert not note.exists()


def test_api_delete_note_outside_vault_400(client, hub, spy_store):
    r = client.post("/api/note/delete", json={"path": "../../etc/passwd"})
    assert r.status_code == 400


def test_grove_api_aggregates_snapshots_without_attach_machinery(client, tmp_path, monkeypatch):
    import json

    import ytk.ui.server as server

    snap = {
        "version": 1, "bucket": "visual-craft", "embedding_model": "thenlper/gte-small",
        "built": "2026-07-12T20:45:00+00:00", "n_notes": 86,
        "params": {"kind": "linkage", "method": "average-cosine", "k_main": 3},
        "stability": {"kind": "temporal", "ari": 0.813, "span_days": 337},
        "nodes": [
            {"id": 0, "parent": -1, "mass": 86, "persistence": 0.1,
             "centroid": [0.0] * 384, "exemplars": ["a title"]},
        ],
        "members": {"some/note.md": 0},
    }
    grove = tmp_path / "grove"
    grove.mkdir()
    (grove / "visual-craft.tree.json").write_text(json.dumps(snap))
    monkeypatch.setattr(server, "_GROVE_DIR", grove)

    r = client.get("/api/grove")
    assert r.status_code == 200
    data = r.json()
    assert len(data["buckets"]) == 1
    b = data["buckets"][0]
    assert b["bucket"] == "visual-craft"
    assert b["stability"]["ari"] == 0.813
    # attach-time machinery stays server-side
    assert "members" not in b
    assert "centroid" not in b["nodes"][0]
    assert b["nodes"][0]["exemplars"] == ["a title"]


def test_grove_api_404_when_no_snapshots(client, tmp_path, monkeypatch):
    import ytk.ui.server as server

    monkeypatch.setattr(server, "_GROVE_DIR", tmp_path / "empty")
    assert client.get("/api/grove").status_code == 404


@pytest.fixture
def e7_grove(client, tmp_path, monkeypatch):
    import json

    import ytk.ui.server as server

    grove = tmp_path / "grove"
    grove.mkdir()
    manifest = {
        "version": 2, "sha256": "abc", "analysis_version": "e7-prereg-2",
        "stimuli": [{"id": "s00", "nodes": [], "n_notes": 5,
                     "geometry_seed": 7, "camera_azimuth": 1.2}],
        "trials": [
            {"trial": "T1-x-0", "task": "semantic-readback", "bucket": "x",
             "left": "s00", "right": "s00", "prompt": "?"},
            {"trial": "T3-x-0", "task": "identification-exploratory", "bucket": "x",
             "single": "s00", "options": ["x", "y", "z"], "prompt": "?"},
        ],
    }
    (grove / "e7-manifest.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(server, "_GROVE_DIR", grove)
    return grove


def test_e7_get_serves_manifest_with_completed_list(client, e7_grove):
    r = client.get("/api/grove/e7")
    assert r.status_code == 200
    data = r.json()
    assert data["sha256"] == "abc"
    assert data["completed"] == []
    client.post("/api/grove/e7/response", json={
        "trial": "T1-x-0", "choice": "left", "confidence": 4, "rt_ms": 2100})
    assert client.get("/api/grove/e7").json()["completed"] == ["T1-x-0"]


def test_e7_post_validates_and_is_idempotent(client, e7_grove):
    import json

    ok = {"trial": "T1-x-0", "choice": "left", "confidence": 4, "rt_ms": 2100}
    assert client.post("/api/grove/e7/response", json=ok).status_code == 200
    # exact duplicate: acknowledged, not re-appended
    dup = client.post("/api/grove/e7/response", json=ok)
    assert dup.status_code == 200 and dup.json().get("duplicate") is True
    # conflicting duplicate: rejected
    conflict = client.post("/api/grove/e7/response",
                           json={**ok, "choice": "right"})
    assert conflict.status_code == 409
    log = (e7_grove / "e7-responses.jsonl").read_text().strip().splitlines()
    assert len(log) == 1 and json.loads(log[0])["choice"] == "left"
    # correctness never echoed anywhere
    assert "answer" not in dup.json() and "correct" not in dup.json()


def test_e7_post_rejects_invalid_trials_choices_and_bounds(client, e7_grove):
    base = {"trial": "T1-x-0", "choice": "left", "confidence": 4, "rt_ms": 100}
    assert client.post("/api/grove/e7/response",
                       json={**base, "trial": "NOPE"}).status_code == 404
    assert client.post("/api/grove/e7/response",
                       json={**base, "choice": "up"}).status_code == 400
    # 3-AFC choices come from the trial's options
    assert client.post("/api/grove/e7/response",
                       json={**base, "trial": "T3-x-0", "choice": "y"}).status_code == 200
    assert client.post("/api/grove/e7/response",
                       json={**base, "trial": "T3-x-0", "choice": "left"}).status_code in (400, 409)
    assert client.post("/api/grove/e7/response",
                       json={**base, "confidence": 9}).status_code == 422
    assert client.post("/api/grove/e7/response",
                       json={**base, "rt_ms": -5}).status_code == 422
