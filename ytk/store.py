"""ChromaDB vector store for ytk — video-level and segment-level embeddings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import logging
import os

import chromadb
from chromadb.utils import embedding_functions

# Suppress noisy model-load output from sentence-transformers / transformers / HF
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")

from .enrich import Enrichment


_CHROMA_PATH = Path(os.environ.get("CHROMA_PATH", str(Path.home() / ".ytk" / "chroma"))).expanduser()
_COLLECTION_VIDEOS = "ytk_videos"
_COLLECTION_SEGMENTS = "ytk_segments"
_COLLECTION_MEMORIES = "ytk_memories"

_client: chromadb.PersistentClient | None = None
_ef: embedding_functions.SentenceTransformerEmbeddingFunction | None = None


def _get_client() -> chromadb.PersistentClient:
    global _client
    if _client is None:
        _CHROMA_PATH.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(_CHROMA_PATH))
    return _client


def _get_ef() -> embedding_functions.SentenceTransformerEmbeddingFunction:
    """
    Lazy-load the embedding model (all-MiniLM-L6-v2, ~100MB download on first use).
    Fast on M-series Macs via MPS after the initial download.
    """
    global _ef
    if _ef is None:
        _ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
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


def strip_frontmatter(text: str) -> str:
    """Strip YAML frontmatter block from markdown so only body text is indexed."""
    if not text.startswith("---"):
        return text
    end = text.find("---", 3)
    return text[end + 3:].lstrip() if end != -1 else text


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
    except Exception:
        pass


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
    # Combine thesis + summary + insights + key concepts for richer semantic search.
    insights_text = " ".join(enrichment.insights)
    video_doc = (
        enrichment.thesis
        + "\n\n" + enrichment.summary
        + "\n\nInsights: " + insights_text
        + "\n\nKey concepts: " + ", ".join(enrichment.key_concepts)
    )
    _videos_collection().upsert(
        ids=[video_id],
        documents=[video_doc],
        metadatas=[{
            "video_id": video_id,
            "title": title,
            "url": meta.get("url", ""),
            "uploader": meta.get("uploader", ""),
            "date": meta.get("upload_date", ""),
            "tags": ", ".join(enrichment.interest_tags),
            "thesis": enrichment.thesis,
            "summary": enrichment.summary,
        }],
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


def search_videos(query: str, n: int = 5) -> list[VideoResult]:
    """Search video-level collection. Returns up to n matches ranked by cosine similarity."""
    col = _videos_collection()
    if col.count() == 0:
        return []

    results = col.query(query_texts=[query], n_results=min(n, col.count()))
    out: list[VideoResult] = []
    for meta, dist in zip(results["metadatas"][0], results["distances"][0]):
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
    """Embed and store an arbitrary memory note in the ytk_memories collection."""
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
        vr = vcol.query(query_texts=[query], n_results=min(n, vcol.count()))
        for meta, dist in zip(vr["metadatas"][0], vr["distances"][0]):
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
