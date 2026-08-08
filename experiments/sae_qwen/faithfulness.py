"""Does an index of SAE reconstructions still retrieve what the real one does?

Instrument only. Production search is untouched and no baseline is re-stamped.
Mirrors the retrieval-gate ranking in numpy over the cached vectors: videos
collapse per video_id, memories per doc_id, the two merge by cosine distance
(retrieval_gate._live_searchers), segments rank in their own collection.
Reranking and the reflected boost are off — both are metadata/text stages
that would mask the embedding effect under test.

Queries keep their real Qwen embeddings; only the index is reconstructed.

    uv run --with torch python experiments/sae_qwen/faithfulness.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DATA = HERE / "data"
FROZEN = REPO / "eval" / "retrieval" / "frozen_corpus.json"


def load_rows():
    return [json.loads(x) for x in (DATA / "rows.jsonl").read_text().splitlines()]


def eval_keys(rows):
    """retrieval-gate key space per pulled vector, plus its collapse group."""
    keys = []
    for r in rows:
        if r["kind"] == "segment":
            keys.append(f"seg::{r['id']}")
        else:
            keys.append(r["note_key"])  # vid::<video_id> / mem::<doc_id>
    return np.array(keys)


def resolve_golds(rows, golds):
    """mem:: fixture golds carry vault-relative paths; live ids are opaque."""
    by_path = {}
    for r in rows:
        if r["kind"] == "memory" and r["source_path"]:
            by_path[r["source_path"]] = r["note_key"]
    out = []
    for g in golds:
        kind, _, key = g.partition("::")
        if kind == "mem":
            hit = next((v for sp, v in by_path.items() if sp.endswith(key)), None)
            out.append(hit)
        else:
            out.append(g)
    return out


def rank(qv, M, keys, group, frozen, top_k=10):
    """Best-scoring row per collapse group, frozen-filtered, top_k keys."""
    sims = M @ qv
    order = np.argsort(-sims)
    seen, out = set(), []
    for i in order:
        g = group[i]
        if g in seen:
            continue
        seen.add(g)
        k = keys[i]
        if k not in frozen:
            continue
        out.append(k)
        if len(out) == top_k:
            break
    return out


def score(Xidx, rows, qz, frozen, top_k=10):
    keys = eval_keys(rows)
    kind = np.array([r["kind"] for r in rows])
    group = np.array([r["note_key"] if r["kind"] != "segment" else f"seg::{r['id']}" for r in rows])
    unified_mask = kind != "segment"
    seg_mask = kind == "segment"

    golds = resolve_golds(rows, qz["gold"].tolist())
    per_query = []
    for i, (q, b, g) in enumerate(zip(qz["Q"], qz["bucket"], golds)):
        m = seg_mask if b == "segments" else unified_mask
        res = rank(q, Xidx[m], keys[m], group[m], frozen, top_k)
        per_query.append(
            {"bucket": str(b), "gold": g, "results": res, "query": str(qz["query"][i])}
        )
    return per_query


def summarize(orig, recon, top_k=10):
    ov, hits_o, hits_r = [], {1: 0, 5: 0, 10: 0}, {1: 0, 5: 0, 10: 0}
    top1_same = 0
    n = 0
    by_bucket = {}
    for a, b in zip(orig, recon):
        if a["gold"] is None:
            continue
        n += 1
        o = len(set(a["results"]) & set(b["results"])) / top_k
        ov.append(o)
        top1_same += int(
            bool(a["results"]) and bool(b["results"]) and a["results"][0] == b["results"][0]
        )
        for k in (1, 5, 10):
            hits_o[k] += int(a["gold"] in a["results"][:k])
            hits_r[k] += int(b["gold"] in b["results"][:k])
        d = by_bucket.setdefault(a["bucket"], {"n": 0, "ov": [], "ho5": 0, "hr5": 0})
        d["n"] += 1
        d["ov"].append(o)
        d["ho5"] += int(a["gold"] in a["results"][:5])
        d["hr5"] += int(b["gold"] in b["results"][:5])
    return {
        "n_scored": n,
        "overlap@10": float(np.mean(ov)),
        "top1_agreement": top1_same / n,
        "orig": {f"hit@{k}": hits_o[k] / n for k in (1, 5, 10)},
        "recon": {f"hit@{k}": hits_r[k] / n for k in (1, 5, 10)},
        "delta": {f"hit@{k}": (hits_r[k] - hits_o[k]) / n for k in (1, 5, 10)},
        "per_bucket": {
            k: {
                "n": v["n"],
                "overlap@10": float(np.mean(v["ov"])),
                "orig_hit@5": v["ho5"] / v["n"],
                "recon_hit@5": v["hr5"] / v["n"],
            }
            for k, v in by_bucket.items()
        },
    }


def reconstruct(ckpt_path, X, device="cpu", batch=4096):
    import train_sae as T

    blob = torch.load(ckpt_path, map_location=device)
    c = blob["cfg"]
    m = T.TopKSAE(X.shape[1], c["d_sae"], c["k"]).to(device)
    m.load_state_dict(blob["state"])
    m.eval()
    out = []
    with torch.no_grad():
        for i in range(0, len(X), batch):
            xh, *_ = m(torch.as_tensor(X[i : i + batch], device=device))
            out.append(xh.cpu().numpy())
    R = np.concatenate(out)
    return R / np.maximum(np.linalg.norm(R, axis=1, keepdims=True), 1e-9)


def main():
    import sys

    sys.path.insert(0, str(HERE))
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpts", nargs="*", default=None)
    ap.add_argument("--out", default="faithfulness.json")
    a = ap.parse_args()

    X = np.load(DATA / "vectors.npz")["X"]
    rows = load_rows()
    qz = np.load(DATA / "queries.npz", allow_pickle=True)
    frozen = set(json.loads(FROZEN.read_text())["ids"])

    base = score(X, rows, qz, frozen)
    report = {"frozen_size": len(frozen), "configs": {}}
    ckpts = a.ckpts or sorted(str(p) for p in (HERE / "checkpoints").glob("sae_*.pt"))
    for c in ckpts:
        R = reconstruct(c, X)
        s = summarize(base, score(R, rows, qz, frozen))
        report["configs"][Path(c).stem] = s
        print(
            Path(c).stem,
            f"overlap@10 {s['overlap@10']:.3f}",
            f"hit@5 {s['orig']['hit@5']:.3f} -> {s['recon']['hit@5']:.3f}",
            f"({s['delta']['hit@5']:+.3f})",
        )
    report["mirror_original"] = {
        "n_scored": summarize(base, base)["n_scored"],
        "hit": summarize(base, base)["orig"],
    }
    (HERE / a.out).write_text(json.dumps(report, indent=1))
    print("wrote", HERE / a.out)


if __name__ == "__main__":
    main()
