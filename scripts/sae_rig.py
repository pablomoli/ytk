#!/usr/bin/env python
"""18.1 — local SAE rig, cross-validated against Neuronpedia (pre-registered).

Loads Gemma 2 2B (unsloth mirror, bf16, CPU — TransformerLens MPS numerics
are unresolved) plus the exact Neuronpedia SAE (gemma-scope-2b-pt-res,
layer 20, 16k, average_l0_71), runs 5 notes of mixed register, and compares
sum-ranked top-10 features against the API's inference on the same texts.

Registered prediction: mean top-10 overlap >= 7/10, shared-feature
activations within 10%. Kill: any note below 5/10 — do not batch on an
unvalidated rig.

    uv run --with sae-lens --with torch python scripts/sae_rig.py
"""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

OUTDIR = Path(__file__).resolve().parents[1] / "docs" / "assets" / "18-sae-fingerprints"
CACHE = OUTDIR / "rig-api-cache"
MODEL_ID = "gemma-2-2b"
LAYER = "20-gemmascope-res-16k"
SAE_RELEASE = "gemma-scope-2b-pt-res"
SAE_ID = "layer_20/width_16k/average_l0_71"
HOOK = "blocks.20.hook_resid_post"
MAX_CHARS = 2000

NOTE_TITLES = [
    "How To De-Slop A Codebase Ruined By AI (with one skill)",
    "Tech interviews with NeetCode",
    "System Design for Beginners (Full Guide)",
    "randyroberts-DWpSK4uDhIO-tribe-brain-heatmap",
    "Turn Claude Into A Design GENIUS In 3 Simple Steps",
]


def api_search_all(text: str, cache_key: str) -> list[dict]:
    CACHE.mkdir(parents=True, exist_ok=True)
    cached = CACHE / f"{cache_key}.json"
    if cached.exists():
        return json.loads(cached.read_text())["result"]
    body = {
        "modelId": MODEL_ID,
        "sourceSet": "gemmascope-res-16k",
        "selectedLayers": [LAYER],
        "sortIndexes": [],
        "text": text,
        "ignoreBos": True,
        "densityThreshold": -1,
        "numResults": 100,
    }
    req = urllib.request.Request(
        "https://www.neuronpedia.org/api/search-all",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        payload = json.loads(resp.read())
    cached.write_text(json.dumps(payload, indent=1))
    return payload["result"]


def sum_rank(per_feature: dict[int, float], k: int = 10) -> list[int]:
    return [i for i, _ in sorted(per_feature.items(), key=lambda p: -p[1])[:k]]


def main() -> None:
    import torch
    from path_blend_demo import note_texts  # name -> text, same keying as harvest
    from sae_lens import SAE, HookedSAETransformer
    from transformers import AutoModelForCausalLM, AutoTokenizer

    texts = note_texts()

    print("loading gemma-2-2b (bf16, cpu) from unsloth mirror ...")
    t0 = time.time()
    hf_model = AutoModelForCausalLM.from_pretrained(
        "unsloth/gemma-2-2b", torch_dtype=torch.bfloat16
    )
    tok = AutoTokenizer.from_pretrained("unsloth/gemma-2-2b")
    model = HookedSAETransformer.from_pretrained_no_processing(
        MODEL_ID, hf_model=hf_model, tokenizer=tok, device="cpu", dtype=torch.bfloat16
    )
    sae = SAE.from_pretrained(release=SAE_RELEASE, sae_id=SAE_ID, device="cpu")
    sae_module = sae[0] if isinstance(sae, tuple) else sae
    print(f"loaded in {time.time() - t0:.0f}s")

    rows = []
    for title in NOTE_TITLES:
        text = texts[title][:MAX_CHARS]
        tokens = model.to_tokens(text)
        t1 = time.time()
        with torch.no_grad():
            _, cache = model.run_with_cache(tokens, names_filter=HOOK)
        acts = sae_module.encode(cache[HOOK].to(sae_module.dtype))[0]  # [seq, 16384]
        secs = time.time() - t1
        acts = acts[1:]  # drop BOS, mirroring ignoreBos on the API side

        sums = acts.sum(0).float()
        local_sum = {int(i): float(sums[i]) for i in sums.nonzero(as_tuple=True)[0].tolist()}
        local_top = sum_rank(local_sum)

        api = api_search_all(text, title[:40].replace("/", "_").replace(" ", "_"))
        api_sum = {int(r["index"]): float(sum(r["values"])) for r in api}
        api_top = sum_rank(api_sum)

        # The API returns only its top-100 features by peak activation; ranking
        # is only comparable inside that shared candidate pool. The unrestricted
        # overlap is kept too — it measures pool truncation, not rig agreement.
        pool = set(api_sum)
        local_top_pooled = sum_rank({i: v for i, v in local_sum.items() if i in pool})
        shared_pooled = set(local_top_pooled) & set(api_top)

        shared = set(local_top) & set(api_top)
        diffs = [
            abs(local_sum[i] - api_sum[i]) / max(api_sum[i], 1e-9)
            for i in shared
            if i in local_sum and i in api_sum
        ]
        rows.append(
            {
                "note": title,
                "tokens": int(tokens.shape[1]),
                "secs_local": round(secs, 1),
                "local_top10": local_top,
                "local_top10_pooled": local_top_pooled,
                "api_top10": api_top,
                "overlap_pooled": len(shared_pooled),
                "overlap_unrestricted": len(shared),
                "median_rel_diff": round(float(sorted(diffs)[len(diffs) // 2]), 4)
                if diffs
                else None,
            }
        )
        print(
            f"{title[:44]:44s} pooled {len(shared_pooled)}/10  "
            f"unrestricted {len(shared)}/10  "
            f"median rel diff {rows[-1]['median_rel_diff']}  {secs:.0f}s/{tokens.shape[1]}tok"
        )

    result = {
        "sae": f"{SAE_RELEASE}/{SAE_ID}",
        "model_source": "unsloth/gemma-2-2b",
        "hook": HOOK,
        "notes": rows,
        "mean_overlap_pooled": round(sum(r["overlap_pooled"] for r in rows) / len(rows), 2),
        "mean_overlap_unrestricted": round(
            sum(r["overlap_unrestricted"] for r in rows) / len(rows), 2
        ),
    }
    (OUTDIR / "rig-validation.json").write_text(json.dumps(result, indent=1))
    print(
        f"\nmean pooled overlap {result['mean_overlap_pooled']}/10  "
        f"(unrestricted {result['mean_overlap_unrestricted']}/10)  -> rig-validation.json"
    )


if __name__ == "__main__":
    main()
