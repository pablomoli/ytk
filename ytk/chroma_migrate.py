"""Safe migration of healthy collections between Chroma clients."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from chromadb.api import ClientAPI

EXCLUDED_COLLECTIONS = frozenset({"ytk_visual", "ytk_visual_pending"})


@dataclass(frozen=True)
class MigrationReport:
    started_at: str
    completed_at: str
    source_path: str
    target_url: str
    collections: dict[str, int]
    excluded: list[str]
    complete: bool


def _client_location(client: ClientAPI) -> str:
    settings = client.get_settings()
    if settings.chroma_server_host:
        scheme = "https" if settings.chroma_server_ssl_enabled else "http"
        return f"{scheme}://{settings.chroma_server_host}:{settings.chroma_server_http_port}"
    return str(settings.persist_directory)


def copy_collections(
    source: ClientAPI,
    target: ClientAPI,
    *,
    resume: bool = False,
    batch_size: int = 256,
) -> MigrationReport:
    """Copy every non-visual collection and verify exact document counts."""
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    if target.list_collections() and not resume:
        raise ValueError("target is not empty; use resume to continue safely")

    started_at = datetime.now(UTC).isoformat()
    source_names = sorted(collection.name for collection in source.list_collections())
    excluded = sorted(EXCLUDED_COLLECTIONS.intersection(source_names))
    included = [name for name in source_names if name not in EXCLUDED_COLLECTIONS]
    copied: dict[str, int] = {}

    for name in included:
        source_collection = source.get_collection(name)
        source_count = source_collection.count()
        target_collection = target.get_or_create_collection(
            name,
            metadata=source_collection.metadata,
        )
        for offset in range(0, source_count, batch_size):
            batch = source_collection.get(
                limit=batch_size,
                offset=offset,
                include=["documents", "metadatas", "embeddings"],
            )
            target_collection.upsert(
                ids=batch["ids"],
                documents=batch["documents"],
                metadatas=batch["metadatas"],
                embeddings=batch["embeddings"],
            )
        target_count = target_collection.count()
        if target_count != source_count:
            raise RuntimeError(
                f"collection {name} count mismatch: source={source_count}, target={target_count}"
            )
        copied[name] = source_count

    return MigrationReport(
        started_at=started_at,
        completed_at=datetime.now(UTC).isoformat(),
        source_path=_client_location(source),
        target_url=_client_location(target),
        collections=copied,
        excluded=excluded,
        complete=True,
    )


def write_report(report: MigrationReport, recovery_dir: Path) -> Path:
    """Atomically persist the latest migration report."""
    recovery_dir.mkdir(parents=True, exist_ok=True)
    path = recovery_dir / "chroma-migration.json"
    temporary = recovery_dir / "chroma-migration.json.tmp"
    temporary.write_text(
        json.dumps(asdict(report), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)
    return path
