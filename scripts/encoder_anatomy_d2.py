#!/usr/bin/env python
"""Section 60, dissection D2: the residual stream across depth, rung A.

Registered in docs/design/encoder-anatomy/README.md before any call. Every
tagged note (section 10's join, 811 rows today) is run once with hidden
states; at each of the 29 depths (token table, then each block) the last
position's residual state goes through the final RMSNorm and unit length,
"where this note would land if the encoder stopped here". Mean-over-positions
pooling is kept as a disclosed side panel.

READ-ONLY on Chroma and the vault. The per-layer vectors land in
~/.ytk/encoder-anatomy/d2-layers.npz; results and figures in
docs/assets/60-encoder-anatomy-d2/.

    uv run --extra lab python scripts/encoder_anatomy_d2.py harvest   # one pass per note
    uv run --extra lab python scripts/encoder_anatomy_d2.py analyze   # cone and tag accuracy per depth, with nulls
    uv run --extra lab python scripts/encoder_anatomy_d2.py figures
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
SECTION = REPO / "docs" / "assets" / "60-encoder-anatomy-d2"
RESULTS = SECTION / "results.json"
HARVEST = Path(os.path.expanduser("~/.ytk/encoder-anatomy"))
LAYERS = HARVEST / "d2-layers.npz"

SPECIMEN_ID = "UZDiGooFs54"
SEED = 20261031
NULL_DRAWS = 300
MIN_NOTES = 6  # section 10's scorable-tag floor
BUDGET_MIN = 40  # abort above this: the registration said about 15 minutes


def _unit(X: np.ndarray) -> np.ndarray:
    return X / (np.linalg.norm(X, axis=-1, keepdims=True) + 1e-12)


def _rows() -> list[dict]:
    """Section 10's join: every stored row whose note carries interest_tags."""
    import tag_coherence as tc

    from ytk import store
    from ytk.vault import _get_brain_path

    brain = _get_brain_path()
    by_path: dict[str, list[str]] = {}
    for note in (brain / "sources").rglob("*.md"):
        tags = tc.parse_frontmatter_tags(note.read_text(encoding="utf-8", errors="ignore"))
        if tags:
            by_path[str(note)] = tags
    rows = []
    vids = store._videos_collection().get(include=["documents", "metadatas", "embeddings"])
    for i, doc, meta, emb in zip(
        vids["ids"], vids["documents"], vids["metadatas"], vids["embeddings"]
    ):
        tags = [t.strip() for t in store.meta_str(meta, "tags").split(",") if t.strip()]
        if tags:
            rows.append(
                {
                    "key": f"vid::{i}",
                    "doc": doc,
                    "tags": tags,
                    "emb": np.asarray(emb, np.float32),
                    "name": store.meta_str(meta, "title")[:80],
                }
            )
    mem = store._memories_collection().get(include=["documents", "metadatas", "embeddings"])
    for i, doc, meta, emb in zip(mem["ids"], mem["documents"], mem["metadatas"], mem["embeddings"]):
        tags = by_path.get(store.meta_str(meta, "source_path"))
        if tags:
            rows.append(
                {
                    "key": f"mem::{store.meta_str(meta, 'doc_id')}#{i}",
                    "doc": doc,
                    "tags": tags,
                    "emb": np.asarray(emb, np.float32),
                    "name": Path(store.meta_str(meta, "source_path")).stem[:80],
                }
            )
    return rows


def harvest() -> None:
    import torch
    from sentence_transformers import SentenceTransformer

    from ytk import store

    rows = _rows()
    print(f"{len(rows)} tagged rows")
    cfg = store._EPOCHS["v2"]
    m = SentenceTransformer(
        cfg["model"],
        revision=cfg["revision"],
        device="mps",
        model_kwargs={"torch_dtype": torch.float16},
    )
    m.max_seq_length = cfg["max_seq"]
    am = m[0].auto_model
    n, L1, d = len(rows), am.config.num_hidden_layers + 1, am.config.hidden_size
    last = np.zeros((n, L1, d), np.float16)
    meanp = np.zeros((n, L1, d), np.float16)
    resid_norm = np.zeros((n, L1), np.float32)
    n_tok = np.zeros(n, np.int32)
    calib = np.zeros(n, np.float32)
    t0 = time.time()
    for i, r in enumerate(rows):
        feats = m.tokenize([r["doc"]])
        feats = {k: v.to("mps") for k, v in feats.items() if hasattr(v, "to")}
        with torch.no_grad():
            out = am(**feats, output_hidden_states=True)
            hs = torch.stack([h[0] for h in out.hidden_states])  # (L1, T, d) raw residual
            lt = hs[:, -1]
            mp = hs.mean(1)
            resid_norm[i] = lt.float().norm(dim=-1).cpu().numpy()
            # hidden_states[-1] is already through the final norm (Qwen3Model
            # appends it after the loop); only depths 0..27 need the norm applied
            last[i, :-1] = _unit(am.norm(lt[:-1]).float().cpu().numpy()).astype(np.float16)
            last[i, -1] = _unit(lt[-1].float().cpu().numpy()).astype(np.float16)
            meanp[i, :-1] = _unit(am.norm(mp[:-1]).float().cpu().numpy()).astype(np.float16)
            meanp[i, -1] = _unit(mp[-1].float().cpu().numpy()).astype(np.float16)
        n_tok[i] = feats["input_ids"].shape[1]
        calib[i] = float(last[i, -1].astype(np.float32) @ _unit(r["emb"].astype(np.float32)))
        if i == 20 or i % 100 == 0:
            el = time.time() - t0
            est = el / (i + 1) * n / 60
            print(
                f"{i + 1}/{n}  {el:.0f}s elapsed, about {est:.0f} min total; calibration so far min {calib[: i + 1].min():.4f}",
                flush=True,
            )
            if est > BUDGET_MIN:
                raise SystemExit(
                    f"estimated {est:.0f} min exceeds the {BUDGET_MIN} min budget; stopped before the run, nothing written"
                )
    HARVEST.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        LAYERS,
        last=last,
        meanp=meanp,
        resid_norm=resid_norm,
        n_tok=n_tok,
        calib=calib,
        keys=np.array([r["key"] for r in rows]),
        names=np.array([r["name"] for r in rows]),
        tags=np.array([json.dumps(r["tags"]) for r in rows]),
    )
    print(
        f"{n} rows x {L1} depths in {(time.time() - t0) / 60:.1f} min; calibration cos min {calib.min():.5f} median {np.median(calib):.5f} -> {LAYERS}"
    )


FROZEN = HARVEST / "d2-frozen.npz"
FROZEN_BUDGET_MIN = 8 * 60


def harvest_frozen() -> None:
    """Rung B's harvest: every stored row inside the gate's frozen corpus, and
    the 156 queries through the instruction prefix, at every depth. Last token
    through the final norm only; mean pooling was the side panel of rung A."""
    import torch
    from sentence_transformers import SentenceTransformer

    from ytk import retrieval_gate as rg
    from ytk import store

    frozen = rg.load_frozen_ids()
    queries = rg.load_queries(rg.QUERIES_PATH)
    cfg = store._EPOCHS["v2"]
    rows: list[tuple[str, str, str]] = []  # key, kind, document
    for kind, col, key_of in (
        (
            "vid",
            store._videos_collection(),
            lambda i, m: f"vid::{store.meta_str(m, 'video_id') or i}",
        ),
        ("mem", store._memories_collection(), lambda i, m: f"mem::{store.meta_str(m, 'doc_id')}"),
        ("seg", store._segments_collection(), lambda i, m: f"seg::{i}"),
    ):
        total, offset = col.count(), 0
        while offset < total:
            got = col.get(limit=2000, offset=offset, include=["documents", "metadatas"])
            for i, doc, meta in zip(got["ids"], got["documents"], got["metadatas"]):
                k = key_of(i, meta)
                if k in frozen:
                    rows.append((k, kind, doc))
            offset += len(got["ids"])
    texts = [cfg["query_prefix"] + q["query"] for q in queries] + [r[2] for r in rows]
    keys = ["query"] * len(queries) + [r[0] for r in rows]
    kinds = ["query"] * len(queries) + [r[1] for r in rows]
    print(f"{len(rows)} frozen rows + {len(queries)} queries", flush=True)

    m = SentenceTransformer(
        cfg["model"],
        revision=cfg["revision"],
        device="mps",
        model_kwargs={"torch_dtype": torch.float16},
    )
    m.max_seq_length = cfg["max_seq"]
    am = m[0].auto_model
    n, L1, d = len(texts), am.config.num_hidden_layers + 1, am.config.hidden_size
    last = np.zeros((n, L1, d), np.float16)
    n_tok = np.zeros(n, np.int32)
    t0 = time.time()
    # shortest first so the estimate is pessimistic late, not optimistic early
    order = np.argsort([len(t) for t in texts])
    for j, i in enumerate(order):
        feats = m.tokenize([texts[i]])
        feats = {k: v.to("mps") for k, v in feats.items() if hasattr(v, "to")}
        with torch.no_grad():
            out = am(**feats, output_hidden_states=True)
            lt = torch.stack([h[0, -1] for h in out.hidden_states])
            last[i, :-1] = _unit(am.norm(lt[:-1]).float().cpu().numpy()).astype(np.float16)
            last[i, -1] = _unit(lt[-1].float().cpu().numpy()).astype(np.float16)  # already normed
        n_tok[i] = feats["input_ids"].shape[1]
        if j % 500 == 0 or j == n - 1:
            el = time.time() - t0
            print(
                f"{j + 1}/{n}  {el / 60:.0f} min elapsed, {n_tok[order[: j + 1]].sum():,} tokens so far",
                flush=True,
            )
            if el / 60 > FROZEN_BUDGET_MIN:
                raise SystemExit(f"over the {FROZEN_BUDGET_MIN} min budget; nothing written")
    q_cal = [
        float(
            last[i, -1].astype(np.float32)
            @ _unit(np.asarray(store._embed_query(queries[i]["query"]), np.float32))
        )
        for i in range(0, len(queries), 20)
    ]
    HARVEST.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(FROZEN, last=last, n_tok=n_tok, keys=np.array(keys), kinds=np.array(kinds))
    print(
        f"{n} rows x {L1} depths in {(time.time() - t0) / 60:.0f} min; query calibration min {min(q_cal):.5f} -> {FROZEN}"
    )


def exam() -> dict:
    """Rung B: sit the gate at every depth, and with the last four depths averaged."""
    import encoder_anatomy_d1 as d1

    from ytk import retrieval_gate as rg

    z = np.load(FROZEN)
    last, keys, kinds = z["last"], z["keys"], z["kinds"]
    queries = rg.load_queries(rg.QUERIES_PATH)
    frozen = rg.load_frozen_ids()
    resolve = rg._live_resolver()
    baseline = json.loads((REPO / "eval/retrieval/baseline.json").read_text())
    base, tol = baseline["overall"], baseline.get("tolerance", 0.02)
    q = np.flatnonzero(kinds == "query")
    dmask = kinds != "query"
    dkeys, dkinds = keys[dmask], kinds[dmask]
    L1 = last.shape[1]

    def sit(Xd: np.ndarray, Qd: np.ndarray) -> dict:
        rep = rg.evaluate(
            queries,
            d1._searchers(Xd, Qd, dkeys, dkinds, queries),
            resolve,
            top_k=10,
            frozen_ids=frozen,
            fetch_k=d1.FETCH_K,
        )
        return {
            "overall": rep["overall"],
            "per_bucket": rep["per_bucket"],
            "n_evaluated": rep["n_evaluated"],
        }

    depths = []
    for k in range(L1):
        Xd = _unit(last[dmask, k].astype(np.float64))
        Qd = _unit(last[q, k].astype(np.float64))
        rep = sit(Xd, Qd)
        depths.append(rep)
        o = rep["overall"]
        print(
            f"depth {k:2d}  hit@1 {o['hit@1']:.3f}  hit@5 {o['hit@5']:.3f}  hit@10 {o['hit@10']:.3f}",
            flush=True,
        )
    Xd = _unit(last[dmask, -4:].astype(np.float64).mean(1))
    Qd = _unit(last[q, -4:].astype(np.float64).mean(1))
    avg4 = sit(Xd, Qd)
    print(
        "mean of last four depths  " + "  ".join(f"{k} {v:.3f}" for k, v in avg4["overall"].items())
    )

    def ships(o: dict) -> bool:
        return (
            o["hit@5"] > base["hit@5"] + tol
            and o["hit@10"] > base["hit@10"] + tol
            and o["hit@1"] >= base["hit@1"]
        )

    def within(o: dict) -> bool:
        return all(abs(o[k] - base[k]) <= tol for k in ("hit@5", "hit@10"))

    out = {
        "baseline": base,
        "tolerance": tol,
        "depths": depths,
        "avg_last4": avg4,
        "best_depth_hit5": int(np.argmax([d["overall"]["hit@5"] for d in depths])),
        "any_earlier_depth_ships": bool(any(ships(d["overall"]) for d in depths[:-1])),
        "earlier_depths_within_tolerance": [
            k for k, d in enumerate(depths[:-1]) if within(d["overall"])
        ],
        "avg_last4_within_tolerance": within(avg4["overall"]),
        "prediction_3_holds": bool(
            not any(ships(d["overall"]) for d in depths[:-1]) and within(avg4["overall"])
        ),
    }
    r = json.loads(RESULTS.read_text()) if RESULTS.exists() else {}
    r["exam"] = out
    RESULTS.write_text(json.dumps(r, indent=1))
    print(
        f"P3: no earlier depth ships ({not out['any_earlier_depth_ships']}), last-four average within tolerance ({out['avg_last4_within_tolerance']}): {out['prediction_3_holds']}"
    )
    return out


def repair() -> None:
    """Undo the double final norm at depth 28 in a harvest written before the
    fix: norm(norm(x)) = norm(x) * w / rms, so dividing by w recovers it."""
    import torch
    from sentence_transformers import SentenceTransformer

    from ytk import store

    cfg = store._EPOCHS["v2"]
    m = SentenceTransformer(
        cfg["model"],
        revision=cfg["revision"],
        device="cpu",
        model_kwargs={"torch_dtype": torch.float32},
    )
    w = m[0].auto_model.norm.weight.detach().numpy().astype(np.float64)
    z = dict(np.load(LAYERS))
    for name in ("last", "meanp"):
        X = z[name].astype(np.float32)
        X[:, -1] = _unit(X[:, -1].astype(np.float64) / w).astype(np.float32)
        z[name] = X.astype(np.float16)
    rows = _rows()
    emb = {r["key"]: _unit(r["emb"].astype(np.float64)) for r in rows}
    calib = np.array(
        [
            float(z["last"][i, -1].astype(np.float64) @ emb[k])
            for i, k in enumerate(z["keys"])
            if k in emb
        ]
    )
    z["calib"] = calib.astype(np.float32)
    np.savez_compressed(LAYERS, **z)
    print(f"repaired depth 28: calibration cos min {calib.min():.5f} median {np.median(calib):.5f}")


def exam_figure() -> None:
    import plot_assets as pa

    pa.OUTDIR = SECTION
    r = json.loads(RESULTS.read_text())
    e = r["exam"]
    base, tol = e["baseline"], e["tolerance"]
    L1 = len(e["depths"])
    x = np.arange(L1)
    ks = ("hit@1", "hit@5", "hit@10")
    cols = {"hit@1": pa.BLUE, "hit@5": pa.GOLD, "hit@10": pa.CYAN}
    d28 = e["depths"][-1]["overall"]
    a4 = e["avg_last4"]["overall"]
    fig, top = pa.figure(
        18,
        9,
        3,
        "section 60, D2: the exam at every depth, rung B",
        "Would the gate prefer an earlier stop: the 156 frozen queries scored against every document at each of the 29 depths",
        meta=(
            f"Every frozen document ({sum(e['depths'][-1]['per_bucket'][b]['n'] for b in e['depths'][-1]['per_bucket'])} queries evaluated over 11,029 rows) "
            f"and every query taken at the same depth, last token through the final norm, exact cosine, memory parts collapsed, filtered to the frozen ids. "
            f"Baseline stamp hit@1 {base['hit@1']:.3f}, hit@5 {base['hit@5']:.3f}, hit@10 {base['hit@10']:.3f}, tolerance {tol}. "
            f"Depth 28 reproduces it ({d28['hit@1']:.3f} / {d28['hit@5']:.3f} / {d28['hit@10']:.3f}). Best hit@5 at depth {e['best_depth_hit5']}; "
            f"earlier depths inside the tolerance on hit@5 and hit@10: {e['earlier_depths_within_tolerance']}; the mean of the last four depths "
            f"scores {a4['hit@1']:.3f} / {a4['hit@5']:.3f} / {a4['hit@10']:.3f}."
        ),
    )
    gs = fig.add_gridspec(
        1,
        2,
        left=pa.MARGIN,
        right=1 - pa.MARGIN,
        top=top,
        bottom=0.09,
        wspace=0.2,
        width_ratios=[1.4, 1],
    )
    ax = fig.add_subplot(gs[0, 0])
    pa.style_axes(ax)
    for k in ks:
        ax.axhspan(base[k] - tol, base[k] + tol, color=pa.DIM, alpha=0.8, lw=0)
        ax.plot(x, [d["overall"][k] for d in e["depths"]], color=cols[k], lw=2.2, label=k)
        ax.scatter([L1 - 0.5], [a4[k]], color=cols[k], s=60, marker="D", zorder=5)
    ax.text(
        L1 - 0.3,
        a4["hit@1"] - 0.12,
        "mean of\nlast four",
        color=pa.MUTED,
        fontsize=pa.TICK_SIZE,
        ha="right",
    )
    ax.set_xlim(0, L1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("depth (0 = token table, k = after block k)")
    ax.set_ylabel("hit rate on the frozen query set")
    ax.legend(
        loc="upper left",
        fontsize=pa.TICK_SIZE,
        facecolor=pa.PANEL,
        edgecolor=pa.FRAME,
        labelcolor=pa.TEXT,
    )
    pa.panel_title(
        ax, "A. The gate at every depth; grey bands are the baseline's tolerance at each k", 60
    )
    ax = fig.add_subplot(gs[0, 1])
    pa.style_axes(ax)
    bcols = {"videos": pa.BLUE, "memories": pa.GOLD, "segments": pa.RED}
    for b, c in bcols.items():
        ax.plot(
            x,
            [d["per_bucket"].get(b, {}).get("hit@5", 0) for d in e["depths"]],
            color=c,
            lw=2.0,
            label=f"{b} (n={e['depths'][-1]['per_bucket'][b]['n']})",
        )
    ax.set_xlim(0, L1 - 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("depth")
    ax.set_ylabel("hit@5")
    ax.legend(
        loc="upper left",
        fontsize=pa.TICK_SIZE,
        facecolor=pa.PANEL,
        edgecolor=pa.FRAME,
        labelcolor=pa.TEXT,
    )
    pa.panel_title(ax, "B. hit@5 by bucket across depth", 50)
    pa.verdict(
        fig,
        f"P3 {'HOLDS' if e['prediction_3_holds'] else 'FAILS'}: earlier depth ships {e['any_earlier_depth_ships']}, "
        f"last-four mean within tolerance {e['avg_last4_within_tolerance']}",
    )
    pa.save(fig, "03-the-exam-by-depth.png")


def _tag_accuracy(X: np.ndarray, keep: list[str], labels: list[set[str]]) -> float:
    """Leave-one-out nearest-centroid accuracy over the scorable tags: a note
    counts as correct when the nearest centroid (its own tags' centroids
    recomputed without it) is one of its tags."""
    pos = {t: j for j, t in enumerate(keep)}
    index = {t: [i for i, ls in enumerate(labels) if t in ls] for t in keep}
    sums = np.stack([X[idx].sum(0) for idx in index.values()])
    counts = np.array([len(idx) for idx in index.values()], float)
    scores = X @ _unit(sums / counts[:, None]).T  # (n, T), every centroid with the note inside
    correct = 0
    scored = 0
    for i, ls in enumerate(labels):
        own = [pos[t] for t in ls if t in pos]
        if not own:
            continue
        scored += 1
        row = scores[i].copy()
        for j in own:
            adj = (sums[j] - X[i]) / max(counts[j] - 1, 1)
            row[j] = X[i] @ adj / (np.linalg.norm(adj) + 1e-12)
        correct += int(np.argmax(row)) in own
    return correct / scored


def analyze() -> dict:
    z = np.load(LAYERS)
    last, meanp = z["last"].astype(np.float32), z["meanp"].astype(np.float32)
    labels = [set(json.loads(t)) for t in z["tags"]]
    n, L1, d = last.shape
    rng = np.random.default_rng(SEED)
    counts = Counter(t for ls in labels for t in ls)
    keep = sorted([t for t, c in counts.items() if c >= MIN_NOTES], key=lambda t: -counts[t])
    t0 = time.time()

    iso_norm = [
        float(np.linalg.norm(_unit(rng.standard_normal((n, d))).mean(0))) for _ in range(NULL_DRAWS)
    ]
    out = {
        "n": n,
        "depths": L1,
        "d": d,
        "n_tags": len(keep),
        "min_notes": MIN_NOTES,
        "calibration": {"min": float(z["calib"].min()), "median": float(np.median(z["calib"]))},
        "null_isotropic_mean_norm": [float(np.mean(iso_norm)), float(np.std(iso_norm))],
        "tokens": {"median": int(np.median(z["n_tok"])), "max": int(z["n_tok"].max())},
    }
    for pool, X_all in (("last", last), ("mean", meanp)):
        cone, pair, acc, acc_null, acc_z = [], [], [], [], []
        for k in range(L1):
            X = X_all[:, k]
            mu = X.mean(0)
            cone.append(float(np.linalg.norm(mu)))
            G = X @ X.T
            pair.append(float((G.sum() - np.trace(G)) / (n * (n - 1))))
            a = _tag_accuracy(X, keep, labels)
            draws = []
            for _ in range(NULL_DRAWS if pool == "last" else 60):
                draws.append(_tag_accuracy(X, keep, _permuted(labels, rng.permutation(n))))
            acc.append(a)
            acc_null.append([float(np.mean(draws)), float(np.std(draws))])
            acc_z.append(float((a - np.mean(draws)) / (np.std(draws) + 1e-12)))
            print(
                f"[{pool}] depth {k:2d}  ||mu|| {cone[-1]:.3f}  pair cos {pair[-1]:.3f}  tag acc {a:.3f}  null {acc_null[-1][0]:.3f}±{acc_null[-1][1]:.3f}  z {acc_z[-1]:.1f}",
                flush=True,
            )
        final = acc[-1]
        sat = next((k for k, a in enumerate(acc) if a >= 0.9 * final), None)
        out[pool] = {
            "cone": cone,
            "pair_cos": pair,
            "tag_acc": acc,
            "tag_acc_null": acc_null,
            "tag_acc_z": acc_z,
            "saturation_depth": sat,
            "cone_max_depth": int(np.argmax(cone)),
            "separating_depths": [k for k, zz in enumerate(acc_z) if zz > 3],
        }
    out["resid_norm_median"] = np.median(z["resid_norm"], axis=0).tolist()
    cl, ca = out["last"]["cone"], out["last"]["tag_acc"]
    out["prediction_1"] = {
        "cone_present_every_depth": bool(
            all(c > 5 * out["null_isotropic_mean_norm"][0] for c in cl)
        ),
        "cone_max_depth": out["last"]["cone_max_depth"],
        "holds": bool(
            all(c > 5 * out["null_isotropic_mean_norm"][0] for c in cl)
            and out["last"]["cone_max_depth"] >= L1 - 3
        ),
    }
    out["prediction_2"] = {
        "saturation_depth": out["last"]["saturation_depth"],
        "bar": 20,
        "rises": bool(ca[-1] > ca[0]),
        "holds": bool(
            out["last"]["saturation_depth"] is not None
            and out["last"]["saturation_depth"] <= 20
            and ca[-1] > ca[0]
        ),
    }
    out["seconds"] = round(time.time() - t0)
    SECTION.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(out, indent=1))
    print(
        f"P1 cone at every depth, max at depth {out['last']['cone_max_depth']}: {out['prediction_1']['holds']}"
    )
    print(
        f"P2 saturation depth {out['last']['saturation_depth']} (bar 20): {out['prediction_2']['holds']}"
    )
    return out


def _permuted(labels: list[set[str]], perm: np.ndarray) -> list[set[str]]:
    return [labels[int(j)] for j in perm]


def figures() -> None:
    import matplotlib.pyplot as plt
    import plot_assets as pa

    pa.OUTDIR = SECTION
    r = json.loads(RESULTS.read_text())
    z = np.load(LAYERS)
    last = z["last"].astype(np.float32)
    keys = z["keys"]
    labels = [set(json.loads(t)) for t in z["tags"]]
    n, L1, d = last.shape
    sp = (
        int(np.flatnonzero(keys == f"vid::{SPECIMEN_ID}")[0])
        if (keys == f"vid::{SPECIMEN_ID}").any()
        else None
    )

    # one projection, fitted on the final depth and held fixed for every frame
    Xf = last[:, -1]
    mu_f = Xf.mean(0)
    U, S, Vt = np.linalg.svd(Xf - mu_f, full_matrices=False)
    W = Vt[:2].T
    proj = np.einsum("nkd,de->nke", last - mu_f, W)  # (n, L1, 2)
    lim = float(np.abs(proj[:, -1]).max()) * 1.08
    counts = Counter(t for ls in labels for t in ls)
    top_tags = [t for t, _ in counts.most_common(6)]
    cols = [pa.GOLD, pa.BLUE, pa.RED, pa.PURPLE, pa.CYAN, "#7bd389"]
    colour = np.full(n, pa.DIM, dtype=object)
    for t, c in zip(reversed(top_tags), reversed(cols)):
        for i, ls in enumerate(labels):
            if t in ls:
                colour[i] = c

    rl = r["last"]
    fig, top = pa.figure(
        18,
        12,
        1,
        "section 60, D2: the residual stream across depth, rung A",
        "The growth film: where every tagged note would land if the encoder stopped at each block, one projection fitted on the last depth and held fixed",
        meta=(
            f"{n} tagged rows, {r['n_tags']} scorable tags, median {r['tokens']['median']} tokens. Each depth: the last position's residual "
            f"state through the final RMSNorm, unit length; depth 0 is the token table, depth 28 the shipped vector (calibration cosine "
            f"min {r['calibration']['min']:.4f}). Cone max at depth {rl['cone_max_depth']}; tag accuracy saturates (90% of final) at depth "
            f"{rl['saturation_depth']}; depths separating topics at z > 3: {len(rl['separating_depths'])} of {L1}. Axes: the final depth's "
            f"first two principal directions. Colour: the six commonest tags; the specimen wears its cyan thread."
        ),
    )
    gs = fig.add_gridspec(
        3,
        6,
        left=pa.MARGIN,
        right=1 - pa.MARGIN,
        top=top,
        bottom=0.06,
        hspace=0.36,
        wspace=0.14,
        height_ratios=[1, 1, 1.15],
    )
    # six film frames on two rows, then the two curves on the third
    axes = [fig.add_subplot(gs[j // 3, (j % 3) * 2 : (j % 3) * 2 + 2]) for j in range(6)]
    for ax, k in zip(axes, [0, 12, 18, 21, 24, 28]):
        pa.style_axes(ax)
        P = proj[:, k]
        ax.scatter(P[:, 0], P[:, 1], s=6, c=list(colour), lw=0, alpha=0.85)
        if sp is not None:
            ax.plot(proj[sp, : k + 1, 0], proj[sp, : k + 1, 1], color=pa.CYAN, lw=1.2, alpha=0.9)
            ax.scatter([P[sp, 0]], [P[sp, 1]], s=70, color=pa.CYAN, marker="*", zorder=5)
        ax.set_xlim(-lim, lim)
        ax.set_ylim(-lim, lim)
        ax.set_xticks([])
        ax.set_yticks([])
        pa.panel_title(
            ax,
            f"depth {k}: ||mean|| {rl['cone'][k]:.2f}, tag accuracy {rl['tag_acc'][k] * 100:.0f}% (shuffled {rl['tag_acc_null'][k][0] * 100:.0f}%)",
            44,
        )
    for t, c in zip(top_tags, cols):
        axes[0].scatter([], [], color=c, s=20, label=t)
    axes[0].legend(
        loc="upper left",
        fontsize=pa.TICK_SIZE - 1,
        facecolor=pa.PANEL,
        edgecolor=pa.FRAME,
        labelcolor=pa.TEXT,
    )

    x = np.arange(L1)
    ax = fig.add_subplot(gs[2, :3])
    pa.style_axes(ax)
    ax.plot(
        x,
        rl["cone"],
        color=pa.GOLD,
        lw=2.2,
        label="last token through the final norm (production pooling)",
    )
    ax.plot(
        x,
        r["mean"]["cone"],
        color=pa.MUTED,
        lw=1.2,
        ls="--",
        label="mean over positions (side panel)",
    )
    ax.axhline(
        r["null_isotropic_mean_norm"][0], color=pa.DIM, lw=2.5, label="isotropic null, same n and d"
    )
    ax.axvline(rl["cone_max_depth"], color=pa.RED, lw=0.8, ls=":")
    ax.set_xlim(0, L1 - 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("depth (0 = token table, k = after block k)")
    ax.set_ylabel("length of the mean vector")
    ax.legend(
        loc="lower left",
        fontsize=pa.TICK_SIZE,
        facecolor=pa.PANEL,
        edgecolor=pa.FRAME,
        labelcolor=pa.TEXT,
    )
    pa.panel_title(
        ax,
        f"A. The cone across depth: {rl['cone'][0]:.2f} at the token table (every note ends in the same token), eroded with depth, {rl['cone'][-2]:.2f} after block 27 and {rl['cone'][-1]:.2f} after block 28",
        60,
    )

    ax = fig.add_subplot(gs[2, 3:])
    pa.style_axes(ax)
    nm = np.array(rl["tag_acc_null"])
    ax.fill_between(
        x,
        nm[:, 0] - 3 * nm[:, 1],
        nm[:, 0] + 3 * nm[:, 1],
        color=pa.DIM,
        alpha=0.9,
        lw=0,
        label="labels shuffled, 300 draws, ±3 sd",
    )
    ax.plot(
        x, rl["tag_acc"], color=pa.GOLD, lw=2.2, label="leave-one-out nearest centroid, last token"
    )
    ax.plot(x, r["mean"]["tag_acc"], color=pa.MUTED, lw=1.2, ls="--", label="mean over positions")
    ax.axhline(0.9 * rl["tag_acc"][-1], color=pa.RED, lw=0.8, ls=":")
    if rl["saturation_depth"] is not None:
        ax.axvline(rl["saturation_depth"], color=pa.RED, lw=0.8, ls=":")
        ax.text(
            rl["saturation_depth"] - 0.3,
            0.05,
            f"90% of final at depth {rl['saturation_depth']} (bar: 20)",
            color=pa.RED,
            fontsize=pa.TICK_SIZE,
            ha="right",
        )
    ax.set_xlim(0, L1 - 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("depth")
    ax.set_ylabel(f"tag accuracy over {r['n_tags']} tags")
    ax.legend(
        loc="upper left",
        fontsize=pa.TICK_SIZE,
        facecolor=pa.PANEL,
        edgecolor=pa.FRAME,
        labelcolor=pa.TEXT,
    )
    pa.panel_title(
        ax,
        f"B. Topics across depth: {rl['tag_acc'][0] * 100:.0f}% at the token table, {rl['tag_acc'][-1] * 100:.0f}% at the top, shuffled labels {nm[-1, 0] * 100:.0f}%",
        60,
    )
    p1, p2 = r["prediction_1"], r["prediction_2"]
    pa.verdict(
        fig,
        f"P1 cone every depth, max at or near the top: {'HOLDS' if p1['holds'] else 'FAILS'} (max at {p1['cone_max_depth']}); "
        f"P2 saturation by block 20: {'HOLDS' if p2['holds'] else 'FAILS'} (depth {p2['saturation_depth']})",
    )
    pa.save(fig, "01-the-growth.png")

    # the film itself: 29 frames
    import matplotlib.animation as anim

    fig2 = plt.figure(figsize=(8, 8), facecolor=pa.BG)
    ax = fig2.add_axes([0.02, 0.02, 0.96, 0.9])
    pa.style_axes(ax)
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    ax.set_xticks([])
    ax.set_yticks([])
    sc = ax.scatter(proj[:, 0, 0], proj[:, 0, 1], s=10, c=list(colour), lw=0, alpha=0.85)
    (thread,) = ax.plot([], [], color=pa.CYAN, lw=1.4)
    star = ax.scatter([], [], s=120, color=pa.CYAN, marker="*", zorder=5)
    title = fig2.text(0.04, 0.95, "", color=pa.TEXT, fontsize=13, va="center")

    def update(k):
        sc.set_offsets(proj[:, k])
        if sp is not None:
            thread.set_data(proj[sp, : k + 1, 0], proj[sp, : k + 1, 1])
            star.set_offsets(proj[sp, k : k + 1])
        title.set_text(
            f"depth {k:2d}   ||mean|| {rl['cone'][k]:.2f}   tag accuracy {rl['tag_acc'][k] * 100:.0f}%"
        )
        return sc, thread, star, title

    a = anim.FuncAnimation(fig2, update, frames=L1, interval=350, blit=False)
    out = SECTION / "02-the-growth-film.gif"
    a.save(out, writer="pillow", fps=3, savefig_kwargs={"facecolor": pa.BG})
    print(f"wrote {out.relative_to(REPO)}  ({out.stat().st_size // 1024}KB)")
    plt.close(fig2)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "harvest"
    {
        "harvest": harvest,
        "analyze": analyze,
        "figures": figures,
        "harvest_frozen": harvest_frozen,
        "exam": exam,
        "repair": repair,
        "exam_figure": exam_figure,
    }[cmd]()
