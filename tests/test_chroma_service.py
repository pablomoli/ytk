"""Local Chroma server lifecycle behavior."""

from __future__ import annotations

import plistlib
import socket
import subprocess
from pathlib import Path

from click.testing import CliRunner

from ytk.chroma_runtime import (
    launchd_plist,
    runtime_config,
    server_arguments,
    wait_for_chroma,
)


def _unused_tcp_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_embedded_runtime_keeps_server_endpoint_defaults(tmp_path):
    cfg = runtime_config({}, default_path=tmp_path / "legacy")

    assert cfg.mode == "embedded"
    assert (cfg.host, cfg.port, cfg.ssl) == ("127.0.0.1", 8000, False)


def test_launchd_plist_is_loopback_persistent_and_keepalive(tmp_path):
    cfg = runtime_config(
        {
            "CHROMA_URL": "http://127.0.0.1:8000",
            "CHROMA_SERVER_PATH": str(tmp_path / "server"),
        },
        default_path=tmp_path / "legacy",
    )

    plist = plistlib.loads(
        launchd_plist(
            cfg,
            ytk_bin=Path("/usr/local/bin/ytk"),
            log_path=tmp_path / "chroma.log",
        ).encode()
    )

    assert plist["Label"] == "com.ytk.chroma"
    assert plist["KeepAlive"] is True
    assert plist["RunAtLoad"] is True
    assert plist["ThrottleInterval"] == 5
    assert plist["ProgramArguments"] == ["/usr/local/bin/ytk", "chroma", "serve"]
    assert plist["StandardOutPath"] == str(tmp_path / "chroma.log")
    assert plist["StandardErrorPath"] == str(tmp_path / "chroma.log")


def test_server_arguments_use_exact_loopback_endpoint_and_data_path(tmp_path):
    cfg = runtime_config(
        {"CHROMA_SERVER_PATH": str(tmp_path / "server")},
        default_path=tmp_path / "legacy",
    )

    assert server_arguments(cfg, Path("/venv/bin/chroma")) == [
        "/venv/bin/chroma",
        "run",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
        "--path",
        str(tmp_path / "server"),
    ]


def test_wait_for_chroma_reports_unreachable_without_creating_legacy_store(tmp_path):
    cfg = runtime_config(
        {"CHROMA_URL": f"http://127.0.0.1:{_unused_tcp_port()}"},
        default_path=tmp_path / "legacy",
    )

    assert not wait_for_chroma(cfg, timeout_s=0.05)
    assert not (tmp_path / "legacy").exists()


def test_chroma_install_writes_and_bootstraps_launch_agent(tmp_path, monkeypatch):
    import ytk.cli as cli_mod

    cfg = runtime_config(
        {"CHROMA_SERVER_PATH": str(tmp_path / "server")},
        default_path=tmp_path / "legacy",
    )
    plist_path = tmp_path / "Library" / "LaunchAgents" / "com.ytk.chroma.plist"
    log_path = tmp_path / ".ytk" / "logs" / "chroma.log"
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(cli_mod, "runtime_config", lambda: cfg, raising=False)
    monkeypatch.setattr(cli_mod, "_CHROMA_PLIST", plist_path, raising=False)
    monkeypatch.setattr(cli_mod, "_CHROMA_LOG", log_path, raising=False)
    monkeypatch.setattr(cli_mod.shutil, "which", lambda name: "/usr/local/bin/ytk")
    monkeypatch.setattr(cli_mod.subprocess, "run", fake_run)

    result = CliRunner().invoke(cli_mod.cli, ["chroma", "install"])

    assert result.exit_code == 0, result.output
    plist = plistlib.loads(plist_path.read_bytes())
    assert plist["ProgramArguments"] == ["/usr/local/bin/ytk", "chroma", "serve"]
    assert calls[0][0][:2] == ["launchctl", "bootout"]
    assert calls[1][0][:2] == ["launchctl", "bootstrap"]


def test_ui_refuses_to_start_before_http_chroma_is_ready(tmp_path, monkeypatch):
    import ytk.cli as cli_mod

    cfg = runtime_config(
        {"CHROMA_URL": "http://127.0.0.1:8000"},
        default_path=tmp_path / "legacy",
    )
    monkeypatch.setattr(cli_mod, "runtime_config", lambda: cfg, raising=False)
    monkeypatch.setattr(cli_mod, "wait_for_chroma", lambda config, timeout_s: False, raising=False)

    result = CliRunner().invoke(cli_mod.cli, ["ui"])

    assert result.exit_code != 0
    assert "Chroma server unavailable at http://127.0.0.1:8000" in result.output
