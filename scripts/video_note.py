"""A note about a whole video, composed from the notes on its moments.

A frame cannot show how a video is made. This step describes each distinct
look of a video with the Kind First prompt (one frame per call), then asks
for one note about the video from those moment notes, with three levels of
evidence so the gain from each can be seen:

  notes      the moment notes, the stored summary, the title
  structure  + how the video is cut: looks, shares, cuts per minute, the order looks appear in
  frames     + the frames themselves, untouched

    uv run python scripts/video_note.py moments    # Kind First on every look not yet described
    uv run python scripts/video_note.py compose    # 3 arms x videos
"""

from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import describer_ab as ab

D = Path.home() / ".ytk" / "describer"
OUT = D / "video"
SPRITES = Path.home() / ".ytk" / "sprites"
VIDEOS = ["LQoFN1K1dZ8", "urKKrMlhgwI", "vSczTbgc8Rc", "VcvhiDV_t3c", "ztkh1r1ioZo", "0iEfNt5vYWQ"]
ARMS = ["notes", "structure", "frames"]
MODEL = "claude-sonnet-5"

SYSTEM = """You write one note about a whole YouTube video that one person saved, for his personal memory and taste library. You are given notes already written about its distinct moments, and other evidence listed below. He saves most videos for the content. Some he saves for content and for how they look. A few he saves because content, execution and looks are all right at once. Your job is to say which this video is, from the evidence, and to write only what earns its place.

Rules:
- Use only the evidence given. If frame files are listed, open each with the Read tool before answering. Never state what the evidence does not support; put what you could not ground in "unsure".
- "what": two or three sentences on what the video is and argues or teaches. Names only as the evidence gives them.
- "made": how the video is put together, only as far as the evidence shows it: what kinds of moments it is built from, in what proportion, how often it cuts, what it cuts between, what devices it uses (on-screen graphics, film clips, diagrams, screen recordings, a host on camera). This is a description, not a review. Leave it empty when the evidence shows nothing beyond a single unbroken kind of shot.
- "look": the look of the video as a whole, only if it has one that is not just the ordinary look of its kind. A person talking to a camera, a sports broadcast, a software window and a plain slide are ordinary. Leave it empty then. Never describe venue or studio lighting.
- "lineage": where that look comes from (a tool, a style, an era, a maker), only when you can point to what shows it. Otherwise empty.
- "vibe": how it feels to watch, only if the evidence carries it. Otherwise empty.
- "weight": 0 to 3 each for content, execution, look and vibe: how much each is a reason to keep this video. Execution is 0 unless "made" shows deliberate construction beyond one kind of shot.
- "come_back_for": any of info, look, feel, cool, nothing.
- "strongest_moments": the letters of the moments most worth returning to, at most three.
- Plain language, American spelling, no praise words."""

SCHEMA = {
    "type": "object",
    "properties": {
        "what": {"type": "string"},
        "made": {"type": "string"},
        "look": {"type": "string"},
        "lineage": {"type": "string"},
        "vibe": {"type": "string"},
        "weight": {
            "type": "object",
            "properties": {
                k: {"type": "integer", "minimum": 0, "maximum": 3}
                for k in ("content", "execution", "look", "vibe")
            },
            "required": ["content", "execution", "look", "vibe"],
        },
        "come_back_for": {
            "type": "array",
            "items": {"type": "string", "enum": ["info", "look", "feel", "cool", "nothing"]},
        },
        "strongest_moments": {"type": "array", "items": {"type": "string"}},
        "unsure": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "what",
        "made",
        "look",
        "lineage",
        "vibe",
        "weight",
        "come_back_for",
        "strongest_moments",
        "unsure",
    ],
}


def looks_of(vid: str) -> list[dict]:
    """The looks of a video that have a real frame on disk, largest first."""
    mo = np.load(SPRITES / "moments.npz")
    rows = np.where(mo["look_video"] == vid)[0]
    out = []
    for k, r in enumerate(rows[:9]):
        path = D / "frames" / vid / f"{chr(65 + k)}.jpg"
        if path.exists():
            out.append(
                {
                    "id": f"{vid}_{chr(65 + k)}",
                    "letter": chr(65 + k),
                    "path": path,
                    "share": float(mo["look_share"][r]),
                    "look": int(mo["look_id"][r]),
                }
            )
    return out


def structure(vid: str) -> str:
    mo = np.load(SPRITES / "moments.npz")
    m = mo["moment_video"] == vid
    start, end, look = mo["moment_start"][m], mo["moment_end"][m], mo["moment_look"][m]
    dur = float(end.max())
    shares = np.sort(mo["look_share"][mo["look_video"] == vid])[::-1]
    order = "".join(chr(65 + int(x)) if x < 9 else "." for x in look[:90])
    lengths = end - start
    return (
        f"length {dur / 60:.1f} min; {len(shares)} distinct looks; {m.sum()} moments; {(m.sum() - 1) / (dur / 60):.1f} changes of look per minute; "
        f"median moment {np.median(lengths):.0f} s, longest {lengths.max():.0f} s; the largest look fills {shares[0]:.0%}, the top three together {shares[:3].sum():.0%}; "
        f"{(shares < 0.01).sum()} looks each fill under 1%.\n"
        f"ORDER OF LOOKS over the first {min(len(look), 90)} moments (letters match the moment notes, a dot is any smaller look): {order}"
    )


def moment_packets() -> list[dict]:
    from ytk import store

    frames = {
        json.loads(x.rstrip(",\n"))["id"]: json.loads(x.rstrip(",\n"))
        for x in (D / "review" / "frames.json").read_text().splitlines()
        if x.startswith("{")
    }
    extra = {x["id"]: x for x in json.loads((ab.AB / "extras.json").read_text())}
    g = store._videos_collection().get(ids=VIDEOS, include=["metadatas"])
    meta = dict(zip(g["ids"], g["metadatas"], strict=True))
    out = []
    for vid in VIDEOS:
        for lk in looks_of(vid):
            f = frames.get(lk["id"]) or extra.get(lk["id"])
            if f is None:
                continue
            user = (
                f"FRAME FILE: {lk['path']}\n"
                f"VIDEO: {meta[vid].get('title', '')} | CHANNEL: {meta[vid].get('uploader', '')}\n"
                f"THIS LOOK FILLS: {lk['share']:.0%} of the video's running time\n"
                f"SAID BEFORE: {f.get('said_before', '')}\nSAID AT THIS MOMENT: {f.get('said', '')}\nSAID AFTER: {f.get('said_after', '')}\n"
                f"MEASURED FROM PIXELS: {ab.measured(lk['path'])}\nTerm facets: {ab.FACETS}."
            )
            out.append(lk | {"video": vid, "user": user})
    return out


def moments() -> None:
    from ytk import sdk

    kind_first = next(
        v for v in json.loads((ab.AB / "variants.json").read_text()) if v["key"] == "kind-first"
    )
    jobs = [p for p in moment_packets() if not (ab.AB / "kind-first" / f"{p['id']}.json").exists()]
    t0, n = time.monotonic(), [0]

    def one(p: dict) -> None:
        try:
            res = sdk.call_structured(
                kind_first["system_prompt"],
                p["user"],
                ab.SCHEMA,
                add_dirs=[p["path"].parent],
                model=MODEL,
            )
            (ab.AB / "kind-first" / f"{p['id']}.json").write_text(json.dumps(res.data, indent=1))
            note = res.data["kind"]
        except Exception as exc:
            note = f"FAILED {str(exc)[:90]}"
        n[0] += 1
        print(
            f"[moment {n[0]}/{len(jobs)}] {p['id']}  {note}  ({time.monotonic() - t0:.0f} s)",
            flush=True,
        )

    with ThreadPoolExecutor(4) as pool:
        list(pool.map(one, jobs))
    print("moments done")


def compose() -> None:
    from ytk import sdk, store

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "DONE").unlink(missing_ok=True)
    g = store._videos_collection().get(ids=VIDEOS, include=["metadatas"])
    meta = dict(zip(g["ids"], g["metadatas"], strict=True))
    jobs = []
    for vid in VIDEOS:
        lks = [lk for lk in looks_of(vid) if (ab.AB / "kind-first" / f"{lk['id']}.json").exists()]
        notes = []
        for lk in lks:
            d = json.loads((ab.AB / "kind-first" / f"{lk['id']}.json").read_text())
            notes.append(
                f"MOMENT {lk['letter']} (this look fills {lk['share']:.0%}) kind: {d['kind']}\n  content: {d['content']}\n"
                + (
                    f"  look: {d['look']}\n  lineage: {d['lineage']}\n"
                    if d["look"]
                    else "  look: (left empty: ordinary for its kind)\n"
                )
                + (f"  vibe: {d['vibe']}\n" if d["vibe"] else "")
            )
        base = (
            f"VIDEO: {meta[vid].get('title', '')} | CHANNEL: {meta[vid].get('uploader', '')}\n"
            f"STORED SUMMARY (written earlier from the transcript): {meta[vid].get('thesis', '')} {meta[vid].get('summary', '')}\n\n"
            f"NOTES ON ITS MOMENTS, largest look first:\n" + "\n".join(notes)
        )
        cut = "\n\nHOW IT IS CUT (measured from a frame every few seconds): " + structure(vid)
        files = "\n\nFRAME FILES, one per moment, in the same order: " + ", ".join(
            str(lk["path"]) for lk in lks
        )
        for arm, user in (
            ("notes", base),
            ("structure", base + cut),
            ("frames", base + cut + files),
        ):
            if not (OUT / arm / f"{vid}.json").exists():
                jobs.append((arm, vid, user, [D / "frames" / vid] if arm == "frames" else None))
    t0, n = time.monotonic(), [0]

    def one(job: tuple) -> None:
        arm, vid, user, dirs = job
        (OUT / arm).mkdir(exist_ok=True)
        try:
            res = sdk.call_structured(SYSTEM, user, SCHEMA, add_dirs=dirs, model=MODEL)
            (OUT / arm / f"{vid}.json").write_text(
                json.dumps(res.data | {"prompt_chars": len(user)}, indent=1)
            )
            note = str(res.data["weight"])
        except Exception as exc:
            note = f"FAILED {str(exc)[:90]}"
        n[0] += 1
        print(
            f"[compose {n[0]}/{len(jobs)}] {arm:9s} {vid}  {note}  ({time.monotonic() - t0:.0f} s)",
            flush=True,
        )

    with ThreadPoolExecutor(3) as pool:
        list(pool.map(one, jobs))
    (OUT / "DONE").write_text("ok\n")
    print("DONE")


if __name__ == "__main__":
    {"moments": moments, "compose": compose}[sys.argv[1]]()
