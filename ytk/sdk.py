# pyright: basic
# Not strict-clean yet (#122). Delete these two lines once the module
# passes strict — the list of files carrying them only shrinks.
"""All ytk LLM transport lives here.

Two entry points:

- `structured(system, user, Result)` — schema-forced classification returning a
  validated Pydantic instance. This is the front door for every cheap Haiku
  pass (memo routing, triage, directive interpretation, future classifiers).
  Dual-path: direct Anthropic API (~1.5s) when ANTHROPIC_API_KEY is set,
  otherwise the Agent SDK subprocess (~10s) on Claude Code subscription auth.
- `run_structured(...)` — the raw Agent SDK call. Enrichment uses it directly
  because `add_dirs` (mounting frame/slide folders) only exists on the SDK
  path; everything else should prefer `structured`.

The helpers are synchronous from the caller's perspective — each call spins up
its own event loop via `asyncio.run`. That's fine for ytk's click-CLI call
sites.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
)
from pydantic import BaseModel

log = logging.getLogger(__name__)

_FAST_MODEL = "claude-haiku-4-5"


@dataclass
class StructuredResult:
    """A structured call plus what it cost (#197 P4): activity rows carry
    model, tokens, duration_ms, so the transport must not discard them."""

    data: dict[str, Any]
    model: str | None
    tokens: int | None  # input + output; the full usage dict keeps the rest
    duration_ms: int | None
    usage: dict[str, Any] | None


def result_from(msg: ResultMessage, requested_model: str | None) -> StructuredResult:
    """Map a ResultMessage to a StructuredResult. Usage may be absent under
    subscription auth (recorded spec uncertainty) — every field is
    None-tolerant so the token ceiling can fall back to a call count."""
    tokens = None
    if msg.usage is not None:
        tokens = int(msg.usage.get("input_tokens", 0)) + int(msg.usage.get("output_tokens", 0))
    model = requested_model
    if model is None and msg.model_usage:
        model = next(iter(msg.model_usage))
    return StructuredResult(
        data=msg.structured_output,
        model=model,
        tokens=tokens,
        duration_ms=msg.duration_ms,
        usage=msg.usage,
    )


def structured[R: BaseModel](
    system_prompt: str,
    user_prompt: str,
    result: type[R],
    *,
    model: str = _FAST_MODEL,
    max_input_chars: int = 20_000,
    max_tokens: int = 1024,
) -> R:
    """Schema-forced one-shot classification; returns a validated `result`.

    Fast path: direct API when ANTHROPIC_API_KEY is set. Fallback (and the
    normal path on subscription-only auth): Agent SDK subprocess. `max_tokens`
    bounds the response on the direct-API path; long-form callers (the recap
    narrative) raise it above the classification default.
    """
    schema = result.model_json_schema()
    user_prompt = user_prompt[:max_input_chars]
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if api_key:
        try:
            data = _structured_via_api(
                system_prompt, user_prompt, schema, api_key, model, max_tokens
            )
            return result.model_validate(data)
        except Exception:
            log.warning("direct API call failed; falling back to Agent SDK", exc_info=True)
    data = run_structured(system_prompt, user_prompt, schema, model=model)
    return result.model_validate(data)


def _structured_via_api(
    system: str, user: str, schema: dict, api_key: str, model: str, max_tokens: int = 1024
) -> dict:
    """Direct Anthropic API call with forced tool-use for structured output.
    ~1.5s round-trip vs ~11s for a Claude Code CLI subprocess; classification
    payloads are small, so the credit cost is negligible unlike enrichment."""
    import json
    import urllib.request

    body = json.dumps(
        {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "tools": [
                {
                    "name": "emit_result",
                    "description": "Emit the classification.",
                    "input_schema": schema,
                }
            ],
            "tool_choice": {"type": "tool", "name": "emit_result"},
        }
    ).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read())
    for block in payload.get("content", []):
        if block.get("type") == "tool_use":
            return block["input"]
    raise RuntimeError(f"no tool_use block in response: {payload.get('stop_reason')}")


# The Agent SDK's _find_cli() prefers its own bundled `claude` binary over the
# system one. The bundled binary does not share the user's OAuth credentials,
# so it auths as anonymous and falls back to ANTHROPIC_API_KEY (which we want
# unset to force subscription billing). Pin to the system CLI so the call uses
# the keychain-stored OAuth token from `claude /login`.
_SYSTEM_CLAUDE_CLI = shutil.which("claude")


def run_structured(
    system_prompt: str,
    user_prompt: str,
    schema: dict,
    add_dirs: Sequence[str | Path] | None = None,
    max_turns: int = 20,
    model: str | None = None,
) -> dict:
    """Legacy front door: JSON only. New callers that write activity rows
    use call_structured, which keeps the usage fields."""
    return call_structured(
        system_prompt, user_prompt, schema, add_dirs=add_dirs, max_turns=max_turns, model=model
    ).data


def call_structured(
    system_prompt: str,
    user_prompt: str,
    schema: dict[str, Any],
    *,
    add_dirs: Sequence[str | Path] | None = None,
    max_turns: int = 20,
    model: str | None = None,
) -> StructuredResult:
    """Run a one-shot structured call against Claude Code; returns the JSON
    plus model/tokens/duration for the caller's activity row.

    The schema must be a valid JSON Schema object (object root). Set
    `add_dirs` to grant filesystem Read access to extracted frames/slides.
    """
    return asyncio.run(
        _run_structured_async(system_prompt, user_prompt, schema, add_dirs or [], max_turns, model)
    )


def _build_options(
    system_prompt: str,
    schema: dict,
    add_dirs: Sequence[str | Path],
    max_turns: int,
    model: str | None = None,
) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        model=model,
        system_prompt=system_prompt,
        allowed_tools=["Read"] if add_dirs else [],
        permission_mode="bypassPermissions",
        max_turns=max_turns,
        add_dirs=[str(d) for d in add_dirs],
        output_format={"type": "json_schema", "schema": schema},
        setting_sources=None,
        env={"ANTHROPIC_API_KEY": ""},
        cli_path=_SYSTEM_CLAUDE_CLI,
        # one base64-encoded carousel slide can exceed the 1MB default
        max_buffer_size=32 * 1024 * 1024,
    )


async def _run_structured_async(
    system_prompt: str,
    user_prompt: str,
    schema: dict,
    add_dirs: Sequence[str | Path],
    max_turns: int,
    model: str | None = None,
) -> StructuredResult:
    options = _build_options(system_prompt, schema, add_dirs, max_turns, model)

    async with ClaudeSDKClient(options=options) as client:
        await client.query(user_prompt)
        async for msg in client.receive_response():
            if isinstance(msg, ResultMessage):
                if msg.is_error:
                    raise RuntimeError(
                        f"Agent SDK call failed ({msg.subtype}): "
                        f"result={msg.result!r} errors={msg.errors!r}"
                    )
                if msg.structured_output is None:
                    raise RuntimeError(
                        f"Agent SDK returned no structured output; result={msg.result!r}"
                    )
                return result_from(msg, model)

    raise RuntimeError("Agent SDK stream ended without a ResultMessage")
