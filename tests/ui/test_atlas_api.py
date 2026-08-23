import json
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

import ytk.ui.server as server
from experiments.sae_qwen import export_hub_features

_REPO = Path(__file__).resolve().parents[2]
_ATLAS_ARTIFACT = _REPO / "experiments" / "sae_qwen" / "atlas.json"


@pytest.fixture
def atlas_api(tmp_path, monkeypatch):
    paths = {
        "atlas": tmp_path / "atlas.json",
        "features": tmp_path / "atlas_features.json",
        "sae": tmp_path / "atlas_sae.npz",
        "docs": tmp_path / "atlas_docs.json",
    }
    monkeypatch.setattr(server, "_ATLAS_JSON", paths["atlas"])
    monkeypatch.setattr(server, "_ATLAS_FEATURES", paths["features"])
    monkeypatch.setattr(server, "_ATLAS_SAE", paths["sae"])
    monkeypatch.setattr(server, "_ATLAS_DOCS", paths["docs"])
    server._atlas_rig = None
    yield TestClient(server.app), paths
    server._atlas_rig = None


@pytest.fixture
def exported_features(tmp_path, monkeypatch):
    monkeypatch.setattr(export_hub_features, "OUT", tmp_path)
    export_hub_features.main()
    return tmp_path / "atlas_features.json"


def _write_knob_assets(paths, *, bg_std=0.0):
    latent_count = 2048
    w_enc = np.zeros((latent_count, 2), dtype=np.float32)
    w_enc[7] = [1.0, 0.0]
    w_dec = np.zeros((latent_count, 2), dtype=np.float32)
    w_dec[7] = [1.0, 0.0]
    w_dec[11] = [0.0, 1.0]
    maxa = np.zeros(latent_count, dtype=np.float32)
    maxa[11] = 1.5
    docs = np.asarray(
        [
            [1.0, 0.0],
            [0.0, 1.0],
            [0.6, 0.8],
        ],
        dtype=np.float32,
    )
    np.savez(
        paths["sae"],
        W_enc=w_enc,
        b_enc=np.zeros(latent_count, dtype=np.float32),
        b_pre=np.zeros(2, dtype=np.float32),
        W_dec=w_dec,
        maxa=maxa,
        docs=docs,
        k=np.asarray(1),
        bg_std=np.asarray(bg_std, dtype=np.float32),
    )
    metadata = [
        {
            "note_key": "base",
            "title": "Base direction",
            "kind": "video",
            "source": "youtube",
        },
        {
            "note_key": "clamp",
            "title": "Clamp direction",
            "kind": "memory",
            "source": "vault",
        },
        {"note_key": "mixed", "title": "Mixed direction", "kind": "note", "source": "web"},
    ]
    paths["docs"].write_text(json.dumps(metadata), encoding="utf-8")


def _assert_atlas_contract(body):
    assert {
        "grid",
        "x_edges",
        "y_edges",
        "n_map_points",
        "n_joined",
        "gate",
        "protagonist",
        "cells",
    } <= body.keys()
    grid = body["grid"]
    assert isinstance(grid, int) and grid > 0
    assert all(isinstance(value, (int, float)) for value in body["x_edges"])
    assert all(isinstance(value, (int, float)) for value in body["y_edges"])
    assert len(body["x_edges"]) == grid + 1
    assert len(body["y_edges"]) == grid + 1
    assert all(a < b for a, b in zip(body["x_edges"], body["x_edges"][1:]))
    assert all(a < b for a, b in zip(body["y_edges"], body["y_edges"][1:]))
    assert isinstance(body["n_map_points"], int)
    assert isinstance(body["n_joined"], int)
    assert 0 < body["n_joined"] <= body["n_map_points"]

    gate = body["gate"]
    assert {"stable_05", "stable_08", "strict_05", "n"} <= gate.keys()
    assert all(isinstance(gate[key], int) for key in ("stable_05", "stable_08", "strict_05", "n"))
    assert 0 <= gate["stable_08"] <= gate["stable_05"] <= gate["n"]
    assert 0 <= gate["strict_05"] <= gate["n"]

    protagonist = body["protagonist"]
    assert {"latent", "cell", "on_frozen_layout", "cell_method"} <= protagonist.keys()
    assert isinstance(protagonist["latent"], int)
    assert isinstance(protagonist["on_frozen_layout"], bool)
    assert isinstance(protagonist["cell_method"], str) and protagonist["cell_method"]
    if protagonist["cell"] is not None:
        assert len(protagonist["cell"]) == 2
        assert all(isinstance(v, int) and 0 <= v < grid for v in protagonist["cell"])

    assert isinstance(body["cells"], list) and body["cells"]
    for cell in body["cells"]:
        assert {
            "cell",
            "x0",
            "y0",
            "x1",
            "y1",
            "n_points",
            "n_scored",
            "ood_frac",
            "head_mass",
            "label_latent",
            "label",
            "label_excess",
            "label_outside_null",
            "top5",
            "seed_cos_top5",
            "stable_05",
            "stable_08",
            "theme_label",
        } <= cell.keys()
        assert len(cell["cell"]) == 2
        assert all(isinstance(value, int) and 0 <= value < grid for value in cell["cell"])
        cx, cy = cell["cell"]
        assert (cell["x0"], cell["x1"]) == (
            body["x_edges"][cx],
            body["x_edges"][cx + 1],
        )
        assert (cell["y0"], cell["y1"]) == (
            body["y_edges"][cy],
            body["y_edges"][cy + 1],
        )
        assert isinstance(cell["n_points"], int)
        assert isinstance(cell["n_scored"], int)
        assert 0 < cell["n_scored"] <= cell["n_points"]
        assert isinstance(cell["ood_frac"], (int, float))
        assert isinstance(cell["head_mass"], (int, float))
        assert 0.0 <= cell["ood_frac"] <= 1.0
        assert 0.0 <= cell["head_mass"] <= 1.0
        assert isinstance(cell["label_latent"], int)
        assert cell["label"] is None or isinstance(cell["label"], str)
        assert isinstance(cell["label_excess"], (int, float))
        assert isinstance(cell["label_outside_null"], bool)
        assert isinstance(cell["top5"], list) and len(cell["top5"]) == 5
        for latent in cell["top5"]:
            assert {"latent", "name", "excess", "outside_null"} <= latent.keys()
            assert isinstance(latent["latent"], int)
            assert latent["name"] is None or isinstance(latent["name"], str)
            assert isinstance(latent["excess"], (int, float))
            assert isinstance(latent["outside_null"], bool)
        assert isinstance(cell["seed_cos_top5"], list)
        assert all(isinstance(value, (int, float)) for value in cell["seed_cos_top5"])
        assert isinstance(cell["stable_05"], bool)
        assert isinstance(cell["stable_08"], bool)
        assert cell["theme_label"] is None or isinstance(cell["theme_label"], str)


def _assert_features_contract(body):
    assert {"checkpoint", "naming", "protagonist", "cards"} <= body.keys()
    assert isinstance(body["checkpoint"], str) and body["checkpoint"]
    assert isinstance(body["naming"], str) and body["naming"]
    assert isinstance(body["protagonist"], int)
    assert isinstance(body["cards"], dict) and body["cards"]
    assert str(body["protagonist"]) in body["cards"]
    for card in body["cards"].values():
        assert {"name", "confidence", "freq", "badge", "exemplars"} <= card.keys()
        assert card["name"] is None or isinstance(card["name"], str)
        assert card["confidence"] is None or isinstance(card["confidence"], str)
        assert isinstance(card["freq"], (int, float))
        assert isinstance(card["badge"], (int, float))
        assert isinstance(card["exemplars"], list)
        for exemplar in card["exemplars"]:
            assert {"title", "kind", "source", "video_id", "act"} <= exemplar.keys()
            assert isinstance(exemplar["title"], str)
            assert isinstance(exemplar["kind"], str)
            assert isinstance(exemplar["source"], str)
            assert exemplar["video_id"] is None or isinstance(exemplar["video_id"], str)
            assert isinstance(exemplar["act"], (int, float))


def test_atlas_contract_checks_every_cell():
    body = json.loads(_ATLAS_ARTIFACT.read_text(encoding="utf-8"))
    assert len(body["cells"]) > 1
    del body["cells"][1]["label_excess"]

    with pytest.raises(AssertionError):
        _assert_atlas_contract(body)


def test_features_contract_checks_every_card(exported_features):
    body = json.loads(exported_features.read_text(encoding="utf-8"))
    protagonist = str(body["protagonist"])
    card_key = next(key for key in body["cards"] if key != protagonist)
    del body["cards"][card_key]["badge"]

    with pytest.raises(AssertionError):
        _assert_features_contract(body)


def test_features_contract_checks_every_exemplar(exported_features):
    body = json.loads(exported_features.read_text(encoding="utf-8"))
    protagonist = str(body["protagonist"])
    card = next(
        card for key, card in body["cards"].items() if key != protagonist and card["exemplars"]
    )
    del card["exemplars"][-1]["source"]

    with pytest.raises(AssertionError):
        _assert_features_contract(body)


def test_atlas_api_serves_canonical_export_contract(atlas_api, monkeypatch):
    client, _ = atlas_api
    monkeypatch.setattr(server, "_ATLAS_JSON", _ATLAS_ARTIFACT)

    response = client.get("/api/atlas")

    assert response.status_code == 200
    _assert_atlas_contract(response.json())


def test_atlas_api_404_without_export(atlas_api):
    client, _ = atlas_api

    response = client.get("/api/atlas")

    assert response.status_code == 404
    assert "atlas built" in response.json()["detail"]


def test_atlas_features_api_serves_production_export_contract(
    atlas_api, exported_features, monkeypatch
):
    client, _ = atlas_api
    monkeypatch.setattr(server, "_ATLAS_FEATURES", exported_features)

    response = client.get("/api/atlas/features")

    assert response.status_code == 200
    _assert_features_contract(response.json())


def test_atlas_features_api_404_without_export(atlas_api):
    client, _ = atlas_api

    response = client.get("/api/atlas/features")

    assert response.status_code == 404
    assert "feature cards" in response.json()["detail"]


@pytest.mark.parametrize("missing", ["sae", "docs"])
def test_atlas_knob_api_404_when_required_export_is_missing(atlas_api, missing):
    client, paths = atlas_api
    if missing != "sae":
        paths["sae"].write_bytes(b"unused")
    if missing != "docs":
        paths["docs"].write_text("[]", encoding="utf-8")

    response = client.post(
        "/api/atlas/knob",
        json={"query": "language model mechanics", "latent": 1597, "clamp": 1.0},
    )

    assert response.status_code == 404
    assert "SAE export" in response.json()["detail"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("query", ""),
        ("query", "x" * 501),
        ("latent", -1),
        ("latent", 2048),
        ("clamp", -0.01),
        ("clamp", 4.01),
    ],
)
def test_atlas_knob_api_validates_request_bounds(atlas_api, field, value):
    client, _ = atlas_api
    payload = {"query": "language model mechanics", "latent": 1597, "clamp": 1.0}
    payload[field] = value

    response = client.post("/api/atlas/knob", json=payload)

    assert response.status_code == 422


def test_atlas_knob_api_retrieves_deterministic_base_and_clamped_results(atlas_api, monkeypatch):
    client, paths = atlas_api
    _write_knob_assets(paths)
    monkeypatch.setattr(
        "ytk.store._embed_query",
        lambda query: np.asarray([1.0, 0.0], dtype=np.float32),
    )

    response = client.post(
        "/api/atlas/knob",
        json={"query": "language model mechanics", "latent": 11, "clamp": 1.0},
    )

    assert response.status_code == 200
    body = response.json()
    assert [row["title"] for row in body["base"]] == [
        "Base direction",
        "Mixed direction",
        "Clamp direction",
    ]
    assert [row["title"] for row in body["clamped"]] == [
        "Mixed direction",
        "Clamp direction",
        "Base direction",
    ]
    assert [row["sim"] for row in body["base"]] == [1.0, 0.6, 0.0]
    assert [row["sim"] for row in body["clamped"]] == [0.9985, 0.8321, 0.5547]
    assert [(row["kind"], row["source"]) for row in body["base"]] == [
        ("video", "youtube"),
        ("note", "web"),
        ("memory", "vault"),
    ]
    assert [(row["kind"], row["source"]) for row in body["clamped"]] == [
        ("note", "web"),
        ("memory", "vault"),
        ("video", "youtube"),
    ]


def test_atlas_knob_api_returns_normalized_share_when_background_std_is_positive(
    atlas_api, monkeypatch
):
    client, paths = atlas_api
    _write_knob_assets(paths, bg_std=0.2)
    monkeypatch.setattr(
        "ytk.store._embed_query",
        lambda query: np.asarray([1.0, 0.0], dtype=np.float32),
    )

    response = client.post(
        "/api/atlas/knob",
        json={"query": "language model mechanics", "latent": 11, "clamp": 1.0},
    )

    assert response.status_code == 200
    for result_set in (response.json()["base"], response.json()["clamped"]):
        assert all("share" in row for row in result_set)
        assert sum(row["share"] for row in result_set) == pytest.approx(1.0, abs=0.001)


def test_atlas_knob_api_reports_query_latents_and_selected_latent_max(atlas_api, monkeypatch):
    client, paths = atlas_api
    _write_knob_assets(paths)
    monkeypatch.setattr(
        "ytk.store._embed_query",
        lambda query: np.asarray([1.0, 0.0], dtype=np.float32),
    )

    response = client.post(
        "/api/atlas/knob",
        json={"query": "language model mechanics", "latent": 11, "clamp": 1.0},
    )

    assert response.status_code == 200
    assert response.json()["query_latents"] == [{"latent": 7, "act": 1.0}]
    assert response.json()["latent_max"] == 1.5
