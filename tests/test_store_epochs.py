"""Embedding-epoch plumbing: v2 collections, instruction-aware EF, whole-doc
upserts, and the query/document path split (encoder-migration spec Phase 1).

Tests run the v2 epoch on gte-small (cached, loads fast) — the epoch logic
and prefix handling under test are model-agnostic; real-Qwen3 behavior is
covered by the pre-flight benches, not unit tests.
"""

import json

import pytest


@pytest.fixture
def store(tmp_path, monkeypatch):
    # Patch the chroma path instead of reloading the module: a reload drops
    # the _efs model cache, and every re-load stacks another model onto MPS —
    # the full suite runs into the 20 GiB MPS ceiling that way.
    import ytk.store as store_mod

    monkeypatch.setattr(store_mod, "_CHROMA_PATH", tmp_path / "chroma")
    monkeypatch.setattr(store_mod, "_client", None)
    return store_mod


@pytest.fixture
def store_v2(store, monkeypatch):
    """The store on the v2 epoch, with the v2 model swapped for the small
    cached one so tests don't load Qwen3."""
    monkeypatch.setitem(
        store._EPOCHS,
        "v2",
        {
            **store._EPOCHS["v2"],
            # cpu like chroma's stock test EFs: the suite's MPS pool is already
            # near its 20 GiB ceiling and torch never frees models
            "model": "thenlper/gte-small",
            "fp16": False,
            "max_seq": 0,
            "device": "cpu",
            "revision": None,
        },
    )
    monkeypatch.setattr(store, "EMBEDDING_EPOCH", "v2")
    return store


def test_epoch_suffix_resolves_collection_names(store_v2):
    assert store_v2._memories_collection().name == "ytk_memories_v2"
    assert store_v2._videos_collection().name == "ytk_videos_v2"
    assert store_v2._segments_collection("v1").name == "ytk_segments"


def test_upsert_doc_overflows_without_truncating(store_v2):
    long_text = "word " * 2000  # far past the v1 split limit
    store_v2.upsert_doc("doc1", long_text, {"source_path": "/x.md"})
    got = store_v2._memories_collection().get()
    assert sorted(got["ids"]) == ["doc1", "doc1#1"]
    docs = dict(zip(got["ids"], got["documents"]))
    recovered = docs["doc1"] + docs["doc1#1"].split("\n\n", 1)[1]
    assert recovered == long_text
    assert all("part" in meta for meta in got["metadatas"])


def test_upsert_doc_v2_keeps_short_doc_representative_only(store_v2):
    store_v2.upsert_doc(
        "doc1",
        "a compact document that clears the retrieval noise floor",
        {"source_path": "/x.md"},
    )
    got = store_v2._memories_collection().get()
    assert got["ids"] == ["doc1"]
    assert "part" not in got["metadatas"][0]


def test_upsert_doc_v2_balances_tiny_overflow(store_v2):
    long_text = "x" * (store_v2._LONG_DOC_PART_LIMIT + 1)
    store_v2.upsert_doc("doc1", long_text, {"source_path": "/x.md"})
    got = store_v2._memories_collection().get()
    docs = dict(zip(got["ids"], got["documents"]))
    tail = docs["doc1#1"].split("\n\n", 1)[1]
    assert len(tail) == store_v2._MIN_OVERFLOW_CHARS
    assert docs["doc1"] + tail == long_text


def test_phantom_guard_survives_v2(store_v2):
    """The #71 phantom guard is independent of chunking and must survive the
    migration: a note re-indexed under a new id scheme leaves no stale vector
    sharing its source_path."""
    store_v2.upsert_doc(
        "old_id_scheme", "note body long enough to clear the embed floor", {"source_path": "/n.md"}
    )
    store_v2.upsert_doc(
        "new_id_scheme", "note body long enough to clear the embed floor", {"source_path": "/n.md"}
    )
    assert store_v2._memories_collection().get()["ids"] == ["new_id_scheme"]


def test_video_upsert_v2_writes_representative_only(store_v2):
    from ytk.enrich import Enrichment, KeyMoment

    enr = Enrichment(
        thesis="Thesis about tiling renderers.",
        summary="A summary of the build.",
        key_concepts=["wgpu: drives the GPU pipeline"],
        insights=["Tiles beat full-screen passes."],
        interest_tags=["gpu"],
        key_moments=[KeyMoment(timestamp="1:02", description="tiled mode")],
    )
    store_v2.upsert(
        {"id": "vid1", "title": "T", "url": "u", "uploader": "x", "upload_date": "20260101"},
        enr,
        segments=[],
    )
    got = store_v2._videos_collection().get()
    assert got["ids"] == ["vid1"]
    assert "Thesis about tiling" in got["documents"][0]


def test_embed_query_uses_instruction_prefix_on_v2(store_v2):
    ef = store_v2._get_ef()
    assert isinstance(ef, store_v2.InstructionAwareEF)
    q = "cache line contention"
    prefixed = store_v2._embed_query(q)
    plain = ef([q])[0]
    manual = ef([store_v2._EPOCHS["v2"]["query_prefix"] + q])[0]
    assert prefixed == pytest.approx(manual)
    assert prefixed != pytest.approx(plain)


def test_chroma_embed_query_protocol_is_the_plain_doc_path_on_v2(store_v2):
    """chroma calls ef.embed_query(input=[...]) on every query_texts path.

    The name is chroma's, with list-in/list-out semantics defaulting to
    __call__. ytk's prefixed user-query path must not squat on it — doing so
    made query_texts raise TypeError on v2, the production epoch.
    """
    ef = store_v2._get_ef()
    assert isinstance(ef, store_v2.InstructionAwareEF)
    q = "cache line contention"
    assert ef.embed_query(input=[q])[0] == pytest.approx(ef([q])[0])
    prefix = store_v2._EPOCHS["v2"]["query_prefix"]
    assert ef.embed_user_query(q) == pytest.approx(ef([prefix + q])[0])


def test_query_texts_runs_against_a_v2_collection(store_v2):
    """The doc-to-doc callers (graph.py, similar_memories) go through here.

    Covered only at v1 or against a stubbed collection until now, so a v2-only
    EF regression reached production unseen.
    """
    store_v2.upsert_doc(
        "cache", "false sharing: cores fight over one cache line", {"source_path": "/a.md"}
    )
    store_v2.upsert_doc("bread", "sourdough starter feeding schedule", {"source_path": "/b.md"})
    res = store_v2._memories_collection().query(query_texts=["cache line contention"], n_results=2)
    assert res["ids"][0][0] == "cache"


def test_embed_query_v1_matches_stock_ef(store):
    q = "cache line contention"
    assert store._embed_query(q) == pytest.approx([float(x) for x in store._get_ef()([q])[0]])


def test_instruction_aware_ef_config_roundtrip(store):
    ef = store.InstructionAwareEF("m", "P: ", fp16=True, max_seq=3072)
    clone = store.InstructionAwareEF.build_from_config(ef.get_config())
    assert clone.get_config() == ef.get_config()
    assert store.InstructionAwareEF.name() == "ytk-instruction-aware"


def test_search_v2_end_to_end(store_v2):
    store_v2.upsert_doc(
        "relevant",
        "False sharing: cores fight over one cache line, MESI ping-pong.",
        {"source_path": "/a.md"},
    )
    store_v2.upsert_doc("decoy", "Sourdough starter feeding schedule.", {"source_path": "/b.md"})
    hits = store_v2.search_all("cpu cache contention", n=2)
    assert hits[0].doc_id == "relevant"


def test_log_search_query_jsonl_and_unicode(tmp_path, monkeypatch):
    from ytk.ui import hub

    monkeypatch.setattr(hub, "_SEARCH_LOG", tmp_path / "logs" / "search.jsonl")
    hub.log_search_query("/api/search", "line\u2028separator query")
    line = (tmp_path / "logs" / "search.jsonl").read_text().strip()
    assert "\u2028" not in line, "raw U+2028 corrupts JSONL consumers"
    row = json.loads(line)
    assert row["q"] == "line\u2028separator query"
    assert row["endpoint"] == "/api/search"

    # logging must never fail the search
    monkeypatch.setattr(hub, "_SEARCH_LOG", tmp_path / "logs")  # a directory
    hub.log_search_query("/api/search", "boom")


def test_api_search_logs_query(tmp_path, monkeypatch):
    """Regression: log_search_query is imported inside the endpoint (server.py
    defers all hub imports); a module-level reference NameErrors at request
    time and 500s every search."""
    from fastapi.testclient import TestClient

    import ytk.store as store_mod
    import ytk.ui.hub as hub
    from ytk.ui.server import app

    monkeypatch.setattr(hub, "_SEARCH_LOG", tmp_path / "search.jsonl")
    monkeypatch.setattr(store_mod, "search_videos", lambda q, n=8, **kw: [])

    resp = TestClient(app).get("/api/search", params={"q": "cache lines"})
    assert resp.status_code == 200
    row = json.loads((tmp_path / "search.jsonl").read_text())
    assert row["q"] == "cache lines"
