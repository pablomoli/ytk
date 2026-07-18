"""add-instagram CLI: reel routing, duplicate protection, --refresh."""

from __future__ import annotations

from click.testing import CliRunner
from pathlib import Path

import pytest

import ytk.cli as cli_mod
import ytk.enrich as enrich_mod
import ytk.instagram as instagram_mod
import ytk.store as store_mod
import ytk.vault as vault_mod
from ytk.enrich import Enrichment
from ytk.instagram import InstagramPost, ReelCapture
from ytk.vault import NoteAlreadyExists


_ENR = Enrichment(
    thesis="t", summary="s", key_concepts=[], insights=[],
    interest_tags=["ai"], key_moments=[],
)


@pytest.fixture
def calls(monkeypatch, tmp_path):
    """Mock every side-effecting collaborator; record how the CLI drives them."""
    rec = {"reel_enrich": None, "carousel_enrich": None, "write": None,
           "refresh": None, "upsert": None, "capture": None}

    def fake_fetch(url):
        return rec["post"]

    def fake_capture(post, whisper_model="base"):
        rec["capture"] = {"post": post, "model": whisper_model}
        return rec["reel_capture"]

    def fake_reel_enrich(**kwargs):
        rec["reel_enrich"] = kwargs
        return _ENR

    def fake_carousel_enrich(**kwargs):
        rec["carousel_enrich"] = kwargs
        return _ENR

    note = tmp_path / "u-2026-07-15-SC.md"

    def fake_write(post, enrichment, **kwargs):
        rec["write"] = kwargs
        note.write_text("---\nx: 1\n---\nbody", encoding="utf-8")
        return note

    def fake_refresh(post, enrichment, **kwargs):
        rec["refresh"] = kwargs
        note.write_text("---\nx: 1\n---\nbody", encoding="utf-8")
        return note

    def fake_upsert(doc_id, body, meta):
        rec["upsert"] = doc_id

    monkeypatch.setattr(instagram_mod, "fetch_instagram", fake_fetch)
    monkeypatch.setattr(instagram_mod, "capture_reel_media", fake_capture)
    monkeypatch.setattr(enrich_mod, "enrich_instagram_reel", fake_reel_enrich)
    monkeypatch.setattr(enrich_mod, "enrich_instagram", fake_carousel_enrich)
    monkeypatch.setattr(vault_mod, "write_instagram_note", fake_write)
    monkeypatch.setattr(vault_mod, "refresh_instagram_note", fake_refresh)
    monkeypatch.setattr(store_mod, "upsert_doc", fake_upsert)

    rec["post"] = InstagramPost(
        url="https://www.instagram.com/reel/SC/", username="u",
        timestamp="2026-07-15", caption="c", images=[], media_kind="video",
    )
    rec["reel_capture"] = ReelCapture(
        frame_bytes=[b"f1", b"f2"],
        transcript_segments=[{"start": 0, "duration": 1.0, "text": "hi"}],
        transcript_status="ok",
        duration=30.0,
        warnings=["frame extraction produced 0 frames (x)"],
    )
    return rec


def _run(*args):
    return CliRunner().invoke(cli_mod.cli, ["add-instagram", *args])


def test_reel_routes_through_video_pipeline(calls):
    result = _run("https://www.instagram.com/reel/SC/")
    assert result.exit_code == 0, result.output
    assert calls["capture"] is not None
    e = calls["reel_enrich"]
    assert e["transcript_segments"] == [{"start": 0, "duration": 1.0, "text": "hi"}]
    assert e["transcript_status"] == "ok"
    assert e["frame_count"] == 2
    assert e["duration"] == 30.0
    assert calls["carousel_enrich"] is None
    w = calls["write"]
    assert w["transcript_status"] == "ok"
    assert w["frame_bytes"] == [b"f1", b"f2"]
    assert calls["upsert"] is not None
    assert "warning" in result.output.lower()      # capture warnings surface in CLI


def test_carousel_keeps_existing_path(calls):
    calls["post"] = InstagramPost(
        url="https://www.instagram.com/p/SC/", username="u",
        timestamp="2026-07-15", caption="c",
        images=["https://cdn.example/1.jpg"], media_kind="carousel",
    )
    result = _run("https://www.instagram.com/p/SC/")
    assert result.exit_code == 0, result.output
    assert calls["capture"] is None
    assert calls["reel_enrich"] is None
    assert calls["carousel_enrich"]["slide_count"] == 1


def test_duplicate_protection_remains(calls, monkeypatch):
    def raise_exists(post, enrichment, **kwargs):
        raise NoteAlreadyExists("already there")

    monkeypatch.setattr(vault_mod, "write_instagram_note", raise_exists)
    result = _run("https://www.instagram.com/reel/SC/")
    assert result.exit_code == 0
    assert "already exists" in result.output.lower()
    assert calls["upsert"] is None


def test_refresh_flag_uses_atomic_replace(calls):
    result = _run("https://www.instagram.com/reel/SC/", "--refresh")
    assert result.exit_code == 0, result.output
    assert calls["refresh"] is not None
    assert calls["write"] is None
    assert calls["upsert"] is not None
