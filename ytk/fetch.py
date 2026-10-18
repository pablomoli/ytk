"""The fetch layer: a URL's content in seconds, before and apart from the
curator. No model calls, no ledger rows, no asks.

One directory per URL under evidence/fetch/<key>/ holds bundle.json (a plain
EvidenceBundle, so read_item can adopt it), meta.json (timings, storyboard
grid, background work), content.md (the chat rendering) and the sheet. A
second fetch of the same URL is a disk read.
"""

from __future__ import annotations

import hashlib
import html
import io
import json
import math
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable, Generator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from .evidence import EvidenceBundle, evidence_dir, load_bundle
from .reels import canonical_url, classify_url

if TYPE_CHECKING:  # vision imports the Agent SDK; load it only where frames are made
    from .vision import TimedFrame

# 48 storyboard tiles at their native 320x180, six across: the whole video in
# one image. Denser looks come from fetch_frames, not a bigger overview.
SHEET_TILES = 48
SPAN_TILES = 60
MAX_CLOSEUPS = 6
CLOSEUP_HEIGHT = 1080
# Media longer than this transcribes in a detached process: in-process it
# would hold the caller for most of a minute.
SYNC_WHISPER_MAX_S = 180.0
# Only feeds the "about N s" the reader is shown.
WHISPER_SECONDS_PER_SECOND = 0.1
PARAGRAPH_S = 30.0
HTTP_TIMEOUT = 20
_UA = {"User-Agent": "Mozilla/5.0"}


class FetchError(RuntimeError):
    pass


def fetch_dir() -> Path:
    return evidence_dir() / "fetch"


def cache_key(url: str) -> str:
    return hashlib.sha1(canonical_url(url).encode(), usedforsecurity=False).hexdigest()[:12]


@dataclass
class Fetched:
    url: str
    dir: Path
    bundle: EvidenceBundle
    meta: dict[str, Any]
    cached: bool

    @property
    def pending(self) -> str | None:
        w = cast(dict[str, Any], self.meta.get("whisper") or {})
        if w and not w.get("done_at"):
            return (
                f"transcribing locally since {w.get('started_at')}, "
                f"about {w.get('estimate_s')} s in all"
            )
        return None

    @property
    def content_path(self) -> Path:
        return self.dir / "content.md"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@contextmanager
def _timed(timings: dict[str, float], name: str) -> Generator[None]:
    t0 = time.monotonic()
    try:
        yield
    finally:
        timings[name] = round(time.monotonic() - t0, 2)


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return cast(bytes, resp.read())


def _ydl(opts: dict[str, Any]) -> Any:
    import yt_dlp

    # The MCP server speaks JSON-RPC on stdout: one progress bar there breaks
    # the session, so yt-dlp logs nowhere and draws no progress.
    base: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "logger": _SilentLogger(),
    }
    return yt_dlp.YoutubeDL(cast(Any, base | opts))


class _SilentLogger:
    def debug(self, msg: str) -> None:
        pass

    def info(self, msg: str) -> None:
        pass

    def warning(self, msg: str) -> None:
        pass

    def error(self, msg: str) -> None:
        pass


# ---------------------------------------------------------------------------
# YouTube: one metadata call, then captions and storyboard side by side
# ---------------------------------------------------------------------------


def caption_track(info: dict[str, Any]) -> tuple[str, bool, str] | None:
    """(language, generated, srv1 url) of the best caption track.

    The video's own language first, manual before auto, then a manual
    English track. Auto tracks named `<lang>-orig` are speech recognition of
    that audio; other auto keys are machine translations. Translations and
    recognition of dubbed audio are never picked: Whisper on the real audio
    says what was said.
    """
    lang = str(info.get("language") or "en").lower()
    base = lang.split("-")[0]
    ranked: list[tuple[int, str, bool, str]] = []

    def srv1(formats: Any) -> str | None:
        for f in cast(list[dict[str, Any]], formats or []):
            if f.get("ext") == "srv1" and f.get("url"):
                return str(f["url"])
        return None

    manual = cast(dict[str, Any], info.get("subtitles") or {})
    for key, formats in manual.items():
        k = key.lower()
        if k == "live_chat" or (url := srv1(formats)) is None:
            continue
        if k.split("-")[0] == base:
            ranked.append((0, key, False, url))
        elif k.startswith("en"):
            ranked.append((1, key, False, url))
    auto = cast(dict[str, Any], info.get("automatic_captions") or {})
    has_orig = any(k.endswith("-orig") for k in auto)
    for key, formats in auto.items():
        k = key.lower()
        own = k.endswith("-orig") and k.split("-")[0] == base
        if (own or (not has_orig and k == base)) and (url := srv1(formats)) is not None:
            ranked.append((2, key.removesuffix("-orig"), True, url))
    if not ranked:
        return None
    _, key, generated, url = min(ranked, key=lambda r: r[0])
    return key, generated, url


def parse_srv1(xml_bytes: bytes) -> list[dict[str, Any]]:
    """YouTube's timedtext srv1: <text start dur>escaped text</text>. Text is
    escaped twice (XML, then HTML), the same shape youtube-transcript-api
    unwraps."""
    segments: list[dict[str, Any]] = []
    for el in ET.fromstring(xml_bytes).iter("text"):
        text = html.unescape("".join(el.itertext())).replace("\n", " ").strip()
        if text:
            segments.append(
                {
                    "start": float(el.get("start") or 0),
                    "duration": float(el.get("dur") or 0),
                    "text": text,
                }
            )
    return segments


def _captions(info: dict[str, Any]) -> tuple[list[dict[str, Any]], str, str | None, str | None]:
    track = caption_track(info)
    if track is None:
        return [], "none", None, "no caption track offered"
    lang, generated, url = track
    try:
        segments = parse_srv1(_get(url))
    except Exception as exc:
        return [], "none", None, f"captions could not be read: {exc}"
    return segments, ("api-auto" if generated else "api-manual"), lang, None


def _storyboard_format(info: dict[str, Any]) -> dict[str, Any] | None:
    formats = cast(list[dict[str, Any]], info.get("formats") or [])
    boards = [
        f for f in formats if str(f.get("format_id", "")).startswith("sb") and f.get("fragments")
    ]
    if not boards:
        return None
    return max(boards, key=lambda f: int(f.get("width") or 0))


def _tile(board_dir: Path, i: int, grid: dict[str, Any]) -> bytes:
    from PIL import Image

    per = grid["rows"] * grid["cols"]
    frag, k = divmod(i, per)
    r, c = divmod(k, grid["cols"])
    with Image.open(board_dir / f"{frag:03d}.jpg") as im:
        w, h = im.width // grid["cols"], im.height // grid["rows"]
        buf = io.BytesIO()
        im.convert("RGB").crop((c * w, r * h, (c + 1) * w, (r + 1) * h)).save(
            buf, format="JPEG", quality=90
        )
    return buf.getvalue()


def _even(n: int, k: int) -> list[int]:
    if n <= k:
        return list(range(n))
    return sorted({round(i * (n - 1) / (k - 1)) for i in range(k)})


def _tiles_sheet(
    board_dir: Path, grid: dict[str, Any], indices: list[int], label: str
) -> bytes | None:
    from .vision import TimedFrame, contact_sheet

    frames = [TimedFrame(t=i * grid["interval"], data=_tile(board_dir, i, grid)) for i in indices]
    return contact_sheet(frames, label=label)


def _storyboard(
    info: dict[str, Any], d: Path
) -> tuple[str | None, dict[str, Any] | None, str | None]:
    sb = _storyboard_format(info)
    if sb is None:
        return None, None, "no storyboard offered"
    frags = cast(list[dict[str, Any]], sb["fragments"])
    rows, cols = int(sb.get("rows") or 1), int(sb.get("columns") or 1)
    board_dir = d / "storyboard"
    board_dir.mkdir(parents=True, exist_ok=True)

    def download(item: tuple[int, dict[str, Any]]) -> None:
        i, frag = item
        (board_dir / f"{i:03d}.jpg").write_bytes(_get(str(frag["url"])))

    try:
        with ThreadPoolExecutor(16) as pool:
            list(pool.map(download, enumerate(frags)))
    except Exception as exc:
        return None, None, f"storyboard could not be read: {exc}"
    interval = float(frags[0].get("duration") or 0) / (rows * cols)
    duration = float(info.get("duration") or sum(float(f.get("duration") or 0) for f in frags))
    if interval <= 0:
        return None, None, "storyboard has no timing"
    tiles = min(len(frags) * rows * cols, math.ceil(duration / interval))
    grid = {
        "rows": rows,
        "cols": cols,
        "interval": interval,
        "tiles": tiles,
        "tile_w": sb.get("width"),
        "tile_h": sb.get("height"),
    }
    data = _tiles_sheet(board_dir, grid, _even(tiles, SHEET_TILES), str(info.get("id") or ""))
    if data is None:
        return None, grid, "storyboard had no tiles"
    sheet = d / "sheet.jpg"
    sheet.write_bytes(data)
    return str(sheet), grid, None


def _youtube(url: str, d: Path, timings: dict[str, float]) -> tuple[EvidenceBundle, dict[str, Any]]:
    with _timed(timings, "metadata"), _ydl({"skip_download": True}) as ydl:
        info = cast(dict[str, Any], ydl.extract_info(url, download=False))

    def captions() -> tuple[list[dict[str, Any]], str, str | None, str | None]:
        with _timed(timings, "captions"):
            return _captions(info)

    def board() -> tuple[str | None, dict[str, Any] | None, str | None]:
        with _timed(timings, "sheet"):
            return _storyboard(info, d)

    with ThreadPoolExecutor(2) as pool:
        cap_future, sb_future = pool.submit(captions), pool.submit(board)
        segments, origin, language, cap_gap = cap_future.result()
        sheet, grid, sb_gap = sb_future.result()
    gaps = [g for g in (cap_gap, sb_gap) if g]
    bundle = EvidenceBundle(
        source="youtube",
        url=url,
        title=info.get("title"),
        transcript=segments,
        transcript_origin=origin,
        transcript_language=language,
        transcript_status="ok" if segments else "none",
        description=info.get("description"),
        gaps=gaps,
        media_id=info.get("id"),
        uploader=info.get("uploader") or info.get("channel"),
        upload_date=info.get("upload_date"),
        duration=info.get("duration"),
        thumbnail=info.get("thumbnail"),
        chapters=cast(list[dict[str, Any]], info.get("chapters") or []),
        sheet=sheet,
        frame_ruler="time" if sheet else None,
    )
    return bundle, {"storyboard": grid, "needs_whisper": not segments}


# ---------------------------------------------------------------------------
# Reels and TikToks: the whole video is a few MB, so keep it for close-ups
# ---------------------------------------------------------------------------


def zen_profile() -> Path | None:
    from .tiktok_fav import zen_cookie_db

    try:
        return zen_cookie_db().parent
    except Exception:
        return None


def _video_post(
    url: str, d: Path, timings: dict[str, float]
) -> tuple[EvidenceBundle, dict[str, Any]]:
    from .transcript import transcribe_file
    from .vision import contact_sheet, extract_frame_tier, frame_plan, nearest_frames

    source = classify_url(url)
    opts: dict[str, Any] = {
        "format": "best[ext=mp4]/best",
        "outtmpl": str(d / "video.%(ext)s"),
    }
    profile = zen_profile() if source == "instagram" else None
    if profile is not None:
        # Browser cookies, never an instagrapi login: repeated logins are what
        # got the account flagged for automation (2026-08-14).
        opts["cookiesfrombrowser"] = ("firefox", str(profile), None, None)
    with _timed(timings, "download"), _ydl(opts) as ydl:
        info = cast(dict[str, Any], ydl.extract_info(url, download=True))
    videos = sorted(d.glob("video.*"))
    if not videos:
        raise FetchError("the download produced no video file")
    video = videos[0]
    duration = cast(float | None, info.get("duration"))
    gaps: list[str] = []
    frames: list[str] = []
    dense: list[dict[str, Any]] = []
    sheet: str | None = None
    ruler: str | None = None
    with _timed(timings, "sheet"):
        plan = frame_plan(duration)
        try:
            tier = extract_frame_tier(video, plan, duration)
        except Exception as exc:
            gaps.append(f"frames could not be extracted: {exc}")
            tier = []
        if tier:
            ruler = plan.ruler
            dense_dir = d / "dense"
            dense_dir.mkdir(exist_ok=True)
            for i, f in enumerate(tier):
                p = dense_dir / f"f-{i:03d}.jpg"
                p.write_bytes(f.data)
                dense.append({"t": f.t, "path": str(p)})
            span = duration or tier[-1].t
            shown_dir = d / "shown"
            shown_dir.mkdir(exist_ok=True)
            for i, f in enumerate(nearest_frames(tier, [span * k / 5 for k in range(1, 5)])):
                p = shown_dir / f"frame-{i}.jpg"
                p.write_bytes(f.data)
                frames.append(str(p))
            data = contact_sheet(tier, label=str(info.get("id") or source))
            if data:
                (d / "sheet.jpg").write_bytes(data)
                sheet = str(d / "sheet.jpg")
    segments: list[dict[str, Any]] = []
    status = "none"
    needs_whisper = False
    if duration is not None and duration > SYNC_WHISPER_MAX_S:
        needs_whisper = True
    else:
        with _timed(timings, "whisper"):
            result = transcribe_file(video)
        segments, status = result.segments, result.status
        if result.error:
            gaps.append(f"transcription failed: {result.error}")
    text = cast(str | None, info.get("description"))
    bundle = EvidenceBundle(
        source=source,
        url=url,
        title=info.get("title") or info.get("uploader"),
        transcript=segments,
        transcript_origin="whisper" if segments else "none",
        transcript_language=None,
        transcript_status=status,
        description=text if source != "instagram" else None,
        caption=text if source == "instagram" else None,
        frames=frames,
        gaps=gaps,
        media_id=info.get("id"),
        uploader=info.get("uploader") or info.get("channel"),
        upload_date=info.get("upload_date"),
        duration=duration,
        thumbnail=info.get("thumbnail"),
        dense_frames=dense,
        sheet=sheet,
        frame_ruler=ruler,
    )
    return bundle, {"video": str(video), "needs_whisper": needs_whisper}


# ---------------------------------------------------------------------------
# Web
# ---------------------------------------------------------------------------

_ARXIV_ABS = re.compile(r"arxiv\.org/abs/(\d{4})\.(\d{4,5})(v\d+)?")


def rewrite_arxiv(url: str) -> str:
    """An /abs/ page is the abstract plus boilerplate; the paper is the HTML
    rendering (arXiv's own from 2312 on, ar5iv before)."""
    m = _ARXIV_ABS.search(url)
    if not m:
        return url
    paper = f"{m.group(1)}.{m.group(2)}"
    if int(m.group(1)) >= 2312:
        return f"https://arxiv.org/html/{paper}{m.group(3) or 'v1'}"
    return f"https://ar5iv.labs.arxiv.org/html/{paper}"


_MD_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")


def _web(url: str, d: Path, timings: dict[str, float]) -> tuple[EvidenceBundle, dict[str, Any]]:
    import trafilatura

    from .evidence import strip_boilerplate

    target = rewrite_arxiv(url)
    with _timed(timings, "download"):
        downloaded = trafilatura.fetch_url(target)
    if not downloaded:
        raise FetchError(f"could not download {target}")
    with _timed(timings, "extract"):
        meta = trafilatura.extract_metadata(downloaded)
        text = trafilatura.extract(
            downloaded,
            url=target,
            output_format="markdown",
            include_comments=False,
            include_tables=True,
            include_formatting=True,
            include_images=True,
        )
    if not text:
        raise FetchError(f"no readable text at {target}")
    text = _MD_IMAGE.sub(
        lambda m: f"![{m.group(1)}]({urllib.parse.urljoin(target, m.group(2))})", text
    )
    text, _ = strip_boilerplate(text)
    gaps = [f"fetched {target} in place of the abstract page"] if target != url else []
    date = (meta.date or "") if meta else ""
    bundle = EvidenceBundle(
        source="web",
        url=url,
        title=(meta.title if meta and meta.title else None) or target,
        transcript=[],
        transcript_origin="none",
        transcript_language=None,
        transcript_status="none",
        text=text,
        gaps=gaps,
        uploader=(meta.author if meta and meta.author else None),
        upload_date=date.replace("-", "") or None,
    )
    return bundle, {}


# ---------------------------------------------------------------------------
# The cache and the entry points
# ---------------------------------------------------------------------------

_VIDEO = ("youtube", "instagram", "tiktok")
Gatherer = Callable[[str, Path, dict[str, float]], tuple[EvidenceBundle, dict[str, Any]]]
_GATHER: dict[str, Gatherer] = {
    "youtube": _youtube,
    "instagram": _video_post,
    "tiktok": _video_post,
    "web": _web,
}


def _atomic(path: Path, text: str) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def _write(f: Fetched) -> None:
    f.dir.mkdir(parents=True, exist_ok=True)
    _atomic(f.dir / "bundle.json", json.dumps(asdict(f.bundle), indent=1))
    _atomic(f.content_path, render(f))
    # Last: an entry with meta.json is complete.
    _atomic(f.dir / "meta.json", json.dumps(f.meta, indent=1))


@contextmanager
def _locked(d: Path) -> Generator[None]:
    """One writer per entry: a second fetch of the URL waits, then reads."""
    import fcntl

    d.mkdir(parents=True, exist_ok=True)
    with open(d / ".lock", "a") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _load(url: str, d: Path) -> Fetched | None:
    """None for a missing or unreadable entry, which is then fetched again."""
    try:
        meta = cast(dict[str, Any], json.loads((d / "meta.json").read_text()))
        bundle = load_bundle(d / "bundle.json")
    except (OSError, ValueError, TypeError):
        return None
    return Fetched(url=url, dir=d, bundle=bundle, meta=meta, cached=True)


def _alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        # Reaps a finished child of this process: a zombie answers kill(0).
        done, _ = os.waitpid(pid, os.WNOHANG)
        return done == 0
    except ChildProcessError:
        pass
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _whisper_running(f: Fetched | None) -> dict[str, Any] | None:
    w = cast(dict[str, Any], (f.meta.get("whisper") if f else None) or {})
    if w and not w.get("done_at") and _alive(int(w.get("pid") or 0)):
        return w
    return None


def _settle_whisper(f: Fetched) -> None:
    """A background run that died without writing back is said, not waited on."""
    w = cast(dict[str, Any], f.meta.get("whisper") or {})
    if w and not w.get("done_at") and _whisper_running(f) is None:
        w["done_at"] = _now()
        w["status"] = "died"
        f.bundle.gaps.append(
            f"local transcription stopped without a result ({f.dir / 'whisper.log'})"
        )
        _write(f)


def _spawn(args: list[str], log_path: Path) -> int:
    """Detached from the caller's session, so it outlives a CLI that exits."""
    with open(log_path, "ab") as log:
        proc = subprocess.Popen(
            args, stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True
        )
    return proc.pid


def _start_whisper(f: Fetched) -> None:
    duration = float(f.bundle.duration or 0)
    pid = _spawn([sys.executable, "-m", "ytk.fetch", str(f.dir)], f.dir / "whisper.log")
    f.meta["whisper"] = {
        "pid": pid,
        "started_at": _now(),
        "estimate_s": max(5, round(duration * WHISPER_SECONDS_PER_SECOND)),
    }


def _clear_looks(d: Path) -> None:
    """Close-ups and span sheets are cut from the old download."""
    import shutil

    for p in d.glob("span-*.jpg"):
        p.unlink()
    shutil.rmtree(d / "closeups", ignore_errors=True)


def fetch(url: str, *, refresh: bool = False, whisper: bool = True) -> Fetched:
    url = url.strip()
    d = fetch_dir() / cache_key(url)
    with _locked(d):
        old = _load(url, d)
        if old is not None and not refresh:
            _settle_whisper(old)
            return old
        _clear_looks(d)
        source = classify_url(url)
        timings: dict[str, float] = {}
        t0 = time.monotonic()
        gather = _GATHER.get(source)
        if gather is not None:
            bundle, meta = gather(url, d, timings)
        else:
            from . import gatherers
            from .evidence import GATHERERS

            _ = gatherers
            with _timed(timings, "gather"):
                bundle = GATHERERS[source](url, None)
            meta = {}
        timings["total"] = round(time.monotonic() - t0, 2)
        meta |= {"url": url, "source": source, "fetched_at": _now(), "timings": timings}
        f = Fetched(url=url, dir=d, bundle=bundle, meta=meta, cached=False)
        if meta.get("needs_whisper") and whisper:
            running = _whisper_running(old)
            if running is not None:
                f.meta["whisper"] = running
            else:
                _start_whisper(f)
        _write(f)
        return f


def adoptable_bundle(url: str) -> EvidenceBundle | None:
    """The cached bundle for the curator's read step, or None when there is
    none or a video's transcript is missing (pending, or never came): the
    gatherer then gets its own try instead of a junk ask."""
    f = _load(url, fetch_dir() / cache_key(url))
    if f is None:
        return None
    if f.bundle.source in _VIDEO and f.bundle.transcript_status not in ("ok", "no_speech"):
        return None
    return f.bundle


def transcribe_into(d: Path) -> None:
    """The detached half of a fetch: Whisper over the kept video, or over the
    audio track for YouTube, written back into the same cache entry. A result
    whose entry was refetched meanwhile is dropped; the new entry owns it."""
    from .transcript import _download_audio, transcribe_file  # pyright: ignore[reportPrivateUsage]

    meta = cast(dict[str, Any], json.loads((d / "meta.json").read_text()))
    url = str(meta["url"])
    try:
        media = Path(meta["video"]) if meta.get("video") else _download_audio(url)
        result = transcribe_file(media)
        segments, status, error = result.segments, result.status, result.error
    except Exception as exc:
        segments, status, error = [], "failed", str(exc)
    with _locked(d):
        f = _load(url, d)
        w = cast(dict[str, Any], (f.meta.get("whisper") if f else None) or {})
        if f is None or w.get("pid") != os.getpid():
            return
        f.bundle.transcript = segments
        f.bundle.transcript_status = status
        f.bundle.transcript_origin = "whisper" if segments else "none"
        f.bundle.gaps = [g for g in f.bundle.gaps if not g.startswith("captions could not be read")]
        if error:
            f.bundle.gaps.append(f"transcription failed: {error}")
        w |= {"done_at": _now(), "status": status}
        f.meta["whisper"] = w
        _write(f)


# ---------------------------------------------------------------------------
# Looking closer: a denser sheet of a stretch, or sharp frames at moments
# ---------------------------------------------------------------------------


def _ffmpeg_frame(video: Path | str, t: float, out: Path) -> Path:
    from .vision import _tool  # pyright: ignore[reportPrivateUsage]

    subprocess.run(
        [
            _tool("ffmpeg"),
            "-y",
            "-loglevel",
            "error",
            "-ss",
            f"{t:.2f}",
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(out),
        ],
        check=True,
        capture_output=True,
    )
    if not out.exists():
        raise FetchError(f"no frame at {t:.1f}s")
    return out


def _youtube_closeup(url: str, t: float, out: Path) -> Path:
    from yt_dlp.utils import download_range_func

    clip_dir = out.parent / f"clip-{t:08.1f}"
    clip_dir.mkdir(parents=True, exist_ok=True)
    opts: dict[str, Any] = {
        "format": f"bestvideo[height<={CLOSEUP_HEIGHT}][ext=mp4]/bestvideo[height<={CLOSEUP_HEIGHT}]",
        "download_ranges": download_range_func([], [(int(t), int(t) + 2)]),
        "outtmpl": str(clip_dir / "clip.%(ext)s"),
    }
    with _ydl(opts) as ydl:
        ydl.extract_info(url, download=True)
    clips = sorted(clip_dir.glob("clip.*"))
    if not clips:
        raise FetchError(f"no clip downloaded at {t:.1f}s")
    _ffmpeg_frame(clips[0], 0, out)
    for c in clip_dir.iterdir():
        c.unlink()
    clip_dir.rmdir()
    return out


def closeups(f: Fetched, at: list[float]) -> list[tuple[float, Path | str]]:
    """Full-resolution frames at the given seconds: a path, or why that one
    failed. YouTube downloads two seconds at each, in parallel; a reel reads
    its kept video."""
    out_dir = f.dir / "closeups"
    out_dir.mkdir(exist_ok=True)

    def one(t: float) -> tuple[float, Path | str]:
        try:
            return t, frame(t)
        except Exception as exc:
            return t, str(exc)

    def frame(t: float) -> Path:
        out = out_dir / f"t{t:08.1f}.jpg"
        if out.exists():
            return out
        if f.bundle.source == "youtube":
            return _youtube_closeup(f.url, t, out)
        video = f.meta.get("video")
        if not video or not Path(video).exists():
            raise FetchError("no kept video for this source")
        return _ffmpeg_frame(video, t, out)

    with ThreadPoolExecutor(MAX_CLOSEUPS) as pool:
        return list(pool.map(one, at[:MAX_CLOSEUPS]))


def _span_frames(video: Path, start: float, end: float) -> list[TimedFrame]:
    """One ffmpeg pass over the stretch at the rate that yields SPAN_TILES."""
    import tempfile

    from .vision import TimedFrame, _tool  # pyright: ignore[reportPrivateUsage]

    span = max(0.1, end - start)
    rate = SPAN_TILES / span
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            [
                _tool("ffmpeg"),
                "-y",
                "-loglevel",
                "error",
                "-ss",
                f"{start:.2f}",
                "-t",
                f"{span:.2f}",
                "-i",
                str(video),
                "-vf",
                f"fps={rate:.4f},scale='min(720,iw)':-2",
                "-q:v",
                "3",
                str(Path(tmp) / "f-%03d.jpg"),
            ],
            check=True,
            capture_output=True,
        )
        files = sorted(Path(tmp).glob("f-*.jpg"))[:SPAN_TILES]
        return [TimedFrame(t=start + i / rate, data=p.read_bytes()) for i, p in enumerate(files)]


def span_sheet(f: Fetched, start: float, end: float) -> Path:
    """Every storyboard tile in [start, end] (up to 60), or for a kept video,
    60 frames spread over the stretch."""
    from .vision import contact_sheet

    if end <= start:
        raise FetchError(f"end ({end:.1f}s) must come after start ({start:.1f}s)")
    out = f.dir / f"span-{start:.1f}-{end:.1f}.jpg"
    if out.exists():
        return out
    grid = cast(dict[str, Any] | None, f.meta.get("storyboard"))
    label = f.bundle.media_id or f.bundle.source
    data: bytes | None
    if grid:
        # The tile showing a moment is the one at or before it.
        last = int(grid["tiles"]) - 1
        lo = min(last, max(0, int(start // grid["interval"])))
        hi = min(last, max(lo, int(end // grid["interval"])))
        idx = list(range(lo, hi + 1))
        picks = [idx[i] for i in _even(len(idx), SPAN_TILES)]
        data = _tiles_sheet(f.dir / "storyboard", grid, picks, label)
    elif f.meta.get("video"):
        data = contact_sheet(_span_frames(Path(f.meta["video"]), start, end), label=label)
    else:
        raise FetchError("nothing to look closer at for this source")
    if data is None:
        raise FetchError(f"no frames between {start:.0f}s and {end:.0f}s")
    out.write_bytes(data)
    return out


# ---------------------------------------------------------------------------
# Rendering for a chat
# ---------------------------------------------------------------------------


def _ts(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def paragraphs(segments: list[dict[str, Any]], every: float = PARAGRAPH_S) -> list[str]:
    """Caption lines joined into ~30 s paragraphs, each led by its start time:
    a line per two-second caption costs a timestamp per handful of words."""
    out: list[str] = []
    start: float | None = None
    words: list[str] = []
    for seg in segments:
        t = float(seg.get("start") or 0)
        if start is None:
            start = t
        elif t - start >= every:
            out.append(f"[{_ts(start)}] {' '.join(words)}")
            start, words = t, []
        words.append(str(seg.get("text") or "").strip())
    if start is not None and words:
        out.append(f"[{_ts(start)}] {' '.join(words)}")
    return out


def render(f: Fetched, cap_chars: int | None = None) -> str:
    b = f.bundle
    facts = [b.source]
    if b.uploader:
        facts.append(b.uploader)
    if b.upload_date and len(b.upload_date) == 8:
        facts.append(f"{b.upload_date[:4]}-{b.upload_date[4:6]}-{b.upload_date[6:]}")
    if b.duration:
        facts.append(_ts(float(b.duration)))
    facts.append(f.url)
    lines = [f"# {b.title or f.url}", " | ".join(facts)]
    timings = cast(dict[str, float], f.meta.get("timings") or {})
    if timings:
        steps = ", ".join(f"{k} {v}s" for k, v in timings.items() if k != "total")
        lines.append(
            f"Fetched {f.meta.get('fetched_at')} in {timings.get('total')}s ({steps})"
            + ("; read from cache" if f.cached else "")
        )
    if b.transcript:
        lang = f", {b.transcript_language}" if b.transcript_language else ""
        lines.append(f"Transcript: {b.transcript_origin}{lang}, {len(b.transcript)} lines")
    elif f.pending:
        lines.append(f"Transcript: pending, {f.pending}. Fetch again for it.")
    elif b.source != "web":
        lines.append(f"Transcript: none ({b.transcript_status})")
    grid = cast(dict[str, Any] | None, f.meta.get("storyboard"))
    if b.sheet:
        if grid:
            shown = min(SHEET_TILES, int(grid["tiles"]))
            every = float(b.duration or 0) / max(1, shown)
            what = (
                f"{shown} storyboard frames at {grid['tile_w']}x{grid['tile_h']}, one every "
                f"~{every:.0f}s across the whole video"
            )
        else:
            what = f"{len(b.dense_frames)} frames, {b.frame_ruler} ruler"
        lines.append(
            f"Sheet: {b.sheet} ({what}; tile labels are seconds). Sharper: fetch_frames with "
            "at=[seconds] for full-resolution close-ups, or start/end for a denser sheet."
        )
    if b.gaps:
        lines.append("Gaps: " + "; ".join(b.gaps))
    parts = ["\n".join(lines)]
    if b.chapters:
        rows = [
            f"- [{_ts(float(c.get('start_time') or 0))}] {c.get('title', '')}" for c in b.chapters
        ]
        parts.append("## Chapters\n" + "\n".join(rows))
    if b.description:
        parts.append("## Description\n" + b.description.strip())
    if b.caption:
        parts.append("## Caption\n" + b.caption.strip())
    if b.text:
        parts.append("## Body\n" + b.text.strip())
    if b.transcript:
        parts.append("## Transcript\n" + "\n\n".join(paragraphs(b.transcript)))
    text = "\n\n".join(parts) + "\n"
    if cap_chars is not None and len(text) > cap_chars:
        cut = text.rfind("\n", 0, cap_chars)
        text = (
            text[: cut if cut > 0 else cap_chars]
            + f"\n\n[Cut at {cap_chars} of {len(text)} characters. The full text is in "
            f"{f.content_path}; read it from there for the rest.]\n"
        )
    return text


if __name__ == "__main__":
    transcribe_into(Path(sys.argv[1]))
