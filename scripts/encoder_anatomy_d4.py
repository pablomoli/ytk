#!/usr/bin/env python
"""Section 61, dissection D4: the register, label or bias.

Registered in docs/design/encoder-anatomy/README.md on 2026-11-08 before any
call. Block 3 head 6 writes one fixed vector at position 0 on every note (59.4);
this asks whether that register is a label the late heads retrieve, so the
cone would carry meaning, or a bias the model needs only for the sink.

READ-ONLY on Chroma and the vault. Reads the D1 store harvest, rung A's and
rung B's depth harvests, and section 58's cone. Results and figures land in
docs/assets/61-encoder-anatomy-d4/.

    uv run --extra lab python scripts/encoder_anatomy_d4.py tag      # reading 1, no model
    uv run --extra lab python scripts/encoder_anatomy_d4.py valley   # reading 2, 42 passes
    uv run --extra lab python scripts/encoder_anatomy_d4.py split    # reading 3, 84 + null passes
    uv run --extra lab python scripts/encoder_anatomy_d4.py tag_figure | valley_figure | split_figure
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
SECTION = REPO / "docs" / "assets" / "61-encoder-anatomy-d4"
RESULTS = SECTION / "results.json"
HARVEST = Path(os.path.expanduser("~/.ytk/encoder-anatomy"))
STORE = HARVEST / "d1-store.npz"
LAYERS = HARVEST / "d2-layers.npz"
FROZEN = HARVEST / "d2-frozen.npz"
CONE = REPO / "docs/assets/58-encoder-anatomy-d1/coords.npz"
POP_NPZ = REPO / "docs/assets/59-encoder-anatomy-d3/population.npz"
POP_JSON = REPO / "docs/assets/59-encoder-anatomy-d3/population.json"
TAG_NPZ = SECTION / "tag.npz"
VALLEY_NPZ = SECTION / "valley.npz"
SPLIT_NPZ = SECTION / "split.npz"

SPECIMEN_ID = "UZDiGooFs54"
SEED = 20261108
CONE_HEAD = (2, 6)  # block 3 head 6 one-indexed, as in D3
BUCKETS = ("vid", "mem", "seg")
BUCKET_NAMES = {"vid": "videos", "mem": "memories", "seg": "segments", "query": "queries"}
TOKEN_EDGES = (0, 48, 96, 192, 384, 768, 1536, 100_000)
FINE_EDGES = (0, 48, 64, 96, 128, 192, 256, 384, 512, 768, 1024, 1536, 100_000)
RANDOM_DIRECTIONS = 300
MIN_PER_BIN = 10
SHUFFLES = 1000
MIN_NOTES = 6  # section 10's scorable-tag floor
NEIGHBOURS = 10
NULL_SPECIMEN = 100
NULL_POP = 20
CONDITIONS = ("pos0", "content", "all", "swap")


def _unit(X: np.ndarray) -> np.ndarray:
    return X / (np.linalg.norm(X, axis=-1, keepdims=True) + 1e-12)


def _mu() -> np.ndarray:
    mu = np.load(CONE)["mu"].astype(np.float64)
    return mu / np.linalg.norm(mu)


def _load_results() -> dict:
    return json.loads(RESULTS.read_text()) if RESULTS.exists() else {}


def _save_results(d: dict) -> None:
    SECTION.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(d, indent=1))


def _erank(M: np.ndarray) -> float:
    """Entropy effective rank (Roy and Vetterli) of the rows of M."""
    s = np.linalg.svd(M, compute_uv=False)
    p = s / s.sum()
    p = p[p > 0]
    return float(np.exp(-(p * np.log(p)).sum()))


# ---------------------------------------------------------------- reading 1


def _bin_index(n_tok: np.ndarray) -> np.ndarray:
    return np.digitize(n_tok, TOKEN_EDGES[1:-1])


def _matched_stats(cos: np.ndarray, kinds: np.ndarray, bins: np.ndarray, X: np.ndarray | None):
    """Per token bin with every bucket present: each bucket's median cosine to
    the cone, and the pairwise cosine of the buckets' mean directions. The
    headline statistic is the mean over bins of the spread of medians."""
    per_bin = []
    for b in np.unique(bins):
        sel = bins == b
        counts = {k: int((kinds[sel] == k).sum()) for k in BUCKETS}
        if min(counts.values()) < MIN_PER_BIN:
            continue
        med = {k: float(np.median(cos[sel & (kinds == k)])) for k in BUCKETS}
        rec = {"bin": int(b), "counts": counts, "medians": med}
        if X is not None:
            means = {k: _unit(X[sel & (kinds == k)].mean(0)) for k in BUCKETS}
            rec["mean_cos"] = {
                f"{a}-{c}": float(means[a] @ means[c])
                for i, a in enumerate(BUCKETS)
                for c in BUCKETS[i + 1 :]
            }
        per_bin.append(rec)
    spread = float(
        np.mean([max(r["medians"].values()) - min(r["medians"].values()) for r in per_bin])
    )
    return per_bin, spread


def _shuffled_spread(cos, kinds, bins, rng, draws: int) -> np.ndarray:
    """The matched spread with bucket labels shuffled inside each token bin."""
    out = np.zeros(draws)
    usable = [
        b
        for b in np.unique(bins)
        if min(int(((bins == b) & (kinds == k)).sum()) for k in BUCKETS) >= MIN_PER_BIN
    ]
    idx = {b: np.flatnonzero(bins == b) for b in usable}
    for d in range(draws):
        spreads = []
        for b in usable:
            sel = idx[b]
            k = kinds[sel][rng.permutation(len(sel))]
            meds = [np.median(cos[sel][k == kk]) for kk in BUCKETS]
            spreads.append(max(meds) - min(meds))
        out[d] = np.mean(spreads)
    return out


def _pairwise_matched(cos, kinds, n_tok, rng, draws: int) -> dict:
    """Two buckets at a time inside finer token bins, so each pair is matched
    where the two overlap rather than where all three do: the mean over bins
    of the difference of medians, with labels shuffled inside bins as the null."""
    bins = np.digitize(n_tok, FINE_EDGES[1:-1])
    out = {}
    for i, a in enumerate(BUCKETS):
        for c in BUCKETS[i + 1 :]:
            rows = []
            for b in np.unique(bins):
                sa = np.flatnonzero((bins == b) & (kinds == a))
                sb = np.flatnonzero((bins == b) & (kinds == c))
                if len(sa) >= MIN_PER_BIN and len(sb) >= MIN_PER_BIN:
                    rows.append((int(b), sa, sb))
            if not rows:
                continue
            diffs = [float(np.median(cos[sa]) - np.median(cos[sb])) for _, sa, sb in rows]
            null = np.zeros(draws)
            for t in range(draws):
                vals = []
                for _, sa, sb in rows:
                    pool = np.concatenate([sa, sb])
                    perm = pool[rng.permutation(len(pool))]
                    vals.append(np.median(cos[perm[: len(sa)]]) - np.median(cos[perm[len(sa) :]]))
                null[t] = np.mean(np.abs(vals))
            out[f"{a}-{c}"] = {
                "bins": [
                    {
                        "from_tokens": FINE_EDGES[b],
                        "n": [len(sa), len(sb)],
                        "medians": [float(np.median(cos[sa])), float(np.median(cos[sb]))],
                    }
                    for b, sa, sb in rows
                ],
                "mean_abs_diff": float(np.mean(np.abs(diffs))),
                "mean_diff": float(np.mean(diffs)),
                "null_99": float(np.percentile(null, 99)),
                "null_median": float(np.median(null)),
            }
    return out


def _tag_spread_ratio(cos_dir: np.ndarray, members: dict) -> float:
    """Spread of per-tag medians of a projection, relative to the projection's
    spread over notes: how much a direction separates the tags."""
    return float(np.std([np.median(cos_dir[m]) for m in members.values()]) / cos_dir.std())


def tag() -> None:
    """Reading 1: the cone's direction against bucket, length and tag."""
    t0 = time.time()
    rng = np.random.default_rng(SEED)
    mu = _mu()

    # the production store at the output: every vector, by bucket
    zs = np.load(STORE)
    Xs = _unit(zs["X"].astype(np.float64))
    ks, keys_s = zs["kinds"], zs["keys"]
    cos_store = Xs @ mu
    store_medians = {k: float(np.median(cos_store[ks == k])) for k in BUCKETS}
    print(
        f"store: {len(Xs)} vectors; median cosine to the cone by bucket "
        + ", ".join(f"{BUCKET_NAMES[k]} {v:.3f}" for k, v in store_medians.items()),
        flush=True,
    )

    # rung B's frozen harvest: every depth, with bucket and token count
    zf = np.load(FROZEN)
    kinds, n_tok, keys_f = zf["kinds"], zf["n_tok"], zf["keys"]
    last = zf["last"]  # (n, 29, 1024) float16, unit, through the final norm
    n, L1, d = last.shape
    cos_depth = np.zeros((L1, n), np.float32)
    for k in range(L1):
        cos_depth[k] = last[:, k].astype(np.float32) @ mu.astype(np.float32)
    X_out = last[:, -1].astype(np.float64)
    docs = kinds != "query"
    cos_out = cos_depth[-1].astype(np.float64)

    # cross-check: the harvest's output against the store, by bucket and by matched key
    frozen_medians = {k: float(np.median(cos_out[kinds == k])) for k in BUCKETS}
    store_idx = {str(k): i for i, k in enumerate(keys_s)}
    matched = [(i, store_idx[str(k)]) for i, k in enumerate(keys_f) if str(k) in store_idx]
    if matched:
        fi, si = map(np.array, zip(*matched))
        match_cos = np.einsum("ij,ij->i", _unit(X_out[fi]), Xs[si])
    else:
        match_cos = np.array([])
    print(
        f"frozen: {int(docs.sum())} documents + {int((~docs).sum())} queries; output medians by bucket "
        + ", ".join(f"{BUCKET_NAMES[k]} {v:.3f}" for k, v in frozen_medians.items())
        + f"; {len(matched)} keys matched to the store at median cosine "
        + (f"{np.median(match_cos):.5f} (min {match_cos.min():.4f})" if len(matched) else "n/a"),
        flush=True,
    )

    # length: the confound, then the matched comparison
    bins = _bin_index(n_tok)
    occupancy = {
        f"{TOKEN_EDGES[b]}-{TOKEN_EDGES[b + 1]}": {
            k: int(((bins == b) & (kinds == k)).sum()) for k in BUCKETS
        }
        for b in range(len(TOKEN_EDGES) - 1)
    }
    from scipy.stats import spearmanr

    rho_len = {
        k: float(spearmanr(n_tok[kinds == k], cos_out[kinds == k]).correlation) for k in BUCKETS
    }
    rho_len["all"] = float(spearmanr(n_tok[docs], cos_out[docs]).correlation)
    per_bin, spread = _matched_stats(cos_out[docs], kinds[docs], bins[docs], X_out[docs])
    null = _shuffled_spread(cos_out[docs], kinds[docs], bins[docs], rng, SHUFFLES)
    null99 = float(np.percentile(null, 99))
    unmatched_spread = max(frozen_medians.values()) - min(frozen_medians.values())
    # bucket mean directions, whole buckets and length-matched
    means = {k: _unit(X_out[kinds == k].mean(0)) for k in BUCKETS}
    pairs = [(a, c) for i, a in enumerate(BUCKETS) for c in BUCKETS[i + 1 :]]
    mean_cos_whole = {f"{a}-{c}": float(means[a] @ means[c]) for a, c in pairs}
    mean_cos_matched = {
        f"{a}-{c}": float(np.median([r["mean_cos"][f"{a}-{c}"] for r in per_bin])) for a, c in pairs
    }
    # null for the mean directions: shuffled labels inside bins, the smallest pairwise cosine
    null_mean_cos = np.zeros(200)
    usable = [r["bin"] for r in per_bin]
    kd, bd = kinds[docs], bins[docs]
    for t in range(200):
        vals = []
        for b in usable:
            sel = np.flatnonzero(bd == b)
            kk = kd[sel][rng.permutation(len(sel))]
            mm = {k: _unit(X_out[docs][sel][kk == k].mean(0)) for k in BUCKETS}
            vals.append(min(mm[a] @ mm[c] for a, c in pairs))
        null_mean_cos[t] = np.median(vals)
    print(
        "length: spearman(tokens, cosine) by bucket "
        + ", ".join(f"{BUCKET_NAMES[k]} {v:+.2f}" for k, v in rho_len.items() if k != "all")
        + f", all {rho_len['all']:+.2f}; unmatched spread of bucket medians {unmatched_spread:.3f}, "
        f"matched {spread:.3f} over {len(per_bin)} bins, shuffled null 99th {null99:.3f}",
        flush=True,
    )
    # the bucket differences decomposed: along the cone, or across it
    raw_means = {k: X_out[kinds == k].mean(0) for k in BUCKETS}
    decomposed = {}
    for a, c in pairs:
        dv = raw_means[a] - raw_means[c]
        along = float(dv @ mu)
        decomposed[f"{a}-{c}"] = {
            "length": float(np.linalg.norm(dv)),
            "along_cone": along,
            "across_cone": float(np.sqrt(max(dv @ dv - along**2, 0.0))),
        }
    bucket_mean = {
        k: {
            "length": float(np.linalg.norm(raw_means[k])),
            "cos_to_cone": float(_unit(raw_means[k]) @ mu),
            "tokens_median": int(np.median(n_tok[kinds == k])),
        }
        for k in BUCKETS
    }
    pairwise = _pairwise_matched(cos_out, kinds, n_tok, rng, SHUFFLES)
    print(
        "bucket mean differences: "
        + "; ".join(
            f"{k} length {v['length']:.3f}, along the cone {v['along_cone']:+.3f}, across it {v['across_cone']:.3f}"
            for k, v in decomposed.items()
        ),
        flush=True,
    )
    print(
        "pairwise, length-matched in fine bins: "
        + "; ".join(
            f"{k} mean |diff| {v['mean_abs_diff']:.3f} over {len(v['bins'])} bins (null 99th {v['null_99']:.3f})"
            for k, v in pairwise.items()
        ),
        flush=True,
    )
    print(
        "bucket mean directions, pairwise cosine: whole "
        + ", ".join(f"{k} {v:.3f}" for k, v in mean_cos_whole.items())
        + "; length-matched "
        + ", ".join(f"{k} {v:.3f}" for k, v in mean_cos_matched.items())
        + f"; shuffled null 1st pct of the smallest pair {np.percentile(null_mean_cos, 1):.3f}",
        flush=True,
    )

    # by depth: each bucket's median cosine to the output cone, queries beside them
    depth_median = {
        k: [float(np.median(cos_depth[j][kinds == k])) for j in range(L1)]
        for k in BUCKETS + ("query",)
    }
    depth_iqr = {
        k: [
            [
                float(np.percentile(cos_depth[j][kinds == k], 25)),
                float(np.percentile(cos_depth[j][kinds == k], 75)),
            ]
            for j in range(L1)
        ]
        for k in BUCKETS + ("query",)
    }
    # where the buckets part: first depth at which the matched spread exceeds its output null
    spread_by_depth = []
    for j in range(L1):
        _, s = _matched_stats(cos_depth[j][docs].astype(np.float64), kinds[docs], bins[docs], None)
        spread_by_depth.append(float(s))

    # by tag: rung A's 811 notes, per-tag median at the output, against shuffled notes
    zl = np.load(LAYERS)
    Xl = zl["last"][:, -1].astype(np.float64)
    cos_l = _unit(Xl) @ mu
    tags_l = [json.loads(t) for t in zl["tags"]]
    from collections import Counter

    counts = Counter(t for ts in tags_l for t in ts)
    scorable = sorted([t for t, c in counts.items() if c >= MIN_NOTES], key=lambda t: -counts[t])
    members = {t: np.array([i for i, ts in enumerate(tags_l) if t in ts]) for t in scorable}
    tag_median = {t: float(np.median(cos_l[members[t]])) for t in scorable}
    obs_tag_spread = float(np.std(list(tag_median.values())))
    null_tag = np.zeros(SHUFFLES)
    for t in range(SHUFFLES):
        perm = cos_l[rng.permutation(len(cos_l))]
        null_tag[t] = np.std([np.median(perm[members[tg]]) for tg in scorable])
    rho_len_tags = float(spearmanr(zl["n_tok"], cos_l).correlation)
    ranked = sorted(tag_median.items(), key=lambda kv: kv[1])
    # is the cone special among directions? the same spread for random unit directions
    Xu = _unit(Xl)
    ratio_cone = _tag_spread_ratio(Xu @ mu, members)
    R = _unit(rng.standard_normal((RANDOM_DIRECTIONS, Xl.shape[1])))
    ratio_random = np.array([_tag_spread_ratio(Xu @ v, members) for v in R])
    # and for the data's own principal directions, after centring
    Xc = Xu - Xu.mean(0)
    _, _, Vt = np.linalg.svd(Xc, full_matrices=False)
    ratio_pcs = np.array([_tag_spread_ratio(Xu @ v, members) for v in Vt[:10]])
    print(
        f"tags: {len(scorable)} scorable; std of per-tag medians {obs_tag_spread:.4f}, shuffled null 99th "
        f"{np.percentile(null_tag, 99):.4f} (z {(obs_tag_spread - null_tag.mean()) / null_tag.std():.1f}); "
        f"lowest {ranked[0][0]} {ranked[0][1]:.3f}, highest {ranked[-1][0]} {ranked[-1][1]:.3f}; "
        f"spearman(tokens, cosine) over the 811 notes {rho_len_tags:+.2f}",
        flush=True,
    )
    print(
        f"tag separation along the cone {ratio_cone:.3f} (spread of tag medians over the spread of notes); "
        f"{RANDOM_DIRECTIONS} random directions median {np.median(ratio_random):.3f}, 99th {np.percentile(ratio_random, 99):.3f}; "
        f"the first 10 principal directions " + " ".join(f"{v:.2f}" for v in ratio_pcs),
        flush=True,
    )

    holds = bool(spread > null99 and min(mean_cos_matched.values()) < 0.95)
    below = int((match_cos < 0.99).sum()) if len(matched) else 0
    rec = {
        "store": {"n": len(Xs), "medians": store_medians},
        "frozen": {
            "n_documents": int(docs.sum()),
            "n_queries": int((~docs).sum()),
            "medians_output": frozen_medians,
            "keys_matched_to_store": len(matched),
            "matched_cos_median": float(np.median(match_cos)) if len(matched) else None,
            "matched_cos_min": float(match_cos.min()) if len(matched) else None,
            "matched_below_0_99": below,
            "query_median_output": float(np.median(cos_out[~docs])),
        },
        "bucket_mean": bucket_mean,
        "bucket_mean_differences": decomposed,
        "pairwise_matched": pairwise,
        "length": {
            "edges": list(TOKEN_EDGES),
            "occupancy": occupancy,
            "spearman_tokens_vs_cosine": rho_len,
            "unmatched_spread_of_bucket_medians": float(unmatched_spread),
            "matched_spread_of_bucket_medians": spread,
            "matched_bins": len(per_bin),
            "shuffled_null_99": null99,
            "shuffled_null_median": float(np.median(null)),
            "per_bin": per_bin,
            "bucket_mean_cos_whole": mean_cos_whole,
            "bucket_mean_cos_matched_median": mean_cos_matched,
            "bucket_mean_cos_null_1st_pct": float(np.percentile(null_mean_cos, 1)),
        },
        "depth": {"spread_matched_by_depth": spread_by_depth},
        "tags": {
            "scorable": len(scorable),
            "std_of_tag_medians": obs_tag_spread,
            "null_99": float(np.percentile(null_tag, 99)),
            "z": float((obs_tag_spread - null_tag.mean()) / null_tag.std()),
            "lowest": ranked[:5],
            "highest": ranked[-5:],
            "spearman_tokens_vs_cosine": rho_len_tags,
            "separation_ratio_cone": ratio_cone,
            "separation_ratio_random_median": float(np.median(ratio_random)),
            "separation_ratio_random_99": float(np.percentile(ratio_random, 99)),
            "separation_ratio_pcs": [round(float(v), 3) for v in ratio_pcs],
        },
        "prediction_1": {
            "spread_beyond_null": bool(spread > null99),
            "mean_cos_under_0_95": bool(min(mean_cos_matched.values()) < 0.95),
            "holds": holds,
        },
        "seconds": round(time.time() - t0),
    }
    SECTION.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        TAG_NPZ,
        cos_store=cos_store.astype(np.float32),
        kinds_store=ks,
        cos_depth=cos_depth,
        kinds=kinds,
        n_tok=n_tok,
        null_spread=null.astype(np.float32),
        null_mean_cos=null_mean_cos.astype(np.float32),
        depth_median=np.array([depth_median[k] for k in BUCKETS + ("query",)], np.float32),
        depth_iqr=np.array([depth_iqr[k] for k in BUCKETS + ("query",)], np.float32),
        cos_tags=cos_l.astype(np.float32),
        n_tok_tags=zl["n_tok"],
        tag_names=np.array(scorable),
        tag_medians=np.array([tag_median[t] for t in scorable], np.float32),
        null_tag=null_tag.astype(np.float32),
        ratio_random=ratio_random.astype(np.float32),
        ratio_pcs=ratio_pcs.astype(np.float32),
    )
    d = _load_results()
    d["tag"] = rec
    _save_results(d)
    print(f"prediction 1 holds: {holds}; {time.time() - t0:.0f} s", flush=True)


# ---------------------------------------------------------------- the model, the notes, the hooks


def _population_notes() -> list[dict]:
    """The 20 notes of 59.3 by their stored keys, so the set cannot drift
    with the store, plus the specimen first."""
    from ytk import store

    meta = {n["key"]: n for n in json.loads(POP_JSON.read_text())["notes"]}
    keys = [str(k) for k in np.load(POP_NPZ, allow_pickle=True)["keys"]]
    notes = []
    got = store._videos_collection().get(ids=[SPECIMEN_ID], include=["documents", "metadatas"])
    notes.append(
        {
            "key": f"vid::{SPECIMEN_ID}",
            "doc": got["documents"][0],
            "name": store.meta_str(got["metadatas"][0], "title")[:80],
            "tag": "specimen",
        }
    )
    vids = store._videos_collection()
    mems = store._memories_collection()
    for k in keys:
        if k.startswith("vid::"):
            got = vids.get(ids=[k[5:]], include=["documents"])
        else:
            got = mems.get(ids=[k.split("#", 1)[1]], include=["documents"])
        if not got["documents"]:
            raise SystemExit(f"population note {k} is no longer in the store; nothing run")
        notes.append(
            {"key": k, "doc": got["documents"][0], "name": meta[k]["name"], "tag": meta[k]["tag"]}
        )
    return notes


def _split_hooks(am, layer_idx: int) -> dict:
    """One pre-hook on the block's o_proj. `state` names the mode for every
    row of the batch: all, pos0, content, swap (position 0 replaced by
    `repl`), with `slices` the coordinates each row touches."""
    import torch

    state: dict = {"mode": None, "slices": None, "repl": None, "heads": None, "final_raw": None}

    def hook(module, args):
        state["heads"] = args[0][0].detach().float().cpu().numpy()
        if state["mode"] is None:
            return None
        x = args[0].clone()
        for b, sl in enumerate(state["slices"]):
            if state["mode"] == "all":
                x[b, :, sl] = 0
            elif state["mode"] == "pos0":
                x[b, 0, sl] = 0
            elif state["mode"] == "content":
                x[b, 1:, sl] = 0
            elif state["mode"] == "swap":
                x[b, 0, sl] = torch.as_tensor(state["repl"], dtype=x.dtype, device=x.device)
        return (x,)

    def keep_final(module, args):
        state["final_raw"] = args[0][0].detach().float().cpu().numpy()

    am.layers[layer_idx].self_attn.o_proj.register_forward_pre_hook(hook)
    am.norm.register_forward_pre_hook(keep_final)
    return state


def _pass(am, feats, state, attentions: bool):
    """One forward pass: raw residual at every depth (29, T, 1024), the sink
    grid (28, 16) when asked, and the unit last-token vector."""
    import torch

    with torch.no_grad():
        out = am(**feats, output_attentions=attentions, output_hidden_states=True)
    raw = np.concatenate(
        [
            torch.stack(list(out.hidden_states[:-1])).float().cpu().numpy()[:, 0],
            state["final_raw"][None],
        ]
    )
    sink = (
        torch.stack([a[0, :, -1, 0] for a in out.attentions]).float().cpu().numpy()
        if attentions
        else None
    )
    last = _unit(out.last_hidden_state[0, -1].float().cpu().numpy())
    del out
    return raw, sink, last


# ---------------------------------------------------------------- reading 2


def valley() -> None:
    """Reading 2: within-sequence effective rank by depth, with and without
    the head, on the specimen and the 20 population notes; the cross-note
    rank from rung A's harvest beside it."""
    import encoder_anatomy_d3 as d3

    t0 = time.time()
    m = d3._model()
    am = m[0].auto_model
    cl, ch = CONE_HEAD
    D = am.config.head_dim
    state = _split_hooks(am, cl)
    notes = _population_notes()
    L1 = am.config.num_hidden_layers + 1
    sl = [slice(ch * D, (ch + 1) * D)]
    er = np.zeros(
        (len(notes), 2, 3, L1), np.float32
    )  # note, with/without, raw/no-pos0/normed, depth
    pos0_norm = np.zeros((len(notes), 2, L1), np.float32)
    n_tok = np.zeros(len(notes), np.int32)
    for i, r in enumerate(notes):
        feats = d3._features(m, r["doc"])
        n_tok[i] = feats["input_ids"].shape[1]
        for j, zero in enumerate((False, True)):
            state["mode"], state["slices"] = ("all", sl) if zero else (None, None)
            raw, _, _ = _pass(am, feats, state, attentions=False)
            state["mode"] = None
            for k in range(L1):
                M = raw[k].astype(np.float64)
                er[i, j, 0, k] = _erank(M)
                er[i, j, 1, k] = _erank(M[1:])
                er[i, j, 2, k] = _erank(_unit(M))
            pos0_norm[i, j] = np.linalg.norm(raw[:, 0], axis=1)
        print(
            f"[{i + 1}/{len(notes)}] {r['name'][:40]}: {n_tok[i]} tok; raw erank at depth 4/16/28 with head "
            f"{er[i, 0, 0, 4]:.1f}/{er[i, 0, 0, 16]:.1f}/{er[i, 0, 0, 28]:.1f}, without {er[i, 1, 0, 4]:.1f}/{er[i, 1, 0, 16]:.1f}/{er[i, 1, 0, 28]:.1f}; "
            f"normed with {er[i, 0, 2, 4]:.1f}/{er[i, 0, 2, 16]:.1f}/{er[i, 0, 2, 28]:.1f}; {time.time() - t0:.0f} s",
            flush=True,
        )

    # the cross-note version: rung A's 811 unit vectors at every depth, as stored and centred
    zl = np.load(LAYERS)
    cross = np.zeros((2, L1), np.float32)
    for k in range(L1):
        X = zl["last"][:, k].astype(np.float64)
        cross[0, k] = _erank(X)
        cross[1, k] = _erank(X - X.mean(0))

    # the bar: raw rank at depths 4..20 below the head-zeroed rank by more than the notes' IQR there
    pop = slice(1, None)
    gap = er[pop, 1, 0, :] - er[pop, 0, 0, :]  # without minus with, per note and depth
    med_gap = np.median(gap, 0)
    iqr_with = np.percentile(er[pop, 0, 0, :], 75, 0) - np.percentile(er[pop, 0, 0, :], 25, 0)
    window = slice(4, 21)
    holds = bool((med_gap[window] > iqr_with[window]).all())
    rec = {
        "notes": len(notes),
        "tokens_median": int(np.median(n_tok)),
        "raw_erank_median_with_head": [round(float(x), 2) for x in np.median(er[pop, 0, 0], 0)],
        "raw_erank_median_head_zeroed": [round(float(x), 2) for x in np.median(er[pop, 1, 0], 0)],
        "no_pos0_erank_median_with_head": [round(float(x), 2) for x in np.median(er[pop, 0, 1], 0)],
        "normed_erank_median_with_head": [round(float(x), 2) for x in np.median(er[pop, 0, 2], 0)],
        "normed_erank_median_head_zeroed": [
            round(float(x), 2) for x in np.median(er[pop, 1, 2], 0)
        ],
        "specimen_raw_with": [round(float(x), 2) for x in er[0, 0, 0]],
        "specimen_raw_without": [round(float(x), 2) for x in er[0, 1, 0]],
        "cross_note_erank": [round(float(x), 2) for x in cross[0]],
        "cross_note_erank_centred": [round(float(x), 2) for x in cross[1]],
        "pos0_norm_median_with": [round(float(x), 1) for x in np.median(pos0_norm[pop, 0], 0)],
        "pos0_norm_median_without": [round(float(x), 1) for x in np.median(pos0_norm[pop, 1], 0)],
        "prediction_2": {
            "window": [4, 20],
            "median_gap_without_minus_with": [round(float(x), 2) for x in med_gap],
            "iqr_with_head": [round(float(x), 2) for x in iqr_with],
            "depths_in_window_beyond_iqr": int((med_gap[window] > iqr_with[window]).sum()),
            "of": int(window.stop - window.start),
            "holds": holds,
        },
        "seconds": round(time.time() - t0),
    }
    SECTION.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        VALLEY_NPZ,
        erank=er,
        pos0_norm=pos0_norm,
        n_tok=n_tok,
        cross=cross,
        names=np.array([r["name"] for r in notes]),
    )
    d = _load_results()
    d["valley"] = rec
    _save_results(d)
    print("raw erank median, with head   ", np.round(np.median(er[pop, 0, 0], 0), 1))
    print("raw erank median, head zeroed ", np.round(np.median(er[pop, 1, 0], 0), 1))
    print("no-pos0 erank median, with    ", np.round(np.median(er[pop, 0, 1], 0), 1))
    print("normed erank median, with     ", np.round(np.median(er[pop, 0, 2], 0), 1))
    print("normed erank median, zeroed   ", np.round(np.median(er[pop, 1, 2], 0), 1))
    print("cross-note erank              ", np.round(cross[0], 1))
    print("cross-note erank, centred     ", np.round(cross[1], 1))
    print(
        f"prediction 2 holds: {holds} ({rec['prediction_2']['depths_in_window_beyond_iqr']}/{rec['prediction_2']['of']} depths); {time.time() - t0:.0f} s",
        flush=True,
    )


# ---------------------------------------------------------------- reading 3


def split() -> None:
    """Reading 3: the head's write zeroed at position 0 only, at content
    positions only, everywhere, and replaced at position 0 by the mean
    register; on the specimen and the 20 population notes, with a
    position-0 null."""
    import encoder_anatomy_d3 as d3

    t_all = time.time()
    rng = np.random.default_rng(SEED)
    mu = _mu()
    m = d3._model()
    am = m[0].auto_model
    cl, ch = CONE_HEAD
    H, D = am.config.num_attention_heads, am.config.head_dim
    L1 = am.config.num_hidden_layers + 1
    state = _split_hooks(am, cl)
    notes = _population_notes()
    N = len(notes)
    sl = [slice(ch * D, (ch + 1) * D)]

    z = np.load(STORE)
    vm = np.flatnonzero(z["kinds"] != "seg")
    Xn = _unit(z["X"][vm].astype(np.float64))
    uniq, inv = np.unique(z["keys"][vm], return_inverse=True)

    def neighbours(v: np.ndarray, exclude: str) -> list[str]:
        best = np.full(len(uniq), -np.inf)
        np.maximum.at(best, inv, Xn @ v)
        return [str(uniq[j]) for j in np.argsort(best)[::-1] if str(uniq[j]) != exclude][
            :NEIGHBOURS
        ]

    C = len(CONDITIONS)
    pos0_norm = np.zeros((N, C + 1, L1), np.float32)
    # baselines first: the head's position-0 output on every note gives the constant
    feats_all, base, raw_base, sink_base, h0 = [], [], [], [], []
    for i, r in enumerate(notes):
        f = d3._features(m, r["doc"])
        feats_all.append(f)
        raw, sk, last = _pass(am, f, state, attentions=True)
        base.append(last)
        raw_base.append(raw[:, -1].copy())  # (29, 1024) last position by depth
        sink_base.append(sk)
        pos0_norm[i, 0] = np.linalg.norm(raw[:, 0], axis=1)
        h0.append(state["heads"][0, sl[0]].copy())
    h0 = np.stack(h0)
    const = h0.mean(0)
    h0u = _unit(h0)
    print(
        f"{N} baselines in {time.time() - t_all:.0f} s; the head's position-0 output before o_proj agrees across notes at median cosine "
        f"{np.median((h0u @ h0u.T)[~np.eye(N, dtype=bool)]):.4f}, norms {np.linalg.norm(h0, axis=1).min():.1f} to {np.linalg.norm(h0, axis=1).max():.1f}",
        flush=True,
    )
    disp = np.zeros((N, C), np.float32)
    changed = np.zeros((N, C), np.int32)
    cone = np.zeros((N, C + 1), np.float32)
    sink = np.zeros((N, C + 1, 28), np.float32)  # median head per block
    dye = np.zeros((N, C, L1), np.float32)
    null_disp = [np.zeros(0)] * N
    null_sink = [np.zeros(0)] * N
    null_content = [np.zeros(0)] * N
    nb0_all = []
    for i, r in enumerate(notes):
        t0 = time.time()
        f = feats_all[i]
        exclude = r["key"].split("#")[0]
        nb0 = neighbours(base[i], exclude)
        nb0_all.append(nb0)
        cone[i, 0] = base[i] @ mu
        sink[i, 0] = np.median(sink_base[i], 1)
        for c, mode in enumerate(CONDITIONS):
            state["mode"], state["slices"], state["repl"] = mode, sl, const
            raw, sk, last = _pass(am, f, state, attentions=True)
            state["mode"] = None
            disp[i, c] = 1 - last @ base[i]
            changed[i, c] = NEIGHBOURS - len(set(neighbours(last, exclude)) & set(nb0))
            cone[i, c + 1] = last @ mu
            sink[i, c + 1] = np.median(sk, 1)
            pos0_norm[i, c + 1] = np.linalg.norm(raw[:, 0], axis=1)
            dye[i, c] = np.einsum("ko,ko->k", _unit(raw[:, -1]), _unit(raw_base[i]))
        # position-0 null: random 128 coordinates of the block's concatenated heads
        draws = NULL_SPECIMEN if i == 0 else NULL_POP
        nd, ns = np.zeros(draws), np.zeros(draws)
        for t in range(draws):
            idx = np.sort(rng.choice(H * D, size=D, replace=False))
            state["mode"], state["slices"] = "pos0", [idx]
            _, sk, last = _pass(am, f, state, attentions=True)
            state["mode"] = None
            nd[t] = 1 - last @ base[i]
            ns[t] = np.median(np.median(sk, 1)[3:])
        null_disp[i], null_sink[i] = nd, ns
        # content null, added after the first run: the position-0 null moves nothing
        # (median 99th percentile 0.00003), so the content cut needs its own matched draw
        nc = np.zeros(draws)
        for t in range(draws):
            idx = np.sort(rng.choice(H * D, size=D, replace=False))
            state["mode"], state["slices"] = "content", [idx]
            _, _, last = _pass(am, f, state, attentions=False)
            state["mode"] = None
            nc[t] = 1 - last @ base[i]
        null_content[i] = nc
        s_late = {k: float(np.median(sink[i, k, 3:])) for k in range(C + 1)}
        print(
            f"[{i + 1}/{N}] {r['name'][:36]}: disp pos0 {disp[i, 0]:.3f} content {disp[i, 1]:.3f} all {disp[i, 2]:.3f} swap {disp[i, 3]:.4f} "
            f"(pos0 null 99th {np.percentile(nd, 99):.5f}, content null 99th {np.percentile(nc, 99):.4f}); moved {changed[i].tolist()}; cone {cone[i, 0]:.2f} -> "
            + "/".join(f"{cone[i, k]:.2f}" for k in range(1, C + 1))
            + f"; sink late {s_late[0]:.2f} -> "
            + "/".join(f"{s_late[k]:.2f}" for k in range(1, C + 1))
            + f"; pos0 norm after block {cl + 1}: {pos0_norm[i, 0, cl + 1]:.0f} -> "
            + "/".join(f"{pos0_norm[i, k, cl + 1]:.0f}" for k in range(1, C + 1))
            + f"; {time.time() - t0:.0f} s, {(time.time() - t_all) / 60:.1f} min so far",
            flush=True,
        )

    null99 = np.array([np.percentile(x, 99) for x in null_disp])
    null99_content = np.array([np.percentile(x, 99) for x in null_content])
    sink_late = np.median(sink[:, :, 3:], 2)  # (N, C+1)
    pop = slice(1, None)
    p3a = {
        "sink_under_0_05": int((sink_late[:, 1] < 0.05).sum()),
        "pos0_norm_under_100": int((pos0_norm[:, 1, cl + 1] < 100).sum()),
        "disp_within_0_05_of_whole_head": int((np.abs(disp[:, 0] - disp[:, 2]) < 0.05).sum()),
        "of": N,
    }
    p3a["holds"] = bool(all(v == N for k, v in p3a.items() if k not in ("of", "holds")))
    p3b = {
        "sink_above_0_5": int((sink_late[:, 2] > 0.5).sum()),
        "pos0_norm_above_1000": int((pos0_norm[:, 2, cl + 1] > 1000).sum()),
        "disp_under_null_99": int((disp[:, 1] < null99).sum()),
        "cone_within_0_03": int((np.abs(cone[:, 2] - cone[:, 0]) < 0.03).sum()),
        "of": N,
    }
    p3b["holds"] = bool(all(v == N for k, v in p3b.items() if k not in ("of", "holds")))
    # the registered clause against the position-0 null, then the matched content null, disclosed
    p3b["disp_under_content_null_99"] = int((disp[:, 1] < null99_content).sum())
    p3c = {
        "disp_under_null_99": int((disp[:, 3] < null99).sum()),
        "neighbours_unchanged": int((changed[:, 3] == 0).sum()),
        "of": N,
    }
    p3c["holds"] = bool(all(v == N for k, v in p3c.items() if k not in ("of", "holds")))
    rec = {
        "notes": N,
        "conditions": list(CONDITIONS),
        "constant": {
            "pos0_output_cos_between_notes_median": float(
                np.median((h0u @ h0u.T)[~np.eye(N, dtype=bool)])
            ),
            "pos0_output_norm_min": float(np.linalg.norm(h0, axis=1).min()),
            "pos0_output_norm_max": float(np.linalg.norm(h0, axis=1).max()),
        },
        "displacement_median": {
            c: float(np.median(disp[pop, k])) for k, c in enumerate(CONDITIONS)
        },
        "displacement_specimen": {c: float(disp[0, k]) for k, c in enumerate(CONDITIONS)},
        "neighbours_moved_median": {
            c: float(np.median(changed[pop, k])) for k, c in enumerate(CONDITIONS)
        },
        "cone_cos_median": {
            "baseline": float(np.median(cone[pop, 0])),
            **{c: float(np.median(cone[pop, k + 1])) for k, c in enumerate(CONDITIONS)},
        },
        "sink_late_median": {
            "baseline": float(np.median(sink_late[pop, 0])),
            **{c: float(np.median(sink_late[pop, k + 1])) for k, c in enumerate(CONDITIONS)},
        },
        "pos0_norm_after_block_median": {
            "baseline": float(np.median(pos0_norm[pop, 0, cl + 1])),
            **{
                c: float(np.median(pos0_norm[pop, k + 1, cl + 1])) for k, c in enumerate(CONDITIONS)
            },
        },
        "dye_final_median": {
            c: float(np.median(dye[pop, k, -1])) for k, c in enumerate(CONDITIONS)
        },
        "null": {
            "draws_specimen": NULL_SPECIMEN,
            "draws_per_population_note": NULL_POP,
            "disp_99_median_over_notes": float(np.median(null99)),
            "content_disp_99_median_over_notes": float(np.median(null99_content)),
            "sink_late_median_over_draws": float(np.median(np.concatenate(null_sink))),
        },
        "prediction_3a": p3a,
        "prediction_3b": p3b,
        "prediction_3c": p3c,
        "seconds": round(time.time() - t_all),
    }
    SECTION.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        SPLIT_NPZ,
        disp=disp,
        changed=changed,
        cone=cone,
        sink=sink,
        pos0_norm=pos0_norm,
        dye=dye,
        null99=null99.astype(np.float32),
        null_disp_specimen=null_disp[0].astype(np.float32),
        null_disp_pop=np.stack(null_disp[1:]).astype(np.float32),
        null_content_specimen=null_content[0].astype(np.float32),
        null_content_pop=np.stack(null_content[1:]).astype(np.float32),
        null99_content=null99_content.astype(np.float32),
        null_sink_specimen=null_sink[0].astype(np.float32),
        null_sink_pop=np.stack(null_sink[1:]).astype(np.float32),
        h0=h0.astype(np.float32),
        names=np.array([r["name"] for r in notes]),
        tags=np.array([r["tag"] for r in notes]),
    )
    d = _load_results()
    d["split"] = rec
    _save_results(d)
    print(
        json.dumps(
            {
                k: v
                for k, v in rec.items()
                if k.startswith("prediction")
                or k
                in (
                    "displacement_median",
                    "cone_cos_median",
                    "sink_late_median",
                    "pos0_norm_after_block_median",
                    "null",
                )
            },
            indent=1,
        )
    )
    print(f"{(time.time() - t_all) / 60:.1f} min", flush=True)


# ---------------------------------------------------------------- figures

LEGEND = {"fontsize": 9}
BUCKET_COLOR = {"vid": "GOLD", "mem": "CYAN", "seg": "PURPLE", "query": "MUTED"}


def _legend_kw(pa) -> dict:
    return {
        "facecolor": pa.PANEL,
        "edgecolor": pa.FRAME,
        "labelcolor": pa.TEXT,
        "fontsize": pa.TICK_SIZE,
    }


def tag_figure() -> None:
    import plot_assets as pa

    pa.OUTDIR = SECTION
    r = _load_results()["tag"]
    z = np.load(TAG_NPZ)
    cos = z["cos_depth"][-1].astype(float)
    kinds, n_tok = z["kinds"], z["n_tok"]
    docs = kinds != "query"
    col = {k: getattr(pa, v) for k, v in BUCKET_COLOR.items()}
    lk = _legend_kw(pa)
    dec = r["bucket_mean_differences"]
    pw = r["pairwise_matched"]
    tg = r["tags"]

    fig, top = pa.figure(
        18,
        12.5,
        1,
        "section 61, D4: the register by bucket, length and tag",
        "Does the cone's weight vary with the kind of note? Every stored vector's cosine to section 58's cone, by bucket, by length and by tag",
        meta=(
            f"Rung B's frozen harvest, {r['frozen']['n_documents']:,} documents at the output depth, matched to the production store at median cosine "
            f"{r['frozen']['matched_cos_median']:.5f} ({r['frozen']['matched_below_0_99']} of {r['frozen']['keys_matched_to_store']:,} keys below 0.99). "
            f"Median cosine to the cone: videos {r['frozen']['medians_output']['vid']:.3f}, memories {r['frozen']['medians_output']['mem']:.3f}, segments {r['frozen']['medians_output']['seg']:.3f}. "
            f"Spearman of token count against cosine {r['length']['spearman_tokens_vs_cosine']['all']:+.2f}. Bucket mean differences along the cone "
            + ", ".join(f"{k} {v['along_cone']:+.3f}" for k, v in dec.items())
            + "; across it "
            + ", ".join(f"{k} {v['across_cone']:.3f}" for k, v in dec.items())
            + ". Length-matched pairwise differences of medians: "
            + ", ".join(
                f"{k} {v['mean_abs_diff']:.3f} (null 99th {v['null_99']:.3f})"
                for k, v in pw.items()
            )
            + f". Tags: {tg['scorable']} scorable over 811 notes; the cone separates them at {tg['separation_ratio_cone']:.2f} against {RANDOM_DIRECTIONS} random directions' median {tg['separation_ratio_random_median']:.2f} and the first principal direction's {tg['separation_ratio_pcs'][0]:.2f}."
        ),
    )
    gs = fig.add_gridspec(
        2,
        3,
        left=pa.MARGIN,
        right=1 - pa.MARGIN,
        top=top - 0.03,
        bottom=0.06,
        hspace=0.42,
        wspace=0.26,
    )

    # A: the distributions, one per bucket, on one axis
    ax = fig.add_subplot(gs[0, 0])
    pa.style_axes(ax)
    bins = np.linspace(0.1, 0.8, 71)
    for k in BUCKETS:
        v = cos[kinds == k]
        ax.hist(
            v,
            bins=bins,
            density=True,
            histtype="step",
            lw=2.0,
            color=col[k],
            label=f"{BUCKET_NAMES[k]} (n {len(v):,}, median {np.median(v):.3f})",
        )
    ax.hist(
        cos[~docs],
        bins=bins,
        density=True,
        histtype="step",
        lw=1.2,
        ls="--",
        color=col["query"],
        label=f"the 156 queries (median {np.median(cos[~docs]):.3f})",
    )
    ax.set_xlabel("cosine to the cone's direction (the shipped vector)")
    ax.set_ylabel("density")
    ax.legend(loc="upper left", **lk)
    pa.panel_title(
        ax,
        "A. Three buckets, one distribution: the cosine to the cone has the same shape and nearly the same median for videos, memories and segments",
        52,
    )

    # B: the differences between bucket means, along the cone against across it
    ax = fig.add_subplot(gs[0, 1])
    pa.style_axes(ax)
    rng = np.random.default_rng(SEED)
    pairs = list(dec.keys())
    x = np.arange(len(pairs))
    along = np.array([dec[p]["along_cone"] for p in pairs])
    across = np.array([dec[p]["across_cone"] for p in pairs])
    # the along component's null: bucket labels shuffled, the difference of mean cosines
    null_along = np.zeros((200, len(pairs)))
    cd, kd = cos[docs], kinds[docs]
    for t in range(200):
        kk = kd[rng.permutation(len(kd))]
        m = {k: cd[kk == k].mean() for k in BUCKETS}
        null_along[t] = [m[p.split("-")[0]] - m[p.split("-")[1]] for p in pairs]
    lo = np.percentile(np.abs(null_along), 99, 0)
    ax.bar(
        x - 0.2,
        np.abs(along),
        0.38,
        color=pa.GOLD,
        label="along the cone (|difference of mean cosines|)",
    )
    ax.bar(
        x + 0.2,
        across,
        0.38,
        color=pa.CYAN,
        label="across the cone (the rest of the difference vector)",
    )
    ax.bar(
        x - 0.2,
        lo,
        0.38,
        color=pa.DIM,
        alpha=0.9,
        zorder=3,
        label="shuffled labels, 99th percentile of the along part",
    )
    ax.set_xticks(x)
    ax.set_xticklabels(
        [f"{BUCKET_NAMES[p.split('-')[0]]}\nvs {BUCKET_NAMES[p.split('-')[1]]}" for p in pairs]
    )
    ax.set_ylabel("length of the component (unit-vector means)")
    ax.legend(loc="upper left", **lk)
    pa.panel_title(
        ax,
        f"B. Where the buckets differ: the difference between two buckets' mean vectors is {across.min() / max(np.abs(along).max(), 1e-3):.0f}x longer across the cone than along it",
        52,
    )

    # C: length, the confound, and the matched comparison
    ax = fig.add_subplot(gs[0, 2])
    pa.style_axes(ax)
    for k in BUCKETS:
        xs, ys, ns = [], [], []
        b = np.digitize(n_tok, FINE_EDGES[1:-1])
        for j in range(len(FINE_EDGES) - 1):
            sel = (b == j) & (kinds == k)
            if sel.sum() >= MIN_PER_BIN:
                xs.append(np.median(n_tok[sel]))
                ys.append(np.median(cos[sel]))
                ns.append(int(sel.sum()))
        ax.plot(xs, ys, color=col[k], lw=2.0, marker="o", ms=5, label=BUCKET_NAMES[k])
        for xx, yy, nn in zip(xs, ys, ns):
            if nn >= 100:
                continue
            ax.annotate(
                f"{nn}",
                (xx, yy),
                xytext=(0, 6),
                textcoords="offset points",
                ha="center",
                color=col[k],
                fontsize=7,
            )
    ax.set_xscale("log")
    ax.set_xlabel("tokens in the document (log), bin medians; the count above each point")
    ax.set_ylabel("median cosine to the cone in the bin")
    ax.set_ylim(0.40, 0.60)
    ax.legend(loc="lower right", **lk)
    pa.panel_title(
        ax,
        f"C. Length is the confound and it is small: cosine rises with tokens (Spearman {r['length']['spearman_tokens_vs_cosine']['all']:+.2f}); where two buckets share a length bin their medians sit within {max(v['mean_abs_diff'] for v in pw.values()):.3f}",
        52,
    )

    # D: by depth, each bucket's median cosine to the output cone
    ax = fig.add_subplot(gs[1, 0])
    pa.style_axes(ax)
    dm, di = z["depth_median"], z["depth_iqr"]
    depths = np.arange(dm.shape[1])
    for i, k in enumerate(BUCKETS + ("query",)):
        ax.fill_between(depths, di[i, :, 0], di[i, :, 1], color=col[k], alpha=0.12, lw=0)
        ax.plot(
            depths,
            dm[i],
            color=col[k],
            lw=2.0 if k != "query" else 1.2,
            ls="-" if k != "query" else "--",
            label=BUCKET_NAMES[k],
        )
    ax.set_xlim(0, depths[-1])
    ax.set_xlabel("depth (0 = token table, k = after block k)")
    ax.set_ylabel("median cosine to the output cone, interquartile band")
    ax.legend(loc="upper right", **lk)
    pa.panel_title(
        ax,
        "D. The buckets ride one curve through every depth: the output cone's direction is absent from the last position through depth 20 and enters in the last seven blocks for all of them alike",
        52,
    )

    # E: per-tag medians against the shuffled null
    ax = fig.add_subplot(gs[1, 1])
    pa.style_axes(ax)
    tm, names = z["tag_medians"], z["tag_names"]
    order = np.argsort(tm)
    grand = float(np.median(z["cos_tags"]))
    nt = z["null_tag"]
    band = np.percentile(nt, 99)
    xx = np.arange(len(tm))
    ax.axhspan(
        grand - band,
        grand + band,
        color=pa.DIM,
        alpha=0.9,
        lw=0,
        label="shuffled notes: the null spread of tag medians (99th) around the grand median",
    )
    ax.bar(xx, tm[order] - grand, bottom=grand, color=pa.GOLD, width=0.8)
    for j in (0, 1, 2, len(tm) - 3, len(tm) - 2, len(tm) - 1):
        ax.annotate(
            str(names[order][j]),
            (xx[j], tm[order][j]),
            xytext=(0, -10 if j < 3 else 4),
            textcoords="offset points",
            ha="center",
            color=pa.TEXT,
            fontsize=7,
            rotation=90,
            va="top" if j < 3 else "bottom",
        )
    ax.set_xlim(-1, len(tm))
    ax.set_ylim(tm.min() - 0.04, tm.max() + 0.05)
    ax.set_xlabel(f"the {len(tm)} scorable tags, sorted")
    ax.set_ylabel("median cosine to the cone over the tag's notes")
    ax.legend(loc="upper left", **lk)
    pa.panel_title(
        ax,
        f"E. Tags do differ in their cosine to the cone: the spread of tag medians is {tg['std_of_tag_medians']:.3f} against a shuffled 99th of {tg['null_99']:.3f}, {names[order][0]} lowest, {names[order][-1]} highest",
        52,
    )

    # F: is the cone a special direction for separating tags
    ax = fig.add_subplot(gs[1, 2])
    pa.style_axes(ax)
    rr, rp = z["ratio_random"], z["ratio_pcs"]
    hb = np.linspace(
        min(rr.min(), rp.min(), tg["separation_ratio_cone"]) - 0.02,
        max(rp.max(), tg["separation_ratio_cone"]) + 0.05,
        50,
    )
    ax.hist(rr, bins=hb, color=pa.DIM, label=f"{len(rr)} random unit directions")
    ymax = ax.get_ylim()[1]
    for j, v in enumerate(rp):
        ax.axvline(
            v,
            color=pa.CYAN,
            lw=1.2,
            alpha=0.9,
            label="the first 10 principal directions" if j == 0 else None,
        )
        if j < 3:
            ax.text(v, ymax * 0.97, f"pc{j + 1}", color=pa.CYAN, fontsize=7, ha="center")
    ax.axvline(
        tg["separation_ratio_cone"],
        color=pa.GOLD,
        lw=3.0,
        label=f"the cone: {tg['separation_ratio_cone']:.2f}",
    )
    ax.set_xlabel(
        "how much a direction separates the 84 tags (spread of tag medians / spread of notes)"
    )
    ax.set_ylabel("directions")
    ax.legend(loc="upper right", **lk)
    pa.panel_title(
        ax,
        f"F. But not more than content does: along the cone the tags separate at {tg['separation_ratio_cone']:.2f}, above a random direction ({np.median(rr):.2f}) and below the data's own first principal directions ({rp[0]:.2f}, {rp[1]:.2f})",
        52,
    )

    pa.verdict(
        fig,
        "THE BUCKETS DIFFER ACROSS THE CONE, NOT ALONG IT; the cone separates tags like an ordinary content direction",
    )
    pa.save(fig, "01-the-tag.png")


def valley_figure() -> None:
    import plot_assets as pa

    pa.OUTDIR = SECTION
    r = _load_results()["valley"]
    z = np.load(VALLEY_NPZ)
    er, cross = z["erank"], z["cross"]
    N, _, _, L1 = er.shape
    depths = np.arange(L1)
    lk = _legend_kw(pa)
    cl = CONE_HEAD[0]
    pop = slice(1, None)
    p2 = r["prediction_2"]

    def band(ax, Y, color, label, ls="-", lw=2.2):
        ax.fill_between(
            depths, np.percentile(Y, 25, 0), np.percentile(Y, 75, 0), color=color, alpha=0.15, lw=0
        )
        ax.plot(depths, np.median(Y, 0), color=color, lw=lw, ls=ls, label=label)

    fig, top = pa.figure(
        18,
        8.6,
        2,
        "section 61, D4: the compression valley",
        "Effective rank of the note's token matrix at every depth, with the cone head and without it, on the specimen and the 20 population notes",
        meta=(
            f"{N} notes (the specimen first), median {r['tokens_median']} tokens; two passes each, every token's raw residual kept at all {L1} depths; entropy effective rank of the T x 1024 matrix. "
            f"Raw, with the head: {r['raw_erank_median_with_head'][4]:.0f} at depth 4, {r['raw_erank_median_with_head'][16]:.0f} at 16, {r['raw_erank_median_with_head'][28]:.0f} at 28; head zeroed: "
            f"{r['raw_erank_median_head_zeroed'][4]:.0f}, {r['raw_erank_median_head_zeroed'][16]:.0f}, {r['raw_erank_median_head_zeroed'][28]:.0f}. Every token unit-normalised, with the head: "
            f"{r['normed_erank_median_with_head'][4]:.0f}, {r['normed_erank_median_with_head'][16]:.0f}, {r['normed_erank_median_with_head'][28]:.0f}. Position 0 dropped, with the head: "
            f"{r['no_pos0_erank_median_with_head'][4]:.0f}, {r['no_pos0_erank_median_with_head'][16]:.0f}, {r['no_pos0_erank_median_with_head'][28]:.0f}. "
            f"Prediction 2 (raw rank at depths 4 to 20 below the head-zeroed rank by more than the notes' interquartile range): {p2['depths_in_window_beyond_iqr']} of {p2['of']} depths. "
            f"Side panel: rung A's 811 notes, one unit vector each after the final norm, the cross-note rank."
        ),
    )
    gs = fig.add_gridspec(
        1, 4, left=pa.MARGIN, right=1 - pa.MARGIN, top=top - 0.04, bottom=0.10, wspace=0.24
    )

    # A: raw, with and without
    ax = fig.add_subplot(gs[0, 0])
    pa.style_axes(ax)
    band(ax, er[pop, 0, 0], pa.GOLD, "as shipped, 20 notes (median, interquartile band)")
    band(ax, er[pop, 1, 0], pa.CYAN, f"block {cl + 1} head 6 zeroed", ls="--")
    ax.plot(depths, er[0, 0, 0], color=pa.GOLD, lw=1.0, alpha=0.7, label="the specimen, as shipped")
    ax.axvline(cl + 1, color=pa.MUTED, lw=0.8, ls=":")
    ax.set_xlim(0, L1 - 1)
    ax.set_ylim(0, max(er[:, :, 0].max(), er[:, :, 2].max()) * 1.05)
    ax.set_xlabel("depth")
    ax.set_ylabel("effective rank of the raw token matrix")
    ax.legend(loc="upper right", **lk)
    pa.panel_title(
        ax,
        f"A. The valley: the raw rank falls from {np.median(er[pop, 0, 0], 0)[cl]:.0f} to {np.median(er[pop, 0, 0], 0)[cl + 1]:.0f} at block {cl + 1} and climbs back over the last blocks; with the head zeroed there is no valley",
        44,
    )

    # B: every token normalised
    ax = fig.add_subplot(gs[0, 1])
    pa.style_axes(ax)
    band(ax, er[pop, 0, 2], pa.GOLD, "as shipped, every token unit-normalised")
    band(ax, er[pop, 1, 2], pa.CYAN, "head zeroed, every token unit-normalised", ls="--")
    ax.axvline(cl + 1, color=pa.MUTED, lw=0.8, ls=":")
    ax.set_xlim(0, L1 - 1)
    ax.set_ylim(0, max(er[:, :, 0].max(), er[:, :, 2].max()) * 1.05)
    ax.set_xlabel("depth")
    ax.set_ylabel("effective rank, tokens unit-normalised")
    ax.legend(loc="upper right", **lk)
    pa.panel_title(
        ax,
        f"B. Normalise each token and the valley is gone: {np.median(er[pop, 0, 2], 0)[4]:.0f} at depth 4 with the head, {np.median(er[pop, 1, 2], 0)[4]:.0f} without",
        44,
    )

    # C: position 0 dropped, against the head-zeroed raw
    ax = fig.add_subplot(gs[0, 2])
    pa.style_axes(ax)
    band(ax, er[pop, 0, 1], pa.GOLD, "as shipped, position 0 dropped from the matrix")
    band(ax, er[pop, 1, 0], pa.CYAN, "head zeroed, raw", ls="--")
    ax.axvline(cl + 1, color=pa.MUTED, lw=0.8, ls=":")
    ax.set_xlim(0, L1 - 1)
    ax.set_ylim(0, max(er[:, :, 0].max(), er[:, :, 2].max()) * 1.05)
    ax.set_xlabel("depth")
    ax.set_ylabel("effective rank")
    ax.legend(loc="upper right", **lk)
    pa.panel_title(
        ax,
        f"C. The valley is one token: drop position 0 from the shipped run and the curve lands on the head-zeroed one (median gap {np.median(np.abs(er[pop, 0, 1] - er[pop, 1, 0])):.1f} ranks)",
        44,
    )

    # D: the cross-note rank from rung A
    ax = fig.add_subplot(gs[0, 3])
    pa.style_axes(ax)
    ax.plot(
        depths,
        cross[0],
        color=pa.GOLD,
        lw=2.2,
        label="811 notes, as stored (unit, after the final norm)",
    )
    ax.plot(
        depths,
        cross[1],
        color=pa.CYAN,
        lw=2.2,
        ls="--",
        label="the same, centred on the depth's mean",
    )
    ax.set_xlim(0, L1 - 1)
    ax.set_ylim(0, cross.max() * 1.1)
    ax.set_xlabel("depth")
    ax.set_ylabel("effective rank across notes")
    ax.legend(loc="upper right", **lk)
    pa.panel_title(
        ax,
        f"D. Across notes (a different quantity): rung A's one-vector-per-note matrix, identical at the token table, has rank {cross[0, 1]:.0f} after block 1 and {cross[0, -1]:.0f} at the top; centred, {cross[1, 1]:.0f} and {cross[1, -1]:.0f}",
        44,
    )

    pa.verdict(
        fig,
        f"THE VALLEY IS THE SINK TOKEN'S NORM, NOT A LOSS OF CONTENT DIMENSIONS: rank {np.median(er[pop, 0, 0], 0)[4]:.0f} vs {np.median(er[pop, 1, 0], 0)[4]:.0f} at depth 4 in the raw matrix, {np.median(er[pop, 0, 2], 0)[4]:.0f} vs {np.median(er[pop, 1, 2], 0)[4]:.0f} with tokens normalised",
    )
    pa.save(fig, "02-the-valley.png")


COND_LABEL = {
    "pos0": "position 0 only",
    "content": "content positions only",
    "all": "the whole head",
    "swap": "position 0 swapped for the mean register",
}


def split_figure() -> None:
    import plot_assets as pa

    pa.OUTDIR = SECTION
    r = _load_results()["split"]
    z = np.load(SPLIT_NPZ)
    disp, changed, cone, sink, pos0_norm, dye = (
        z["disp"],
        z["changed"],
        z["cone"],
        z["sink"],
        z["pos0_norm"],
        z["dye"],
    )
    N, C = disp.shape
    L1 = dye.shape[2]
    cl = CONE_HEAD[0]
    lk = _legend_kw(pa)
    ccol = {"pos0": pa.GOLD, "content": pa.CYAN, "all": pa.PURPLE, "swap": pa.BLUE}
    cols = [ccol[c] for c in CONDITIONS]
    rng = np.random.default_rng(0)
    jit = lambda n, w=0.10: rng.uniform(-w, w, n)
    sink_late = np.median(sink[:, :, 3:], 2)
    null_pos0 = np.concatenate([z["null_disp_specimen"], z["null_disp_pop"].ravel()])
    null_cont = np.concatenate([z["null_content_specimen"], z["null_content_pop"].ravel()])
    p3a, p3b, p3c = r["prediction_3a"], r["prediction_3b"], r["prediction_3c"]
    dm, cm, sm, pm = (
        r["displacement_median"],
        r["cone_cos_median"],
        r["sink_late_median"],
        r["pos0_norm_after_block_median"],
    )

    def strips(ax, Y, xs, colors, log=False):
        """One column per condition: the 20 population notes as points, the specimen ringed."""
        for j, x in enumerate(xs):
            y = Y[:, j]
            if log:
                y = np.maximum(y, 1e-7)
            ax.scatter(x + jit(N - 1), y[1:], s=22, color=colors[j], alpha=0.85, zorder=4, lw=0)
            ax.scatter([x], [y[0]], s=70, facecolor="none", edgecolor=colors[j], lw=1.6, zorder=5)
            ax.hlines(np.median(y[1:]), x - 0.22, x + 0.22, color=colors[j], lw=2.4, zorder=6)

    fig, top = pa.figure(
        18,
        12.5,
        3,
        "section 61, D4: the position split",
        "The cone head's write removed at position 0 only, at the content positions only, everywhere, and replaced at position 0 by the mean register, on the specimen and 20 notes",
        meta=(
            f"{N} notes, four conditions each, one pass per condition with attention and every depth kept. Median displacement of the shipped vector: position 0 only {dm['pos0']:.3f}, "
            f"content only {dm['content']:.4f}, whole head {dm['all']:.3f}, swap {dm['swap']:.1e}; position-0 null (128 random coordinates of the block's heads zeroed at position 0) 99th percentile "
            f"{r['null']['disp_99_median_over_notes']:.1e}, content null {r['null']['content_disp_99_median_over_notes']:.4f}. Sink, median head on token 0 over blocks 4 to 28: baseline {sm['baseline']:.2f}, "
            f"position 0 only {sm['pos0']:.3f}, content only {sm['content']:.2f}, whole head {sm['all']:.3f}, swap {sm['swap']:.2f}. Position 0's residual norm after block {cl + 1}: {pm['baseline']:,.0f}, "
            f"{pm['pos0']:.0f}, {pm['content']:,.0f}, {pm['all']:.0f}, {pm['swap']:,.0f}. Cosine to the cone: {cm['baseline']:.2f} to {cm['pos0']:.2f} / {cm['content']:.2f} / {cm['all']:.2f} / {cm['swap']:.2f}. "
            f"P3a {p3a['sink_under_0_05']}, {p3a['pos0_norm_under_100']}, {p3a['disp_within_0_05_of_whole_head']} of {N} on its three clauses; P3b {p3b['sink_above_0_5']}, {p3b['pos0_norm_above_1000']}, "
            f"{p3b['disp_under_null_99']} ({p3b['disp_under_content_null_99']} against the content null), {p3b['cone_within_0_03']} of {N}; P3c {p3c['disp_under_null_99']}, {p3c['neighbours_unchanged']} of {N}. "
            f"The head's position-0 output before o_proj agrees across notes at cosine {r['constant']['pos0_output_cos_between_notes_median']:.3f}."
        ),
    )
    gs = fig.add_gridspec(
        2,
        3,
        left=pa.MARGIN,
        right=1 - pa.MARGIN,
        top=top - 0.03,
        bottom=0.07,
        hspace=0.42,
        wspace=0.26,
    )
    xs = np.arange(C)
    xt = [
        COND_LABEL[c]
        .replace(" for the mean register", "\nfor the mean register")
        .replace(" positions only", "\npositions only")
        .replace(" only", "\nonly")
        if c != "all"
        else "the whole\nhead"
        for c in CONDITIONS
    ]

    # A: displacement against the two nulls
    ax = fig.add_subplot(gs[0, 0])
    pa.style_axes(ax)
    for x, nul in ((0, null_pos0), (1, null_cont), (2, null_pos0), (3, null_pos0)):
        ax.scatter(
            x - 0.3 + jit(len(nul), 0.06),
            np.maximum(nul, 1e-7),
            s=6,
            color=pa.DIM,
            lw=0,
            zorder=2,
            label="matched null draws (position-0 null; content null under the content cut)"
            if x == 0
            else None,
        )
    strips(ax, disp, xs, cols, log=True)
    ax.set_yscale("log")
    ax.set_ylim(5e-8, 2)
    from matplotlib.ticker import FixedLocator, FuncFormatter

    # the serif face has no U+2212, so the log labels are set in mathtext
    ax.yaxis.set_major_locator(FixedLocator([10.0**k for k in range(-7, 1)]))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"$10^{{{round(np.log10(v))}}}$"))
    ax.set_xticks(xs)
    ax.set_xticklabels(xt)
    ax.set_ylabel("displacement of the shipped vector, 1 - cosine (log)")
    ax.legend(loc="lower left", **lk)
    pa.panel_title(
        ax,
        f"A. Position 0 is the whole head: median displacement {dm['pos0']:.2f} for the position-0 cut and {dm['all']:.2f} for the whole head; the content cut moves the note {dm['content']:.3f}, the swap {dm['swap']:.0e}",
        52,
    )

    # B: the sink
    ax = fig.add_subplot(gs[0, 1])
    pa.style_axes(ax)
    allx = np.arange(C + 1)
    strips(ax, sink_late, allx, [pa.TEXT] + cols)
    ns = np.concatenate([z["null_sink_specimen"], z["null_sink_pop"].ravel()])
    ax.scatter(
        1 - 0.3 + jit(len(ns), 0.06),
        ns,
        s=6,
        color=pa.DIM,
        lw=0,
        zorder=2,
        label="position-0 null draws",
    )
    ax.set_xticks(allx)
    ax.set_xticklabels(["as shipped"] + xt)
    ax.set_ylim(-0.03, 0.8)
    ax.set_ylabel("median head's share on token 0, blocks 4 to 28")
    ax.legend(loc="center right", **lk)
    pa.panel_title(
        ax,
        f"B. The sink follows position 0: {sm['baseline']:.2f} as shipped, {sm['pos0']:.3f} with the position-0 cut, {sm['content']:.2f} with the content cut, {sm['swap']:.2f} with the mean register swapped in",
        52,
    )

    # C: the massive activation
    ax = fig.add_subplot(gs[0, 2])
    pa.style_axes(ax)
    strips(ax, pos0_norm[:, :, cl + 1], allx, [pa.TEXT] + cols, log=True)
    ax.set_yscale("log")
    ax.set_xticks(allx)
    ax.set_xticklabels(["as shipped"] + xt)
    ax.set_ylabel(f"position 0's residual norm after block {cl + 1} (log)")
    pa.panel_title(
        ax,
        f"C. So does the massive activation: {pm['baseline']:,.0f} as shipped, {pm['pos0']:.0f} with the position-0 cut, {pm['content']:,.0f} with the content cut, {pm['swap']:,.0f} with the swap",
        52,
    )

    # D: the cone
    ax = fig.add_subplot(gs[1, 0])
    pa.style_axes(ax)
    for i in range(N):
        ax.plot(allx, cone[i], color=pa.FRAME, lw=0.6, zorder=1)
    strips(ax, cone, allx, [pa.TEXT] + cols)
    ax.set_xticks(allx)
    ax.set_xticklabels(["as shipped"] + xt)
    ax.set_ylabel("the shipped vector's cosine to the cone")
    pa.panel_title(
        ax,
        f"D. The cone goes with the register: {cm['baseline']:.2f} as shipped, {cm['pos0']:.2f} after the position-0 cut, unchanged after the content cut ({cm['content']:.2f}) and the swap ({cm['swap']:.2f})",
        52,
    )

    # E: the dye
    ax = fig.add_subplot(gs[1, 1])
    pa.style_axes(ax)
    depths = np.arange(L1)
    for j, c in enumerate(CONDITIONS):
        Y = dye[1:, j]
        ax.fill_between(
            depths,
            np.percentile(Y, 25, 0),
            np.percentile(Y, 75, 0),
            color=cols[j],
            alpha=0.15,
            lw=0,
        )
        ax.plot(
            depths,
            np.median(Y, 0),
            color=cols[j],
            lw=2.2,
            ls="--" if c == "all" else "-",
            label=COND_LABEL[c],
        )
    ax.axvline(cl + 1, color=pa.MUTED, lw=0.8, ls=":")
    ax.set_xlim(0, L1 - 1)
    ax.set_ylim(-0.05, 1.05)
    ax.set_xlabel("depth")
    ax.set_ylabel("last position's cosine to the as-shipped run")
    ax.legend(loc="lower left", **lk)
    pa.panel_title(
        ax,
        f"E. The dye by depth: the position-0 cut and the whole head part from the shipped run on the same curve; the content cut and the swap never leave it (final cosine {1 - dm['content']:.3f} and {1 - dm['swap']:.4f})",
        52,
    )

    # F: neighbours moved
    ax = fig.add_subplot(gs[1, 2])
    pa.style_axes(ax)
    w = 0.2
    for j, c in enumerate(CONDITIONS):
        counts = np.bincount(changed[1:, j], minlength=NEIGHBOURS + 1)
        ax.bar(
            np.arange(NEIGHBOURS + 1) + (j - 1.5) * w, counts, w, color=cols[j], label=COND_LABEL[c]
        )
    ax.set_xticks(np.arange(NEIGHBOURS + 1))
    ax.set_xlabel("of the note's 10 nearest neighbours, how many changed")
    ax.set_ylabel("notes (of 20)")
    ax.legend(loc="upper center", **lk)
    pa.panel_title(
        ax,
        f"F. Neighbours: median {r['neighbours_moved_median']['pos0']:.0f} of 10 change under the position-0 cut and {r['neighbours_moved_median']['all']:.0f} under the whole head; {r['neighbours_moved_median']['content']:.0f} under the content cut, {r['neighbours_moved_median']['swap']:.0f} under the swap",
        52,
    )

    pa.verdict(
        fig,
        "POSITION 0 IS THE WHOLE HEAD: the register alone carries the sink, the activation and the cone; the content writes and the register's note-to-note variation carry nothing",
    )
    pa.save(fig, "03-the-split.png")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "tag"
    {
        "tag": tag,
        "valley": valley,
        "split": split,
        "tag_figure": tag_figure,
        "valley_figure": valley_figure,
        "split_figure": split_figure,
    }[cmd]()
