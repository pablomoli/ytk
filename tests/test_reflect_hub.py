"""POST /api/reflect runs the reflection second loop through a background job."""

import threading
import time
from unittest.mock import patch

from fastapi.testclient import TestClient

from ytk.ui import hub
from ytk.ui.server import app

client = TestClient(app)

PAYLOAD = {
    "path": "second-brain/sources/youtube/a-video.md",
    "question": "why did you save this?",
    "answer": "it changed how I debug tokenizers",
}


def _wait(timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = hub.reflect_status()["state"]
        if state in ("done", "error"):
            return state
        time.sleep(0.05)
    raise AssertionError("reflect job never finished")


def test_reflect_roundtrip_and_cache_drop():
    hub._LIB_CACHE = (time.time(), 1, [{"stale": True}])
    with patch("ytk.reflect.reflect_note") as run:
        resp = client.post("/api/reflect", json=PAYLOAD)
        assert resp.status_code == 200
        assert _wait() == "done"
    run.assert_called_once_with(PAYLOAD["path"], PAYLOAD["question"], PAYLOAD["answer"])
    assert hub._LIB_CACHE is None
    assert hub.reflect_status()["path"] == PAYLOAD["path"]


def test_reflect_single_flight():
    gate = threading.Event()
    with patch("ytk.reflect.reflect_note", side_effect=lambda *a: gate.wait(5)):
        first = client.post("/api/reflect", json=PAYLOAD)
        assert first.status_code == 200
        second = client.post("/api/reflect", json=PAYLOAD)
        assert second.status_code == 409
        gate.set()
        assert _wait() == "done"


def test_reflect_error_surfaces_detail():
    with patch("ytk.reflect.reflect_note", side_effect=FileNotFoundError("Note not found: x")):
        resp = client.post("/api/reflect", json=PAYLOAD)
        assert resp.status_code == 200
        assert _wait() == "error"
    assert "Note not found" in hub.reflect_status()["detail"]


def test_reflect_empty_answer_rejected():
    resp = client.post("/api/reflect", json={**PAYLOAD, "answer": "  "})
    assert resp.status_code == 422
