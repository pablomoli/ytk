"""`ytk lsd` — sample, generate, judge, deck, and score one run.

Every subcommand is a thin call into `ytk.lsd`; `scripts/lsd_run.py` is the
section's reproducibility entry and calls the same functions.
"""

from __future__ import annotations

import json

import click
import numpy as np

from . import lsd


@click.group(name="lsd")
def lsd_group():
    """Orthogonal idea generation over the vault's source notes (section 53)."""


@lsd_group.command(name="sample")
@click.option("--seed", type=int, default=53, show_default=True)
@click.option("--n", type=int, default=100, show_default=True, help="pairs per pool")
def lsd_sample(seed: int, n: int):
    """Freeze a new run: three pools of pairs, no model calls."""
    run = lsd.new_run(seed, n)
    path = lsd.save_run(run)
    click.echo(
        f"{run.run_id}: {run.n_notes} notes, {len(run.pairs)} pairs, tail {run.tail:.3f} -> {path}"
    )


@lsd_group.command(name="generate")
@click.argument("run_id")
def lsd_generate(run_id: str):
    """Fill candidates for every pair without them (resumable)."""
    run = lsd.load_run(run_id)
    lsd.generate(run, checkpoint=lsd.save_run, log=click.echo)
    click.echo(f"{len(run.candidates)} candidates")


@lsd_group.command(name="judge")
@click.argument("run_id")
def lsd_judge(run_id: str):
    """Score unscored candidates for coherence, then measure novelty."""
    run = lsd.load_run(run_id)
    lsd.judge(run, np.random.default_rng(run.seed + 7), log=click.echo)
    notes, mat = lsd.load_notes()
    if len(notes) != run.n_notes:
        ids = {n.id for n in run.notes}
        mat = mat[[k for k, n in enumerate(notes) if n.id in ids]]
    lsd.novelty(run, mat)
    lsd.save_run(run)
    click.echo(f"{sum(c.judge is not None for c in run.candidates)}/{len(run.candidates)} scored")


@lsd_group.command(name="deck")
@click.argument("run_id")
def lsd_deck(run_id: str):
    """Write the blind rating deck beside the run file."""
    run = lsd.load_run(run_id)
    deck = lsd.build_deck(run, np.random.default_rng(run.seed + 11))
    out = lsd.run_path(run.run_id).with_name(f"{run.run_id}-deck.json")
    out.write_text(json.dumps(deck, indent=1))
    click.echo(f"{len(deck)} cards -> {out}")


@lsd_group.command(name="rate")
@click.argument("run_id")
@click.argument("candidate_id")
@click.argument("score", type=click.IntRange(1, 5))
@click.option("--note", default="")
def lsd_rate(run_id: str, candidate_id: str, score: int, note: str):
    """Record one owner rating (last rating per candidate wins)."""
    import time

    lsd.append_rating(
        lsd.Rating(run_id, candidate_id, float(score), note, time.strftime("%Y-%m-%dT%H:%M:%S"))
    )
    click.echo(f"{candidate_id} <- {score}")


@lsd_group.command(name="score")
@click.argument("run_id")
def lsd_score(run_id: str):
    """G1 and G2 against the registered bars."""
    run = lsd.load_run(run_id)
    res = lsd.gates(run, lsd.load_ratings(run_id), np.random.default_rng(run.seed + 13))
    click.echo(json.dumps(res, indent=1))
