"""Chroma runtime configuration and client boundary."""

from __future__ import annotations

import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

from ytk.chroma_runtime import create_client, runtime_config


def _free_tcp_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@contextmanager
def _running_chroma_server(path: Path, port: int):
    executable = Path(sys.executable).with_name("chroma")
    process = subprocess.Popen(
        [
            str(executable),
            "run",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--path",
            str(path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    deadline = time.monotonic() + 20
    try:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                output = process.communicate()[0]
                pytest.fail(f"Chroma server exited before readiness:\n{output}")
            try:
                client = create_client(runtime_config({"CHROMA_URL": f"http://127.0.0.1:{port}"}))
                try:
                    client.heartbeat()
                    break
                finally:
                    client.close()
            except Exception:
                time.sleep(0.05)
        else:
            pytest.fail("Chroma server did not become ready within 20 seconds")
        yield
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)


def test_runtime_defaults_to_embedded(tmp_path):
    cfg = runtime_config({}, default_path=tmp_path / "legacy")

    assert cfg.mode == "embedded"
    assert cfg.legacy_path == tmp_path / "legacy"
    assert cfg.url is None


def test_runtime_selects_loopback_http(tmp_path):
    cfg = runtime_config(
        {
            "CHROMA_URL": "http://127.0.0.1:8000",
            "CHROMA_SERVER_PATH": str(tmp_path / "server"),
        },
        default_path=tmp_path / "legacy",
    )

    assert (cfg.mode, cfg.host, cfg.port, cfg.ssl) == ("http", "127.0.0.1", 8000, False)
    assert cfg.server_path == tmp_path / "server"


@pytest.mark.parametrize(
    "url",
    [
        "http://0.0.0.0:8000",
        "http://192.168.1.2:8000",
        "https://example.com:443",
        "http://127.0.0.1",
        "http://user:pass@127.0.0.1:8000",
        "http://127.0.0.1:8000/api",
        "http://127.0.0.1:8000?tenant=other",
    ],
)
def test_runtime_rejects_non_loopback_or_ambiguous_url(url, tmp_path):
    with pytest.raises(ValueError, match="CHROMA_URL"):
        runtime_config({"CHROMA_URL": url}, default_path=tmp_path / "legacy")


def test_embedded_client_creates_only_the_configured_path(tmp_path):
    legacy = tmp_path / "legacy"
    cfg = runtime_config({}, default_path=legacy)

    client = create_client(cfg)
    try:
        client.create_collection("runtime_test")
        assert legacy.is_dir()
        assert client.get_collection("runtime_test").name == "runtime_test"
    finally:
        client.close()


def test_active_store_info_does_not_claim_legacy_path_is_live_in_http_mode(tmp_path):
    from ytk.chroma_runtime import active_store_info

    cfg = runtime_config(
        {
            "CHROMA_URL": "http://127.0.0.1:8000",
            "CHROMA_PATH": str(tmp_path / "legacy"),
            "CHROMA_SERVER_PATH": str(tmp_path / "server"),
        }
    )

    assert active_store_info(cfg) == {
        "mode": "http",
        "url": "http://127.0.0.1:8000",
        "server_path": str(tmp_path / "server"),
        "legacy_path": str(tmp_path / "legacy"),
    }


def test_default_paths_expand_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))

    cfg = runtime_config(
        {
            "CHROMA_PATH": "~/.ytk/chroma",
            "CHROMA_SERVER_PATH": "~/.ytk/chroma-server",
        }
    )

    assert cfg.legacy_path == tmp_path / ".ytk" / "chroma"
    assert cfg.server_path == tmp_path / ".ytk" / "chroma-server"


def test_http_client_round_trip_with_real_server(tmp_path):
    port = _free_tcp_port()
    with _running_chroma_server(tmp_path / "server", port):
        cfg = runtime_config(
            {
                "CHROMA_URL": f"http://127.0.0.1:{port}",
                "CHROMA_SERVER_PATH": str(tmp_path / "server"),
            },
            default_path=tmp_path / "legacy",
        )
        client = create_client(cfg)
        try:
            col = client.create_collection(
                "round_trip",
                metadata={"hnsw:space": "cosine"},
            )
            col.add(
                ids=["one"],
                embeddings=[[1.0, 0.0]],
                metadatas=[{"kind": "test"}],
            )

            assert col.count() == 1
            assert col.query(query_embeddings=[[1.0, 0.0]], n_results=1)["ids"] == [["one"]]
            client.delete_collection("round_trip")
            assert client.list_collections() == []
        finally:
            client.close()

    assert not (tmp_path / "legacy").exists()
