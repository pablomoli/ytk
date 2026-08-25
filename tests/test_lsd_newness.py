"""Rung 0.5: multi-sample generation, farthest selection, newness gates, latent pairs."""

from __future__ import annotations

import json
from typing import Any

import numpy as np

from ytk import lsd


def _run(n_notes: int = 12, n_pairs: int = 4) -> tuple[lsd.Run, lsd.Vec]:
    rng = np.random.default_rng(0)
    X = rng.normal(size=(n_notes, 16)).astype(np.float32) + 0.5
    X /= np.linalg.norm(X, axis=1, keepdims=True)
    notes = [lsd.Note(f"n{k}", "youtube", f"Note {k}", f"text {k}") for k in range(n_notes)]
    pairs = [lsd.Pair(lsd.POOLS[k % 3], k, (k + 1) % n_notes, 0.3, 0.0) for k in range(n_pairs)]
    return lsd.Run("r", 0, n_notes, 0.5, -0.1, 0.09, notes, pairs), X


def _stub_v2(system: str, user: str, result: type[Any]) -> Any:
    assert "### A" in user and "Note A" not in system.split("Forbidden")[0]
    return lsd.PairIdeasV2(
        build=lsd.BuildIdea(title="T", pitch="P", first_experiment="E"),
        post=lsd.PostIdea(hook="H", angle="G"),
        whatif=lsd.WhatIf(title="W", body="B"),
    )


def test_generate_v2_keeps_every_sample_and_resumes():
    run, _ = _run()
    lsd.generate_v2(run, _stub_v2, samples=3, log=lambda s: None)
    assert len(run.candidates) == 4 * 3 * 3
    assert {c.kind for c in run.candidates} == {"build", "post", "whatif"}
    assert run.candidates[0].id.endswith("-s0") and run.candidates[3].id.endswith("-s1")
    calls: list[str] = []
    lsd.generate_v2(run, lambda s, u, r: calls.append(u), samples=3, log=lambda s: None)
    assert calls == []


def test_select_farthest_keeps_one_per_pair_and_kind_away_from_the_centroid():
    run, X = _run(n_pairs=2)
    lsd.generate_v2(run, _stub_v2, samples=2, log=lambda s: None)
    mu = X.mean(axis=0)
    C = np.tile(mu / np.linalg.norm(mu), (len(run.candidates), 1)).astype(np.float32)
    # First samples sit on the corpus mean; second samples point elsewhere and
    # are unrelated to each other, so each group must keep its second sample.
    rng = np.random.default_rng(7)
    for row, c in enumerate(run.candidates):
        if c.id.endswith("-s1"):
            v = rng.normal(size=C.shape[1]).astype(np.float32)
            v -= (v @ C[row]) * C[row]
            C[row] = v / np.linalg.norm(v)
    kept = lsd.select_farthest(run, C, mu.astype(np.float32))
    assert len(kept) == 2 * 3
    assert all(run.candidates[r].id.endswith("-s1") for r in kept)


def test_newness_reports_gates_and_text_stats():
    run, X = _run(n_pairs=3)
    lsd.generate_v2(run, _stub_v2, samples=1, log=lambda s: None)
    run.candidates[0].body = "Note A shows the piece argues that"
    run.candidates[1].title = "hook — with a dash"
    rng = np.random.default_rng(1)
    C = rng.normal(size=(len(run.candidates), 16)).astype(np.float32)
    C /= np.linalg.norm(C, axis=1, keepdims=True)
    rep = lsd.newness(run, list(range(len(run.candidates))), C, X)
    assert set(rep) >= {"n1", "n2", "n3", "leak", "banned", "em_dash_hooks", "per_kind"}
    assert rep["leak"] == 1 and rep["banned"] == 1
    assert rep["em_dash_hooks"] == 1 / 3
    assert -1 <= rep["n1"] <= 1 and -1 <= rep["n3"] <= 1
    assert set(rep["per_kind"]) == {"build", "post", "whatif"}


def test_load_latents_reads_names_and_decoder_rows(tmp_path):
    feats = {
        "features": [
            {
                "feature": "3",
                "name": "Alpha thing",
                "name_rationale": "why",
                "exemplars": "[{'title': 'T1'}, {'title': 'T2'}, {'title': 'T1'}]",
            },
            {"feature": "5", "name": "", "exemplars": []},
            {"feature": "7", "name": "Beta", "name_rationale": "", "exemplars": [{"title": "X"}]},
        ]
    }
    (tmp_path / "features.json").write_text(json.dumps(feats))
    W = np.random.default_rng(0).normal(size=(8, 4)).astype(np.float32)
    np.savez(tmp_path / "sae.npz", W_dec=W)
    notes, V = lsd.load_latents(tmp_path / "features.json", tmp_path / "sae.npz")
    assert [n.id for n in notes] == ["latent-3", "latent-7"]
    assert notes[0].text.startswith("Alpha thing. why\nSeen in: T1; T2")
    assert np.allclose(np.linalg.norm(V, axis=1), 1.0, atol=1e-5)


def _stub_v3(system: str, user: str, result: type[Any]) -> Any:
    assert "cross product" in system and "### A" in user
    return lsd.CrossProduct(
        trail=[f"step {k}" for k in range(10)],
        bridge="same shape",
        third=lsd.Third(
            name="Glassweight", definition="a def", properties=["p1", "p2", "p3", "p4"]
        ),
        consequence="breaks",
        question="why?",
    )


def test_generate_v3_yields_one_third_per_sample_with_scaffolding():
    run, _ = _run(n_pairs=2)
    lsd.generate_v3(run, _stub_v3, samples=2, log=lambda s: None)
    assert len(run.candidates) == 4
    c = run.candidates[0]
    assert c.kind == "third" and c.title == "Glassweight"
    assert c.body == "a def\n\n- p1\n- p2\n- p3"
    assert set(c.extra) == {"trail", "bridge", "consequence", "question"}
    assert len(c.extra["trail"]) == 10
    calls: list[str] = []
    lsd.generate_v3(run, lambda s, u, r: calls.append(u), samples=2, log=lambda s: None)
    assert calls == []


def test_newness_reports_n4_and_per_pool():
    run, X = _run(n_pairs=3)
    lsd.generate_v3(run, _stub_v3, samples=1, log=lambda s: None)
    Xc, _ = lsd.centre(X)
    # Every third embeds onto its first parent: N4 must read 1.0.
    C = np.stack([X[run.pairs[c.pair_index].i] for c in run.candidates]).astype(np.float32)
    rep = lsd.newness(run, list(range(len(run.candidates))), C, X)
    assert abs(rep["n4"] - 1.0) < 1e-4
    assert set(rep["per_pool"]) == {"ortho", "near", "rand"}
    assert "n4" in rep["per_kind"]["third"]


def test_extra_survives_json_and_deck(tmp_path, monkeypatch):
    monkeypatch.setattr(lsd, "LSD_HOME", tmp_path)
    run, _ = _run(n_pairs=3)
    lsd.generate_v3(run, _stub_v3, samples=1, log=lambda s: None)
    for c in run.candidates:
        c.judge = 4.0
    lsd.save_run(run)
    back = lsd.load_run("r")
    assert back.candidates[0].extra["question"] == "why?"
    deck = lsd.build_deck(back, np.random.default_rng(0), top=1, extra=0)
    assert all(card["kind"] == "third" and card["extra"]["bridge"] == "same shape" for card in deck)
