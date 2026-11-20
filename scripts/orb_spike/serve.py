"""Serve the orb spike's hub app on a spare port with no curator loop and the
spike copy of map.json (knn attached). Run from the worktree's venv.

Spike-only routes, all read-only:
  /api/orb-search  query scored against the orb's own tile vectors; writes
                   neither the search log nor the retrieval log
  /api/orb-ring    the baked pending ring (ring_bake.py) and its cover atlas
  /api/orb-pending one pending item's row from the queue snapshot (queue.json),
                   plus the tiles its words sit nearest; reads the snapshot only
  /api/orb-queue   which ring items have left the queue or are with the ingest job

The queue is a sandbox: the hub's own keep (/api/ingest) and drop
(/api/queue/drop) routes run their real code against sandbox/reels_state.json, a
copy of the live file made when the copy is missing. The hand-off to the curator
is a stand-in that waits and writes nothing; a url listed in sandbox/fail.txt
fails there instead. Delete the sandbox folder's files to start over."""

import json
import shutil
import threading
import time
import types
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
import uvicorn
from fastapi.responses import FileResponse

from ytk import reels
from ytk.ui import hub, server

HERE = Path.home() / ".ytk" / "orb-spike"
server._ORB_MAP = HERE / "map.json"
_VECS = np.load(HERE / "orb_vecs.npy")


SANDBOX = HERE / "sandbox"
SANDBOX.mkdir(exist_ok=True)
if not (SANDBOX / "reels_state.json").exists():
    shutil.copy2(reels.STATE_PATH, SANDBOX / "reels_state.json")
hub.STATE_PATH = SANDBOX / "reels_state.json"
hub.JOB_PATH = SANDBOX / "ingest-job.json"
HAND_S = 6.0  # how long the stand-in takes to hand an item on


def _hand_on(item_or_url, note=""):
    url = getattr(item_or_url, "url", item_or_url)
    time.sleep(HAND_S)
    fail = SANDBOX / "fail.txt"
    if fail.exists() and url in fail.read_text().split():
        raise RuntimeError("the stand-in was told to fail this one")


hub.INGEST = hub.INGEST_TEXT = _hand_on
# the drain's other writes: the capture log, and a stored reflection answer's trip into the vault
hub.capture_log = types.SimpleNamespace(log_capture=lambda *a, **k: None)
hub.reflection_answers = dict
hub.store_reflection_answer = lambda *a, **k: None


@asynccontextmanager
async def _noop(app):
    yield


def orb_search(q: str, n: int = 12, check: int = 0):
    from ytk.store import _embed_query

    q = q.strip()
    if not q:
        return {"hits": []}
    v = np.asarray(_embed_query(q), dtype=np.float32)
    v /= np.linalg.norm(v) + 1e-12
    sim = _VECS @ v
    order = np.argsort(-sim)[:n]
    out = {"hits": [{"i": int(i), "s": round(float(sim[i]), 4)} for i in order]}
    if check:
        # production candidate order, read straight off the collection so nothing is logged
        from ytk.store import _collapse_by_video, _videos_collection, chroma_field

        col = _videos_collection()
        res = col.query(query_embeddings=[v.tolist()], n_results=min(n * 3, col.count()))
        collapsed = _collapse_by_video(
            chroma_field(res["metadatas"], "metadatas")[0],
            chroma_field(res["distances"], "distances")[0],
        )
        out["production"] = [
            {"title": m.get("title", ""), "url": m.get("url", ""), "distance": round(float(d), 4)}
            for m, d in collapsed[:n]
        ]
    return out


def orb_ring():
    return FileResponse(HERE / "ring.json", media_type="application/json")


def orb_ring_atlas():
    return FileResponse(HERE / "ring.jpg", media_type="image/jpeg")


_QUEUE = {r["url"]: r for r in json.loads((HERE / "queue.json").read_text())["items"]}


def orb_pending(u: str, n: int = 6):
    from ytk.store import _embed_query

    r = _QUEUE.get(u)
    if r is None:
        return {"row": None, "hits": []}
    row = {
        "title": r.get("title") or "",
        "text": r.get("text") or "",
        "author": r.get("author") or "",
        "source": r.get("source") or "",
        "shared_at": r.get("shared_at") or "",
        "question": (r.get("reflection_question") or "")
        if not r.get("reflection_answered")
        else "",
    }
    words = " ".join(x for x in (row["title"], row["text"]) if x).strip()[:1000]
    if not words:
        return {"row": row, "hits": []}
    v = np.asarray(_embed_query(words), dtype=np.float32)
    v /= np.linalg.norm(v) + 1e-12
    sim = _VECS @ v
    order = np.argsort(-sim)[:n]
    return {"row": row, "hits": [{"i": int(i), "s": round(float(sim[i]), 4)} for i in order]}


_RING = [r["u"] for r in json.loads((HERE / "ring.json").read_text())["items"]]


def orb_queue():
    pending = {i.url for i in hub.queue_items()}
    job = hub.job_status()
    held = set(job["queued"]) | {job["current"]}
    return {
        "sandbox": True,
        "gone": [k for k, u in enumerate(_RING) if u not in pending],
        "waiting": [k for k, u in enumerate(_RING) if u in held],
    }


server.app.add_api_route("/api/orb-queue", orb_queue, methods=["GET"])
server.app.add_api_route("/api/orb-pending", orb_pending, methods=["GET"])
server.app.add_api_route("/api/orb-search", orb_search, methods=["GET"])
server.app.add_api_route("/api/orb-ring", orb_ring, methods=["GET"])
server.app.add_api_route("/api/orb-ring.jpg", orb_ring_atlas, methods=["GET"])
# ahead of the app's own routes, so the SPA catch-all cannot shadow them
routes = server.app.router.routes
for _ in range(5):
    routes.insert(0, routes.pop())


def _warm():
    from ytk.store import warm_text_encoder

    warm_text_encoder()


threading.Thread(target=_warm, daemon=True).start()
server.app.router.lifespan_context = _noop
uvicorn.run(server.app, host="127.0.0.1", port=8877, log_level="warning")
