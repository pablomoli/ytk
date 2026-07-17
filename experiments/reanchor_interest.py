"""Re-anchor interest-snapshot centroids into the active embedding epoch.

Run AFTER the epoch cutover (store.EMBEDDING_EPOCH flipped): theme identity
is preserved exactly — same ids, labels, weights, note_ids, profile text —
only the centroid geometry is recomputed as the unit-mean of each theme's
member vectors in the new space. Membership IS identity here; centroid
matching (TTEC-style) is only the fallback for snapshots without note_ids.

The re-anchored snapshot records embedding_model and reanchored_from so the
interest time series (#83) shows an epoch boundary, not a fake taste event.

  uv run python experiments/reanchor_interest.py [--dry-run]
"""

import argparse
import json
import time
from datetime import datetime, timezone

import numpy as np

from ytk import interest, ops, store


def _fetch_vectors(ids: list[str]) -> dict[str, np.ndarray]:
    """id -> unit vector from the active epoch's videos/memories collections."""
    out: dict[str, np.ndarray] = {}
    for col in (store._videos_collection(), store._memories_collection()):
        got = col.get(ids=ids, include=["embeddings"])
        for rid, emb in zip(got["ids"], got["embeddings"]):
            v = np.asarray(emb, dtype=np.float32)
            out[rid] = v / max(float(np.linalg.norm(v)), 1e-12)
    return out


def _recentroid(note_ids: list[str], vecs: dict[str, np.ndarray],
                label: str) -> tuple[list[float] | None, int]:
    found = [vecs[i] for i in note_ids if i in vecs]
    if not found:
        print(f"  {label}: 0/{len(note_ids)} members found — centroid dropped")
        return None, 0
    cent = np.mean(found, axis=0)
    cent /= max(float(np.linalg.norm(cent)), 1e-12)
    return [round(float(x), 6) for x in cent], len(found)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    snap = interest.load_latest()
    if snap is None:
        raise SystemExit("no interest snapshot to re-anchor")
    model = store._EPOCHS[store.EMBEDDING_EPOCH]["model"]
    if snap.embedding_model == model:
        print(f"latest snapshot already anchored to {model}; nothing to do")
        return

    all_ids = sorted({i for t in snap.themes for i in t.note_ids}
                     | (set(snap.explicit.note_ids) if snap.explicit else set()))
    vecs = _fetch_vectors(all_ids)
    print(f"re-anchoring {len(snap.themes)} themes over {len(all_ids)} notes "
          f"({len(vecs)} resolvable) into {model}")

    report = []
    for t in snap.themes:
        cent, found = _recentroid(t.note_ids, vecs, t.label)
        report.append(f"{t.label}: {found}/{len(t.note_ids)}")
        if not args.dry_run:
            t.centroid = cent
    if snap.explicit and not args.dry_run:
        cent, _ = _recentroid(snap.explicit.note_ids, vecs, "explicit channel")
        if cent is not None:
            snap.explicit.centroid = cent
    print("; ".join(report))

    if args.dry_run:
        return
    snap.reanchored_from = snap.generated_at
    snap.embedding_model = model
    snap.generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    path = interest.save_snapshot(snap, time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()))
    ops.journal(f"interest snapshot re-anchored to {model}: {path.name}")
    print(f"saved {path}")


if __name__ == "__main__":
    main()
