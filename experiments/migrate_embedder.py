"""Encoder-epoch migration: embed v1 text collections into fresh v2 collections.

Spec: docs/superpowers/specs/2026-07-16-encoder-migration-qwen3.md (Phase 2).
Writes ytk_videos_v2 / ytk_segments_v2 / ytk_memories_v2 at the v2 epoch
(Qwen3-Embedding-0.6B, 1024d, whole-doc). v1 collections are never touched —
rollback is flipping store.EMBEDDING_EPOCH back.

Per-collection sources, mirroring what the encoder audit measured
(experiments/encoder_harness/export_corpus.py):
  memories — one vector per doc: full note body re-read from source_path
             (v1 stores truncated parts, the original text is not in chroma);
             docs whose file is gone are reconstructed from their parts.
  videos   — representative doc (thesis+summary, id without '#') verbatim;
             '#c'/'#i' parts are not carried over (retrieval gate measured
             representative docs on both sides).
  segments — every 60s block verbatim.

Metadata is copied verbatim — ingested_at stamps survive (grove v6 finding
15). Idempotent and resumable: ids already present in v2 are skipped, so a
killed run continues where it stopped. Progress logs to
/tmp/ytk-encoder-eval.log for the tmux tail.

  uv run python experiments/migrate_embedder.py [--dry-run] [--only memories]
"""

import argparse
import json
import os
import time
from pathlib import Path

os.environ["HF_HUB_OFFLINE"] = "0"

from ytk import ops, store

LOG = Path("/tmp/ytk-encoder-eval.log")
BATCH = 64
TARGET_EPOCH = "v2"


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] migrate_embedder: {msg}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def _reconstruct_from_parts(rep_doc: str, tail_docs: list[str]) -> str:
    """Rebuild a note body from its v1 part vectors' documents.

    upsert_doc prefixed every tail part with "{context}\n\n"; strip that
    prefix and rejoin. Lossy only for paragraphs the splitter hard-sliced,
    which rejoin without their original boundary.
    """
    tails = []
    for d in tail_docs:
        cut = d.find("\n\n")
        tails.append(d[cut + 2 :] if cut != -1 else d)
    return "\n\n".join([rep_doc] + tails)[:8000]


def _memory_rows() -> tuple[list[tuple[str, str, dict]], dict]:
    """(id, text, metadata) per memory doc + source stats."""
    col = store._memories_collection("v1")
    dump = col.get(include=["documents", "metadatas"])
    reps: dict[str, tuple[str, dict]] = {}
    tails: dict[str, list[tuple[int, str]]] = {}
    for rid, doc, meta in zip(dump["ids"], dump["documents"], dump["metadatas"]):
        doc_id = (meta or {}).get("doc_id") or rid.split("#")[0]
        if "#" in rid:
            tails.setdefault(doc_id, []).append(((meta or {}).get("part", 0), doc or ""))
        else:
            reps[doc_id] = (doc or "", meta or {})

    rows: list[tuple[str, str, dict]] = []
    stats = {"from_vault": 0, "from_parts": 0, "rep_only": 0}
    for doc_id, (rep_doc, meta) in reps.items():
        src = meta.get("source_path", "")
        text = ""
        if src and Path(src).exists():
            body = store.strip_frontmatter(Path(src).read_text(encoding="utf-8", errors="ignore"))
            if body.strip():
                text = body[:8000]
                stats["from_vault"] += 1
        if not text:
            parts = [d for _, d in sorted(tails.get(doc_id, []))]
            if parts:
                text = _reconstruct_from_parts(rep_doc, parts)
                stats["from_parts"] += 1
            else:
                text = rep_doc
                stats["rep_only"] += 1
        # part-count metadata is meaningless for whole-doc vectors
        rows.append((doc_id, text, {k: v for k, v in meta.items() if k != "part"}))
    return rows, stats


def _video_rows() -> tuple[list[tuple[str, str, dict]], dict]:
    col = store._videos_collection("v1")
    dump = col.get(include=["documents", "metadatas"])
    rows = [
        (rid, doc, meta or {})
        for rid, doc, meta in zip(dump["ids"], dump["documents"], dump["metadatas"])
        if "#" not in rid and (doc or "").strip()
    ]
    return rows, {"representative_docs": len(rows)}


def _segment_rows() -> tuple[list[tuple[str, str, dict]], dict]:
    col = store._segments_collection("v1")
    dump = col.get(include=["documents", "metadatas"])
    rows = [
        (rid, doc, meta or {})
        for rid, doc, meta in zip(dump["ids"], dump["documents"], dump["metadatas"])
        if (doc or "").strip()
    ]
    return rows, {"segments": len(rows)}


SOURCES = {
    "memories": (_memory_rows, store._memories_collection),
    "videos": (_video_rows, store._videos_collection),
    "segments": (_segment_rows, store._segments_collection),
}


def migrate(kind: str, dry_run: bool) -> dict:
    rows_fn, col_fn = SOURCES[kind]
    rows, stats = rows_fn()
    v2 = col_fn(TARGET_EPOCH)
    done = set(v2.get(include=[])["ids"])
    todo = [r for r in rows if r[0] not in done]
    log(f"{kind}: {len(rows)} docs, {len(done)} already in v2, {len(todo)} to embed {stats}")
    if dry_run or not todo:
        return {"kind": kind, "total": len(rows), "embedded": 0, **stats}

    ops.step(f"migrate {kind}", "running", f"{len(todo)} to embed")
    t0 = time.perf_counter()
    for i in range(0, len(todo), BATCH):
        batch = todo[i : i + BATCH]
        v2.upsert(
            ids=[r[0] for r in batch],
            documents=[r[1] for r in batch],
            metadatas=[r[2] for r in batch],
        )
        n = i + len(batch)
        rate = n / (time.perf_counter() - t0)
        log(
            f"{kind}: {n}/{len(todo)} ({rate:.1f} vec/s, "
            f"~{(len(todo) - n) / max(rate, 0.1) / 60:.0f} min left)"
        )
        ops.progress(n, len(todo), rate, label=kind)

    final = v2.count()
    ok = final == len(rows)
    log(f"{kind}: v2 count {final} vs expected {len(rows)} [{'OK' if ok else 'MISMATCH'}]")
    ops.step(
        f"migrate {kind}", "done" if ok else "fail", f"v2 count {final} vs expected {len(rows)}"
    )
    return {
        "kind": kind,
        "total": len(rows),
        "embedded": len(todo),
        "v2_count": final,
        "ok": ok,
        **stats,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--dry-run", action="store_true", help="report counts and source stats, embed nothing"
    )
    ap.add_argument("--only", choices=sorted(SOURCES), default=None)
    args = ap.parse_args()

    if store.EMBEDDING_EPOCH == TARGET_EPOCH:
        log(
            "store.EMBEDDING_EPOCH is already v2 — migration writes through "
            "the same collections the live system reads; refusing."
        )
        raise SystemExit(1)

    kinds = [args.only] if args.only else list(SOURCES)
    log(f"=== v1 -> {TARGET_EPOCH} migration starting (dry_run={args.dry_run}, kinds={kinds}) ===")
    results = [migrate(k, args.dry_run) for k in kinds]
    print(json.dumps(results, indent=2))
    if not args.dry_run and not all(r.get("ok", True) for r in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
