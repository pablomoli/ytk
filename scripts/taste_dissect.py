"""Cut the taste test set into frames at native resolution.

Video: cuts from the picture (scene change above 0.30 on a small decode), then one
frame from the middle of each of the longest shots, saved at the file's own size.
Carousel: every slide as it was served. Writes ~/.ytk/taste-test/frames and frames.json.

    uv run python scripts/taste_dissect.py frames
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

T = Path.home() / ".ytk" / "taste-test"
SCENE, PER_VIDEO = 0.30, 12


def probe(path: str) -> tuple[int, int, float]:
    out = (
        subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height,duration",
                "-of",
                "csv=p=0",
                path,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        .stdout.strip()
        .strip(",")
        .split(",")
    )
    return (
        int(out[0]),
        int(out[1]),
        float(out[2]) if len(out) > 2 and out[2] not in ("", "N/A") else 0.0,
    )


def cuts(path: str) -> list[float]:
    log = subprocess.run(
        [
            "ffmpeg",
            "-hwaccel",
            "videotoolbox",
            "-i",
            path,
            "-vf",
            f"scale=320:-2,select='gt(scene,{SCENE})',showinfo",
            "-an",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=False,
    ).stderr
    return [float(x) for x in re.findall(r"pts_time:([0-9.]+)", log)]


def frames() -> None:
    manifest = json.loads((T / "manifest.json").read_text())
    sample = {x["url"]: x for x in json.loads((T / "sample.json").read_text())}
    out_path = T / "frames.json"
    done = json.loads(out_path.read_text()) if out_path.exists() else {}
    (T / "FRAMES_DONE").unlink(missing_ok=True)
    t0 = time.monotonic()
    for n, (url, row) in enumerate(manifest.items(), 1):
        key = f"{row['kind']}-{n:02d}"
        if key in done:
            continue
        d = T / "frames" / key
        d.mkdir(parents=True, exist_ok=True)
        item = {"kind": row["kind"], "url": url, "title": sample[url]["title"], "frames": []}
        if row.get("video"):
            w, h, dur = probe(row["video"])
            c = cuts(row["video"])
            edges = np.array([0.0, *c, dur])
            lengths = np.diff(edges)
            # The longest shots, in time order; a video with no cuts is sampled evenly.
            if len(c) >= 2:
                pick = np.sort(np.argsort(-lengths)[:PER_VIDEO])
                times = [float(edges[i] + lengths[i] / 2) for i in pick]
            else:
                times = [dur * (i + 0.5) / 6 for i in range(6)]
            for k, t in enumerate(times):
                p = d / f"{k:02d}.jpg"
                if not p.exists():
                    subprocess.run(
                        [
                            "ffmpeg",
                            "-y",
                            "-loglevel",
                            "error",
                            "-ss",
                            f"{t:.2f}",
                            "-i",
                            row["video"],
                            "-frames:v",
                            "1",
                            "-q:v",
                            "2",
                            str(p),
                        ],
                        check=False,
                    )
                if p.exists():
                    item["frames"].append({"path": str(p), "t": round(t, 2)})
            item |= {"width": w, "height": h, "seconds": dur, "cuts": c}
        else:
            for k, s in enumerate(row.get("slides") or []):
                if s.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                    item["frames"].append({"path": s, "t": k})
            item |= {"slides": len(item["frames"])}
        done[key] = item
        out_path.write_text(json.dumps(done, indent=1))
        print(
            f"[{n}/{len(manifest)}] {key}  {len(item['frames'])} frames, {len(item.get('cuts', []))} cuts  ({time.monotonic() - t0:.0f} s)",
            flush=True,
        )
    (T / "FRAMES_DONE").write_text(f"{sum(len(i['frames']) for i in done.values())}\n")
    print("DONE", sum(len(i["frames"]) for i in done.values()), "frames")


if __name__ == "__main__":
    {"frames": frames}[sys.argv[1]]()
