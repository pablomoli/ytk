"""Obsidian note writer for ingested YouTube videos and generic vault operations."""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from ytk.enrich import Enrichment

load_dotenv()


class NoteAlreadyExists(Exception):
    """Raised when a note for the given video ID already exists in the vault."""


def _get_vault_path() -> Path:
    raw = os.getenv("OBSIDIAN_VAULT_PATH")
    if not raw:
        raise EnvironmentError(
            "OBSIDIAN_VAULT_PATH is not set. Add it to your .env file."
        )
    return Path(raw).expanduser()


def _fmt_duration(seconds: int) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _fmt_date(yyyymmdd: str) -> str:
    """Convert YYYYMMDD to YYYY-MM-DD."""
    d = yyyymmdd.strip()
    if len(d) == 8 and d.isdigit():
        return f"{d[:4]}-{d[4:6]}-{d[6:]}"
    return d


def _slug(title: str) -> str:
    """Sanitize a video title into a safe filename (max 100 chars)."""
    sanitized = re.sub(r'[\\/*?:"<>|]', "", title)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    return sanitized[:100]


def _build_transcript(video_id: str, segments: list[dict]) -> str:
    """
    Format transcript segments into timestamped blocks grouped by ~60-second windows.
    Each block opens with a clickable YouTube timestamp link.
    """
    if not segments:
        return "_No transcript available._"

    lines: list[str] = []
    block_texts: list[str] = []
    block_start: float = segments[0]["start"]
    window = 60.0

    def _ts_link(start: float) -> str:
        h, rem = divmod(int(start), 3600)
        m, s = divmod(rem, 60)
        label = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
        return f"[{label}](https://youtu.be/{video_id}?t={int(start)})"

    for seg in segments:
        if seg["start"] - block_start >= window and block_texts:
            lines.append(f"{_ts_link(block_start)} {' '.join(block_texts)}")
            block_texts = []
            block_start = seg["start"]
        block_texts.append(seg["text"])

    if block_texts:
        lines.append(f"{_ts_link(block_start)} {' '.join(block_texts)}")

    return "\n\n".join(lines)


def _build_note(meta: dict, enrichment: Enrichment, segments: list[dict]) -> str:
    date = _fmt_date(meta.get("upload_date", ""))
    duration = _fmt_duration(meta.get("duration", 0))
    video_id: str = meta.get("id", "")

    def _normalize_tag(t: str) -> str:
        return re.sub(r"\s+", "-", t.strip().lower())

    tags_yaml = "\n".join(f"  - {_normalize_tag(t)}" for t in enrichment.interest_tags)

    concepts = "\n".join(f"- {c}" for c in enrichment.key_concepts)
    insights = "\n".join(f"- {i}" for i in enrichment.insights)
    moments = "\n".join(
        f"- **{km.timestamp}** — {km.description}" for km in enrichment.key_moments
    )
    transcript_body = _build_transcript(video_id, segments)

    return f"""\
---
url: {meta.get("url", "")}
title: {meta.get("title", "")}
uploader: {meta.get("uploader", "")}
date: {date}
tags:
{tags_yaml}
duration: {duration}
---

## Thesis
{enrichment.thesis}

## Commentary
{enrichment.summary}

## Key Concepts
{concepts}

## Insights
{insights}

## Key Moments
{moments}

## Transcript
<details>
<summary>Raw transcript</summary>

{transcript_body}
</details>
"""


def _update_index(vault_path: Path, video_id: str, title: str, date: str) -> None:
    """Append a row to the sources/youtube/ table in wiki/index.md."""
    index_path = vault_path / "wiki" / "index.md"
    if not index_path.exists():
        return

    content = index_path.read_text(encoding="utf-8")

    row = f"| [[sources/youtube/{video_id}]] | {title} | {date} |"

    table_header = "## sources/youtube/"

    # Table already has a markdown table — just append a row.
    header_re = re.compile(
        r"(## sources/youtube/\n\|[^\n]+\|\n\|[-| ]+\|\n)((?:\|[^\n]+\|\n)*)",
        re.MULTILINE,
    )
    match = header_re.search(content)
    if match:
        # Insert the new row after all existing rows.
        insert_at = match.end()
        new_content = content[:insert_at] + row + "\n" + content[insert_at:]
        index_path.write_text(new_content, encoding="utf-8")
        return

    # Placeholder block: replace the prose line under the heading.
    placeholder_re = re.compile(
        r"(## sources/youtube/\n)(.*?\n)",
        re.MULTILINE | re.DOTALL,
    )
    placeholder_match = placeholder_re.search(content)
    if placeholder_match:
        new_table = (
            "## sources/youtube/\n"
            "| Note | Title | Date |\n"
            "|------|-------|------|\n"
            f"{row}\n"
        )
        new_content = (
            content[: placeholder_match.start()]
            + new_table
            + content[placeholder_match.end() :]
        )
        index_path.write_text(new_content, encoding="utf-8")
        return

    # Section not found — append it at the end of the file.
    new_section = (
        "\n## sources/youtube/\n"
        "| Note | Title | Date |\n"
        "|------|-------|------|\n"
        f"{row}\n"
    )
    index_path.write_text(content.rstrip() + "\n" + new_section, encoding="utf-8")


def read_note(rel_path: str) -> str:
    """Read any vault note by relative path from vault root."""
    vault_path = _get_vault_path()
    note_path = (vault_path / rel_path).resolve()
    if not str(note_path).startswith(str(vault_path.resolve())):
        raise ValueError(f"Path escapes vault root: {rel_path}")
    if not note_path.exists():
        raise FileNotFoundError(f"Note not found: {rel_path}")
    return note_path.read_text(encoding="utf-8")


def list_index() -> str:
    """Return the contents of wiki/index.md."""
    vault_path = _get_vault_path()
    index_path = vault_path / "wiki" / "index.md"
    if not index_path.exists():
        return "_wiki/index.md not found._"
    return index_path.read_text(encoding="utf-8")


def write_raw(rel_path: str, content: str) -> Path:
    """Write or overwrite any note at rel_path (relative to vault root)."""
    vault_path = _get_vault_path()
    note_path = (vault_path / rel_path).resolve()
    if not str(note_path).startswith(str(vault_path.resolve())):
        raise ValueError(f"Path escapes vault root: {rel_path}")
    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text(content, encoding="utf-8")
    return note_path


def remember(text: str, tags: list[str] | None = None) -> tuple[Path, str]:
    """
    Create an atomic memory note in inbox/memories/ and return (path, doc_id).
    The caller is responsible for upserting the doc_id + text to ChromaDB.
    """
    vault_path = _get_vault_path()
    tags = tags or []
    date_str = datetime.now().strftime("%Y-%m-%d")
    slug = re.sub(r"[^a-z0-9]+", "-", text[:50].lower()).strip("-")
    filename = f"{date_str}-{slug}.md"

    note_dir = vault_path / "inbox" / "memories"
    note_dir.mkdir(parents=True, exist_ok=True)
    note_path = note_dir / filename

    tags_yaml = "\n".join(f"  - {t}" for t in tags) if tags else ""
    doc_id = f"memory_{date_str}_{slug}"
    note_path.write_text(
        f"---\nid: {doc_id}\ndate: {date_str}\ntags:\n{tags_yaml}\ntype: memory\n---\n\n{text}\n",
        encoding="utf-8",
    )
    return note_path, doc_id


def write_web_note(url: str, title: str, author: str, date: str, enrichment: Enrichment) -> Path:
    """Write an Obsidian note for an ingested web article. Returns the path written."""
    vault_path = _get_vault_path()
    note_dir = vault_path / "sources" / "web"
    note_dir.mkdir(parents=True, exist_ok=True)

    filename = _slug(title)
    note_path = note_dir / f"{filename}.md"

    def _normalize_tag(t: str) -> str:
        return re.sub(r"\s+", "-", t.strip().lower())

    tags_yaml = "\n".join(f"  - {_normalize_tag(t)}" for t in enrichment.interest_tags)
    concepts = "\n".join(f"- {c}" for c in enrichment.key_concepts)
    insights = "\n".join(f"- {i}" for i in enrichment.insights)

    note_path.write_text(
        f"---\nurl: {url}\ntitle: {title}\nauthor: {author}\ndate: {date}\ntags:\n{tags_yaml}\ntype: web\n---\n\n"
        f"## Thesis\n{enrichment.thesis}\n\n"
        f"## Summary\n{enrichment.summary}\n\n"
        f"## Key Concepts\n{concepts}\n\n"
        f"## Insights\n{insights}\n",
        encoding="utf-8",
    )
    return note_path


def reindex_vault() -> int:
    """
    Scan vault directories and bulk-upsert all .md files into ChromaDB.
    Skips sources/youtube/ (indexed separately by store.upsert).
    Returns count of notes indexed.
    """
    from .store import upsert_doc, strip_frontmatter

    vault_path = _get_vault_path()
    scan_dirs = ["inbox/memories", "inbox", "projects", "decisions", "debugging", "tools"]
    seen_paths: set[str] = set()
    count = 0

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
            rel = md_file.relative_to(vault_path)
            doc_id = "note_" + str(rel).replace("/", "_").replace(".md", "").replace(" ", "_")
            content = md_file.read_text(encoding="utf-8")
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
            count += 1

    return count


def rebuild_index() -> None:
    """Scan the vault and rewrite wiki/index.md from scratch."""
    vault_path = _get_vault_path()
    index_path = vault_path / "wiki" / "index.md"
    index_path.parent.mkdir(parents=True, exist_ok=True)

    sections: list[str] = ["# Vault Index\n"]

    def _md_files(subdir: str) -> list[Path]:
        d = vault_path / subdir
        if not d.exists():
            return []
        return sorted(d.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)

    # wiki/
    wiki_files = _md_files("wiki")
    if wiki_files:
        rows = "\n".join(f"- [[wiki/{p.stem}]]" for p in wiki_files if p.stem != "index")
        sections.append(f"## wiki/\n{rows}\n")

    # projects/ — grouped by subdirectory
    projects_dir = vault_path / "projects"
    if projects_dir.exists():
        project_rows: list[str] = []
        for proj in sorted(projects_dir.iterdir()):
            if proj.is_dir():
                briefs = sorted(proj.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
                for b in briefs:
                    project_rows.append(f"- [[projects/{proj.name}/{b.stem}]]")
        if project_rows:
            sections.append("## projects/\n" + "\n".join(project_rows) + "\n")

    # sources/youtube/ — table, deduplicated by stem (video title slug)
    youtube_dir = vault_path / "sources" / "youtube"
    if youtube_dir.exists():
        notes = sorted(youtube_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        seen: set[str] = set()
        rows: list[str] = []
        for p in notes:
            if p.stem not in seen:
                seen.add(p.stem)
                rows.append(f"| [[sources/youtube/{p.stem}]] | {p.stem} |")
        if rows:
            table = "| Note | Title |\n|------|-------|\n" + "\n".join(rows)
            sections.append(f"## sources/youtube/\n{table}\n")

    # inbox/
    inbox_dir = vault_path / "inbox"
    if inbox_dir.exists():
        inbox_files = [
            p for p in sorted(inbox_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        ]
        memory_files = sorted(
            (inbox_dir / "memories").glob("*.md") if (inbox_dir / "memories").exists() else [],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        rows = [f"- [[inbox/{p.stem}]]" for p in inbox_files]
        rows += [f"- [[inbox/memories/{p.stem}]]" for p in memory_files]
        if rows:
            sections.append("## inbox/\n" + "\n".join(rows) + "\n")

    for subdir in ("decisions", "debugging", "tools"):
        files = _md_files(subdir)
        if files:
            rows = "\n".join(f"- [[{subdir}/{p.stem}]]" for p in files)
            sections.append(f"## {subdir}/\n{rows}\n")

    index_path.write_text("\n".join(sections), encoding="utf-8")


def write_note(meta: dict, enrichment: Enrichment, segments: list[dict]) -> Path:
    """
    Write an Obsidian note for a video. Returns the path written.
    Raises NoteAlreadyExists if the note already exists.
    segments: raw transcript segments [{start, duration, text}] for timestamped linking.
    """
    vault_path = _get_vault_path()
    video_id: str = meta["id"]
    title: str = meta.get("title", video_id)
    note_dir = vault_path / "sources" / "youtube"
    note_dir.mkdir(parents=True, exist_ok=True)

    filename = _slug(title)
    note_path = note_dir / f"{filename}.md"
    if note_path.exists():
        raise NoteAlreadyExists(
            f"Note already exists for '{title}': {note_path}"
        )

    note_content = _build_note(meta, enrichment, segments)
    note_path.write_text(note_content, encoding="utf-8")

    date = _fmt_date(meta.get("upload_date", ""))
    _update_index(vault_path, filename, title, date)

    return note_path
