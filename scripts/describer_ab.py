"""A/B/C test of describer system prompts on the same frames, one frame per call.

Each call sees only that moment's evidence: the real frame, the caption lines
around it, the title and channel, how much of the video the look fills, and
colors measured from the pixels. Never another frame's description.
Variants come from ~/.ytk/describer/ab/variants.json. Resumable.

    uv run python scripts/describer_ab.py extras      # frames for one more video and eight reels, no model
    uv run python scripts/describer_ab.py packets     # build the evidence, no model
    uv run python scripts/describer_ab.py run         # variants x frames model calls
"""

from __future__ import annotations

import colorsys
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

D = Path.home() / ".ytk" / "describer"
AB = D / "ab"
MODEL = "claude-sonnet-5"
WORKERS = 4
FACETS = "subject, technique, medium, palette, light, texture, composition, style, mood"

SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string"},
        "content": {"type": "string"},
        "named": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "role": {"type": "string"},
                    "source": {
                        "type": "string",
                        "enum": ["on screen", "transcript", "title", "channel"],
                    },
                },
                "required": ["name", "role", "source"],
            },
        },
        "look": {"type": "string"},
        "lineage": {"type": "string"},
        "vibe": {"type": "string"},
        "weight": {
            "type": "object",
            "properties": {
                k: {"type": "integer", "minimum": 0, "maximum": 3}
                for k in ("content", "look", "vibe")
            },
            "required": ["content", "look", "vibe"],
        },
        "come_back_for": {
            "type": "array",
            "items": {"type": "string", "enum": ["info", "look", "feel", "cool", "nothing"]},
        },
        "terms": {"type": "array", "items": {"type": "string"}},
        "unsure": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "kind",
        "content",
        "named",
        "look",
        "lineage",
        "vibe",
        "weight",
        "come_back_for",
        "terms",
        "unsure",
    ],
}

# Named color families, checked in order; a pixel belongs to the first that fits.
FAMILIES = [
    ("black", lambda h, s, v: v < 0.12),
    ("white", lambda h, s, v: (s < 0.12) & (v > 0.82)),
    ("gray", lambda h, s, v: s < 0.14),
    ("red", lambda h, s, v: (h < 15) | (h >= 345)),
    ("orange or brown", lambda h, s, v: h < 45),
    ("yellow", lambda h, s, v: h < 70),
    ("green", lambda h, s, v: h < 165),
    ("teal", lambda h, s, v: h < 200),
    ("blue", lambda h, s, v: h < 255),
    ("violet", lambda h, s, v: h < 295),
    ("magenta or pink", lambda h, s, v: h < 345),
]
_hsv = np.vectorize(colorsys.rgb_to_hsv)


def measured(path: Path) -> str:
    with Image.open(path) as im:
        a = np.asarray(im.convert("RGB").resize((192, 108)), float) / 255
    h, s, v = _hsv(a[..., 0], a[..., 1], a[..., 2])
    h = h * 360
    lum = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]
    left = np.ones(h.shape, bool)
    shares = []
    for name, rule in FAMILIES:
        hit = left & rule(h, s, v)
        left &= ~hit
        shares.append((float(hit.mean()), name))
    colors = ", ".join(
        f"{name} {share:.0%}" for share, name in sorted(shares, reverse=True) if share >= 0.04
    )
    return f"brightness {lum.mean():.2f}, contrast {lum.std():.2f}, saturation {s.mean():.2f}; main colors: {colors}"


REELS = [
    "3765199b77fa",
    "70d87a90153f",
    "ca3da3792689",
    "83cde90e77fa",
    "80296c6c3a28",
    "de4c95e9c504",
    "b29310466de3",
    "cd1290a9ddce",
]
EXTRA_VIDEO = "LQoFN1K1dZ8"  # saved, in the owner's words, for content, execution and looks at once


def _said(segs: list[dict], t: float) -> tuple[str, str, str]:
    if not segs:
        return "", "", ""
    i = max([j for j, x in enumerate(segs) if x["start"] <= t] or [0])
    join = lambda xs: " ".join(" ".join(x["text"].split()) for x in xs)
    return join(segs[max(0, i - 2) : i]), join(segs[i : i + 1]), join(segs[i + 1 : i + 4])


def extras() -> None:
    """Frames and caption lines for the extra video and the reels, written beside the pilot's."""
    from ytk import fetch, store

    out = []
    mo = np.load(Path.home() / ".ytk" / "sprites" / "moments.npz")
    vid = EXTRA_VIDEO
    meta = store._videos_collection().get(ids=[vid], include=["metadatas"])["metadatas"][0]
    with fetch._ydl({"skip_download": True}) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
    segs = [{"start": x["start"], "text": x["text"]} for x in fetch._captions(info)[0]]
    interval = json.loads((Path.home() / ".ytk" / "sprites" / vid / "grid.json").read_text())[
        "interval"
    ]
    rows = np.where(mo["look_video"] == vid)[0][:6]
    for k, r in enumerate(rows):
        t = (int(mo["look_rep"][r]) + 0.5) * interval
        path = D / "frames" / vid / f"{chr(65 + k)}.jpg"
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            fetch._youtube_closeup(f"https://www.youtube.com/watch?v={vid}", t, path)
        b, a, n = _said(segs, t)
        out.append(
            {
                "id": f"{vid}_{chr(65 + k)}",
                "video": vid,
                "letter": chr(65 + k),
                "path": str(path),
                "title": meta.get("title", ""),
                "channel": meta.get("uploader", ""),
                "fills": f"{float(mo['look_share'][r]):.0%} of the video's running time",
                "said_before": b,
                "said": a,
                "said_after": n,
                "source": "youtube",
            }
        )
    for key in REELS:
        d = fetch.fetch_dir() / key
        m, b = (
            json.loads((d / "meta.json").read_text()),
            json.loads((d / "bundle.json").read_text()),
        )
        import subprocess

        # The picture can end before the sound does; frames come from the picture's own length.
        probe = (
            subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=duration",
                    "-of",
                    "csv=p=0",
                    m["video"],
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            .stdout.strip()
            .strip(",")
        )
        dur = float(probe or b.get("duration") or 0)
        segs = [
            {"start": float(x.get("start", 0)), "text": x.get("text", "")}
            for x in (b.get("transcript") or [])
        ]
        for k, frac in enumerate((0.3, 0.7)):
            t = dur * frac
            path = D / "frames" / f"ig-{key}" / f"{chr(65 + k)}.jpg"
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                fetch._ffmpeg_frame(m["video"], t, path)
            sb, sa, sn = _said(segs, t)
            caption = " ".join((b.get("caption") or b.get("description") or "").split())[:300]
            out.append(
                {
                    "id": f"ig-{key}_{chr(65 + k)}",
                    "video": f"ig-{key}",
                    "letter": chr(65 + k),
                    "path": str(path),
                    "title": f"(Instagram reel, no title) CAPTION: {caption}",
                    "channel": b.get("uploader") or "",
                    "fills": f"not measured; a {dur:.0f} s reel, this frame is at {t:.0f} s",
                    "said_before": sb,
                    "said": sa,
                    "said_after": sn,
                    "source": "instagram",
                }
            )
    AB.mkdir(parents=True, exist_ok=True)
    (AB / "extras.json").write_text(json.dumps(out, indent=1))
    print(len(out), "extra frames;", sum(bool(x["said"]) for x in out), "with a caption line")


def packets() -> list[dict]:
    from ytk import store

    frames = [
        json.loads(x.rstrip(",\n"))
        for x in (D / "review" / "frames.json").read_text().splitlines()
        if x.startswith("{")
    ]
    judged = {p.stem for p in (D / "review-answers" / "reviews").glob("*.json")}
    seen_videos = {f["video"] for f in frames if f["id"] in judged}
    picked = [f for f in frames if f["id"] in judged]
    picked += [f for f in frames if f["video"] not in seen_videos and f["letter"] == "A"]
    picked += [
        f
        for f in frames
        if f["video"] == "VcvhiDV_t3c" and f["id"] not in judged and f["letter"] in "ABC"
    ]
    mo = np.load(Path.home() / ".ytk" / "sprites" / "moments.npz")
    g = store._videos_collection().get(
        ids=sorted({f["video"] for f in picked}), include=["metadatas"]
    )
    channel = {i: m.get("uploader", "") for i, m in zip(g["ids"], g["metadatas"], strict=True)}
    out = []
    for f in picked:
        rows = np.where(mo["look_video"] == f["video"])[0]
        share = float(mo["look_share"][rows[ord(f["letter"]) - 65]])
        path = D / "frames" / f["video"] / f"{f['letter']}.jpg"
        user = (
            f"FRAME FILE: {path}\n"
            f"VIDEO: {f['title']} | CHANNEL: {channel.get(f['video'], '')}\n"
            f"THIS LOOK FILLS: {share:.0%} of the video's running time\n"
            f"SAID BEFORE: {f.get('said_before', '')}\n"
            f"SAID AT THIS MOMENT: {f.get('said', '')}\n"
            f"SAID AFTER: {f.get('said_after', '')}\n"
            f"MEASURED FROM PIXELS: {measured(path)}\n"
            f"Term facets: {FACETS}."
        )
        out.append(
            {
                "id": f["id"],
                "video": f["video"],
                "letter": f["letter"],
                "path": str(path),
                "user": user,
                "judged": f["id"] in judged,
            }
        )
    extra = json.loads((AB / "extras.json").read_text()) if (AB / "extras.json").exists() else []
    for x in extra:
        user = (
            f"FRAME FILE: {x['path']}\n"
            f"VIDEO: {x['title']} | CHANNEL: {x['channel']}\n"
            f"THIS LOOK FILLS: {x['fills']}\n"
            f"SAID BEFORE: {x['said_before']}\n"
            f"SAID AT THIS MOMENT: {x['said']}\n"
            f"SAID AFTER: {x['said_after']}\n"
            f"MEASURED FROM PIXELS: {measured(Path(x['path']))}\n"
            f"Term facets: {FACETS}."
        )
        out.append(
            {
                "id": x["id"],
                "video": x["video"],
                "letter": x["letter"],
                "path": x["path"],
                "user": user,
                "judged": False,
                "source": x["source"],
            }
        )
    AB.mkdir(parents=True, exist_ok=True)
    (AB / "packets.json").write_text(json.dumps(out, indent=1))
    return out


def run() -> None:
    from ytk import sdk

    pk = json.loads((AB / "packets.json").read_text())
    variants = json.loads((AB / "variants.json").read_text())
    (AB / "DONE").unlink(missing_ok=True)
    jobs = [
        (v, p) for p in pk for v in variants if not (AB / v["key"] / f"{p['id']}.json").exists()
    ]
    total, t0, done = len(jobs), time.monotonic(), [0]

    def one(job: tuple[dict, dict]) -> None:
        v, p = job
        target = AB / v["key"] / f"{p['id']}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            res = sdk.call_structured(
                v["system_prompt"],
                p["user"],
                SCHEMA,
                add_dirs=[Path(p["path"]).parent],
                model=MODEL,
            )
            target.write_text(json.dumps(res.data, indent=1))
            note = f"{len(res.data['look'].split())} look words, {len(res.data['named'])} named"
        except Exception as exc:
            note = f"FAILED {type(exc).__name__}: {str(exc)[:100]}"
        done[0] += 1
        print(
            f"[{done[0]}/{total}] {v['key']:10s} {p['id']:16s} {note}  ({time.monotonic() - t0:.0f} s)",
            flush=True,
        )

    with ThreadPoolExecutor(WORKERS) as pool:
        list(pool.map(one, jobs))
    (AB / "DONE").write_text("ok\n")
    print("DONE")


if __name__ == "__main__":
    {"extras": extras, "packets": lambda: print(len(packets()), "packets"), "run": run}[
        sys.argv[1]
    ]()
