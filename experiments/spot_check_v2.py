"""Post-cutover spot check: known-item retrieval against the live collections.

Takes a fixed sample of eval queries (gold ids known) and verifies each gold
lands in the top-5 of the relevant live collection under the ACTIVE epoch.
Run after flipping store.EMBEDDING_EPOCH; the eval measured hit@5 0.923 for
v2, so 10 queries should land ~9 — below 7 means something is wired wrong
(prefix path, collection, dims), not sampling noise.

  uv run python experiments/spot_check_v2.py
"""

import json
import random
from pathlib import Path

from ytk import store

QUERIES = Path("experiments/encoder_harness/data/queries.jsonl")
PER_BUCKET = {"memories": 4, "videos": 3, "segments": 3}


def hit(q: dict) -> tuple[bool, str]:
    emb = store._embed_query(q["query"])
    bucket, gold = q["bucket"], q["gold_id"]
    if bucket == "videos":
        col = store._videos_collection()
        res = col.query(query_embeddings=[emb], n_results=min(10, col.count()))
        ids = {i.split("#")[0] for i in res["ids"][0][:5]}
        return gold.removeprefix("vid::") in ids, f"top5={sorted(ids)}"
    if bucket == "segments":
        col = store._segments_collection()
        res = col.query(query_embeddings=[emb], n_results=min(5, col.count()))
        ids = set(res["ids"][0])
        return gold.removeprefix("seg::") in ids, f"top5={sorted(ids)}"
    # memories: gold is mem::<vault-relative-path>; match on source_path suffix
    rel = gold.removeprefix("mem::")
    col = store._memories_collection()
    res = col.query(query_embeddings=[emb], n_results=min(10, col.count()),
                    include=["metadatas"])
    seen, paths = set(), []
    for meta in res["metadatas"][0]:
        did = meta.get("doc_id", "")
        if did in seen:
            continue
        seen.add(did)
        paths.append(meta.get("source_path", ""))
        if len(paths) == 5:
            break
    return any(p.endswith(rel) for p in paths), f"top5 paths={[p[-40:] for p in paths]}"


def main() -> None:
    qs = [json.loads(l) for l in QUERIES.open(encoding="utf-8") if l.strip()]
    random.Random(7).shuffle(qs)
    sample = []
    need = dict(PER_BUCKET)
    for q in qs:
        if need.get(q["bucket"], 0) > 0:
            sample.append(q)
            need[q["bucket"]] -= 1
    passed = 0
    for q in sample:
        ok, detail = hit(q)
        passed += ok
        print(f"[{'ok' if ok else 'MISS'}] ({q['bucket']}) {q['query'][:70]!r}")
        if not ok:
            print(f"        gold={q['gold_id']} {detail}")
    print(f"\n{passed}/{len(sample)} gold items in top-5 "
          f"(epoch {store.EMBEDDING_EPOCH})")
    raise SystemExit(0 if passed >= 7 else 1)


if __name__ == "__main__":
    main()
