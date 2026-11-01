#!/usr/bin/env python
"""Section 59, dissection D3: the summarizing heads, specimen run.

Registered in docs/design/encoder-anatomy/README.md before any call. With
last-token pooling one position carries the note; this asks which heads fill
it, how much of each head's attention goes to the sink at position 0, and how
far the note moves when one head is switched off.

READ-ONLY on Chroma and the vault. Reads the D1 harvest for neighbours.
Results and figures land in docs/assets/59-encoder-anatomy-d3/.

    uv run --extra lab python scripts/encoder_anatomy_d3.py specimen
    uv run --extra lab python scripts/encoder_anatomy_d3.py figures
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
SECTION = REPO / "docs" / "assets" / "59-encoder-anatomy-d3"
RESULTS = SECTION / "results.json"
STORE = Path(os.path.expanduser("~/.ytk/encoder-anatomy/d1-store.npz"))
MAP = Path(os.path.expanduser("~/.ytk/map.json"))

SPECIMEN_ID = "UZDiGooFs54"  # Welch Labs, AlexNet; held since section 42
SEED = 20261031
NULL_DRAWS = 100  # per block, registered
BATCH = 16  # one block's heads, or 16 null draws, in one forward pass
NEIGHBOURS = 10
MOVE_COS = 0.95  # prediction 2's "moves the vector" threshold


def _unit(X: np.ndarray) -> np.ndarray:
    return X / (np.linalg.norm(X, axis=-1, keepdims=True) + 1e-12)


def _model():
    import torch
    from sentence_transformers import SentenceTransformer

    from ytk import store

    cfg = store._EPOCHS["v2"]
    # eager attention is the only path that returns attention weights; the
    # vector it produces matches the SDPA path to 1e-7 (probe, 2026-10-31)
    m = SentenceTransformer(
        cfg["model"],
        revision=cfg["revision"],
        device="mps",
        model_kwargs={"torch_dtype": torch.float16, "attn_implementation": "eager"},
    )
    m.max_seq_length = cfg["max_seq"]
    return m


def _features(m, doc: str) -> dict:
    feats = m.tokenize([doc])
    return {k: v.to("mps") for k, v in feats.items() if hasattr(v, "to")}


def _last_vectors(am, feats: dict, batch: int) -> np.ndarray:
    """Unit last-token vectors for `batch` copies of the same document."""
    import torch

    ids = feats["input_ids"].expand(batch, -1)
    mask = feats["attention_mask"].expand(batch, -1)
    with torch.no_grad():
        out = am(input_ids=ids, attention_mask=mask)
    return _unit(out.last_hidden_state[:, -1].float().cpu().numpy())


def specimen() -> dict:
    import torch

    from ytk import store

    t_all = time.time()
    got = store._videos_collection().get(
        ids=[SPECIMEN_ID], include=["documents", "embeddings", "metadatas"]
    )
    doc = got["documents"][0]
    stored = _unit(np.asarray(got["embeddings"][0], float))
    title = store.meta_str(got["metadatas"][0], "title")
    m = _model()
    am = m[0].auto_model
    feats = _features(m, doc)
    n_tok = int(feats["input_ids"].shape[1])
    tokens = m.tokenizer.convert_ids_to_tokens(feats["input_ids"][0].tolist())
    cfg = am.config
    L, H, D = cfg.num_hidden_layers, cfg.num_attention_heads, cfg.head_dim

    # --- the attention pass: sink shares, content targets, and the hidden states for D2's thread
    with torch.no_grad():
        out = am(**feats, output_attentions=True, output_hidden_states=True)
    base = _unit(out.last_hidden_state[0, -1].float().cpu().numpy())
    calib = float(base @ stored)
    last_rows = (
        torch.stack([a[0, :, -1, :] for a in out.attentions]).float().cpu().numpy()
    )  # (L, H, T)
    sink = last_rows[:, :, 0]
    self_share = last_rows[:, :, -1]
    content = last_rows[:, :, 1:-1]
    # top content positions per head, for the words the summary is read from
    top_pos = np.argsort(content, axis=2)[:, :, ::-1][:, :, :5] + 1
    hidden = torch.stack([h[0, -1] for h in out.hidden_states]).float()  # (L+1, 1024), raw residual
    with torch.no_grad():
        normed = am.norm(hidden.to(am.norm.weight.dtype)).float().cpu().numpy()
    del out

    # --- neighbours: videos and memory docs from the D1 harvest, best part per doc, specimen excluded
    z = np.load(STORE)
    keys, kinds = z["keys"], z["kinds"]
    keep = np.flatnonzero((kinds != "seg") & (keys != f"vid::{SPECIMEN_ID}"))
    Xn = _unit(z["X"][keep].astype(np.float64))
    kn = keys[keep]
    uniq, inv = np.unique(kn, return_inverse=True)

    def neighbours(v: np.ndarray) -> list[str]:
        s = Xn @ v
        best = np.full(len(uniq), -np.inf)
        np.maximum.at(best, inv, s)
        return [str(uniq[j]) for j in np.argsort(best)[::-1][:NEIGHBOURS]]

    nb0 = neighbours(base)

    # --- ablation: zero one head's output before o_proj, sixteen rows per pass,
    # each row of the batch zeroing its own slice of the concatenated heads
    _active = {"layer": None, "slices": None}

    def run(layer: int, slices: list) -> np.ndarray:
        vecs = []
        for i in range(0, len(slices), BATCH):
            chunk = slices[i : i + BATCH]
            _active["layer"] = layer
            _active["slices"] = chunk
            vecs.append(_last_vectors(am, feats, len(chunk)))
        _active["slices"] = None
        return np.vstack(vecs)

    def make_hook(layer_idx: int):
        def hook(module, args):
            if _active["slices"] is None or _active["layer"] != layer_idx:
                return None
            x = args[0].clone()
            for b, sl in enumerate(_active["slices"]):
                x[b, :, sl] = 0
            return (x,)

        return hook

    for i, layer in enumerate(am.layers):
        layer.self_attn.o_proj.register_forward_pre_hook(make_hook(i))

    t0 = time.time()
    abl = np.zeros((L, H, 1024))
    for layer in range(L):
        slices = [slice(h * D, (h + 1) * D) for h in range(H)]
        abl[layer] = run(layer, slices)
        if layer == 0:
            per = time.time() - t0
            print(
                f"one block of {H} ablations: {per:.1f}s; ablation total about {per * L / 60:.1f} min, "
                f"null about {per * L * NULL_DRAWS / H / 60:.1f} min"
            )
    t_abl = time.time() - t0
    disp = 1 - abl @ base  # (L, H)
    changed = np.zeros((L, H), int)
    for layer in range(L):
        for h in range(H):
            changed[layer, h] = NEIGHBOURS - len(set(neighbours(abl[layer, h])) & set(nb0))

    # --- matched null: 128 random coordinates of the concatenated head outputs at that block
    rng = np.random.default_rng(SEED)
    t0 = time.time()
    null = np.zeros((L, NULL_DRAWS))
    for layer in range(L):
        draws = [np.sort(rng.choice(H * D, size=D, replace=False)) for _ in range(NULL_DRAWS)]
        null[layer] = 1 - run(layer, draws) @ base
    t_null = time.time() - t0
    null99 = np.percentile(null, 99, axis=1)

    # --- bars and predictions
    summarising = (changed >= 3) & (disp > null99[:, None])
    flat = disp.ravel()
    order = np.argsort(flat)[::-1]
    top5 = [(int(i // H), int(i % H)) for i in order[:5]]
    movers = int((flat > 1 - MOVE_COS).sum())
    from scipy.stats import spearmanr

    rho = float(spearmanr(disp.ravel(), sink.ravel()).correlation)
    late = sink[19:]  # blocks 20..28, one-indexed
    late_median = np.median(late, axis=1)
    top = top5[0]
    nb1 = neighbours(abl[top])
    words = [tokens[p] for p in top_pos[top]]

    out = {
        "specimen": {
            "id": SPECIMEN_ID,
            "title": title,
            "chars": len(doc),
            "tokens": n_tok,
            "first_token": tokens[0],
            "last_token": tokens[-1],
        },
        "calibration_cos": calib,
        "L": L,
        "H": H,
        "head_dim": D,
        "sink_median_by_block": [float(v) for v in np.median(sink, axis=1)],
        "sink_uniform_null": 1 / n_tok,
        "prediction_1": {
            "blocks_20_to_28_median_over_half": int((late_median > 0.5).sum()),
            "of": len(late_median),
            "medians": [float(v) for v in late_median],
            "holds": bool((late_median > 0.5).all()),
        },
        "prediction_2": {
            "movers_below_0_95": movers,
            "bar": 45,
            "top5": top5,
            "top5_in_last_8": bool(all(l >= L - 8 for l, _ in top5)),
            "holds": bool(movers < 45 and all(l >= L - 8 for l, _ in top5)),
        },
        "prediction_3": {"spearman_disp_vs_sink": rho, "bar": -0.3, "holds": bool(rho < -0.3)},
        "summarising_heads": [[int(l), int(h)] for l, h in zip(*np.nonzero(summarising))],
        "n_summarising": int(summarising.sum()),
        "top_head": {
            "block": top[0],
            "head": top[1],
            "displacement": float(disp[top]),
            "cos_after": float(1 - disp[top]),
            "sink_share": float(sink[top]),
            "neighbours_changed": int(changed[top]),
            "words": words,
            "null99_at_block": float(null99[top[0]]),
        },
        "neighbours_before": nb0,
        "neighbours_after_top_head": nb1,
        "null_draws_per_block": NULL_DRAWS,
        "seconds": {
            "ablation": round(t_abl),
            "null": round(t_null),
            "total": round(time.time() - t_all),
        },
    }
    SECTION.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        SECTION / "specimen.npz",
        sink=sink.astype(np.float32),
        self_share=self_share.astype(np.float32),
        disp=disp.astype(np.float32),
        changed=changed,
        null=null.astype(np.float32),
        top_pos=top_pos,
        tokens=np.array(tokens),
        base=base.astype(np.float32),
        abl_top=abl[top].astype(np.float32),
        hidden_last_token=hidden.cpu().numpy().astype(np.float32),
        hidden_normed=normed.astype(np.float32),
    )
    RESULTS.write_text(json.dumps(out, indent=1))
    print(f"calibration cos {calib:.5f}; {n_tok} tokens; ablation {t_abl:.0f}s, null {t_null:.0f}s")
    print(
        f"P1 late-block medians over 0.5: {out['prediction_1']['blocks_20_to_28_median_over_half']}/{len(late_median)}  {np.round(late_median, 2).tolist()}"
    )
    print(
        f"P2 movers below cos 0.95: {movers} (bar 45); top5 {top5} all in last 8: {out['prediction_2']['top5_in_last_8']}"
    )
    print(f"P3 spearman(disp, sink) = {rho:+.3f} (bar -0.3)")
    print(
        f"summarising heads (>=3 neighbours changed and above the block's null 99th pct): {out['n_summarising']}: {out['summarising_heads'][:20]}"
    )
    print(
        f"top head block {top[0] + 1} head {top[1]}: cos after {1 - disp[top]:.3f}, sink {sink[top]:.2f}, "
        f"neighbours changed {changed[top]}, words {words}"
    )
    return out


POP_N = 20
POP_TOKENS = (
    200,
    800,
)  # the specimen is 477; eager attention for all 28 blocks is quadratic in tokens
CONE_HEAD = (2, 6)  # the specimen's top head, block 3 head 6 one-indexed
POP_NPZ = SECTION / "population.npz"
POP_JSON = SECTION / "population.json"


def _install_hooks(am) -> dict:
    """One pre-hook per block on o_proj; rows of a batch zero their own slice
    of the concatenated heads when the shared state names that block."""
    active = {"layer": None, "slices": None}

    def make_hook(layer_idx: int):
        def hook(module, args):
            if active["slices"] is None or active["layer"] != layer_idx:
                return None
            x = args[0].clone()
            for b, sl in enumerate(active["slices"]):
                x[b, :, sl] = 0
            return (x,)

        return hook

    for i, layer in enumerate(am.layers):
        layer.self_attn.o_proj.register_forward_pre_hook(make_hook(i))
    return active


def _sample_population(m, rows: list[dict], rng) -> list[dict]:
    """Twenty notes, one per tag, tags spread evenly over the scorable list
    (count >= 6, ordered by count), inside the token window."""
    from collections import Counter

    counts = Counter(t for r in rows for t in r["tags"])
    keep = sorted([t for t, c in counts.items() if c >= 6], key=lambda t: -counts[t])
    for r in rows:
        r["n_tok"] = len(m.tokenizer(r["doc"])["input_ids"])
    eligible = [r for r in rows if POP_TOKENS[0] <= r["n_tok"] <= POP_TOKENS[1]]
    picks: list[dict] = []
    used_docs: set[str] = set()
    for j in np.linspace(0, len(keep) - 1, POP_N).round().astype(int):
        tag = keep[j]
        pool = [
            r
            for r in eligible
            if tag in r["tags"]
            and r["key"].split("#")[0] not in used_docs
            and r["key"] != f"vid::{SPECIMEN_ID}"
        ]
        if not pool:
            continue
        r = pool[rng.integers(len(pool))]
        r["tag"] = tag
        picks.append(r)
        used_docs.add(r["key"].split("#")[0])
    return picks


def population() -> None:
    import encoder_anatomy_d2 as d2
    import torch

    rng = np.random.default_rng(SEED + 1)
    m = _model()
    am = m[0].auto_model
    cfg = am.config
    L, H, D = cfg.num_hidden_layers, cfg.num_attention_heads, cfg.head_dim
    active = _install_hooks(am)
    picks = _sample_population(m, d2._rows(), rng)
    print(
        f"{len(picks)} notes: "
        + "; ".join(f"{p['tag']}: {p['name'][:40]} ({p['n_tok']} tok)" for p in picks),
        flush=True,
    )

    z = np.load(STORE)
    keys_all, kinds_all = z["keys"], z["kinds"]
    vm = np.flatnonzero(kinds_all != "seg")
    Xn = _unit(z["X"][vm].astype(np.float64))
    uniq, inv = np.unique(keys_all[vm], return_inverse=True)
    mu = np.load(REPO / "docs/assets/58-encoder-anatomy-d1/coords.npz")["mu"].astype(float)
    mu /= np.linalg.norm(mu)

    def neighbours(v: np.ndarray, exclude: str) -> list[str]:
        best = np.full(len(uniq), -np.inf)
        np.maximum.at(best, inv, Xn @ v)
        return [str(uniq[j]) for j in np.argsort(best)[::-1] if str(uniq[j]) != exclude][
            :NEIGHBOURS
        ]

    done = dict(np.load(POP_NPZ, allow_pickle=True)) if POP_NPZ.exists() else {}
    done_keys = list(done.get("keys", []))
    acc = {k: list(done[k]) for k in done if k != "keys"}
    meta = json.loads(POP_JSON.read_text()) if POP_JSON.exists() else {"notes": []}
    t_all = time.time()
    for ni, r in enumerate(picks):
        if r["key"] in done_keys:
            continue
        t0 = time.time()
        feats = _features(m, r["doc"])
        exclude = r["key"].split("#")[0]
        with torch.no_grad():
            out = am(**feats, output_attentions=True)
        base = _unit(out.last_hidden_state[0, -1].float().cpu().numpy())
        sink = torch.stack([a[0, :, -1, 0] for a in out.attentions]).float().cpu().numpy()
        del out
        calib = float(base @ _unit(r["emb"].astype(np.float64)))
        nb0 = neighbours(base, exclude)

        def run(layer: int, slices: list) -> np.ndarray:
            vecs = []
            for i in range(0, len(slices), BATCH):
                active["layer"], active["slices"] = layer, slices[i : i + BATCH]
                vecs.append(_last_vectors(am, feats, len(active["slices"])))
            active["slices"] = None
            return np.vstack(vecs)

        abl = np.zeros((L, H, 1024))
        for layer in range(L):
            abl[layer] = run(layer, [slice(h * D, (h + 1) * D) for h in range(H)])
        disp = 1 - abl @ base
        changed = np.array(
            [
                [NEIGHBOURS - len(set(neighbours(abl[l, h], exclude)) & set(nb0)) for h in range(H)]
                for l in range(L)
            ]
        )
        null = np.zeros((L, NULL_DRAWS))
        for layer in range(L):
            null[layer] = (
                1
                - run(
                    layer,
                    [np.sort(rng.choice(H * D, size=D, replace=False)) for _ in range(NULL_DRAWS)],
                )
                @ base
            )
        # the specimen's cone head, zeroed, with attention kept: does the sink survive it
        active["layer"], active["slices"] = (
            CONE_HEAD[0],
            [slice(CONE_HEAD[1] * D, (CONE_HEAD[1] + 1) * D)],
        )
        with torch.no_grad():
            out = am(**feats, output_attentions=True)
        active["slices"] = None
        sink_after = torch.stack([a[0, :, -1, 0] for a in out.attentions]).float().cpu().numpy()
        del out

        rec = {
            "sink": sink,
            "disp": disp,
            "changed": changed,
            "null99": np.percentile(null, 99, axis=1),
            "sink_after_cone_head": sink_after,
            "cone_cos_before": np.array(base @ mu),
            "cone_cos_after_cone_head": np.array(abl[CONE_HEAD] @ mu),
            "base": base,
            "abl_cone_head": abl[CONE_HEAD],
        }
        for k, v in rec.items():
            acc.setdefault(k, []).append(np.asarray(v, np.float32))
        done_keys.append(r["key"])
        np.savez_compressed(
            POP_NPZ, keys=np.array(done_keys), **{k: np.stack(v) for k, v in acc.items()}
        )
        top = np.unravel_index(int(np.argmax(disp)), disp.shape)
        meta["notes"].append(
            {
                "key": r["key"],
                "name": r["name"],
                "tag": r["tag"],
                "tokens": int(r["n_tok"]),
                "calibration_cos": calib,
                "top_head": [int(top[0]), int(top[1])],
                "top_disp": float(disp[top]),
                "cone_head_disp": float(disp[CONE_HEAD]),
                "cone_head_changed": int(changed[CONE_HEAD]),
                "cone_cos_before": float(base @ mu),
                "cone_cos_after": float(abl[CONE_HEAD] @ mu),
                "neighbours_before": nb0,
                "seconds": round(time.time() - t0),
            }
        )
        POP_JSON.write_text(json.dumps(meta, indent=1))
        print(
            f"[{len(done_keys)}/{len(picks)}] {r['name'][:40]}: {r['n_tok']} tok, calib {calib:.4f}, top head block {top[0] + 1} head {top[1]} "
            f"disp {disp[top]:.3f}; cone head disp {disp[CONE_HEAD]:.3f} changed {changed[CONE_HEAD]}, cone cos {base @ mu:.2f} -> {abl[CONE_HEAD] @ mu:.2f}; "
            f"{(time.time() - t0) / 60:.0f} min, {(time.time() - t_all) / 60:.0f} min so far",
            flush=True,
        )


def figures() -> None:
    import plot_assets as pa
    from matplotlib.patches import Rectangle

    pa.OUTDIR = SECTION
    r = json.loads(RESULTS.read_text())
    z = np.load(SECTION / "specimen.npz")
    sink, disp, changed, null = z["sink"], z["disp"], z["changed"], z["null"]
    L, H = sink.shape
    null99 = np.percentile(null, 99, axis=1)
    summ = (changed >= 3) & (disp > null99[:, None])
    sp, th = r["specimen"], r["top_head"]
    cmap = pa.saturated_magma()
    p1, p2, p3 = r["prediction_1"], r["prediction_2"], r["prediction_3"]

    fig, top = pa.figure(
        18,
        12.5,
        1,
        "section 59, D3: the summarizing heads, specimen",
        f"Which heads write the note: sink share and ablation displacement for every head of the encoder on {sp['title']}",
        meta=(
            f"{sp['tokens']} tokens, first {sp['first_token']!r}, last {sp['last_token']!r}; manual last-token pass matches the "
            f"shipped vector at cosine {r['calibration_cos']:.5f}. {L} blocks x {H} heads = {L * H} ablations, each zeroing one head's "
            f"128 outputs before o_proj; matched null {r['null_draws_per_block']} draws per block of 128 random coordinates. "
            f"P1 (late blocks' median sink share over 0.5): {p1['blocks_20_to_28_median_over_half']}/{p1['of']} blocks. "
            f"P2 (heads moving the vector below cosine 0.95): {p2['movers_below_0_95']} against a bar of 45, five largest all in the last 8 blocks: {p2['top5_in_last_8']}. "
            f"P3 (Spearman of displacement against sink share): {p3['spearman_disp_vs_sink']:+.2f} against a bar of -0.3. "
            f"Summarising heads by the bar: {r['n_summarising']}."
        ),
    )
    gs = fig.add_gridspec(
        2,
        3,
        left=pa.MARGIN,
        right=1 - pa.MARGIN,
        top=top,
        bottom=0.06,
        hspace=0.38,
        wspace=0.28,
        width_ratios=[1, 1, 1.1],
    )

    def grid(ax, M, title, vmax=None, label=""):
        pa.style_axes(ax)
        im = ax.imshow(M, cmap=cmap, aspect="auto", vmin=0, vmax=vmax, interpolation="nearest")
        ax.set_xlabel("head")
        ax.set_ylabel("block")
        ax.set_yticks(range(0, L, 3))
        ax.set_yticklabels([str(i + 1) for i in range(0, L, 3)])
        ax.set_xticks(range(0, H, 3))
        cb = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02)
        cb.ax.tick_params(colors=pa.MUTED, labelsize=pa.TICK_SIZE)
        cb.outline.set_edgecolor(pa.FRAME)
        cb.set_label(label, color=pa.MUTED, fontsize=pa.TICK_SIZE)
        cb.ax._is_colorbar = True
        pa.panel_title(ax, title, 48)
        return im

    # A: sink share grid
    ax = fig.add_subplot(gs[0, 0])
    grid(
        ax,
        sink,
        f"A. Share of the last position's attention on token 0, the sink (uniform would be {r['sink_uniform_null'] * 100:.2f}%)",
        1.0,
        "sink share",
    )
    # B: displacement grid, summarising heads outlined
    ax = fig.add_subplot(gs[0, 1])
    vmax = float(np.percentile(disp, 99.5))
    grid(
        ax,
        disp,
        "B. Displacement when the head is zeroed, 1 minus cosine to the shipped vector; cyan boxes are the summarising heads by the bar",
        vmax,
        "1 - cosine",
    )
    for l, h in zip(*np.nonzero(summ)):
        ax.add_patch(Rectangle((h - 0.5, l - 0.5), 1, 1, fill=False, edgecolor=pa.CYAN, lw=1.2))
    ax.add_patch(
        Rectangle(
            (th["head"] - 0.5, th["block"] - 0.5), 1, 1, fill=False, edgecolor=pa.GOLD, lw=2.0
        )
    )

    # C: displacement vs sink share, every head
    ax = fig.add_subplot(gs[0, 2])
    pa.style_axes(ax)
    blocks = np.repeat(np.arange(L), H)
    sc = ax.scatter(sink.ravel(), disp.ravel(), c=blocks, cmap=cmap, s=16, alpha=0.9, lw=0)
    ax.scatter(
        sink[summ],
        disp[summ],
        facecolors="none",
        edgecolors=pa.CYAN,
        s=60,
        lw=1.2,
        label="summarising heads",
    )
    ax.scatter(
        [th["sink_share"]],
        [th["displacement"]],
        facecolors="none",
        edgecolors=pa.GOLD,
        s=120,
        lw=2,
        label=f"top head: block {th['block'] + 1}, head {th['head']}",
    )
    ax.set_yscale("log")
    ax.set_xlabel("sink share")
    ax.set_ylabel("displacement, 1 - cosine (log)")
    cb = fig.colorbar(sc, ax=ax, fraction=0.04, pad=0.02)
    cb.ax.tick_params(colors=pa.MUTED, labelsize=pa.TICK_SIZE)
    cb.outline.set_edgecolor(pa.FRAME)
    cb.set_label("block (0-indexed)", color=pa.MUTED, fontsize=pa.TICK_SIZE)
    cb.ax._is_colorbar = True
    ax.legend(
        loc="lower left",
        fontsize=pa.TICK_SIZE,
        facecolor=pa.PANEL,
        edgecolor=pa.FRAME,
        labelcolor=pa.TEXT,
    )
    pa.panel_title(
        ax,
        f"C. Every head: do the heads that move the note avoid the sink? Spearman {p3['spearman_disp_vs_sink']:+.2f} (bar below -0.3)",
        52,
    )

    # D: sink share by block, median and quartiles, uniform null in DIM
    ax = fig.add_subplot(gs[1, 0])
    pa.style_axes(ax)
    x = np.arange(1, L + 1)
    q1, med, q3 = np.percentile(sink, [25, 50, 75], axis=1)
    ax.fill_between(x, q1, q3, color=pa.GOLD, alpha=0.3, lw=0, label="middle half of the 16 heads")
    ax.plot(x, med, color=pa.GOLD, lw=2, label="median head")
    ax.axhline(r["sink_uniform_null"], color=pa.DIM, lw=2.5, label="uniform attention")
    ax.axhline(0.5, color=pa.RED, lw=0.8, ls=":")
    ax.axvspan(20, 28, color=pa.DIM, alpha=0.35, lw=0)
    ax.text(20.2, 0.03, "P1 window: blocks 20 to 28", color=pa.RED, fontsize=pa.TICK_SIZE)
    ax.set_xlim(1, L)
    ax.set_ylim(0, 1.32)
    ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_xlabel("block")
    ax.set_ylabel("last position's share on token 0")
    ax.legend(
        loc="upper left",
        ncol=3,
        fontsize=pa.TICK_SIZE,
        facecolor=pa.PANEL,
        edgecolor=pa.FRAME,
        labelcolor=pa.TEXT,
    )
    pa.panel_title(
        ax,
        f"D. The sink across depth: nothing in blocks 1 to 3, then most heads park over half their mass on token 0 ({p1['blocks_20_to_28_median_over_half']}/{p1['of']} late blocks above 0.5)",
        56,
    )

    # E: the top head's displacement inside its block's null
    ax = fig.add_subplot(gs[1, 1])
    pa.style_axes(ax)
    b = th["block"]
    ax.hist(
        null[b],
        bins=25,
        color=pa.DIM,
        label=f"null at block {b + 1}: 128 random coordinates, {null.shape[1]} draws",
    )
    for h in range(H):
        ax.axvline(disp[b, h], color=pa.CYAN if summ[b, h] else pa.MUTED, lw=1.0, alpha=0.9)
    ax.axvline(
        th["displacement"],
        color=pa.GOLD,
        lw=2.5,
        label=f"head {th['head']}: {th['displacement']:.3f}, {th['neighbours_changed']} of 10 neighbours change",
    )
    ax.axvline(null99[b], color=pa.RED, lw=0.8, ls=":", label="null 99th percentile")
    ax.set_xscale("log")
    ax.set_xlabel("displacement, 1 - cosine (log)")
    ax.set_ylabel("draws")
    ax.legend(
        loc="upper left",
        fontsize=pa.TICK_SIZE - 0.5,
        facecolor=pa.PANEL,
        edgecolor=pa.FRAME,
        labelcolor=pa.TEXT,
    )
    pa.panel_title(
        ax,
        f"E. Block {b + 1}'s sixteen heads (thin lines) against its matched null; cyan ones pass the bar",
        50,
    )

    # F: where the note falls relative to the cone when the head is zeroed
    ax = fig.add_subplot(gs[1, 2])
    pa.style_axes(ax)
    zs = np.load(STORE)
    mu = np.load(REPO / "docs/assets/58-encoder-anatomy-d1/coords.npz")["mu"].astype(float)
    mu /= np.linalg.norm(mu)
    cos_all = _unit(zs["X"].astype(np.float64)) @ mu
    c0, c1 = float(z["base"].astype(float) @ mu), float(z["abl_top"].astype(float) @ mu)
    ax.hist(cos_all, bins=60, color=pa.DIM, label=f"every stored vector ({len(cos_all):,})")
    ax.axvline(c0, color=pa.GOLD, lw=2.5, label=f"the specimen as shipped: {c0:.2f}")
    ax.axvline(
        c1, color=pa.CYAN, lw=2.5, label=f"with block {b + 1} head {th['head']} zeroed: {c1:.2f}"
    )
    ax.set_xlabel("cosine to the cone's direction (the mean of all vectors)")
    ax.set_ylabel("vectors")
    ax.legend(
        loc="upper left",
        fontsize=pa.TICK_SIZE,
        facecolor=pa.PANEL,
        edgecolor=pa.FRAME,
        labelcolor=pa.TEXT,
    )
    kept = len(set(r["neighbours_before"]) & set(r["neighbours_after_top_head"]))
    pa.panel_title(
        ax,
        f"F. Where the note goes: cosine to the cone's direction, the specimen before and after the top head is zeroed; {kept} of 10 neighbours kept",
        56,
    )

    holds = sum(int(p["holds"]) for p in (p1, p2, p3))
    pa.verdict(
        fig,
        f"{holds} OF 3 PREDICTIONS HOLD; {r['n_summarising']} summarising heads by the bar; top head block {th['block'] + 1} head {th['head']} reads {', '.join(w.replace('Ġ', ' ').strip() for w in th['words'][:4])}",
    )
    pa.save(fig, "01-the-heads.png")


def population_figures() -> None:
    import plot_assets as pa
    from matplotlib.patches import Rectangle

    pa.OUTDIR = SECTION
    z = np.load(POP_NPZ)
    meta = json.loads(POP_JSON.read_text())["notes"]
    sink, disp, changed, null99 = z["sink"], z["disp"], z["changed"], z["null99"]
    sink_after = z["sink_after_cone_head"]
    before, after = z["cone_cos_before"], z["cone_cos_after_cone_head"]
    N, L, H = sink.shape
    cmap = pa.saturated_magma()
    bar_notes = int(np.ceil(0.75 * N))  # the registered 15 of 20
    hits = (changed >= 3).sum(0)  # notes on which each head moves 3 of the 10 neighbours
    real = hits >= bar_notes
    cone_l, cone_h = CONE_HEAD
    mu = np.load(REPO / "docs/assets/58-encoder-anatomy-d1/coords.npz")["mu"].astype(float)
    mu /= np.linalg.norm(mu)
    zs = np.load(STORE)
    cos_all = _unit(zs["X"].astype(np.float64)) @ mu
    tops = [tuple(m["top_head"]) for m in meta]
    top_is_cone = sum(t == CONE_HEAD for t in tops)

    fig, top = pa.figure(
        18,
        12.5,
        2,
        "section 59, D3: the summarizing heads, population",
        f"The same cuts on {N} notes drawn one per tag: is the sink the same, is the cone head the same head, and does any head pass the population bar",
        meta=(
            f"{N} notes, one from each of {N} tags spread over the {84} scorable ones, {POP_TOKENS[0]} to {POP_TOKENS[1]} tokens, "
            f"median {int(np.median([m['tokens'] for m in meta]))}; calibration cosine min {min(m['calibration_cos'] for m in meta):.4f}. "
            f"Per note: the attention pass, {L * H} single-head ablations, a matched null of {NULL_DRAWS} draws per block. "
            f"Population bar: a head counts when it moves at least 3 of the 10 neighbours on at least {bar_notes} of {N} notes; "
            f"heads passing: {int(real.sum())}. The specimen's cone head (block {cone_l + 1}, head {cone_h}) is the top head on "
            f"{top_is_cone} of {N} notes; zeroing it moves the note by a median of {np.median(disp[:, cone_l, cone_h]):.3f} and drops its "
            f"cosine to the cone from a median {np.median(before):.2f} to {np.median(after):.2f}."
        ),
    )
    # left margin widened for panel D's tag labels, the longest is 17 characters
    gs = fig.add_gridspec(
        2,
        3,
        left=pa.MARGIN + 0.035,
        right=1 - pa.MARGIN,
        top=top,
        bottom=0.06,
        hspace=0.38,
        wspace=0.28,
    )

    def grid(ax, M, title, vmax=None, label="", width=48):
        pa.style_axes(ax)
        im = ax.imshow(M, cmap=cmap, aspect="auto", vmin=0, vmax=vmax, interpolation="nearest")
        ax.set_xlabel("head")
        ax.set_ylabel("block")
        ax.set_yticks(range(0, L, 3))
        ax.set_yticklabels([str(i + 1) for i in range(0, L, 3)])
        ax.set_xticks(range(0, H, 3))
        cb = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02)
        cb.ax.tick_params(colors=pa.MUTED, labelsize=pa.TICK_SIZE)
        cb.outline.set_edgecolor(pa.FRAME)
        cb.set_label(label, color=pa.MUTED, fontsize=pa.TICK_SIZE)
        cb.ax._is_colorbar = True
        pa.panel_title(ax, title, width)

    ax = fig.add_subplot(gs[0, 0])
    grid(
        ax,
        sink.mean(0),
        f"A. Sink share, mean over the {N} notes; the specimen's grid is figure 01's panel A",
        1.0,
        "sink share",
    )
    ax = fig.add_subplot(gs[0, 1])
    grid(
        ax,
        np.median(disp, 0),
        "B. Displacement when the head is zeroed, median over notes; gold box is the specimen's cone head",
        float(np.percentile(np.median(disp, 0), 99.5)),
        "1 - cosine",
    )
    ax.add_patch(
        Rectangle((cone_h - 0.5, cone_l - 0.5), 1, 1, fill=False, edgecolor=pa.GOLD, lw=2.0)
    )
    ax = fig.add_subplot(gs[0, 2])
    grid(
        ax,
        hits,
        f"C. Notes on which the head moves 3 of 10 neighbours; cyan boxes reach the bar of {bar_notes} of {N}",
        N,
        "notes",
        52,
    )
    for l, h in zip(*np.nonzero(real)):
        ax.add_patch(Rectangle((h - 0.5, l - 0.5), 1, 1, fill=False, edgecolor=pa.CYAN, lw=1.4))

    # D: the cone head on every note, against each note's own null at that block
    ax = fig.add_subplot(gs[1, 0])
    pa.style_axes(ax)
    order = np.argsort(disp[:, cone_l, cone_h])[::-1]
    y = np.arange(N)
    ax.barh(
        y,
        disp[order, cone_l, cone_h],
        color=pa.GOLD,
        height=0.7,
        label=f"block {cone_l + 1} head {cone_h} zeroed",
    )
    ax.scatter(
        null99[order, cone_l],
        y,
        color=pa.DIM,
        s=30,
        marker="|",
        lw=2,
        label="that note's null, 99th percentile",
    )
    ax.scatter(
        [m["top_disp"] for m in np.array(meta, dtype=object)[order]],
        y,
        color=pa.CYAN,
        s=18,
        marker="D",
        label="the note's own top head",
    )
    ax.set_yticks(y)
    ax.set_yticklabels([meta[i]["tag"] for i in order], fontsize=pa.TICK_SIZE - 1)
    ax.set_xscale("log")
    ax.set_xlabel("displacement, 1 - cosine (log)")
    ax.invert_yaxis()
    ax.legend(
        loc="lower right",
        fontsize=pa.TICK_SIZE - 0.5,
        facecolor=pa.PANEL,
        edgecolor=pa.FRAME,
        labelcolor=pa.TEXT,
    )
    pa.panel_title(
        ax,
        f"D. The specimen's cone head on every note, one row per note (by tag): top head on {top_is_cone} of {N}",
        50,
    )

    # E: cosine to the cone, before and after, every note, on the corpus histogram
    ax = fig.add_subplot(gs[1, 1])
    pa.style_axes(ax)
    ax.hist(cos_all, bins=60, color=pa.DIM, label=f"every stored vector ({len(cos_all):,})")
    ax2 = ax.twinx()
    ax2.set_yticks([])
    for i in range(N):
        ax2.plot([before[i], after[i]], [i, i], color=pa.MUTED, lw=0.8)
    ax2.scatter(before, np.arange(N), color=pa.GOLD, s=22, zorder=5, label="as shipped")
    ax2.scatter(
        after,
        np.arange(N),
        color=pa.CYAN,
        s=22,
        zorder=5,
        label=f"block {cone_l + 1} head {cone_h} zeroed",
    )
    ax2.set_ylim(-1, N)
    ax.set_xlim(0.05, 1.0)  # the corpus ends at 0.72; the strip to the right holds the legend
    ax.set_xlabel("cosine to the cone's direction")
    ax.set_ylabel("vectors")
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(
        h1 + h2,
        l1 + l2,
        loc="upper right",
        fontsize=pa.TICK_SIZE,
        facecolor=pa.PANEL,
        edgecolor=pa.FRAME,
        labelcolor=pa.TEXT,
    )
    pa.panel_title(
        ax,
        f"E. Where each note goes when the cone head is zeroed: median cosine to the cone {np.median(before):.2f} to {np.median(after):.2f}",
        52,
    )

    # F: the sink with and without the cone head, median head per block, across notes
    ax = fig.add_subplot(gs[1, 2])
    pa.style_axes(ax)
    x = np.arange(1, L + 1)
    med_b = np.median(np.median(sink, 2), 0)
    med_a = np.median(np.median(sink_after, 2), 0)
    q1b, q3b = np.percentile(np.median(sink, 2), [25, 75], axis=0)
    ax.fill_between(x, q1b, q3b, color=pa.GOLD, alpha=0.25, lw=0)
    ax.plot(
        x,
        med_b,
        color=pa.GOLD,
        lw=2.2,
        label="median head, as shipped (band: middle half of notes)",
    )
    ax.plot(
        x,
        med_a,
        color=pa.CYAN,
        lw=2.2,
        ls="--",
        label=f"median head with block {cone_l + 1} head {cone_h} zeroed",
    )
    ax.axhline(0.5, color=pa.RED, lw=0.8, ls=":")
    ax.set_xlim(1, L)
    ax.set_ylim(0, 1.32)
    ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_xlabel("block")
    ax.set_ylabel("last position's share on token 0")
    ax.legend(
        loc="upper left",
        fontsize=pa.TICK_SIZE,
        facecolor=pa.PANEL,
        edgecolor=pa.FRAME,
        labelcolor=pa.TEXT,
    )
    pa.panel_title(
        ax,
        "F. Does the cone head write the sink: the sink across depth with and without it, over all notes",
        52,
    )
    pa.verdict(
        fig,
        f"{int(real.sum())} HEADS PASS THE POPULATION BAR; the specimen's cone head is the top head on {top_is_cone} of {N} notes "
        f"and the sink {'survives' if med_a[8:].mean() > 0.5 * med_b[8:].mean() else 'collapses'} without it",
    )
    pa.save(fig, "02-the-population.png")


TRACE_NPZ = SECTION / "trace.npz"


def _capture_hooks(am, layer_idx: int) -> dict:
    """Pre-hooks that keep block `layer_idx`'s o_proj input (every head's
    output at every position) and the raw residual entering the final norm."""
    got: dict = {}

    def keep_heads(module, args):
        got["heads"] = args[0][0].detach().float().cpu().numpy()

    def keep_final(module, args):
        got["final_raw"] = args[0][0].detach().float().cpu().numpy()

    am.layers[layer_idx].self_attn.o_proj.register_forward_pre_hook(keep_heads)
    am.norm.register_forward_pre_hook(keep_final)
    return got


def trace() -> None:
    """Follow block 3 head 6's write through the whole forward pass on the
    specimen: what it writes at every position, how much of the final vector
    is its own, where the two runs (with and without it) part, and whether
    position 0's massive activation exists without it. Then the same head's
    write on the 20 population notes, one pass each, for constancy."""
    import encoder_anatomy_d2 as d2
    import torch

    from ytk import store

    t_all = time.time()
    got = store._videos_collection().get(ids=[SPECIMEN_ID], include=["documents", "embeddings"])
    doc = got["documents"][0]
    stored = _unit(np.asarray(got["embeddings"][0], float))
    m = _model()
    am = m[0].auto_model
    cfg = am.config
    H, D = cfg.num_attention_heads, cfg.head_dim
    cl, ch = CONE_HEAD
    W_o = am.layers[cl].self_attn.o_proj.weight.detach().float().cpu().numpy()  # (1024, H*D)
    w_norm = am.norm.weight.detach().float().cpu().numpy()
    mu = np.load(REPO / "docs/assets/58-encoder-anatomy-d1/coords.npz")["mu"].astype(float)
    mu /= np.linalg.norm(mu)
    active = _install_hooks(am)
    cap = _capture_hooks(am, cl)
    feats = _features(m, doc)
    T = int(feats["input_ids"].shape[1])
    tokens = m.tokenizer.convert_ids_to_tokens(feats["input_ids"][0].tolist())

    def through_norm(x: np.ndarray) -> np.ndarray:
        """A residual direction as the final RMSNorm reads it: scaled by its weight."""
        return _unit(x * w_norm)

    def run(zero: bool):
        if zero:
            active["layer"], active["slices"] = cl, [slice(ch * D, (ch + 1) * D)]
        with torch.no_grad():
            out = am(**feats, output_attentions=True, output_hidden_states=True)
        active["slices"] = None
        # hidden_states[:-1] are the raw residual at depths 0..27; the last entry is
        # already through the final norm, so depth 28 raw comes from the norm's input
        raw = np.concatenate(
            [
                torch.stack(list(out.hidden_states[:-1])).float().cpu().numpy()[:, 0],
                cap["final_raw"][None],
            ]
        )
        sink = torch.stack([a[0, :, -1, 0] for a in out.attentions]).float().cpu().numpy()
        last = _unit(out.last_hidden_state[0, -1].float().cpu().numpy())
        heads = cap["heads"].copy()
        del out
        return raw, sink, last, heads

    rawA, sinkA, lastA, heads = run(False)
    rawB, sinkB, lastB, _ = run(True)
    calib = float(lastA @ stored)
    print(
        f"specimen: {T} tokens, calibration {calib:.5f}, two passes {time.time() - t_all:.0f} s",
        flush=True,
    )

    # every head of block cl, its write at every position, through o_proj
    writes = np.einsum("thd,ohd->hto", heads.reshape(T, H, D), W_o.reshape(1024, H, D))
    wnorm = np.linalg.norm(writes, axis=2)  # (H, T)
    mean_write = writes.mean(1)  # (H, 1024)
    cos_to_mean = np.einsum("hto,ho->ht", _unit(writes), _unit(mean_write))
    top_frac = np.zeros(H)
    for h in range(H):
        s = np.linalg.svd(writes[h], compute_uv=False)
        top_frac[h] = s[0] ** 2 / (s**2).sum()
    cos_write_mu = through_norm(writes) @ mu  # (H, T)
    final_raw = rawA[-1, -1]
    direct_cos_final = _unit(writes[:, -1]) @ _unit(final_raw)
    direct_cos_shipped = through_norm(writes[:, -1]) @ lastA
    direct_cos_mu = through_norm(writes[:, -1]) @ mu
    direct_norm_ratio = wnorm[:, -1] / np.linalg.norm(final_raw)

    # the dye: the two runs compared at every depth, last position and position 0
    cos_last = np.einsum("ko,ko->k", _unit(rawA[:, -1]), _unit(rawB[:, -1]))
    cos_pos0 = np.einsum("ko,ko->k", _unit(rawA[:, 0]), _unit(rawB[:, 0]))
    mu_last_A = through_norm(rawA[:, -1]) @ mu
    mu_last_B = through_norm(rawB[:, -1]) @ mu
    normA, normB = np.linalg.norm(rawA, axis=2), np.linalg.norm(rawB, axis=2)  # (L+1, T)

    # the same head on the population notes, one pass each
    rng = np.random.default_rng(SEED + 1)
    picks = _sample_population(m, d2._rows(), rng)
    sl = slice(ch * D, (ch + 1) * D)
    pop = {"mean": [], "last": [], "pos0": [], "top_frac": [], "first_token": [], "name": []}
    for r in picks:
        f = _features(m, r["doc"])
        with torch.no_grad():
            am(**f)
        w = cap["heads"][:, sl] @ W_o[:, sl].T
        s = np.linalg.svd(w, compute_uv=False)
        pop["mean"].append(_unit(w.mean(0)))
        pop["last"].append(_unit(w[-1]))
        pop["pos0"].append(_unit(w[0]))
        pop["top_frac"].append(float(s[0] ** 2 / (s**2).sum()))
        pop["first_token"].append(m.tokenizer.convert_ids_to_tokens([int(f["input_ids"][0, 0])])[0])
        pop["name"].append(r["name"])
    pop_mean = np.vstack(pop["mean"] + [_unit(mean_write[ch])])
    pop_last = np.vstack(pop["last"] + [_unit(writes[ch, -1])])
    pop_pos0 = np.vstack(pop["pos0"] + [_unit(writes[ch, 0])])

    def off_diag_median(X: np.ndarray) -> float:
        G = X @ X.T
        return float(np.median(G[~np.eye(len(X), dtype=bool)]))

    np.savez_compressed(
        TRACE_NPZ,
        tokens=np.array(tokens),
        write_norm=wnorm.astype(np.float32),
        cos_to_mean=cos_to_mean.astype(np.float32),
        top_frac=top_frac.astype(np.float32),
        cos_write_mu=cos_write_mu.astype(np.float32),
        cone_head_writes=writes[ch].astype(np.float16),
        direct=np.stack(
            [direct_cos_final, direct_cos_shipped, direct_cos_mu, direct_norm_ratio]
        ).astype(np.float32),
        cos_last=cos_last.astype(np.float32),
        cos_pos0=cos_pos0.astype(np.float32),
        mu_last_A=mu_last_A.astype(np.float32),
        mu_last_B=mu_last_B.astype(np.float32),
        norm_A=normA.astype(np.float32),
        norm_B=normB.astype(np.float32),
        sink_A=sinkA.astype(np.float32),
        sink_B=sinkB.astype(np.float32),
        pop_mean=pop_mean.astype(np.float32),
        pop_last=pop_last.astype(np.float32),
        pop_pos0=pop_pos0.astype(np.float32),
        pop_top_frac=np.array(pop["top_frac"], np.float32),
        pop_first_token=np.array(pop["first_token"]),
        pop_name=np.array(pop["name"]),
    )
    others = [h for h in range(H) if h != ch]
    part = int(np.argmax(cos_last < 0.95)) if (cos_last < 0.95).any() else -1
    rec = {
        "tokens": T,
        "first_token": tokens[0],
        "calibration_cos": calib,
        "cone_head": {
            "write_norm_pos0": float(wnorm[ch, 0]),
            "write_norm_last": float(wnorm[ch, -1]),
            "write_norm_median": float(np.median(wnorm[ch])),
            "other_heads_write_norm_median": float(np.median(wnorm[others])),
            "cos_to_mean_median": float(np.median(cos_to_mean[ch])),
            "cos_to_mean_min": float(cos_to_mean[ch].min()),
            "other_heads_cos_to_mean_median": float(np.median(cos_to_mean[others])),
            "top_singular_fraction": float(top_frac[ch]),
            "other_heads_top_singular_fraction_median": float(np.median(top_frac[others])),
            "cos_write_mu_median": float(np.median(cos_write_mu[ch])),
            "other_heads_cos_write_mu_median": float(np.median(cos_write_mu[others])),
            "direct_cos_final_raw": float(direct_cos_final[ch]),
            "direct_cos_shipped": float(direct_cos_shipped[ch]),
            "direct_cos_mu": float(direct_cos_mu[ch]),
            "direct_norm_ratio": float(direct_norm_ratio[ch]),
            "other_heads_direct_cos_shipped_median": float(np.median(direct_cos_shipped[others])),
        },
        "dye": {
            "cos_last_by_depth": [round(float(x), 4) for x in cos_last],
            "cos_pos0_by_depth": [round(float(x), 4) for x in cos_pos0],
            "first_depth_last_below_0_95": part,
            "mu_last_by_depth_as_shipped": [round(float(x), 3) for x in mu_last_A],
            "mu_last_by_depth_head_zeroed": [round(float(x), 3) for x in mu_last_B],
        },
        "massive": {
            "pos0_norm_by_depth_as_shipped": [round(float(x), 1) for x in normA[:, 0]],
            "pos0_norm_by_depth_head_zeroed": [round(float(x), 1) for x in normB[:, 0]],
            "median_norm_by_depth_as_shipped": [round(float(x), 1) for x in np.median(normA, 1)],
            "argmax_norm_position_by_depth_as_shipped": [int(x) for x in normA.argmax(1)],
            "argmax_norm_position_by_depth_head_zeroed": [int(x) for x in normB.argmax(1)],
        },
        "sink": {
            "median_head_by_block_as_shipped": [round(float(x), 3) for x in np.median(sinkA, 1)],
            "median_head_by_block_head_zeroed": [round(float(x), 3) for x in np.median(sinkB, 1)],
        },
        "population": {
            "notes": len(picks),
            "mean_write_cos_between_notes_median": off_diag_median(pop_mean),
            "last_write_cos_between_notes_median": off_diag_median(pop_last),
            "pos0_write_cos_between_notes_median": off_diag_median(pop_pos0),
            "top_singular_fraction_median": float(np.median(pop["top_frac"])),
            "first_tokens": pop["first_token"],
        },
        "seconds": round(time.time() - t_all),
    }
    d = json.loads(RESULTS.read_text())
    d["trace"] = rec
    RESULTS.write_text(json.dumps(d, indent=1))
    print(
        json.dumps({k: v for k, v in rec.items() if k not in ("dye", "massive", "sink")}, indent=1)
    )
    print("cos(A,B) last by depth", np.round(cos_last, 3))
    print("cos to mu, last, A", np.round(mu_last_A, 2))
    print("cos to mu, last, B", np.round(mu_last_B, 2))
    print("pos0 norm A", np.round(normA[:, 0], 0))
    print("pos0 norm B", np.round(normB[:, 0], 0))
    print("median norm A", np.round(np.median(normA, 1), 0))
    print("argmax pos A", normA.argmax(1), "B", normB.argmax(1))
    print("sink median A", np.round(np.median(sinkA, 1), 2))
    print("sink median B", np.round(np.median(sinkB, 1), 2))
    print(f"{time.time() - t_all:.0f} s", flush=True)


def trace_figure() -> None:
    import plot_assets as pa

    pa.OUTDIR = SECTION
    z = np.load(TRACE_NPZ)
    rec = json.loads(RESULTS.read_text())["trace"]
    cl, ch = CONE_HEAD
    wn = z["write_norm"]
    H, T = wn.shape
    norm_A, norm_B = z["norm_A"], z["norm_B"]
    depths = np.arange(norm_A.shape[0])
    cos_last, cos_pos0 = z["cos_last"], z["cos_pos0"]
    mu_A, mu_B = z["mu_last_A"], z["mu_last_B"]
    sink_A, sink_B = np.median(z["sink_A"], 1), np.median(z["sink_B"], 1)
    pop_pos0 = z["pop_pos0"]
    n_pop = len(pop_pos0)
    others = [h for h in range(H) if h != ch]
    c = rec["cone_head"]
    p = rec["population"]
    legend = {
        "facecolor": pa.PANEL,
        "edgecolor": pa.FRAME,
        "labelcolor": pa.TEXT,
        "fontsize": pa.TICK_SIZE,
    }

    fig, top = pa.figure(
        18,
        12.5,
        3,
        "section 59, D3: the cone head traced",
        "What the cone head writes at every position, whether it is the same vector on every note, and what the other 25 blocks do with it",
        meta=(
            f"The specimen, {rec['tokens']} tokens, calibration {rec['calibration_cos']:.5f}; two passes with every head's output in block {cl + 1} and the residual at every depth kept, "
            f"then one pass on each of the {p['notes']} population notes. The head's write has norm {c['write_norm_pos0']:.1f} at position 0 and a median of {c['write_norm_median']:.2f} elsewhere "
            f"(the other 15 heads of the block: median {c['other_heads_write_norm_median']:.2f}). Its own write at the last position is {c['direct_norm_ratio'] * 100:.1f}% of the final residual's norm, "
            f"cosine {c['direct_cos_shipped']:.3f} to the shipped vector and {c['direct_cos_mu']:.3f} to the cone: the direct share is nil. Constancy over content positions: top direction holds "
            f"{c['top_singular_fraction']:.0%} of the write's variance (other heads' median {c['other_heads_top_singular_fraction_median']:.0%}); across notes the mean write agrees at cosine "
            f"{p['mean_write_cos_between_notes_median']:.2f} and the position-0 write at {p['pos0_write_cos_between_notes_median']:.3f}, with first tokens as different as "
            f"{', '.join(repr(t) for t in sorted(set(p['first_tokens']))[:6])}."
        ),
    )
    gs = fig.add_gridspec(
        2, 3, left=pa.MARGIN, right=1 - pa.MARGIN, top=top, bottom=0.06, hspace=0.38, wspace=0.26
    )

    # A: the head's write, position by position, against its block
    ax = fig.add_subplot(gs[0, 0])
    pa.style_axes(ax)
    x = np.arange(T)
    for h in others:
        ax.plot(x, wn[h], color=pa.DIM, lw=0.7)
    ax.plot(x, wn[ch], color=pa.GOLD, lw=1.4, label=f"block {cl + 1} head {ch}")
    ax.plot([], [], color=pa.DIM, lw=0.7, label="the block's other 15 heads")
    ax.scatter([0], [wn[ch, 0]], color=pa.GOLD, s=40, zorder=5)
    ax.annotate(
        f"position 0: {wn[ch, 0]:.0f}",
        (0, wn[ch, 0]),
        xytext=(40, wn[ch, 0] * 0.9),
        color=pa.GOLD,
        fontsize=pa.TICK_SIZE,
        va="top",
    )
    ax.set_yscale("log")
    ax.set_xlim(-5, T)
    ax.set_xlabel("position in the note")
    ax.set_ylabel("norm of the head's write (log)")
    ax.legend(loc="upper right", **legend)
    pa.panel_title(
        ax,
        f"A. What the head writes at each position: a vector {wn[ch, 0] / np.median(wn[ch]):.0f}x its usual size at position 0, ordinary elsewhere",
        50,
    )

    # B: the massive activation at position 0, with and without the head
    ax = fig.add_subplot(gs[0, 1])
    pa.style_axes(ax)
    ax.plot(depths, np.median(norm_A, 1), color=pa.DIM, lw=1.6, label="median position, as shipped")
    ax.plot(depths, norm_A[:, 0], color=pa.GOLD, lw=2.2, label="position 0, as shipped")
    ax.plot(
        depths,
        norm_B[:, 0],
        color=pa.CYAN,
        lw=2.2,
        ls="--",
        label=f"position 0, block {cl + 1} head {ch} zeroed",
    )
    ax.axvline(cl + 1, color=pa.MUTED, lw=0.8, ls=":")
    ax.set_yscale("log")
    ax.set_xlim(0, depths[-1])
    ax.set_xlabel("depth (0 = token table, k = after block k)")
    ax.set_ylabel("residual norm at the position (log)")
    ax.legend(loc="lower right", **legend)
    pa.panel_title(
        ax,
        f"B. The sink's birth: position 0's residual is {norm_A[cl + 1, 0]:,.0f} after block {cl + 1} as shipped and {norm_B[cl + 1, 0]:.0f} without the head",
        50,
    )

    # C: the head's write across notes, position 0 against the content positions
    ax = fig.add_subplot(gs[0, 2])
    pa.style_axes(ax)
    off = ~np.eye(n_pop, dtype=bool)
    bins = np.linspace(-0.2, 1.0, 61)
    for X, color, label in (
        (z["pop_mean"], pa.MUTED, "mean write over the note's positions"),
        (z["pop_last"], pa.CYAN, "write at the last position"),
        (pop_pos0, pa.GOLD, "write at position 0"),
    ):
        ax.hist((X @ X.T)[off], bins=bins, color=color, alpha=0.85, label=label)
    ax.set_xlabel(f"cosine between two notes' writes ({n_pop} notes, every pair)")
    ax.set_ylabel("pairs")
    ax.legend(loc="upper left", **legend)
    pa.panel_title(
        ax,
        f"C. The same vector on every note at position 0 (median cosine {p['pos0_write_cos_between_notes_median']:.3f}, first tokens all different); the content writes agree at {p['mean_write_cos_between_notes_median']:.2f}",
        50,
    )

    # D: the dye, the two runs compared at every depth
    ax = fig.add_subplot(gs[1, 0])
    pa.style_axes(ax)
    ax.plot(
        depths, cos_last, color=pa.GOLD, lw=2.2, label="last position (the one the pooling reads)"
    )
    ax.plot(depths, cos_pos0, color=pa.CYAN, lw=2.2, ls="--", label="position 0")
    ax.axvline(cl + 1, color=pa.MUTED, lw=0.8, ls=":")
    ax.set_xlim(0, depths[-1])
    ax.set_ylim(-0.05, 1.05)
    ax.set_xlabel("depth")
    ax.set_ylabel("cosine, as shipped vs head zeroed")
    ax.legend(loc="upper right", **legend)
    pa.panel_title(
        ax,
        f"D. The dye downstream: cosine between the two runs' residual at every depth; the last position parts at depth {rec['dye']['first_depth_last_below_0_95']} and ends at {cos_last[-1]:.2f}",
        50,
    )

    # E: the cone deposited late
    ax = fig.add_subplot(gs[1, 1])
    pa.style_axes(ax)
    late = int(np.argmax(mu_A > 0.1))
    ax.axvspan(late, depths[-1], color=pa.GOLD, alpha=0.08, lw=0)
    ax.plot(depths, mu_A, color=pa.GOLD, lw=2.2, label="as shipped")
    ax.plot(depths, mu_B, color=pa.CYAN, lw=2.2, ls="--", label=f"block {cl + 1} head {ch} zeroed")
    ax.axhline(mu_A[-1], color=pa.MUTED, lw=0.8, ls=":")
    ax.set_xlim(0, depths[-1])
    ax.set_ylim(-0.1, 0.7)
    ax.set_xlabel("depth")
    ax.set_ylabel("last position's cosine to the cone's direction")
    ax.legend(loc="upper left", **legend)
    pa.panel_title(
        ax,
        f"E. Where the cone enters the note: the last position's cosine to the shared direction is under 0.1 through depth {late - 1}, then climbs to {mu_A[-1]:.2f}; without the head it ends at {mu_B[-1]:.2f}",
        50,
    )

    # F: the sink on the specimen with and without the head
    ax = fig.add_subplot(gs[1, 2])
    pa.style_axes(ax)
    blocks = np.arange(1, len(sink_A) + 1)
    ax.plot(blocks, sink_A, color=pa.GOLD, lw=2.2, label="median head, as shipped")
    ax.plot(
        blocks,
        sink_B,
        color=pa.CYAN,
        lw=2.2,
        ls="--",
        label=f"median head, block {cl + 1} head {ch} zeroed",
    )
    ax.axhline(0.5, color=pa.RED, lw=0.8, ls=":")
    ax.set_xlim(1, blocks[-1])
    ax.set_ylim(0, 1.25)
    ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_xlabel("block")
    ax.set_ylabel("last position's share on token 0")
    ax.legend(loc="upper left", **legend)
    pa.panel_title(
        ax,
        "F. The sink on the specimen, with and without the head: the later heads park on position 0 only when the massive activation is there",
        50,
    )
    pa.verdict(
        fig,
        "A FIXED VECTOR AT POSITION 0 ON EVERY NOTE; without it no massive activation, no sink, and no cone in the last position",
    )
    pa.save(fig, "03-the-trace.png")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "specimen"
    {
        "specimen": specimen,
        "population": population,
        "figures": figures,
        "population_figures": population_figures,
        "trace": trace,
        "trace_figure": trace_figure,
    }[cmd]()
