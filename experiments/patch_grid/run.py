"""Section 53 (#218): four lenses on SigLIP-2's patch grid, gated against occlusion.

Pre-registered in docs/assets/53-patch-grid/README.md (b32f21f, before this
ran). Per-image maps are cached under ~/.ytk/patch_grid so an interrupted run
resumes; the score file carries ids and numbers only, never titles.

    HF_HUB_OFFLINE=1 uv run python experiments/patch_grid/run.py --limit 2   # smoke
    HF_HUB_OFFLINE=1 uv run python experiments/patch_grid/run.py             # the gate, ~13.5 min
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import random
import subprocess
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from scipy.stats import spearmanr

from ytk import store, visual

SEED = 53
SPIKE, GATE, RATED = 3, 40, 20
G = 6  # occlusion blocks per side; 384 / 6 = 64 px, four patches
PASS_MARK = 0.40
NULL_DRAWS = 2000
BOOT_DRAWS = 2000
CACHE = Path(os.path.expanduser("~/.ytk/patch_grid"))
OUT = Path(__file__).resolve().parents[2] / "docs" / "assets" / "53-patch-grid" / "patch_grid.json"


def sample() -> list[tuple[str, dict]]:
    got = store._get_client().get_collection("ytk_visual").get(include=["metadatas"])
    rows = [
        (i, m)
        for i, m in zip(got["ids"], got["metadatas"])
        if m
        and m.get("source") == "youtube"
        and m.get("title")
        and os.path.exists(os.path.expanduser(m["image_path"]))
    ]
    rows.sort(key=lambda r: r[0])
    random.Random(SEED).shuffle(rows)
    return rows[SPIKE : SPIKE + GATE]


def _unit(x: torch.Tensor) -> torch.Tensor:
    return x / x.norm(dim=-1, keepdim=True)


def lenses(
    vision, head, processor, device, image_path: str, texts: list[str]
) -> dict[str, np.ndarray]:
    """All four maps for one image under texts = [true title, wrong title]."""
    txt = _unit(torch.tensor(visual.embed_texts(texts)))
    pil = Image.open(os.path.expanduser(image_path)).convert("RGB")
    px = processor(images=[pil], return_tensors="pt")["pixel_values"].to(device).to(torch.float16)
    with torch.no_grad():
        h = vision(pixel_values=px).last_hidden_state.float().cpu()
        side = int(h.shape[1] ** 0.5)
        _, w = head.attention(head.probe, h, h, need_weights=True, average_attn_weights=True)
        e = head.probe.shape[-1]
        wv, bv = head.attention.in_proj_weight[2 * e :], head.attention.in_proj_bias[2 * e :]
        v = head.attention.out_proj(h @ wv.T + bv)
        v = v + head.mlp(head.layernorm(v))
        lens2 = (_unit(v[0]) @ txt.T).numpy().reshape(side, side, 2)

        b = px.shape[-1] // G
        batch = [px[0]]
        for r in range(G):
            for c in range(G):
                q = px[0].clone()
                q[:, r * b : (r + 1) * b, c * b : (c + 1) * b] = 0.0  # mid grey in normalized space
                batch.append(q)
        pooled = [
            vision(pixel_values=torch.stack(batch[s : s + 12])).pooler_output.float().cpu()
            for s in range(0, len(batch), 12)
        ]
        sims = (_unit(torch.cat(pooled)) @ txt.T).numpy()

    grads = []
    for t in range(2):
        hg = h.clone().requires_grad_(True)
        (_unit(head(hg)) @ txt[t]).sum().backward()
        grads.append((hg.grad * hg).sum(-1)[0].detach().numpy().reshape(side, side))

    return {
        "lens1": w[0, 0].numpy().reshape(side, side),
        "lens2": lens2,
        "lens3": (sims[0] - sims[1:]).reshape(G, G, 2),
        "lens4": np.stack(grads, -1),
        "base": sims[0],
    }


def blocks(m: np.ndarray, how: str) -> np.ndarray:
    k = m.shape[0] // G
    r = m.reshape(G, k, G, k)
    return (r.sum(axis=(1, 3)) if how == "sum" else r.mean(axis=(1, 3))).ravel()


def rho(a: np.ndarray, b: np.ndarray) -> float:
    r = spearmanr(a, b)[0]
    return 0.0 if np.isnan(r) else float(r)


def score(maps: list[dict[str, np.ndarray]]) -> dict:
    rng = np.random.default_rng(SEED)
    n = len(maps)
    ref = [m["lens3"][..., 0].ravel() for m in maps]
    cheap = {
        "lens1": ([blocks(m["lens1"], "mean") for m in maps], None),
        "lens2": (
            [blocks(m["lens2"][..., 0], "mean") for m in maps],
            [blocks(m["lens2"][..., 1], "mean") for m in maps],
        ),
        "lens4": (
            [blocks(m["lens4"][..., 0], "sum") for m in maps],
            [blocks(m["lens4"][..., 1], "sum") for m in maps],
        ),
    }
    out: dict = {}
    for name, (true_maps, wrong_maps) in cheap.items():
        obs = np.array([rho(true_maps[i], ref[i]) for i in range(n)])
        cross = np.array([[rho(true_maps[i], ref[j]) for j in range(n)] for i in range(n)])
        null_means = np.empty(NULL_DRAWS)
        for d in range(NULL_DRAWS):
            j = rng.integers(0, n - 1, size=n)
            j = np.where(j >= np.arange(n), j + 1, j)  # never the image's own referee map
            null_means[d] = cross[np.arange(n), j].mean()
        p95 = float(np.quantile(null_means, 0.95))
        entry = {
            "per_image": obs.round(4).tolist(),
            "mean": float(obs.mean()),
            "null_means": null_means.round(4).tolist(),
            "null_p95": p95,
            "passes": bool(obs.mean() >= PASS_MARK and obs.mean() > p95),
        }
        if wrong_maps is not None:
            wrong = np.array([rho(wrong_maps[i], ref[i]) for i in range(n)])
            diff = obs - wrong
            boots = np.array([diff[rng.integers(0, n, size=n)].mean() for _ in range(BOOT_DRAWS)])
            lo, hi = np.quantile(boots, [0.025, 0.975])
            entry |= {
                "wrong_title_per_image": wrong.round(4).tolist(),
                "true_minus_wrong": float(diff.mean()),
                "true_minus_wrong_ci95": [float(lo), float(hi)],
                "reads_text": bool(lo > 0),
            }
        out[name] = entry
    out["referee"] = {
        "max_drop_true": [float(m["lens3"][..., 0].max()) for m in maps],
        "max_drop_wrong": [float(m["lens3"][..., 1].max()) for m in maps],
        "base_true": [float(m["base"][0]) for m in maps],
        "base_wrong": [float(m["base"][1]) for m in maps],
    }
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--limit", type=int, default=GATE, help="score only the first N gate images (smoke test)"
    )
    args = ap.parse_args()

    rows = sample()
    CACHE.mkdir(parents=True, exist_ok=True)
    model, processor, device = visual._load()
    vision = model.vision_model
    head = copy.deepcopy(vision.head).float().cpu()

    maps, t0 = [], time.time()
    for k, (iid, meta) in enumerate(rows[: args.limit]):
        f = CACHE / f"{iid.replace(':', '_')}.npz"
        if f.exists():
            maps.append(dict(np.load(f)))
            continue
        wrong = rows[(k + 1) % len(rows)][1]["title"]
        m = lenses(vision, head, processor, device, meta["image_path"], [meta["title"], wrong])
        np.savez(f, **m)
        maps.append(m)
        print(f"[{k + 1}/{args.limit}] {iid}  {time.time() - t0:.0f}s", flush=True)

    result = score(maps) if len(maps) >= 3 else {}
    sha = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=OUT.parent
    ).stdout.strip()
    result |= {
        "ids": [iid for iid, _ in rows[: args.limit]],
        "rated_ids": [iid for iid, _ in rows[:RATED]],
        "n": len(maps),
        "pass_mark": PASS_MARK,
        "model": visual.MODEL_ID,
        "revision": visual.MODEL_REVISION,
        "commit": sha,
        "seconds": round(time.time() - t0, 1),
    }
    if args.limit == GATE:
        OUT.write_text(json.dumps(result, indent=1) + "\n")
        print("wrote", OUT)
    for name in ("lens1", "lens2", "lens4"):
        if name in result:
            r = result[name]
            print(
                f"{name}: mean rho {r['mean']:.3f}  null p95 {r['null_p95']:.3f}  passes {r['passes']}"
            )


if __name__ == "__main__":
    main()
