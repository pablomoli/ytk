"""POST /api/memo runs the memo pipeline through a background job."""

import time
from unittest.mock import patch

from fastapi.testclient import TestClient

from ytk.memo import MemoResult
from ytk.ui import hub
from ytk.ui.server import app

client = TestClient(app)


def _pipeline_patches(tmp_path):
    return [
        patch("ytk.ui.hub.memo_ensure_wav", side_effect=lambda p: p),
        patch("ytk.ui.hub.memo_transcribe", return_value="from the phone"),
        patch("ytk.ui.hub.memo_write_note", return_value=tmp_path / "n.md"),
        patch(
            "ytk.ui.hub.memo_route",
            return_value=MemoResult(kind="thought", summary="phone thought"),
        ),
        patch("ytk.ui.hub.memo_execute", return_value=[]),
        patch("ytk.ui.hub.memo_finalize"),
        patch("ytk.ui.hub.memo_index"),
        patch("ytk.ui.hub.memo_notify", return_value=[]),
    ]


def _wait_done(timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = hub.memo_status()["state"]
        if state in ("done", "error"):
            return state
        time.sleep(0.05)
    raise AssertionError("memo job never finished")


def test_memo_upload_roundtrip(tmp_path):
    from contextlib import ExitStack

    with ExitStack() as stack:
        for p in _pipeline_patches(tmp_path):
            stack.enter_context(p)
        resp = client.post("/api/memo", files={"file": ("m.m4a", b"fake-audio", "audio/mp4")})
        assert resp.status_code == 200
        assert _wait_done() == "done"
    assert "phone thought" in hub.memo_status()["detail"]


def test_memo_text_only(tmp_path):
    from contextlib import ExitStack

    with ExitStack() as stack:
        mocks = [stack.enter_context(p) for p in _pipeline_patches(tmp_path)]
        resp = client.post("/api/memo", data={"text": "typed from phone"})
        assert resp.status_code == 200
        assert _wait_done() == "done"
        mocks[1].assert_not_called()  # memo_transcribe skipped


def test_memo_requires_file_or_text():
    resp = client.post("/api/memo")
    assert resp.status_code == 422


def test_memo_409_when_job_running(monkeypatch):
    monkeypatch.setitem(hub._memo_job, "state", "running")
    resp = client.post("/api/memo", data={"text": "second memo"})
    assert resp.status_code == 409
    hub._memo_job["state"] = "idle"
