#!/usr/bin/env python
"""Backfill title/url metadata onto existing memories-collection vectors (#169).

The indexer historically stored only {doc_id, tags, source_path}, so every
consumer that wanted a title re-derived it from body text — which for
image-first notes is embed markup. This updates metadata in place from each
note's frontmatter; embeddings are untouched, so no re-embed cost.

    uv run python scripts/backfill_note_metadata.py [--dry-run]
"""

from __future__ import annotations

import sys
from pathlib import Path

import ytk.vault  # noqa: F401  — sets CHROMA_URL; bare store import reads a stale DB (#164)
from ytk import store
from ytk.vault import note_identity_fields


def main() -> None:
    dry = "--dry-run" in sys.argv
    client = store._get_client()
    col = client.get_collection(store.epoch_collection_name("ytk_memories"))
    got = col.get(include=["metadatas"], limit=1_000_000)
    ids, metas = got["ids"], got["metadatas"]
    assert metas is not None
    upd_ids, upd_metas = [], []
    missing_file = already = no_fields = 0
    for i, m in zip(ids, metas):
        if "#" in i:
            continue  # retrieval-only part vector; identity rides the main doc
        path = Path(str(m.get("source_path", "")))
        if not path.exists():
            missing_file += 1
            continue
        fields = note_identity_fields(path.read_text(encoding="utf-8"))
        if not fields:
            no_fields += 1
            continue
        if all(m.get(k) == v for k, v in fields.items()):
            already += 1
            continue
        upd_ids.append(i)
        upd_metas.append({**m, **fields})
    print(
        f"{len(ids)} rows: {len(upd_ids)} to update, {already} current, "
        f"{no_fields} without title/url frontmatter, {missing_file} files missing"
    )
    if dry or not upd_ids:
        return
    for at in range(0, len(upd_ids), 500):
        col.update(ids=upd_ids[at : at + 500], metadatas=upd_metas[at : at + 500])
    print(f"updated {len(upd_ids)} rows")


if __name__ == "__main__":
    main()
