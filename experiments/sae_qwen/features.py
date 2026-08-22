"""Latent activations, per-feature exemplars, and Haiku names.

Stage 1 (--acts): dump the top-k latent activations for every cached vector.
Stage 2 (--name): name the N most-active features from their top-8 activating
texts via ytk.sdk.structured (claude-haiku-4-5). Names are hypotheses, not
probes: nothing here has been causally tested.

    uv run --with torch python experiments/sae_qwen/features.py --ckpt <p> --acts
    YTK_VISUAL_INDEX=off uv run python experiments/sae_qwen/features.py --name --top 100
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from paths import DATA
from pydantic import BaseModel

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))

NAME_SYSTEM = (
    "You name features of a sparse autoencoder trained on document embeddings "
    "from a personal knowledge vault (YouTube transcripts, Instagram/TikTok "
    "captures, web articles, project notes). Given the excerpts that activate "
    "one latent most strongly, state the single concept the latent appears to "
    "detect. Be concrete and specific: name topics, tools, or registers, not "
    "vague abstractions. If the excerpts share nothing, say so."
)


class Name(BaseModel):
    name: str
    confidence: str
    rationale: str


def dump_acts(ckpt: str, device: str = "cpu", batch: int = 2048) -> None:
    import torch
    import train_sae as T

    X = np.load(DATA / "vectors.npz")["X"]
    blob = torch.load(ckpt, map_location=device)
    c = blob["cfg"]
    m = T.TopKSAE(X.shape[1], c["d_sae"], c["k"]).to(device)
    m.load_state_dict(blob["state"])
    m.eval()
    idxs, vals = [], []
    with torch.no_grad():
        for i in range(0, len(X), batch):
            x = torch.as_tensor(X[i : i + batch], device=device)
            pre = m.pre_acts(x)
            v, ix = pre.topk(c["k"], dim=-1)
            idxs.append(ix.cpu().numpy().astype(np.int32))
            vals.append(v.cpu().numpy().astype(np.float32))
    out = DATA / f"acts_{Path(ckpt).stem}.npz"
    np.savez_compressed(
        out, idx=np.concatenate(idxs), val=np.concatenate(vals), d_sae=c["d_sae"], k=c["k"]
    )
    print("wrote", out)


def feature_table(acts_path: Path, rows: list[dict], top: int) -> list[dict]:
    z = np.load(acts_path)
    idx, val, d_sae = z["idx"], z["val"], int(z["d_sae"])
    n = len(idx)
    freq = np.bincount(idx.ravel()[val.ravel() > 0], minlength=d_sae) / n
    order = np.argsort(-freq)[:top]

    # exemplars: strongest activating row per selected feature
    want = {int(f): [] for f in order}
    for r in range(n):
        for j in range(idx.shape[1]):
            f = int(idx[r, j])
            if f in want and val[r, j] > 0:
                want[f].append((float(val[r, j]), r))
    table = []
    for f in order:
        ex = sorted(want[int(f)], reverse=True)[:8]
        table.append(
            {
                "feature": int(f),
                "freq": float(freq[f]),
                "n_fire": len(want[int(f)]),
                "exemplars": [
                    {
                        "act": round(a, 4),
                        "id": rows[r]["id"],
                        "kind": rows[r]["kind"],
                        "source": rows[r]["source"],
                        "title": rows[r]["title"],
                        "text": rows[r]["text"][:420],
                    }
                    for a, r in ex
                ],
            }
        )
    return table


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt")
    ap.add_argument("--acts", action="store_true")
    ap.add_argument("--name", action="store_true")
    ap.add_argument("--top", type=int, default=100)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()

    if a.acts:
        dump_acts(a.ckpt)
        return

    rows = [json.loads(x) for x in (DATA / "rows.jsonl").read_text().splitlines()]
    acts = DATA / f"acts_{Path(a.ckpt).stem}.npz"
    table = feature_table(acts, rows, a.top)

    if a.name:
        from concurrent.futures import ThreadPoolExecutor

        from ytk.sdk import structured

        def name_one(t):
            body = "\n\n".join(
                f"[{e['kind']}/{e['source']}] {e['title'][:80]}\n{e['text'][:380]}"
                for e in t["exemplars"]
            )
            try:
                res = structured(
                    NAME_SYSTEM,
                    f"Latent #{t['feature']} fires on {t['freq'] * 100:.2f}% of documents.\n"
                    f"Its 8 strongest activating excerpts:\n\n{body}\n\n"
                    "Name the concept in at most 6 words. confidence: high|medium|low "
                    "(low if the excerpts look unrelated).",
                    Name,
                    max_tokens=300,
                )
                t["name"] = res.name
                t["name_confidence"] = res.confidence
                t["name_rationale"] = res.rationale
            except Exception as e:
                t["name"] = None
                t["name_error"] = str(e)[:200]
            return t

        with ThreadPoolExecutor(max_workers=a.workers) as ex:
            for i, _ in enumerate(ex.map(name_one, table)):
                if (i + 1) % 10 == 0:
                    print(f"named {i + 1}/{len(table)}", flush=True)
        ok = sum(1 for t in table if t.get("name"))
        print(f"named {ok}/{len(table)} ({len(table) - ok} failed)")

    out = HERE / "features.json"
    out.write_text(
        json.dumps(
            {
                "checkpoint": Path(a.ckpt).name,
                "acts": acts.name,
                "top_by": "firing frequency over all 16,483 cached vectors",
                "naming": "claude-haiku-4-5 via ytk.sdk.structured; UNPROBED hypotheses",
                "features": table,
            },
            indent=1,
        )
    )
    print("wrote", out)


if __name__ == "__main__":
    main()
