"""Local UI server for ytk vault chat and browsing.

Exposes a streaming Claude Agent SDK chat endpoint with vault tools pre-wired
as in-process MCP tools, a vault search endpoint, and a note reader endpoint.
Serves the single-page HTML shell from ytk/ui/static/index.html.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, AsyncGenerator

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    create_sdk_mcp_server,
    tool,
)
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

_STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="ytk vault chat", docs_url=None, redoc_url=None)


# ---------------------------------------------------------------------------
# Vault tools — exposed to the model as an in-process MCP server
# ---------------------------------------------------------------------------


def _text_result(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


@tool(
    "vault_search",
    "Semantic search across all vault notes. Returns the most relevant notes.",
    {"query": str, "n": int},
)
async def vault_search_tool(args: dict[str, Any]) -> dict[str, Any]:
    from ytk.store import search_videos

    results = search_videos(args["query"], n=int(args.get("n") or 5))
    if not results:
        return _text_result("No results found.")
    lines = [f"- [{r.title}] ({r.url}) — distance: {r.distance:.3f}" for r in results]
    return _text_result("\n".join(lines))


@tool(
    "vault_read",
    "Read a vault note by its relative path (e.g. 'second-brain/sources/youtube/video-title.md').",
    {"path": str},
)
async def vault_read_tool(args: dict[str, Any]) -> dict[str, Any]:
    from ytk.vault import read_note

    content = read_note(args["path"])
    if content is None:
        return _text_result(f"Note not found: {args['path']}")
    return _text_result(content[:8000])


@tool(
    "vault_remember",
    "Save a memory note to the vault for future retrieval.",
    {"content": str, "tags": list},
)
async def vault_remember_tool(args: dict[str, Any]) -> dict[str, Any]:
    from ytk.vault import remember

    path = remember(args["content"], tags=args.get("tags") or [])
    return _text_result(f"Saved to vault: {path}")


@tool(
    "vault_list",
    "List vault notes matching an optional glob pattern relative to vault root.",
    {"pattern": str, "limit": int},
)
async def vault_list_tool(args: dict[str, Any]) -> dict[str, Any]:
    from ytk.vault import _get_vault_path

    vault = _get_vault_path()
    pattern = args.get("pattern") or "**/*.md"
    limit = int(args.get("limit") or 20)
    matches = sorted(vault.glob(pattern))[:limit]
    if not matches:
        return _text_result("No notes matched.")
    return _text_result("\n".join(str(p.relative_to(vault)) for p in matches))


_VAULT_MCP = create_sdk_mcp_server(
    name="vault",
    version="1.0.0",
    tools=[
        vault_search_tool,
        vault_read_tool,
        vault_remember_tool,
        vault_list_tool,
    ],
)

_ALLOWED_TOOLS = [
    "mcp__vault__vault_search",
    "mcp__vault__vault_read",
    "mcp__vault__vault_remember",
    "mcp__vault__vault_list",
]


_SYSTEM_PROMPT = """You are a personal knowledge assistant with access to the user's Obsidian vault.
The vault contains YouTube video notes, web articles, memories, and project session briefs.

Use vault_search to find relevant notes before answering. When the user asks about a video or topic,
search first, then read the most relevant note(s) to give a grounded answer.

Be concise and specific. Reference exact tools, commands, and timestamps from the notes when available.
Never hallucinate content — if you cannot find it, say so and offer to search differently."""


# ---------------------------------------------------------------------------
# Streaming chat endpoint
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    messages: list[dict]
    # `model` retained for wire compatibility with the existing SPA, but the
    # Agent SDK selects the model via Claude Code config, not per-request.
    model: str | None = None


def _flatten_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return " ".join(parts)
    return ""


def _build_prompt(messages: list[dict]) -> str:
    """Flatten the chat history into a single prompt.

    The chat endpoint is stateless — the SPA sends full history every request —
    so we replay prior turns as context and let the latest user message drive
    the response.
    """
    if not messages:
        return ""
    if len(messages) == 1:
        return _flatten_content(messages[0].get("content", ""))

    lines = ["Previous conversation:"]
    for m in messages[:-1]:
        role = (m.get("role") or "user").upper()
        text = _flatten_content(m.get("content", ""))
        if text:
            lines.append(f"\n{role}: {text}")
    latest = _flatten_content(messages[-1].get("content", ""))
    lines.append(f"\n\nCurrent message:\n{latest}")
    return "\n".join(lines)


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event)}\n\n"


async def _stream_chat(messages: list[dict]) -> AsyncGenerator[str, None]:
    """Stream a vault-grounded response via the Claude Agent SDK."""
    prompt = _build_prompt(messages)

    options = ClaudeAgentOptions(
        system_prompt=_SYSTEM_PROMPT,
        mcp_servers={"vault": _VAULT_MCP},
        allowed_tools=_ALLOWED_TOOLS,
        permission_mode="bypassPermissions",
        max_turns=10,
        setting_sources=None,
        env={"ANTHROPIC_API_KEY": ""},
        cli_path=shutil.which("claude"),
    )

    pending_tool_names: dict[str, str] = {}

    try:
        async with ClaudeSDKClient(options=options) as client:
            await client.query(prompt)
            async for msg in client.receive_response():
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            if block.text:
                                yield _sse({"type": "text", "text": block.text})
                        elif isinstance(block, ToolUseBlock):
                            pending_tool_names[block.id] = block.name
                            yield _sse(
                                {
                                    "type": "tool_call",
                                    "name": block.name,
                                    "inputs": block.input,
                                }
                            )
                elif isinstance(msg, UserMessage):
                    for block in msg.content:
                        if isinstance(block, ToolResultBlock):
                            tool_name = pending_tool_names.pop(
                                block.tool_use_id, ""
                            )
                            content = block.content
                            if isinstance(content, list):
                                content = " ".join(
                                    b.get("text", "")
                                    for b in content
                                    if isinstance(b, dict)
                                )
                            elif not isinstance(content, str):
                                content = json.dumps(content)
                            yield _sse(
                                {
                                    "type": "tool_result",
                                    "name": tool_name,
                                    "result": (content or "")[:500],
                                }
                            )
                elif isinstance(msg, ResultMessage):
                    if msg.is_error:
                        yield _sse(
                            {
                                "type": "error",
                                "error": str(msg.result) if msg.result else "Agent SDK error",
                            }
                        )
                    yield _sse({"type": "done"})
                    return
    except Exception as exc:
        yield _sse({"type": "error", "error": str(exc)})
        yield _sse({"type": "done"})


@app.post("/api/chat")
async def chat(req: ChatRequest):
    return StreamingResponse(
        _stream_chat(req.messages),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Vault search endpoint (for sidebar)
# ---------------------------------------------------------------------------


@app.get("/api/search")
async def search(q: str, n: int = 8):
    try:
        from ytk.store import search_videos

        results = search_videos(q, n=n)
        return [
            {
                "title": r.title,
                "url": r.url,
                "distance": r.distance,
                "video_id": r.video_id,
            }
            for r in results
        ]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Vault note reader endpoint (for in-panel display)
# ---------------------------------------------------------------------------


@app.get("/api/note")
async def read_note_api(path: str):
    try:
        from ytk.vault import read_note

        content = read_note(path)
        if content is None:
            raise HTTPException(status_code=404, detail="Note not found")
        return {"path": path, "content": content}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Serve the SPA shell
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = _STATIC_DIR / "index.html"
    if not html_path.exists():
        return HTMLResponse("<h1>UI not found</h1>", status_code=404)
    return HTMLResponse(html_path.read_text(encoding="utf-8"))
