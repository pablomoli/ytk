import json

from fastapi.testclient import TestClient

import ytk.ui.server as server

client = TestClient(server.app)


def _map(tmp_path, with_sphere=True):
    content = {
        "params": {},
        "groups": [{"label": "ai-tools"}, {"label": "design"}],
    }
    if with_sphere:
        content["sphere"] = {
            "radial": [[0, 0, 1], [1, 0, 0]],
            "haversine": None,
            "lattice": [[0, 1, 0], [0, 0, -1]],
            "scores": {
                "radial": {
                    "trustworthiness": 0.9,
                    "mean_nn_deg": 40.0,
                    "overlap": 0,
                    "overlap_frac": 0.0,
                }
            },
            "chosen": "radial",
        }
    data = {
        "v": 2,
        "points": [
            {
                "t": "vid",
                "c": "youtube",
                "u": "https://y",
                "d": "2026-01-01",
                "p": "second-brain/sources/youtube/vid.md",
                "c3": [0, 0, 1],
                "th": 0,
                "thumb": "sources/youtube/thumbnails/x-thumb.jpg",
            },
            {"t": "atom", "c": "memory", "p": "second-brain/inbox/a.md"},
            {
                "t": "gram",
                "c": "instagram",
                "u": "https://i",
                "d": None,
                "p": "second-brain/sources/instagram/g.md",
                "c3": [1, 0, 0],
                "th": 1,
            },
        ],
        "content": content,
        "all": {},
    }
    p = tmp_path / "map.json"
    p.write_text(json.dumps(data))
    return p


def test_orb_serves_content_points_in_c3_order(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_ORB_MAP", _map(tmp_path))
    r = client.get("/api/orb")
    assert r.status_code == 200
    body = r.json()
    assert [p["t"] for p in body["points"]] == ["vid", "gram"]  # memory excluded
    assert body["points"][0]["thumb"] == "sources/youtube/thumbnails/x-thumb.jpg"
    assert body["points"][1]["thumb"] is None
    assert body["themes"] == ["ai-tools", "design"]
    assert body["sphere"]["chosen"] == "radial"
    assert len(body["sphere"]["radial"]) == 2


def test_orb_404_without_sphere_block(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_ORB_MAP", _map(tmp_path, with_sphere=False))
    r = client.get("/api/orb")
    assert r.status_code == 404
    assert "attach-sphere" in r.json()["detail"]


def test_orb_404_without_map(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_ORB_MAP", tmp_path / "missing.json")
    assert client.get("/api/orb").status_code == 404
