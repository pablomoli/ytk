"""Video docs are embedded as parts so no section falls off the 512-token cliff."""

import importlib

import pytest

from ytk.enrich import Enrichment, KeyMoment


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
    import ytk.store as store_mod

    importlib.reload(store_mod)
    store_mod.EMBEDDING_EPOCH = "v1"  # reload resets to the production default
    return store_mod


def _enr(thesis="Thesis about tiling renderers.", concepts=None, moments=None):
    return Enrichment(
        thesis=thesis,
        summary="A summary of the build.",
        key_concepts=concepts or ["wgpu: drives the GPU pipeline", "naga: shader translation"],
        insights=["Tiles beat full-screen passes on mobile."],
        interest_tags=["gpu", "creative-coding"],
        key_moments=moments
        or [KeyMoment(timestamp="1:02", description="switches the renderer to tiled mode")],
    )


def _upsert(store, vid="vid1", title="Tiling Renderer", enr=None):
    store.upsert(
        {"id": vid, "title": title, "url": "u", "uploader": "x", "upload_date": "20260101"},
        enr or _enr(),
        segments=[],
    )


def test_upsert_splits_video_into_parts(store):
    _upsert(store)
    got = store._videos_collection().get()
    assert sorted(got["ids"]) == ["vid1", "vid1#c", "vid1#i"]
    docs = dict(zip(got["ids"], got["documents"]))
    assert "Key concepts" in docs["vid1#c"] and "wgpu" in docs["vid1#c"]
    assert "Insights" in docs["vid1#i"] and "tiled mode" in docs["vid1#i"]
    # every part carries situating context and the full metadata
    assert "Tiling Renderer" in docs["vid1#c"]
    metas = dict(zip(got["ids"], got["metadatas"]))
    assert metas["vid1#c"]["video_id"] == "vid1"


def test_search_videos_collapses_parts_to_one_result(store):
    _upsert(store)
    _upsert(
        store,
        vid="vid2",
        title="Sourdough",
        enr=_enr(
            thesis="Baking sourdough at home.", concepts=["levain: overnight starter"], moments=[]
        ),
    )
    hits = store.search_videos("gpu tiling shader pipeline", n=5)
    ids = [h.video_id for h in hits]
    assert len(ids) == len(set(ids)), "parts of one video must collapse"
    assert ids[0] == "vid1"


def test_search_finds_video_by_concept_tail(store):
    """The point of the fix: concept text is now genuinely embedded."""
    _upsert(store)
    hits = store.search_videos("naga shader translation", n=3)
    assert hits and hits[0].video_id == "vid1"


def test_get_all_videos_one_row_per_video(store):
    _upsert(store)
    rows = store.get_all_videos()
    assert [r["id"] for r in rows] == ["vid1"]


def test_tag_counts_count_each_video_once(store):
    _upsert(store)
    assert store.tag_counts()["gpu"] == 1


def test_search_all_dedupes_video_parts(store):
    _upsert(store)
    hits = [r for r in store.search_all("tiling renderer gpu", n=6) if r.type == "video"]
    ids = [h.doc_id for h in hits]
    assert len(ids) == len(set(ids)) == 1
