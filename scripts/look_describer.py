"""Pilot: a model describes each distinct look of a video, with and without the corpus in view.

Aware arm: the describer is handed the vocabulary built so far and, for each
tile, how the nearest already-described looks (by tile vector) were described.
Blind arm: the same frames with neither. Titles are never shown, so the
subject can only come from the frames. Frames are pulled from the video at
full resolution and handed over untouched; a sprite tile stands in, at its
native size, only when that pull fails. Resumable; writes ~/.ytk/describer/.

    uv run python scripts/look_describer.py            # 20 aware + 10 blind calls
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

from ytk import fetch, sdk, store

SPRITES, OUT = Path.home() / ".ytk" / "sprites", Path.home() / ".ytk" / "describer"
MODEL = "claude-sonnet-5"
LOOKS_PER_VIDEO, NEAR_SIM, NEAR_K = 9, 0.70, 2
FACETS = ["medium", "palette", "light", "texture", "composition", "style"]
LETTERS = "ABCDEFGHI"

SYSTEM = """You describe how video frames LOOK for a personal taste library. You are given up to nine frames from one video as separate image files, A.jpg to I.jpg. Each frame stands for one distinct look that recurs in the video.

For every frame return:
- usable: false if the frame is blank, black, a transition blur or otherwise carries no look; then leave the other fields empty.
- shown: one plain sentence on what is depicted.
- look: two or three sentences on how it looks with the subject taken away: palette, light, texture or grain, how the frame is composed, what medium it is (live footage, screen recording, 2D animation, 3D render, slides). Someone who has never seen the frame should be able to picture its surface. Do not restate what is depicted.
- lineage: named styles, eras, movements, tools or makers this look descends from or resembles, if any. Be specific or leave it empty; never invent a name to fill the field.
- feel: three to five words for how it lands.
- terms: short reusable tags, each written facet:term, facets limited to medium, palette, light, texture, composition, style. Four to eight per frame. Terms describe the look, never the subject.
- new_terms: for every term you used that was not in the vocabulary you were given, its one-line definition.

Read every frame file with the Read tool before answering. A file named with -sprite is a small thumbnail standing in for a frame that could not be fetched: describe it, but claim nothing about its texture."""

AWARE_RULES = """A vocabulary built from frames already described in this library follows, then, per frame, how the nearest already-described frames were described. Two frames that look alike must end up with the same terms, so reuse an existing term whenever it fits, even if you would have phrased it differently. Coin a new term only when no existing one fits, and define it."""

SCHEMA = {
    "type": "object",
    "properties": {
        "frames": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tile": {"type": "string"},
                    "usable": {"type": "boolean"},
                    "shown": {"type": "string"},
                    "look": {"type": "string"},
                    "lineage": {"type": "string"},
                    "feel": {"type": "string"},
                    "terms": {"type": "array", "items": {"type": "string"}},
                    "new_terms": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "term": {"type": "string"},
                                "definition": {"type": "string"},
                            },
                            "required": ["term", "definition"],
                        },
                    },
                },
                "required": [
                    "tile",
                    "usable",
                    "shown",
                    "look",
                    "lineage",
                    "feel",
                    "terms",
                    "new_terms",
                ],
            },
        }
    },
    "required": ["frames"],
}


def pick_videos() -> tuple[list[str], list[str]]:
    """Three families of near neighbors (so reuse can be tested) plus a spread."""
    sp = np.load(SPRITES / "spaces.npz")
    ids = list(sp["ids"])
    g = store._videos_collection().get(ids=ids, include=["metadatas"])
    title = {i: m.get("title", "").lower() for i, m in zip(g["ids"], g["metadatas"], strict=True)}
    chosen: list[int] = []
    for words, extra in (("usman", 4), ("svd visualized", 3), ("touchdesigner tutorial: video", 3)):
        seed = next(k for k, i in enumerate(ids) if words in title[i])
        chosen += [seed, *[int(j) for j in sp["nn_shown"][seed] if int(j) not in chosen][:extra]]
    family = list(chosen)
    x = sp["shown"]
    while len(chosen) < 20:
        chosen.append(int(np.argmax((1 - x @ x[chosen].T).min(1))))
    return [ids[k] for k in chosen], [ids[k] for k in family[:10]]


def sprite_tile(vid: str, i: int) -> Image.Image:
    grid = json.loads((SPRITES / vid / "grid.json").read_text())
    frag, k = divmod(i, grid["rows"] * grid["cols"])
    r, c = divmod(k, grid["cols"])
    with Image.open(SPRITES / vid / f"{frag:03d}.jpg") as im:
        w, h = im.width // grid["cols"], im.height // grid["rows"]
        return im.convert("RGB").crop((c * w, r * h, (c + 1) * w, (r + 1) * h))


def frames(vid: str, reps: list[int]) -> tuple[Path, list[str]]:
    """One file per look, lettered, in the video's own folder. Returns the folder and the file names."""
    d = OUT / "frames" / vid
    d.mkdir(parents=True, exist_ok=True)
    interval = json.loads((SPRITES / vid / "grid.json").read_text())["interval"]

    def one(item: tuple[int, int]) -> str:
        n, rep = item
        real, stand_in = d / f"{LETTERS[n]}.jpg", d / f"{LETTERS[n]}-sprite.jpg"
        if real.exists() or stand_in.exists():
            return real.name if real.exists() else stand_in.name
        try:
            fetch._youtube_closeup(
                f"https://www.youtube.com/watch?v={vid}", (rep + 0.5) * interval, real
            )
            return real.name
        except Exception:
            sprite_tile(vid, rep).save(stand_in, quality=95)
            return stand_in.name

    with ThreadPoolExecutor(4) as pool:
        return d, list(pool.map(one, enumerate(reps)))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "DONE").unlink(missing_ok=True)
    mo = np.load(SPRITES / "moments.npz")
    videos, blind_set = pick_videos()
    (OUT / "videos.json").write_text(json.dumps({"aware": videos, "blind": blind_set}))
    vocab: dict[str, dict] = {}
    seen_vec: list[np.ndarray] = []
    seen_desc: list[dict] = []
    t0 = time.monotonic()
    for n, vid in enumerate(videos, 1):
        rows = np.where(mo["look_video"] == vid)[0][:LOOKS_PER_VIDEO]
        _, names = frames(vid, [int(r) for r in mo["look_rep"][rows]])
        print(
            f"[frames {n}/{len(videos)}] {vid}  {len(names)} frames, {sum('sprite' in x for x in names)} sprite stand-ins  ({time.monotonic() - t0:.0f} s)",
            flush=True,
        )
    for arm, vids in (("aware", videos), ("blind", blind_set)):
        (OUT / arm).mkdir(exist_ok=True)
        for n, vid in enumerate(vids, 1):
            rows = np.where(mo["look_video"] == vid)[0][:LOOKS_PER_VIDEO]
            reps, vecs = [int(r) for r in mo["look_rep"][rows]], mo["look_vec"][rows]
            target = OUT / arm / f"{vid}.json"
            folder, names = frames(vid, reps)
            user = f"The frames are in {folder}: {', '.join(names)}."
            if arm == "aware" and vocab:
                lines = [
                    f"- {t}: {v['definition']} (used {v['count']}x)"
                    for t, v in sorted(vocab.items())
                ]
                near = []
                for k, v in enumerate(vecs):
                    sims = np.stack(seen_vec) @ v
                    for j in np.argsort(-sims)[:NEAR_K]:
                        if sims[j] >= NEAR_SIM:
                            d = seen_desc[j]
                            near.append(
                                f"- frame {LETTERS[k]} resembles one described as: {d['look']} Terms: {', '.join(d['terms'])}"
                            )
                user += f"\n\n{AWARE_RULES}\n\nVOCABULARY\n" + "\n".join(lines)
                user += "\n\nNEAREST ALREADY-DESCRIBED FRAMES\n" + (
                    "\n".join(near) if near else "(none close enough)"
                )
            if target.exists():
                data = json.loads(target.read_text())
            else:
                res = sdk.call_structured(SYSTEM, user, SCHEMA, add_dirs=[folder], model=MODEL)
                data = {
                    "video": vid,
                    "reps": reps,
                    "files": names,
                    "frames": res.data["frames"],
                    "prompt_chars": len(user),
                }
                target.write_text(json.dumps(data, indent=1))
            if arm == "aware":
                for k, fr in enumerate(data["frames"][: len(reps)]):
                    if not fr["usable"]:
                        continue
                    defs = {d["term"]: d["definition"] for d in fr["new_terms"]}
                    for t in fr["terms"]:
                        vocab.setdefault(t, {"definition": defs.get(t, ""), "count": 0})[
                            "count"
                        ] += 1
                    seen_vec.append(vecs[k])
                    seen_desc.append(fr)
                (OUT / "vocabulary.json").write_text(json.dumps(vocab, indent=1, sort_keys=True))
            used = sum(len(f["terms"]) for f in data["frames"])
            print(
                f"[{arm} {n}/{len(vids)}] {vid}  {len(data['frames'])} frames, {used} terms, vocabulary {len(vocab)}  ({time.monotonic() - t0:.0f} s)",
                flush=True,
            )
    (OUT / "DONE").write_text("ok\n")
    print("DONE")


if __name__ == "__main__":
    main()
