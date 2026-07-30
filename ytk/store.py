# pyright: basic
# Not strict-clean yet (#122). Delete these two lines once the module
# passes strict — the list of files carrying them only shrinks.
"""ChromaDB vector store for ytk — video-level and segment-level embeddings."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import warnings
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TypeVar

import chromadb
from chromadb.api import ClientAPI
from chromadb.api.types import Metadata, Where
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

from datetime import UTC

from .chroma_runtime import create_client, runtime_config
from .enrich import Enrichment

_CHROMA_PATH = Path(
    os.environ.get("CHROMA_PATH", str(Path.home() / ".ytk" / "chroma"))
).expanduser()
_T = TypeVar("_T")
_COLLECTION_VISUAL = "ytk_visual"
_COLLECTION_VISUAL_PENDING = "ytk_visual_pending"

# Text-embedding epochs (spec: docs/superpowers/specs/2026-07-16-encoder-migration-qwen3.md).
# Embeddings are frozen at write time, so a model change is a new epoch: fresh
# collections, one migration pass, never two geometries in one collection.
# Cutover is flipping EMBEDDING_EPOCH in one commit (Phase 2 step 4); v1
# collections stay intact for rollback.
_EPOCHS: dict[str, dict] = {
    "v1": {
        # gte-small: 384d, symmetric (no query prefix), 512-token window —
        # docs must be split into parts or the window silently drops tails.
        "model": "thenlper/gte-small",
        "query_prefix": "",
        "suffix": "",
        "parts": True,
        "fp16": False,
        "max_seq": 0,
        "revision": None,
    },
    "v2": {
        # Qwen3-Embedding-0.6B: 1024d native, instruction-aware (docs embed
        # plain, queries get the retrieval prefix), 32k native window. The
        # MPS runtime uses max_seq 3072; overflow notes get retrieval parts.
        # fp16 + max_seq 3072 are mandatory on MPS:
        # fp32 whole-doc runs get SIGKILLed by macOS memory pressure.
        "model": "Qwen/Qwen3-Embedding-0.6B",
        "query_prefix": (
            "Instruct: Given a web search query, retrieve relevant passages "
            "that answer the query\nQuery: "
        ),
        "suffix": "_v2",
        "parts": False,
        "fp16": True,
        "max_seq": 3072,
        # Pin the exact encoder snapshot used to build the v2 collections;
        # otherwise a mutable Hub model silently invalidates eval baselines.
        "revision": "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3",
        # encode few docs at a time: attention scores for a batch of
        # max_seq-long docs are batch*heads*3072^2 fp16 — 32 at once asks
        # Metal for a 10 GB buffer and SIGABRTs (migration night finding)
        "encode_batch": 4,
    },
}
EMBEDDING_EPOCH = "v2"

# Stamped into garden/map artifacts (dendro compares stamps to detect engine
# changes); resolves from the active epoch so a cutover invalidates caches.
_TEXT_MODEL = _EPOCHS[EMBEDDING_EPOCH]["model"]

_COLLECTION_VIDEOS = "ytk_videos"
_COLLECTION_SEGMENTS = "ytk_segments"
_COLLECTION_MEMORIES = "ytk_memories"

_client: ClientAPI | None = None
_efs: dict[str, embedding_functions.EmbeddingFunction] = {}


def _get_client() -> ClientAPI:
    global _client
    if _client is None:
        _client = create_client(runtime_config(default_path=_CHROMA_PATH))
    return _client


# --- Chroma result accessors -------------------------------------------------
# Two invariants hold wherever ytk reads a Get/Query result, and neither is
# expressible in Chroma's own types. Stating them here keeps them out of the
# ~50 read sites below — and out of graph, tags, retrieval_gate and the hub
# server, which read the same collections and so share these accessors.


def chroma_field(value: _T | None, field: str) -> _T:
    """A result field the caller's `include=` asked for, hence not None.

    Chroma types every field of a Get/Query result as optional because
    `include=` decides which come back. A None here means the `include=` list
    and the read below it have drifted apart, which is a caller bug — so say
    that, rather than failing later on an unrelated TypeError.
    """
    if value is None:
        raise KeyError(f"chroma result is missing {field!r}: check the include= list")
    return value


def meta_str(meta: Metadata | None, key: str, default: str = "") -> str:
    """One metadata value as the string ytk stored.

    Chroma widens every metadata value to str|int|float|bool|SparseVector|None
    because the store accepts all of them. ytk only ever writes strings, so a
    non-string here is data written by something else; fall back rather than
    propagate a surprise type into a dataclass field.
    """
    value = (meta or {}).get(key, default)
    return value if isinstance(value, str) else default


def meta_float(meta: Metadata | None, key: str, default: float = 0.0) -> float:
    """One numeric metadata value, for the few fields ytk stores as numbers.

    Same widening as meta_str; bool is excluded deliberately, since it is a
    subclass of int and a flag read as a coordinate would be a silent wrong
    answer rather than a loud one.
    """
    value = (meta or {}).get(key, default)
    return (
        float(value) if isinstance(value, int | float) and not isinstance(value, bool) else default
    )


@embedding_functions.register_embedding_function
class InstructionAwareEF(embedding_functions.EmbeddingFunction):
    """Embedding function for instruction-aware retrieval models (Qwen3).

    __call__ embeds plain — that is the document path, and it is also correct
    for doc-to-doc similarity queries (graph.py queries with document text via
    query_texts, which routes through here). User queries must NOT take this
    path: chroma's EF protocol exposes only one call, so search functions
    embed queries via embed_query() and pass query_embeddings explicitly.
    """

    def __init__(
        self,
        model_name: str,
        query_prefix: str,
        fp16: bool = True,
        max_seq: int = 0,
        device: str | None = None,
        encode_batch: int = 32,
        revision: str | None = None,
    ):
        self._model_name = model_name
        self._query_prefix = query_prefix
        self._fp16 = fp16
        self._max_seq = max_seq
        self._device = device  # None = auto (MPS); tests pass "cpu"
        self._encode_batch = encode_batch
        self._revision = revision
        self._model = None

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            kwargs = {}
            if self._fp16:
                import torch

                kwargs["model_kwargs"] = {"torch_dtype": torch.float16}
            if self._device:
                kwargs["device"] = self._device
            self._model = SentenceTransformer(self._model_name, revision=self._revision, **kwargs)
            if self._max_seq:
                self._model.max_seq_length = self._max_seq
        return self._model

    def __call__(self, input) -> list[list[float]]:
        embs = self._load().encode(
            list(input),
            batch_size=self._encode_batch,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [[float(x) for x in e] for e in embs]

    def embed_query(self, text: str) -> list[float]:
        return self([self._query_prefix + text])[0]

    @staticmethod
    def name() -> str:
        return "ytk-instruction-aware"

    def get_config(self) -> dict:
        return {
            "model_name": self._model_name,
            "query_prefix": self._query_prefix,
            "fp16": self._fp16,
            "max_seq": self._max_seq,
            "device": self._device,
            "encode_batch": self._encode_batch,
            "revision": self._revision,
        }

    @staticmethod
    def build_from_config(config: dict) -> InstructionAwareEF:
        return InstructionAwareEF(**config)


def _get_ef(epoch: str | None = None):
    """Lazy-load the text embedding function for an epoch (default: current).

    v1 keeps chroma's stock SentenceTransformerEmbeddingFunction — gte-small
    is symmetric, so queries and documents share one path. v2 is instruction-
    aware; see InstructionAwareEF. Changing a model means a new epoch and a
    full re-embed — see experiments/migrate_embedder.py.
    """
    epoch = epoch or EMBEDDING_EPOCH
    if epoch not in _efs:
        cfg = _EPOCHS[epoch]
        if cfg["query_prefix"]:
            _efs[epoch] = InstructionAwareEF(
                model_name=cfg["model"],
                query_prefix=cfg["query_prefix"],
                fp16=cfg["fp16"],
                max_seq=cfg["max_seq"],
                device=cfg.get("device"),
                encode_batch=cfg.get("encode_batch", 32),
                revision=cfg.get("revision"),
            )
        else:
            _efs[epoch] = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=cfg["model"]
            )
    return _efs[epoch]


def _embed_query(query: str, epoch: str | None = None) -> list[float]:
    """Embed a user search query for the epoch's collections.

    Instruction-aware epochs prefix the retrieval instruction; symmetric
    epochs produce exactly the vector chroma's query_texts path would.
    Search functions must pass this as query_embeddings — never query_texts,
    which would embed the query on the document path.
    """
    ef = _get_ef(epoch)
    # explicit isinstance, not duck typing: chroma's EF base class also
    # defines embed_query, but with list-in/list-out semantics
    if isinstance(ef, InstructionAwareEF):
        return ef.embed_query(query)
    return [float(x) for x in ef([query])[0]]


def warm_text_encoder() -> None:
    """Load the current epoch's model and run one encode (hub startup path).

    Cold start is ~7.4 s for Qwen3 on MPS (measured, Phase 0 pre-flight);
    lazy-loading would hang the first search after every hub restart.
    """
    _embed_query("warm up the index")


def epoch_collection_name(base: str, epoch: str | None = None) -> str:
    """Resolve a text-collection name for an epoch (default: current).

    External readers (build_map, dedupe_chroma) must use this instead of
    hardcoding names, or a cutover leaves them silently reading the retired
    geometry. Visual collections are epoch-free — SigLIP is untouched.
    """
    return base + _EPOCHS[epoch or EMBEDDING_EPOCH]["suffix"]


def _text_collection(base: str, epoch: str | None = None) -> chromadb.Collection:
    return _get_client().get_or_create_collection(
        name=epoch_collection_name(base, epoch),
        embedding_function=_get_ef(epoch),
        metadata={"hnsw:space": "cosine"},
    )


def _videos_collection(epoch: str | None = None) -> chromadb.Collection:
    return _text_collection(_COLLECTION_VIDEOS, epoch)


def _segments_collection(epoch: str | None = None) -> chromadb.Collection:
    return _text_collection(_COLLECTION_SEGMENTS, epoch)


def _memories_collection(epoch: str | None = None) -> chromadb.Collection:
    return _text_collection(_COLLECTION_MEMORIES, epoch)


def _visual_collection() -> chromadb.Collection:
    """SigLIP-2 image embeddings — vectors are precomputed by ytk.visual, so no
    embedding function is attached; querying by text here would be a bug."""
    return _get_client().get_or_create_collection(
        name=_COLLECTION_VISUAL,
        metadata={"hnsw:space": "cosine"},
    )


_VISUAL_PROBE: bool | None = None


def visual_index_enabled() -> bool:
    """Whether visual-index access is enabled for the current process."""
    return os.environ.get("YTK_VISUAL_INDEX", "on").strip().lower() != "off"


def _probe_visual(timeout_s: float) -> bool:
    """Count both visual collections in a throwaway process. True if they answer."""
    probe = (
        "from ytk.store import _visual_collection, _visual_pending_collection;"
        "_visual_collection().count();_visual_pending_collection().count()"
    )
    try:
        done = subprocess.run([sys.executable, "-c", probe], timeout=timeout_s, capture_output=True)
    except (subprocess.TimeoutExpired, OSError):
        return False
    return done.returncode == 0


def visual_index_ok(timeout_s: float = 25.0) -> bool:
    """Whether the visual collections answer a trivial count() in time.

    A damaged HNSW segment makes chroma's Rust count() block forever while
    holding the GIL, which freezes every thread in the process — uvicorn's
    event loop included, so the hub binds its port and then never answers a
    request (#130). That call cannot be interrupted or timed out in-process,
    so the probe runs in a subprocess that can actually be killed. Cached:
    the answer cannot change without a restart, and the probe is not cheap.
    """
    global _VISUAL_PROBE
    if not visual_index_enabled():
        return False
    if _VISUAL_PROBE is None:
        _VISUAL_PROBE = _probe_visual(timeout_s)
        if not _VISUAL_PROBE:
            logging.getLogger(__name__).error(
                "visual index unresponsive — visual search disabled this run (#130)"
            )
    return _VISUAL_PROBE


def reset_visual_collections() -> None:
    """Recreate both visual collections on the configured HTTP server."""
    global _VISUAL_PROBE
    config = runtime_config(default_path=_CHROMA_PATH)
    if config.mode != "http":
        raise RuntimeError("visual collection reset requires the Chroma HTTP server")

    client = _get_client()
    existing = {collection.name for collection in client.list_collections()}
    for name in (_COLLECTION_VISUAL, _COLLECTION_VISUAL_PENDING):
        if name in existing:
            client.delete_collection(name)

    _VISUAL_PROBE = None
    _visual_collection()
    _visual_pending_collection()
    _VISUAL_PROBE = True


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
    if not visual_index_ok():
        return
    _visual_collection().upsert(
        ids=[item_id],
        embeddings=[embedding],
        metadatas=[metadata],
    )


def visual_count() -> int:
    if not visual_index_ok():
        return 0
    return _visual_collection().count()


def visual_ids() -> set[str]:
    """All item_ids already present in the visual collection."""
    if not visual_index_ok():
        return set()
    return set(_visual_collection().get(include=[])["ids"])


def update_visual_metadata(item_id: str, metadata: dict) -> bool:
    """Replace metadata for an existing cover without recomputing its vector."""
    if not visual_index_ok():
        return False
    col = _visual_collection()
    if not col.get(ids=[item_id], include=[])["ids"]:
        return False
    col.update(ids=[item_id], metadatas=[metadata])
    return True


def _visual_pending_collection() -> chromadb.Collection:
    """SigLIP-2 embeddings of pending-queue covers, keyed by item url.

    Separate from ytk_visual so ingested-library search stays clean; entries
    live exactly as long as their item stays in the pending queue."""
    return _get_client().get_or_create_collection(
        name=_COLLECTION_VISUAL_PENDING,
        metadata={"hnsw:space": "cosine"},
    )


def pending_visual_ids() -> set[str]:
    if not visual_index_ok():
        return set()
    return set(_visual_pending_collection().get(include=[])["ids"])


def upsert_pending_visual(url: str, embedding: list[float], metadata: dict) -> None:
    if not visual_index_ok():
        return
    _visual_pending_collection().upsert(ids=[url], embeddings=[embedding], metadatas=[metadata])


def delete_pending_visual(urls: list[str]) -> None:
    if not urls or not visual_index_ok():
        return
    _visual_pending_collection().delete(ids=urls)


def pending_visual_similar(embedding: list[float], n: int = 30) -> list[VisualResult]:
    """Nearest pending-queue covers to a SigLIP vector (image or text tower)."""
    if not visual_index_ok():
        return []
    col = _visual_pending_collection()
    if col.count() == 0:
        return []
    res = col.query(query_embeddings=[embedding], n_results=min(n, col.count()))
    return [
        VisualResult(
            item_id=rid,
            source=meta_str(meta, "source"),
            title=meta_str(meta, "title"),
            url=rid,
            image_path=meta_str(meta, "image_path"),
            note_path="",
            distance=dist,
        )
        for rid, meta, dist in zip(
            res["ids"][0],
            chroma_field(res["metadatas"], "metadatas")[0],
            chroma_field(res["distances"], "distances")[0],
        )
    ]


def get_profile_visual_pool(pending: bool = False) -> list[dict]:
    """Return saved or pending cover vectors for the profile ranking eval.

    Pending covers are candidates the discovery queue has not written to the
    vault. Keeping this boundary explicit is what makes them honest non-vault
    negatives rather than relabeling another one of the user's saves.
    """
    if not visual_index_ok():
        return []
    col = _visual_pending_collection() if pending else _visual_collection()
    if col.count() == 0:
        return []
    data = col.get(include=["embeddings", "metadatas"])
    return [
        {
            "id": item_id,
            "embedding": list(embedding),
            "source": meta_str(meta, "source"),
            "note_path": meta_str(meta, "note_path"),
        }
        for item_id, embedding, meta in zip(
            data["ids"],
            chroma_field(data["embeddings"], "embeddings"),
            chroma_field(data["metadatas"], "metadatas"),
        )
    ]


def get_visual_embedding(item_id: str) -> list[float] | None:
    if not visual_index_ok():
        return None
    res = _visual_collection().get(ids=[item_id], include=["embeddings"])
    if not res["ids"]:
        return None
    return list(chroma_field(res["embeddings"], "embeddings")[0])


def get_visual_metadata(item_id: str) -> dict | None:
    """Return one cover's metadata without exposing the Chroma collection."""
    if not visual_index_ok():
        return None
    res = _visual_collection().get(ids=[item_id], include=["metadatas"])
    if not res["ids"]:
        return None
    metadata = chroma_field(res["metadatas"], "metadatas")[0]
    return dict(metadata) if metadata is not None else {}


def visual_similar(
    item_id: str | None = None,
    embedding: list[float] | None = None,
    n: int = 10,
) -> list[VisualResult]:
    """Nearest covers by SigLIP-2 cosine distance. Query by stored id or raw
    vector (image or text-tower — same space). Excludes the query item."""
    if not visual_index_ok():
        return []
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
        res["ids"][0],
        chroma_field(res["metadatas"], "metadatas")[0],
        chroma_field(res["distances"], "distances")[0],
    ):
        if rid == item_id:
            continue
        out.append(
            VisualResult(
                item_id=rid,
                source=meta_str(meta, "source"),
                title=meta_str(meta, "title"),
                url=meta_str(meta, "url"),
                image_path=meta_str(meta, "image_path"),
                note_path=meta_str(meta, "note_path"),
                distance=dist,
            )
        )
    return out[:n]


_FM_RE = re.compile(r"^---\n.*?^---\n", re.DOTALL | re.MULTILINE)


def strip_frontmatter(text: str) -> str:
    """Strip YAML frontmatter block from markdown so only body text is indexed."""
    if not text.startswith("---"):
        return text
    m = _FM_RE.match(text)
    return text[m.end() :].lstrip() if m else text


# R3 (#150): notes with superseded history embed only their live slice — the
# history stays on disk and greppable, but two dated copies of a project's
# state in one vector would smear the embedding across time.
_SUPERSEDED_DIVIDER = "<!-- superseded -->"


def live_slice(body: str) -> str:
    """The pre-divider portion of a note body; the whole body when undivided."""
    return body.split(_SUPERSEDED_DIVIDER)[0].rstrip()


def _with_ingest_time(col, ids: list[str], metas: list[dict]) -> list[Metadata]:
    """Stamp ingested_at (UTC ISO) exactly once per id: first write wins,
    re-upserts carry the existing stamp forward (chroma upsert replaces
    metadata wholesale, so preservation must be explicit). Records written
    before this field existed stay unstamped until they pass through an
    API upsert again — absent means unknown, never a backfilled guess.
    The embedder migration copies metadata verbatim, so stamps survive
    re-embedding (garden v6 finding 15)."""
    from datetime import datetime

    try:
        existing = col.get(ids=ids, include=["metadatas"])
        prior = {
            i: (m or {}).get("ingested_at")
            for i, m in zip(existing["ids"], chroma_field(existing["metadatas"], "metadatas"))
        }
    except Exception:
        prior = {}
    now = datetime.now(UTC).isoformat(timespec="seconds")
    return [{**meta, "ingested_at": prior.get(i) or now} for i, meta in zip(ids, metas)]


_DOC_PART_LIMIT = 1800  # chars (~450 tokens): fits the v1 512-token window
# Conservative character proxy for v2's 3,072-token runtime window. Notes
# beyond it overflow into retrieval-only parts instead of losing their tail.
_LONG_DOC_PART_LIMIT = 8000
_MIN_OVERFLOW_CHARS = 400


def _split_doc(text: str, limit: int = _DOC_PART_LIMIT) -> list[str]:
    """Greedy paragraph packing into chunks that fit the embedder window."""
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    buf = ""
    for para in text.split("\n\n"):
        while len(para) > limit:
            if buf:
                parts.append(buf)
                buf = ""
            parts.append(para[:limit])
            para = para[limit:]
        candidate = f"{buf}\n\n{para}" if buf else para
        if len(candidate) > limit:
            parts.append(buf)
            buf = para
        else:
            buf = candidate
    if buf.strip():
        parts.append(buf)
    return [p for p in parts if p.strip()]


def _split_long_doc(text: str) -> list[str]:
    """Split for v2 without leaving a useless one-line overflow vector."""
    chunks = _split_doc(text, _LONG_DOC_PART_LIMIT)
    if len(chunks) > 1 and len(chunks[-1]) < _MIN_OVERFLOW_CHARS:
        needed = _MIN_OVERFLOW_CHARS - len(chunks[-1])
        if len(chunks[-2]) - needed >= _MIN_OVERFLOW_CHARS:
            chunks[-1] = chunks[-2][-needed:] + chunks[-1]
            chunks[-2] = chunks[-2][:-needed]
    return chunks


# below this, a text is noise in the retrieval surface, not a card (#87)
MIN_EMBED_CHARS = 40


def upsert_doc(doc_id: str, text: str, metadata: dict) -> None:
    """Upsert arbitrary text into the memories collection.

    Under parts epochs (v1/gte-small), documents are embedded as PARTS, same
    convention as videos: the embedder hard-truncates at 512 tokens, so a
    single vector for a long note silently drops the tail. The plain doc_id
    is the representative vector that counting consumers (map, garden,
    synthesis) use; '#'-suffixed parts exist for retrieval only and are
    collapsed by doc_id at query time. Tail parts are prefixed with the
    note's first line as situating context. Long-context epochs (v2/Qwen3)
    use one vector up to the conservative runtime window, then overflow into
    retrieval-only parts. No text is silently discarded.

    Also guards against double-indexing: any existing vectors that share this
    write's source_path or doc_id but are not part of it are deleted, so a
    note re-indexed under a new id scheme cannot leave phantom copies behind.
    """
    col = _memories_collection()
    if len(text.strip()) < MIN_EMBED_CHARS:
        # too short to be a retrieval card ("good good" test memos, #87
        # audit); clear any stale vectors so an edited-down note disappears
        logging.getLogger(__name__).info(
            "upsert_doc %s: %d chars < %d, not embedding",
            doc_id,
            len(text.strip()),
            MIN_EMBED_CHARS,
        )
        delete_doc(doc_id)
        return
    base = {**metadata, "doc_id": doc_id}
    if _EPOCHS[EMBEDDING_EPOCH]["parts"]:
        chunks = _split_doc(text, _DOC_PART_LIMIT)
    else:
        chunks = _split_long_doc(text)

    if len(chunks) > 1:
        logging.getLogger(__name__).info(
            "upsert_doc %s: %d chars overflowed into %d vectors",
            doc_id,
            len(text),
            len(chunks),
        )

    if _EPOCHS[EMBEDDING_EPOCH]["parts"] or len(chunks) > 1:
        context = next(
            (line.strip().lstrip("# ") for line in text.splitlines() if line.strip()), ""
        )[:120]
        ids = [doc_id] + [f"{doc_id}#{i}" for i in range(1, len(chunks))]
        docs = [chunks[0]] + [f"{context}\n\n{c}" for c in chunks[1:]]
        metas = [{**base, "part": i} for i in range(len(chunks))]
    else:
        # Long-context epoch and a document inside its conservative window.
        # The stale guard below clears any old overflow parts after a note is
        # edited shorter.
        ids = [doc_id]
        docs = [text]
        metas = [base]

    stale: list[str] = []
    try:
        clauses: list[Where] = [{"doc_id": doc_id}]
        if base.get("source_path"):
            clauses.append({"source_path": base["source_path"]})
        where: Where = clauses[0] if len(clauses) == 1 else {"$or": clauses}
        existing = col.get(where=where, include=[])
        stale = [i for i in existing["ids"] if i not in set(ids)]
    except Exception as exc:
        logging.getLogger(__name__).debug("upsert_doc guard %s: %s", doc_id, exc)

    col.upsert(ids=ids, documents=docs, metadatas=_with_ingest_time(col, ids, metas))
    if stale:
        try:
            col.delete(ids=stale)
        except Exception as exc:
            logging.getLogger(__name__).debug("upsert_doc stale %s: %s", doc_id, exc)


def delete_doc(doc_id: str) -> None:
    """Remove a document and its '#'-suffixed parts from the memories collection."""
    log = logging.getLogger(__name__)
    try:
        _memories_collection().delete(ids=[doc_id])
    except Exception as exc:
        log.debug("delete_doc %s: %s", doc_id, exc)
    try:
        _memories_collection().delete(where={"doc_id": doc_id})
    except Exception as exc:
        log.debug("delete_doc parts %s: %s", doc_id, exc)


def orphaned_memory_vectors() -> list[dict[str, str]]:
    """Return memory vectors whose source file no longer exists (#93).

    Chroma may hold the last surviving copy of an orphan's text, so this is
    deliberately read-only. One row is returned per searchable vector.
    """
    col = _memories_collection()
    if col.count() == 0:
        return []
    got = col.get(include=["metadatas"])
    out: list[dict[str, str]] = []
    for vector_id, meta in zip(got["ids"], chroma_field(got["metadatas"], "metadatas")):
        source_path = meta_str(meta, "source_path")
        if not source_path or not Path(source_path).expanduser().exists():
            out.append(
                {
                    "vector_id": vector_id,
                    "doc_id": meta_str(meta, "doc_id", vector_id),
                    "source_path": source_path,
                }
            )
    return out


def append_video_take(video_id: str, thought: str) -> None:
    """Append the user's take to a video's representative doc and re-embed.

    YouTube annotations otherwise never reach the index (#87 audit):
    reindex_vault skips sources/youtube and upsert() embeds enrichment text
    only. Idempotent per thought text; missing videos are a no-op.
    """
    take = thought.strip()
    if not take:
        return
    col = _videos_collection()
    got = col.get(ids=[video_id], include=["documents", "metadatas"])
    if not got["ids"]:
        return
    doc = chroma_field(got["documents"], "documents")[0] or ""
    if take in doc:
        return
    col.upsert(
        ids=[video_id],
        documents=[doc.rstrip() + f"\n\nMy take: {take}"],
        metadatas=[chroma_field(got["metadatas"], "metadatas")[0]],
    )


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
    if not item_ids or not visual_index_ok():
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
    # Under parts epochs (v1), embedded as PARTS, not one concatenated doc:
    # the embedder (gte-small) hard-truncates at 512 tokens, and a single
    # thesis+summary+insights+concepts doc measurably overflows that window,
    # silently dropping the entity-dense tail (2026-07 enrichment audit).
    # Part ids: the plain video_id is the representative vector
    # (thesis+summary) that clustering, tag counts, the map, and the graph
    # consume; '#'-suffixed parts exist for retrieval only and are collapsed
    # by video_id at query time. Each extra part is prefixed with
    # title+thesis as situating context (contextual retrieval: naked
    # fragments match vague queries poorly).
    # Long-context epochs (v2) write only the representative doc — that is
    # what the encoder-audit retrieval gate measured on both sides; folding
    # concepts/insights into the whole doc is unmeasured (spec Phase 3).
    context = f"{title}. {enrichment.thesis}"
    parts: dict[str, str] = {
        video_id: enrichment.thesis + "\n\n" + enrichment.summary,
    }
    if _EPOCHS[EMBEDDING_EPOCH]["parts"]:
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
        # Stored, never embedded (decision 2026-07-24): metadata is not part of
        # any document, so keeping the raw description here costs nothing at
        # query time and spares every future consumer a re-fetch. Its semantics
        # reach the vectors through enrichment, which now reads it.
        "description": meta.get("description", "") or "",
    }
    vcol = _videos_collection()
    vcol.upsert(
        ids=list(parts.keys()),
        documents=list(parts.values()),
        metadatas=_with_ingest_time(vcol, list(parts.keys()), [dict(part_meta) for _ in parts]),
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
        seg_metas.append(
            {
                "video_id": video_id,
                "title": title,
                "url": meta.get("url", ""),
                "start": start,
                "timestamp_url": f"https://youtu.be/{video_id}?t={int(start)}",
            }
        )

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
        scol = _segments_collection()
        scol.upsert(
            ids=seg_ids,
            documents=seg_docs,
            metadatas=_with_ingest_time(scol, seg_ids, seg_metas),
        )


# --- second-stage reranking (#86) ---
# The cross-encoder reorders the bi-encoder's top candidates reading query
# and document together. Off unless requested per call or via YTK_RERANK=1;
# depth/latency tradeoffs are measured by experiments/rerank_bench.py.
_RERANK_DEPTH = 30
_reranker = None  # lazy QwenReranker; tests inject a plain callable


def _get_reranker():
    global _reranker
    if _reranker is None:
        from .rerank import QwenReranker

        _reranker = QwenReranker()
    return _reranker


def _rerank_enabled(flag: bool | None) -> bool:
    if flag is None:
        return os.environ.get("YTK_RERANK", "") == "1"
    return flag


def _apply_rerank(query: str, items: list, texts: list[str], n: int) -> list:
    import time

    from .rerank import rerank as _rerank_order

    t0 = time.perf_counter()
    out = _rerank_order(query, items, texts, scorer=_get_reranker(), top_n=n)
    # the issue budget is +1s per search; keep the added cost observable
    logging.getLogger("ytk.rerank").info(
        "reranked %d candidates in %.2fs", len(items), time.perf_counter() - t0
    )
    return out


def _collapse_by_video(metas: list[Metadata], dists: list[float]) -> list[tuple[Metadata, float]]:
    """Collapse part hits to one per video, keeping the best (first) distance.

    Chroma returns hits in ascending distance, so the first occurrence of a
    video_id is its max-sim part; later parts of the same video are dropped.
    """
    seen: set[str] = set()
    out: list[tuple[Metadata, float]] = []
    for meta, dist in zip(metas, dists):
        vid = meta_str(meta, "video_id")
        if vid in seen:
            continue
        seen.add(vid)
        out.append((meta, dist))
    return out


# #150 A4: served-hit log for the usage-aware gc question (R6). Rank and
# distance are recorded, not bare inclusion — served-is-not-used. Instrumentation
# only: any failure is swallowed so logging can never break a search.
_RETRIEVAL_LOG = Path.home() / ".ytk" / "retrieval_log.jsonl"


def log_retrieval(surface: str, query: str, hits: Iterable[tuple[str, float]]) -> None:
    target = os.environ.get("YTK_RETRIEVAL_LOG", str(_RETRIEVAL_LOG))
    if target.strip().lower() == "off":
        return
    try:
        ts = datetime.now(UTC).isoformat(timespec="seconds")
        lines = [
            json.dumps(
                {
                    "ts": ts,
                    "surface": surface,
                    "query": query,
                    "doc_id": doc_id,
                    "rank": rank,
                    "distance": round(float(distance), 4),
                }
            )
            for rank, (doc_id, distance) in enumerate(hits, start=1)
        ]
        if not lines:
            return
        with open(target, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    except OSError:
        pass


def search_videos(query: str, n: int = 5, rerank: bool | None = None) -> list[VideoResult]:
    """Search video-level collection. Returns up to n matches ranked by cosine similarity.

    With rerank on, the cross-encoder reorders the top _RERANK_DEPTH
    candidates on their representative text (thesis + summary) before the
    top-n cut.
    """
    col = _videos_collection()
    if col.count() == 0:
        return []

    rerank_on = _rerank_enabled(rerank)
    fetch = _RERANK_DEPTH if rerank_on else n
    # over-fetch: a video may match on up to 3 parts that collapse to one hit
    results = col.query(
        query_embeddings=[_embed_query(query)], n_results=min(fetch * 3, col.count())
    )
    out: list[VideoResult] = []
    collapsed = _collapse_by_video(
        chroma_field(results["metadatas"], "metadatas")[0],
        chroma_field(results["distances"], "distances")[0],
    )
    for meta, dist in collapsed[:fetch]:
        tags = meta_str(meta, "tags")
        out.append(
            VideoResult(
                video_id=meta_str(meta, "video_id"),
                title=meta_str(meta, "title"),
                url=meta_str(meta, "url"),
                uploader=meta_str(meta, "uploader"),
                date=meta_str(meta, "date"),
                tags=tags.split(", ") if tags else [],
                thesis=meta_str(meta, "thesis"),
                summary=meta_str(meta, "summary"),
                distance=dist,
            )
        )
    if rerank_on and out:
        # thesis+summary is the representative doc the video was embedded on
        out = _apply_rerank(query, out, [f"{r.thesis}\n\n{r.summary}" for r in out], n)
    served = out[:n]
    log_retrieval("videos", query, [(r.video_id, r.distance) for r in served])
    return served


def search_segments(
    query: str, video_id: str | None = None, n: int = 10, rerank: bool | None = None
) -> list[SegmentResult]:
    """
    Search segment-level collection. Optionally filter to a specific video_id.
    Used by the future `ytk dive` command.
    """
    col = _segments_collection()
    if col.count() == 0:
        return []

    rerank_on = _rerank_enabled(rerank)
    fetch = _RERANK_DEPTH if rerank_on else n
    where = {"video_id": video_id} if video_id else None
    kwargs: dict = {
        "query_embeddings": [_embed_query(query)],
        "n_results": min(fetch, col.count()),
    }
    if where:
        kwargs["where"] = where

    results = col.query(**kwargs)
    out: list[SegmentResult] = []
    for meta, doc, dist in zip(
        chroma_field(results["metadatas"], "metadatas")[0],
        chroma_field(results["documents"], "documents")[0],
        chroma_field(results["distances"], "distances")[0],
    ):
        out.append(
            SegmentResult(
                video_id=meta_str(meta, "video_id"),
                title=meta_str(meta, "title"),
                url=meta_str(meta, "url"),
                start=meta_float(meta, "start"),
                text=doc,
                timestamp_url=meta_str(meta, "timestamp_url"),
                distance=dist,
            )
        )
    if rerank_on and out:
        out = _apply_rerank(query, out, [r.text for r in out], n)
    served = out[:n]
    log_retrieval("segments", query, [(f"{r.video_id}@{r.start:g}", r.distance) for r in served])
    return served


@dataclass
class UnifiedResult:
    type: str
    doc_id: str
    title: str
    excerpt: str
    source: str
    distance: float


def upsert_memory(doc_id: str, text: str, tags: list[str], source_path: str) -> None:
    """Embed and store an arbitrary memory note in the memories collection."""
    upsert_doc(
        doc_id,
        text,
        {
            "doc_id": doc_id,
            "tags": ", ".join(tags),
            "source_path": source_path,
            # R2/#150: capture date in metadata, forward-only; older docs
            # fall back to the date in their doc_id at ranking time
            "captured": datetime.now(UTC).strftime("%Y-%m-%d"),
        },
    )


# R2 (#150): recency-decayed ranking for memory hits. Boost-only — a video's
# score is its similarity untouched, and a memory can only gain. Default OFF
# (lambda 0); the sweep sets YTK_MEMORY_DECAY_LAMBDA / _HALFLIFE. Unknown
# capture dates get zero boost, not recency_factor's neutral 1.0: freshness a
# record cannot prove must not move its rank (timestamp-coverage bias).
_DOC_ID_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def memory_captured_at(meta: Metadata | None, doc_id: str) -> str:
    stamped = meta_str(meta, "captured")
    if stamped:
        return stamped
    m = _DOC_ID_DATE_RE.search(doc_id)
    return m.group(1) if m else ""


def _memory_decay_params() -> tuple[float, float]:
    lam = float(os.environ.get("YTK_MEMORY_DECAY_LAMBDA", "0") or 0)
    half = float(os.environ.get("YTK_MEMORY_DECAY_HALFLIFE", "90") or 90)
    return lam, half


def apply_memory_decay(
    results: list[UnifiedResult],
    lam: float,
    half_life_days: float,
    now: datetime | None = None,
    captured: dict[str, str] | None = None,
) -> list[UnifiedResult]:
    """Stable re-sort by sim * (1 + lam * recency); memories only can gain."""
    if lam <= 0:
        return results
    from .signals import recency_factor

    now = now or datetime.now(UTC)

    def score(r: UnifiedResult) -> float:
        sim = 1.0 - r.distance
        if r.type != "memory":
            return sim
        at = (captured or {}).get(r.doc_id) or memory_captured_at(None, r.doc_id)
        factor = recency_factor(at, now, half_life_days) if at else 0.0
        return sim * (1.0 + lam * factor)

    return sorted(results, key=score, reverse=True)


@dataclass
class MemoryNeighbor:
    doc_id: str
    source_path: str
    similarity: float
    excerpt: str


def similar_memories(
    text: str, n: int = 5, exclude_doc_id: str | None = None
) -> list[MemoryNeighbor]:
    """Nearest existing memories to a candidate text — R1 (#150).

    Doc-to-doc similarity, so the candidate embeds through the plain document
    path (query_texts routes through the EF's __call__), matching how the
    stored memories were embedded and how A1's thresholds were calibrated.
    """
    col = _memories_collection()
    if col.count() == 0:
        return []
    results = col.query(query_texts=[text], n_results=min(n * 3, col.count()))
    out: list[MemoryNeighbor] = []
    seen: set[str] = set()
    for meta, doc, dist in zip(
        chroma_field(results["metadatas"], "metadatas")[0],
        chroma_field(results["documents"], "documents")[0],
        chroma_field(results["distances"], "distances")[0],
    ):
        doc_id = meta_str(meta, "doc_id")
        if doc_id in seen or doc_id == exclude_doc_id:
            continue
        seen.add(doc_id)
        out.append(
            MemoryNeighbor(
                doc_id=doc_id,
                source_path=meta_str(meta, "source_path"),
                similarity=max(0.0, min(1.0, 1.0 - dist)),
                excerpt=doc[:200],
            )
        )
        if len(out) >= n:
            break
    return out


def search_all(query: str, n: int = 5, rerank: bool | None = None) -> list[UnifiedResult]:
    """Semantic search across video summaries and memory notes, merged by distance.

    With rerank on, the cross-encoder reorders the merged top _RERANK_DEPTH
    on full document text (excerpts are display artifacts) before the top-n
    cut.
    """
    rerank_on = _rerank_enabled(rerank)
    fetch = _RERANK_DEPTH if rerank_on else n
    # (result, rerank text) pairs: videos score on their representative doc,
    # memories on the stored document
    pairs: list[tuple[UnifiedResult, str]] = []
    query_emb = _embed_query(query)

    vcol = _videos_collection()
    if vcol.count() > 0:
        vr = vcol.query(query_embeddings=[query_emb], n_results=min(fetch * 3, vcol.count()))
        collapsed = _collapse_by_video(
            chroma_field(vr["metadatas"], "metadatas")[0],
            chroma_field(vr["distances"], "distances")[0],
        )
        for meta, dist in collapsed[:fetch]:
            summary = meta_str(meta, "summary")
            pairs.append(
                (
                    UnifiedResult(
                        type="video",
                        doc_id=meta_str(meta, "video_id"),
                        title=meta_str(meta, "title"),
                        # thesis falling back to summary only when absent, not
                        # when empty: an empty thesis is a deliberate value.
                        excerpt=meta_str(meta, "thesis", summary)[:200],
                        source=meta_str(meta, "url"),
                        distance=dist,
                    ),
                    f"{meta_str(meta, 'thesis')}\n\n{summary}",
                )
            )

    mcol = _memories_collection()
    if mcol.count() > 0:
        mr = mcol.query(query_embeddings=[query_emb], n_results=min(fetch * 3, mcol.count()))
        seen_docs: set[str] = set()
        for meta, doc, dist in zip(
            chroma_field(mr["metadatas"], "metadatas")[0],
            chroma_field(mr["documents"], "documents")[0],
            chroma_field(mr["distances"], "distances")[0],
        ):
            doc_id = meta_str(meta, "doc_id")
            if doc_id in seen_docs:  # best-ranked part already represents this doc
                continue
            seen_docs.add(doc_id)
            pairs.append(
                (
                    UnifiedResult(
                        type="memory",
                        doc_id=doc_id,
                        title=doc_id,
                        excerpt=doc[:200],
                        source=meta_str(meta, "source_path"),
                        distance=dist,
                    ),
                    doc,
                )
            )

    pairs.sort(key=lambda p: p[0].distance)
    lam, half_life = _memory_decay_params()
    if rerank_on and pairs:
        pairs = pairs[:_RERANK_DEPTH]
        served = _apply_rerank(query, [p[0] for p in pairs], [p[1] for p in pairs], n)
    elif lam > 0:
        # decay is scoped to the plain path: the cross-encoder re-scores on
        # text, and blending two score systems is a different experiment
        served = apply_memory_decay([p[0] for p in pairs], lam, half_life)[:n]
    else:
        served = [p[0] for p in pairs[:n]]
    log_retrieval("all", query, [(r.doc_id, r.distance) for r in served])
    return served


def top_tags(n: int = 40) -> list[str]:
    """Existing tag vocabulary, most-used first, from indexed metadata.

    Frequency ranking makes the canonical spelling win: the common variant of
    a drifting pair (3d-printing vs 3dprint) reaches the vocabulary, the rare
    one does not, so enrichment converges on the winner.
    """
    return [t for t, _ in tag_counts().most_common(n)]


def tag_counts() -> Counter[str]:
    """Tag -> usage count over enrichment-produced interest_tags.

    Videos collection only: the memories collection's tags metadata holds
    folder path segments (vault_write / reindex derive tags from the note's
    directory), which are structural labels, not interest tags. Feeding those
    into the enrichment vocabulary would teach it to tag content "inbox".
    """
    counts: Counter[str] = Counter()
    col = _videos_collection()
    if col.count():
        res = col.get(include=["metadatas"])
        for doc_id, meta in zip(res["ids"], chroma_field(res["metadatas"], "metadatas")):
            if "#" in doc_id:  # retrieval-only part; count each video once
                continue
            for tag in meta_str(meta, "tags").split(", "):
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
    for vid, emb, meta in zip(
        res["ids"],
        chroma_field(res["embeddings"], "embeddings"),
        chroma_field(res["metadatas"], "metadatas"),
    ):
        if "#" in vid:  # retrieval-only part; one representative vector per video
            continue
        tags = meta_str(meta, "tags")
        out.append(
            {
                "id": vid,
                "source": "youtube",
                "title": meta_str(meta, "title"),
                "thesis": meta_str(meta, "thesis"),
                "summary": meta_str(meta, "summary"),
                "tags": tags.split(", ") if tags else [],
                "embedding": list(emb),
                "captured_at": meta_str(meta, "ingested_at"),
            }
        )
    return out


_THESIS_RE = re.compile(r"##\s*Thesis\s*\n(.+?)(?:\n##|\Z)", re.DOTALL)


def _extract_thesis(document: str) -> str:
    """Pull the text under a '## Thesis' heading from a stored note body, else a short prefix."""
    m = _THESIS_RE.search(document or "")
    if m:
        return m.group(1).strip()
    return (document or "").strip()[:200]


def get_content_memories(prefixes: list[str]) -> list[dict]:
    """Return memory docs for the given content sources.

    Content notes live under exactly one id scheme: the path-derived
    ``note_sources_{source}_...`` that ingest and reindex now share (#95).
    The old ingest-time ``{source}_{stem60}`` ids were migrated by
    scripts/migrate_content_note_ids.py, so no dual-prefix matching remains.

    Each item: {id, source, title, thesis, summary, tags, embedding, ...}.
    title is '' (memories have no separate title); thesis is extracted from the
    stored note body's '## Thesis' section. Used by the synthesis engine so the
    interest profile reflects ingested reels/TikToks/articles, not just YouTube.
    Returns [] when empty.
    """
    col = _memories_collection()
    if col.count() == 0:
        return []
    allow = tuple(f"note_sources_{p}_" for p in prefixes)
    res = col.get(include=["embeddings", "metadatas", "documents"])
    out: list[dict] = []
    for mid, emb, meta, doc in zip(
        res["ids"],
        chroma_field(res["embeddings"], "embeddings"),
        chroma_field(res["metadatas"], "metadatas"),
        chroma_field(res["documents"], "documents"),
    ):
        if "#" in mid:  # retrieval-only part; one entry per doc
            continue
        doc_id = meta_str(meta, "doc_id", mid)
        if not doc_id.startswith(allow):
            continue
        source = doc_id.split("_", 3)[2]
        tags = meta_str(meta, "tags")
        out.append(
            {
                "id": mid,
                "source": source,
                "title": "",
                "thesis": _extract_thesis(doc),
                "summary": "",
                "tags": tags.split(", ") if tags else [],
                "embedding": list(emb),
                "source_path": meta_str(meta, "source_path"),
                "captured_at": meta_str(meta, "ingested_at"),
            }
        )
    return out
