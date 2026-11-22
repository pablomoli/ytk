"""Fetch YouTube's sprite grids for every YouTube save in the visual index.

Sprites only: one metadata call per video, then the grid JPEGs. No captions,
no video. Resumable; writes ~/.ytk/sprites/<video_id>/{NNN.jpg,grid.json}.

    uv run python scripts/sprite_sweep.py [--limit N]
"""

from __future__ import annotations

import argparse
import json
import math
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ytk import fetch, store

OUT = Path.home() / ".ytk" / "sprites"
# One video at a time with a pause: a bulk sweep has had captions rate-limited before.
PAUSE_S = 0.4


def sweep_one(video_id: str) -> str:
    d = OUT / video_id
    if (d / "grid.json").exists():
        return "kept"
    with fetch._ydl({"skip_download": True}) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
    sb = fetch._storyboard_format(info)
    if sb is None:
        return "no sprites offered"
    frags = sb["fragments"]
    rows, cols = int(sb.get("rows") or 1), int(sb.get("columns") or 1)
    d.mkdir(parents=True, exist_ok=True)

    def download(item: tuple[int, dict]) -> None:
        i, frag = item
        (d / f"{i:03d}.jpg").write_bytes(fetch._get(str(frag["url"])))

    with ThreadPoolExecutor(16) as pool:
        list(pool.map(download, enumerate(frags)))
    interval = float(frags[0].get("duration") or 0) / (rows * cols)
    duration = float(info.get("duration") or 0)
    if interval <= 0 or duration <= 0:
        return "no timing"
    tiles = min(len(frags) * rows * cols, math.ceil(duration / interval))
    grid = {"rows": rows, "cols": cols, "interval": interval, "tiles": tiles, "duration": duration}
    (d / "grid.json").write_text(json.dumps(grid))
    return f"{tiles} tiles, one per {interval:.1f} s"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "DONE").unlink(missing_ok=True)
    ids = sorted(i[3:] for i in store._visual_collection().get(include=[])["ids"] if i[:3] == "yt:")
    if args.limit:
        ids = ids[: args.limit]
    failed: dict[str, str] = {}
    t0 = time.monotonic()
    for n, vid in enumerate(ids, 1):
        try:
            result = sweep_one(vid)
        except Exception as exc:
            result = f"FAILED {type(exc).__name__}: {str(exc)[:90]}"
        if result.startswith(("FAILED", "no ")):
            failed[vid] = result
        print(f"[{n}/{len(ids)}] {vid}  {result}  ({time.monotonic() - t0:.0f} s)", flush=True)
        if result != "kept":
            time.sleep(PAUSE_S)
    (OUT / "failed.json").write_text(json.dumps(failed, indent=1))
    (OUT / "DONE").write_text(f"{len(ids) - len(failed)} of {len(ids)}\n")
    print(f"DONE {len(ids) - len(failed)} of {len(ids)} with sprites, {len(failed)} without")


if __name__ == "__main__":
    main()
