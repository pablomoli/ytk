"""Fresh reconstruction of server-owned visual collections."""

from __future__ import annotations

import hashlib

import chromadb
import pytest
from click.testing import CliRunner

from ytk.chroma_runtime import runtime_config


def test_reset_visual_collections_refuses_embedded_mode(tmp_path, monkeypatch):
    from ytk import store

    cfg = runtime_config({}, default_path=tmp_path / "legacy")
    monkeypatch.setattr(store, "runtime_config", lambda **kwargs: cfg)

    with pytest.raises(RuntimeError, match="HTTP"):
        store.reset_visual_collections()


def test_rebuild_replaces_both_visual_collections_from_sources(tmp_path, monkeypatch):
    from ytk import reels, store, visual

    client = chromadb.PersistentClient(path=str(tmp_path / "target"))
    cfg = runtime_config(
        {
            "CHROMA_URL": "http://127.0.0.1:8000",
            "CHROMA_SERVER_PATH": str(tmp_path / "target"),
        },
        default_path=tmp_path / "legacy",
    )
    store._client = client
    store._VISUAL_PROBE = True
    monkeypatch.setenv("YTK_VISUAL_INDEX", "on")
    monkeypatch.setattr(store, "runtime_config", lambda **kwargs: cfg)

    store._visual_collection().upsert(
        ids=["saved:old"],
        embeddings=[[0.0] * 4],
        metadatas=[{"source": "old"}],
    )
    store._visual_pending_collection().upsert(
        ids=["https://old/"],
        embeddings=[[0.0] * 4],
        metadatas=[{"source": "old"}],
    )
    client.create_collection("keep_me").add(ids=["safe"], embeddings=[[1.0]])

    saved_cover = tmp_path / "saved.jpg"
    saved_cover.write_bytes(b"saved")
    monkeypatch.setattr(
        visual,
        "iter_covers",
        lambda: [
            visual.CoverItem(
                item_id="ig:new",
                image_path=saved_cover,
                source="instagram",
                title="New save",
                url="https://saved/",
                note_path="/vault/new.md",
            )
        ],
    )

    pending_url = "https://new/"
    state_path = tmp_path / "state.json"
    state = reels.ReelsState()
    state.pending = [
        reels.ReelItem(
            url=pending_url,
            author="Pending author",
            source="youtube",
        )
    ]
    reels.save_state(state, state_path)
    monkeypatch.setattr(reels, "STATE_PATH", state_path)
    covers = tmp_path / ".ytk" / "covers"
    covers.mkdir(parents=True)
    pending_name = (
        hashlib.sha1(pending_url.encode(), usedforsecurity=False).hexdigest()[:20] + ".jpg"
    )
    (covers / pending_name).write_bytes(b"pending")
    monkeypatch.setattr(visual.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(
        visual,
        "embed_images",
        lambda paths: [[float(index + 1)] * 4 for index, _ in enumerate(paths)],
    )

    saved, pending = visual.rebuild_visual_indexes()

    assert (saved, pending) == (1, 1)
    assert store.visual_ids() == {"ig:new"}
    assert store.pending_visual_ids() == {pending_url}
    assert store.get_visual_metadata("ig:new") == {
        "source": "instagram",
        "title": "New save",
        "url": "https://saved/",
        "image_path": str(saved_cover),
        "note_path": "/vault/new.md",
    }
    pending_data = store._visual_pending_collection().get(include=["metadatas"])
    assert pending_data["metadatas"] == [
        {
            "source": "youtube",
            "title": "Pending author",
            "image_path": str(covers / pending_name),
        }
    ]
    assert client.get_collection("keep_me").count() == 1


def test_visual_rebuild_cli_requires_confirmation_and_enabled_index(monkeypatch):
    import ytk.cli as cli_mod

    calls = []
    monkeypatch.setattr(
        "ytk.visual.rebuild_visual_indexes",
        lambda progress=None: calls.append(progress) or (3, 4),
        raising=False,
    )

    missing_confirmation = CliRunner().invoke(cli_mod.cli, ["visual", "rebuild"])
    assert missing_confirmation.exit_code != 0
    assert "--yes" in missing_confirmation.output

    monkeypatch.setenv("YTK_VISUAL_INDEX", "off")
    disabled = CliRunner().invoke(cli_mod.cli, ["visual", "rebuild", "--yes"])
    assert disabled.exit_code != 0
    assert "YTK_VISUAL_INDEX" in disabled.output

    monkeypatch.setenv("YTK_VISUAL_INDEX", "on")
    rebuilt = CliRunner().invoke(cli_mod.cli, ["visual", "rebuild", "--yes"])
    assert rebuilt.exit_code == 0, rebuilt.output
    assert "Saved covers: 3" in rebuilt.output
    assert "Pending covers: 4" in rebuilt.output
    assert len(calls) == 1
