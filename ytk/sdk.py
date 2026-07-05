"""Thin wrapper around the Claude Agent SDK for structured one-shot enrichment.

All ytk LLM calls go through `run_structured`. It uses the user's Claude Code
subscription auth (via the Agent SDK) rather than direct Anthropic API credits.

The helper is synchronous from the caller's perspective — each call spins up its
own event loop via `asyncio.run`. That's fine for ytk's click-CLI call sites.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
)

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
    add_dirs: list[str | Path] | None = None,
    max_turns: int = 20,
) -> dict:
    """Run a one-shot enrichment against Claude Code and return validated JSON.

    The schema must be a valid JSON Schema object (object root). Set
    `add_dirs` to grant filesystem Read access to extracted frames/slides.
    """
    return asyncio.run(
        _run_structured_async(
            system_prompt, user_prompt, schema, add_dirs or [], max_turns
        )
    )


def _build_options(
    system_prompt: str,
    schema: dict,
    add_dirs: list[str | Path],
    max_turns: int,
) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
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
    add_dirs: list[str | Path],
    max_turns: int,
) -> dict:
    options = _build_options(system_prompt, schema, add_dirs, max_turns)

    async with ClaudeSDKClient(options=options) as client:
        await client.query(user_prompt)
        async for msg in client.receive_response():
            if isinstance(msg, ResultMessage):
                if msg.is_error:
                    raise RuntimeError(f"Agent SDK call failed: {msg.result!r}")
                if msg.structured_output is None:
                    raise RuntimeError(
                        f"Agent SDK returned no structured output; result={msg.result!r}"
                    )
                return msg.structured_output

    raise RuntimeError("Agent SDK stream ended without a ResultMessage")
