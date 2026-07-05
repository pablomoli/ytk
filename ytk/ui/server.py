"""Local UI server for the ytk ingest hub.

Serves the fresh feed (/), the inbox queue picker (/inbox), the hub API
(queue, ingest job, fresh notes), vault media, plus vault search and note
reader endpoints.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

_STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="ytk ingest hub", docs_url=None, redoc_url=None)


# ---------------------------------------------------------------------------
# Vault search + note reader
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
# Ingest hub: queue, ingest job, fresh feed, vault media
# ---------------------------------------------------------------------------


class QueueAddRequest(BaseModel):
    urls: list[str]


class IngestRequest(BaseModel):
    indices: list[int]
    tags: list[str] = []
    thought: str = ""


@app.post("/api/queue/add")
async def queue_add_api(req: QueueAddRequest):
    from ytk.ui import hub

    added = hub.queue_add(req.urls)
    return {"added": added, "pending": len(hub.queue_items())}


@app.post("/api/queue/refresh")
def queue_refresh_api(force: bool = False):
    # sync def on purpose: FastAPI runs it in a threadpool, and the source
    # pulls (Instagram private API + YouTube Data API) block for seconds
    from ytk.ui import hub

    return hub.refresh_sources(force=force)


class TagRequest(BaseModel):
    name: str


@app.get("/api/tags")
async def tags_api():
    from ytk.ui import hub

    return {"tags": hub.tag_list()}


@app.post("/api/tags")
async def tag_add_api(req: TagRequest):
    from ytk.ui import hub

    try:
        return {"tags": hub.add_tag(req.name)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/queue")
async def queue_api():
    from dataclasses import asdict

    from ytk.ui import hub

    items = [dict(asdict(item), n=i) for i, item in enumerate(hub.queue_items(), 1)]
    return {"items": items}


@app.post("/api/ingest")
async def ingest_api(req: IngestRequest):
    from ytk.ui import hub

    try:
        started = hub.start_ingest(req.indices, req.tags, req.thought)
    except hub.HubBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"started": started}


@app.get("/api/ingest/status")
async def ingest_status_api():
    from ytk.ui import hub

    return hub.job_status()


@app.get("/api/fresh")
async def fresh_api(n: int = 30):
    from ytk.ui import hub

    return hub.fresh_notes(n=n)


@app.get("/api/cover")
def cover_api(u: str):
    # sync def: first request per item downloads from the source CDN
    from fastapi.responses import FileResponse

    from ytk.ui import hub

    path = hub.cover_for(u)
    if path is None:
        raise HTTPException(status_code=404, detail="No cover")
    return FileResponse(path, headers={"Cache-Control": "public, max-age=31536000"})


def _item_id_for_note(note_path: str) -> str | None:
    """Map a vault note to its ytk_visual id via the url in its frontmatter."""
    import re

    p = Path(note_path).expanduser()
    if not p.is_file():
        return None
    head = p.read_text(errors="ignore")[:2000]
    if m := re.search(r"[?&]v=([\w-]{11})|youtu\.be/([\w-]{11})", head):
        return f"yt:{m.group(1) or m.group(2)}"
    if m := re.search(r"instagram\.com/(?:p|reel)/([\w-]+)", head):
        return f"ig:{m.group(1)}"
    return None


@app.get("/api/similar")
def similar_api(q: str = "", note: str = "", n: int = 8):
    # sync def: SigLIP inference runs in FastAPI's threadpool
    from ytk import visual as vis
    from ytk.store import get_visual_embedding, visual_similar

    item_id = None
    embedding = None
    if note:
        item_id = _item_id_for_note(note)
        if item_id is None or get_visual_embedding(item_id) is None:
            return []
    elif get_visual_embedding(q) is not None:
        item_id = q
    elif q:
        embedding = vis.embed_text(q)
    else:
        raise HTTPException(status_code=422, detail="q or note required")
    results = visual_similar(item_id=item_id, embedding=embedding, n=n)
    return [
        {
            "item_id": r.item_id,
            "source": r.source,
            "title": r.title,
            "url": r.url,
            "image_path": r.image_path,
            "note_path": r.note_path,
            "distance": r.distance,
        }
        for r in results
    ]


@app.post("/api/snap")
async def snap_api(request: Request, note: str = "", tags: str = ""):
    """Accept a raw image body (phone screenshot via Tailscale + iOS Shortcut).
    The note travels as a query param: POST /api/snap?note=...&tags=a,b"""
    from ytk.snap import save_snap

    body = await request.body()
    if len(body) < 100:
        raise HTTPException(status_code=422, detail="No image body")
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    note_path = save_snap(body, note.strip(), tag_list)
    return {"saved": note_path.name, "note": note.strip()}


@app.get("/api/visual-image")
def visual_image_api(id: str):
    from fastapi.responses import FileResponse
    from pathlib import Path as _P

    from ytk.store import _visual_collection

    res = _visual_collection().get(ids=[id])
    if not res["ids"]:
        raise HTTPException(status_code=404, detail="Unknown item")
    p = _P(res["metadatas"][0].get("image_path", ""))
    allowed = (
        _P.home() / ".ytk" / "covers",
        _P(os.environ.get("OBSIDIAN_VAULT_PATH", "")).expanduser(),
    )
    rp = p.resolve()
    if not p.is_file() or not any(
        str(a) and rp.is_relative_to(a.resolve()) for a in allowed if str(a)
    ):
        raise HTTPException(status_code=404, detail="No image")
    return FileResponse(p, headers={"Cache-Control": "public, max-age=86400"})


@app.get("/vault-media/{rel_path:path}")
async def vault_media(rel_path: str):
    from fastapi.responses import FileResponse

    from ytk.vault import _get_brain_path

    brain = _get_brain_path().resolve()
    target = (brain / rel_path).resolve()
    if not target.is_relative_to(brain) or not target.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(target)


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


def _serve_static(name: str) -> HTMLResponse:
    html_path = _STATIC_DIR / name
    if not html_path.exists():
        return HTMLResponse("<h1>UI not found</h1>", status_code=404)
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.get("/inbox", response_class=HTMLResponse)
async def inbox_page():
    return _serve_static("inbox.html")


@app.get("/", response_class=HTMLResponse)
async def index():
    return _serve_static("fresh.html")
