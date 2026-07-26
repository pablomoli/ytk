# pyright: basic
# Not strict-clean yet (#122). Delete these two lines once the module
# passes strict — the list of files carrying them only shrinks.
"""Local UI server for the ytk ingest hub.

Serves the fresh feed (/), the inbox queue picker (/inbox), the hub API
(queue, ingest job, fresh notes), vault media, plus vault search and note
reader endpoints.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

_STATIC_DIR = Path(__file__).parent / "static"

from contextlib import asynccontextmanager


@asynccontextmanager
async def _lifespan(app: FastAPI):
    from ytk.ui import hub

    # Pick a batch back up before anything else: the hub is killed and restarted
    # whenever its uv-installed package is reinstalled under it, and the queue
    # lives in memory, so an interrupted ingest would otherwise vanish silently.
    revived = hub.resume_ingest()
    if revived:
        print(f"resumed {revived} interrupted ingest item(s)")

    # Watch chat.db so self-notes land within seconds, and preload the search
    # model so the first real search doesn't eat the cold-start lag.
    hub.probe_capture_health()
    hub.start_imessage_watcher()
    hub.start_sync_catchup()
    hub.warm_search()
    yield


app = FastAPI(title="ytk ingest hub", docs_url=None, redoc_url=None, lifespan=_lifespan)

from datetime import UTC

from fastapi.staticfiles import StaticFiles

app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


# ---------------------------------------------------------------------------
# Vault search + note reader
# ---------------------------------------------------------------------------


@app.get("/api/search")
async def search(q: str, n: int = 8):
    try:
        from ytk.store import search_videos
        from ytk.ui.hub import log_search_query

        log_search_query("/api/search", q)
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


class NoteDeleteRequest(BaseModel):
    path: str


@app.post("/api/note/delete")
def delete_note_api(req: NoteDeleteRequest):
    from ytk.ui import hub

    try:
        summary = hub.delete_note(req.path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Note not found")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"deleted": True, "removed": summary}


# ---------------------------------------------------------------------------
# Ingest hub: queue, ingest job, fresh feed, vault media
# ---------------------------------------------------------------------------


class EnrichPreviewRequest(BaseModel):
    tone: str = ""


@app.post("/api/enrich-preview")
def enrich_preview_api(req: EnrichPreviewRequest):
    from ytk.enrich_eval import run_eval

    try:
        return run_eval(req.tone)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


class QueueAddRequest(BaseModel):
    urls: list[str]


class IngestRequest(BaseModel):
    urls: list[str]
    tags: list[str] = []
    thought: str = ""


@app.post("/api/queue/add")
async def queue_add_api(req: QueueAddRequest):
    from ytk.ui import hub

    added = hub.queue_add(req.urls)
    return {"added": added, "pending": len(hub.queue_items())}


@app.post("/api/queue/refresh")
def queue_refresh_api(force: bool = False, only: str | None = None):
    # sync def on purpose: FastAPI runs it in a threadpool, and the source
    # pulls (Instagram private API + YouTube Data API) block for seconds
    from ytk.ui import hub

    # `only` is a comma-separated allow-list from the source-pull menu. Intersect
    # with the real pull sources so an unknown name can never reach the pull
    # dispatch; an empty result means "nothing valid asked for", not "pull all",
    # so we keep it as an empty set rather than collapsing to None.
    selected: set[str] | None = None
    if only is not None:
        selected = {s.strip() for s in only.split(",") if s.strip()} & hub.PULL_SOURCES
    return hub.refresh_sources(force=force, only=selected)


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


@app.post("/api/tags/merge/propose")
async def tag_merge_propose_api():
    from ytk.ui import hub

    return {"started": hub.start_tag_proposals()}


@app.get("/api/tags/merge/status")
async def tag_merge_status_api():
    from ytk.ui import hub

    return hub.tags_merge_status()


class TagMergeRequest(BaseModel):
    mapping: dict[str, str]


@app.post("/api/tags/merge/apply")
def tag_merge_apply_api(req: TagMergeRequest):
    # sync def on purpose: frontmatter + Chroma rewrites run in the threadpool
    from ytk.ui import hub

    return hub.apply_tag_merges(req.mapping)


@app.get("/api/queue")
async def queue_api():
    from dataclasses import asdict

    from ytk.ui import hub

    items = [dict(asdict(item), n=i) for i, item in enumerate(hub.queue_items(), 1)]
    return {"items": items}


@app.post("/api/queue/profile-rank")
async def queue_profile_rank_api():
    """Start the expensive, on-demand profile ranking for pending items."""
    from ytk.ui import hub

    return {"started": hub.start_profile_rank()}


@app.get("/api/queue/profile-rank/status")
async def queue_profile_rank_status_api():
    """Return the active rank job or the last result cached on disk."""
    from ytk.ui import hub

    return hub.profile_rank_status()


@app.post("/api/recap")
def recap_api(n: int = 12):
    # sync def on purpose: gather_recent hits the embedder and synthesize makes
    # a Claude call, both blocking for seconds; FastAPI runs it in a threadpool.
    from ytk import digest

    ctx = digest.gather_recent(n=n)
    return {"markdown": digest.synthesize(ctx), "count": len(ctx.ingests)}


@app.post("/api/ingest")
async def ingest_api(req: IngestRequest):
    from ytk.ui import hub

    try:
        started = hub.start_ingest(req.urls, req.tags, req.thought)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"started": started}


@app.get("/api/ingest/status")
async def ingest_status_api():
    from ytk.ui import hub

    return hub.job_status()


@app.post("/api/memo")
async def memo_api(
    file: UploadFile | None = File(default=None),
    text: str = Form(default=""),
):
    from ytk.ui import hub

    if file is None and not text:
        raise HTTPException(status_code=422, detail="file or text required")
    audio = await file.read() if file is not None else b""
    filename = file.filename if file is not None else ""
    if not hub.start_memo(audio, filename or "memo.m4a", text):
        raise HTTPException(status_code=409, detail="memo job already running")
    return {"status": "accepted"}


@app.get("/api/memo/status")
async def memo_status_api():
    from ytk.ui import hub

    return hub.memo_status()


@app.get("/api/fresh")
async def fresh_api(n: int = 30):
    from ytk.ui import hub

    return hub.fresh_notes(n=n)


@app.get("/api/library")
async def library_api(n: int = 60, offset: int = 0, source: str = "", q: str = ""):
    """The whole ingested store as cards — the fresh feed without the window."""
    from ytk.ui import hub

    return hub.library_notes(n=n, offset=offset, source=source, match=q)


@app.get("/api/channels")
async def channels_api():
    """Creators you consume, grouped and loved-first, for the /channels page."""
    from ytk.ui import hub

    return {"channels": hub.channels_list()}


class ChannelStatusRequest(BaseModel):
    status: str | None = None


@app.post("/api/channels/{key:path}/status")
async def channel_status_api(key: str, req: ChannelStatusRequest):
    """Set a creator's loved/muted flag (null clears it)."""
    from ytk.ui import hub

    try:
        return {"affinity": hub.set_channel_status(key, req.status)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/recs")
async def recs_api(kind: str = ""):
    """Resolved movie/show/anime/book/manga recommendations for the /recs page."""
    from ytk.ui import hub

    return {"recs": hub.recs_list(kind or None)}


class RecStatusRequest(BaseModel):
    status: str | None = None


@app.post("/api/recs/{key:path}/status")
async def rec_status_api(key: str, req: RecStatusRequest):
    """Set a rec's want/seen/skip flag (null clears it)."""
    from ytk.ui import hub

    try:
        hub.set_rec_status(key, req.status)
        return {"ok": True}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/profile")
async def profile_api():
    """The latest interest snapshot, shaped for the /profile page."""
    from ytk import interest

    snap = interest.load_latest()
    if snap is None:
        raise HTTPException(status_code=404, detail="no interest snapshot yet — run ytk profile")
    return {
        "generated_at": snap.generated_at,
        "note_count": snap.note_count,
        "embedding_model": snap.embedding_model,
        "reanchored_from": snap.reanchored_from,
        "alpha": snap.alpha,
        "decay_half_life_days": snap.decay_half_life_days,
        "profile_markdown": snap.profile_markdown,
        "profile_score": snap.profile_score.model_dump() if snap.profile_score else None,
        "claims": [{"text": c.text, "evidence_ids": c.evidence_ids} for c in snap.portrait_claims],
        "themes": [
            {
                "id": t.id,
                "label": t.label,
                "summary": t.summary,
                "weight": t.weight,
                "n_notes": len(t.note_ids),
                "fresh_notes": t.fresh_note_count,
                "exemplars": [
                    {"title": title, "source": source}
                    for title, source in zip(
                        t.exemplar_titles[:3],
                        (t.exemplar_sources + [""] * 3)[:3],
                    )
                ],
                "evidence_ids": t.evidence_ids,
                "note_ids": t.note_ids,
            }
            for t in snap.themes
        ],
    }


@app.post("/api/profile/run")
def profile_run_api():
    # sync def: run_profile blocks on one Haiku call (~15-60 s) in the threadpool
    from ytk.synthesis import SynthesisTooSparse, run_profile

    try:
        snap, _ = run_profile()
    except SynthesisTooSparse as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"generated_at": snap.generated_at, "themes": len(snap.themes)}


_GROVE_BUCKETS_PATH = Path.home() / ".ytk" / "grove_buckets.yaml"


@app.get("/api/grove-buckets")
async def grove_buckets_get():
    text = _GROVE_BUCKETS_PATH.read_text(encoding="utf-8") if _GROVE_BUCKETS_PATH.exists() else ""
    return {"text": text, "path": str(_GROVE_BUCKETS_PATH)}


@app.put("/api/grove-buckets")
async def grove_buckets_put(request: Request):
    """Save the bucket file VERBATIM after validation — it is hand-authored
    yaml whose comments document the matching rules; round-tripping through a
    parser would destroy them."""
    import yaml

    raw = (await request.json()).get("text", "")
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=422, detail=f"invalid yaml: {exc}")
    if not isinstance(data, dict) or not isinstance(data.get("buckets"), list):
        raise HTTPException(status_code=422, detail="top level needs a 'buckets' list")
    names = []
    for i, b in enumerate(data["buckets"]):
        if not isinstance(b, dict) or not b.get("name"):
            raise HTTPException(status_code=422, detail=f"bucket {i} needs a name")
        names.append(str(b["name"]))
    if len(set(names)) != len(names):
        raise HTTPException(status_code=422, detail="duplicate bucket names")
    _GROVE_BUCKETS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _GROVE_BUCKETS_PATH.write_text(raw, encoding="utf-8")
    return {
        "saved": True,
        "buckets": names,
        "hint": "rebuild to apply: uv run --extra dev python -m scripts.grove_lab.dendro --rebuild",
    }


_GROWTH_PHILOSOPHY_PATH = Path.home() / ".ytk" / "growth_philosophy.md"

_GROWTH_PHILOSOPHY_DEFAULT = """---
glow_max: 0.35
asymmetry_min: 0.45
curvature_min: 0.3
saturation_max: 0.8
---

# Growth philosophy

Hard constraints live in the frontmatter above and are enforced by the
workbench. The prose below is for you (and a future LLM steering layer).

- Never reads as a graph: no hub-and-spoke, no straight radial spokes.
- Organic before geometric; asymmetric before balanced.
- Color belongs to the content: palettes come from the notes themselves.
"""


@app.get("/api/growth/philosophy")
async def growth_philosophy_get():
    if not _GROWTH_PHILOSOPHY_PATH.exists():
        _GROWTH_PHILOSOPHY_PATH.parent.mkdir(parents=True, exist_ok=True)
        _GROWTH_PHILOSOPHY_PATH.write_text(_GROWTH_PHILOSOPHY_DEFAULT, encoding="utf-8")
    return {
        "text": _GROWTH_PHILOSOPHY_PATH.read_text(encoding="utf-8"),
        "path": str(_GROWTH_PHILOSOPHY_PATH),
    }


@app.put("/api/growth/philosophy")
async def growth_philosophy_put(request: Request):
    """Save verbatim — hand-authored markdown, same contract as grove-buckets."""
    raw = (await request.json()).get("text", "")
    if not raw.strip():
        raise HTTPException(status_code=422, detail="empty philosophy")
    _GROWTH_PHILOSOPHY_PATH.parent.mkdir(parents=True, exist_ok=True)
    _GROWTH_PHILOSOPHY_PATH.write_text(raw, encoding="utf-8")
    return {"saved": True}


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


_pending_sync_lock = __import__("threading").Lock()


def _kick_pending_sync() -> None:
    """Refresh the pending-covers index in the background, at most one at a time."""
    import threading

    def run():
        if not _pending_sync_lock.acquire(blocking=False):
            return
        try:
            from ytk import visual

            visual.sync_pending_visual()
        except Exception:
            pass
        finally:
            _pending_sync_lock.release()

    threading.Thread(target=run, daemon=True).start()


@app.get("/api/ready")
def ready_api():
    """Readiness of the search subsystem, for the UI's warming indicator.

    capture_problems surfaces dead capture sources (e.g. chat.db access lost
    to a TCC reset) so a broken pipeline is visible instead of silent."""
    from ytk.ui import hub

    return {"search": hub.search_ready(), "capture_problems": hub._CAPTURE_PROBLEMS}


@app.get("/api/imessage-warm")
def imessage_warm_api():
    """Still-warm self-note sessions, for the inbox 'brewing' card."""
    from ytk.ui import hub

    try:
        return {"warm": hub.imessage_warm()}
    except Exception:
        return {"warm": []}


@app.get("/api/inbox-search")
def inbox_search_api(q: str, n: int = 30, scope: str = "ingested"):
    """Visual+text search for the inbox picker.

    scope=ingested: note-backed covers (re-ingest candidates).
    scope=pending: covers of items waiting in the queue (find-to-drain)."""
    from ytk import visual
    from ytk.store import pending_visual_similar, visual_similar
    from ytk.vault import _get_brain_path

    if not q.strip():
        return {"results": []}
    from ytk.ui.hub import log_search_query

    log_search_query("/api/inbox-search", q)
    brain = _get_brain_path().resolve()
    try:
        embedding = visual.embed_text(q)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"embed failed: {exc}")

    if scope == "pending":
        _kick_pending_sync()  # pick up newly cached covers for next search
        hits = pending_visual_similar(embedding=embedding, n=n)
        return {
            "results": [
                {
                    "url": r.url,
                    "title": r.title,
                    "source": r.source,
                    "thumbnail": None,  # served via /api/cover?u= like grid cards
                    "pending": True,
                    "distance": r.distance,
                }
                for r in hits
            ]
        }

    # small over-fetch: a few indexed covers (old tiktok thumbs) lack urls
    hits = visual_similar(embedding=embedding, n=n + 10)

    out = []
    for r in hits:
        if not r.url:
            continue  # not re-ingestable without a url
        if len(out) >= n:
            break
        thumb = None
        try:
            p = Path(r.image_path).resolve()
            if p.is_relative_to(brain):
                thumb = str(p.relative_to(brain))
        except Exception:
            pass
        out.append(
            {
                "url": r.url,
                "title": r.title,
                "source": r.source,
                "thumbnail": thumb,
                "distance": r.distance,
            }
        )
    return {"results": out}


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
    from pathlib import Path as _P

    from fastapi.responses import FileResponse

    from ytk.store import get_visual_metadata, meta_str

    metadata = get_visual_metadata(id)
    if metadata is None:
        raise HTTPException(status_code=404, detail="Unknown item")
    p = _P(meta_str(metadata, "image_path"))
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


@app.get("/api/memo-audio/{name}")
async def memo_audio(name: str):
    """Serve a memo recording by basename from the memo audio dir only."""
    from fastapi.responses import FileResponse

    from ytk.memo import AUDIO_DIR

    root = AUDIO_DIR.resolve()
    target = (root / name).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(target)


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


@app.get("/favicon.svg")
async def favicon():
    from fastapi.responses import Response

    from ytk.config import load_config

    glyph = load_config().hub.favicon or "✦"
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
        '<rect width="32" height="32" rx="7" fill="#000"/>'
        '<text x="16" y="17" font-size="20" fill="#e2b04a" '
        'text-anchor="middle" dominant-baseline="central">'
        f"{glyph}</text></svg>"
    )
    return Response(svg, media_type="image/svg+xml")


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


@app.get("/api/settings")
async def settings_get():
    from ytk import reels
    from ytk.config import load_config
    from ytk.ui import hub

    cfg = load_config()
    state = reels.load_state(hub.STATE_PATH)
    return {
        "config": cfg.model_dump(mode="json"),
        "meta": {
            "restart_required_fields": ["hub.host", "hub.port"],
            "last_pulls": state.last_pulls,
            "last_pull_at": state.last_pull_at,
            "environment": _environment_info(),
        },
    }


def _environment_info() -> dict:
    """Read-only facts for the settings page: where data lives, which
    encoder epoch is serving, how the daemon is packaged."""
    from ytk import store, vault

    epoch = store.EMBEDDING_EPOCH
    return {
        "vault_path": str(vault._get_brain_path()),
        "chroma_path": str(store._CHROMA_PATH),
        "embedding_epoch": epoch,
        "embedding_model": store._EPOCHS[epoch]["model"],
        "collections": store.epoch_collection_name("ytk_*"),
        "app_bundle": Path("/Applications/ytk.app").exists(),
        "grove_buckets_path": str(_GROVE_BUCKETS_PATH),
    }


@app.put("/api/settings")
async def settings_put(request: Request):
    from pydantic import ValidationError

    from ytk.config import Config, load_config, save_config

    raw = await request.json()
    before = load_config()
    try:
        cfg = Config.model_validate(raw)
    except ValidationError as exc:
        # field-path -> message, so the page can render errors inline
        errors = [
            {"loc": ".".join(str(p) for p in e["loc"]), "msg": e["msg"]} for e in exc.errors()
        ]
        raise HTTPException(status_code=422, detail=errors)
    save_config(cfg)
    restart_required = cfg.hub.host != before.hub.host or cfg.hub.port != before.hub.port
    return {"saved": True, "restart_required": restart_required}


_GROVE_DIR = Path.home() / ".ytk" / "grove"


@app.get("/api/grove")
async def grove_topology_api():
    """Per-bucket tree topology snapshots for the grove's data-native mode.

    Serves render data only: centroids and member maps are attach-time
    machinery (scripts/grove_lab/dendro.py) and stay server-side.
    """
    snaps = sorted(_GROVE_DIR.glob("*.tree.json")) if _GROVE_DIR.exists() else []
    if not snaps:
        raise HTTPException(
            status_code=404,
            detail="No grove topology built yet — run: "
            "uv run --extra dev python -m scripts.grove_lab.dendro",
        )
    buckets = []
    for p in snaps:
        snap = json.loads(p.read_text())
        bucket = {
            "bucket": snap["bucket"],
            "n_notes": snap["n_notes"],
            "built": snap.get("built"),
            "embedding_model": snap.get("embedding_model"),
            "params": snap.get("params"),
            "stability": snap.get("stability"),
            "nodes": [{k: v for k, v in n.items() if k != "centroid"} for n in snap["nodes"]],
        }
        if snap.get("palette"):
            bucket["palette"] = snap["palette"]
        buckets.append(bucket)
    return {"version": 1, "buckets": buckets}


class E7Response(BaseModel):
    trial: str
    choice: str
    confidence: int = Field(ge=1, le=5)
    rt_ms: int = Field(ge=0)


def _e7_manifest() -> dict:
    path = _GROVE_DIR / "e7-manifest.json"
    if not path.exists():
        raise HTTPException(
            status_code=404, detail="no E7 manifest; run scripts.grove_lab.e7_manifest"
        )
    return json.loads(path.read_text())


def _e7_log(sha: str) -> list[dict]:
    path = _GROVE_DIR / "e7-responses.jsonl"
    if not path.exists():
        return []
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return [r for r in rows if r.get("manifest_sha") == sha]


@app.get("/api/grove/e7")
async def grove_e7_manifest():
    """The public E7 manifest (truth lives only in the private answer key,
    never in this file) plus completed trial ids for safe resume."""
    manifest = _e7_manifest()
    manifest["completed"] = [r["trial"] for r in _e7_log(manifest["sha256"])]
    return manifest


@app.post("/api/grove/e7/response")
async def grove_e7_response(resp: E7Response):
    """Validated, idempotent, append-only. Correctness is never computed
    here — the answer key is not readable by this process's code path."""
    from datetime import datetime

    manifest = _e7_manifest()
    trial = next((t for t in manifest["trials"] if t["trial"] == resp.trial), None)
    if trial is None:
        raise HTTPException(status_code=404, detail="unknown trial")
    allowed = trial["options"] if trial.get("options") else ["left", "right"]
    if resp.choice not in allowed:
        raise HTTPException(status_code=400, detail=f"choice must be one of {allowed}")
    prior = [r for r in _e7_log(manifest["sha256"]) if r["trial"] == resp.trial]
    if prior:
        same = prior[0]["choice"] == resp.choice and prior[0]["confidence"] == resp.confidence
        if same:
            return {"logged": True, "duplicate": True}
        raise HTTPException(status_code=409, detail="conflicting duplicate for this trial")
    row = {
        **resp.model_dump(),
        "manifest_sha": manifest["sha256"],
        "ts": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    with (_GROVE_DIR / "e7-responses.jsonl").open("a") as f:
        f.write(json.dumps(row) + "\n")
    return {"logged": True}


@app.get("/api/map")
async def map_data_api():
    map_path = Path.home() / ".ytk" / "map.json"
    if not map_path.exists():
        map_path = _STATIC_DIR / "map.json"  # pre-runtime-dir builds
    if not map_path.exists():
        raise HTTPException(
            status_code=404,
            detail="No map built yet — run: uv run python scripts/build_map.py",
        )
    from fastapi.responses import FileResponse

    return FileResponse(map_path, media_type="application/json")


@app.get("/docs/settings", response_class=HTMLResponse)
async def settings_docs():
    md = (_STATIC_DIR / "docs-settings.md").read_text(encoding="utf-8")
    # served as readable plain text in the hub theme; no markdown pipeline
    body = md.replace("&", "&amp;").replace("<", "&lt;")
    return HTMLResponse(
        '<!doctype html><html><head><meta charset="utf-8"><title>ytk settings docs</title>'
        '<link rel="stylesheet" href="/static/theme.css">'
        '<link rel="icon" href="/favicon.svg">'
        "<style>body{margin:0} header{display:flex;gap:1rem;padding:.8rem 1rem} "
        "header a{color:#e2b04a;text-decoration:none} "
        "pre{max-width:820px;margin:1.2rem auto;padding:0 1rem;white-space:pre-wrap;"
        "font-family:var(--serif);font-size:15px;line-height:1.55;letter-spacing:0}</style>"
        '</head><body><header><a href="/settings">&larr; settings</a></header>'
        f"<pre>{body}</pre></body></html>"
    )


# ---------------------------------------------------------------------------
# React SPA (web/dist), served at the root
# ---------------------------------------------------------------------------

# When installed, the built SPA is bundled inside the package at ytk/ui/webdist
# (via the force-include in pyproject.toml). When running from a source checkout,
# it lives at the repo's web/dist. Prefer the bundled copy, fall back to source.
_PKG_DIST = Path(__file__).parent / "webdist"
_SRC_DIST = Path(__file__).resolve().parents[2] / "web" / "dist"
_WEB_DIST = _PKG_DIST if (_PKG_DIST / "index.html").exists() else _SRC_DIST

if (_WEB_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=_WEB_DIST / "assets"), name="app-assets")


@app.get("/app", response_class=HTMLResponse, include_in_schema=False)
@app.get("/app/{path:path}", response_class=HTMLResponse, include_in_schema=False)
def _spa_redirect(path: str = ""):
    # pre-cutover bookmarks: the SPA used to live under /app
    from fastapi.responses import RedirectResponse

    return RedirectResponse(f"/{path}", status_code=308)


# The SPA's client-side routes. Serving index.html only for these (rather
# than a blanket fallback) keeps real 404s for junk paths and traversal noise.
_SPA_ROUTES = {
    "",
    "library",
    "inbox",
    "tags",
    "map",
    "grove",
    "growth",
    "profile",
    "settings",
    "channels",
    "recs",
}


# Registered last on purpose: FastAPI matches routes in registration order,
# so every API route, mount, and page above wins first.
@app.get("/", response_class=HTMLResponse)
@app.get("/{path:path}", response_class=HTMLResponse)
def _spa(path: str = "") -> HTMLResponse:
    if path.rstrip("/") not in _SPA_ROUTES:
        raise HTTPException(status_code=404)
    index = _WEB_DIST / "index.html"
    if not index.exists():
        return HTMLResponse("<h1>SPA not built - run: cd web && vp build</h1>", status_code=404)
    return HTMLResponse(index.read_text(encoding="utf-8"))
