"""One-off migration: re-embed all text collections with the model configured
in store._TEXT_MODEL (2026-07-05: all-MiniLM-L6-v2 -> thenlper/gte-small).

Embeddings are frozen at write time, so a model change means re-embedding
every document into fresh collections. Documents and metadata are preserved
verbatim; ytk_visual (SigLIP-2, precomputed vectors) is untouched.

Take a backup of ~/.ytk/chroma before running. Usage:

  uv run python experiments/migrate_embedder.py
"""

import os

os.environ["HF_HUB_OFFLINE"] = "0"

from ytk import store  # noqa: E402


def migrate(name: str) -> tuple[int, int]:
    client = store._get_client()
    col = client.get_collection(name)
    old_count = col.count()
    if old_count == 0:
        return 0, 0
    dump = col.get(include=["documents", "metadatas"])
    client.delete_collection(name)
    new = client.get_or_create_collection(
        name=name,
        embedding_function=store._get_ef(),
        metadata={"hnsw:space": "cosine"},
    )
    batch = 100
    ids, docs, metas = dump["ids"], dump["documents"], dump["metadatas"]
    for i in range(0, len(ids), batch):
        new.upsert(
            ids=ids[i : i + batch],
            documents=docs[i : i + batch],
            metadatas=metas[i : i + batch],
        )
    return old_count, new.count()


def main():
    for name in (
        store._COLLECTION_VIDEOS,
        store._COLLECTION_SEGMENTS,
        store._COLLECTION_MEMORIES,
    ):
        before, after = migrate(name)
        status = "OK" if before == after else "MISMATCH"
        print(f"{name}: {before} -> {after} [{status}]")


if __name__ == "__main__":
    main()
