"""Gates for `ytk lsd`: G1 on judge-top-5 hits, G2 on judge-owner Spearman."""

from __future__ import annotations

import numpy as np

from ytk import lsd


def _scored_run(n_pairs: int = 60) -> lsd.Run:
    notes = [lsd.Note(f"n{k}", "youtube", f"Note {k}", "t") for k in range(n_pairs + 1)]
    pairs = [lsd.Pair(lsd.POOLS[k % 3], k, k + 1, 0.3, 0.0) for k in range(n_pairs)]
    run = lsd.Run("r", 0, len(notes), 0.5, -0.1, 0.09, notes, pairs)
    for k in range(n_pairs):
        for kind in lsd.KINDS:
            run.candidates.append(
                lsd.Candidate(f"r-{k}-{kind}", k, kind, "t", "b", judge=float(1 + (k * 7) % 5))
            )
    return run


def test_spearman_matches_known_values():
    assert lsd.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == 1.0
    assert lsd.spearman([1, 2, 3, 4], [40, 30, 20, 10]) == -1.0
    assert lsd.spearman([1, 1, 1], [1, 2, 3]) == 0.0


def test_g1_passes_only_when_ortho_top5_hits_bar_and_beats_near():
    run = _scored_run()
    ratings: dict[str, float] = {}
    for c in lsd.judge_top(run, "build", "ortho"):
        ratings[c.id] = 5.0
    for c in lsd.judge_top(run, "build", "near"):
        ratings[c.id] = 2.0
    res = lsd.gates(run, ratings, np.random.default_rng(0), permutations=50)
    assert res["g1_pass"] and res["g1_kinds"] == ["build"]
    assert res["hits_top"]["build"] == {"ortho": 5, "near": 0, "rand": 0}
    for c in lsd.judge_top(run, "build", "near"):
        ratings[c.id] = 5.0
    res = lsd.gates(run, ratings, np.random.default_rng(0), permutations=50)
    assert not res["g1_pass"]


def test_g2_tracks_agreement_with_the_judge():
    run = _scored_run()
    agree = {c.id: float(c.judge or 0) for c in run.candidates[:40]}
    res = lsd.gates(run, agree, np.random.default_rng(1), permutations=200)
    assert res["g2_pass"] and res["rho"] > 0.99 and res["rho_p"] < 0.05
    noise = {c.id: float(1 + k % 5) for k, c in enumerate(run.candidates[:40])}
    res = lsd.gates(run, noise, np.random.default_rng(1), permutations=200)
    assert res["rho_null_p95"] < 0.5


def test_ratings_round_trip_last_wins(tmp_path, monkeypatch):
    monkeypatch.setattr(lsd, "LSD_HOME", tmp_path)
    lsd.append_rating(lsd.Rating("r", "r-0-build", 2.0))
    lsd.append_rating(lsd.Rating("r", "r-0-build", 4.0, note="changed my mind"))
    lsd.append_rating(lsd.Rating("other", "x", 5.0))
    assert lsd.load_ratings("r") == {"r-0-build": 4.0}
