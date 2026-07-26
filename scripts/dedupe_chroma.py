"""One-time dedupe of double-indexed notes in ytk_memories (#71).

The same vault note can hold vectors under several historical id schemes:
ingest-time ids (instagram_X, web_X), reindex path ids (note_sources_...),
frontmatter ids, and pre-migration path prefixes (Vault/inbox/memories vs
Vault/second-brain/inbox/memories). Every downstream consumer that treats
rows as notes double-counts.

Groups rows by normalized source_path, keeps exactly one doc family per
note, deletes the rest. Rows without a source_path are reported, never
touched. Dry-run by default; pass --apply to delete.

    uv run python scripts/dedupe_chroma.py [--apply]
"""

import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def norm_source_path(sp: str) -> str:
    """Path suffix that survives vault relocations: everything after the
    brain dir marker, with the seed-era prefix collapsed onto the current one."""
    for marker in ("second-brain/", "Documents/Vault/"):
        if marker in sp:
            return sp.split(marker, 1)[1]
    return sp


def family(doc_id: str) -> str:
    """Part ids (doc#1, doc#2) belong to their head doc's family."""
    return doc_id.split("#", 1)[0]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="actually delete (default: dry run)")
    args = ap.parse_args()

    from ytk.store import _get_client, epoch_collection_name

    client = _get_client()
    col = client.get_collection(epoch_collection_name("ytk_memories"))
    res = col.get(include=["metadatas"])

    # normalized note path -> family id -> [(row_id, meta)]
    notes: dict[str, dict[str, list[tuple[str, dict]]]] = defaultdict(lambda: defaultdict(list))
    no_path = 0
    for rid, meta in zip(res["ids"], res["metadatas"]):
        meta = meta or {}
        sp = meta.get("source_path", "")
        if not sp:
            no_path += 1
            continue
        notes[norm_source_path(sp)][family(rid)].append((rid, meta))

    to_delete: list[str] = []
    dup_notes = 0
    by_category: dict[str, int] = defaultdict(int)

    def newest(rows: list[tuple[str, dict]]) -> str:
        return max((r[1].get("ingested_at") or "") for r in rows)

    def on_disk(rows: list[tuple[str, dict]]) -> bool:
        return Path(rows[0][1].get("source_path", "")).exists()

    for norm, families in notes.items():
        if len(families) < 2:
            continue
        dup_notes += 1
        # keeper first: file-on-disk wins, then newest ingested_at, then id order
        ranked = sorted(families.items(), key=lambda kv: kv[0])
        ranked.sort(key=lambda kv: newest(kv[1]), reverse=True)
        ranked.sort(key=lambda kv: (not on_disk(kv[1]), newest(kv[1]) == ""))
        keeper, losers = ranked[0], ranked[1:]
        cat = norm.split("/")[0] if "/" in norm else norm
        for fam_id, rows in losers:
            by_category[cat] += len(rows)
            to_delete.extend(rid for rid, _ in rows)
        print(f"{norm}\n  keep   {keeper[0]}\n  delete {', '.join(f for f, _ in losers)}")

    print(f"\n{dup_notes} notes with duplicate doc families")
    print(f"{len(to_delete)} vectors to delete")
    for cat, n in sorted(by_category.items(), key=lambda kv: -kv[1]):
        print(f"  {cat}: {n}")
    print(f"{no_path} rows have no source_path (untouched)")

    if not to_delete:
        return
    if args.apply:
        col.delete(ids=to_delete)
        print(f"\nDeleted {len(to_delete)} vectors. New count: {col.count()}")
    else:
        print("\nDry run — pass --apply to delete.")


if __name__ == "__main__":
    main()
