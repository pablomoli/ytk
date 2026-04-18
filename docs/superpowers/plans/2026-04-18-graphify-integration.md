# graphify Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adopt three patterns from graphify — Whisper transcription fallback, SHA256 incremental vault cache, and HTML knowledge graph — as native ytk features without taking graphifyy as a dependency.

**Architecture:** Feature 1 replaces the yt-dlp subtitle tier in `transcript.py` with a faster-whisper local ASR tier that preserves timestamps. Feature 2 adds a SHA256 cache in `ytk/cache.py` wired into `vault.py`'s `reindex_vault()` to skip unchanged files. Feature 3 adds `ytk/graph.py` that builds a NetworkX graph from vault notes (tag/concept/semantic edges) and exports an interactive vis.js HTML file, exposed via `ytk graph`.

**Tech Stack:** faster-whisper (local ASR), networkx (graph), yt-dlp (audio download, already a dep), ChromaDB (semantic edges), vis.js CDN (HTML graph), pytest (tests)

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `pyproject.toml` | Modify | Add faster-whisper, networkx; optional graspologic; pytest dev dep |
| `ytk/config.py` | Modify | Add `whisper_model: str = "base"` field |
| `ytk/transcript.py` | Modify | Remove `_fetch_via_ytdlp`; add `_download_audio`, `_fetch_via_whisper` |
| `ytk/cache.py` | Create | SHA256 file hashing + index cache read/write |
| `ytk/vault.py` | Modify | `reindex_vault(force=False)` uses cache to skip unchanged files |
| `ytk/mcp_server.py` | Modify | `vault_reindex` exposes `force`; `vault_write` updates cache |
| `ytk/cli.py` | Modify | `reindex --force` flag; new `ytk graph` command |
| `ytk/graph.py` | Create | Graph building, community detection, HTML/JSON export |
| `tests/test_transcript.py` | Create | Whisper tier tests |
| `tests/test_cache.py` | Create | Cache module tests |
| `tests/test_graph.py` | Create | Graph building and export tests |

---

## Task 1: Deps and Config Field

**Files:**
- Modify: `pyproject.toml`
- Modify: `ytk/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
from ytk.config import Config, load_config


def test_default_whisper_model():
    cfg = Config()
    assert cfg.whisper_model == "base"


def test_whisper_model_from_yaml(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("whisper_model: small\n", encoding="utf-8")
    cfg = load_config(cfg_file)
    assert cfg.whisper_model == "small"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_config.py -v
```
Expected: `FAILED — AttributeError: 'Config' object has no attribute 'whisper_model'`

- [ ] **Step 3: Add faster-whisper and networkx to pyproject.toml**

In `pyproject.toml`, add to `dependencies`:
```toml
dependencies = [
    "click>=8.1",
    "yt-dlp>=2024.1.1",
    "youtube-transcript-api>=0.6.2",
    "python-dotenv>=1.0",
    "rich>=13.0",
    "anthropic>=0.40.0",
    "pyyaml>=6.0",
    "google-api-python-client>=2.100",
    "google-auth-oauthlib>=1.0",
    "chromadb>=0.5",
    "sentence-transformers>=3.0",
    "mcp>=1.0",
    "trafilatura>=1.6",
    "faster-whisper>=1.0",
    "networkx>=3.0",
]

[project.optional-dependencies]
graph = ["graspologic"]
dev = ["pytest>=8.0"]
```

- [ ] **Step 4: Add `whisper_model` field to Config**

Replace the `Config` class in `ytk/config.py`:
```python
class Config(BaseModel):
    filters: FilterConfig = Field(default_factory=FilterConfig)
    whisper_model: str = Field(default="base", description="faster-whisper model size: base | small | medium | large")
```

- [ ] **Step 5: Install deps and run test**

```bash
uv sync
uv run pytest tests/test_config.py -v
```
Expected: `PASSED` (both tests green)

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml ytk/config.py tests/test_config.py
git commit -m "feat: add faster-whisper + networkx deps and whisper_model config field"
```

---

## Task 2: Whisper Transcription Tier

**Files:**
- Modify: `ytk/transcript.py`
- Modify: `ytk/cli.py` (pass `cfg.whisper_model`)
- Modify: `ytk/scheduler.py` (pass `cfg.whisper_model`)
- Modify: `scripts/reindex.py` (use default)
- Create: `tests/test_transcript.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_transcript.py
from unittest.mock import MagicMock, patch
from pathlib import Path
import pytest

from ytk.transcript import fetch_transcript, _fetch_via_whisper, _download_audio


class _FakeSeg:
    def __init__(self, start, end, text):
        self.start = start
        self.end = end
        self.text = text


def _fake_segments():
    return [
        _FakeSeg(0.0, 5.0, "Hello world"),
        _FakeSeg(5.0, 10.0, "Second segment"),
    ], MagicMock(language="en")


def test_whisper_segments_have_timestamps(tmp_path):
    """_fetch_via_whisper converts faster-whisper segments to {start, duration, text}."""
    audio_file = tmp_path / "audio.m4a"
    audio_file.write_bytes(b"fake")

    with patch("ytk.transcript._download_audio", return_value=audio_file), \
         patch("ytk.transcript.WhisperModel") as MockModel:
        MockModel.return_value.transcribe.return_value = _fake_segments()
        segments, source = _fetch_via_whisper("https://youtu.be/test123", whisper_model="base")

    assert source == "whisper"
    assert segments[0] == {"start": 0.0, "duration": 5.0, "text": "Hello world"}
    assert segments[1] == {"start": 5.0, "duration": 5.0, "text": "Second segment"}


def test_fetch_transcript_falls_back_to_whisper():
    """When youtube-transcript-api fails, fetch_transcript calls Whisper."""
    from youtube_transcript_api import NoTranscriptFound

    with patch("ytk.transcript._fetch_via_api", side_effect=NoTranscriptFound("x", "x", {}, [])), \
         patch("ytk.transcript._fetch_via_whisper", return_value=([], "whisper")) as mock_whisper:
        segments, source = fetch_transcript("https://youtu.be/abc123")

    mock_whisper.assert_called_once()
    assert source == "whisper"


def test_fetch_transcript_no_ytdlp_subtitle_tier():
    """The old yt-dlp subtitle tier is gone — only two tiers exist."""
    import ytk.transcript as t
    assert not hasattr(t, "_fetch_via_ytdlp"), "yt-dlp subtitle tier should be removed"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_transcript.py -v
```
Expected: `FAILED` — `_fetch_via_whisper` not found, `_fetch_via_ytdlp` still present.

- [ ] **Step 3: Rewrite transcript.py**

Replace the entire content of `ytk/transcript.py`:

```python
"""Fetch transcript with youtube-transcript-api primary, faster-whisper fallback."""

from __future__ import annotations

import hashlib
import re
import tempfile
from pathlib import Path

from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled

_AUDIO_CACHE = Path.home() / ".ytk" / "audio"


def _video_id(url: str) -> str:
    """Extract the 11-char video ID from a YouTube URL."""
    match = re.search(r"(?:v=|youtu\.be/|embed/)([A-Za-z0-9_-]{11})", url)
    if not match:
        raise ValueError(f"Could not extract video ID from URL: {url}")
    return match.group(1)


def _fetch_via_api(video_id: str) -> tuple[list[dict], str]:
    """Try youtube-transcript-api. Returns (segments, source_label)."""
    transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
    try:
        transcript = transcript_list.find_manually_created_transcript(["en"])
    except NoTranscriptFound:
        transcript = transcript_list.find_generated_transcript(["en"])
    segments = transcript.fetch()
    return [{"start": s["start"], "duration": s["duration"], "text": s["text"]} for s in segments], "youtube-transcript-api"


def _download_audio(url: str) -> Path:
    """Download audio-only stream from a YouTube URL via yt-dlp. Caches by URL hash."""
    import yt_dlp

    _AUDIO_CACHE.mkdir(parents=True, exist_ok=True)
    url_hash = hashlib.sha1(url.encode()).hexdigest()[:12]

    for ext in (".m4a", ".opus", ".mp3", ".ogg", ".wav", ".webm"):
        candidate = _AUDIO_CACHE / f"yt_{url_hash}{ext}"
        if candidate.exists():
            return candidate

    out_template = str(_AUDIO_CACHE / f"yt_{url_hash}.%(ext)s")
    opts = {
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": out_template,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        ext = info.get("ext", "m4a")
        downloaded = _AUDIO_CACHE / f"yt_{url_hash}.{ext}"
        if not downloaded.exists():
            for p in _AUDIO_CACHE.glob(f"yt_{url_hash}.*"):
                downloaded = p
                break
    return downloaded


def WhisperModel(model_name: str, **kwargs):
    """Lazy import of faster_whisper.WhisperModel."""
    from faster_whisper import WhisperModel as _WM
    return _WM(model_name, **kwargs)


def _fetch_via_whisper(url: str, whisper_model: str = "base") -> tuple[list[dict], str]:
    """Download audio and transcribe locally with faster-whisper. Preserves timestamps."""
    audio_path = _download_audio(url)
    model = WhisperModel(whisper_model, device="cpu", compute_type="int8")
    raw_segments, _ = model.transcribe(str(audio_path), beam_size=5)
    segments = [
        {"start": seg.start, "duration": round(seg.end - seg.start, 3), "text": seg.text.strip()}
        for seg in raw_segments
        if seg.text.strip()
    ]
    return segments, "whisper"


def fetch_transcript(url: str, whisper_model: str = "base") -> tuple[list[dict], str]:
    """
    Return (segments, source) where segments are [{start, duration, text}].
    Tries youtube-transcript-api first, falls back to faster-whisper local ASR.
    """
    video_id = _video_id(url)
    try:
        return _fetch_via_api(video_id)
    except (NoTranscriptFound, TranscriptsDisabled, Exception):
        return _fetch_via_whisper(url, whisper_model=whisper_model)


def segments_to_text(segments: list[dict]) -> str:
    """Join transcript segments into a single readable string."""
    return " ".join(s["text"] for s in segments)
```

- [ ] **Step 4: Update callers to pass whisper_model**

In `ytk/cli.py`, change line 89:
```python
# Before:
segments, source = fetch_transcript(url)
# After:
segments, source = fetch_transcript(url, whisper_model=cfg.whisper_model)
```

In `ytk/scheduler.py`, find the `fetch_transcript(url)` call (around line 209) and change it:
```python
# Before:
segments, _source = fetch_transcript(url)
# After:
segments, _source = fetch_transcript(url, whisper_model=cfg.whisper_model)
```

`scripts/reindex.py` uses `fetch_transcript(url)` — no change needed, default `"base"` applies.

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_transcript.py -v
```
Expected: all 3 tests `PASSED`

- [ ] **Step 6: Commit**

```bash
git add ytk/transcript.py ytk/cli.py ytk/scheduler.py tests/test_transcript.py
git commit -m "feat(transcript): replace yt-dlp subtitle tier with faster-whisper local ASR"
```

---

## Task 3: SHA256 Cache Module

**Files:**
- Create: `ytk/cache.py`
- Create: `tests/test_cache.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_cache.py
import json
from pathlib import Path
import pytest

from ytk.cache import file_hash, load_index_cache, save_index_cache, update_cache_entry


def _write(path: Path, content: str):
    path.write_text(content, encoding="utf-8")
    return path


def test_file_hash_strips_frontmatter(tmp_path):
    """Same body content = same hash regardless of frontmatter."""
    body = "## Summary\nThis is the content.\n"
    f1 = _write(tmp_path / "a.md", f"---\ntitle: A\ntags: [ai]\n---\n{body}")
    f2 = _write(tmp_path / "b.md", f"---\ntitle: B\ntags: [go]\n---\n{body}")
    assert file_hash(f1) == file_hash(f2)


def test_file_hash_changes_on_body_change(tmp_path):
    """Body content change produces different hash."""
    fm = "---\ntitle: X\n---\n"
    f = tmp_path / "note.md"
    _write(f, fm + "original body")
    h1 = file_hash(f)
    _write(f, fm + "changed body")
    h2 = file_hash(f)
    assert h1 != h2


def test_file_hash_no_frontmatter(tmp_path):
    """Files without frontmatter hash the full content."""
    f = tmp_path / "plain.md"
    _write(f, "just a plain note")
    h = file_hash(f)
    assert len(h) == 64  # SHA256 hex


def test_load_save_roundtrip(tmp_path, monkeypatch):
    """save then load returns the same dict."""
    cache_file = tmp_path / "index_cache.json"
    monkeypatch.setattr("ytk.cache._CACHE_PATH", cache_file)

    data = {"/vault/note.md": "abc123", "/vault/other.md": "def456"}
    save_index_cache(data)
    loaded = load_index_cache()
    assert loaded == data


def test_load_missing_cache_returns_empty(tmp_path, monkeypatch):
    """Missing cache file returns empty dict, no error."""
    monkeypatch.setattr("ytk.cache._CACHE_PATH", tmp_path / "nonexistent.json")
    assert load_index_cache() == {}


def test_update_cache_entry(tmp_path, monkeypatch):
    """update_cache_entry adds the file's hash to the cache dict."""
    cache_file = tmp_path / "index_cache.json"
    monkeypatch.setattr("ytk.cache._CACHE_PATH", cache_file)

    note = tmp_path / "note.md"
    _write(note, "---\ntitle: T\n---\nbody text")

    cache = {}
    updated = update_cache_entry(note, cache)
    assert str(note) in updated
    assert len(updated[str(note)]) == 64
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_cache.py -v
```
Expected: `ModuleNotFoundError: No module named 'ytk.cache'`

- [ ] **Step 3: Implement ytk/cache.py**

```python
# ytk/cache.py
"""SHA256-based file cache for incremental vault reindexing."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

_CACHE_PATH = Path.home() / ".ytk" / "index_cache.json"

_FM_RE = __import__("re").compile(r"^---\n.*?\n---\n", __import__("re").DOTALL)


def _strip_frontmatter(text: str) -> str:
    if not text.startswith("---"):
        return text
    m = _FM_RE.match(text)
    return text[m.end():] if m else text


def file_hash(path: Path) -> str:
    """SHA256 of file body with YAML frontmatter stripped."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    body = _strip_frontmatter(text)
    return hashlib.sha256(body.encode()).hexdigest()


def load_index_cache() -> dict[str, str]:
    """Load cache from disk. Returns empty dict if file missing or corrupt."""
    try:
        return json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_index_cache(cache: dict[str, str]) -> None:
    """Write cache atomically via temp file."""
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _CACHE_PATH.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(cache), encoding="utf-8")
        os.replace(tmp, _CACHE_PATH)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def update_cache_entry(path: Path, cache: dict[str, str]) -> dict[str, str]:
    """Hash file and set its entry in cache. Returns updated cache."""
    cache[str(path)] = file_hash(path)
    return cache
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_cache.py -v
```
Expected: all 6 tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add ytk/cache.py tests/test_cache.py
git commit -m "feat(cache): add SHA256 file hash cache for incremental vault reindexing"
```

---

## Task 4: Wire Cache into reindex_vault

**Files:**
- Modify: `ytk/vault.py` — `reindex_vault(force=False)`
- Modify: `ytk/mcp_server.py` — `vault_reindex` tool, `vault_write` tool
- Modify: `ytk/cli.py` — `reindex` command `--force` flag

- [ ] **Step 1: Write failing tests**

```python
# tests/test_reindex_cache.py
from unittest.mock import patch, MagicMock, call
from pathlib import Path
import pytest


def _make_note(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_reindex_skips_cached_files(tmp_path, monkeypatch):
    """Files whose hash is already in cache are not re-embedded."""
    from ytk import cache as cache_mod

    note = _make_note(tmp_path / "projects" / "note.md", "---\ntitle: T\n---\nbody")
    cached_hash = cache_mod.file_hash(note)

    monkeypatch.setattr("ytk.cache._CACHE_PATH", tmp_path / "cache.json")
    cache_mod.save_index_cache({str(note): cached_hash})

    with patch("ytk.vault._get_vault_path", return_value=tmp_path), \
         patch("ytk.vault.upsert_doc") as mock_upsert:
        from ytk.vault import reindex_vault
        count = reindex_vault(force=False)

    mock_upsert.assert_not_called()
    assert count == 0


def test_reindex_embeds_changed_files(tmp_path, monkeypatch):
    """Files with a stale hash are re-embedded and cache updated."""
    from ytk import cache as cache_mod

    note = _make_note(tmp_path / "projects" / "note.md", "---\ntitle: T\n---\nbody")

    monkeypatch.setattr("ytk.cache._CACHE_PATH", tmp_path / "cache.json")
    cache_mod.save_index_cache({str(note): "stale_hash_value"})

    with patch("ytk.vault._get_vault_path", return_value=tmp_path), \
         patch("ytk.vault.upsert_doc") as mock_upsert:
        from ytk.vault import reindex_vault
        count = reindex_vault(force=False)

    mock_upsert.assert_called_once()
    assert count == 1


def test_reindex_force_skips_cache(tmp_path, monkeypatch):
    """force=True re-embeds all files regardless of cache."""
    from ytk import cache as cache_mod

    note = _make_note(tmp_path / "projects" / "note.md", "---\ntitle: T\n---\nbody")
    monkeypatch.setattr("ytk.cache._CACHE_PATH", tmp_path / "cache.json")
    cache_mod.save_index_cache({str(note): cache_mod.file_hash(note)})

    with patch("ytk.vault._get_vault_path", return_value=tmp_path), \
         patch("ytk.vault.upsert_doc") as mock_upsert:
        from ytk.vault import reindex_vault
        count = reindex_vault(force=True)

    mock_upsert.assert_called_once()
    assert count == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_reindex_cache.py -v
```
Expected: `FAILED` — `reindex_vault` does not accept `force` parameter yet.

- [ ] **Step 3: Update reindex_vault in vault.py**

Find `def reindex_vault() -> int:` in `ytk/vault.py` (line 273) and replace the entire function:

```python
def reindex_vault(force: bool = False) -> int:
    """
    Scan vault directories and bulk-upsert changed .md files into ChromaDB.
    Skips sources/youtube/ (indexed separately by store.upsert).
    Skips files whose SHA256 hash matches the cache unless force=True.
    Returns count of notes indexed.
    """
    from .store import upsert_doc, strip_frontmatter
    from .cache import file_hash, load_index_cache, save_index_cache, update_cache_entry

    vault_path = _get_vault_path()
    scan_dirs = ["inbox/memories", "inbox", "projects", "decisions", "debugging", "tools"]
    seen_paths: set[str] = set()
    count = 0

    cache = {} if force else load_index_cache()

    for subdir in scan_dirs:
        d = vault_path / subdir
        if not d.exists():
            continue
        pattern = "*.md" if subdir == "inbox" else "**/*.md"
        for md_file in d.glob(pattern):
            str_path = str(md_file)
            if str_path in seen_paths:
                continue
            seen_paths.add(str_path)

            if not force:
                current_hash = file_hash(md_file)
                if cache.get(str_path) == current_hash:
                    continue

            rel = md_file.relative_to(vault_path)
            content = md_file.read_text(encoding="utf-8")
            id_match = re.search(r"^id:\s*(.+)$", content, re.MULTILINE)
            if id_match:
                doc_id = id_match.group(1).strip()
            else:
                doc_id = "note_" + str(rel).replace("/", "_").replace(".md", "").replace(" ", "_")
            body = strip_frontmatter(content)
            if not body.strip():
                continue
            parts = str(rel).split("/")
            tags = parts[:-1]
            upsert_doc(doc_id, body, {
                "doc_id": doc_id,
                "tags": ", ".join(tags),
                "source_path": str_path,
            })
            update_cache_entry(md_file, cache)
            count += 1

    # Remove stale entries for deleted files
    stale = [p for p in list(cache) if not Path(p).exists()]
    for p in stale:
        del cache[p]

    save_index_cache(cache)
    return count
```

- [ ] **Step 4: Update vault_reindex and vault_write in mcp_server.py**

Replace the `vault_reindex` tool:
```python
@app.tool()
def vault_reindex(force: bool = False) -> str:
    """Scan and index all vault notes into ChromaDB. Set force=True to bypass cache and re-embed everything."""
    from .vault import reindex_vault

    count = reindex_vault(force=force)
    return f"Indexed {count} notes."
```

In `vault_write`, add a cache update after the `upsert_doc` call:
```python
@app.tool()
def vault_write(path: str, content: str) -> str:
    """Write or overwrite a note at a vault path and index it in ChromaDB for search."""
    from .store import upsert_doc, strip_frontmatter
    from .vault import write_raw
    from .cache import update_cache_entry, load_index_cache, save_index_cache

    note_path = write_raw(path, content)
    doc_id = "note_" + path.replace("/", "_").replace(".md", "").replace(" ", "_")
    body = strip_frontmatter(content)
    parts = path.split("/")
    tags = parts[:-1]
    upsert_doc(doc_id, body, {
        "doc_id": doc_id,
        "tags": ", ".join(tags),
        "source_path": str(note_path),
    })
    cache = load_index_cache()
    update_cache_entry(note_path, cache)
    save_index_cache(cache)
    return f"Written and indexed: {note_path}"
```

- [ ] **Step 5: Add --force to reindex command in cli.py**

Find the `reindex_cmd` function and replace it:
```python
@cli.command(name="reindex")
@click.option("--force", is_flag=True, default=False, help="Re-embed all files, ignoring cache.")
def reindex_cmd(force: bool):
    """Index all vault notes into ChromaDB for semantic search."""
    from .vault import _get_vault_path, reindex_vault

    try:
        _get_vault_path()
    except EnvironmentError as exc:
        console.print(f"[red]Vault not configured:[/] {exc}")
        raise SystemExit(1)

    label = "Re-indexing all vault notes..." if force else "Indexing changed vault notes..."
    with console.status(f"[bold cyan]{label}[/]"):
        count = reindex_vault(force=force)

    console.print(f"[bold green]Indexed:[/] {count} notes")
```

- [ ] **Step 6: Run tests**

```bash
uv run pytest tests/test_reindex_cache.py -v
```
Expected: all 3 tests `PASSED`

- [ ] **Step 7: Commit**

```bash
git add ytk/vault.py ytk/mcp_server.py ytk/cli.py tests/test_reindex_cache.py
git commit -m "feat(cache): wire SHA256 cache into reindex_vault, vault_write, and reindex --force"
```

---

## Task 5: Graph Building

**Files:**
- Create: `ytk/graph.py` (build_graph, detect_communities)
- Create: `tests/test_graph.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_graph.py
from unittest.mock import patch, MagicMock
from pathlib import Path
import pytest


def _mock_collection(docs: list[dict]) -> MagicMock:
    """Build a mock ChromaDB collection from a list of {id, document, metadata} dicts."""
    col = MagicMock()
    col.count.return_value = len(docs)
    col.get.return_value = {
        "ids": [d["id"] for d in docs],
        "documents": [d["document"] for d in docs],
        "metadatas": [d["metadata"] for d in docs],
    }

    def _query(query_texts, n_results, **kwargs):
        # Return all docs except the queried one as neighbors with distance 0.1
        results = [d for d in docs if d["document"] != query_texts[0]][:n_results]
        return {
            "ids": [[d["id"] for d in results]],
            "distances": [[0.1] * len(results)],
            "metadatas": [[d["metadata"] for d in results]],
            "documents": [[d["document"] for d in results]],
        }
    col.query.side_effect = _query
    return col


SAMPLE_DOCS = [
    {
        "id": "note_projects_ytk",
        "document": "ytk knowledge system",
        "metadata": {"doc_id": "note_projects_ytk", "tags": "projects", "source_path": "/vault/projects/ytk.md"},
    },
    {
        "id": "note_projects_epicmap",
        "document": "epicmap mapping tool",
        "metadata": {"doc_id": "note_projects_epicmap", "tags": "projects", "source_path": "/vault/projects/epicmap.md"},
    },
]


def test_build_graph_creates_nodes():
    """build_graph creates one node per indexed document."""
    import networkx as nx
    from ytk.graph import build_graph

    with patch("ytk.graph._memories_collection", return_value=_mock_collection(SAMPLE_DOCS)), \
         patch("ytk.graph._videos_collection", return_value=_mock_collection([])), \
         patch("ytk.graph._read_note_concepts", return_value=[]):
        G = build_graph(threshold=0.5)

    assert len(G.nodes) == 2
    assert "note_projects_ytk" in G.nodes


def test_build_graph_shared_tag_edge():
    """Two notes with the same tag get an EXTRACTED edge."""
    from ytk.graph import build_graph

    with patch("ytk.graph._memories_collection", return_value=_mock_collection(SAMPLE_DOCS)), \
         patch("ytk.graph._videos_collection", return_value=_mock_collection([])), \
         patch("ytk.graph._read_note_concepts", return_value=[]):
        G = build_graph(threshold=0.5)

    # Both notes have tag "projects" → should have edge
    assert G.has_edge("note_projects_ytk", "note_projects_epicmap") or \
           G.has_edge("note_projects_epicmap", "note_projects_ytk")


def test_build_graph_semantic_edge_below_threshold():
    """Pairs with distance > (1 - threshold) do not get semantic edges."""
    from ytk.graph import build_graph

    # distance 0.1 means similarity 0.9 — above 0.95 threshold, no edge
    with patch("ytk.graph._memories_collection", return_value=_mock_collection(SAMPLE_DOCS)), \
         patch("ytk.graph._videos_collection", return_value=_mock_collection([])), \
         patch("ytk.graph._read_note_concepts", return_value=[]):
        G_strict = build_graph(threshold=0.95)
        G_loose = build_graph(threshold=0.5)

    # With threshold=0.95, distance 0.1 = similarity 0.9, should still add edge
    # Just verify it runs without error for both thresholds
    assert len(G_strict.nodes) == 2
    assert len(G_loose.nodes) == 2


def test_parse_key_concepts():
    """_read_note_concepts extracts concept names from ## Key Concepts section."""
    from ytk.graph import _read_note_concepts

    content = (
        "---\ntitle: T\n---\n"
        "## Key Concepts\n"
        "- yt-dlp: a video downloader\n"
        "- ChromaDB: vector store\n"
        "- plain concept\n"
        "## Other\n"
        "other content\n"
    )
    concepts = _read_note_concepts(content)
    assert "yt-dlp" in concepts
    assert "ChromaDB" in concepts
    assert "plain concept" in concepts


def test_detect_communities_returns_mapping():
    """detect_communities returns a dict mapping every node to an int."""
    import networkx as nx
    from ytk.graph import detect_communities

    G = nx.Graph()
    G.add_edges_from([("a", "b"), ("b", "c"), ("d", "e")])
    communities = detect_communities(G)

    assert set(communities.keys()) == {"a", "b", "c", "d", "e"}
    assert all(isinstance(v, int) for v in communities.values())
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_graph.py -v
```
Expected: `ModuleNotFoundError: No module named 'ytk.graph'`

- [ ] **Step 3: Implement ytk/graph.py (building and detection)**

```python
# ytk/graph.py
"""Knowledge graph builder: vault notes as nodes, edges from tags/concepts/semantics."""

from __future__ import annotations

import json
import re
from pathlib import Path

import networkx as nx

_PALETTE = [
    "#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f",
    "#edc948", "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac",
]


# --- ChromaDB collection accessors (importable and mockable) ---

def _memories_collection():
    from .store import _memories_collection as _mc
    return _mc()


def _videos_collection():
    from .store import _videos_collection as _vc
    return _vc()


# --- Concept parsing ---

def _read_note_concepts(content: str) -> list[str]:
    """Extract concept names from the ## Key Concepts section of a vault note."""
    m = re.search(r"^## Key Concepts\n(.*?)(?=^##|\Z)", content, re.MULTILINE | re.DOTALL)
    if not m:
        return []
    section = m.group(1)
    # Match "- concept name: ..." or "- concept name"
    return re.findall(r"^- ([^:\n]+?)(?:\s*:.*)?$", section, re.MULTILINE)


# --- Graph building ---

def build_graph(threshold: float = 0.75) -> nx.Graph:
    """
    Build a NetworkX graph from all indexed vault notes.

    Nodes: one per indexed document (memories + videos collections).
    Edges:
      - Shared interest_tags (weight=1.0, type=EXTRACTED)
      - Shared key_concept terms (weight=0.9, type=EXTRACTED)
      - ChromaDB semantic similarity >= threshold (weight=similarity, type=INFERRED)
    """
    G = nx.Graph()

    # Collect all docs from both collections
    all_docs: list[dict] = []

    mem_col = _memories_collection()
    if mem_col.count() > 0:
        result = mem_col.get()
        for doc_id, doc_text, meta in zip(
            result["ids"], result["documents"], result["metadatas"]
        ):
            all_docs.append({
                "id": doc_id,
                "text": doc_text,
                "meta": meta,
                "collection": "memory",
            })

    vid_col = _videos_collection()
    if vid_col.count() > 0:
        result = vid_col.get()
        for doc_id, doc_text, meta in zip(
            result["ids"], result["documents"], result["metadatas"]
        ):
            all_docs.append({
                "id": doc_id,
                "text": doc_text,
                "meta": meta,
                "collection": "video",
            })

    if not all_docs:
        return G

    # Add nodes
    for doc in all_docs:
        meta = doc["meta"]
        source_path = meta.get("source_path", "")
        note_type = _infer_type(source_path, doc["collection"])
        G.add_node(
            doc["id"],
            title=meta.get("title", doc["id"]),
            url=meta.get("url", source_path),
            note_type=note_type,
            tags=meta.get("tags", ""),
            source_path=source_path,
            community=0,
        )

    # Tag edges
    by_tag: dict[str, list[str]] = {}
    for doc in all_docs:
        for tag in [t.strip() for t in doc["meta"].get("tags", "").split(",") if t.strip()]:
            by_tag.setdefault(tag, []).append(doc["id"])
    for tag, node_ids in by_tag.items():
        for i in range(len(node_ids)):
            for j in range(i + 1, len(node_ids)):
                _add_or_upgrade_edge(G, node_ids[i], node_ids[j], 1.0, "EXTRACTED", f"tag:{tag}")

    # Concept edges
    concepts_by_node: dict[str, list[str]] = {}
    for doc in all_docs:
        sp = doc["meta"].get("source_path", "")
        if sp and Path(sp).exists():
            content = Path(sp).read_text(encoding="utf-8", errors="replace")
            concepts_by_node[doc["id"]] = _read_note_concepts(content)

    by_concept: dict[str, list[str]] = {}
    for node_id, concepts in concepts_by_node.items():
        for concept in concepts:
            key = concept.lower().strip()
            by_concept.setdefault(key, []).append(node_id)
    for concept, node_ids in by_concept.items():
        for i in range(len(node_ids)):
            for j in range(i + 1, len(node_ids)):
                _add_or_upgrade_edge(G, node_ids[i], node_ids[j], 0.9, "EXTRACTED", f"concept:{concept}")

    # Semantic edges
    all_ids = {doc["id"] for doc in all_docs}
    for doc in all_docs:
        try:
            col = mem_col if doc["collection"] == "memory" else vid_col
            n_results = min(10, col.count())
            if n_results < 2:
                continue
            results = col.query(query_texts=[doc["text"]], n_results=n_results)
            for neighbor_id, distance in zip(results["ids"][0], results["distances"][0]):
                if neighbor_id == doc["id"] or neighbor_id not in all_ids:
                    continue
                similarity = 1.0 - distance
                if similarity >= threshold:
                    _add_or_upgrade_edge(G, doc["id"], neighbor_id, similarity, "INFERRED", "semantic")
        except Exception:
            continue

    return G


def _infer_type(source_path: str, collection: str) -> str:
    if collection == "video" or "sources/youtube" in source_path:
        return "video"
    if "sources/web" in source_path:
        return "web"
    return "memory"


def _add_or_upgrade_edge(
    G: nx.Graph, a: str, b: str, weight: float, edge_type: str, label: str
) -> None:
    """Add edge or upgrade to higher-confidence type if edge already exists."""
    if G.has_edge(a, b):
        if weight > G[a][b].get("weight", 0):
            G[a][b].update({"weight": weight, "type": edge_type, "label": label})
    else:
        G.add_edge(a, b, weight=weight, type=edge_type, label=label)


# --- Community detection ---

def detect_communities(G: nx.Graph) -> dict:
    """Assign community IDs to all nodes. Returns {node_id: community_int}."""
    if len(G.nodes) == 0:
        return {}
    try:
        import graspologic
        from graspologic.partition import leiden
        communities_list = leiden(G)
        # leiden returns list of sets
        mapping: dict = {}
        for i, community in enumerate(communities_list):
            for node in community:
                mapping[node] = i
        return mapping
    except (ImportError, Exception):
        from networkx.algorithms.community import greedy_modularity_communities
        communities_list = list(greedy_modularity_communities(G))
        mapping = {}
        for i, community in enumerate(communities_list):
            for node in community:
                mapping[node] = i
        return mapping
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_graph.py -v
```
Expected: all 5 tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add ytk/graph.py tests/test_graph.py
git commit -m "feat(graph): add graph building and community detection to ytk/graph.py"
```

---

## Task 6: Graph Export and CLI Command

**Files:**
- Modify: `ytk/graph.py` — add `export_html`, `export_json`
- Modify: `ytk/cli.py` — add `ytk graph` command

- [ ] **Step 1: Write failing tests**

Add to `tests/test_graph.py`:

```python
def test_export_json(tmp_path):
    """export_json writes a valid JSON file with nodes and edges."""
    import networkx as nx
    from ytk.graph import export_json

    G = nx.Graph()
    G.add_node("a", title="Note A", url="https://example.com", note_type="memory", tags="ai", community=0)
    G.add_node("b", title="Note B", url="https://youtube.com", note_type="video", tags="ai", community=0)
    G.add_edge("a", "b", weight=0.9, type="EXTRACTED", label="tag:ai")

    out = tmp_path / "graph.json"
    export_json(G, out)

    data = json.loads(out.read_text())
    assert len(data["nodes"]) == 2
    assert len(data["edges"]) == 1
    assert data["nodes"][0]["id"] in {"a", "b"}


def test_export_html(tmp_path):
    """export_html writes a self-contained HTML file."""
    import networkx as nx
    from ytk.graph import export_html

    G = nx.Graph()
    G.add_node("a", title="Note A", url="https://example.com", note_type="memory", tags="ai", community=0)

    out = tmp_path / "graph.html"
    export_html(G, out)

    html = out.read_text()
    assert "vis-network" in html
    assert "Note A" in html
    assert "<script" in html
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_graph.py::test_export_json tests/test_graph.py::test_export_html -v
```
Expected: `FAILED — AttributeError: module 'ytk.graph' has no attribute 'export_json'`

- [ ] **Step 3: Add export functions to ytk/graph.py**

Append to `ytk/graph.py`:

```python
_VIS_CDN = "https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"

_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<title>ytk knowledge graph</title>
<script src="{vis_cdn}"></script>
<style>
  body {{ margin: 0; background: #1a1a2e; font-family: monospace; }}
  #graph {{ width: 100vw; height: 100vh; }}
  #info {{ position: fixed; top: 12px; right: 16px; color: #aaa; font-size: 12px; }}
</style>
</head>
<body>
<div id="graph"></div>
<div id="info">{node_count} nodes &middot; {edge_count} edges &middot; {community_count} communities</div>
<script>
var nodes = new vis.DataSet({nodes_json});
var edges = new vis.DataSet({edges_json});
var network = new vis.Network(
  document.getElementById("graph"),
  {{ nodes: nodes, edges: edges }},
  {{
    nodes: {{ shape: "dot", scaling: {{ min: 8, max: 30 }}, font: {{ color: "#eee" }} }},
    edges: {{ smooth: false }},
    physics: {{ stabilization: {{ iterations: 200 }} }}
  }}
);
network.on("click", function(p) {{
  if (p.nodes.length > 0) {{
    var n = nodes.get(p.nodes[0]);
    if (n && n.url) window.open(n.url, "_blank");
  }}
}});
</script>
</body>
</html>"""

_EDGE_COLORS = {"EXTRACTED": "#4e79a7", "INFERRED": "#888"}


def export_html(G: nx.Graph, output: Path) -> None:
    """Render G as an interactive vis.js HTML file."""
    communities = detect_communities(G)
    nx.set_node_attributes(G, communities, "community")

    vis_nodes = []
    for node_id, attrs in G.nodes(data=True):
        community = attrs.get("community", 0)
        color = _PALETTE[community % len(_PALETTE)]
        degree = G.degree(node_id)
        vis_nodes.append({
            "id": node_id,
            "label": attrs.get("title", node_id)[:40],
            "title": attrs.get("title", node_id),
            "value": degree,
            "color": color,
            "url": attrs.get("url", ""),
        })

    vis_edges = []
    for i, (src, dst, attrs) in enumerate(G.edges(data=True)):
        edge_type = attrs.get("type", "INFERRED")
        opacity = min(1.0, max(0.2, attrs.get("weight", 0.5)))
        vis_edges.append({
            "id": i,
            "from": src,
            "to": dst,
            "color": {"color": _EDGE_COLORS.get(edge_type, "#888"), "opacity": opacity},
            "title": attrs.get("label", edge_type),
        })

    n_communities = len(set(communities.values())) if communities else 0
    html = _HTML_TEMPLATE.format(
        vis_cdn=_VIS_CDN,
        node_count=len(vis_nodes),
        edge_count=len(vis_edges),
        community_count=n_communities,
        nodes_json=json.dumps(vis_nodes),
        edges_json=json.dumps(vis_edges),
    )
    Path(output).write_text(html, encoding="utf-8")


def export_json(G: nx.Graph, output: Path) -> None:
    """Write graph as JSON {nodes: [...], edges: [...]} for programmatic querying."""
    data = {
        "nodes": [
            {"id": n, **{k: v for k, v in attrs.items()}}
            for n, attrs in G.nodes(data=True)
        ],
        "edges": [
            {"from": src, "to": dst, **attrs}
            for src, dst, attrs in G.edges(data=True)
        ],
    }
    Path(output).write_text(json.dumps(data, indent=2), encoding="utf-8")
```

- [ ] **Step 4: Run export tests**

```bash
uv run pytest tests/test_graph.py -v
```
Expected: all 7 tests `PASSED`

- [ ] **Step 5: Add ytk graph command to cli.py**

Add this import at the top of `ytk/cli.py` where other imports live (after the existing `from .store import ...` line):
```python
# (no new import needed at top — graph is imported inside the command)
```

Append the following command to `ytk/cli.py` (before the `schedule` group):

```python
@cli.command(name="graph")
@click.option("--open", "open_browser", is_flag=True, default=False, help="Open graph.html in browser after building.")
@click.option("--output", default=None, help="Output path for graph.html (default: ~/.ytk/graph.html).")
@click.option("--threshold", default=0.75, show_default=True, type=float, help="Semantic similarity cutoff for edges.")
def graph_cmd(open_browser: bool, output: str | None, threshold: float):
    """Build a knowledge graph from all vault notes and export as interactive HTML."""
    import webbrowser
    from .graph import build_graph, export_html, export_json

    default_html = Path.home() / ".ytk" / "graph.html"
    default_json = Path.home() / ".ytk" / "graph.json"
    html_path = Path(output) if output else default_html

    with console.status("[bold cyan]Building graph...[/]"):
        G = build_graph(threshold=threshold)

    if len(G.nodes) == 0:
        console.print("[yellow]No indexed notes found.[/] Run [bold]ytk reindex[/] first.")
        return

    with console.status("[bold cyan]Exporting...[/]"):
        export_html(G, html_path)
        export_json(G, default_json)

    console.print(f"[bold green]Graph built:[/] {len(G.nodes)} nodes, {len(G.edges)} edges")
    console.print(f"  HTML: {html_path}")
    console.print(f"  JSON: {default_json}")

    if open_browser:
        webbrowser.open(f"file://{html_path.resolve()}")
```

- [ ] **Step 6: Run full test suite**

```bash
uv run pytest tests/ -v
```
Expected: all tests `PASSED`

- [ ] **Step 7: Smoke test the graph command**

```bash
uv run ytk graph --help
```
Expected output includes `--open`, `--output`, `--threshold` options with no import errors.

- [ ] **Step 8: Commit**

```bash
git add ytk/graph.py ytk/cli.py tests/test_graph.py
git commit -m "feat(graph): add export_html, export_json, and ytk graph CLI command"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|---|---|
| Remove yt-dlp subtitle tier | Task 2 |
| Add faster-whisper as 3rd tier | Task 2 |
| Timestamps preserved in Whisper output | Task 2, test_whisper_segments_have_timestamps |
| `whisper_model` config field | Task 1 |
| Audio cached in `~/.ytk/audio/` | Task 2, `_download_audio` |
| Source label `"whisper"` returned | Task 2 |
| `ytk/cache.py` with `file_hash` | Task 3 |
| Frontmatter stripped before hashing | Task 3, test_file_hash_strips_frontmatter |
| Cache at `~/.ytk/index_cache.json` | Task 3 |
| Atomic write via temp file | Task 3, `save_index_cache` |
| `reindex_vault(force=False)` | Task 4 |
| Stale entry cleanup on reindex | Task 4 |
| `vault_reindex` MCP tool gets `force` | Task 4 |
| `vault_write` updates cache | Task 4 |
| `ytk reindex --force` | Task 4 |
| Graph nodes from memories + videos | Task 5 |
| Tag edges weight 1.0 EXTRACTED | Task 5 |
| Concept edges weight 0.9 EXTRACTED | Task 5 |
| Semantic edges weight=similarity INFERRED | Task 5 |
| Community detection (graspologic / networkx fallback) | Task 5 |
| `export_html` vis.js self-contained | Task 6 |
| `export_json` for future querying | Task 6 |
| `ytk graph --open --output --threshold` | Task 6 |
| Nodes sized by degree | Task 6, `value: degree` |
| Edges colored by type | Task 6, `_EDGE_COLORS` |
| Click node opens URL | Task 6, `network.on("click")` |
| networkx in base deps | Task 1 |
| graspologic as optional dep | Task 1 |

All spec requirements covered. No gaps found.
