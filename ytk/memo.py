# pyright: basic
# Not strict-clean yet (#122). Delete these two lines once the module
# passes strict — the list of files carrying them only shrinks.
"""Voice memo pipeline: record -> transcribe -> route -> execute.

The memo note is always written before routing so a routing failure can
never lose the transcript. See docs/superpowers/specs/2026-07-05-voice-memo-capture-design.md.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from .sdk import structured
from .store import upsert_memory
from .triage import ActionItem
from .vault import _get_brain_path, remember

_SYSTEM_MEMO = """\
You are routing a spoken voice memo captured into a personal knowledge system.
The transcript may be informal, rambling, or contain speech-recognition noise.

Classify it into exactly one kind:

kind:
  "memory"  — a durable fact, decision, or preference worth remembering long-term.
  "action"  — the memo is primarily one or more concrete actionable tasks.
  "thought" — everything else: musings, reflections, half-ideas not yet actionable.
  kind reflects the DOMINANT character of the memo, but action items are
  extracted regardless of kind (see items).

summary: One line under 80 chars capturing the memo, used in a desktop notification.

tags: For "memory" only — 1-4 lowercase hyphenated topic tags. Otherwise [].

items: Every concrete, stated ask in the memo, whatever its kind — a memo that
  is mostly musing can still contain "can we add X" or "we need to Y" asks;
  extract those too. [] only when nothing actionable was stated. Each item has:
  title: Short imperative phrase under 70 chars.
  description: 1-2 sentences with enough context to act on without the recording.
  priority: "high", "medium", or "low" based on urgency signals in the memo.
  suggested_route: "gh-issue" for concrete software tasks in a known repo,
    "idea" for loose ideas to try later, "investigate" for things to research first.
  suggested_repo: Full "owner/repo" if the item clearly belongs to an available
    repo, otherwise null.
Otherwise [].

Prefer "thought" when unsure. Do not invent actions the speaker did not state.
"""


class MemoResult(BaseModel):
    kind: Literal["memory", "action", "thought"]
    summary: str
    tags: list[str] = Field(default_factory=list)
    items: list[ActionItem] = Field(default_factory=list)


def route(transcript: str, repos: list[str] | None = None) -> MemoResult:
    """Classify a memo transcript. One primary kind per memo (v1)."""
    repo_hint = f"\nAvailable GitHub repos: {', '.join(repos)}\n" if repos else ""
    return structured(_SYSTEM_MEMO + repo_hint, transcript, MemoResult)


_DEDUP_WINDOW_SECONDS = 6 * 60 * 60


def _recent_memo_with_hash(note_dir: Path, text_hash: str) -> Path | None:
    """Return a recent memo note with the same content hash, if one exists.

    The content hash is the last filename segment, so an identical transcript
    always produces the same suffix. We only suppress a duplicate written within
    a recent window so a genuinely-repeated thought days later still lands.
    """
    now = datetime.now().timestamp()
    matches = sorted(
        note_dir.glob(f"*-{text_hash}.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in matches:
        if now - path.stat().st_mtime <= _DEDUP_WINDOW_SECONDS:
            return path
    return None


def write_memo_note(transcript: str, audio_path: Path | None, source: str = "voice") -> Path:
    """Write the memo note BEFORE routing. Nothing said is ever lost.

    `source` distinguishes capture channels: "voice" (recorded) vs "imessage"
    (typed self-notes ingested through the same routing pipeline).
    """
    now = datetime.now()
    slug = re.sub(r"[^a-z0-9]+", "-", transcript[:40].lower()).strip("-") or "memo"
    text_hash = hashlib.sha1(transcript.encode("utf-8"), usedforsecurity=False).hexdigest()[:6]
    note_dir = _get_brain_path() / "inbox" / "memos"
    note_dir.mkdir(parents=True, exist_ok=True)

    existing = _recent_memo_with_hash(note_dir, text_hash)
    if existing is not None:
        return existing

    note_path = note_dir / f"{now.strftime('%Y-%m-%d-%H%M')}-{slug}-{text_hash}.md"

    audio_line = f"audio: {audio_path}\n" if audio_path else ""
    note_path.write_text(
        f"---\ncaptured: {now.isoformat(timespec='seconds')}\n"
        f"source: {source}\n{audio_line}route: pending\n---\n\n{transcript}\n",
        encoding="utf-8",
    )
    return note_path


def finalize_memo_note(note_path: Path, route_kind: str, routed_lines: list[str]) -> None:
    """Update route: frontmatter and append the ## Routed section."""
    content = note_path.read_text(encoding="utf-8")
    content = content.replace("route: pending", f"route: {route_kind}", 1)
    if routed_lines:
        content += "\n## Routed\n" + "\n".join(f"- {line}" for line in routed_lines) + "\n"
    note_path.write_text(content, encoding="utf-8")


def index_memo_note(note_path: Path, transcript: str, kind: str) -> None:
    """Index the memo note into Chroma like other vault writes."""
    upsert_memory(f"memo_{note_path.stem}", transcript, ["memo", kind], str(note_path))


def _append_idea(item: ActionItem, note: str = "") -> str:
    """Append an action item to inbox/ideas.md (triage entry format)."""
    ideas_path = _get_brain_path() / "inbox" / "ideas.md"
    ideas_path.parent.mkdir(parents=True, exist_ok=True)
    suffix = f" ({note})" if note else ""
    with ideas_path.open("a", encoding="utf-8") as f:
        f.write(f"\n- [ ] {item.title}{suffix}\n  {item.description}\n")
    return f"idea{suffix or ' ->'} inbox/ideas.md: {item.title}"


def execute_route(result: MemoResult, transcript: str, github_repos: list[str]) -> list[str]:
    """Create the artifacts for a routed memo. Returns human-readable lines.

    Mixed routing: `kind` names the memo's dominant character, but stated
    action items are executed whatever the kind — a mostly-musing memo with a
    "can we add X" buried in it still gets that ask filed.
    """
    lines: list[str] = []

    if result.kind == "memory":
        note_path, doc_id = remember(transcript, result.tags)
        upsert_memory(doc_id, transcript, result.tags, str(note_path))
        lines.append(f"memory -> {note_path.name}")

    for item in result.items:
        if item.suggested_route == "gh-issue" and item.suggested_repo in github_repos:
            try:
                gh = subprocess.run(
                    [
                        "gh",
                        "issue",
                        "create",
                        "--title",
                        item.title,
                        "--body",
                        item.description,
                        "--repo",
                        item.suggested_repo,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    stdin=subprocess.DEVNULL,
                )
            except (FileNotFoundError, subprocess.TimeoutExpired):
                gh = None
            if gh is not None and gh.returncode == 0:
                lines.append(
                    f"gh-issue -> {item.suggested_repo}: {item.title} ({gh.stdout.strip()})"
                )
            else:
                lines.append(_append_idea(item, "gh failed"))
        elif item.suggested_route == "investigate":
            lines.append(_append_idea(item, "investigate"))
        else:
            lines.append(_append_idea(item))

    return lines  # a pure "thought": the transcript note is the artifact


AUDIO_DIR = Path.home() / ".ytk" / "audio" / "memos"


def record(out_path: Path, max_seconds: int = 300, wait=input) -> Path:
    """Record mic audio via ffmpeg avfoundation until Enter (or max_seconds)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "avfoundation",
            "-i",
            ":default",
            "-t",
            str(max_seconds),
            "-ar",
            "16000",
            "-ac",
            "1",
            str(out_path),
        ],
        stdin=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        wait("Recording... press Enter to stop. ")
    except (EOFError, KeyboardInterrupt):
        pass
    try:
        _, err = proc.communicate(b"q", timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        _, err = proc.communicate()
    if proc.returncode not in (0, 255) or not out_path.exists() or out_path.stat().st_size == 0:
        detail = (err or b"").decode(errors="replace").strip()
        raise RuntimeError(
            "Microphone capture failed. Grant mic access in System Settings > "
            f"Privacy & Security > Microphone for your terminal. ffmpeg said: {detail}"
        )
    return out_path


def ensure_wav(path: Path) -> Path:
    """Convert any audio container to 16 kHz mono WAV (no-op for .wav)."""
    if path.suffix.lower() == ".wav":
        return path
    out = path.with_suffix(".wav")
    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(path),
            "-ar",
            "16000",
            "-ac",
            "1",
            str(out),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg conversion failed: {result.stderr.strip()}")
    return out


LOG_PATH = Path.home() / ".ytk" / "logs" / "memo.log"


class StageLog:
    """Append-only state machine trace: one line per transition with the
    delta since the previous state. Correlate runs by run_id."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.prev = time.monotonic()
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.mark("START")

    def mark(self, state: str, detail: str = "") -> None:
        now = time.monotonic()
        delta = now - self.prev
        self.prev = now
        stamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        with LOG_PATH.open("a") as f:
            f.write(
                f"{stamp} [{self.run_id}] +{delta:6.2f}s {state}"
                + (f" {detail}" if detail else "")
                + "\n"
            )


_MODEL_CACHE: dict = {}


def _whisper_model(model_name: str):
    from faster_whisper import WhisperModel

    if model_name not in _MODEL_CACHE:
        _MODEL_CACHE[model_name] = WhisperModel(model_name, device="cpu", compute_type="int8")
    return _MODEL_CACHE[model_name]


def preload_model(model_name: str) -> None:
    """Warm the whisper model in a daemon thread (call before recording so the
    load overlaps with the user speaking)."""
    import threading

    threading.Thread(target=_whisper_model, args=(model_name,), daemon=True).start()


def transcribe(wav_path: Path, model_name: str) -> str:
    """Local faster-whisper transcription; returns plain joined text."""
    segments, _info = _whisper_model(model_name).transcribe(str(wav_path))
    return " ".join(s.text.strip() for s in segments).strip()


def _which(name: str) -> str | None:
    """shutil.which with a homebrew fallback — background workers spawned from
    tmux popups can carry a PATH without /opt/homebrew/bin."""
    found = shutil.which(name)
    if found:
        return found
    brew = Path("/opt/homebrew/bin") / name
    return str(brew) if brew.exists() else None


def _terminal_visible() -> bool | None:
    """True/False via AeroSpace; None if aerospace is unavailable."""
    aerospace = _which("aerospace")
    if aerospace is None:
        return None
    try:
        out = subprocess.run(
            [aerospace, "list-windows", "--workspace", "visible", "--format", "%{app-name}"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if out.returncode != 0:
            return None
        return "ghostty" in out.stdout.lower()
    except Exception:
        return None


def _fire(backend: str, summary: str, kind: str) -> bool:
    msg = f"ytk memo [{kind}]: {summary}"
    cmds = {
        "tmux": ["tmux", "display-message", "-d", "4000", msg],
        "macos": [
            "terminal-notifier",
            "-title",
            "ytk memo",
            "-subtitle",
            kind,
            "-message",
            summary,
            "-group",
            "ytk-memo",
        ],
        "sketchybar": ["sketchybar", "--trigger", "ytk_memo", f"RESULT={summary}", f"ROUTE={kind}"],
    }
    cmd = cmds.get(backend)
    if cmd is None:
        return False
    exe = _which(cmd[0])
    if exe is None:
        return False
    cmd = [exe] + cmd[1:]

    # For tmux notifications, hide cursor during display to avoid visual collision
    # with the red margin and jumping cursor animation
    if backend == "tmux":
        try:
            subprocess.run(["tput", "civis"], capture_output=True, timeout=1)  # Hide cursor
            subprocess.run(cmd, capture_output=True, timeout=3)
            subprocess.run(["tput", "cnorm"], capture_output=True, timeout=1)  # Show cursor
            return True
        except Exception:
            return False

    try:
        subprocess.run(cmd, capture_output=True, timeout=3)
        return True
    except Exception:
        return False


def notify(summary: str, kind: str, backends: list[str] | None = None) -> list[str]:
    """Send the routing result where the eyes are. Never raises."""
    if not backends:
        visible = _terminal_visible()
        if visible is None:
            primary = "tmux" if os.environ.get("TMUX") else "macos"
        else:
            primary = "tmux" if visible else "macos"
        backends = [primary, "sketchybar"]
    return [b for b in backends if _fire(b, summary, kind)]
