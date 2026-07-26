#!/usr/bin/env -S uv run python
"""Migrate bare-scheme content note ids to the canonical path-derived form (#95).

Two writers used to race over content notes: ingest upserted
``{source}_{stem60}`` and reindex_vault re-upserted the same file as
``note_sources_{source}_{stem}``. Sources the reindexer scanned (instagram,
web, journal) ended up canonical; sources it never scanned (tiktok, reddit,
pinterest) kept their ingest-time ids. Ingest now writes the canonical id
directly (vault.content_note_doc_id) and the reindexer scans every source
folder, so this migration renames the stragglers once and the store carries
one scheme forever after.

Pure rename: embeddings, documents, and metadata (including the original
``ingested_at``) are copied verbatim under the new id — nothing is re-embedded
and no timestamp is restamped. '#'-suffixed retrieval parts move with their
base doc. A record whose source file no longer exists is reported and left
untouched (orphan handling belongs to gc, not an id migration).

Also emits the old->new id map as JSON (--map-out) so the retrieval gate's
frozen corpus (eval/retrieval/frozen_corpus.json) can be re-keyed to the same
documents. Dry run by default; --apply writes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ytk import store
from ytk.vault import _get_brain_path, vault_note_doc_id

# Every ingest-time content scheme that ever existed. memory_/memo_/shot_ are
# NOT content notes: they are memory records whose ids are pinned by id:
# frontmatter or written once by upsert_memory, with no second writer racing.
BARE_PREFIXES = ("tiktok_", "reddit_", "pinterest_", "instagram_", "web_", "journal_")


def plan_renames() -> tuple[list[dict], list[dict]]:
    """Return (renames, skipped): one entry per base doc under a bare scheme."""
    brain = _get_brain_path()
    col = store._memories_collection()
    got = col.get(include=["metadatas"])

    by_base: dict[str, list[str]] = {}
    meta_by_id: dict[str, dict] = {}
    for vector_id, meta in zip(got["ids"], store.chroma_field(got["metadatas"], "metadatas")):
        base = vector_id.split("#", 1)[0]
        by_base.setdefault(base, []).append(vector_id)
        meta_by_id[vector_id] = meta or {}

    renames: list[dict] = []
    skipped: list[dict] = []
    for base, vector_ids in sorted(by_base.items()):
        if not base.startswith(BARE_PREFIXES):
            continue
        source_path = str(meta_by_id[base].get("source_path") or "")
        note = Path(source_path).expanduser() if source_path else None
        if note is None or not note.exists():
            skipped.append({"id": base, "reason": "source file missing", "path": source_path})
            continue
        new_id = vault_note_doc_id(note, brain)
        if new_id == base:
            continue
        renames.append({"old": base, "new": new_id, "vectors": sorted(vector_ids)})
    return renames, skipped


def apply_renames(renames: list[dict]) -> None:
    col = store._memories_collection()
    for r in renames:
        got = col.get(ids=r["vectors"], include=["embeddings", "documents", "metadatas"])
        new_ids = []
        new_metas = []
        for vector_id, meta in zip(got["ids"], store.chroma_field(got["metadatas"], "metadatas")):
            suffix = vector_id[len(r["old"]) :]  # '' or '#N'
            new_ids.append(r["new"] + suffix)
            new_metas.append({**(meta or {}), "doc_id": r["new"]})
        col.add(
            ids=new_ids,
            embeddings=store.chroma_field(got["embeddings"], "embeddings"),
            documents=store.chroma_field(got["documents"], "documents"),
            metadatas=new_metas,
        )
        col.delete(ids=got["ids"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the renames (default: dry run)")
    parser.add_argument("--map-out", type=Path, help="write the old->new id map as JSON")
    args = parser.parse_args()

    before = store._memories_collection().count()
    renames, skipped = plan_renames()

    print(f"{'APPLY' if args.apply else 'DRY RUN'}: {len(renames)} base docs to rename")
    for r in renames:
        parts = len(r["vectors"]) - 1
        print(f"  {r['old']}  ->  {r['new']}" + (f"  (+{parts} parts)" if parts else ""))
    for s in skipped:
        print(f"  SKIP {s['id']}: {s['reason']} ({s['path']})")

    if args.map_out:
        args.map_out.write_text(
            json.dumps({r["old"]: r["new"] for r in renames}, indent=2) + "\n", encoding="utf-8"
        )
        print(f"id map written to {args.map_out}")

    if not args.apply:
        return 0

    apply_renames(renames)
    after = store._memories_collection().count()
    print(f"vector count before={before} after={after} (must be equal)")
    if before != after:
        print("VECTOR COUNT CHANGED — investigate before trusting the store")
        return 1

    leftovers = [
        i
        for i in store._memories_collection().get(include=[])["ids"]
        if i.split("#", 1)[0].startswith(BARE_PREFIXES)
        and not any(i.split("#", 1)[0] == s["id"] for s in skipped)
    ]
    if leftovers:
        print(f"LEFTOVER bare-scheme ids after apply: {leftovers}")
        return 1
    print("no bare-scheme content ids remain")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
