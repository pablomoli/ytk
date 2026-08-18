"""Section 49: build extractive latent portraits and run the registered gate.

Pre-registered in docs/assets/49-latent-portraits/README.md. Portrait =
activation-weighted average of a latent's top-24 exemplar thumbnails
(center-cropped, 128x128). Gate P1 = disjoint-half portraits of the same
latent must separate from cross-pairs at ROC AUC >= 0.80 (pixel Pearson r).

    YTK_VISUAL_INDEX=off uv run python experiments/sae_qwen/latent_portraits.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
VAULT = Path.home() / (
    "Library/Mobile Documents/iCloud~md~obsidian/Documents/Vault/second-brain/sources"
)
SIDE = 128
TOP_EX = 24
MIN_IMG = 12


def thumb_path(kind: str, source: str, rid: str) -> Path | None:
    if kind in ("video", "segment"):
        vid = rid if kind == "video" else rid.rsplit("_", 1)[0]
        return VAULT / "youtube" / "thumbnails" / f"{vid}-thumb.jpg"
    if source in ("instagram", "tiktok"):
        slug = rid.split(f"note_sources_{source}_", 1)[-1]
        return VAULT / source / "thumbnails" / f"{slug.rsplit('-', 1)[-1]}-thumb.jpg"
    return None


_cache: dict[Path, np.ndarray | None] = {}


def load(p: Path | None) -> np.ndarray | None:
    if p is None:
        return None
    if p not in _cache:
        try:
            im = Image.open(p).convert("RGB")
            side = min(im.size)
            left, up = (im.width - side) // 2, (im.height - side) // 2
            im = im.crop((left, up, left + side, up + side)).resize((SIDE, SIDE))
            _cache[p] = np.asarray(im, np.float32) / 255.0
        except Exception:
            _cache[p] = None
    return _cache[p]


def main() -> None:
    rows = [json.loads(x) for x in (DATA / "rows.jsonl").read_text().splitlines()]
    z = np.load(DATA / "acts_final_d2048_k32_s0.npz")
    idx, val = z["idx"], z["val"]
    names = {
        f["feature"]: f.get("name")
        for f in json.loads((HERE / "features.json").read_text())["features"]
    }

    # top-24 exemplar rows per latent, by activation, over the full cache
    per: dict[int, list[tuple[float, int]]] = {}
    r_, j_ = np.nonzero(val > 0)
    for r, j in zip(r_, j_):
        per.setdefault(int(idx[r, j]), []).append((float(val[r, j]), int(r)))

    portraits: dict[int, np.ndarray] = {}
    halves: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    meta: dict[int, dict] = {}
    for f, hits in per.items():
        hits.sort(reverse=True)
        imgs, acts = [], []
        for a, r in hits[:TOP_EX]:
            row = rows[r]
            img = load(thumb_path(row["kind"], row["source"], row["id"]))
            if img is not None:
                imgs.append(img)
                acts.append(a)
        if len(imgs) < MIN_IMG:
            continue
        W = np.asarray(acts)[:, None, None, None]
        M = np.asarray(imgs)
        portraits[f] = (M * W).sum(0) / W.sum()
        even, odd = M[0::2], M[1::2]
        we, wo = W[0::2], W[1::2]
        halves[f] = ((even * we).sum(0) / we.sum(), (odd * wo).sum(0) / wo.sum())
        meta[f] = {"name": names.get(f), "n_img": len(imgs)}

    feats = sorted(portraits)
    print(f"{len(feats)} latents qualify (>= {MIN_IMG} image exemplars)")

    def corr(a: np.ndarray, b: np.ndarray) -> float:
        x, y = a.ravel(), b.ravel()
        x = x - x.mean()
        y = y - y.mean()
        return float((x @ y) / (np.linalg.norm(x) * np.linalg.norm(y) + 1e-12))

    same = np.array([corr(*halves[f]) for f in feats])
    rng = np.random.default_rng(49)
    cross = []
    for _ in range(2000):
        i, j = rng.choice(len(feats), 2, replace=False)
        cross.append(corr(halves[feats[i]][0], halves[feats[j]][1]))
    cross = np.array(cross)

    scores = np.concatenate([same, cross])
    ranks = scores.argsort().argsort().astype(float) + 1
    p1_auc = float(
        (ranks[: len(same)].sum() - len(same) * (len(same) + 1) / 2) / (len(same) * len(cross))
    )

    result = {
        "registered": "P1: same-latent split-half vs cross-pair pixel r, AUC >= 0.80",
        "n_qualifying": len(feats),
        "same_median_r": round(float(np.median(same)), 4),
        "cross_median_r": round(float(np.median(cross)), 4),
        "auc": round(p1_auc, 4),
        "gate": "PASS" if p1_auc >= 0.80 else "FAIL",
        "seed": 49,
    }
    np.savez_compressed(
        DATA / "portraits.npz",
        feats=np.array(feats),
        portraits=np.stack([portraits[f] for f in feats]),
        same=same,
        cross=cross,
    )
    (HERE / "portraits.json").write_text(
        json.dumps({**result, "latents": {str(f): meta[f] for f in feats}}, indent=1)
    )
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
