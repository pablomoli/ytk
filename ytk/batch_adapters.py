# pyright: basic
# Not strict-clean yet (#122): thin glue over untyped legacy modules
# (metadata, transcript, enrich). The state machine in batch.py is strict.
"""Live adapters behind the batch state machine's seams (#148)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any, cast

from .batch import (
    RESULTS_DIR,
    BatchItem,
    FilteredOut,
    Guard,
    RequestParams,
    enrichment_path,
    payload_path,
)

# The sources with a fetch+file adapter below. Anything else routed overnight
# reaches _fetch and dies as FilteredOut, which is terminal — so every caller
# that decides what to send overnight must gate on this, never on "is bulk".
OVERNIGHT_SOURCES = ("youtube",)


def fetch_youtube_payload(item: BatchItem) -> dict[str, str]:
    """Fetch metadata + transcript now, persist them for the file stage, and
    return the enrichment prompt material. Runs overnight — the expensive
    local work happens here, not in the 5am window."""
    from .config import load_config
    from .enrich import build_system, description_block, fmt_ts, vocab_block
    from .filter import check_pre_transcript
    from .metadata import fetch_metadata
    from .transcript import fetch_transcript, segments_to_text

    meta = fetch_metadata(item.url)
    verdict = check_pre_transcript(meta, load_config())
    if not verdict.passed:
        raise FilteredOut("; ".join(f.reason for f in verdict.failures))
    segments, _source = fetch_transcript(item.url)
    transcript = segments_to_text(segments)

    chapters_text = ""
    if meta.get("chapters"):
        rows = [f"  {fmt_ts(ch['start_time'])} — {ch['title']}" for ch in meta["chapters"]]
        chapters_text = "\nChapters:\n" + "\n".join(rows)
    content_block = f"""\
Title: {meta.get("title", "")}
Uploader: {meta.get("uploader", "")}
Duration: {meta.get("duration", 0)}s
Tags: {", ".join(meta.get("tags", [])[:10])}{chapters_text}
{description_block(meta.get("description", ""))}
Transcript:
{transcript}
"""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    payload_path(item).write_text(
        json.dumps({"meta": meta, "segments": segments}), encoding="utf-8"
    )
    return {"system": build_system("youtube"), "user": content_block + vocab_block()}


def submit_enrichment_batch(requests: list[RequestParams]) -> str:
    import anthropic

    client = anthropic.Anthropic()
    return client.messages.batches.create(requests=cast(Any, requests)).id


def poll_batch(batch_id: str) -> str:
    import anthropic

    return anthropic.Anthropic().messages.batches.retrieve(batch_id).processing_status


def fetch_batch_results(batch_id: str) -> Iterator[dict[str, Any]]:
    import anthropic

    client = anthropic.Anthropic()
    for result in client.messages.batches.results(batch_id):
        if result.result.type == "succeeded":
            message = result.result.message
            text = next((b.text for b in message.content if b.type == "text"), "")
            try:
                enrichment = json.loads(text)
            except json.JSONDecodeError:
                yield {
                    "custom_id": result.custom_id,
                    "type": "errored",
                    "error": "unparseable enrichment JSON",
                }
                continue
            yield {"custom_id": result.custom_id, "type": "succeeded", "enrichment": enrichment}
        else:
            kind = result.result.type
            yield {"custom_id": result.custom_id, "type": kind, "error": kind}


def file_youtube_item(item: BatchItem) -> None:
    """Write the note and embed via the exact synchronous-path functions, so
    the retrieval gate is untouched by construction (same upsert, same
    encoder, same epoch)."""
    from .enrich import Enrichment
    from .store import upsert
    from .vault import NoteAlreadyExists, write_note

    stored = json.loads(payload_path(item).read_text(encoding="utf-8"))
    enrichment = Enrichment.model_validate(
        json.loads(enrichment_path(item).read_text(encoding="utf-8"))
    )
    try:
        write_note(stored["meta"], enrichment, stored["segments"])
    except NoteAlreadyExists:
        pass
    upsert(stored["meta"], enrichment, stored["segments"])


def default_guards(min_free_pct: int = 20) -> list[Guard]:
    def chroma_healthy() -> bool:
        from .chroma_runtime import create_client, runtime_config

        client = create_client(runtime_config())
        try:
            client.heartbeat()
            return True
        finally:
            close = getattr(client, "close", None)
            if close:
                close()

    def memory_sane() -> bool:
        import re
        import subprocess

        out = subprocess.run(
            ["memory_pressure", "-Q"], capture_output=True, text=True, timeout=10
        ).stdout
        match = re.search(r"free percentage: (\d+)", out)
        return bool(match) and int(match.group(1)) >= min_free_pct

    def machine_idle() -> bool:
        import subprocess

        out = subprocess.run(
            ["ioreg", "-c", "IOHIDSystem"], capture_output=True, text=True, timeout=10
        ).stdout
        import re

        match = re.search(r'"HIDIdleTime" = (\d+)', out)
        # 5 minutes of no input counts as idle; HIDIdleTime is nanoseconds
        return bool(match) and int(match.group(1)) > 5 * 60 * 10**9

    return [("chroma", chroma_healthy), ("memory", memory_sane), ("idle", machine_idle)]
