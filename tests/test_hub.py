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
    monkeypatch.setattr(hub_mod, "PACING_SECONDS", 0.0)
    monkeypatch.setattr(hub_mod, "REINDEX", lambda: 0)
    # reset job state between tests
    hub_mod._JOB.update(running=False, total=0, done=0, current=None,
                        failures=[], annotated=0)
    hub_mod.brain = brain
    return hub_mod


def _wait_done(hub_mod, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not hub_mod.job_status()["running"]:
            return hub_mod.job_status()
        time.sleep(0.02)
    raise TimeoutError("ingest job never finished")


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
    started = hub.start_ingest([1], tags=["build-idea"], thought="I want one.")
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
    hub.start_ingest([1], tags=[], thought="")
    status = _wait_done(hub)

    assert status["failures"][0]["url"] == url
    assert [i.url for i in hub.queue_items()] == [url]


def test_ingest_rejects_bad_indices_and_busy(hub):
    hub.queue_add(["https://youtu.be/abc"])
    with pytest.raises(ValueError):
        hub.start_ingest([5], tags=[], thought="")
    with pytest.raises(ValueError):
        hub.start_ingest([], tags=[], thought="")

    import threading

    gate = threading.Event()

    def slow(u, note=""):
        gate.wait(timeout=5)

    hub.INGEST = slow
    hub.start_ingest([1], tags=[], thought="")
    with pytest.raises(hub.HubBusy):
        hub.start_ingest([1], tags=[], thought="")
    gate.set()
    _wait_done(hub)


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
        "/api/ingest", json={"indices": [1], "tags": ["design"], "thought": "nice"}
    )
    assert r.status_code == 200
    assert r.json()["started"] == 1
    _wait_done(hub)
    status = client.get("/api/ingest/status").json()
    assert status["done"] == 1 and status["running"] is False


def test_api_ingest_bad_indices_400(client, hub):
    r = client.post("/api/ingest", json={"indices": [9], "tags": [], "thought": ""})
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


def test_inbox_page_served(client):
    r = client.get("/inbox")
    assert r.status_code == 200
    for marker in ('id="grid"', 'id="tags"', 'id="thought"', 'id="addurls"',
                   'id="side"', 'id="newtag"', "/api/queue", "/api/tags"):
        assert marker in r.text
    assert "selstr" not in r.text          # no index-string UI
    assert "monospace" not in r.text       # normalized typography
    assert "Pull sources" not in r.text    # auto-pull replaced the button
    assert "\u2014" not in r.text            # no em dashes in UI copy


def test_fresh_page_has_no_em_dashes(client):
    r = client.get("/")
    assert "\u2014" not in r.text


def test_fresh_notes_flags_my_take(hub):
    note = hub.brain / "sources" / "instagram" / "taken.md"
    note.write_text(
        NOTE_TEMPLATE.format(url="https://x/") + "\n## My take\n\nmine\n",
        encoding="utf-8",
    )
    assert hub.fresh_notes(n=5)[0]["has_take"] is True


def test_both_pages_have_source_filters(client):
    for path in ("/", "/inbox"):
        r = client.get(path)
        assert 'id="filters"' in r.text, path


def test_fresh_page_is_main(client):
    r = client.get("/")
    assert r.status_code == 200
    assert 'id="fresh"' in r.text
    assert "/api/fresh" in r.text


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
    hub.start_ingest([1], tags=[], thought="make this about touchdesigner")
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
