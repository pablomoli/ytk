"""Cut every sprite-swept video into moments and distinct looks. No model.

A look is a group of a video's tiles that resemble each other (average-link
clustering of the tile vectors, cosine distance under LOOK_DIST); a moment is
an unbroken run of one look. Near-black tiles are dropped first. Writes
~/.ytk/sprites/moments.npz.

    uv run python scripts/sprite_moments.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.cluster.hierarchy import fcluster, linkage

SPRITES, EMB = Path.home() / ".ytk" / "sprites", Path.home() / ".ytk" / "sprites-emb"
# Tiles closer than this (cosine distance, average link) count as one look.
LOOK_DIST = 0.22
BLACK_MEAN, BLACK_STD = 0.03, 0.02


def black_mask(d: Path, n: int) -> np.ndarray:
    grid = json.loads((d / "grid.json").read_text())
    out: list[bool] = []
    for sheet in sorted(d.glob("[0-9]*.jpg")):
        with Image.open(sheet) as im:
            a = np.asarray(im.convert("L"), dtype=np.float32) / 255
        h, w = a.shape[0] // grid["rows"], a.shape[1] // grid["cols"]
        for k in range(grid["rows"] * grid["cols"]):
            r, c = divmod(k, grid["cols"])
            t = a[r * h : (r + 1) * h, c * w : (c + 1) * w]
            out.append(bool(t.mean() < BLACK_MEAN and t.std() < BLACK_STD))
    return np.array(out[:n])


def main() -> None:
    rec: dict[str, list] = {k: [] for k in ("video", "look", "start", "end", "rep", "share")}
    look_rec: dict[str, list] = {k: [] for k in ("video", "look", "rep", "share", "vec")}
    per_video = []
    ids = sorted(p.stem for p in EMB.glob("*.npy"))
    for vi, vid in enumerate(ids):
        t = np.load(EMB / f"{vid}.npy").astype(np.float32)
        interval = json.loads((SPRITES / vid / "grid.json").read_text())["interval"]
        keep = np.where(~black_mask(SPRITES / vid, len(t)))[0]
        if len(keep) < 2:
            continue
        x = t[keep]
        labels = fcluster(linkage(x, "average", metric="cosine"), LOOK_DIST, "distance")
        # Looks numbered by how much of the video they hold, largest first.
        order = {
            lab: r for r, lab in enumerate(np.argsort(-np.bincount(labels))[: labels.max()]) if lab
        }
        looks = np.array([order[lab] for lab in labels])
        for lk in range(looks.max() + 1):
            m = np.where(looks == lk)[0]
            mean = x[m].mean(0)
            rep = keep[m[np.argmax(x[m] @ mean)]]
            look_rec["video"].append(vid)
            look_rec["look"].append(lk)
            look_rec["rep"].append(int(rep))
            look_rec["share"].append(len(m) / len(keep))
            look_rec["vec"].append(mean / np.linalg.norm(mean))
        cuts = np.where((np.diff(looks) != 0) | (np.diff(keep) != 1))[0] + 1
        for seg in np.split(np.arange(len(keep)), cuts):
            rec["video"].append(vid)
            rec["look"].append(int(looks[seg[0]]))
            rec["start"].append(float(keep[seg[0]] * interval))
            rec["end"].append(float((keep[seg[-1]] + 1) * interval))
            rec["rep"].append(int(keep[seg[len(seg) // 2]]))
            rec["share"].append(len(seg) / len(keep))
        per_video.append((vid, len(keep), len(t) - len(keep), int(looks.max() + 1), len(cuts) + 1))
        if (vi + 1) % 60 == 0:
            print(f"[{vi + 1}/{len(ids)}]", flush=True)
    pv = np.array([p[1:] for p in per_video])
    np.savez(
        SPRITES / "moments.npz",
        moment_video=np.array(rec["video"]),
        moment_look=np.array(rec["look"]),
        moment_start=np.array(rec["start"]),
        moment_end=np.array(rec["end"]),
        moment_rep=np.array(rec["rep"]),
        look_video=np.array(look_rec["video"]),
        look_id=np.array(look_rec["look"]),
        look_rep=np.array(look_rec["rep"]),
        look_share=np.array(look_rec["share"]),
        look_vec=np.stack(look_rec["vec"]).astype(np.float32),
        video=np.array([p[0] for p in per_video]),
        video_stats=pv,
    )
    print(
        f"DONE {len(per_video)} videos, {pv[:, 0].sum()} tiles kept, {pv[:, 1].sum()} black dropped, "
        f"{pv[:, 2].sum()} looks (median {int(np.median(pv[:, 2]))}), {pv[:, 3].sum()} moments (median {int(np.median(pv[:, 3]))})"
    )


if __name__ == "__main__":
    main()
