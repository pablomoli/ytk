"""Local UI server for ytk vault chat and browsing.

Exposes a streaming Anthropic chat endpoint with vault tools pre-wired,
a vault search endpoint, and a note reader endpoint. Serves the single-page
HTML shell from ytk/ui/static/index.html.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import AsyncGenerator

import anthropic
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

_STATIC_DIR = Path(__file__).parent / "static"
_MODEL = "claude-haiku-4-5-20251001"

app = FastAPI(title="ytk vault chat", docs_url=None, redoc_url=None)

# ---------------------------------------------------------------------------
# Vault tools exposed to the LLM
# ---------------------------------------------------------------------------

_VAULT_TOOLS: list[dict] = [
    {
        "name": "vault_search",
        "description": "Semantic search across all vault notes. Returns the most relevant notes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural-language search query"},
                "n": {"type": "integer", "description": "Max results (default 5)", "default": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "vault_read",
        "description": "Read a vault note by its relative path (e.g. 'second-brain/sources/youtube/video-title.md').",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path from vault root"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "vault_remember",
        "description": "Save a memory note to the vault for future retrieval.",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Memory content to save"},
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional tags (e.g. ['ytk', 'insight'])",
                },
            },
            "required": ["content"],
        },
    },
    {
        "name": "vault_list",
        "description": "List vault notes matching an optional glob pattern relative to vault root.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern (default: '**/*.md')",
                    "default": "**/*.md",
                },
                "limit": {"type": "integer", "description": "Max results (default 20)", "default": 20},
            },
        },
    },
]

_SYSTEM_PROMPT = """You are a personal knowledge assistant with access to the user's Obsidian vault.
The vault contains YouTube video notes, web articles, memories, and project session briefs.

Use vault_search to find relevant notes before answering. When the user asks about a video or topic,
search first, then read the most relevant note(s) to give a grounded answer.

Be concise and specific. Reference exact tools, commands, and timestamps from the notes when available.
Never hallucinate content — if you cannot find it, say so and offer to search differently."""


def _dispatch_tool(name: str, inputs: dict) -> str:
    """Execute a vault tool call and return the result as a string."""
    try:
        if name == "vault_search":
            from ytk.store import search_videos
            results = search_videos(inputs["query"], n=inputs.get("n", 5))
            if not results:
                return "No results found."
            lines = []
            for r in results:
                lines.append(f"- [{r.title}] ({r.url}) — distance: {r.distance:.3f}")
            return "\n".join(lines)

        elif name == "vault_read":
            from ytk.vault import read_note
            content = read_note(inputs["path"])
            if content is None:
                return f"Note not found: {inputs['path']}"
            return content[:8000]  # cap to avoid huge context

        elif name == "vault_remember":
            from ytk.vault import remember
            path = remember(inputs["content"], tags=inputs.get("tags") or [])
            return f"Saved to vault: {path}"

        elif name == "vault_list":
            from ytk.vault import _get_vault_path
            vault = _get_vault_path()
            pattern = inputs.get("pattern", "**/*.md")
            limit = inputs.get("limit", 20)
            matches = sorted(vault.glob(pattern))[:limit]
            if not matches:
                return "No notes matched."
            return "\n".join(str(p.relative_to(vault)) for p in matches)

        else:
            return f"Unknown tool: {name}"
    except Exception as exc:
        return f"Tool error: {exc}"


# ---------------------------------------------------------------------------
# Streaming chat endpoint
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    messages: list[dict]
    model: str = _MODEL


async def _stream_chat(messages: list[dict], model: str) -> AsyncGenerator[str, None]:
    """
    Agentic loop: send messages to Anthropic, handle tool_use blocks by
    dispatching vault tools, then continue the stream. Yields SSE-formatted
    text chunks.
    """
    client = anthropic.Anthropic()
    conversation = list(messages)

    while True:
        # Collect a complete response before deciding whether to loop
        full_text = ""
        tool_calls: list[dict] = []
        stop_reason = None

        with client.messages.stream(
            model=model,
            max_tokens=2048,
            system=_SYSTEM_PROMPT,
            tools=_VAULT_TOOLS,
            messages=conversation,
        ) as stream:
            for event in stream:
                if hasattr(event, "type"):
                    if event.type == "content_block_start":
                        if hasattr(event, "content_block") and event.content_block.type == "tool_use":
                            tool_calls.append({
                                "id": event.content_block.id,
                                "name": event.content_block.name,
                                "input_json": "",
                            })
                    elif event.type == "content_block_delta":
                        delta = event.delta
                        if delta.type == "text_delta":
                            full_text += delta.text
                            yield f"data: {json.dumps({'type': 'text', 'text': delta.text})}\n\n"
                        elif delta.type == "input_json_delta":
                            if tool_calls:
                                tool_calls[-1]["input_json"] += delta.partial_json
                    elif event.type == "message_delta":
                        stop_reason = getattr(event.delta, "stop_reason", None)

        if not tool_calls or stop_reason == "end_turn":
            # No tool calls — done
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            break

        # Execute tool calls and continue the loop
        assistant_content = []
        if full_text:
            assistant_content.append({"type": "text", "text": full_text})
        for tc in tool_calls:
            try:
                inputs = json.loads(tc["input_json"]) if tc["input_json"] else {}
            except json.JSONDecodeError:
                inputs = {}
            assistant_content.append({
                "type": "tool_use",
                "id": tc["id"],
                "name": tc["name"],
                "input": inputs,
            })
        conversation.append({"role": "assistant", "content": assistant_content})

        tool_results = []
        for tc in tool_calls:
            try:
                inputs = json.loads(tc["input_json"]) if tc["input_json"] else {}
            except json.JSONDecodeError:
                inputs = {}
            yield f"data: {json.dumps({'type': 'tool_call', 'name': tc['name'], 'inputs': inputs})}\n\n"
            result = _dispatch_tool(tc["name"], inputs)
            yield f"data: {json.dumps({'type': 'tool_result', 'name': tc['name'], 'result': result[:500]})}\n\n"
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tc["id"],
                "content": result,
            })

        conversation.append({"role": "user", "content": tool_results})
        # loop continues — model will process tool results and respond


@app.post("/api/chat")
async def chat(req: ChatRequest):
    return StreamingResponse(
        _stream_chat(req.messages, req.model),
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
