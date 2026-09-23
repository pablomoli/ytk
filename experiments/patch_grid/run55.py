"""Section 55 (#218): the long tokens in SigLIP-2's encoder and what hiding them does.

HF_HUB_OFFLINE=1 uv run python experiments/patch_grid/run55.py norms   # 50 images, one forward each, hooks on all 27 layers
HF_HUB_OFFLINE=1 uv run python experiments/patch_grid/run55.py hide    # CPU: the head with and without the long tokens
"""

from __future__ import annotations

import copy
import os
import sys
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import night as N
import run as R53
from region_head import region_attention, region_vectors

from ytk import visual

NORM_THRESHOLD = 150.0  # Darcet et al., arXiv 2309.16588
OUT = N.CACHE / "55_norms.npz"


def images() -> list[tuple[str, str]]:
    """The ten night images then the 40 gate thumbnails, (name, path)."""
    rows = [(n, str(N.image_path(n))) for n in N.IMAGES]
    rows += [(iid, os.path.expanduser(m["image_path"])) for iid, m in R53.sample()]
    return rows


def norms() -> None:
    model, processor, device = visual._load()
    vision = model.vision_model
    layers = vision.encoder.layers
    grabbed: list[torch.Tensor] = []

    def hook(_m, _i, out):
        grabbed.append((out[0] if isinstance(out, tuple) else out).detach())

    handles = [layer.register_forward_hook(hook) for layer in layers]
    rows = images()
    per_layer = np.zeros((len(rows), len(layers), N.SIDE * N.SIDE), dtype=np.float32)
    tokens = np.zeros((len(rows), N.SIDE * N.SIDE, vision.config.hidden_size), dtype=np.float16)
    pooled = np.zeros((len(rows), vision.config.hidden_size), dtype=np.float32)
    t0 = time.time()
    with torch.no_grad():
        for k, (name, path) in enumerate(rows):
            grabbed.clear()
            px = processor(images=[Image.open(path).convert("RGB")], return_tensors="pt")[
                "pixel_values"
            ]
            o = vision(pixel_values=px.to(device).to(torch.float16))
            assert len(grabbed) == len(layers), len(grabbed)
            per_layer[k] = torch.stack([g[0].float().norm(dim=-1) for g in grabbed]).cpu().numpy()
            tokens[k] = o.last_hidden_state[0].float().cpu().numpy().astype(np.float16)
            pooled[k] = o.pooler_output[0].float().cpu().numpy()
            if k % 10 == 9:
                print(f"[{k + 1}/{len(rows)}] {time.time() - t0:.0f}s", flush=True)
    for h in handles:
        h.remove()
    high = per_layer[:, -1] > NORM_THRESHOLD
    np.savez_compressed(
        OUT,
        names=np.array([n for n, _ in rows]),
        per_layer=per_layer,
        high=high,
        tokens=tokens,
        pooled=pooled,
        threshold=np.array(NORM_THRESHOLD),
    )
    frac = (per_layer > NORM_THRESHOLD).mean(axis=(0, 2))
    print("fraction of tokens above", NORM_THRESHOLD, "per layer:", np.round(frac, 3).tolist())
    print(
        "long tokens per image at the last layer: median",
        int(np.median(high.sum(1))),
        "range",
        high.sum(1).min(),
        high.sum(1).max(),
    )
    print(
        "median norm at the last layer, long",
        np.median(per_layer[:, -1][high]).round(0),
        "others",
        np.median(per_layer[:, -1][~high]).round(0),
    )


def hide() -> None:
    """Exclude the long tokens from the probe: cosine between the pooled vector
    with and without them, per image, plus the attention maps for the ten."""
    model, _, _ = visual._load()
    head = copy.deepcopy(model.vision_model.head).float().cpu()
    d = dict(np.load(OUT, allow_pickle=True))
    n = len(d["names"])
    cos = np.zeros(n)
    cos_random = np.zeros(n)
    rng = np.random.default_rng(55)
    att_full = np.zeros((10, N.SIDE, N.SIDE), dtype=np.float32)
    att_hidden = np.zeros_like(att_full)
    full = np.ones((1, N.SIDE, N.SIDE), dtype=bool)
    for k in range(n):
        tok = d["tokens"][k].astype(np.float32)
        hi = d["high"][k]
        keep = (~hi).reshape(1, N.SIDE, N.SIDE)
        a = region_vectors(head, tok, full)[0]
        b = region_vectors(head, tok, keep)[0]
        cos[k] = a @ b / (np.linalg.norm(a) * np.linalg.norm(b))
        # the null: hide the same number of tokens drawn at random from the rest
        pick = rng.choice(np.where(~hi)[0], size=int(hi.sum()), replace=False)
        rk = np.ones(N.SIDE * N.SIDE, dtype=bool)
        rk[pick] = False
        c = region_vectors(head, tok, rk.reshape(1, N.SIDE, N.SIDE))[0]
        cos_random[k] = a @ c / (np.linalg.norm(a) * np.linalg.norm(c))
        if k < 10:
            att_full[k] = region_attention(head, tok, full[0])
            att_hidden[k] = region_attention(head, tok, keep[0])
    # the production vector, for the record: does the CPU float32 head match it
    prod = d["pooled"]
    np.savez_compressed(
        N.CACHE / "55_hide.npz",
        cos=cos,
        cos_random=cos_random,
        att_full=att_full,
        att_hidden=att_hidden,
    )
    print(
        "cosine with vs without the long tokens: median",
        np.median(cos).round(4),
        "min",
        cos.min().round(4),
        "| moved by more than 0.01:",
        int((cos < 0.99).sum()),
        "of",
        n,
    )
    print(
        "same count of random tokens hidden: median",
        np.median(cos_random).round(4),
        "min",
        cos_random.min().round(4),
    )
    share = np.array([att_full[k][d["high"][k].reshape(N.SIDE, N.SIDE)].sum() for k in range(10)])
    print(
        "share of the probe's attention on the long tokens, ten images:",
        np.round(share, 2).tolist(),
    )
    del prod


def registers() -> None:
    """arXiv 2506.08010 on this checkpoint: score every MLP neuron by its activation
    at the three long-token positions, then (a) zero the top neurons everywhere and
    (b) move their activation to an appended zero token, a test-time register."""
    model, processor, device = visual._load()
    vision = model.vision_model
    layers = vision.encoder.layers
    d = dict(np.load(OUT, allow_pickle=True))
    pos = np.where(d["high"].all(0))[0]  # the positions every image shares
    assert len(pos) == 3, pos
    names = list(N.IMAGES)
    pils = [Image.open(N.image_path(n)).convert("RGB") for n in names]
    px_all = [
        processor(images=[p], return_tensors="pt")["pixel_values"].to(device).to(torch.float16)
        for p in pils
    ]
    L, H = len(layers), layers[0].mlp.fc2.in_features

    # 1. score neurons: mean |activation| at the long positions minus elsewhere
    acts_at = np.zeros((L, H))
    acts_else = np.zeros((L, H))
    store: dict[int, torch.Tensor] = {}

    def logger(i):
        def pre(_m, inp):
            store[i] = inp[0].detach()[0]

        return pre

    hs = [layers[i].mlp.fc2.register_forward_pre_hook(logger(i)) for i in range(L)]
    with torch.no_grad():
        for px in px_all:
            vision(pixel_values=px)
            for i in range(L):
                a = store[i].float().abs()
                acts_at[i] += a[pos].mean(0).cpu().numpy()
                mask = torch.ones(a.shape[0], dtype=torch.bool)
                mask[pos] = False
                acts_else[i] += a[mask].mean(0).cpu().numpy()
    for h in hs:
        h.remove()
    acts_at /= len(px_all)
    acts_else /= len(px_all)
    score = acts_at - acts_else
    order = np.argsort(-score.ravel())
    top = [(int(o // H), int(o % H), float(score.ravel()[o])) for o in order[:40]]
    print("top neurons (layer, neuron, score):", [(a, b, round(c, 1)) for a, b, c in top[:12]])

    # 2. interventions, measured on the ten: norms along depth, pooled cosine, probe attention
    def measure(pre_hooks, emb_hook=None):
        grabbed: list[torch.Tensor] = []
        h_layers = [
            layer.register_forward_hook(
                lambda m, i, o: grabbed.append((o[0] if isinstance(o, tuple) else o).detach())
            )
            for layer in layers
        ]
        h_emb = vision.embeddings.register_forward_hook(emb_hook) if emb_hook else None
        norms_, cos_, att_ = [], [], []
        with torch.no_grad():
            for k, px in enumerate(px_all):
                grabbed.clear()
                o = vision(pixel_values=px)
                norms_.append(
                    torch.stack([g[0].float().norm(dim=-1) for g in grabbed]).cpu().numpy()
                )
                pv = o.pooler_output[0].float().cpu().numpy()
                ref = d["pooled"][k]
                cos_.append(float(pv @ ref / (np.linalg.norm(pv) * np.linalg.norm(ref))))
                hcpu = o.last_hidden_state.float().cpu()
                att_.append(hcpu[0].numpy().astype(np.float16))
        for h in h_layers:
            h.remove()
        if h_emb:
            h_emb.remove()
        return np.stack(norms_), np.array(cos_), np.stack(att_)

    results = {
        "positions": pos,
        "score": score.astype(np.float32),
        "top": np.array(top),
        "names": np.array(names),
    }
    for k in (3, 10, 30):
        chosen = top[:k]
        by_layer: dict[int, list[int]] = {}
        for layer, neuron, _ in chosen:
            by_layer.setdefault(layer, []).append(neuron)

        def ablate(idx):
            def pre(_m, inp):
                x = inp[0].clone()
                x[..., idx] = 0
                return (x,)

            return pre

        hs = [
            layers[i].mlp.fc2.register_forward_pre_hook(ablate(idx)) for i, idx in by_layer.items()
        ]
        n_, c_, t_ = measure(hs)
        for h in hs:
            h.remove()
        results[f"ablate{k}/norms"], results[f"ablate{k}/cos"], results[f"ablate{k}/tokens"] = (
            n_,
            c_,
            t_,
        )
        print(
            f"ablate top {k:2d}: last-layer max norm {n_[:, -1].max():7.1f}  tokens >150 per image {(n_[:, -1] > 150).sum(1).mean():.1f}  cosine to original median {np.median(c_):.4f} min {c_.min():.4f}"
        )

        # (b) shift: append one zero token; register neurons fire there and nowhere else
        def append(_m, _i, out):
            return torch.cat(
                [
                    out,
                    torch.zeros(out.shape[0], 1, out.shape[2], dtype=out.dtype, device=out.device),
                ],
                dim=1,
            )

        def shift(idx):
            def pre(_m, inp):
                x = inp[0].clone()
                v = x[:, :-1, idx]
                sign = torch.where(
                    v.abs().amax(dim=1, keepdim=True) == v.amax(dim=1, keepdim=True), 1.0, -1.0
                )
                x[:, -1, idx] = (v.abs().amax(dim=1) * sign[:, 0]).to(x.dtype)
                x[:, :-1, idx] = 0
                return (x,)

            return pre

        hs = [
            layers[i].mlp.fc2.register_forward_pre_hook(shift(idx)) for i, idx in by_layer.items()
        ]
        n_, c_, t_ = measure(hs, append)
        for h in hs:
            h.remove()
        results[f"shift{k}/norms"], results[f"shift{k}/cos"], results[f"shift{k}/tokens"] = (
            n_,
            c_,
            t_,
        )
        img_norms = n_[:, -1, :-1]
        print(
            f"shift  top {k:2d}: image tokens >150 per image {(img_norms > 150).sum(1).mean():.1f}  max {img_norms.max():7.1f}  register norm {n_[:, -1, -1].mean():7.1f}  cosine to original median {np.median(c_):.4f} min {c_.min():.4f}"
        )
    np.savez_compressed(N.CACHE / "55_registers.npz", **results)


def attention_after() -> None:
    """The probe's attention over the tokens the head receives, before and after
    the interventions, for figure 4: image part as 24 x 24, register share apart."""
    model, _, _ = visual._load()
    head = copy.deepcopy(model.vision_model.head).float().cpu()
    r = dict(np.load(N.CACHE / "55_registers.npz", allow_pickle=True))
    d = dict(np.load(OUT, allow_pickle=True))
    out: dict[str, np.ndarray] = {}
    sets = {
        "original": d["tokens"][:10],
        "ablate10": r["ablate10/tokens"],
        "shift30": r["shift30/tokens"],
    }
    for key, toks in sets.items():
        maps, reg = [], []
        for k in range(10):
            h = torch.as_tensor(toks[k].astype(np.float32))[None]
            with torch.no_grad():
                _, w = head.attention(
                    head.probe, h, h, need_weights=True, average_attn_weights=True
                )
            w = w[0, 0].numpy()
            maps.append(w[: N.SIDE * N.SIDE].reshape(N.SIDE, N.SIDE))
            reg.append(w[N.SIDE * N.SIDE :].sum() if w.shape[0] > N.SIDE * N.SIDE else 0.0)
        out[f"{key}/att"] = np.stack(maps)
        out[f"{key}/register_share"] = np.array(reg)
        print(
            f"{key:9} top patch {np.mean([m.max() for m in maps]):.3f}  top ten {np.mean([np.sort(m.ravel())[-10:].sum() for m in maps]):.0%}  register share {np.mean(reg):.0%}"
        )
    np.savez_compressed(N.CACHE / "55_attention.npz", **out)


if __name__ == "__main__":
    {"norms": norms, "hide": hide, "registers": registers, "attention": attention_after}[
        sys.argv[1]
    ]()
