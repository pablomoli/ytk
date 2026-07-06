"""One-time migration: split existing ytk_videos docs into part vectors.

The old index stored one thesis+summary+insights+concepts doc per video, which
overflows gte-small's 512-token window and silently drops the tail (2026-07
enrichment audit). store.upsert now writes three parts; this script rebuilds
the same parts for every already-indexed video by parsing its vault note, so
the fix applies retroactively without any API calls.

Usage: uv run python scripts/rebuild_video_parts.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ytk import store  # noqa: E402
from ytk.vault import _get_brain_path  # noqa: E402

_SEC_RE = re.compile(
    r"^## (Thesis|Commentary|Summary|Key Concepts|Insights|Key Moments)\n(.*?)(?=^## |\Z)",
    re.MULTILINE | re.DOTALL,
)
_URL_RE = re.compile(r"^url:\s*(\S+)\s*$", re.MULTILINE)
_MOMENT_RE = re.compile(r"^- \*\*[^*]+\*\*\s*[—-]\s*(.+)$", re.MULTILINE)


def _sections(text: str) -> dict[str, str]:
    return {name: body.strip() for name, body in _SEC_RE.findall(text)}


def _bullets(body: str) -> list[str]:
    return [ln[2:].strip() for ln in body.splitlines() if ln.startswith("- ")]


def main() -> None:
    brain = _get_brain_path()
    notes_by_url: dict[str, Path] = {}
    for md in (brain / "sources" / "youtube").glob("*.md"):
        head = md.read_text(encoding="utf-8")[:2000]
        if m := _URL_RE.search(head):
            notes_by_url[m.group(1)] = md

    col = store._videos_collection()
    res = col.get(include=["metadatas"])
    plain = [(i, m) for i, m in zip(res["ids"], res["metadatas"]) if "#" not in i]
    print(f"videos in index: {len(plain)}, notes found: {len(notes_by_url)}")

    ids: list[str] = []
    docs: list[str] = []
    metas: list[dict] = []
    with_note = without_note = 0

    for video_id, meta in plain:
        thesis = meta.get("thesis", "")
        summary = meta.get("summary", "")
        title = meta.get("title", "")
        context = f"{title}. {thesis}"

        # part 0: replace the old truncated mega-doc with thesis+summary only
        ids.append(video_id)
        docs.append(thesis + "\n\n" + summary)
        metas.append(dict(meta))

        note = notes_by_url.get(meta.get("url", ""))
        if not note:
            without_note += 1
            continue
        with_note += 1
        sec = _sections(note.read_text(encoding="utf-8"))
        concepts = _bullets(sec.get("Key Concepts", ""))
        insights = _bullets(sec.get("Insights", ""))
        moments = _MOMENT_RE.findall(sec.get("Key Moments", ""))

        if concepts:
            ids.append(f"{video_id}#c")
            docs.append(context + "\n\nKey concepts: " + ", ".join(concepts))
            metas.append(dict(meta))
        if insights or moments:
            doc = context
            if insights:
                doc += "\n\nInsights: " + " ".join(insights)
            if moments:
                doc += "\n\nKey moments: " + "; ".join(moments)
            ids.append(f"{video_id}#i")
            docs.append(doc)
            metas.append(dict(meta))

    print(f"with note: {with_note}, metadata-only: {without_note}, vectors to embed: {len(ids)}")
    for i in range(0, len(ids), 32):
        col.upsert(ids=ids[i:i + 32], documents=docs[i:i + 32], metadatas=metas[i:i + 32])
        print(f"  embedded {min(i + 32, len(ids))}/{len(ids)}")
    print(f"done. collection now holds {col.count()} vectors")


if __name__ == "__main__":
    main()
