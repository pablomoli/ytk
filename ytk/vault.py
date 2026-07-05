"""Obsidian note writer for ingested YouTube videos and generic vault operations."""

from __future__ import annotations

import hashlib
import os
import re
import urllib.request
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

from typing import TYPE_CHECKING

from ytk.enrich import Enrichment
from ytk.store import upsert_doc, strip_frontmatter

if TYPE_CHECKING:
    from ytk.instagram import InstagramPost
    from ytk.imessage import MessageThread
    from ytk.tiktok import TikTokPost

load_dotenv(Path.home() / ".ytk" / ".env")
load_dotenv()


LINK_REMINDER = "Add [[wikilinks]] in Obsidian to connect this note to related notes."


class NoteAlreadyExists(Exception):
    """Raised when a note for the given video ID already exists in the vault."""


def _get_vault_path() -> Path:
    raw = os.getenv("OBSIDIAN_VAULT_PATH")
    if not raw:
        raise EnvironmentError(
            "OBSIDIAN_VAULT_PATH is not set. Add it to your .env file."
        )
    return Path(raw).expanduser()


def _get_brain_path() -> Path:
    """Return the second-brain subtree root inside the Obsidian vault."""
    return _get_vault_path() / "second-brain"


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
    """Normalize a title into a lowercase-hyphenated filename slug (max 80 chars)."""
    # strip non-ASCII (emoji, accented chars, etc.)
    ascii_only = title.encode("ascii", "ignore").decode()
    # drop chars that are illegal in filenames
    cleaned = re.sub(r'[\\/*?:"<>|]', "", ascii_only)
    # collapse whitespace/punctuation runs into hyphens
    hyphenated = re.sub(r"[^a-zA-Z0-9]+", "-", cleaned).strip("-").lower()
    return hyphenated[:80]


def _normalize_tag(t: str) -> str:
    """Normalize a tag to lowercase-hyphenated form, then resolve aliases."""
    from .config import tag_aliases

    t = re.sub(r"\s+", "-", t.strip().lower())
    return tag_aliases().get(t, t)


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


def _build_note(
    meta: dict,
    enrichment: Enrichment,
    segments: list[dict],
    saved_frames: list[Path] | None = None,
) -> str:
    date = _fmt_date(meta.get("upload_date", ""))
    duration = _fmt_duration(meta.get("duration", 0))
    video_id: str = meta.get("id", "")

    tags_yaml = "\n".join(f"  - {_normalize_tag(t)}" for t in enrichment.interest_tags)
    image_paths_yaml = (
        "\n" + "\n".join(f"  - {p.relative_to(_get_brain_path())}" for p in saved_frames)
        if saved_frames else " []"
    )

    concepts = "\n".join(f"- {c}" for c in enrichment.key_concepts)
    insights = "\n".join(f"- {i}" for i in enrichment.insights)
    moments = "\n".join(
        f"- **{km.timestamp}** — {km.description}" for km in enrichment.key_moments
    )
    transcript_body = _build_transcript(video_id, segments)

    frame_embeds = (
        "\n".join(f"![[{p.name}]]" for p in saved_frames) + "\n\n"
        if saved_frames else ""
    )

    return f"""\
---
url: {meta.get("url", "")}
title: {meta.get("title", "")}
uploader: {meta.get("uploader", "")}
date: {date}
tags:
{tags_yaml}
duration: {duration}
image_paths:{image_paths_yaml}
---

{frame_embeds}## Thesis
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
    if not note_path.is_relative_to(vault_path.resolve()):
        raise ValueError(f"Path escapes vault root: {rel_path}")
    if not note_path.exists():
        raise FileNotFoundError(f"Note not found: {rel_path}")
    return note_path.read_text(encoding="utf-8")


def list_index() -> str:
    """Return the contents of wiki/index.md."""
    index_path = _get_brain_path() / "wiki" / "index.md"
    if not index_path.exists():
        return "_wiki/index.md not found._"
    return index_path.read_text(encoding="utf-8")


def write_raw(rel_path: str, content: str) -> Path:
    """Write or overwrite any note at rel_path (relative to vault root)."""
    vault_path = _get_vault_path()
    note_path = (vault_path / rel_path).resolve()
    if not note_path.is_relative_to(vault_path.resolve()):
        raise ValueError(f"Path escapes vault root: {rel_path}")
    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text(content, encoding="utf-8")
    return note_path


def remember(text: str, tags: list[str] | None = None) -> tuple[Path, str]:
    """
    Create an atomic memory note in inbox/memories/ and return (path, doc_id).
    The caller is responsible for upserting the doc_id + text to ChromaDB.
    """
    tags = tags or []
    date_str = datetime.now().strftime("%Y-%m-%d")
    slug = re.sub(r"[^a-z0-9]+", "-", text[:50].lower()).strip("-")
    text_hash = hashlib.sha1(text.encode("utf-8")).hexdigest()[:6]
    filename = f"{date_str}-{slug}-{text_hash}.md"

    note_dir = _get_brain_path() / "inbox" / "memories"
    note_dir.mkdir(parents=True, exist_ok=True)
    note_path = note_dir / filename

    tags_yaml = "\n".join(f"  - {t}" for t in tags) if tags else ""
    doc_id = f"memory_{date_str}_{slug}_{text_hash}"
    note_path.write_text(
        f"---\nid: {doc_id}\ndate: {date_str}\ntags:\n{tags_yaml}\ntype: memory\n---\n\n{text}\n",
        encoding="utf-8",
    )
    return note_path, doc_id


def read_atom(project_slug: str, atom: str) -> str | None:
    """Read an atomic note. Returns content body (no frontmatter) or None if missing."""
    brain = _get_brain_path()
    path = brain / "inbox" / "memories" / project_slug / f"{atom}.md"
    if not path.resolve().is_relative_to(brain.resolve()):
        raise ValueError(f"Path escapes brain root: {project_slug}/{atom}")
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            return text[end + 3:].strip()
    return text.strip()


def write_atom(project_slug: str, atom: str, content: str) -> Path:
    """Write an atomic note, creating the project folder if needed."""
    brain = _get_brain_path()
    atom_dir = brain / "inbox" / "memories" / project_slug
    path = atom_dir / f"{atom}.md"
    if not path.resolve().is_relative_to(brain.resolve()):
        raise ValueError(f"Path escapes brain root: {project_slug}/{atom}")
    atom_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    path.write_text(
        f"---\ntype: atom\natom: {atom}\nproject: {project_slug}\nupdated: {date_str}\n---\n\n{content}\n",
        encoding="utf-8",
    )
    return path


def write_project_hub(
    project_slug: str,
    project_display: str,
    status: str,
    tech: list[str],
    last_active: str,
    session_refs: list[tuple[str, str]],
) -> Path:
    """Write or overwrite the project hub index.md (links only, no prose)."""
    brain = _get_brain_path()
    hub_dir = brain / "inbox" / "memories" / project_slug
    hub_path = hub_dir / "index.md"
    if not hub_path.resolve().is_relative_to(brain.resolve()):
        raise ValueError(f"Path escapes brain root: {project_slug}")
    hub_dir.mkdir(parents=True, exist_ok=True)

    tech_yaml = ", ".join(tech) if tech else ""
    session_log = "\n".join(
        f"- [[{ref}]] — {date}" for ref, date in session_refs
    ) or "_no sessions indexed yet_"

    content = (
        f"---\ntype: project-hub\nstatus: {status}\ntech: [{tech_yaml}]\n"
        f"last_active: {last_active}\n---\n\n"
        f"## Current Understanding\n"
        f"[[purpose]] · [[tech]] · [[state]] · [[questions]]\n\n"
        f"## This Session\n[[recent]]\n\n"
        f"## Session Log\n{session_log}\n"
    )
    path = hub_dir / "index.md"
    path.write_text(content, encoding="utf-8")
    return path


def write_memories_moc(projects: list[dict]) -> Path:
    """
    Regenerate second-brain/inbox/memories/index.md.
    projects: list of { slug, display, status, purpose_line }
    """
    brain = _get_brain_path()
    moc_path = brain / "inbox" / "memories" / "index.md"
    moc_path.parent.mkdir(parents=True, exist_ok=True)

    by_status: dict[str, list[dict]] = {"active": [], "paused": [], "archived": []}
    for p in projects:
        by_status.get(p["status"], by_status["paused"]).append(p)

    sections = ["# Projects\n"]
    for status_label in ("active", "paused", "archived"):
        group = by_status[status_label]
        if not group:
            continue
        rows = "\n".join(
            f"- [[{p['slug']}/index|{p['display']}]] — {p['purpose_line']}"
            for p in group
        )
        sections.append(f"## {status_label.capitalize()}\n{rows}\n")

    moc_path.write_text("\n".join(sections), encoding="utf-8")
    return moc_path


def write_web_note(url: str, title: str, author: str, date: str, enrichment: Enrichment) -> Path:
    """Write an Obsidian note for an ingested web article. Returns the path written."""
    note_dir = _get_brain_path() / "sources" / "web"
    note_dir.mkdir(parents=True, exist_ok=True)

    filename = _slug(title)
    note_path = note_dir / f"{filename}.md"

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


def write_journal_note(thread: "MessageThread", enrichment: Enrichment) -> Path:
    """Write an Obsidian note for an iMessage journal thread. Returns the path written."""
    note_dir = _get_brain_path() / "sources" / "journal"
    note_dir.mkdir(parents=True, exist_ok=True)

    date_slug = re.sub(r"[,\s]+", "-", thread.date).strip("-").lower()
    contact_slug = re.sub(r"[^a-z0-9]+", "-", thread.contact.lower()).strip("-")
    note_path = note_dir / f"{date_slug}-{contact_slug}.md"
    if note_path.exists():
        raise NoteAlreadyExists(note_path)

    tags_yaml = "\n".join(f"  - {_normalize_tag(t)}" for t in enrichment.interest_tags)
    concepts = "\n".join(f"- {c}" for c in enrichment.key_concepts)
    insights = "\n".join(f"- {i}" for i in enrichment.insights)

    content = (
        f"---\ncontact: {thread.contact}\ndate: {thread.date}\n"
        f"tags:\n{tags_yaml}\ntype: journal\n---\n\n"
        f"## Thesis\n{enrichment.thesis}\n\n"
        f"## Summary\n{enrichment.summary}\n\n"
        f"## Key Concepts\n{concepts}\n\n"
        f"## Insights\n{insights}\n"
    )
    if enrichment.key_moments:
        moments = "\n".join(
            f"- **{m.timestamp}** — {m.description}" for m in enrichment.key_moments
        )
        content += f"\n## Key Moments\n{moments}\n"

    messages = "\n".join(f"[{m.timestamp}] {m.text}" for m in thread.messages)
    content += f"\n## Messages\n{messages}\n"

    note_path.write_text(content, encoding="utf-8")
    return note_path


_CT_TO_EXT = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}


def _save_image(url: str, dest: Path) -> Path | None:
    """Download an image URL to dest (no extension). Returns final path or None on failure."""
    from urllib.parse import urlparse
    if urlparse(url).scheme not in ("http", "https"):
        return None
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            ct = resp.headers.get("Content-Type", "image/jpeg").lower().split(";")[0].strip()
            ext = _CT_TO_EXT.get(ct, ".jpg")
            final = dest.with_suffix(ext)
            final.write_bytes(resp.read())
            return final
    except Exception:
        return None


def write_instagram_note(post: "InstagramPost", enrichment: Enrichment) -> Path:
    """Write an Obsidian note for an ingested Instagram post. Returns the path written."""
    note_dir = _get_brain_path() / "sources" / "instagram"
    note_dir.mkdir(parents=True, exist_ok=True)

    sc_match = re.search(r"/(?:p|reel|tv)/([A-Za-z0-9_-]+)", post.url)
    shortcode = sc_match.group(1) if sc_match else "post"
    filename = f"{post.username}-{post.timestamp}-{shortcode}.md"
    note_path = note_dir / filename
    if note_path.exists():
        raise NoteAlreadyExists(note_path)

    # Download images before writing note so we know the saved filenames
    saved_images: list[Path] = []
    for i, img_url in enumerate(post.images or [], start=1):
        img_dest = note_dir / f"{shortcode}-img-{i}"
        saved = _save_image(img_url, img_dest)
        if saved:
            saved_images.append(saved)

    # video-only reels have no slides; keep the cover so Fresh has a thumbnail
    if not saved_images and getattr(post, "thumbnail_url", None):
        thumb_dir = note_dir / "thumbnails"
        thumb_dir.mkdir(parents=True, exist_ok=True)
        saved_thumb = _save_image(post.thumbnail_url, thumb_dir / f"{shortcode}-thumb")
        if saved_thumb:
            saved_images.append(saved_thumb)

    tags_yaml = "\n".join(f"  - {_normalize_tag(t)}" for t in enrichment.interest_tags)
    concepts = "\n".join(f"- {c}" for c in enrichment.key_concepts)
    insights = "\n".join(f"- {i}" for i in enrichment.insights)

    brain = _get_brain_path()
    image_paths_yaml = (
        "\n" + "\n".join(f"  - {p.relative_to(brain)}" for p in saved_images)
        if saved_images else " []"
    )

    content = (
        f"---\nurl: {post.url}\nusername: {post.username}\ndate: {post.timestamp}\n"
        f"title: {enrichment.thesis}\n"
        f"tags:\n{tags_yaml}\ntype: instagram\n"
        f"image_paths:{image_paths_yaml}\n---\n\n"
    )
    if saved_images:
        embeds = "\n".join(f"![[{p.name}]]" for p in saved_images)
        content += f"{embeds}\n\n"

    content += (
        f"## Caption\n{post.caption}\n\n"
        f"## Thesis\n{enrichment.thesis}\n\n"
        f"## Summary\n{enrichment.summary}\n\n"
        f"## Key Concepts\n{concepts}\n\n"
        f"## Insights\n{insights}\n"
    )
    if enrichment.key_moments:
        moments = "\n".join(
            f"- **{m.timestamp}** — {m.description}" for m in enrichment.key_moments
        )
        content += f"\n## Key Moments\n{moments}\n"

    note_path.write_text(content, encoding="utf-8")
    return note_path


def write_tiktok_note(
    post: "TikTokPost",
    enrichment: Enrichment,
    transcript: str = "",
    frame_bytes: list[bytes] | None = None,
) -> Path:
    """Write an Obsidian note for an ingested TikTok. Returns the path written."""
    brain = _get_brain_path()
    note_dir = brain / "sources" / "tiktok"
    note_dir.mkdir(parents=True, exist_ok=True)

    title_slug = _slug(post.title) if post.title else "tiktok"
    filename = f"{post.username}-{post.timestamp}-{post.video_id}-{title_slug}"[:120]
    note_path = note_dir / f"{filename}.md"
    if note_path.exists():
        raise NoteAlreadyExists(f"Note already exists for TikTok {post.video_id}: {note_path}")

    saved_thumb: Path | None = None
    if post.thumbnail_url:
        thumb_dir = note_dir / "thumbnails"
        thumb_dir.mkdir(parents=True, exist_ok=True)
        saved_thumb = _save_image(post.thumbnail_url, thumb_dir / f"{post.video_id}-thumb")

    saved_frames: list[Path] = []
    if frame_bytes:
        frame_dir = note_dir / "frames" / post.video_id
        frame_dir.mkdir(parents=True, exist_ok=True)
        for i, raw in enumerate(frame_bytes, start=1):
            fp = frame_dir / f"frame-{i}.jpg"
            fp.write_bytes(raw)
            saved_frames.append(fp)

    tags_yaml = "\n".join(f"  - {_normalize_tag(t)}" for t in enrichment.interest_tags)
    concepts = "\n".join(f"- {c}" for c in enrichment.key_concepts)
    insights = "\n".join(f"- {i}" for i in enrichment.insights)

    media_paths = [p for p in [saved_thumb, *saved_frames] if p]
    media_yaml = (
        "\n" + "\n".join(f"  - {p.relative_to(brain)}" for p in media_paths)
        if media_paths else " []"
    )

    content = (
        f"---\nurl: {post.url}\nusername: {post.username}\ndate: {post.timestamp}\n"
        f"title: {enrichment.thesis}\nduration: {post.duration}\n"
        f"tags:\n{tags_yaml}\ntype: tiktok\n"
        f"image_paths:{media_yaml}\n---\n\n"
    )
    if saved_thumb:
        content += f"![[{saved_thumb.name}]]\n\n"
    if saved_frames:
        content += "\n".join(f"![[{p.name}]]" for p in saved_frames) + "\n\n"

    if post.music:
        content += f"**Music:** {post.music}\n\n"

    content += (
        f"## Caption\n{post.description or '_(no caption)_'}\n\n"
        f"## Thesis\n{enrichment.thesis}\n\n"
        f"## Summary\n{enrichment.summary}\n\n"
        f"## Key Concepts\n{concepts}\n\n"
        f"## Insights\n{insights}\n"
    )
    if transcript.strip():
        content += (
            f"\n## Transcript\n<details>\n<summary>Whisper transcript</summary>\n\n"
            f"{transcript}\n</details>\n"
        )

    note_path.write_text(content, encoding="utf-8")
    return note_path


def write_pinterest_note(pin, enrichment: Enrichment) -> Path:
    """Write an Obsidian note for an ingested Pinterest pin. Returns the path."""
    note_dir = _get_brain_path() / "sources" / "pinterest"
    note_dir.mkdir(parents=True, exist_ok=True)

    note_path = note_dir / f"pinterest-{pin.pin_id}.md"
    if note_path.exists():
        raise NoteAlreadyExists(note_path)

    saved = _save_image(pin.image_url, note_dir / f"{pin.pin_id}-img")
    brain = _get_brain_path()
    image_paths_yaml = f"\n  - {saved.relative_to(brain)}" if saved else " []"

    tags_yaml = "\n".join(f"  - {_normalize_tag(t)}" for t in enrichment.interest_tags)
    concepts = "\n".join(f"- {c}" for c in enrichment.key_concepts)
    insights = "\n".join(f"- {i}" for i in enrichment.insights)

    content = (
        f"---\nurl: {pin.url}\ntitle: {enrichment.thesis}\n"
        f"tags:\n{tags_yaml}\ntype: pinterest\n"
        f"image_paths:{image_paths_yaml}\n---\n\n"
    )
    if saved:
        content += f"![[{saved.name}]]\n\n"
    if pin.title or pin.description:
        content += f"> {pin.title}\n> {pin.description}\n\n"
    content += (
        f"## Summary\n{enrichment.summary}\n\n"
        f"## Key Concepts\n{concepts}\n\n"
        f"## Insights\n{insights}\n"
    )

    note_path.write_text(content, encoding="utf-8")
    return note_path


def annotate_note(note_path: Path, tags: list[str], thought: str) -> None:
    """Attach the user's ingest-hub annotation to a written note.

    Each tag joins the frontmatter tags (so it embeds and filters like any
    interest tag); the thought lands in a `## My take` section. Idempotent on
    tags; repeated thoughts append under the same section.
    """
    text = note_path.read_text(encoding="utf-8")

    for tag in [_normalize_tag(t) for t in tags if t]:
        fm_end = text.index("---", 4) if text.startswith("---") else 0
        frontmatter = text[:fm_end]
        if f"- {tag}\n" in frontmatter:
            continue
        if re.search(r"^tags:", frontmatter, re.MULTILINE):
            text = text.replace("tags:\n", f"tags:\n  - {tag}\n", 1)
        else:
            text = text[:fm_end] + f"tags:\n  - {tag}\n" + text[fm_end:]

    if thought.strip():
        if "## My take" in text:
            text = text.rstrip("\n") + f"\n\n{thought.strip()}\n"
        else:
            text = text.rstrip("\n") + f"\n\n## My take\n\n{thought.strip()}\n"

    note_path.write_text(text, encoding="utf-8")


def append_daily_digest(note_path: Path, tags: list[str], thought: str) -> Path:
    """Append one wikilinked line for an annotated ingest to today's digest.

    Returns the digest path (inbox/review-YYYY-MM-DD.md, created on first use)
    so the daily journal flow has a single hub to glance at.
    """
    from datetime import date

    inbox = _get_brain_path() / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    digest = inbox / f"review-{today}.md"
    if not digest.exists():
        digest.write_text(f"# Ingest digest — {today}\n\n", encoding="utf-8")

    snippet = " ".join(thought.split())
    if len(snippet) > 80:
        snippet = snippet[:80].rstrip() + "..."
    line = f"- [[{note_path.stem}]]"
    hashtags = " ".join(f"#{_normalize_tag(t)}" for t in tags if t)
    if hashtags:
        line += f" ({hashtags})"
    if snippet:
        line += f": {snippet}"
    with digest.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    return digest


def reindex_vault(force: bool = False) -> int:
    """
    Scan vault directories and bulk-upsert changed .md files into ChromaDB.
    Skips sources/youtube/ (indexed separately by store.upsert).
    Skips files whose SHA256 hash matches the cache unless force=True.
    Returns count of notes indexed.
    """
    from .cache import file_hash, load_index_cache, save_index_cache, update_cache_entry

    brain = _get_brain_path()
    scan_dirs = ["inbox/memories", "inbox", "projects", "decisions", "debugging", "tools", "sources/instagram", "sources/web", "sources/journal"]
    seen_paths: set[str] = set()
    count = 0

    cache = load_index_cache()

    for subdir in scan_dirs:
        d = brain / subdir
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

            rel = md_file.relative_to(brain)
            content = md_file.read_text(encoding="utf-8")
            id_match = re.search(r"^id:\s*(.+)$", content, re.MULTILINE)
            if id_match:
                doc_id = id_match.group(1).strip()
            else:
                doc_id = "note_" + str(rel).replace("/", "_").replace(".md", "").replace(" ", "_")
            body = strip_frontmatter(content)
            if not body.strip():
                update_cache_entry(md_file, cache)
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


def rebuild_index() -> None:
    """Scan the vault and rewrite wiki/index.md from scratch."""
    vault_path = _get_brain_path()
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

    # sources/instagram/
    instagram_dir = vault_path / "sources" / "instagram"
    if instagram_dir.exists():
        notes = sorted(instagram_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        if notes:
            rows_ig = "\n".join(f"- [[sources/instagram/{p.stem}]]" for p in notes)
            sections.append(f"## sources/instagram/\n{rows_ig}\n")

    # sources/web/
    web_dir = vault_path / "sources" / "web"
    if web_dir.exists():
        notes = sorted(web_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        if notes:
            rows_web = "\n".join(f"- [[sources/web/{p.stem}]]" for p in notes)
            sections.append(f"## sources/web/\n{rows_web}\n")

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


def write_note(
    meta: dict,
    enrichment: Enrichment,
    segments: list[dict],
    frame_bytes: list[bytes] | None = None,
) -> Path:
    """
    Write an Obsidian note for a video. Returns the path written.
    Raises NoteAlreadyExists if the note already exists.
    segments: raw transcript segments [{start, duration, text}] for timestamped linking.
    frame_bytes: optional raw JPEG frames to save alongside the note.
    """
    brain = _get_brain_path()
    video_id: str = meta["id"]
    title: str = meta.get("title", video_id)
    note_dir = brain / "sources" / "youtube"
    note_dir.mkdir(parents=True, exist_ok=True)

    filename = _slug(title)
    note_path = note_dir / f"{filename}.md"
    if note_path.exists():
        raise NoteAlreadyExists(
            f"Note already exists for '{title}': {note_path}"
        )

    # Save thumbnail + any extracted frames before building note
    saved_frames: list[Path] = []
    thumb_url = meta.get("thumbnail")
    if thumb_url:
        thumb_dir = note_dir / "thumbnails"
        thumb_dir.mkdir(parents=True, exist_ok=True)
        saved = _save_image(thumb_url, thumb_dir / f"{video_id}-thumb")
        if saved:
            saved_frames.append(saved)
    if frame_bytes:
        frame_dir = note_dir / "frames" / video_id
        frame_dir.mkdir(parents=True, exist_ok=True)
        for i, raw in enumerate(frame_bytes, start=1):
            fp = frame_dir / f"frame-{i}.jpg"
            fp.write_bytes(raw)
            saved_frames.append(fp)

    note_content = _build_note(meta, enrichment, segments, saved_frames or None)
    note_path.write_text(note_content, encoding="utf-8")

    date = _fmt_date(meta.get("upload_date", ""))
    _update_index(brain, filename, title, date)

    return note_path
