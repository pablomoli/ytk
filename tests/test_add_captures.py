"""P2/P5 (#197): every add-shaped command inserts a ledger row, nudges the
loop, and writes nothing to the vault. Reads and advances are the loop's."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from ytk import ledger
from ytk.cli import cli
from ytk.evidence import EvidenceBundle


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("YTK_LEDGER", str(tmp_path / "ledger.db"))
    monkeypatch.setenv("YTK_EVIDENCE", str(tmp_path / "evidence"))
    monkeypatch.setenv("YTK_CAPTURE_LOG", str(tmp_path / "capture_log.jsonl"))
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(tmp_path / "vault"))
    return tmp_path


def clean_bundle(source: str, url: str) -> EvidenceBundle:
    return EvidenceBundle(
        source=source,
        url=url,
        title="T",
        transcript=[{"start": 0, "duration": 2, "text": "hi"}],
        transcript_origin="api-manual",
        transcript_language="en",
        transcript_status="ok",
    )


@pytest.fixture(autouse=True)
def stub_nudge(monkeypatch):
    """The CLI inserts and nudges (P5, single writer); tests record the
    nudge instead of POSTing at a hub."""
    calls: list[bool] = []
    monkeypatch.setattr("ytk.wake.nudge_loop", lambda: calls.append(True) or True)
    return calls


@pytest.mark.parametrize(
    ("args", "source", "url"),
    [
        (["add"], "youtube", "https://www.youtube.com/watch?v=abcdefghijk"),
        (["add"], "instagram", "https://www.instagram.com/reel/xyz/"),
        (["add"], "tiktok", "https://www.tiktok.com/@u/video/123"),
        (["add"], "reddit", "https://www.reddit.com/r/rust/comments/abc/t/"),
        (["add"], "pinterest", "https://www.pinterest.com/pin/123/"),
        (["add"], "web", "https://example.org/article"),
        (["ingest"], "web", "https://example.org/article"),
        (["add-instagram"], "instagram", "https://www.instagram.com/reel/xyz/"),
        (["add-tiktok"], "tiktok", "https://www.tiktok.com/@u/video/123"),
        (["add-reddit"], "reddit", "https://www.reddit.com/r/rust/comments/abc/t/"),
        (["add-pinterest"], "pinterest", "https://www.pinterest.com/pin/123/"),
    ],
)
def test_command_captures_and_nudges_without_reading(env, stub_nudge, args, source, url):
    result = CliRunner().invoke(cli, [*args, url, "--note", "my take"])
    assert result.exit_code == 0, result.output
    conn = ledger.connect()
    row = conn.execute("SELECT * FROM items").fetchone()
    assert row["source"] == source
    assert row["url"] == url
    # P5: the CLI stops at the capture; the loop reads and advances.
    assert ledger.item_state(conn, row["id"]) == "captured"
    take = conn.execute("SELECT text FROM takes WHERE item_id = ?", (row["id"],)).fetchone()
    assert take["text"] == "my take"
    assert not (env / "vault").exists()  # nothing wrote a note
    assert stub_nudge == [True]


def test_add_points_at_the_digest(env, stub_nudge):
    url = "https://www.youtube.com/watch?v=abcdefghijk"
    result = CliRunner().invoke(cli, ["add", url])
    assert result.exit_code == 0, result.output
    assert "loop" in result.output.lower()


def test_add_reports_unreachable_hub_and_keeps_the_capture(env, monkeypatch):
    monkeypatch.setattr("ytk.wake.nudge_loop", lambda: False)
    url = "https://www.youtube.com/watch?v=abcdefghijk"
    result = CliRunner().invoke(cli, ["add", url])
    assert result.exit_code == 0, result.output
    assert "hub not reachable" in result.output
    conn = ledger.connect()
    row = conn.execute("SELECT id FROM items").fetchone()
    assert ledger.item_state(conn, row["id"]) == "captured"


def test_feed_captures_with_feed_surface(env, tmp_path):
    urls = tmp_path / "urls.txt"
    urls.write_text("https://www.youtube.com/watch?v=abcdefghijk\n")
    result = CliRunner().invoke(cli, ["feed", "--file", str(urls)])
    assert result.exit_code == 0, result.output
    conn = ledger.connect()
    row = conn.execute("SELECT provenance FROM items").fetchone()
    assert row["provenance"] == "feed"


def test_add_never_calls_enrichment(env):
    with patch("ytk.enrich.enrich", side_effect=AssertionError("enrichment ran")) as _:
        result = CliRunner().invoke(cli, ["add", "https://www.youtube.com/watch?v=abcdefghijk"])
    assert result.exit_code == 0, result.output


def test_add_never_reads_in_process(env, monkeypatch):
    def boom(conn, item_id, *, actor="loop"):
        raise AssertionError("read_item must not run on the CLI surface (P5)")

    monkeypatch.setattr("ytk.evidence.read_item", boom)
    result = CliRunner().invoke(cli, ["add", "https://www.youtube.com/watch?v=abcdefghijk"])
    assert result.exit_code == 0, result.output
