"""Pull the production Qwen v2 vectors out of Chroma into a local cache.

Read-only against the store. Writes experiments/sae_qwen/data/vectors.npz
(float32, L2-normalized) plus rows.jsonl (id, kind, note_key, source, text
prefix) in matching order.

    YTK_VISUAL_INDEX=off uv run python experiments/sae_qwen/pull_vectors.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from paths import DATA as OUT

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

TEXT_PREFIX = 900


def main() -> None:
    from ytk import store
    from ytk.config import load_config

    cfg = load_config()
    allow = tuple(f"note_sources_{p}_" for p in cfg.interest.content_sources)
    OUT.mkdir(parents=True, exist_ok=True)

    vecs: list[np.ndarray] = []
    rows: list[dict] = []

    def add(cid, emb, meta, doc, kind, note_key, source, in_dist):
        vecs.append(np.asarray(emb, dtype=np.float32))
        rows.append(
            {
                "id": cid,
                "kind": kind,
                "note_key": note_key,
                "source": source,
                "in_dist": in_dist,
                "title": str((meta or {}).get("title", "")),
                "source_path": str((meta or {}).get("source_path", "")),
                "text": (doc or "")[:TEXT_PREFIX],
            }
        )

    inc = ["embeddings", "metadatas", "documents"]

    v = store._videos_collection().get(include=inc)
    for cid, emb, meta, doc in zip(v["ids"], v["embeddings"], v["metadatas"], v["documents"]):
        vid = str((meta or {}).get("video_id", cid.split("#")[0]))
        add(cid, emb, meta, doc, "video", f"vid::{vid}", "youtube", True)

    s = store._segments_collection().get(include=inc)
    for cid, emb, meta, doc in zip(s["ids"], s["embeddings"], s["metadatas"], s["documents"]):
        vid = str((meta or {}).get("video_id", cid.rsplit("_", 1)[0]))
        add(cid, emb, meta, doc, "segment", f"vid::{vid}", "youtube", True)

    m = store._memories_collection().get(include=inc)
    for cid, emb, meta, doc in zip(m["ids"], m["embeddings"], m["metadatas"], m["documents"]):
        doc_id = str((meta or {}).get("doc_id", cid))
        base = doc_id.split("#")[0]
        content = base.startswith(allow)
        source = base.split("_", 3)[2] if content else "vault"
        add(cid, emb, meta, doc, "memory", f"mem::{base}", source, content)

    X = np.stack(vecs)
    X /= np.maximum(np.linalg.norm(X, axis=1, keepdims=True), 1e-9)

    seen: dict[str, int] = {}
    keep = []
    for i in range(len(X)):
        h = hashlib.sha1(np.round(X[i], 5).tobytes(), usedforsecurity=False).hexdigest()
        if h in seen:
            continue
        seen[h] = i
        keep.append(i)
    keep = np.asarray(keep)
    X = X[keep]
    rows = [rows[i] for i in keep]

    np.savez_compressed(OUT / "vectors.npz", X=X)
    with (OUT / "rows.jsonl").open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    from collections import Counter

    print("kept", X.shape, "dropped dup", len(vecs) - len(keep))
    print("by kind:", Counter(r["kind"] for r in rows))
    print("in-dist:", Counter(r["in_dist"] for r in rows))
    print("notes:", len({r["note_key"] for r in rows}))
    print("in-dist notes:", len({r["note_key"] for r in rows if r["in_dist"]}))


if __name__ == "__main__":
    main()
