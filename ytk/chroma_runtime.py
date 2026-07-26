"""Runtime selection for embedded and server-backed Chroma clients."""

from __future__ import annotations

import os
import plistlib
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable
from urllib.parse import urlparse

import chromadb
from chromadb.api import ClientAPI

_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


@runtime_checkable
class _Closable(Protocol):
    def close(self) -> None: ...


@dataclass(frozen=True)
class ChromaRuntime:
    mode: Literal["embedded", "http"]
    legacy_path: Path
    server_path: Path
    url: str | None
    host: str
    port: int
    ssl: bool


def runtime_config(
    environ: Mapping[str, str] | None = None,
    *,
    default_path: Path | None = None,
) -> ChromaRuntime:
    """Resolve one local Chroma topology from environment configuration."""
    source = os.environ if environ is None else environ
    legacy_path = Path(
        source.get("CHROMA_PATH", str(default_path or Path.home() / ".ytk" / "chroma"))
    ).expanduser()
    server_path = Path(
        source.get("CHROMA_SERVER_PATH", str(Path.home() / ".ytk" / "chroma-server"))
    ).expanduser()
    url = source.get("CHROMA_URL", "").strip()
    if not url:
        return ChromaRuntime(
            mode="embedded",
            legacy_path=legacy_path,
            server_path=server_path,
            url=None,
            host="127.0.0.1",
            port=8000,
            ssl=False,
        )

    parsed = urlparse(url)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("CHROMA_URL has an invalid port") from exc
    if parsed.scheme != "http" or parsed.hostname not in _LOOPBACK_HOSTS:
        raise ValueError("CHROMA_URL must be an HTTP loopback URL")
    if parsed.username or parsed.password or parsed.path not in {"", "/"}:
        raise ValueError("CHROMA_URL must contain only a loopback host and port")
    if parsed.query or parsed.fragment or port is None:
        raise ValueError("CHROMA_URL must contain only a loopback host and port")

    return ChromaRuntime(
        mode="http",
        legacy_path=legacy_path,
        server_path=server_path,
        url=url.rstrip("/"),
        host=parsed.hostname,
        port=port,
        ssl=False,
    )


def create_client(config: ChromaRuntime) -> ClientAPI:
    """Create the exact client selected by runtime configuration."""
    if config.mode == "http":
        return chromadb.HttpClient(host=config.host, port=config.port, ssl=config.ssl)
    config.legacy_path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(config.legacy_path))


def active_store_info(config: ChromaRuntime | None = None) -> dict[str, str | None]:
    """Serializable storage facts for diagnostics and migration checks."""
    config = config or runtime_config()
    return {
        "mode": config.mode,
        "url": config.url,
        "server_path": str(config.server_path),
        "legacy_path": str(config.legacy_path),
    }


def server_arguments(config: ChromaRuntime, executable: Path) -> list[str]:
    """Exact foreground server command used by launchd and tests."""
    return [
        str(executable),
        "run",
        "--host",
        config.host,
        "--port",
        str(config.port),
        "--path",
        str(config.server_path),
    ]


def launchd_plist(config: ChromaRuntime, *, ytk_bin: Path, log_path: Path) -> str:
    """Render the loopback-only KeepAlive launch agent."""
    payload = {
        "Label": "com.ytk.chroma",
        "ProgramArguments": [str(ytk_bin), "chroma", "serve"],
        "KeepAlive": True,
        "RunAtLoad": True,
        "ThrottleInterval": 5,
        "StandardOutPath": str(log_path),
        "StandardErrorPath": str(log_path),
    }
    return plistlib.dumps(payload, fmt=plistlib.FMT_XML, sort_keys=False).decode()


def wait_for_chroma(config: ChromaRuntime, timeout_s: float = 30.0) -> bool:
    """Wait for the configured server heartbeat until a monotonic deadline."""
    deadline = time.monotonic() + timeout_s
    while True:
        client: ClientAPI | None = None
        try:
            client = chromadb.HttpClient(
                host=config.host,
                port=config.port,
                ssl=config.ssl,
            )
            client.heartbeat()
            return True
        except Exception:
            if time.monotonic() >= deadline:
                return False
        finally:
            if isinstance(client, _Closable):
                client.close()
        time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
