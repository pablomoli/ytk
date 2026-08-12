"""The /docs experiment-record backend: manifest parsing and the media guard."""

from __future__ import annotations

import pytest

from ytk.ui.docs_record import (
    _parse_readme_head,
    assets_root,
    build_manifest,
    read_section,
    resolve_media,
)

README_30 = """\
# E30 — Coastlines: The Land/Sea Boundary

E29 quietly proved the planet has a shoreline; E30 draws it. The sphere is
the **embedding manifold**, contoured at the `calibrated` radius.

> **Later:** the cosmetic option was exercised the same day.

![fig](01-the-planet-unrolled.png)
"""

README_02 = """\
# E02 — Picking

Raycasts against instanced spheres.
"""


@pytest.fixture
def record(tmp_path):
    root = tmp_path / "repo" / "docs" / "assets"
    (root / "30-coastlines").mkdir(parents=True)
    (root / "README.md").write_text("# house style", encoding="utf-8")
    s30 = root / "30-coastlines"
    (s30 / "README.md").write_text(README_30, encoding="utf-8")
    (s30 / "01-the-planet-unrolled.png").write_bytes(b"png")
    (s30 / "02-the-named-continents.png").write_bytes(b"png")
    (s30 / "03-the-planet-turns.mp4").write_bytes(b"mp4")
    (s30 / "continents.json").write_text("{}", encoding="utf-8")
    s02 = root / "02-picking"
    s02.mkdir()
    (s02 / "README.md").write_text(README_02, encoding="utf-8")
    # non-sections the scan must skip
    (root / "memory-field").mkdir()
    (root / "memory-field" / "README.md").write_text("# not numbered", encoding="utf-8")
    (root / "hub-fresh.png").write_bytes(b"png")
    (root / "99-no-readme").mkdir()
    return root


def test_manifest_newest_first_with_parsed_heads(record):
    sections = build_manifest(record)
    assert [s["id"] for s in sections] == ["30-coastlines", "02-picking"]
    s30 = sections[0]
    assert s30["num"] == 30
    assert s30["title"] == "E30 — Coastlines: The Land/Sea Boundary"
    # deck is the first paragraph, joined and stripped of inline markdown
    assert s30["deck"].startswith("E29 quietly proved")
    assert "embedding manifold" in s30["deck"] and "**" not in s30["deck"]
    # figure order = name order, videos excluded
    assert s30["images"] == [
        "30-coastlines/01-the-planet-unrolled.png",
        "30-coastlines/02-the-named-continents.png",
    ]
    assert s30["hasVideo"] is True
    assert sections[1]["images"] == [] and sections[1]["hasVideo"] is False


def test_deck_skips_blockquotes_and_images():
    md = "# T\n\n> **Later:** annotation first.\n\n![f](x.png)\n\nThe real deck.\n\nMore.\n"
    title, deck = _parse_readme_head(md)
    assert title == "T"
    assert deck == "The real deck."


def test_read_section_returns_readme_and_typed_files(record):
    section = read_section(record, "30-coastlines")
    assert section is not None
    assert section["readme"].startswith("# E30")
    kinds = {f["name"]: f["kind"] for f in section["files"]}
    assert kinds == {
        "01-the-planet-unrolled.png": "image",
        "02-the-named-continents.png": "image",
        "03-the-planet-turns.mp4": "video",
        "continents.json": "data",
    }
    assert read_section(record, "31-nope") is None
    assert read_section(record, "../../etc") is None


def test_resolve_media_refuses_escape(record):
    ok = resolve_media(record, "30-coastlines/01-the-planet-unrolled.png")
    assert ok is not None and ok.name == "01-the-planet-unrolled.png"
    assert resolve_media(record, "../../../etc/passwd") is None
    assert resolve_media(record, "30-coastlines/../../assets") is None
    assert resolve_media(record, "30-coastlines") is None  # dirs are not media


def test_assets_root_prefers_env_then_source(record, tmp_path, monkeypatch):
    monkeypatch.setenv("YTK_REPO_PATH", str(tmp_path / "repo"))
    assert assets_root() == record
    # an env path without a record falls through to the source checkout
    monkeypatch.setenv("YTK_REPO_PATH", str(tmp_path / "elsewhere"))
    monkeypatch.setattr("ytk.ui.docs_record._source_root", lambda: tmp_path / "repo")
    assert assets_root() == record
    # neither present: the record is unavailable, not an error
    monkeypatch.setattr("ytk.ui.docs_record._source_root", lambda: tmp_path / "elsewhere")
    assert assets_root() is None


@pytest.fixture
def client(record, monkeypatch):
    monkeypatch.setenv("YTK_REPO_PATH", str(record.parents[1]))
    from fastapi.testclient import TestClient

    from ytk.ui.server import app

    return TestClient(app)


def test_api_docs_manifest(client):
    body = client.get("/api/docs").json()
    assert body["available"] is True
    assert [s["id"] for s in body["sections"]] == ["30-coastlines", "02-picking"]


def test_api_docs_section_and_404(client):
    assert client.get("/api/docs/30-coastlines").json()["id"] == "30-coastlines"
    assert client.get("/api/docs/31-nope").status_code == 404


def test_docs_media_serves_with_cache_header(client):
    resp = client.get("/docs-media/30-coastlines/01-the-planet-unrolled.png")
    assert resp.status_code == 200
    assert resp.content == b"png"
    assert "max-age" in resp.headers["cache-control"]
    assert client.get("/docs-media/30-coastlines/absent.png").status_code == 404


def test_api_docs_unavailable_without_record(tmp_path, monkeypatch):
    monkeypatch.setenv("YTK_REPO_PATH", str(tmp_path / "nowhere"))
    monkeypatch.setattr("ytk.ui.docs_record._source_root", lambda: tmp_path / "nowhere")
    from fastapi.testclient import TestClient

    from ytk.ui.server import app

    body = TestClient(app).get("/api/docs").json()
    assert body == {"available": False, "sections": []}


def test_spa_serves_docs_paths(client, tmp_path, monkeypatch):
    # the SPA catch-all admits /docs and /docs/<section>, keeps 404 for junk
    from ytk.ui import server

    (tmp_path / "index.html").write_text("<html>spa</html>", encoding="utf-8")
    monkeypatch.setattr(server, "_WEB_DIST", tmp_path)
    assert client.get("/docs").status_code == 200
    assert client.get("/docs/30-coastlines").status_code == 200
    assert client.get("/docs/not-a-section").status_code == 404
    assert client.get("/docs/30-coastlines/deeper").status_code == 404
