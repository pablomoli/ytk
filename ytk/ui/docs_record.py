"""The docs/assets experiment record, parsed for the hub's /docs route.

The record is 136MB of figures and cannot ride in the wheel, so the
installed hub serves it from the repo checkout: YTK_REPO_PATH when set,
else the source tree this module was imported from (dev checkout).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import TypedDict


class SectionFile(TypedDict):
    name: str
    kind: str
    size: int


class SectionSummary(TypedDict):
    id: str
    num: int
    title: str
    deck: str
    cover: str | None
    figures: int
    hasVideo: bool


class Section(TypedDict):
    id: str
    readme: str
    files: list[SectionFile]


_SECTION_RE = re.compile(r"^(\d{2})-([a-z0-9-]+)$")
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
_VIDEO_EXTS = {".mp4", ".webm", ".mov"}
# **bold**, *italic*, `code`, [label](url) -> plain text, for deck lines only
_INLINE_MD_RE = re.compile(r"\*\*(.+?)\*\*|\*([^*\n]+)\*|`([^`]+)`|\[([^\]]+)\]\([^)]*\)")


def _source_root() -> Path:
    return Path(__file__).resolve().parents[2]


def assets_root() -> Path | None:
    """Where docs/assets lives, or None if the record is not reachable."""
    candidates: list[Path] = []
    env = os.environ.get("YTK_REPO_PATH", "").strip()
    if env:
        candidates.append(Path(env).expanduser())
    candidates.append(_source_root())
    for repo in candidates:
        root = repo / "docs" / "assets"
        if (root / "README.md").is_file():
            return root
    return None


def _strip_inline_md(text: str) -> str:
    return _INLINE_MD_RE.sub(lambda m: next(g for g in m.groups() if g is not None), text)


def _parse_readme_head(md: str) -> tuple[str, str]:
    """(title, deck): the H1 and the first plain paragraph after it."""
    title = ""
    deck_lines: list[str] = []
    for line in md.splitlines():
        stripped = line.strip()
        if not title:
            if stripped.startswith("# "):
                title = stripped[2:].strip()
            continue
        if deck_lines and not stripped:
            break
        # decks are prose: skip structure that can precede the first paragraph
        if not stripped or stripped.startswith(("#", ">", "|", "```", "![", "---")):
            if deck_lines:
                break
            continue
        deck_lines.append(stripped)
    return title, _strip_inline_md(" ".join(deck_lines))


def _file_kind(name: str) -> str | None:
    ext = Path(name).suffix.lower()
    if ext in _IMAGE_EXTS:
        return "image"
    if ext in _VIDEO_EXTS:
        return "video"
    if ext in {".json", ".csv"}:
        return "data"
    return None


def _section_files(section_dir: Path) -> list[SectionFile]:
    files: list[SectionFile] = []
    for p in sorted(section_dir.iterdir()):
        kind = _file_kind(p.name) if p.is_file() else None
        if kind:
            files.append({"name": p.name, "kind": kind, "size": p.stat().st_size})
    return files


def build_manifest(root: Path) -> list[SectionSummary]:
    """One entry per numbered section, newest first; unreadable dirs skipped."""
    sections: list[SectionSummary] = []
    for d in root.iterdir():
        m = _SECTION_RE.match(d.name)
        if not m or not d.is_dir():
            continue
        readme = d / "README.md"
        if not readme.is_file():
            continue
        title, deck = _parse_readme_head(readme.read_text(encoding="utf-8"))
        if not title:
            continue
        files = _section_files(d)
        images = [f["name"] for f in files if f["kind"] == "image"]
        sections.append(
            {
                "id": d.name,
                "num": int(m.group(1)),
                "title": title,
                "deck": deck,
                "cover": f"{d.name}/{images[0]}" if images else None,
                "figures": len(images),
                "hasVideo": any(f["kind"] == "video" for f in files),
            }
        )
    return sorted(sections, key=lambda s: s["num"], reverse=True)


def read_section(root: Path, section_id: str) -> Section | None:
    if not _SECTION_RE.match(section_id):
        return None
    readme = root / section_id / "README.md"
    if not readme.is_file():
        return None
    return {
        "id": section_id,
        "readme": readme.read_text(encoding="utf-8"),
        "files": _section_files(root / section_id),
    }


def resolve_media(root: Path, rel_path: str) -> Path | None:
    """A file inside the record, or None — never a path outside it."""
    target = (root / rel_path).resolve()
    if not target.is_relative_to(root.resolve()) or not target.is_file():
        return None
    return target
