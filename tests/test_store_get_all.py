import importlib

from ytk.enrich import Enrichment


def test_get_all_videos_returns_embeddings_and_meta(tmp_path, monkeypatch):
    monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
    import ytk.store as store
    importlib.reload(store)
    store.EMBEDDING_EPOCH = "v1"  # reload resets to the production default

    enr = Enrichment(
        thesis="A precise thesis about tiling renderers.",
        summary="Summary text.",
        key_concepts=["wgpu: used for the GPU pipeline"],
        insights=["Insight one."],
        interest_tags=["creative-coding", "gpu"],
        key_moments=[],
    )
    store.upsert({"id": "vid1", "title": "Tiling Renderer", "url": "u", "uploader": "x",
                  "upload_date": "20260101"}, enr, segments=[])

    rows = store.get_all_videos()
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == "vid1"
    assert row["title"] == "Tiling Renderer"
    assert row["thesis"].startswith("A precise thesis")
    assert row["tags"] == ["creative-coding", "gpu"]
    assert len(row["embedding"]) > 10
