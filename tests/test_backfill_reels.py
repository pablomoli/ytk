"""Structural discovery + CLI for backfilling pre-schema reel notes."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

import ytk.cli as cli_mod
from ytk.vault import find_reel_backfill_candidates


@pytest.fixture
def brain(tmp_path, monkeypatch):
    monkeypatch.setattr("ytk.vault._get_brain_path", lambda: tmp_path)
    (tmp_path / "sources" / "instagram").mkdir(parents=True)
    return tmp_path


def _note(brain, filename, url, image_paths=(), extra_fm="", body=""):
    paths_yaml = "\n" + "\n".join(f"  - {p}" for p in image_paths) if image_paths else " []"
    content = (
        f"---\nurl: {url}\nusername: {filename.split('-')[0]}\ndate: 2026-07-15\n"
        f"title: whatever\ntags:\n  - x\ntype: instagram\n{extra_fm}"
        f"image_paths:{paths_yaml}\n---\n\n## Caption\nc\n{body}"
    )
    p = brain / "sources" / "instagram" / f"{filename}.md"
    p.write_text(content, encoding="utf-8")
    return p


KNOWN_SEVEN = [
    ("cabeza_patata-2026-07-14-Daxp5aJM1VA", "https://www.instagram.com/reel/Daxp5aJM1VA/"),
    ("elif.codes-2026-07-15-Da0cAr_tf_L", "https://www.instagram.com/reel/Da0cAr_tf_L/"),
    ("stephen_blum_code-2026-07-11-DaqZhEKjQp3", "https://www.instagram.com/reel/DaqZhEKjQp3/"),
    ("nateramerbooks-2026-02-15-DUw7GlVjQnA", "https://www.instagram.com/reel/DUw7GlVjQnA/"),
    ("_triiibe_-2026-07-03-DaVl_d2MOiq", "https://www.instagram.com/reel/DaVl_d2MOiq/"),
    ("marimo_io-2026-07-14-Dax-us0O7-s", "https://www.instagram.com/reel/Dax-us0O7-s/"),
    ("kopacreative.lv-2026-07-14-DaxgD2kIUt1", "https://www.instagram.com/reel/DaxgD2kIUt1/"),
]


def _seed_known_seven(brain):
    for filename, url in KNOWN_SEVEN:
        sc = url.rstrip("/").rsplit("/", 1)[-1]
        _note(brain, filename, url, image_paths=[f"sources/instagram/thumbnails/{sc}-thumb.jpg"])


def test_reel_url_without_schema_qualifies(brain):
    _note(
        brain,
        "u-2026-07-15-SC1",
        "https://www.instagram.com/reel/SC1/",
        image_paths=["sources/instagram/thumbnails/SC1-thumb.jpg"],
    )
    cands = find_reel_backfill_candidates()
    assert len(cands) == 1
    c = cands[0]
    assert c["url"] == "https://www.instagram.com/reel/SC1/"
    assert c["shortcode"] == "SC1"
    assert not c["has_transcript"]
    assert not c["has_frames"]
    assert c["reason"]


def test_thumbnail_only_p_url_qualifies_as_probable_video(brain):
    _note(
        brain,
        "u-2026-07-15-P1",
        "https://www.instagram.com/p/P1/",
        image_paths=["sources/instagram/thumbnails/P1-thumb.jpg"],
    )
    assert len(find_reel_backfill_candidates()) == 1


def test_carousel_with_slides_does_not_qualify(brain):
    _note(
        brain,
        "u-2026-07-15-CAR",
        "https://www.instagram.com/p/CAR/",
        image_paths=[
            "sources/instagram/slides/CAR-img-1.jpg",
            "sources/instagram/slides/CAR-img-2.jpg",
        ],
    )
    assert find_reel_backfill_candidates() == []


def test_schema2_note_does_not_requalify(brain):
    _note(
        brain,
        "u-2026-07-15-SC2",
        "https://www.instagram.com/reel/SC2/",
        image_paths=["sources/instagram/thumbnails/SC2-thumb.jpg"],
        extra_fm="media: video\ncapture_schema: 2\nframes: 4\ntranscript: ok\n",
    )
    assert find_reel_backfill_candidates() == []


def test_note_with_transcript_and_frames_is_reported(brain):
    _note(
        brain,
        "u-2026-07-15-SC3",
        "https://www.instagram.com/reel/SC3/",
        image_paths=["sources/instagram/frames/SC3/frame-1.jpg"],
        body="\n## Transcript\n<details>\nhello\n</details>\n",
    )
    cands = find_reel_backfill_candidates()
    assert len(cands) == 1  # still schema-less, still a candidate
    assert cands[0]["has_transcript"]
    assert cands[0]["has_frames"]


def test_known_seven_are_discovered(brain):
    _seed_known_seven(brain)
    # decoys that must not qualify
    _note(
        brain,
        "codedex.io-2026-07-06-Dad6x1smPvR",
        "https://www.instagram.com/p/Dad6x1smPvR/",
        image_paths=["sources/instagram/slides/Dad6x1smPvR-img-1.jpg"],
    )
    _note(
        brain,
        "supercalstudio-2026-06-25-DaATV4rlCC2",
        "https://www.instagram.com/p/DaATV4rlCC2/",
        image_paths=["sources/instagram/slides/DaATV4rlCC2-img-1.jpg"],
    )
    found = {c["shortcode"] for c in find_reel_backfill_candidates()}
    assert found == {url.rstrip("/").rsplit("/", 1)[-1] for _, url in KNOWN_SEVEN}


def test_cli_dry_run_lists_without_ingesting(brain, monkeypatch):
    _seed_known_seven(brain)
    called = []
    monkeypatch.setattr(cli_mod, "_backfill_ingest", lambda url: called.append(url))
    result = CliRunner().invoke(cli_mod.cli, ["backfill-instagram-reels", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert called == []
    assert "Da0cAr_tf_L" in result.output
    assert "7" in result.output  # total


def test_cli_apply_continues_after_failure_and_reports(brain, monkeypatch):
    _seed_known_seven(brain)
    calls = []

    def flaky(url):
        calls.append(url)
        if "DaqZhEKjQp3" in url:
            raise RuntimeError("fetch blew up")

    monkeypatch.setattr(cli_mod, "_backfill_ingest", flaky)
    result = CliRunner().invoke(cli_mod.cli, ["backfill-instagram-reels", "--apply"])
    assert result.exit_code == 0, result.output
    assert len(calls) == 7  # failure did not stop the loop
    assert "1 failed" in result.output
    assert "6" in result.output  # succeeded count
    assert "DaqZhEKjQp3" in result.output  # failed URL named in report
