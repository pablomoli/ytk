"""Pending-queue visual index: sync mirrors the queue exactly (no SigLIP)."""

import hashlib
import importlib


def _cover_name(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:20] + ".jpg"


def test_sync_pending_visual_embeds_and_evicts(tmp_path, monkeypatch):
    monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
    import ytk.store as store

    importlib.reload(store)
    store.EMBEDDING_EPOCH = "v1"  # reload resets to the production default
    import ytk.visual as visual

    importlib.reload(visual)
    from ytk import reels

    # pending queue with two items
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(reels, "STATE_PATH", state_path)
    state = reels.ReelsState()
    state.pending = [
        reels.ReelItem(url="https://www.instagram.com/reel/aaa/", author="ana", source="instagram"),
        reels.ReelItem(url="https://youtu.be/bbb", author="A Title", source="youtube"),
    ]
    reels.save_state(state, state_path)

    # cached cover exists only for the first item
    covers = tmp_path / ".ytk" / "covers"
    covers.mkdir(parents=True)
    (covers / _cover_name(state.pending[0].url)).write_bytes(b"jpg")
    monkeypatch.setattr(visual.Path, "home", classmethod(lambda cls: tmp_path))

    # a stale entry from an item no longer in the queue
    store.upsert_pending_visual("https://gone/", [0.0] * 4, {"source": "web"})

    monkeypatch.setattr(visual, "embed_images", lambda paths: [[1.0] * 4] * len(paths))

    done, evicted = visual.sync_pending_visual()
    assert (done, evicted) == (1, 1)
    ids = store.pending_visual_ids()
    assert ids == {"https://www.instagram.com/reel/aaa/"}

    # search returns the embedded pending item with its metadata
    hits = store.pending_visual_similar([1.0] * 4, n=5)
    assert hits[0].url == "https://www.instagram.com/reel/aaa/"
    assert hits[0].source == "instagram"
    assert hits[0].title == "ana"

    # second run is a no-op
    assert visual.sync_pending_visual() == (0, 0)
