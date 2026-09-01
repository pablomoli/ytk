from __future__ import annotations

import base64
from unittest.mock import MagicMock, patch


def test_hint_detect_no_cues_skips_sdk():
    from ytk.vision import hint_detect

    segments = [{"start": 0.0, "text": "Hello everyone welcome to this podcast episode today."}]
    with patch("ytk.vision.run_structured") as mock_run:
        result = hint_detect(segments)
    mock_run.assert_not_called()
    assert result == []


def test_hint_detect_with_cues_calls_sdk():
    from ytk.vision import hint_detect

    segments = [
        {"start": 5.0, "text": "As you can see on screen this is the main dashboard."},
        {"start": 10.0, "text": "Let me show you what happens when we click here."},
    ]
    with patch("ytk.vision.run_structured", return_value={"timestamps": [5.0, 10.0]}):
        result = hint_detect(segments)
    assert result == [5.0, 10.0]


def test_hint_detect_deduplicates_and_sorts():
    from ytk.vision import hint_detect

    segments = [{"start": 3.0, "text": "As you can see the code here is straightforward."}]
    with patch("ytk.vision.run_structured", return_value={"timestamps": [10.0, 3.0, 10.0]}):
        result = hint_detect(segments)
    assert result == [3.0, 10.0]


def test_hint_detect_sdk_error_returns_empty():
    from ytk.vision import hint_detect

    segments = [{"start": 0.0, "text": "look at this amazing result on screen"}]
    with patch("ytk.vision.run_structured", side_effect=RuntimeError("boom")):
        result = hint_detect(segments)
    assert result == []


def test_image_blocks_bytes():
    from ytk.vision import image_blocks

    raw = b"\xff\xd8\xff\xe0"  # JPEG magic bytes
    blocks = image_blocks(frame_bytes=[raw])
    assert len(blocks) == 1
    assert blocks[0]["type"] == "image"
    assert blocks[0]["source"]["type"] == "base64"
    assert blocks[0]["source"]["media_type"] == "image/jpeg"
    assert blocks[0]["source"]["data"] == base64.standard_b64encode(raw).decode()


def test_image_blocks_url_reachable():
    from ytk.vision import image_blocks

    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.status = 200
    with patch("ytk.vision.urllib.request.urlopen", return_value=mock_resp):
        blocks = image_blocks(urls=["https://cdn.example.com/img.jpg"])
    assert len(blocks) == 1
    assert blocks[0]["source"]["type"] == "url"
    assert blocks[0]["source"]["url"] == "https://cdn.example.com/img.jpg"


def test_image_blocks_url_unreachable_falls_back_to_base64():
    from ytk.vision import image_blocks

    raw = b"\xff\xd8\xff"
    call_count = 0

    def fake_urlopen(req_or_url, timeout=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise OSError("connection refused")
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.headers.get.return_value = "image/jpeg"
        mock_resp.read.return_value = raw
        return mock_resp

    with patch("ytk.vision.urllib.request.urlopen", side_effect=fake_urlopen):
        blocks = image_blocks(urls=["https://cdn.example.com/private.jpg"])
    assert len(blocks) == 1
    assert blocks[0]["source"]["type"] == "base64"


def test_image_blocks_empty_returns_empty():
    from ytk.vision import image_blocks

    assert image_blocks() == []
    assert image_blocks(urls=[], frame_bytes=[]) == []


class TestToolResolver:
    """#202: the hub runs under launchd with PATH=/usr/bin:/bin:/usr/sbin:/sbin,
    so bare 'ffmpeg'/'ffprobe' fail in exactly the process the loop reads in."""

    def test_prefers_a_path_hit(self, monkeypatch):
        from ytk import vision

        monkeypatch.setattr("shutil.which", lambda name: f"/found/{name}")
        assert vision._tool("ffmpeg") == "/found/ffmpeg"

    def test_falls_back_to_known_install_dirs(self, monkeypatch, tmp_path):
        from ytk import vision

        monkeypatch.setattr("shutil.which", lambda name: None)
        monkeypatch.setattr(vision, "_TOOL_DIRS", (tmp_path,))
        (tmp_path / "ffprobe").write_text("")
        assert vision._tool("ffprobe") == str(tmp_path / "ffprobe")

    def test_bare_name_is_the_last_resort(self, monkeypatch, tmp_path):
        from ytk import vision

        monkeypatch.setattr("shutil.which", lambda name: None)
        monkeypatch.setattr(vision, "_TOOL_DIRS", (tmp_path / "missing",))
        assert vision._tool("ffmpeg") == "ffmpeg"

    def test_probe_and_extract_invoke_the_resolved_binary(self, monkeypatch, tmp_path):
        import subprocess as sp

        from ytk import vision

        seen = []

        def fake_run(cmd, **kw):
            seen.append(cmd[0])
            raise sp.CalledProcessError(1, cmd)

        monkeypatch.setattr(vision, "_tool", lambda name: f"/resolved/{name}")
        monkeypatch.setattr("subprocess.run", fake_run)
        assert vision.probe_duration(tmp_path / "v.mp4") is None
        assert seen == ["/resolved/ffprobe"]
