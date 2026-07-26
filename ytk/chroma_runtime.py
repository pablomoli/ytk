"""Runtime selection for embedded and server-backed Chroma clients."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import chromadb
from chromadb.api import ClientAPI

_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


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
            host="",
            port=0,
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
