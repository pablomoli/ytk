"""/api/lsd: the deck never carries a pool label; ratings append, last wins."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from ytk import lsd
from ytk.ui.server import app


@pytest.fixture
def deck_home(tmp_path, monkeypatch):
    monkeypatch.setattr(lsd, "LSD_HOME", tmp_path)
    runs = tmp_path / "runs"
    runs.mkdir()
    cards = [
        {
            "id": "r1-0-build",
            "kind": "build",
            "title": "T",
            "body": "B",
            "parents": [{"id": "a", "title": "A"}, {"id": "b", "title": "B"}],
        },
        {
            "id": "r1-1-post",
            "kind": "post",
            "title": "H",
            "body": "G",
            "parents": [{"id": "c", "title": "C"}, {"id": "d", "title": "D"}],
        },
    ]
    (runs / "r1-deck.json").write_text(json.dumps(cards))
    return TestClient(app)


def test_runs_and_deck_have_no_pool(deck_home):
    runs = deck_home.get("/api/lsd/runs").json()["runs"]
    assert runs == [{"run_id": "r1", "cards": 2, "rated": 0}]
    deck = deck_home.get("/api/lsd/deck", params={"run": "r1"}).json()
    assert [c["id"] for c in deck["cards"]] == ["r1-0-build", "r1-1-post"]
    assert "pool" not in json.dumps(deck)
    assert deck["ratings"] == {}


def test_rate_appends_and_last_wins(deck_home):
    r = deck_home.post(
        "/api/lsd/rate", json={"run_id": "r1", "candidate_id": "r1-0-build", "score": 2}
    )
    assert r.status_code == 200
    deck_home.post(
        "/api/lsd/rate",
        json={"run_id": "r1", "candidate_id": "r1-0-build", "score": 5, "note": "yes"},
    )
    deck = deck_home.get("/api/lsd/deck", params={"run": "r1"}).json()
    assert deck["ratings"] == {"r1-0-build": 5.0}
    assert deck_home.get("/api/lsd/runs").json()["runs"][0]["rated"] == 1
    assert (
        deck_home.post(
            "/api/lsd/rate", json={"run_id": "r1", "candidate_id": "x", "score": 9}
        ).status_code
        == 422
    )


def test_missing_deck_is_404(deck_home):
    assert deck_home.get("/api/lsd/deck", params={"run": "nope"}).status_code == 404
