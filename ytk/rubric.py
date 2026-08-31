"""The grading rubric (#197 P4): owner-written prose at ~/.ytk/rubric.md.

The grader's model layer reads it; the enricher never does. Versioned by
content hash so every grade activity row names the version it was judged
under. A wrong bounce is fixed by editing the file, never a prompt in code.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Rubric:
    text: str
    hash: str


def rubric_path() -> Path:
    env = os.environ.get("YTK_RUBRIC")
    return Path(env) if env else Path.home() / ".ytk" / "rubric.md"


def load() -> Rubric:
    """Read the rubric; FileNotFoundError stays loud — grading against an
    absent rubric would silently judge by nothing."""
    path = rubric_path()
    text = path.read_text(encoding="utf-8")
    digest = hashlib.sha256(text.encode()).hexdigest()[:12]
    return Rubric(text=text, hash=digest)
