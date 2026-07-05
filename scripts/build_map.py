"""Build the second-brain embedding map (issue #20).

Pulls every text-space embedding (ytk_videos + ytk_memories, shared gte-small
384-dim space), assigns each point to the nearest interest-profile theme
centroid, joins signal levels r from disk, projects to 2D with UMAP, and
writes map.json for the /map hub page.

UMAP parameters are fitted, not eyeballed: --sweep scores every
(n_neighbors, min_dist) combo on trustworthiness (does the 2D layout preserve
local neighborhoods?) and theme silhouette (do the profile's themes appear as
visible structure?), then the chosen combo is passed explicitly for the final
build. Visual embeddings (1152-dim SigLIP space) are geometrically
incompatible and stay out per the E5 verdict; thumbnails join as hover
imagery only.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import chromadb
import numpy as np

from ytk import signals

SNAPSHOT = Path(os.path.expanduser("~/.ytk/interest/latest.json"))
CHROMA = os.path.expanduser("~/.ytk/chroma")
OUT = Path(__file__).resolve().parent.parent / "ytk" / "ui" / "static" / "map.json"

UNTHEMED_PERCENTILE = 25  # bottom quartile by centroid affinity renders as dust


def _normalize(m: np.ndarray) -> np.ndarray:
    return m / np.linalg.norm(m, axis=1, keepdims=True)


def load_points() -> tuple[np.ndarray, list[dict]]:
    client = chromadb.PersistentClient(path=CHROMA)
    vecs: list[np.ndarray] = []
    meta: list[dict] = []

    videos = client.get_collection("ytk_videos").get(
        include=["embeddings", "metadatas", "documents"]
    )
    for emb, m in zip(videos["embeddings"], videos["metadatas"]):
        vecs.append(np.asarray(emb))
        meta.append(
            {
                "kind": "video",
                "cat": "youtube",
                "title": m.get("title", ""),
                "url": m.get("url", ""),
                "date": m.get("date", ""),
                "video_id": m.get("video_id", ""),
            }
        )

    memories = client.get_collection("ytk_memories").get(
        include=["embeddings", "metadatas", "documents"]
    )
    for emb, m, doc in zip(
        memories["embeddings"], memories["metadatas"], memories["documents"]
    ):
        # memories tags metadata is folder path segments (operating guide
        # exhibit B) — the first segment is the note's source category
        segs = [t.strip() for t in (m.get("tags") or "").split(",") if t.strip()]
        cat = segs[0] if segs else "memory"
        title = doc.strip().splitlines()[0][:120] if doc else m.get("doc_id", "")
        meta.append(
            {
                "kind": "memory",
                "cat": cat,
                "title": title,
                "url": "",
                "date": (m.get("doc_id") or "")[7:17],
                "path": m.get("source_path", ""),
            }
        )
        vecs.append(np.asarray(emb))

    return np.vstack(vecs), meta


def assign_themes(vecs: np.ndarray, snapshot: dict) -> tuple[list[int], np.ndarray]:
    cents = _normalize(np.array([t["centroid"] for t in snapshot["themes"]]))
    sims = _normalize(vecs) @ cents.T
    best = sims.argmax(axis=1)
    conf = sims.max(axis=1)
    floor = np.percentile(conf, UNTHEMED_PERCENTILE)
    labels = [int(b) if c >= floor else -1 for b, c in zip(best, conf)]
    return labels, conf


def score_layout(xy: np.ndarray, vecs: np.ndarray, labels: list[int]) -> dict:
    from sklearn.manifold import trustworthiness
    from sklearn.metrics import silhouette_score

    themed = np.array(labels) >= 0
    return {
        "trustworthiness": float(
            trustworthiness(vecs, xy, n_neighbors=15, metric="cosine")
        ),
        "silhouette": float(
            silhouette_score(xy[themed], np.array(labels)[themed])
        ),
    }


def project(vecs: np.ndarray, n_neighbors: int, min_dist: float) -> np.ndarray:
    import umap

    return umap.UMAP(
        n_neighbors=n_neighbors,
        min_dist=min_dist,
        metric="cosine",
        random_state=42,
    ).fit_transform(vecs)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep", action="store_true", help="fit UMAP params first")
    ap.add_argument("--n-neighbors", type=int, default=30)
    ap.add_argument("--min-dist", type=float, default=0.1)
    args = ap.parse_args()

    snapshot = json.loads(SNAPSHOT.read_text())
    vecs, meta = load_points()
    labels, conf = assign_themes(vecs, snapshot)
    print(f"{len(meta)} points | themed: {sum(1 for l in labels if l >= 0)}")

    if args.sweep:
        results = []
        for nn in (10, 15, 30, 50, 100):
            for md in (0.05, 0.1, 0.3):
                xy = project(vecs, nn, md)
                s = score_layout(xy, vecs, labels)
                results.append((nn, md, s))
                print(f"nn={nn:>3} min_dist={md:.2f}  trust={s['trustworthiness']:.4f}  sil={s['silhouette']:.4f}")
        # pick: highest silhouette among combos within 0.01 trust of the best
        best_trust = max(s["trustworthiness"] for _, _, s in results)
        ok = [r for r in results if r[2]["trustworthiness"] >= best_trust - 0.01]
        nn, md, s = max(ok, key=lambda r: r[2]["silhouette"])
        print(f"\nchosen: n_neighbors={nn} min_dist={md} ({s})")
        args.n_neighbors, args.min_dist = nn, md

    xy = project(vecs, args.n_neighbors, args.min_dist)
    scores = score_layout(xy, vecs, labels)
    print(f"final layout: {scores}")

    smap = signals.signal_map()
    thumbs: dict[str, str] = {}
    client = chromadb.PersistentClient(path=CHROMA)
    for m in client.get_collection("ytk_visual").get(include=["metadatas"])["metadatas"]:
        if m.get("url") and m.get("image_path"):
            thumbs[m["url"]] = m["image_path"]

    xy -= xy.mean(axis=0)
    xy /= np.abs(xy).max()

    points = []
    for (x, y), m, lab, cf in zip(xy, meta, labels, conf):
        r = smap.get(m.get("video_id") or "", smap.get(m.get("path") or "", 0))
        points.append(
            {
                "x": round(float(x), 4),
                "y": round(float(y), 4),
                "t": m["title"],
                "k": m["kind"],
                "c": m["cat"],
                "u": m["url"],
                "d": m["date"],
                "th": lab,
                "r": r,
                "img": bool(thumbs.get(m["url"])),
            }
        )

    theme_pos = []
    arr = np.array(labels)
    for i, t in enumerate(snapshot["themes"]):
        mask = arr == i
        cx, cy = (xy[mask].mean(axis=0) if mask.any() else (0.0, 0.0))
        theme_pos.append(
            {"label": t["label"], "weight": t["weight"], "x": round(float(cx), 4), "y": round(float(cy), 4)}
        )

    OUT.write_text(
        json.dumps(
            {
                "generated": snapshot["generated_at"],
                "params": {
                    "n_neighbors": args.n_neighbors,
                    "min_dist": args.min_dist,
                    **scores,
                },
                "themes": theme_pos,
                "points": points,
            }
        )
    )
    print(f"wrote {OUT} ({len(points)} points)")


if __name__ == "__main__":
    main()
