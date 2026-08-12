from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ytk.ui.server import _SPA_ROUTES, app

client = TestClient(app)

_ROUTES_DIR = Path(__file__).resolve().parents[2] / "web" / "src" / "routes"


def test_root_serves_spa_index():
    r = client.get("/")
    assert r.status_code == 200
    assert 'id="root"' in r.text  # SPA shell


def test_deep_links_serve_spa_index():
    for path in ("/inbox", "/tags", "/map", "/settings", "/orb", "/galaxy"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert 'id="root"' in r.text, path


@pytest.mark.skipif(not _ROUTES_DIR.is_dir(), reason="web/src absent (installed package)")
def test_every_spa_route_file_is_allowlisted():
    """A route the allowlist does not know about 404s on reload and deep-link.
    /galaxy shipped that way; this keeps the next one from doing the same."""
    # nested route files (docs.$section.tsx) share their top-level segment's
    # allowlist entry; subpath handling beyond that is the server's own concern
    missing = sorted(
        {
            "" if f.stem == "index" else f.stem.split(".")[0]
            for f in _ROUTES_DIR.glob("*.tsx")
            if not f.stem.startswith(("__", "-")) and not f.stem.endswith(".test")
        }
        - _SPA_ROUTES
    )
    assert missing == [], f"routes missing from _SPA_ROUTES: {missing}"


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
