"""Local UI server for the ytk ingest hub.

Serves the fresh feed (/), the inbox queue picker (/inbox), the hub API
(queue, ingest job, fresh notes), vault media, plus vault search and note
reader endpoints.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
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
