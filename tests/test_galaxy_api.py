import json

from fastapi.testclient import TestClient

import ytk.ui.server as server


def _client(tmp_path, monkeypatch, block):
    m = tmp_path / "map.json"
    m.write_text(json.dumps({"points": [], "content": ({"galaxy": block} if block else {})}))
    monkeypatch.setattr(server, "_ORB_MAP", m)
    tex = tmp_path / "tex"
    tex.mkdir()
    (tex / "0.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    monkeypatch.setattr(server, "_GALAXY_TEX_DIR", tex)
    return TestClient(server.app)


def test_galaxy_api_serves_block(tmp_path, monkeypatch):
    block = {"epoch": "v2", "k_deg": 3.0, "planets": []}
    c = _client(tmp_path, monkeypatch, block)
    assert c.get("/api/galaxy").json() == block


def test_galaxy_api_404_without_block(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch, None)
    r = c.get("/api/galaxy")
    assert r.status_code == 404 and "galaxy block" in r.json()["detail"]


def test_galaxy_tex_serves_and_guards(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch, {"planets": []})
    assert c.get("/galaxy-tex/0.png").status_code == 200
    assert c.get("/galaxy-tex/../secrets.png").status_code == 404
    assert c.get("/galaxy-tex/missing.png").status_code == 404
