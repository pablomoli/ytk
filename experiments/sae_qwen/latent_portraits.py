"""Section 49: build extractive latent portraits and run the registered gate.

Pre-registered in docs/assets/49-latent-portraits/README.md. AMENDED before
merge: the first run was contaminated — segments inherit their parent
video's thumbnail, so 40% of a typical latent's top-24 exemplars were the
same image repeated, and split-half similarity partially measured "do both
halves contain the same video". Exemplars now dedupe by note BEFORE the
top-24 cut; the gate is otherwise unchanged. Also ships the medoid face:
the real exemplar image closest to the deduped weighted mean.

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

    def note_key(r: int) -> str:
        row = rows[r]
        if row["kind"] == "segment":
            return row["id"].rsplit("_", 1)[0]
        return row["id"]

    portraits: dict[int, np.ndarray] = {}
    medoids: dict[int, np.ndarray] = {}
    halves: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    halves_raw: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    meta: dict[int, dict] = {}
    for f, hits in per.items():
        hits.sort(reverse=True)
        # contaminated variant, as first run: no dedup, top-24 by rank
        raw_imgs, raw_w = [], []
        for a, r in hits[:TOP_EX]:
            row = rows[r]
            img = load(thumb_path(row["kind"], row["source"], row["id"]))
            if img is not None:
                raw_imgs.append(img)
                raw_w.append(a)
        if len(raw_imgs) >= MIN_IMG:
            RM = np.asarray(raw_imgs)
            RW = np.asarray(raw_w)[:, None, None, None]
            halves_raw[f] = (
                (RM[0::2] * RW[0::2]).sum(0) / RW[0::2].sum(),
                (RM[1::2] * RW[1::2]).sum(0) / RW[1::2].sum(),
            )
        imgs, acts, seen = [], [], set()
        for a, r in hits:
            nk = note_key(r)
            if nk in seen:
                continue  # one exemplar per note: segments share their video's thumbnail
            row = rows[r]
            img = load(thumb_path(row["kind"], row["source"], row["id"]))
            if img is not None:
                seen.add(nk)
                imgs.append(img)
                acts.append(a)
            if len(imgs) == TOP_EX:
                break
        if len(imgs) < MIN_IMG:
            continue
        W = np.asarray(acts)[:, None, None, None]
        M = np.asarray(imgs)
        portraits[f] = (M * W).sum(0) / W.sum()
        d = ((M - portraits[f][None]) ** 2).sum(axis=(1, 2, 3))
        medoids[f] = M[int(np.argmin(d))]
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

    feats_raw = sorted(halves_raw)
    same_raw = np.array([corr(*halves_raw[f]) for f in feats_raw])
    cross_raw = []
    for _ in range(2000):
        i, j = rng.choice(len(feats_raw), 2, replace=False)
        cross_raw.append(corr(halves_raw[feats_raw[i]][0], halves_raw[feats_raw[j]][1]))
    cross_raw = np.array(cross_raw)
    sc = np.concatenate([same_raw, cross_raw])
    rk = sc.argsort().argsort().astype(float) + 1
    auc_raw = float(
        (rk[: len(same_raw)].sum() - len(same_raw) * (len(same_raw) + 1) / 2)
        / (len(same_raw) * len(cross_raw))
    )

    scores = np.concatenate([same, cross])
    ranks = scores.argsort().argsort().astype(float) + 1
    p1_auc = float(
        (ranks[: len(same)].sum() - len(same) * (len(same) + 1) / 2) / (len(same) * len(cross))
    )

    result = {
        "registered": "P1: same-latent split-half vs cross-pair pixel r, AUC >= 0.80",
        "amendment": "exemplars deduped by note before the top-24 cut (contamination found by owner in the hub: segments repeat their video thumbnail; 40% mean duplication)",
        "n_qualifying": len(feats),
        "same_median_r": round(float(np.median(same)), 4),
        "cross_median_r": round(float(np.median(cross)), 4),
        "auc": round(p1_auc, 4),
        "gate": "PASS" if p1_auc >= 0.80 else "FAIL",
        "contaminated_auc": round(auc_raw, 4),
        "contaminated_same_median_r": round(float(np.median(same_raw)), 4),
        "mean_duplicate_fraction_top24": 0.40,
        "seed": 49,
    }
    np.savez_compressed(
        DATA / "portraits.npz",
        feats=np.array(feats),
        portraits=np.stack([portraits[f] for f in feats]),
        medoids=np.stack([medoids[f] for f in feats]),
        same=same,
        cross=cross,
        same_raw=same_raw,
        cross_raw=cross_raw,
    )
    (HERE / "portraits.json").write_text(
        json.dumps({**result, "latents": {str(f): meta[f] for f in feats}}, indent=1)
    )
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
