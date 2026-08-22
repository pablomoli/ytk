"""Section 51 (49R, #192): the portrait claim re-judged in CLIP-image space.

Pre-registered in docs/assets/51-clip-identity/README.md (8af27ed, before
this ran). Same split-half design as section 49, deduped one-per-note; the
judge is cosine between activation-weighted mean CLIP ViT-L/14 image
embeddings of disjoint exemplar halves. Gate: AUC >= 0.80.

    YTK_VISUAL_INDEX=off uv run --with torch --with open_clip_torch python \
        experiments/sae_qwen/clip_identity.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from paths import DATA
from PIL import Image

HERE = Path(__file__).resolve().parent
VAULT = Path.home() / (
    "Library/Mobile Documents/iCloud~md~obsidian/Documents/Vault/second-brain/sources"
)
TOP_EX = 24
MIN_IMG = 12
PROT = 1597


def thumb_path(kind: str, source: str, rid: str) -> Path | None:
    if kind in ("video", "segment"):
        vid = rid if kind == "video" else rid.rsplit("_", 1)[0]
        return VAULT / "youtube" / "thumbnails" / f"{vid}-thumb.jpg"
    if source in ("instagram", "tiktok"):
        slug = rid.split(f"note_sources_{source}_", 1)[-1]
        return VAULT / source / "thumbnails" / f"{slug.rsplit('-', 1)[-1]}-thumb.jpg"
    return None


def main() -> None:
    import open_clip
    import torch

    rows = [json.loads(x) for x in (DATA / "rows.jsonl").read_text().splitlines()]
    z = np.load(DATA / "acts_final_d2048_k32_s0.npz")
    idx, val = z["idx"], z["val"]

    per: dict[int, list[tuple[float, int]]] = {}
    r_, j_ = np.nonzero(val > 0)
    for r, j in zip(r_, j_):
        per.setdefault(int(idx[r, j]), []).append((float(val[r, j]), int(r)))

    def note_key(r: int) -> str:
        row = rows[r]
        return row["id"].rsplit("_", 1)[0] if row["kind"] == "segment" else row["id"]

    # collect per-latent deduped exemplar image paths + weights
    sets: dict[int, list[tuple[float, Path]]] = {}
    all_paths: set[Path] = set()
    for f, hits in per.items():
        hits.sort(reverse=True)
        chosen, seen = [], set()
        for a, r in hits:
            nk = note_key(r)
            if nk in seen:
                continue
            row = rows[r]
            p = thumb_path(row["kind"], row["source"], row["id"])
            if p is not None and p.exists():
                seen.add(nk)
                chosen.append((a, p))
            if len(chosen) == TOP_EX:
                break
        if len(chosen) >= MIN_IMG:
            sets[f] = chosen
            all_paths.update(p for _, p in chosen)

    paths = sorted(all_paths)
    print(f"{len(sets)} latents qualify; {len(paths)} unique thumbnails to embed")

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model, _, preprocess = open_clip.create_model_and_transforms("ViT-L-14", pretrained="openai")
    model = model.to(device).eval()

    cache_f = DATA / "clip_image.npz"
    if cache_f.exists():
        cz = np.load(cache_f, allow_pickle=True)
        cached = {str(p): e for p, e in zip(cz["paths"], cz["E"])}
    else:
        cached = {}
    todo = [p for p in paths if str(p) not in cached]
    B = 16

    def save_cache() -> None:
        np.savez_compressed(
            cache_f,
            paths=np.array(list(cached.keys())),
            E=np.stack(list(cached.values())) if cached else np.zeros((0, 768), np.float32),
        )

    with torch.no_grad():
        for i in range(0, len(todo), B):
            batch = []
            ok_paths = []
            for p in todo[i : i + B]:
                try:
                    batch.append(preprocess(Image.open(p).convert("RGB")))
                    ok_paths.append(p)
                except Exception:
                    continue
            if not batch:
                continue
            e = model.encode_image(torch.stack(batch).to(device)).float().cpu().numpy()
            for p, v in zip(ok_paths, e):
                cached[str(p)] = v
            if (i // B) % 10 == 0:
                save_cache()  # a kill costs minutes, not the run
            print(f"  embedded {min(i + B, len(todo))}/{len(todo)} [{device}]", flush=True)
    save_cache()
    E = {p: v / (np.linalg.norm(v) + 1e-12) for p, v in cached.items()}
    np.savez_compressed(
        cache_f,
        paths=np.array(list(cached.keys())),
        E=np.stack(list(cached.values())),
    )

    def identity(items: list[tuple[float, Path]]) -> np.ndarray | None:
        vs, ws = [], []
        for a, p in items:
            v = E.get(str(p))
            if v is not None:
                vs.append(v)
                ws.append(a)
        if not vs:
            return None
        m = (np.asarray(vs) * np.asarray(ws)[:, None]).sum(0) / sum(ws)
        return m / (np.linalg.norm(m) + 1e-12)

    feats, same, halves = [], [], {}
    medoids = {}
    for f, items in sets.items():
        a, b = identity(items[0::2]), identity(items[1::2])
        if a is None or b is None:
            continue
        feats.append(f)
        halves[f] = (a, b)
        same.append(float(a @ b))
        full = identity(items)
        sims = [float(full @ E[str(p)]) for _, p in items if str(p) in E]
        medoids[f] = str(items[int(np.argmax(sims))][1])
    same = np.array(same)

    rng = np.random.default_rng(51)
    cross = []
    for _ in range(2000):
        i, j = rng.choice(len(feats), 2, replace=False)
        cross.append(float(halves[feats[i]][0] @ halves[feats[j]][1]))
    cross = np.array(cross)

    scores = np.concatenate([same, cross])
    ranks = scores.argsort().argsort().astype(float) + 1
    auc = float(
        (ranks[: len(same)].sum() - len(same) * (len(same) + 1) / 2) / (len(same) * len(cross))
    )

    result = {
        "registered": "AUC >= 0.80, same-latent split-half vs cross-pair, CLIP-image cosine",
        "n_qualifying": len(feats),
        "n_unique_thumbnails": len(paths),
        "same_median_cos": round(float(np.median(same)), 4),
        "cross_median_cos": round(float(np.median(cross)), 4),
        "auc": round(auc, 4),
        "gate": "PASS" if auc >= 0.80 else "FAIL",
        "pixel_judge_auc_section49": 0.4282,
        "device": device,
        "protagonist_medoid": medoids.get(PROT),
        "seed": 51,
    }
    np.savez_compressed(
        DATA / "clip_identity.npz",
        feats=np.array(feats),
        same=same,
        cross=cross,
    )
    (HERE / "clip_identity.json").write_text(
        json.dumps({**result, "medoids": {str(f): medoids[f] for f in feats}}, indent=1)
    )
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
