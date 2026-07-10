"""ChromaDB vector store for ytk — video-level and segment-level embeddings."""

from __future__ import annotations

import logging
import os
import re
import warnings
from dataclasses import dataclass
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

# Model is cached locally — no network calls needed. Suppresses the
# "unauthenticated requests" warning from huggingface_hub.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", message=".*unauthenticated.*")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")

from .enrich import Enrichment


_CHROMA_PATH = Path(os.environ.get("CHROMA_PATH", str(Path.home() / ".ytk" / "chroma"))).expanduser()
_COLLECTION_VIDEOS = "ytk_videos"
_COLLECTION_SEGMENTS = "ytk_segments"
_COLLECTION_MEMORIES = "ytk_memories"
_COLLECTION_VISUAL = "ytk_visual"
_COLLECTION_VISUAL_PENDING = "ytk_visual_pending"

_client: chromadb.PersistentClient | None = None
_ef: embedding_functions.SentenceTransformerEmbeddingFunction | None = None


def _get_client() -> chromadb.PersistentClient:
    global _client
    if _client is None:
        _CHROMA_PATH.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(_CHROMA_PATH))
    return _client


_TEXT_MODEL = "thenlper/gte-small"


def _get_ef() -> embedding_functions.SentenceTransformerEmbeddingFunction:
    """
    Lazy-load the text embedding model (~130MB download on first use).
    gte-small replaced all-MiniLM-L6-v2 on 2026-07-05: same 384 dims and
    symmetric (no query prefix needed), but markedly stronger retrieval.
    Changing _TEXT_MODEL requires re-embedding every text collection —
    see experiments/migrate_embedder.py.
    """
    global _ef
    if _ef is None:
        _ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=_TEXT_MODEL
        )
    return _ef


def _videos_collection() -> chromadb.Collection:
    return _get_client().get_or_create_collection(
        name=_COLLECTION_VIDEOS,
        embedding_function=_get_ef(),
        metadata={"hnsw:space": "cosine"},
    )


def _segments_collection() -> chromadb.Collection:
    return _get_client().get_or_create_collection(
        name=_COLLECTION_SEGMENTS,
        embedding_function=_get_ef(),
        metadata={"hnsw:space": "cosine"},
    )


def _memories_collection() -> chromadb.Collection:
    return _get_client().get_or_create_collection(
        name=_COLLECTION_MEMORIES,
        embedding_function=_get_ef(),
        metadata={"hnsw:space": "cosine"},
    )


def _visual_collection() -> chromadb.Collection:
    """SigLIP-2 image embeddings — vectors are precomputed by ytk.visual, so no
    embedding function is attached; querying by text here would be a bug."""
    return _get_client().get_or_create_collection(
        name=_COLLECTION_VISUAL,
        metadata={"hnsw:space": "cosine"},
    )


@dataclass
class VisualResult:
    item_id: str
    source: str
    title: str
    url: str
    image_path: str
    note_path: str
    distance: float


def upsert_visual(item_id: str, embedding: list[float], metadata: dict) -> None:
    """Store one precomputed SigLIP-2 vector for a saved item's cover."""
    _visual_collection().upsert(
        ids=[item_id],
        embeddings=[embedding],
        metadatas=[metadata],
    )


def visual_count() -> int:
    return _visual_collection().count()


def visual_ids() -> set[str]:
    """All item_ids already present in the visual collection."""
    return set(_visual_collection().get(include=[])["ids"])


def _visual_pending_collection() -> chromadb.Collection:
    """SigLIP-2 embeddings of pending-queue covers, keyed by item url.

    Separate from ytk_visual so ingested-library search stays clean; entries
    live exactly as long as their item stays in the pending queue."""
    return _get_client().get_or_create_collection(
        name=_COLLECTION_VISUAL_PENDING,
        metadata={"hnsw:space": "cosine"},
    )


def pending_visual_ids() -> set[str]:
    return set(_visual_pending_collection().get(include=[])["ids"])


def upsert_pending_visual(url: str, embedding: list[float], metadata: dict) -> None:
    _visual_pending_collection().upsert(
        ids=[url], embeddings=[embedding], metadatas=[metadata]
    )


def delete_pending_visual(urls: list[str]) -> None:
    if urls:
        _visual_pending_collection().delete(ids=urls)


def pending_visual_similar(embedding: list[float], n: int = 30) -> list[VisualResult]:
    """Nearest pending-queue covers to a SigLIP vector (image or text tower)."""
    col = _visual_pending_collection()
    if col.count() == 0:
        return []
    res = col.query(query_embeddings=[embedding], n_results=min(n, col.count()))
    return [
        VisualResult(
            item_id=rid,
            source=meta.get("source", ""),
            title=meta.get("title", ""),
            url=rid,
            image_path=meta.get("image_path", ""),
            note_path="",
            distance=dist,
        )
        for rid, meta, dist in zip(
            res["ids"][0], res["metadatas"][0], res["distances"][0]
        )
    ]


def get_visual_embedding(item_id: str) -> list[float] | None:
    res = _visual_collection().get(ids=[item_id], include=["embeddings"])
    if not res["ids"]:
        return None
    return list(res["embeddings"][0])


def visual_similar(
    item_id: str | None = None,
    embedding: list[float] | None = None,
    n: int = 10,
) -> list[VisualResult]:
    """Nearest covers by SigLIP-2 cosine distance. Query by stored id or raw
    vector (image or text-tower — same space). Excludes the query item."""
    col = _visual_collection()
    if col.count() == 0:
        return []
    if embedding is None:
        if item_id is None:
            raise ValueError("visual_similar needs item_id or embedding")
        embedding = get_visual_embedding(item_id)
        if embedding is None:
            return []
    res = col.query(
        query_embeddings=[embedding],
        n_results=min(n + 1, col.count()),
    )
    out: list[VisualResult] = []
    for rid, meta, dist in zip(
        res["ids"][0], res["metadatas"][0], res["distances"][0]
    ):
        if rid == item_id:
            continue
        out.append(VisualResult(
            item_id=rid,
            source=meta.get("source", ""),
            title=meta.get("title", ""),
            url=meta.get("url", ""),
            image_path=meta.get("image_path", ""),
            note_path=meta.get("note_path", ""),
            distance=dist,
        ))
    return out[:n]


_FM_RE = re.compile(r"^---\n.*?^---\n", re.DOTALL | re.MULTILINE)


def strip_frontmatter(text: str) -> str:
    """Strip YAML frontmatter block from markdown so only body text is indexed."""
    if not text.startswith("---"):
        return text
    m = _FM_RE.match(text)
    return text[m.end():].lstrip() if m else text


def upsert_doc(doc_id: str, text: str, metadata: dict) -> None:
    """Upsert arbitrary text into the memories collection."""
    _memories_collection().upsert(
        ids=[doc_id],
        documents=[text[:8000]],
        metadatas=[metadata],
    )


def delete_doc(doc_id: str) -> None:
    """Remove a document from the memories collection by ID."""
    try:
        _memories_collection().delete(ids=[doc_id])
    except Exception as exc:
        logging.getLogger(__name__).debug("delete_doc %s: %s", doc_id, exc)


def delete_video(video_id: str) -> None:
    """Remove a video's channel/insight parts and all its segment vectors.

    Videos are keyed `{video_id}#c` / `{video_id}#i`; segments carry a
    `video_id` metadata field, so they're purged by where-filter. Each
    collection fails independently so a partial index never blocks the rest.
    """
    log = logging.getLogger(__name__)
    try:
        _videos_collection().delete(ids=[f"{video_id}#c", f"{video_id}#i"])
    except Exception as exc:
        log.debug("delete_video parts %s: %s", video_id, exc)
    try:
        _segments_collection().delete(where={"video_id": video_id})
    except Exception as exc:
        log.debug("delete_video segments %s: %s", video_id, exc)


def delete_visual(item_ids: list[str]) -> None:
    """Remove cover embeddings from the visual collection by item id."""
    if not item_ids:
        return
    try:
        _visual_collection().delete(ids=item_ids)
    except Exception as exc:
        logging.getLogger(__name__).debug("delete_visual %s: %s", item_ids, exc)


@dataclass
class VideoResult:
    video_id: str
    title: str
    url: str
    uploader: str
    date: str
    tags: list[str]
    thesis: str
    summary: str
    distance: float


@dataclass
class SegmentResult:
    video_id: str
    title: str
    url: str
    start: float
    text: str
    timestamp_url: str
    distance: float


def upsert(meta: dict, enrichment: Enrichment, segments: list[dict]) -> None:
    """
    Embed and store a video at both granularities:
      - ytk_videos: one document = summary + key concepts (for ytk search)
      - ytk_segments: one document per ~60s block (for future ytk dive)
    Safe to call multiple times — upsert overwrites on matching ID.
    """
    video_id: str = meta["id"]
    title: str = meta.get("title", "")

    # --- video-level ---
    # Embedded as PARTS, not one concatenated doc: the embedder (gte-small)
    # hard-truncates at 512 tokens, and a single thesis+summary+insights+
    # concepts doc measurably overflows that window, silently dropping the
    # entity-dense tail (2026-07 enrichment audit). Part ids: the plain
    # video_id is the representative vector (thesis+summary) that clustering,
    # tag counts, the map, and the graph consume; '#'-suffixed parts exist for
    # retrieval only and are collapsed by video_id at query time. Each extra
    # part is prefixed with title+thesis as situating context (contextual
    # retrieval: naked fragments match vague queries poorly).
    context = f"{title}. {enrichment.thesis}"
    parts: dict[str, str] = {
        video_id: enrichment.thesis + "\n\n" + enrichment.summary,
    }
    if enrichment.key_concepts:
        parts[f"{video_id}#c"] = (
            context + "\n\nKey concepts: " + ", ".join(enrichment.key_concepts)
        )
    moments_text = "; ".join(m.description for m in enrichment.key_moments)
    insights_text = " ".join(enrichment.insights)
    if insights_text or moments_text:
        parts[f"{video_id}#i"] = (
            context
            + ("\n\nInsights: " + insights_text if insights_text else "")
            + ("\n\nKey moments: " + moments_text if moments_text else "")
        )
    part_meta = {
        "video_id": video_id,
        "title": title,
        "url": meta.get("url", ""),
        "uploader": meta.get("uploader", ""),
        "date": meta.get("upload_date", ""),
        "tags": ", ".join(enrichment.interest_tags),
        "thesis": enrichment.thesis,
        "summary": enrichment.summary,
    }
    _videos_collection().upsert(
        ids=list(parts.keys()),
        documents=list(parts.values()),
        metadatas=[dict(part_meta) for _ in parts],
    )

    # --- segment-level (60s blocks, mirrors vault.py grouping) ---
    if not segments:
        return

    seg_ids: list[str] = []
    seg_docs: list[str] = []
    seg_metas: list[dict] = []

    block_texts: list[str] = []
    block_start: float = segments[0]["start"]
    window = 60.0
    block_index = 0

    def _flush(start: float, texts: list[str], idx: int) -> None:
        seg_ids.append(f"{video_id}_{idx}")
        seg_docs.append(" ".join(texts))
        seg_metas.append({
            "video_id": video_id,
            "title": title,
            "url": meta.get("url", ""),
            "start": start,
            "timestamp_url": f"https://youtu.be/{video_id}?t={int(start)}",
        })

    for seg in segments:
        if seg["start"] - block_start >= window and block_texts:
            _flush(block_start, block_texts, block_index)
            block_index += 1
            block_texts = []
            block_start = seg["start"]
        block_texts.append(seg["text"])

    if block_texts:
        _flush(block_start, block_texts, block_index)

    if seg_ids:
        _segments_collection().upsert(
            ids=seg_ids,
            documents=seg_docs,
            metadatas=seg_metas,
        )


def _collapse_by_video(metas: list[dict], dists: list[float]) -> list[tuple[dict, float]]:
    """Collapse part hits to one per video, keeping the best (first) distance.

    Chroma returns hits in ascending distance, so the first occurrence of a
    video_id is its max-sim part; later parts of the same video are dropped.
    """
    seen: set[str] = set()
    out: list[tuple[dict, float]] = []
    for meta, dist in zip(metas, dists):
        vid = meta["video_id"]
        if vid in seen:
            continue
        seen.add(vid)
        out.append((meta, dist))
    return out


def search_videos(query: str, n: int = 5) -> list[VideoResult]:
    """Search video-level collection. Returns up to n matches ranked by cosine similarity."""
    col = _videos_collection()
    if col.count() == 0:
        return []

    # over-fetch: a video may match on up to 3 parts that collapse to one hit
    results = col.query(query_texts=[query], n_results=min(n * 3, col.count()))
    out: list[VideoResult] = []
    for meta, dist in _collapse_by_video(results["metadatas"][0], results["distances"][0])[:n]:
        out.append(VideoResult(
            video_id=meta["video_id"],
            title=meta["title"],
            url=meta["url"],
            uploader=meta["uploader"],
            date=meta["date"],
            tags=meta["tags"].split(", ") if meta["tags"] else [],
            thesis=meta.get("thesis", ""),
            summary=meta["summary"],
            distance=dist,
        ))
    return out


def search_segments(query: str, video_id: str | None = None, n: int = 10) -> list[SegmentResult]:
    """
    Search segment-level collection. Optionally filter to a specific video_id.
    Used by the future `ytk dive` command.
    """
    col = _segments_collection()
    if col.count() == 0:
        return []

    where = {"video_id": video_id} if video_id else None
    kwargs: dict = {"query_texts": [query], "n_results": min(n, col.count())}
    if where:
        kwargs["where"] = where

    results = col.query(**kwargs)
    out: list[SegmentResult] = []
    for meta, doc, dist in zip(
        results["metadatas"][0], results["documents"][0], results["distances"][0]
    ):
        out.append(SegmentResult(
            video_id=meta["video_id"],
            title=meta["title"],
            url=meta["url"],
            start=meta["start"],
            text=doc,
            timestamp_url=meta["timestamp_url"],
            distance=dist,
        ))
    return out


@dataclass
class UnifiedResult:
    type: str
    doc_id: str
    title: str
    excerpt: str
    source: str
    distance: float


def upsert_memory(doc_id: str, text: str, tags: list[str], source_path: str) -> None:
    """Embed and store an arbitrary memory note in the ytk_memories collection.

    Text is truncated to 8000 characters via upsert_doc.
    """
    upsert_doc(doc_id, text, {
        "doc_id": doc_id,
        "tags": ", ".join(tags),
        "source_path": source_path,
    })


def search_all(query: str, n: int = 5) -> list[UnifiedResult]:
    """Semantic search across video summaries and memory notes, merged by distance."""
    out: list[UnifiedResult] = []

    vcol = _videos_collection()
    if vcol.count() > 0:
        vr = vcol.query(query_texts=[query], n_results=min(n * 3, vcol.count()))
        for meta, dist in _collapse_by_video(vr["metadatas"][0], vr["distances"][0])[:n]:
            out.append(UnifiedResult(
                type="video",
                doc_id=meta["video_id"],
                title=meta["title"],
                excerpt=meta.get("thesis", meta["summary"])[:200],
                source=meta["url"],
                distance=dist,
            ))

    mcol = _memories_collection()
    if mcol.count() > 0:
        mr = mcol.query(query_texts=[query], n_results=min(n, mcol.count()))
        for meta, doc, dist in zip(mr["metadatas"][0], mr["documents"][0], mr["distances"][0]):
            out.append(UnifiedResult(
                type="memory",
                doc_id=meta["doc_id"],
                title=meta["doc_id"],
                excerpt=doc[:200],
                source=meta["source_path"],
                distance=dist,
            ))

    out.sort(key=lambda r: r.distance)
    return out[:n]


def top_tags(n: int = 40) -> list[str]:
    """Existing tag vocabulary, most-used first, from indexed metadata.

    Frequency ranking makes the canonical spelling win: the common variant of
    a drifting pair (3d-printing vs 3dprint) reaches the vocabulary, the rare
    one does not, so enrichment converges on the winner.
    """
    return [t for t, _ in tag_counts().most_common(n)]


def tag_counts() -> "Counter[str]":
    """Tag -> usage count over enrichment-produced interest_tags.

    Videos collection only: the memories collection's tags metadata holds
    folder path segments (vault_write / reindex derive tags from the note's
    directory), which are structural labels, not interest tags. Feeding those
    into the enrichment vocabulary would teach it to tag content "inbox".
    """
    from collections import Counter

    counts: Counter[str] = Counter()
    col = _videos_collection()
    if col.count():
        res = col.get(include=["metadatas"])
        for doc_id, meta in zip(res["ids"], res["metadatas"]):
            if "#" in doc_id:  # retrieval-only part; count each video once
                continue
            for tag in (meta.get("tags") or "").split(", "):
                if tag:
                    counts[tag] += 1
    return counts


def get_all_videos() -> list[dict]:
    """Return every video-level record with its embedding and enrichment metadata.

    Each item: {id, title, thesis, summary, tags(list[str]), embedding(list[float])}.
    Used by the synthesis engine for clustering. Returns [] when empty.
    """
    col = _videos_collection()
    if col.count() == 0:
        return []
    res = col.get(include=["embeddings", "metadatas"])
    out: list[dict] = []
    for vid, emb, meta in zip(res["ids"], res["embeddings"], res["metadatas"]):
        if "#" in vid:  # retrieval-only part; one representative vector per video
            continue
        tags = meta.get("tags", "")
        out.append({
            "id": vid,
            "title": meta.get("title", ""),
            "thesis": meta.get("thesis", ""),
            "summary": meta.get("summary", ""),
            "tags": tags.split(", ") if tags else [],
            "embedding": list(emb),
        })
    return out


_THESIS_RE = re.compile(r"##\s*Thesis\s*\n(.+?)(?:\n##|\Z)", re.DOTALL)


def _extract_thesis(document: str) -> str:
    """Pull the text under a '## Thesis' heading from a stored note body, else a short prefix."""
    m = _THESIS_RE.search(document or "")
    if m:
        return m.group(1).strip()
    return (document or "").strip()[:200]


def get_content_memories(prefixes: list[str]) -> list[dict]:
    """Return memory docs whose doc_id starts with one of the given prefixes (+ '_').

    Each item: {id, title, thesis, summary, tags(list[str]), embedding(list[float])}.
    title is '' (memories have no separate title); thesis is extracted from the
    stored note body's '## Thesis' section. Used by the synthesis engine so the
    interest profile reflects ingested reels/TikToks/articles, not just YouTube.
    Returns [] when empty.
    """
    col = _memories_collection()
    if col.count() == 0:
        return []
    allow = tuple(f"{p}_" for p in prefixes)
    res = col.get(include=["embeddings", "metadatas", "documents"])
    out: list[dict] = []
    for mid, emb, meta, doc in zip(
        res["ids"], res["embeddings"], res["metadatas"], res["documents"]
    ):
        doc_id = meta.get("doc_id", mid)
        if not doc_id.startswith(allow):
            continue
        tags = meta.get("tags", "")
        out.append({
            "id": mid,
            "title": "",
            "thesis": _extract_thesis(doc),
            "summary": "",
            "tags": tags.split(", ") if tags else [],
            "embedding": list(emb),
            "source_path": meta.get("source_path", ""),
        })
    return out
