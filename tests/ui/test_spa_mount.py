from fastapi.testclient import TestClient

from ytk.ui.server import app

client = TestClient(app)


def test_app_route_serves_spa_index():
    r = client.get("/app/inbox")
    assert r.status_code == 200
    assert 'id="root"' in r.text  # SPA shell


def test_legacy_inbox_still_served():
    r = client.get("/inbox")
    assert r.status_code == 200
    assert "showSkeletons" in r.text  # legacy inbox JS still present


def test_api_not_shadowed_by_spa():
    r = client.get("/api/fresh?n=1")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
