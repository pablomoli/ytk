"""Tests for the Pinterest pin fetcher and note writer."""

from __future__ import annotations

import pytest

PIN_HTML = """<html><head>
<meta property="og:title" content="Keyboard Builders&#x27; Digest"/>
<meta property="og:description" content="A cool split keyboard build."/>
<meta property="og:image" content="https://i.pinimg.com/originals/aa/bb/cc.jpg"/>
</head><body></body></html>"""


def test_parse_og_extracts_fields():
    from ytk.pinterest import _parse_og

    og = _parse_og(PIN_HTML)
    assert og["title"] == "Keyboard Builders' Digest"
    assert og["description"] == "A cool split keyboard build."
    assert og["image"] == "https://i.pinimg.com/originals/aa/bb/cc.jpg"


def test_parse_og_handles_reversed_attribute_order():
    from ytk.pinterest import _parse_og

    html = '<meta content="https://i.pinimg.com/x.jpg" property="og:image">'
    assert _parse_og(html)["image"] == "https://i.pinimg.com/x.jpg"


def test_fetch_pinterest_requires_image(monkeypatch):
    from ytk import pinterest

    monkeypatch.setattr(pinterest, "_get_html", lambda url: "<html></html>")
    with pytest.raises(ValueError, match="image"):
        pinterest.fetch_pinterest("https://www.pinterest.com/pin/123/")


def test_fetch_pinterest_builds_pin(monkeypatch):
    from ytk import pinterest

    monkeypatch.setattr(pinterest, "_get_html", lambda url: PIN_HTML)
    pin = pinterest.fetch_pinterest("https://www.pinterest.com/pin/470274386109181088/")
    assert pin.pin_id == "470274386109181088"
    assert pin.title == "Keyboard Builders' Digest"
    assert pin.image_url.endswith("cc.jpg")


def test_write_pinterest_note(tmp_path, monkeypatch):
    from ytk.enrich import Enrichment
    from ytk.pinterest import PinterestPin
    from ytk.vault import write_pinterest_note

    monkeypatch.setattr("ytk.vault._get_brain_path", lambda: tmp_path)
    monkeypatch.setattr("ytk.vault._save_image", lambda url, dest: None)

    pin = PinterestPin(
        url="https://www.pinterest.com/pin/123/",
        pin_id="123",
        title="A keyboard",
        description="desc",
        image_url="https://i.pinimg.com/x.jpg",
    )
    enrichment = Enrichment(
        thesis="A split keyboard build reference.",
        summary="Summary here.",
        key_concepts=["split keyboards"],
        insights=["insight"],
        interest_tags=["keyboards"],
        key_moments=[],
    )
    path = write_pinterest_note(pin, enrichment)
    text = path.read_text(encoding="utf-8")
    assert path.parent.name == "pinterest"
    assert path.stem == "pinterest-123"
    assert "url: https://www.pinterest.com/pin/123/" in text
    assert "type: pinterest" in text
    assert "## Summary" in text

    from ytk.vault import NoteAlreadyExists

    with pytest.raises(NoteAlreadyExists):
        write_pinterest_note(pin, enrichment)


NO_OG_HTML = """<html><head>
<title>Pokemon fofo | Imagens de pokemon, Ilustracoes | Pinterest</title>
<style>.x{background:url(https://i.pinimg.com/originals/d5/3b/01/cssnoise.png)}</style>
</head><body>
<script>{"url":"https://i.pinimg.com/736x/bf/af/65/realimage.jpg"}</script>
<script>{"again":"https://i.pinimg.com/736x/bf/af/65/realimage.jpg"}</script>
</body></html>"""


def test_fetch_pinterest_falls_back_to_embedded_image(monkeypatch):
    from ytk import pinterest

    monkeypatch.setattr(pinterest, "_get_html", lambda url: NO_OG_HTML)
    pin = pinterest.fetch_pinterest("https://www.pinterest.com/pin/999/")
    assert pin.image_url == "https://i.pinimg.com/736x/bf/af/65/realimage.jpg"
    assert pin.title == "Pokemon fofo"
