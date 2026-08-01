from fastapi.testclient import TestClient

from ytk.ui.server import app

client = TestClient(app)


def test_root_serves_spa_index():
    r = client.get("/")
    assert r.status_code == 200
    assert 'id="root"' in r.text  # SPA shell


def test_deep_links_serve_spa_index():
    for path in ("/inbox", "/tags", "/map", "/settings", "/orb"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert 'id="root"' in r.text, path


def test_old_app_prefix_redirects():
    r = client.get("/app/inbox", follow_redirects=False)
    assert r.status_code == 308
    assert r.headers["location"] == "/inbox"


def test_api_not_shadowed_by_spa():
    r = client.get("/api/fresh?n=1")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")


def test_unknown_api_path_is_404_not_spa():
    r = client.get("/api/does-not-exist")
    assert r.status_code == 404


def test_docs_settings_still_served():
    r = client.get("/docs/settings")
    assert r.status_code == 200
    assert "settings docs" in r.text
