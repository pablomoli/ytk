"""Safe migration from the legacy embedded store to the Chroma server."""

from __future__ import annotations

import json

import chromadb
import numpy as np
import pytest
from click.testing import CliRunner

from ytk.chroma_migrate import MigrationReport, copy_collections, write_report
from ytk.chroma_runtime import runtime_config


@pytest.fixture
def chroma_clients():
    clients = []

    def open_client(path):
        client = chromadb.PersistentClient(path=str(path))
        clients.append(client)
        return client

    yield open_client

    for client in reversed(clients):
        client.close()


def _source_with_text_and_visual_collections(tmp_path, chroma_clients):
    source = chroma_clients(tmp_path / "source")
    source.create_collection(
        "ytk_memories_v2",
        metadata={"hnsw:space": "cosine"},
    ).add(
        ids=["a", "b"],
        documents=["alpha", "beta"],
        embeddings=[[1.0, 0.0], [0.0, 1.0]],
        metadatas=[{"source": "one"}, {"source": "two"}],
    )
    source.create_collection("ytk_visual")
    source.create_collection("ytk_visual_pending")
    return source


def _target(tmp_path, chroma_clients, name="target"):
    return chroma_clients(tmp_path / name)


def test_copy_preserves_vectors_and_never_opens_visual_collections(tmp_path, chroma_clients):
    source = _source_with_text_and_visual_collections(tmp_path, chroma_clients)
    target = _target(tmp_path, chroma_clients)
    original_get_collection = source.get_collection
    opened: list[str] = []

    def tracking_get_collection(name, *args, **kwargs):
        opened.append(name)
        if name in {"ytk_visual", "ytk_visual_pending"}:
            raise AssertionError(f"migration opened excluded collection {name}")
        return original_get_collection(name, *args, **kwargs)

    source.get_collection = tracking_get_collection

    report = copy_collections(source, target, batch_size=1)

    assert report.collections == {"ytk_memories_v2": 2}
    assert report.excluded == ["ytk_visual", "ytk_visual_pending"]
    assert report.complete is True
    assert opened == ["ytk_memories_v2"]
    assert {collection.name for collection in target.list_collections()} == {"ytk_memories_v2"}
    got = target.get_collection("ytk_memories_v2").get(
        include=["documents", "metadatas", "embeddings"]
    )
    assert got["ids"] == ["a", "b"]
    assert got["documents"] == ["alpha", "beta"]
    assert got["metadatas"] == [{"source": "one"}, {"source": "two"}]
    np.testing.assert_allclose(got["embeddings"], [[1.0, 0.0], [0.0, 1.0]])


def test_copy_refuses_a_nonempty_target_without_resume(tmp_path, chroma_clients):
    source = _source_with_text_and_visual_collections(tmp_path, chroma_clients)
    target = _target(tmp_path, chroma_clients)
    target.create_collection("existing").add(ids=["occupied"], embeddings=[[1.0]])

    with pytest.raises(ValueError, match="target is not empty"):
        copy_collections(source, target)


def test_resumed_copy_is_idempotent(tmp_path, chroma_clients):
    source = _source_with_text_and_visual_collections(tmp_path, chroma_clients)
    target = _target(tmp_path, chroma_clients)

    first = copy_collections(source, target, resume=True, batch_size=1)
    second = copy_collections(source, target, resume=True, batch_size=1)

    assert first.collections == second.collections == {"ytk_memories_v2": 2}
    migrated = target.get_collection("ytk_memories_v2")
    assert migrated.count() == 2
    assert migrated.get()["ids"] == ["a", "b"]


def test_copy_preserves_client_supplied_embedding_function_compatibility(tmp_path, chroma_clients):
    from ytk.store import InstructionAwareEF

    source = chroma_clients(tmp_path / "source")
    target = chroma_clients(tmp_path / "target")
    embedding_function = InstructionAwareEF(
        "test/model",
        "Query: ",
        fp16=False,
        max_seq=32,
        device="cpu",
    )
    source.create_collection(
        "ytk_custom_config",
        embedding_function=embedding_function,
        metadata={"hnsw:space": "cosine"},
    ).add(ids=["one"], embeddings=[[1.0, 0.0]])

    copy_collections(source, target)

    reopened = target.get_or_create_collection(
        "ytk_custom_config",
        embedding_function=embedding_function,
        metadata={"hnsw:space": "cosine"},
    )
    assert reopened.count() == 1


def test_write_report_is_valid_json_and_replaces_existing_file(tmp_path, chroma_clients):
    source = _source_with_text_and_visual_collections(tmp_path, chroma_clients)
    report = copy_collections(source, _target(tmp_path, chroma_clients))
    recovery_dir = tmp_path / "recovery"

    path = write_report(report, recovery_dir)
    first = json.loads(path.read_text())
    path.write_text("incomplete")
    replaced = write_report(report, recovery_dir)

    assert replaced == path
    assert json.loads(replaced.read_text()) == first
    assert not list(recovery_dir.glob("*.tmp"))


def test_cli_refuses_migration_while_visual_indexing_is_enabled(tmp_path, monkeypatch):
    import ytk.cli as cli_mod

    cfg = runtime_config(
        {
            "CHROMA_URL": "http://127.0.0.1:8000",
            "CHROMA_PATH": str(tmp_path / "legacy"),
            "CHROMA_SERVER_PATH": str(tmp_path / "server"),
        }
    )
    monkeypatch.setattr(cli_mod, "runtime_config", lambda: cfg)
    monkeypatch.setenv("YTK_VISUAL_INDEX", "on")

    result = CliRunner().invoke(cli_mod.cli, ["chroma", "migrate"])

    assert result.exit_code != 0
    assert "YTK_VISUAL_INDEX=off" in result.output


def test_cli_refuses_migration_when_legacy_and_server_paths_match(tmp_path, monkeypatch):
    import ytk.cli as cli_mod

    cfg = runtime_config(
        {
            "CHROMA_URL": "http://127.0.0.1:8000",
            "CHROMA_PATH": str(tmp_path / "same"),
            "CHROMA_SERVER_PATH": str(tmp_path / "same"),
        }
    )
    monkeypatch.setattr(cli_mod, "runtime_config", lambda: cfg)
    monkeypatch.setenv("YTK_VISUAL_INDEX", "off")

    result = CliRunner().invoke(cli_mod.cli, ["chroma", "migrate"])

    assert result.exit_code != 0
    assert "must be different" in result.output


def test_cli_migrates_explicit_source_to_http_target_and_writes_report(tmp_path, monkeypatch):
    import ytk.cli as cli_mod

    cfg = runtime_config(
        {
            "CHROMA_URL": "http://127.0.0.1:8765",
            "CHROMA_PATH": str(tmp_path / "legacy"),
            "CHROMA_SERVER_PATH": str(tmp_path / "server"),
        }
    )
    source = object()
    target = object()
    report = MigrationReport(
        started_at="start",
        completed_at="finish",
        source_path=str(cfg.legacy_path),
        target_url=cfg.url or "",
        collections={"ytk_memories": 2},
        excluded=["ytk_visual", "ytk_visual_pending"],
        complete=True,
    )
    calls = {}

    monkeypatch.setenv("YTK_VISUAL_INDEX", "off")
    monkeypatch.setattr(cli_mod, "runtime_config", lambda: cfg)

    def fake_migration_clients(actual_config):
        calls["config"] = actual_config
        return source, target

    monkeypatch.setattr(cli_mod, "create_migration_clients", fake_migration_clients)

    def fake_copy(actual_source, actual_target, *, resume, batch_size):
        calls["copy"] = (actual_source, actual_target, resume, batch_size)
        return report

    monkeypatch.setattr(cli_mod, "copy_collections", fake_copy, raising=False)
    monkeypatch.setattr(
        cli_mod,
        "write_report",
        lambda actual_report, recovery_dir: tmp_path / "migration.json",
        raising=False,
    )

    result = CliRunner().invoke(
        cli_mod.cli,
        ["chroma", "migrate", "--resume", "--batch-size", "64"],
    )

    assert result.exit_code == 0, result.output
    assert calls["config"] is cfg
    assert calls["copy"] == (source, target, True, 64)
    assert "ytk_memories: 2" in result.output
