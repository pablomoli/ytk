#!/usr/bin/env python
"""Do Claude's key_moments land where people actually rewatch? (#144)

YouTube returns a `heatmap` in the yt-dlp info dict: 100 uniform bins over the
video, each with a normalized replay intensity. ytk fetches it on every ingest
and throws it away. It is a free, crowd-sourced attention signal, and it is
directly comparable against the `## Key Moments` timestamps we pay Claude to
generate — which turns "are our timestamps any good" from a vibe into a
measurement.

Three phases, each writing its output so the next can be rerun without refetching:

    harvest  -> raw.json      one record per video: heatmap, key moments, chapters
    analyze  -> results.json  scores vs a uniform-random null
    plot     -> *.png         the figures

The null model matters more than the score. "Key moments average 0.42 replay
intensity" means nothing on its own; what means something is 0.42 against a
null of 0.31 drawn from the same videos, and whether that gap survives the
per-video variance. Chapters (author-placed, where present) act as a human
reference point on the same axis.
"""

from __future__ import annotations

import json
import random
import re
import statistics
import sys
from pathlib import Path
from typing import Any

ASSETS = Path(__file__).resolve().parent.parent / "docs" / "assets" / "09-heatmap-key-moments"
RAW = ASSETS / "raw.json"
RESULTS = ASSETS / "results.json"

# The null is drawn, not derived, so it needs a seed to stay reproducible.
SEED = 20260728
DRAWS_PER_VIDEO = 200


def _ts_to_seconds(ts: str) -> int | None:
    """'1:23:45' or '12:34' -> seconds. Returns None for junk."""
    parts = ts.strip().split(":")
    if not all(p.isdigit() for p in parts) or not 1 <= len(parts) <= 3:
        return None
    total = 0
    for p in parts:
        total = total * 60 + int(p)
    return total


def parse_note(path: Path) -> dict[str, Any] | None:
    """Pull video id and key-moment offsets out of an ingested note."""
    text = path.read_text(encoding="utf-8", errors="ignore")
    url = re.search(r"^url:\s*(\S+)", text, re.MULTILINE)
    if not url:
        return None
    vid = re.search(r"(?:v=|youtu\.be/)([\w-]{11})", url.group(1))
    if not vid:
        return None
    section = re.search(r"^## Key Moments\n(.*?)(?=\n## |\Z)", text, re.MULTILINE | re.DOTALL)
    moments: list[int] = []
    if section:
        for ts in re.findall(r"^-\s+\*\*([\d:]+)\*\*", section.group(1), re.MULTILINE):
            secs = _ts_to_seconds(ts)
            if secs is not None:
                moments.append(secs)
    if not moments:
        return None
    title = re.search(r"^title:\s*(.+)$", text, re.MULTILINE)
    return {
        "video_id": vid.group(1),
        "title": (title.group(1).strip() if title else path.stem)[:90],
        "note": path.name,
        "key_moments": sorted(set(moments)),
    }


def harvest(limit: int | None = None) -> None:
    """Fetch heatmaps for every ingested video that has key moments.

    Newest note first: an interrupted sweep then costs the stale half, not the
    fresh half.
    """
    import yt_dlp

    from ytk.vault import _get_brain_path

    ASSETS.mkdir(parents=True, exist_ok=True)
    notes = sorted(
        (_get_brain_path() / "sources" / "youtube").glob("*.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    todo = [rec for rec in (parse_note(p) for p in notes) if rec]
    if limit:
        todo = todo[:limit]

    done: dict[str, Any] = {}
    if RAW.exists():
        done = {r["video_id"]: r for r in json.loads(RAW.read_text())["videos"]}

    opts = {"quiet": True, "skip_download": True, "no_warnings": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        for i, rec in enumerate(todo, 1):
            vid = rec["video_id"]
            if vid in done:
                continue
            try:
                info = ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
            except Exception as exc:  # private, deleted, region-locked
                print(f"[{i}/{len(todo)}] {vid} FETCH-FAIL {type(exc).__name__}", flush=True)
                done[vid] = {**rec, "heatmap": None, "error": type(exc).__name__}
                continue
            heat = info.get("heatmap")
            done[vid] = {
                **rec,
                "duration": info.get("duration"),
                "view_count": info.get("view_count"),
                # bins are uniform, so the values alone reconstruct the curve
                "heatmap": [round(p["value"], 5) for p in heat] if heat else None,
                "chapters": [int(c["start_time"]) for c in (info.get("chapters") or [])],
            }
            state = "ok " if heat else "NO-HEATMAP"
            print(f"[{i}/{len(todo)}] {vid} {state} {rec['title'][:52]}", flush=True)
            if i % 10 == 0:
                _write_raw(done)
    _write_raw(done)
    have = sum(1 for r in done.values() if r.get("heatmap"))
    print(f"\nharvested {len(done)} videos, {have} with a heatmap -> {RAW}")


def _write_raw(done: dict[str, Any]) -> None:
    RAW.write_text(json.dumps({"videos": list(done.values())}, separators=(",", ":")))


def _intensity_at(heat: list[float], duration: int, t: float) -> float | None:
    """Replay intensity at offset t. Bins are uniform across the duration."""
    if not duration or t < 0 or t > duration:
        return None
    idx = min(int(t / duration * len(heat)), len(heat) - 1)
    return heat[idx]


def analyze() -> dict[str, Any]:
    """Score key moments against a uniform-random null drawn per video."""
    rng = random.Random(SEED)
    raw = json.loads(RAW.read_text())["videos"]
    usable = [r for r in raw if r.get("heatmap") and r.get("duration") and len(r["heatmap"]) >= 20]

    per_video = []
    for r in usable:
        heat, dur = r["heatmap"], r["duration"]
        km = [_intensity_at(heat, dur, t) for t in r["key_moments"]]
        km = [v for v in km if v is not None]
        if not km:
            continue
        null = [
            _intensity_at(heat, dur, rng.uniform(0, dur)) or 0.0 for _ in range(DRAWS_PER_VIDEO)
        ]
        ch = [_intensity_at(heat, dur, t) for t in r.get("chapters") or []]
        ch = [v for v in ch if v is not None]
        per_video.append(
            {
                "video_id": r["video_id"],
                "title": r["title"],
                "duration": dur,
                "n_moments": len(km),
                "km_mean": statistics.fmean(km),
                "null_mean": statistics.fmean(null),
                "chapter_mean": statistics.fmean(ch) if ch else None,
                "peak": max(heat),
                "km_values": [round(v, 5) for v in km],
            }
        )

    lifts = [v["km_mean"] - v["null_mean"] for v in per_video]
    wins = sum(1 for x in lifts if x > 0)
    with_ch = [v for v in per_video if v["chapter_mean"] is not None]

    # Pooled draws for the distribution panel. Sampled rather than exhaustive so
    # results.json stays a readable sidecar rather than a data dump.
    pooled_km = [v for r in per_video for v in r["km_values"]]
    pooled_null: list[float] = []
    for r in usable:
        heat, dur = r["heatmap"], r["duration"]
        pooled_null.extend(
            round(_intensity_at(heat, dur, rng.uniform(0, dur)) or 0.0, 5) for _ in range(20)
        )

    results = {
        "seed": SEED,
        "draws_per_video": DRAWS_PER_VIDEO,
        "videos_harvested": len(raw),
        "videos_with_heatmap": len(usable),
        "videos_scored": len(per_video),
        "key_moments_scored": sum(v["n_moments"] for v in per_video),
        "km_mean": statistics.fmean(v["km_mean"] for v in per_video),
        "null_mean": statistics.fmean(v["null_mean"] for v in per_video),
        "chapter_mean": (statistics.fmean(v["chapter_mean"] for v in with_ch) if with_ch else None),
        "videos_with_chapters": len(with_ch),
        "mean_lift": statistics.fmean(lifts),
        "median_lift": statistics.median(lifts),
        "lift_stdev": statistics.stdev(lifts) if len(lifts) > 1 else 0.0,
        "win_rate": wins / len(per_video) if per_video else 0.0,
        "pooled": {"key_moments": pooled_km, "null": pooled_null},
        "per_video": per_video,
    }
    RESULTS.write_text(json.dumps(results, indent=1))
    print(
        f"scored {results['videos_scored']} videos / {results['key_moments_scored']} moments\n"
        f"  key moments {results['km_mean']:.4f}  null {results['null_mean']:.4f}  "
        f"lift {results['mean_lift']:+.4f}  win rate {results['win_rate']:.1%}"
    )
    return results


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "harvest"
    if cmd == "harvest":
        harvest(limit=int(sys.argv[2]) if len(sys.argv) > 2 else None)
    elif cmd == "analyze":
        analyze()
    else:
        raise SystemExit(f"unknown phase: {cmd}")
