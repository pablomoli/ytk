"""Section 53 rung 0.5: five sequential arms on the same 30 frozen pairs.

    uv run python scripts/lsd_pilot.py --base 20260824-234313 [--arms A1,A2,A3,A5]

Each arm is its own run file (<base>-A?.json) beside the base run, plus a
vectors file (<base>-A?.npy) with one embedding per candidate, so every arm
is resumable and the newness gates are recomputed from disk. pilot.json
next to them carries the per-arm gate readouts. See the README's rung 0.5
pre-registration for what each arm changes and what was predicted.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ytk import lsd

PER_POOL = 10
ARMS = ("A0", "A1", "A2", "A3", "A5", "A6", "A7")
K_SAMPLES = 4


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def vec_path(run_id: str) -> Path:
    return lsd.run_path(run_id).with_suffix(".npy")


def embed_all(run: lsd.Run, run_id: str) -> lsd.Vec:
    """Embed every candidate once; cached beside the run, keyed by count."""
    path = vec_path(run_id)
    if path.exists():
        C = np.load(path)
        if len(C) == len(run.candidates):
            return C
    C = lsd._embed_documents([f"{c.title}\n{c.body}" for c in run.candidates])  # pyright: ignore[reportPrivateUsage]
    np.save(path, C)
    return C


def subset_pairs(base: lsd.Run) -> list[int]:
    rng = np.random.default_rng(base.seed)
    picked: list[int] = []
    for pool in lsd.POOLS:
        idx = [k for k, p in enumerate(base.pairs) if p.pool == pool]
        picked.extend(int(i) for i in rng.choice(idx, size=PER_POOL, replace=False))
    return picked


def arm_run(base: lsd.Run, arm: str, picked: list[int]) -> lsd.Run:
    run_id = f"{base.run_id}-{arm}"
    if lsd.run_path(run_id).exists():
        return lsd.load_run(run_id)
    if arm in ("A5", "A7"):
        run = lsd.latent_run(base.seed + 5, len(picked), run_id)
    else:
        run = lsd.Run(
            run_id=run_id,
            seed=base.seed,
            n_notes=base.n_notes,
            mean_norm=base.mean_norm,
            tail=base.tail,
            background_std=base.background_std,
            notes=base.notes,
            pairs=[base.pairs[i] for i in picked],
        )
        if arm == "A0":
            for new_index, old_index in enumerate(picked):
                for c in base.candidates:
                    if c.pair_index == old_index:
                        run.candidates.append(
                            lsd.Candidate(
                                id=f"{run_id}-{new_index}-{c.kind}",
                                pair_index=new_index,
                                kind=c.kind,
                                title=c.title,
                                body=c.body,
                                judge=c.judge,
                            )
                        )
    lsd.save_run(run)
    return run


def generate_arm(run: lsd.Run, arm: str) -> None:
    if arm == "A0":
        return
    model = lsd.SONNET if arm == "A3" else None
    samples = K_SAMPLES if arm in ("A2", "A6", "A7") else 1
    gen = lsd.generate_v3 if arm in ("A6", "A7") else lsd.generate_v2
    gen(
        run,
        lsd.structured_with_model(model),
        samples=samples,
        checkpoint=lsd.save_run,
        log=log,
    )


def kept_rows(run: lsd.Run, arm: str, C: lsd.Vec, mu: lsd.Vec) -> list[int]:
    if arm in ("A2", "A6", "A7"):
        return lsd.select_farthest(run, C, mu)
    return list(range(len(run.candidates)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--arms", default=",".join(ARMS))
    args = ap.parse_args()
    base = lsd.load_run(args.base)
    picked = subset_pairs(base)
    notes, X = lsd.load_notes()
    ids = {n.id for n in base.notes}
    X = X[[k for k, n in enumerate(notes) if n.id in ids]]
    mu = X.mean(axis=0)
    out_path = lsd.run_path(base.run_id).with_name(f"{base.run_id}-pilot.json")
    results: dict[str, object] = (
        json.loads(out_path.read_text())
        if out_path.exists()
        else {"base": base.run_id, "pairs": picked, "arms": {}}
    )
    arms_out = results["arms"]
    assert isinstance(arms_out, dict)

    for arm in args.arms.split(","):
        log(f"== {arm}")
        run = arm_run(base, arm, picked)
        generate_arm(run, arm)
        if not run.candidates:
            log(f"{arm}: no candidates, skipping")
            continue
        lsd.judge(run, np.random.default_rng(run.seed + 7), log=log)
        lsd.save_run(run)
        C = embed_all(run, run.run_id)
        rows = kept_rows(run, arm, C, mu)
        # Latent parents are not notes, so nothing is excluded from A5's N3.
        report = lsd.newness(run, rows, C, X, exclude_parents=arm not in ("A5", "A7"))
        report["kept"] = len(rows)
        report["judge_mean"] = float(np.mean([run.candidates[r].judge or 0.0 for r in rows]))
        if arm in ("A2", "A6"):
            # A4 lives here: novelty-first vs judge-first top-5 over A2's kept ideas.
            report["a4"] = lsd.rank_compare(run, rows, C, X)
        arms_out[arm] = report
        out_path.write_text(json.dumps(results, indent=1))
        log(
            f"{arm}: "
            + ", ".join(
                f"{k} {v:.3f}" if isinstance(v, float) else f"{k} {v}"
                for k, v in report.items()
                if k not in ("per_kind", "per_pool", "a4")
            )
        )
    log(f"pilot -> {out_path}")


if __name__ == "__main__":
    main()
