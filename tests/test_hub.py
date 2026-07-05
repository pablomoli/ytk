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

    def fake_ingest(u):
        note = hub.brain / "sources" / "instagram" / "someone-abc.md"
        note.write_text(NOTE_TEMPLATE.format(url=u), encoding="utf-8")

    hub.INGEST = fake_ingest
    started = hub.start_ingest([1], bucket="build-idea", thought="I want one.")
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

    def exploding(u):
        raise RuntimeError("fetch failed")

    hub.INGEST = exploding
    hub.start_ingest([1], bucket="", thought="")
    status = _wait_done(hub)

    assert status["failures"][0]["url"] == url
    assert [i.url for i in hub.queue_items()] == [url]


def test_ingest_rejects_bad_indices_and_busy(hub):
    hub.queue_add(["https://youtu.be/abc"])
    with pytest.raises(ValueError):
        hub.start_ingest([5], bucket="", thought="")
    with pytest.raises(ValueError):
        hub.start_ingest([], bucket="", thought="")

    import threading

    gate = threading.Event()

    def slow(u):
        gate.wait(timeout=5)

    hub.INGEST = slow
    hub.start_ingest([1], bucket="", thought="")
    with pytest.raises(hub.HubBusy):
        hub.start_ingest([1], bucket="", thought="")
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
    assert notes[-1]["stem"] == "older"


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

    def fake_ingest(u):
        note = hub.brain / "sources" / "instagram" / "someone-abc.md"
        note.write_text(NOTE_TEMPLATE.format(url=u), encoding="utf-8")

    hub.INGEST = fake_ingest
    r = client.post(
        "/api/ingest", json={"indices": [1], "bucket": "design", "thought": "nice"}
    )
    assert r.status_code == 200
    assert r.json()["started"] == 1
    _wait_done(hub)
    status = client.get("/api/ingest/status").json()
    assert status["done"] == 1 and status["running"] is False


def test_api_ingest_bad_indices_400(client, hub):
    r = client.post("/api/ingest", json={"indices": [9], "bucket": "", "thought": ""})
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
