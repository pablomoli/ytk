"""Section 67: where a video cuts, set against where its sentences end.

Cuts come from the picture itself (ffmpeg scene change on a 360p copy), words
from YouTube's speech-recognition track with a time per word. No model calls.

    uv run python scripts/edit_rhythm.py fetch
    uv run --with matplotlib python scripts/edit_rhythm.py plot
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

R = Path.home() / ".ytk" / "describer" / "rhythm"
OUT = Path(__file__).resolve().parents[1] / "docs" / "assets" / "67-edit-rhythm"
VIDEOS = [
    ("LQoFN1K1dZ8", "film essay (kept for its editing rhythm and writing)"),
    ("ztkh1r1ioZo", "voxel rendering explainer"),
    ("vSczTbgc8Rc", "math animation"),
]
SCENE = 0.30  # ffmpeg's scene-change score above which a frame counts as a cut
NULLS = 500


def fetch() -> None:
    from ytk import fetch as f

    R.mkdir(parents=True, exist_ok=True)
    for vid, _ in VIDEOS:
        target = R / f"{vid}.json"
        if target.exists():
            continue
        url = f"https://www.youtube.com/watch?v={vid}"
        opts = {
            "format": "bestvideo[height<=360][ext=mp4]/bestvideo[height<=360]",
            "outtmpl": str(R / f"{vid}.%(ext)s"),
        }
        with f._ydl(opts) as ydl:
            info = ydl.extract_info(url, download=True)
        video = next(p for p in R.glob(f"{vid}.*") if p.suffix != ".json")
        log = subprocess.run(
            [
                "ffmpeg",
                "-i",
                str(video),
                "-vf",
                f"select='gt(scene,{SCENE})',showinfo",
                "-an",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
            check=False,
        ).stderr
        cuts = [float(x) for x in re.findall(r"pts_time:([0-9.]+)", log)]
        auto = info.get("automatic_captions") or {}
        lang = str(info.get("language") or "en").split("-")[0]
        key = next((k for k in (f"{lang}-orig", lang, "en-orig", "en") if k in auto), None)
        words = []
        if key:
            j3 = next((x["url"] for x in auto[key] if x.get("ext") == "json3"), None)
            if j3:
                for ev in json.loads(f._get(j3)).get("events", []):
                    for seg in ev.get("segs") or []:
                        w = seg.get("utf8", "").strip()
                        if w:
                            words.append(
                                [(ev.get("tStartMs", 0) + seg.get("tOffsetMs", 0)) / 1000, w]
                            )
        target.write_text(
            json.dumps({"duration": float(info.get("duration") or 0), "cuts": cuts, "words": words})
        )
        video.unlink()
        print(f"{vid}: {len(cuts)} cuts, {len(words)} words, {info.get('duration')} s", flush=True)


def load(vid: str) -> dict:
    d = json.loads((R / f"{vid}.json").read_text())
    t = np.array([w[0] for w in d["words"]])
    text = [w[1] for w in d["words"]]
    # A sentence ends where a word carries closing punctuation; its time is when the next word starts.
    ends = np.array([t[i + 1] for i in range(len(text) - 1) if text[i][-1] in ".?!"])
    return d | {"t": t, "ends": ends, "cuts": np.array(d["cuts"])}


def nearest(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """For each time in a, the distance to the closest time in b."""
    i = np.clip(np.searchsorted(b, a), 1, len(b) - 1)
    return np.minimum(np.abs(a - b[i - 1]), np.abs(a - b[i]))


def plot() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from plot_assets import (
        BG,
        CYAN,
        DIM,
        GOLD,
        MUTED,
        TEXT,
        figure,
        frame_panels,
        panel_title,
        style_axes,
        verdict,
    )

    rng = np.random.default_rng(11)
    plt.style.use("dark_background")
    data, res = {}, {}
    for vid, name in VIDEOS:
        d = load(vid)
        cuts, ends, dur = d["cuts"], d["ends"], d["duration"]
        shots = np.diff(np.concatenate([[0], cuts, [dur]]))
        obs = nearest(cuts, ends) if len(cuts) and len(ends) > 1 else np.array([])
        # Null: the same cuts slid along the video by a random amount, wrapping at the end.
        null = (
            np.array(
                [
                    np.median(nearest(np.sort((cuts + rng.uniform(5, dur - 5)) % dur), ends))
                    for _ in range(NULLS)
                ]
            )
            if len(obs)
            else np.array([])
        )
        within = float((obs < 0.5).mean()) if len(obs) else float("nan")
        null_within = (
            np.array(
                [
                    (nearest(np.sort((cuts + rng.uniform(5, dur - 5)) % dur), ends) < 0.5).mean()
                    for _ in range(NULLS)
                ]
            )
            if len(obs)
            else np.array([])
        )
        data[vid] = d | {"shots": shots, "obs": obs, "null": null, "null_within": null_within}
        res[name] = {
            "minutes": dur / 60,
            "cuts": len(cuts),
            "cuts_per_minute": len(cuts) / (dur / 60),
            "median_shot_s": float(np.median(shots)),
            "words_per_minute": len(d["t"]) / (dur / 60),
            "sentences": len(ends),
            "median_sentence_s": float(np.median(np.diff(ends))) if len(ends) > 1 else None,
            "cuts_within_half_second_of_a_sentence_end": within,
            "same_if_cuts_fell_anywhere": [
                float(np.mean(null_within)),
                float(np.percentile(null_within, 99)),
            ]
            if len(null_within)
            else None,
            "median_distance_cut_to_sentence_end_s": float(np.median(obs)) if len(obs) else None,
            "median_distance_if_cuts_fell_anywhere_s": float(np.median(null))
            if len(null)
            else None,
        }
    (OUT / "results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))
    e = res[VIDEOS[0][1]]
    fig, top = figure(
        20,
        10,
        67,
        "EDIT RHYTHM  ·  CUTS AGAINST SENTENCES",
        "Does a video cut on the sentence?",
        f"cuts from the picture (scene change above {SCENE} on a 360p copy), words from the speech-recognition track with a time per word  ·  "
        f"film essay: {e['cuts']} cuts in {e['minutes']:.0f} min, median shot {e['median_shot_s']:.1f} s, {e['cuts_within_half_second_of_a_sentence_end']:.0%} of cuts within half a second of a sentence end",
    )
    gs = fig.add_gridspec(
        len(VIDEOS),
        3,
        left=0.05,
        right=0.975,
        bottom=0.09,
        top=top - 0.07,
        wspace=0.17,
        hspace=0.5,
        width_ratios=[2.3, 1, 1],
    )
    for r, (vid, name) in enumerate(VIDEOS):
        d = data[vid]
        lo, hi = d["duration"] * 0.3, d["duration"] * 0.3 + 120
        ax = fig.add_subplot(gs[r, 0])
        style_axes(ax)
        m = (d["t"] >= lo) & (d["t"] <= hi)
        ax.vlines(d["t"][m], 0.0, 0.42, color=MUTED, lw=0.6, label="a word")
        se = d["ends"][(d["ends"] >= lo) & (d["ends"] <= hi)]
        ax.vlines(se, 0.0, 0.62, color=CYAN, lw=1.4, label="a sentence ends")
        cc = d["cuts"][(d["cuts"] >= lo) & (d["cuts"] <= hi)]
        ax.vlines(cc, 0.5, 1.0, color=GOLD, lw=2.0, label="the picture cuts")
        ax.set_xlim(lo, hi)
        ax.set_ylim(0, 1.05)
        ax.set_yticks([])
        ax.set_xlabel("seconds into the video (a two-minute stretch)")
        if r == 0:
            ax.legend(
                frameon=False,
                fontsize=9,
                labelcolor=TEXT,
                loc="upper right",
                ncol=3,
                bbox_to_anchor=(1, 1.32),
            )
        panel_title(ax, name, width=70)
        ax = fig.add_subplot(gs[r, 1])
        style_axes(ax)
        ax.hist(
            d["shots"], bins=np.geomspace(0.2, 400, 34), color=GOLD, label="shots in this video"
        )
        ax.axvline(
            np.median(d["shots"]),
            color=TEXT,
            lw=1.2,
            ls="--",
            label=f"median {np.median(d['shots']):.1f} s",
        )
        ax.set_xscale("log")
        ax.set_xlabel("how long a shot holds, seconds (log)")
        ax.legend(frameon=False, fontsize=8.5, labelcolor=TEXT, loc="upper right")
        panel_title(ax, "Shot lengths", width=30)
        ax = fig.add_subplot(gs[r, 2])
        style_axes(ax)
        if len(d["null_within"]):
            ax.hist(d["null_within"], bins=30, color=DIM, label="the same cuts slid to anywhere")
            w = float((d["obs"] < 0.5).mean())
            ax.axvline(w, color=GOLD, lw=2.4, label=f"this video: {w:.0%}")
            ax.legend(frameon=False, fontsize=8.5, labelcolor=TEXT, loc="upper right")
        ax.set_yticks([])
        ax.set_xlabel("share of cuts within half a second of a sentence end")
        panel_title(ax, "Cuts landing on a sentence end", width=30)
    z = e["cuts_within_half_second_of_a_sentence_end"] - e["same_if_cuts_fell_anywhere"][0]
    verdict(
        fig,
        f"film essay: {e['cuts_within_half_second_of_a_sentence_end']:.0%} of cuts land on a sentence end, against {e['same_if_cuts_fell_anywhere'][0]:.0%} if they fell anywhere ({z:+.0%})",
    )
    frame_panels(fig)
    fig.savefig(OUT / "01-rhythm.png", dpi=300, facecolor=BG)
    print("saved")


if __name__ == "__main__":
    {"fetch": fetch, "plot": plot}[sys.argv[1]]()
