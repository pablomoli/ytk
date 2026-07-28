#!/usr/bin/env python
"""Do the enrichment's interest_tags carve real regions of embedding space?

Every ingested note gets `interest_tags` from enrichment — `ai`, `creative-coding`,
`self-improvement`, and a long tail. Nobody has checked whether a tag names a
genuine neighbourhood or is a label sprayed across unrelated things. Issue #37
("enrichment mis-tags non-technical content with canonical vocab") is that
suspicion; this makes it a measurement.

The test, per tag: mean pairwise cosine similarity between the notes carrying it,
against a null of same-size random note sets drawn from the same corpus. Size
matching matters — a 4-note tag is cohesive by accident far more easily than a
200-note tag, so the raw mean is unusable and the z-score against a size-matched
null is the only comparable number.

STRICTLY READ-ONLY. Reads note frontmatter and calls Chroma `get()`. It never
upserts, deletes, reindexes, or writes a single byte into the vault. Output goes
to docs/assets/10-tag-coherence/ in the repo.

    harvest -> vectors.npz + tags.json
    analyze -> results.json
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ASSETS = Path(__file__).resolve().parent.parent / "docs" / "assets" / "10-tag-coherence"
VECTORS = ASSETS / "vectors.npz"
TAGS = ASSETS / "tags.json"
RESULTS = ASSETS / "results.json"

SEED = 20260728
NULL_DRAWS = 400
MIN_NOTES = 6  # below this a tag's cohesion is dominated by which notes, not the tag


def parse_frontmatter_tags(text: str) -> list[str]:
    """Pull the YAML `tags:` list out of a note's frontmatter.

    Handles both block form (``tags:\\n  - ai``) and inline (``tags: [ai, go]``),
    because the vault has both depending on which writer produced the note.
    """
    fm = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not fm:
        return []
    body = fm.group(1)
    inline = re.search(r"^tags:\s*\[(.*?)\]", body, re.MULTILINE)
    if inline:
        return [t.strip().strip("'\"") for t in inline.group(1).split(",") if t.strip()]
    block = re.search(r"^tags:\s*\n((?:\s+-\s*.+\n?)+)", body, re.MULTILINE)
    if block:
        return [
            line.strip().lstrip("-").strip().strip("'\"")
            for line in block.group(1).splitlines()
            if line.strip()
        ]
    return []


def harvest() -> None:
    """Join note tags to their stored vectors. Read-only on both sides."""
    from ytk import store
    from ytk.vault import _get_brain_path

    ASSETS.mkdir(parents=True, exist_ok=True)
    brain = _get_brain_path()

    # tags by note path, for every ingested content note
    by_path: dict[str, list[str]] = {}
    for note in (brain / "sources").rglob("*.md"):
        tags = parse_frontmatter_tags(note.read_text(encoding="utf-8", errors="ignore"))
        if tags:
            by_path[str(note)] = tags
    print(f"{len(by_path)} notes carry interest_tags")

    vecs: list[np.ndarray] = []
    labels: list[list[str]] = []
    names: list[str] = []
    sources: list[str] = []

    # youtube notes live in the videos collection, keyed by video_id, and their
    # metadata already carries interest_tags verbatim
    vids = store._videos_collection().get(include=["embeddings", "metadatas"])
    for emb, meta in zip(vids["embeddings"], vids["metadatas"]):
        tags = [t.strip() for t in str(meta.get("tags", "")).split(",") if t.strip()]
        if not tags:
            continue
        vecs.append(np.asarray(emb, dtype=np.float32))
        labels.append(tags)
        names.append(str(meta.get("title", meta.get("video_id", "")))[:80])
        sources.append("youtube")

    # everything else is in memories, joined back to the note by source_path
    mem = store._memories_collection().get(include=["embeddings", "metadatas"])
    for emb, meta in zip(mem["embeddings"], mem["metadatas"]):
        path = str(meta.get("source_path", ""))
        tags = by_path.get(path)
        if not tags:
            continue
        vecs.append(np.asarray(emb, dtype=np.float32))
        labels.append(tags)
        names.append(Path(path).stem[:80])
        sources.append(Path(path).parent.name)

    X = np.vstack(vecs)
    # cosine similarity is a dot product once rows are unit length
    X /= np.linalg.norm(X, axis=1, keepdims=True) + 1e-12
    np.savez_compressed(VECTORS, X=X)
    TAGS.write_text(json.dumps({"labels": labels, "names": names, "sources": sources}))
    counts = Counter(t for ts in labels for t in ts)
    print(f"{len(X)} notes with vectors  ·  {len(counts)} distinct tags")
    print(f"tags with >= {MIN_NOTES} notes: {sum(1 for c in counts.values() if c >= MIN_NOTES)}")
    print(f"-> {VECTORS.name}, {TAGS.name}")


def _mean_pairwise(sub: np.ndarray) -> float:
    """Mean off-diagonal cosine similarity of a unit-normed block."""
    if len(sub) < 2:
        return float("nan")
    gram = sub @ sub.T
    n = len(sub)
    return float((gram.sum() - np.trace(gram)) / (n * (n - 1)))


def analyze() -> dict:
    X = np.load(VECTORS)["X"]
    meta = json.loads(TAGS.read_text())
    labels = meta["labels"]
    rng = np.random.default_rng(SEED)

    counts = Counter(t for ts in labels for t in ts)
    keep = sorted([t for t, c in counts.items() if c >= MIN_NOTES], key=lambda t: -counts[t])
    index = {t: [i for i, ts in enumerate(labels) if t in ts] for t in keep}

    # one null distribution per distinct tag size, reused across tags of that size
    null_cache: dict[int, tuple[float, float]] = {}
    rows = []
    for tag in keep:
        idx = index[tag]
        obs = _mean_pairwise(X[idx])
        n = len(idx)
        if n not in null_cache:
            draws = [
                _mean_pairwise(X[rng.choice(len(X), size=n, replace=False)])
                for _ in range(NULL_DRAWS)
            ]
            null_cache[n] = (float(np.mean(draws)), float(np.std(draws)))
        mu, sd = null_cache[n]
        rows.append(
            {
                "tag": tag,
                "n": n,
                "cohesion": obs,
                "null_mean": mu,
                "null_sd": sd,
                "z": (obs - mu) / sd if sd > 0 else 0.0,
            }
        )

    rows.sort(key=lambda r: -r["z"])
    # centroid similarity between tags -- which labels are near-duplicates
    cents = {t: X[index[t]].mean(0) for t in keep}
    for t in cents:
        cents[t] /= np.linalg.norm(cents[t]) + 1e-12
    order = [r["tag"] for r in rows]
    C = np.array([cents[t] for t in order])
    overlap = C @ C.T

    results = {
        "seed": SEED,
        "null_draws": NULL_DRAWS,
        "min_notes": MIN_NOTES,
        "n_notes": len(X),
        "n_tags_total": len(counts),
        "n_tags_scored": len(rows),
        "tags": rows,
        "overlap_order": order,
        "overlap": np.round(overlap, 4).tolist(),
    }
    RESULTS.write_text(json.dumps(results, indent=1))
    sig = [r for r in rows if r["z"] > 2]
    print(f"scored {len(rows)} tags over {len(X)} notes")
    print(f"  {len(sig)} tags cohere beyond z=2; {sum(1 for r in rows if r['z'] < 2)} do not")
    print("  most coherent :", ", ".join(f"{r['tag']}(z={r['z']:.0f})" for r in rows[:5]))
    print("  least coherent:", ", ".join(f"{r['tag']}(z={r['z']:.1f})" for r in rows[-5:]))
    return results


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "harvest"
    if cmd == "harvest":
        harvest()
    elif cmd == "analyze":
        analyze()
    else:
        raise SystemExit(f"unknown phase: {cmd}")
