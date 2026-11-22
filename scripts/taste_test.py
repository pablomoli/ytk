"""The taste test set: 10 YouTube videos, 20 reels, 10 carousels, 10 TikToks, on disk at native resolution.

The sample is drawn from the owner's saves and kept in ~/.ytk/taste-test/sample.json
(titles and URLs stay outside the repo). Instagram and TikTok go through the fetch
layer, which reuses the browser's cookie session; YouTube is downloaded whole.

    uv run python scripts/taste_test.py download
"""

from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

T = Path.home() / ".ytk" / "taste-test"
# One Instagram request at a time with a human-sized gap; the cookie session is one login.
IG_GAP_S = (12, 22)


def download() -> None:
    from ytk import fetch

    sample = json.loads((T / "sample.json").read_text())
    manifest = (
        json.loads((T / "manifest.json").read_text()) if (T / "manifest.json").exists() else {}
    )
    (T / "DONE").unlink(missing_ok=True)
    rng, t0, misses = random.Random(5), time.monotonic(), 0
    for n, x in enumerate(sample, 1):
        url = x["url"]
        if manifest.get(url, {}).get("ok"):
            continue
        row: dict = {"kind": x["kind"], "ok": False}
        try:
            if x["kind"] == "youtube":
                vid = url.split("v=")[1]
                out = T / "youtube"
                out.mkdir(parents=True, exist_ok=True)
                opts = {
                    "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best",
                    "merge_output_format": "mp4",
                    "outtmpl": str(out / f"{vid}.%(ext)s"),
                }
                with fetch._ydl(opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                row |= {
                    "ok": True,
                    "video": str(out / f"{vid}.mp4"),
                    "height": info.get("height"),
                    "seconds": info.get("duration"),
                }
            else:
                f = fetch.fetch(url, whisper=False)
                video = f.meta.get("video")
                slides = (
                    sorted(str(p) for p in (f.dir / "slides").glob("*"))
                    if (f.dir / "slides").exists()
                    else []
                )
                row |= {
                    "ok": bool(video or slides),
                    "video": video,
                    "slides": slides,
                    "dir": str(f.dir),
                    "gaps": list(f.bundle.gaps or []),
                }
                if x["kind"] in ("reel", "carousel"):
                    time.sleep(rng.uniform(*IG_GAP_S))
        except Exception as exc:
            row["error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
        misses = 0 if row["ok"] else misses + 1
        manifest[url] = row
        (T / "manifest.json").write_text(json.dumps(manifest, indent=1))
        what = row.get("error") or (
            f"{len(row.get('slides') or [])} slides" if row.get("slides") else "video"
        )
        print(
            f"[{n}/{len(sample)}] {x['kind']:8s} {'ok ' if row['ok'] else 'MISS'} {what[:90]}  ({time.monotonic() - t0:.0f} s)",
            flush=True,
        )
        # Two Instagram misses in a row is the signal to stop, not to pace around.
        if misses >= 2 and x["kind"] in ("reel", "carousel"):
            print("STOPPED: two misses in a row on Instagram")
            return
    ok = sum(r["ok"] for r in manifest.values())
    (T / "DONE").write_text(f"{ok} of {len(sample)}\n")
    print(f"DONE {ok} of {len(sample)}")


if __name__ == "__main__":
    {"download": download}[sys.argv[1]]()
