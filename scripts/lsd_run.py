"""Section 53 rung 0: generate, judge, and measure novelty for one frozen run.

    uv run python scripts/lsd_run.py --run RUN_ID [--limit N] [--stage all|generate|judge|novelty|deck]

Resumable: every generated pair is checkpointed to the run file, so a
crash or a Ctrl-C loses at most one model call. The deck is written next
to the run with pool labels stripped.
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


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument(
        "--stage", default="all", choices=["all", "generate", "judge", "novelty", "deck"]
    )
    ap.add_argument(
        "--limit", type=int, default=None, help="generate at most N pairs this invocation"
    )
    args = ap.parse_args()
    run = lsd.load_run(args.run)
    log(f"run {run.run_id}: {len(run.pairs)} pairs, {len(run.candidates)} candidates so far")

    if args.stage in ("all", "generate"):
        if args.limit is not None:
            done = {c.pair_index for c in run.candidates}
            todo = [i for i in range(len(run.pairs)) if i not in done][: args.limit]
            for index in todo:
                run.candidates.extend(lsd.generate_pair(run, index))
                lsd.save_run(run)
                log(f"generated pair {index} ({run.pairs[index].pool})")
        else:
            lsd.generate(run, checkpoint=lsd.save_run, log=log)
        log(f"generation done: {len(run.candidates)} candidates")

    if args.stage in ("all", "judge"):
        lsd.judge(run, np.random.default_rng(run.seed + 7), log=log)
        lsd.save_run(run)
        scored = sum(c.judge is not None for c in run.candidates)
        log(f"judge done: {scored}/{len(run.candidates)} scored")

    if args.stage in ("all", "novelty"):
        notes, X = lsd.load_notes()
        if len(notes) != run.n_notes:
            log(f"store grew {run.n_notes} -> {len(notes)}; novelty uses the run's own note order")
            ids = {n.id for n in run.notes}
            keep = [k for k, n in enumerate(notes) if n.id in ids]
            X = X[keep]
        lsd.novelty(run, X)
        lsd.save_run(run)
        log("novelty done")

    if args.stage in ("all", "deck"):
        deck = lsd.build_deck(run, np.random.default_rng(run.seed + 11))
        out = lsd.run_path(run.run_id).with_name(f"{run.run_id}-deck.json")
        out.write_text(json.dumps(deck, indent=1))
        log(f"deck: {len(deck)} cards -> {out}")


if __name__ == "__main__":
    main()
