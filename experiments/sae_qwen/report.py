"""Collect every measured number of E2 into one report.json."""

from __future__ import annotations

import glob
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def group(tag):
    return [
        json.loads(Path(f).read_text())[0]
        for f in sorted(glob.glob(str(HERE / f"results_{tag}_s*.json")))
    ]


def cond(rs):
    v = [r["val"]["recon_cos"] for r in rs]
    return {
        "seeds": [round(x, 4) for x in v],
        "mean": round(float(np.mean(v)), 4),
        "sd": round(float(np.std(v)), 4),
        "in_dist": round(float(np.mean([r["val_in_dist"]["recon_cos"] for r in rs])), 4),
        "out_dist": round(float(np.mean([r["val_out_dist"]["recon_cos"] for r in rs])), 4),
        "dead_pct": round(float(100 * np.mean([r["dead_frac_on_train"] for r in rs])), 3),
        "l0": round(float(np.mean([r["val"]["l0"] for r in rs])), 2),
        "best_step": [r["best_step"] for r in rs],
    }


def faith_group(blob, pred):
    rs = [v for k, v in blob["configs"].items() if pred(k)]
    return {
        "overlap@10": round(float(np.mean([r["overlap@10"] for r in rs])), 4),
        "top1_agreement": round(float(np.mean([r["top1_agreement"] for r in rs])), 4),
        "recon_hit@5": round(float(np.mean([r["recon"]["hit@5"] for r in rs])), 4),
        "recon_hit@5_seeds": [round(r["recon"]["hit@5"], 4) for r in rs],
        "delta_hit@5": round(float(np.mean([r["delta"]["hit@5"] for r in rs])), 4),
        "delta_hit@1": round(float(np.mean([r["delta"]["hit@1"] for r in rs])), 4),
        "delta_hit@10": round(float(np.mean([r["delta"]["hit@10"] for r in rs])), 4),
        "per_bucket_overlap": {
            b: round(float(np.mean([r["per_bucket"][b]["overlap@10"] for r in rs])), 4)
            for b in rs[0]["per_bucket"]
        },
    }


def main() -> None:
    sweep = json.loads((HERE / "sweep_table.json").read_text())
    faith = json.loads((HERE / "faithfulness.json").read_text())
    faith_f = json.loads((HERE / "faithfulness_final.json").read_text())
    taste = json.loads((HERE / "taste.json").read_text())
    stab = json.loads((HERE / "stability.json").read_text())
    feats = json.loads((HERE / "features.json").read_text())["features"]

    rep = {
        "experiment": "E2 — top-k SAE trained natively on the production Qwen v2 space",
        "data": {
            "vectors": 16483,
            "dim": 1024,
            "notes": 5026,
            "by_kind": {"segment": 11412, "memory": 4726, "video": 345},
            "in_distribution": {
                "vectors": 12034,
                "notes": 610,
                "definition": "videos + segments + memories under interest.content_sources",
            },
            "duplicates_dropped": 3,
            "val_split": "10% of note keys held out; a note's segments never straddle the split",
        },
        "sweep_4k_steps": sweep,
        "conditions": {
            "plateau_2048_k32_14k": cond(group("final")),
            "plateau_2048_k32_14k_content_sources_only": cond(group("restrict")),
            "fixed_split_inits": cond(group("fixsplit")),
        },
        "faithfulness": {
            "instrument": "numpy mirror of the production ranking; reproduces "
            "eval/retrieval/baseline.json exactly",
            "mirror_original_hit": faith["mirror_original"]["hit"],
            "baseline_hit": {"hit@1": 0.7115384615, "hit@5": 0.9038461538, "hit@10": 0.9423076923},
            "by_config": {
                f"d{d}_k{k}": faith_group(
                    faith, lambda key, d=d, k=k: key.startswith(f"sae_d{d}_k{k}_")
                )
                for d in (2048, 4096)
                for k in (16, 32)
            },
            "plateau_2048_k32": faith_group(faith_f, lambda key: True),
        },
        "stability": stab,
        "taste": {
            k: {kk: vv for kk, vv in taste[k].items() if kk != "auc_all"}
            for k in ("A_deliberate", "B_thought", "C_thought_instagram")
        }
        | {"raw_baseline": taste["raw_baseline"], "n_notes": taste["n_notes"], "C": taste["C"]},
        "named_features": {
            "checkpoint": "final_d2048_k32_s0.pt",
            "n_named": len([f for f in feats if f.get("name")]),
            "confidence": {
                c: sum(1 for f in feats if f.get("name_confidence") == c)
                for c in ("high", "medium", "low")
            },
        },
    }
    (HERE / "report.json").write_text(json.dumps(rep, indent=1))
    print(json.dumps(rep["faithfulness"]["by_config"], indent=1))
    print(json.dumps(rep["faithfulness"]["plateau_2048_k32"], indent=1))
    print(json.dumps(rep["conditions"], indent=1))
    print("wrote", HERE / "report.json")


if __name__ == "__main__":
    main()
