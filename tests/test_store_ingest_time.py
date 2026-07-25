"""Ingest-time capture (grove v6 finding 15): every text upsert stamps
ingested_at (UTC ISO) exactly once — first write wins, re-upserts and
reindexes preserve the original stamp, pre-existing records without the
field stay honest (absent = unknown, never backfilled with a lie)."""

from __future__ import annotations

import importlib


def _fresh_store(tmp_path, monkeypatch):
    monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
    import ytk.store as store

    importlib.reload(store)
    store.EMBEDDING_EPOCH = "v1"  # reload resets to the production default
    return store


def test_upsert_doc_stamps_ingested_at_once(tmp_path, monkeypatch):
    store = _fresh_store(tmp_path, monkeypatch)
    store.upsert_doc(
        "m1", "first text long enough to clear the minimum embed length floor", {"doc_id": "m1"}
    )
    got = store._memories_collection().get(ids=["m1"], include=["metadatas"])
    first = got["metadatas"][0]["ingested_at"]
    assert first.endswith(("+00:00", "Z"))

    # edit + reindex: text changes, stamp must not
    store.upsert_doc(
        "m1", "edited text long enough to clear the minimum embed length floor", {"doc_id": "m1"}
    )
    got = store._memories_collection().get(ids=["m1"], include=["metadatas"])
    assert got["metadatas"][0]["ingested_at"] == first
    assert got["documents"] is None or True  # stamp is the assertion here


def test_video_upsert_stamps_all_parts_and_preserves_on_reupsert(tmp_path, monkeypatch):
    from ytk.enrich import Enrichment

    store = _fresh_store(tmp_path, monkeypatch)
    enr = Enrichment(
        thesis="t",
        summary="s",
        key_concepts=["k"],
        insights=["i"],
        interest_tags=["x"],
        key_moments=[],
    )
    meta = {"id": "vid1", "title": "T", "url": "u", "uploader": "U", "upload_date": "20260101"}
    store.upsert(meta, enr, segments=[])
    got = store._videos_collection().get(include=["metadatas"])
    stamps = {m["ingested_at"] for m in got["metadatas"]}
    assert len(stamps) == 1  # every part carries the same first-seen stamp
    first = stamps.pop()

    store.upsert(meta, enr, segments=[])  # re-ingest
    got = store._videos_collection().get(include=["metadatas"])
    assert {m["ingested_at"] for m in got["metadatas"]} == {first}


def test_preexisting_records_are_not_backfilled(tmp_path, monkeypatch):
    store = _fresh_store(tmp_path, monkeypatch)
    # a legacy row written without the field, via raw chroma
    store._memories_collection().upsert(
        ids=["legacy"], documents=["old"], metadatas=[{"doc_id": "legacy"}]
    )
    got = store._memories_collection().get(ids=["legacy"], include=["metadatas"])
    assert "ingested_at" not in got["metadatas"][0]
    # but the moment it is re-upserted through the API, it gets stamped NOW
    # (that is the earliest honest knowledge of its existence)
    store.upsert_doc(
        "legacy", "old body long enough to clear the embed length floor", {"doc_id": "legacy"}
    )
    got = store._memories_collection().get(ids=["legacy"], include=["metadatas"])
    assert "ingested_at" in got["metadatas"][0]
