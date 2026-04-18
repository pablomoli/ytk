"""SHA256-based file cache for incremental vault reindexing."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

_CACHE_PATH = Path.home() / ".ytk" / "index_cache.json"

_FM_RE = re.compile(r"^---\n.*?\n---\n", re.DOTALL)


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
