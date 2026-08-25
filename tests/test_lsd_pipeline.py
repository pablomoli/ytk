"""Generator, judge, novelty and deck for `ytk lsd`, with the model stubbed."""

from __future__ import annotations

from typing import Any

import numpy as np

from ytk import lsd


def _run(n_notes: int = 12, n_pairs: int = 6) -> tuple[lsd.Run, lsd.Vec]:
    rng = np.random.default_rng(0)
    X = rng.normal(size=(n_notes, 16)).astype(np.float32) + 0.5
    X /= np.linalg.norm(X, axis=1, keepdims=True)
    notes = [lsd.Note(f"n{k}", "youtube", f"Note {k}", f"text {k}") for k in range(n_notes)]
    pairs = [lsd.Pair(lsd.POOLS[k % 3], k, (k + 1) % n_notes, 0.3, 0.0) for k in range(n_pairs)]
    return lsd.Run("r1", 0, n_notes, 0.5, -0.1, 0.09, notes, pairs), X


def _stub_gen(system: str, user: str, result: type[Any]) -> Any:
    assert "Note A" in user and "Note B" in user
    return lsd.PairIdeas(
        build=lsd.BuildIdea(title="T", pitch="P", first_experiment="E"),
        post=lsd.PostIdea(hook="H", angle="A"),
    )


def test_generate_makes_two_candidates_per_pair_and_resumes():
    run, _ = _run()
    saves: list[int] = []
    lsd.generate(
        run,
        call=_stub_gen,
        checkpoint=lambda r: saves.append(len(r.candidates)),
        log=lambda s: None,
    )
    assert len(run.candidates) == 12
    assert {c.kind for c in run.candidates} == {"build", "post"}
    assert saves == [2, 4, 6, 8, 10, 12]
    calls: list[str] = []
    lsd.generate(run, call=lambda s, u, r: calls.append(u), log=lambda s: None)
    assert calls == []


def test_generate_survives_a_failing_pair():
    run, _ = _run()

    def flaky(system: str, user: str, result: type[Any]) -> Any:
        if "Note 2" in user.split("### Note B")[0]:
            raise RuntimeError("boom")
        return _stub_gen(system, user, result)

    lsd.generate(run, call=flaky, log=lambda s: None)
    assert len(run.candidates) == 10
    assert 2 not in {c.pair_index for c in run.candidates}


def test_judge_scores_every_candidate_in_mixed_batches():
    run, _ = _run()
    lsd.generate(run, call=_stub_gen, log=lambda s: None)
    batches: list[list[str]] = []

    def stub_judge(system: str, user: str, result: type[Any]) -> Any:
        ids = [line.split("id: ")[1] for line in user.splitlines() if line.startswith("id: ")]
        batches.append(ids)
        return lsd.JudgeScores(
            scores=[lsd.JudgeScore(id=i, score=7 if i.endswith("build") else 0) for i in ids]
        )

    lsd.judge(run, np.random.default_rng(1), call=stub_judge, batch_size=5, log=lambda s: None)
    assert all(c.judge is not None for c in run.candidates)
    assert {c.judge for c in run.candidates} == {5.0, 1.0}
    assert [len(b) for b in batches] == [5, 5, 2]


def test_novelty_fills_three_numbers_and_excludes_parents():
    run, X = _run()
    lsd.generate(run, call=_stub_gen, log=lambda s: None)
    Xc, _ = lsd.centre(X)

    def embed(texts: list[str]) -> lsd.Vec:
        # Every candidate embeds exactly onto its first parent: nearest must skip it.
        assert len(texts) == len(run.candidates)
        return np.stack([X[run.pairs[c.pair_index].i] for c in run.candidates]).astype(np.float32)

    lsd.novelty(run, X, embed=embed)
    for c in run.candidates:
        assert (
            c.novelty_nearest is not None
            and c.novelty_parents is not None
            and c.corpus_cos is not None
        )
        assert c.novelty_nearest < 0.999


def test_deck_hides_pools_and_takes_top_plus_extra():
    run, _ = _run(n_notes=40, n_pairs=36)
    lsd.generate(run, call=_stub_gen, log=lambda s: None)
    for k, c in enumerate(run.candidates):
        c.judge = float(1 + k % 5)
    deck = lsd.build_deck(run, np.random.default_rng(2), top=2, extra=1)
    assert len(deck) == 2 * 3 * 3
    assert all("pool" not in card for card in deck)
    assert all(len(card["parents"]) == 2 for card in deck)
    ids = [card["id"] for card in deck]
    assert len(set(ids)) == len(ids)


def test_run_round_trips_through_json(tmp_path, monkeypatch):
    monkeypatch.setattr(lsd, "LSD_HOME", tmp_path)
    run, _ = _run()
    lsd.generate(run, call=_stub_gen, log=lambda s: None)
    run.candidates[0].judge = 4.0
    lsd.save_run(run)
    back = lsd.load_run("r1")
    assert back.candidates[0].judge == 4.0
    assert back.pairs == run.pairs
    assert back.notes == run.notes
