# pyright: basic
# Composes vault.py and store.py, both legacy basic-mode modules (#122).
"""The curator note writer (#197 P4): a grader-passed draft becomes a vault
note with the spine My take, Response, Thesis, then the rest.

Idempotent by design: the note is located by frontmatter url before any
path is derived from the title, so a re-run (or a rename upstream)
rewrites the same file instead of duplicating it. Indexing mirrors what
ingestion used to do — store.upsert owns sources/youtube ids (#147),
everything else lands via upsert_doc under the reindex doc-id scheme.
"""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from . import vault
from .enricher import EnrichmentV2
from .evidence import EvidenceBundle


def _media_key(bundle: EvidenceBundle) -> str:
    return (
        bundle.media_id or hashlib.sha1(bundle.url.encode(), usedforsecurity=False).hexdigest()[:12]
    )


def _save_media(bundle: EvidenceBundle, note_dir: Path) -> list[Path]:
    """Thumbnail (URL) and locally captured frames into the note's typed
    subfolders; basenames carry the media key because Obsidian resolves
    ![[name]] vault-wide. Best-effort: a failed download is a gap already
    named in the bundle, never a failed note."""
    key = _media_key(bundle)
    saved: list[Path] = []
    if bundle.thumbnail:
        thumb_dir = note_dir / "thumbnails"
        thumb_dir.mkdir(parents=True, exist_ok=True)
        got = vault._save_image(bundle.thumbnail, thumb_dir / f"{key}-thumb")
        if got:
            saved.append(got)
    local_frames = [Path(p) for p in bundle.frames if Path(p).is_file()]
    if local_frames:
        frame_dir = note_dir / "frames" / key
        frame_dir.mkdir(parents=True, exist_ok=True)
        for i, src in enumerate(local_frames, start=1):
            dst = frame_dir / f"{key}-frame-{i}{src.suffix or '.jpg'}"
            shutil.copyfile(src, dst)
            saved.append(dst)
    return saved


def _spine(
    bundle: EvidenceBundle,
    take_kind: str | None,
    take_text: str | None,
    draft: EnrichmentV2,
) -> str:
    sections: list[str] = []
    if take_text and take_kind != "reflex":
        sections.append(f"## My take\n{take_text}")
    if draft.take_response:
        sections.append(f"## Response\n{draft.take_response}")
    sections.append(f"## Thesis\n{draft.thesis}")
    sections.append(f"## Commentary\n{draft.summary}")
    if draft.key_concepts:
        sections.append("## Key Concepts\n" + "\n".join(f"- {c}" for c in draft.key_concepts))
    if draft.insights:
        sections.append("## Insights\n" + "\n".join(f"- {i}" for i in draft.insights))
    if draft.key_moments:
        rows = "\n".join(f"- **{m.timestamp}** — {m.description}" for m in draft.key_moments)
        sections.append("## Key Moments\n" + rows)
    if draft.evidence_gaps:
        sections.append("## Evidence Gaps\n" + "\n".join(f"- {g}" for g in draft.evidence_gaps))
    if bundle.source == "youtube" and bundle.transcript:
        body = vault._build_transcript(_media_key(bundle), bundle.transcript)
        sections.append(
            f"## Transcript\n<details>\n<summary>Raw transcript</summary>\n\n{body}\n</details>"
        )
    return "\n\n".join(sections) + "\n"


def write_curator_note(
    bundle: EvidenceBundle,
    take_kind: str | None,
    take_text: str | None,
    draft: EnrichmentV2,
) -> Path:
    """Write (or rewrite, located by frontmatter url) the note. Returns the
    path written."""
    brain = vault._get_brain_path()
    note_dir = brain / "sources" / bundle.source
    note_dir.mkdir(parents=True, exist_ok=True)
    existing = vault.find_note_by_url(bundle.url, 0.0)
    path = existing or note_dir / f"{vault._slug(bundle.title or _media_key(bundle))}.md"

    saved = _save_media(bundle, note_dir)
    tags_yaml = "\n".join(f"  - {vault._normalize_tag(t)}" for t in draft.interest_tags)
    image_paths_yaml = (
        "\n" + "\n".join(f"  - {p.relative_to(brain)}" for p in saved) if saved else " []"
    )
    date = vault._fmt_date(bundle.upload_date or "")
    lines = [
        "---",
        f"url: {bundle.url}",
        f"title: {bundle.title or ''}",
    ]
    if bundle.uploader:
        lines.append(f"uploader: {bundle.uploader}")
    if date:
        lines.append(f"date: {date}")
    lines.append(f"captured: {datetime.now():%Y-%m-%d}")
    lines.append(f"tags:\n{tags_yaml}" if tags_yaml else "tags: []")
    if bundle.duration:
        lines.append(f"duration: {vault._fmt_duration(int(bundle.duration))}")
    lines.append(f"image_paths:{image_paths_yaml}")
    lines.append("---")

    embeds = "\n".join(f"![[{p.name}]]" for p in saved)
    body = _spine(bundle, take_kind, take_text, draft)
    content = "\n".join(lines) + "\n\n" + (embeds + "\n\n" if embeds else "") + body
    path.write_text(content, encoding="utf-8")

    if bundle.source == "youtube" and existing is None:
        vault._update_index(brain, path.stem, bundle.title or "", date)
    return path


def index_note(note_path: Path, bundle: EvidenceBundle, draft: EnrichmentV2) -> None:
    """Embed the note as ingestion used to. YouTube ids belong to
    store.upsert (#147); everything else shares reindex's doc-id scheme so
    ingest and reindex stay one writer."""
    from . import store  # deferred: chroma import cost rides only on landing

    if bundle.source == "youtube":
        meta = {
            "id": _media_key(bundle),
            "url": bundle.url,
            "title": bundle.title or "",
            "uploader": bundle.uploader or "",
            "upload_date": bundle.upload_date or "",
            "description": bundle.description or "",
        }
        store.upsert(meta, draft, bundle.transcript)
        return
    doc_id = vault.content_note_doc_id(note_path)
    body = store.strip_frontmatter(note_path.read_text(encoding="utf-8"))
    store.upsert_doc(
        doc_id,
        body,
        {
            "doc_id": doc_id,
            "tags": ", ".join(draft.interest_tags),
            "source_path": str(note_path),
        },
    )


# ---------------------------------------------------------------------------
# Snapshots and the Connections section (#197 P6)
# ---------------------------------------------------------------------------


def snapshots_dir() -> Path:
    import os

    from .evidence import evidence_dir

    env = os.environ.get("YTK_SNAPSHOTS")
    return Path(env) if env else evidence_dir() / "snapshots"


def snapshot_note(conn: sqlite3.Connection, item_id: int, path: Path) -> Path:
    """Copy the note before a rewrite and record the snapshots row. The vault
    is iCloud, not git; this row is the only undo. Every rewriter of an
    existing note calls this first."""
    from . import ledger

    dst_dir = snapshots_dir()
    dst_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    dst = dst_dir / f"{item_id}-{stamp}.md"
    n = 1
    while dst.exists():
        dst = dst_dir / f"{item_id}-{stamp}-{n}.md"
        n += 1
    shutil.copyfile(path, dst)
    conn.execute(
        "INSERT INTO snapshots (item_id, at, before_ref, after_ref) VALUES (?, ?, ?, ?)",
        (item_id, ledger.now(), str(dst), str(path)),
    )
    conn.commit()
    return dst


def apply_connections(path: Path, links: Iterable[tuple[str, str]]) -> None:
    """Write (or replace) the `## Connections` section: one wikilink per
    approved link with its one-clause argument. Sits after Thesis — the
    section argues the thesis's neighbors — or at the end when no Thesis
    exists. Replacing the whole section keeps re-runs idempotent."""
    text = path.read_text(encoding="utf-8")
    block = "## Connections\n" + "\n".join(f"- [[{t}]] — {arg}" for t, arg in links)

    lines = text.split("\n")
    starts = [i for i, ln in enumerate(lines) if ln.startswith("## ")]

    def section_end(start_idx: int) -> int:
        later = [i for i in starts if i > start_idx]
        return later[0] if later else len(lines)

    existing = [i for i, ln in enumerate(lines) if ln.strip() == "## Connections"]
    if existing:
        i = existing[0]
        lines[i : section_end(i)] = [*block.split("\n"), ""]
    else:
        thesis = [i for i, ln in enumerate(lines) if ln.strip() == "## Thesis"]
        if thesis:
            at = section_end(thesis[0])
            lines[at:at] = [*block.split("\n"), ""]
        else:
            if lines and lines[-1] == "":
                lines = lines[:-1]
            lines += ["", *block.split("\n")]
    path.write_text("\n".join(lines), encoding="utf-8")
