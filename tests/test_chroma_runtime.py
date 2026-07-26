"""Chroma runtime configuration and client boundary."""

from __future__ import annotations

import pytest

from ytk.chroma_runtime import create_client, runtime_config


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
