"""The fetch layer: a URL's content in seconds, no model calls, no ledger.
Network is faked at the two seams (yt-dlp and _get); ffmpeg runs for real
where a test says so."""

from __future__ import annotations

import io
import json
import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from click.testing import CliRunner
from PIL import Image

from ytk import fetch as F
from ytk.evidence import EvidenceBundle
from ytk.transcript import TranscriptionResult

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")

YT = "https://www.youtube.com/watch?v=abcdefghijk"


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("YTK_EVIDENCE", str(tmp_path / "evidence"))
    monkeypatch.setenv("YTK_LEDGER", str(tmp_path / "ledger.db"))
    monkeypatch.setenv("YTK_CAPTURE_LOG", "off")
    return tmp_path


def _grid_jpeg(rows: int = 3, cols: int = 3, w: int = 32, h: int = 18) -> bytes:
    im = Image.new("RGB", (cols * w, rows * h))
    for k in range(rows * cols):
        r, c = divmod(k, cols)
        im.paste((k * 25 % 255, 40, 200 - k * 20 % 200), (c * w, r * h, (c + 1) * w, (r + 1) * h))
    buf = io.BytesIO()
    im.save(buf, format="JPEG")
    return buf.getvalue()


SRV1 = (
    b'<?xml version="1.0" encoding="utf-8" ?><transcript>'
    b'<text start="0.5" dur="2.1">it&amp;#39;s a galaxy</text>'
    b'<text start="40" dur="3">second\nline</text>'
    b'<text start="41" dur="1">  </text></transcript>'
)


def _info(**over: Any) -> dict[str, Any]:
    info: dict[str, Any] = {
        "id": "abcdefghijk",
        "title": "Simulating Galaxies",
        "uploader": "DevPotato",
        "upload_date": "20260825",
        "duration": 100,
        "language": "en",
        "description": "the description",
        "chapters": [{"start_time": 0, "title": "Intro"}],
        "thumbnail": "https://i.ytimg.com/x.jpg",
        "subtitles": {},
        "automatic_captions": {
            "en-orig": [{"ext": "json3", "url": "j"}, {"ext": "srv1", "url": "cap://en-orig"}],
            "fr": [{"ext": "srv1", "url": "cap://fr"}],
        },
        "formats": [
            {
                "format_id": "sb0",
                "width": 32,
                "height": 18,
                "rows": 3,
                "columns": 3,
                "fragments": [{"url": f"sb://{i}", "duration": 45.0} for i in range(3)],
            },
            {
                "format_id": "sb1",
                "width": 16,
                "height": 9,
                "rows": 3,
                "columns": 3,
                "fragments": [{"url": "sb1://0", "duration": 100.0}],
            },
        ],
    }
    info.update(over)
    return info


class _FakeYDL:
    def __init__(self, info: dict[str, Any], calls: list[dict[str, Any]], opts: dict[str, Any]):
        self.info, self.calls, self.opts = info, calls, opts

    def __enter__(self) -> _FakeYDL:
        return self

    def __exit__(self, *a: object) -> None:
        return None

    def extract_info(self, url: str, download: bool = False) -> dict[str, Any]:
        self.calls.append({"url": url, "download": download, **self.opts})
        return self.info


def _fake_get(caption: bytes | Exception = SRV1):
    def get(url: str) -> bytes:
        if url.startswith("cap://"):
            if isinstance(caption, Exception):
                raise caption
            return caption
        if url.startswith("sb"):
            return _grid_jpeg()
        raise AssertionError(f"unexpected GET {url}")

    return get


@contextmanager
def _youtube_net(info: dict[str, Any], caption: bytes | Exception = SRV1):
    calls: list[dict[str, Any]] = []
    with (
        patch.object(F, "_ydl", lambda opts: _FakeYDL(info, calls, opts)),
        patch.object(F, "_get", _fake_get(caption)),
    ):
        yield calls


# ------------------------------------------------------------ stdout is sacred


def test_yt_dlp_never_writes_progress_or_logs_to_stdout():
    # The MCP server speaks JSON-RPC on stdout; a progress bar there kills it.
    ydl = F._ydl({"format": "x"})
    assert ydl.params["quiet"] and ydl.params["noprogress"]
    assert isinstance(ydl.params["logger"], F._SilentLogger)
    assert ydl.params["format"] == "x"


# --------------------------------------------------------------- the cache key


def test_every_youtube_url_shape_shares_one_cache_entry():
    keys = {
        F.cache_key(u)
        for u in (
            YT,
            "https://youtu.be/abcdefghijk?si=x",
            "https://www.youtube.com/shorts/abcdefghijk",
            "https://www.youtube.com/watch?v=abcdefghijk&t=40s",
        )
    }
    assert len(keys) == 1


def test_share_link_tracking_params_do_not_split_a_reel():
    a = F.cache_key("https://www.instagram.com/reel/Dc6J8GVpPca/?igsh=abc")
    assert a == F.cache_key("https://www.instagram.com/reel/Dc6J8GVpPca/")


def test_web_query_strings_are_kept():
    assert F.cache_key("https://x.org/a?page=1") != F.cache_key("https://x.org/a?page=2")


# ------------------------------------------------------------- caption choice


def _tracks(manual: dict[str, str], auto: dict[str, str], language: str = "en") -> dict[str, Any]:
    def fmts(url: str) -> list[dict[str, str]]:
        return [{"ext": "vtt", "url": "v"}, {"ext": "srv1", "url": url}]

    return {
        "language": language,
        "subtitles": {k: fmts(v) for k, v in manual.items()},
        "automatic_captions": {k: fmts(v) for k, v in auto.items()},
    }


def test_manual_in_the_video_language_wins():
    info = _tracks({"en-US": "m"}, {"en-orig": "a"})
    assert F.caption_track(info) == ("en-US", False, "m")


def test_own_language_recognition_beats_english_translation_of_nothing():
    info = _tracks({}, {"pt-BR-orig": "a", "en": "translated"}, language="pt-BR")
    assert F.caption_track(info) == ("pt-BR", True, "a")


def test_dubbed_audio_recognition_and_translations_are_never_picked():
    info = _tracks({"es": "translation"}, {"ar-orig": "dub", "fr": "mt"}, language="en")
    assert F.caption_track(info) is None


def test_english_manual_track_of_a_foreign_video_is_kept():
    info = _tracks({"en": "m"}, {"ar-orig": "dub"}, language="pt")
    assert F.caption_track(info) == ("en", False, "m")


def test_older_yt_dlp_without_orig_keys_uses_the_plain_language_key():
    info = _tracks({}, {"en": "a", "fr": "mt"})
    assert F.caption_track(info) == ("en", True, "a")


def test_live_chat_is_not_a_caption_track():
    info = _tracks({"live_chat": "chat"}, {})
    assert F.caption_track(info) is None


def test_srv1_text_is_unescaped_twice_and_blank_lines_dropped():
    segs = F.parse_srv1(SRV1)
    assert segs == [
        {"start": 0.5, "duration": 2.1, "text": "it's a galaxy"},
        {"start": 40.0, "duration": 3.0, "text": "second line"},
    ]


# ----------------------------------------------------------------- youtube


def test_youtube_fetch_reads_captions_and_builds_the_storyboard_sheet():
    with _youtube_net(_info()) as calls:
        f = F.fetch(YT)
    b = f.bundle
    assert (b.source, b.title, b.uploader, b.duration) == (
        "youtube",
        "Simulating Galaxies",
        "DevPotato",
        100,
    )
    assert (b.transcript_origin, b.transcript_language, b.transcript_status) == (
        "api-auto",
        "en",
        "ok",
    )
    assert [s["text"] for s in b.transcript] == ["it's a galaxy", "second line"]
    assert b.sheet and Path(b.sheet).is_file()
    grid = f.meta["storyboard"]
    # 45 s per 3x3 fragment is a tile every 5 s; 100 s of video is 20 tiles.
    assert (grid["interval"], grid["tiles"]) == (5.0, 20)
    with Image.open(b.sheet) as sheet:
        assert sheet.width == 6 * 320
    assert calls == [calls[0]] and calls[0]["download"] is False
    assert {"metadata", "captions", "sheet", "total"} <= set(f.meta["timings"])
    assert f.pending is None


def test_the_second_fetch_is_a_disk_read():
    with _youtube_net(_info()):
        F.fetch(YT)
    with patch.object(F, "_ydl", side_effect=AssertionError("network on a cache hit")):
        f = F.fetch("https://youtu.be/abcdefghijk")
    assert f.cached and f.bundle.title == "Simulating Galaxies"


def test_blocked_captions_start_local_transcription_and_say_so():
    spawned: list[list[str]] = []

    def fake_spawn(args, log_path):
        spawned.append(args)
        return 4242

    with (
        _youtube_net(_info(), caption=RuntimeError("HTTP Error 429: Too Many Requests")),
        patch.object(F, "_spawn", fake_spawn),
        patch.object(F, "_alive", return_value=True),
    ):
        f = F.fetch(YT)
        assert f.pending and "about 10 s" in f.pending
        assert "captions could not be read: HTTP Error 429" in f.bundle.gaps[0]
        assert spawned[0][-3:] == ["-m", "ytk.fetch", str(f.dir)]
        assert "Transcript: pending" in F.render(f)
        assert F.adoptable_bundle(YT) is None


def test_a_dead_background_run_is_reported_not_waited_on():
    with (
        _youtube_net(_info(), caption=RuntimeError("429")),
        patch.object(F, "_spawn", return_value=4242),
    ):
        F.fetch(YT)
    with patch.object(F, "_alive", return_value=False):
        f = F.fetch(YT)
    assert f.pending is None
    assert f.meta["whisper"]["status"] == "died"
    assert any("stopped without a result" in g for g in f.bundle.gaps)


def test_the_background_half_writes_the_transcript_back():
    with (
        _youtube_net(_info(), caption=RuntimeError("HTTP Error 429")),
        patch.object(F, "_spawn", return_value=4242),
    ):
        f = F.fetch(YT)
    heard = TranscriptionResult(
        segments=[{"start": 0.0, "duration": 2.0, "text": "heard"}], status="ok"
    )
    with (
        patch("ytk.transcript._download_audio", return_value=Path("/tmp/a.m4a")),
        patch("ytk.transcript.transcribe_file", return_value=heard),
    ):
        F.transcribe_into(f.dir)
    with patch.object(F, "_alive", return_value=False):
        f = F.fetch(YT)
    assert f.pending is None
    assert (f.bundle.transcript_origin, f.bundle.transcript[0]["text"]) == ("whisper", "heard")
    assert not any(g.startswith("captions could not be read") for g in f.bundle.gaps)
    assert "heard" in f.content_path.read_text()
    assert F.adoptable_bundle(YT) is not None


def test_span_sheet_takes_every_storyboard_tile_in_the_stretch():
    with _youtube_net(_info()):
        f = F.fetch(YT)
    path = F.span_sheet(f, 10, 30)
    with Image.open(path) as im:
        # tiles at 10, 15, 20, 25, 30 s: one row of five, 18 px label strip
        assert im.size == (6 * 320, 18 + 180)


def test_no_storyboard_is_a_gap_not_a_failure():
    with _youtube_net(_info(formats=[])):
        f = F.fetch(YT)
    assert f.bundle.sheet is None
    assert "no storyboard offered" in f.bundle.gaps


# -------------------------------------------------------------- rendering


def test_captions_render_as_thirty_second_paragraphs():
    segs = [{"start": float(t), "text": f"w{t}"} for t in (0, 10, 29, 30, 31, 75)]
    assert F.paragraphs(segs) == ["[0:00] w0 w10 w29", "[0:30] w30 w31", "[1:15] w75"]


def test_render_names_the_sheet_and_how_to_look_closer():
    with _youtube_net(_info()):
        f = F.fetch(YT)
    text = F.render(f)
    assert text.startswith("# Simulating Galaxies\nyoutube | DevPotato | 2026-08-25 | 1:40 | ")
    assert "20 storyboard frames at 32x18" in text
    assert "fetch_frames" in text
    assert "## Chapters\n- [0:00] Intro" in text
    assert "[0:00] it's a galaxy\n\n[0:40] second line" in text


def test_a_capped_render_points_at_the_full_text():
    with _youtube_net(_info(description="x" * 5000)):
        f = F.fetch(YT)
    text = F.render(f, cap_chars=2000)
    assert len(text) < 2400
    assert str(f.content_path) in text
    assert len(f.content_path.read_text()) > 5000


# -------------------------------------------------------------------- web


def test_arxiv_abstract_pages_are_rewritten_to_the_paper():
    assert (
        F.rewrite_arxiv("https://arxiv.org/abs/2405.07987") == "https://arxiv.org/html/2405.07987v1"
    )
    assert (
        F.rewrite_arxiv("https://arxiv.org/abs/2405.07987v3")
        == "https://arxiv.org/html/2405.07987v3"
    )
    assert (
        F.rewrite_arxiv("https://arxiv.org/abs/2001.08361")
        == "https://ar5iv.labs.arxiv.org/html/2001.08361"
    )
    assert F.rewrite_arxiv("https://example.org/abs/1") == "https://example.org/abs/1"


def test_web_keeps_code_and_resolves_image_links():
    class _Meta:
        title, author, date = "Pingora", "Cloudflare", "2022-09-14"

    seen: dict[str, Any] = {}

    def extract(html: str, **kw: Any) -> str:
        seen.update(kw)
        return "Intro\n\n```rust\nfn main() {}\n```\n\n![arch](/_image?href=a.png)"

    with (
        patch("trafilatura.fetch_url", return_value="<html/>"),
        patch("trafilatura.extract_metadata", return_value=_Meta()),
        patch("trafilatura.extract", side_effect=extract),
    ):
        f = F.fetch("https://blog.cloudflare.com/pingora/")
    b = f.bundle
    assert seen["include_formatting"] and seen["include_images"]
    assert "```rust" in (b.text or "")
    assert "![arch](https://blog.cloudflare.com/_image?href=a.png)" in (b.text or "")
    assert (b.title, b.uploader, b.upload_date) == ("Pingora", "Cloudflare", "20220914")


# ------------------------------------------------------- reels, real ffmpeg


@contextmanager
def _reel_net(source_url: str, duration: float = 6.0):
    """yt-dlp 'downloads' a generated test video; Whisper is faked."""
    calls: list[dict[str, Any]] = []

    class _YDL(_FakeYDL):
        def extract_info(self, url: str, download: bool = False) -> dict[str, Any]:
            out = Path(self.opts["outtmpl"].replace("%(ext)s", "mp4"))
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    f"testsrc=duration={duration}:size=320x240:rate=10",
                    str(out),
                ],
                check=True,
            )
            return super().extract_info(url, download)

    info = {
        "id": "Dc6",
        "title": "Video by someone",
        "uploader": "someone",
        "duration": duration,
        "description": "the caption #tag",
    }
    said = TranscriptionResult(
        segments=[{"start": 0.0, "duration": 2.0, "text": "said"}], status="ok"
    )
    with (
        patch.object(F, "_ydl", lambda opts: _YDL(info, calls, opts)),
        patch.object(F, "zen_profile", return_value=Path("/zen/profile")),
        patch("ytk.transcript.transcribe_file", return_value=said),
    ):
        yield calls


@needs_ffmpeg
def test_reel_keeps_its_video_and_reads_caption_frames_and_speech():
    url = "https://www.instagram.com/reel/Dc6/"
    with _reel_net(url) as calls:
        f = F.fetch(url)
    b = f.bundle
    assert calls[0]["cookiesfrombrowser"] == ("firefox", "/zen/profile", None, None)
    assert (b.source, b.caption, b.description) == ("instagram", "the caption #tag", None)
    assert (b.transcript_origin, b.transcript[0]["text"]) == ("whisper", "said")
    assert b.sheet and Path(b.sheet).is_file()
    assert len(b.dense_frames) == 3 and len(b.frames) >= 1
    assert Path(f.meta["video"]).is_file()
    shots = F.closeups(f, [1.0, 4.5])
    with Image.open(shots[0]) as im:
        assert im.size == (320, 240)  # the kept video's own resolution
    with Image.open(F.span_sheet(f, 0, 6)) as im:
        assert im.width == 6 * 320


@needs_ffmpeg
def test_tiktok_uses_no_cookies_and_files_its_caption_as_description():
    url = "https://www.tiktok.com/@u/video/123"
    with _reel_net(url) as calls:
        f = F.fetch(url)
    assert "cookiesfrombrowser" not in calls[0]
    assert (f.bundle.description, f.bundle.caption) == ("the caption #tag", None)


@needs_ffmpeg
def test_a_long_video_post_transcribes_in_the_background():
    url = "https://www.tiktok.com/@u/video/456"
    with (
        _reel_net(url, duration=1.0),
        patch.object(F, "SYNC_WHISPER_MAX_S", 0.5),
        patch.object(F, "_spawn", return_value=4242),
        patch.object(F, "_alive", return_value=True),
    ):
        f = F.fetch(url)
        assert f.pending is not None
        assert f.bundle.transcript == []


# ------------------------------------------------------ the curator adopts it


def test_read_item_adopts_the_fetched_bundle_and_says_so():
    from ytk import capture, evidence, ledger

    with _youtube_net(_info()):
        F.fetch(YT)
    conn = ledger.connect()
    item = capture.capture(
        conn, source="youtube", url=YT, surface="cli", text="take", take_kind="intent"
    )
    with patch.dict(
        evidence.GATHERERS, {"youtube": lambda *a: (_ for _ in ()).throw(AssertionError)}
    ):
        res = evidence.read_item(conn, item.item_id)
    assert res.error is None
    saved = json.loads(Path(res.bundle_path).read_text())
    assert saved["sheet"] and saved["transcript"][0]["text"] == "it's a galaxy"
    row = conn.execute("SELECT inputs FROM activity WHERE action = 'read'").fetchone()
    assert json.loads(row["inputs"]) == {"from": "fetch-cache"}


def test_read_item_gathers_as_before_without_a_fetch():
    from ytk import capture, evidence, ledger

    conn = ledger.connect()
    item = capture.capture(
        conn, source="youtube", url=YT, surface="cli", text="take", take_kind="intent"
    )
    own = EvidenceBundle(
        source="youtube",
        url=YT,
        title="T",
        transcript=[{"start": 0, "duration": 1, "text": "hi"}],
        transcript_origin="api-manual",
        transcript_language="en",
        transcript_status="ok",
    )
    with patch.dict(evidence.GATHERERS, {"youtube": lambda *a: own}):
        res = evidence.read_item(conn, item.item_id)
    assert json.loads(Path(res.bundle_path).read_text())["title"] == "T"
    row = conn.execute("SELECT inputs FROM activity WHERE action = 'read'").fetchone()
    assert row["inputs"] is None


# ------------------------------------------------------------ the surfaces


@pytest.fixture()
def no_nudge(monkeypatch):
    monkeypatch.setattr("ytk.wake.nudge_loop", lambda: True)


def test_add_shows_the_fetch_then_captures(no_nudge):
    from ytk import ledger
    from ytk.cli import cli

    with _youtube_net(_info()):
        result = CliRunner().invoke(cli, ["add", YT])
    assert result.exit_code == 0, result.output
    assert "# Simulating Galaxies" in result.output
    assert "full text:" in result.output
    assert "Captured youtube item" in result.output
    assert ledger.connect().execute("SELECT count(*) FROM items").fetchone()[0] == 1


def test_add_no_keep_leaves_the_ledger_alone(no_nudge):
    from ytk import ledger
    from ytk.cli import cli

    with _youtube_net(_info()):
        result = CliRunner().invoke(cli, ["add", YT, "--no-keep"])
    assert result.exit_code == 0, result.output
    assert ledger.connect().execute("SELECT count(*) FROM items").fetchone()[0] == 0


def test_add_print_puts_only_content_on_stdout(no_nudge):
    from ytk.cli import cli

    with _youtube_net(_info()):
        result = CliRunner().invoke(cli, ["add", YT, "--print"])
    assert result.exit_code == 0, result.stderr
    assert result.stdout.startswith("# Simulating Galaxies")
    assert "[0:40] second line" in result.stdout
    assert "Captured" not in result.stdout and "Captured" in result.stderr


def test_a_failed_fetch_never_blocks_the_capture(no_nudge):
    from ytk import ledger
    from ytk.cli import cli

    with patch.object(F, "fetch", side_effect=RuntimeError("offline")):
        result = CliRunner().invoke(cli, ["add", YT])
    assert result.exit_code == 0
    assert "Fetch failed" in result.stderr
    assert ledger.connect().execute("SELECT count(*) FROM items").fetchone()[0] == 1


def test_mcp_fetch_url_returns_text_and_the_sheet():
    import asyncio

    from ytk import mcp_server

    with _youtube_net(_info()):
        result = asyncio.run(mcp_server.app.call_tool("fetch_url", {"url": YT}))
    content = result[0] if isinstance(result, tuple) else result
    assert [c.type for c in content] == ["text", "image"]
    assert content[0].text.startswith("# Simulating Galaxies")


def test_mcp_fetch_frames_returns_a_span_sheet():
    import asyncio

    from ytk import mcp_server

    with _youtube_net(_info()):
        F.fetch(YT)
        result = asyncio.run(
            mcp_server.app.call_tool("fetch_frames", {"url": YT, "start": 0, "end": 20})
        )
    content = result[0] if isinstance(result, tuple) else result
    assert [c.type for c in content] == ["text", "image"]
