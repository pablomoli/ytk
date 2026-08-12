"""One-note Gemma-Scope fingerprint for the dark-matter video note (section 34 input).

Mirrors scripts/sae_batch.py: same SAE (gemma-scope-2b-pt-res layer 20 16k),
same hook, same MAX_CHARS=2000 truncation of the stored Chroma document, so the
result is comparable with 18-sae-fingerprints/fingerprints.npz rows.
"""

import sys
import time
from pathlib import Path

import numpy as np

REPO = Path("/Users/melocoton/Developer/ytk")
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO))

OUT = Path(__file__).parent / "darkmatter-fingerprint.npz"
VIDEO_ID = "UGO_Ehywuxc"
MAX_CHARS = 2000

from ytk import store

col = store._videos_collection()
res = col.get(include=["metadatas", "documents", "embeddings"])
idx = next(
    i
    for i, m in enumerate(res["metadatas"])
    if VIDEO_ID in str(m.get("video_id", "")) or VIDEO_ID in str(res["ids"][i])
)
doc = res["documents"][idx]
emb = np.asarray(res["embeddings"][idx], dtype=np.float32)
title = res["metadatas"][idx].get("title", "?")
print(f"note: {title!r}  doc chars={len(doc)}  qwen dim={emb.shape}", flush=True)

from sae_batch import encode_sums, load_rig

t0 = time.time()
model, sae_module = load_rig("mps")
print(f"rig loaded in {time.time() - t0:.0f}s", flush=True)

t1 = time.time()
sums, maxs, n_tok = encode_sums(model, sae_module, doc[:MAX_CHARS])
print(f"encoded {n_tok} tokens in {time.time() - t1:.0f}s", flush=True)

np.savez_compressed(
    OUT,
    sum=np.asarray(sums, dtype=np.float16),
    max=np.asarray(maxs, dtype=np.float16),
    qwen=emb,
    tokens=np.int32(n_tok),
)
print(f"saved -> {OUT}", flush=True)
