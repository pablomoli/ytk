"""P2 capture unification (#197): every add-shaped command inserts a ledger
row and writes nothing to the vault."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from ytk import evidence, ledger
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
def stub_gatherers(monkeypatch):
    """Consumer tests never do network; the read verb gets a clean bundle."""
    import ytk.gatherers  # noqa: F401 — fill the registry before overriding

    for source in list(evidence.GATHERERS):
        monkeypatch.setitem(
            evidence.GATHERERS, source, lambda url, title, s=source: clean_bundle(s, url)
        )


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
def test_command_captures_and_reads_without_vault_write(env, args, source, url):
    result = CliRunner().invoke(cli, [*args, url, "--note", "my take"])
    assert result.exit_code == 0, result.output
    conn = ledger.connect()
    row = conn.execute("SELECT * FROM items").fetchone()
    assert row["source"] == source
    assert row["url"] == url
    assert ledger.item_state(conn, row["id"]) == "read"
    take = conn.execute("SELECT text FROM takes WHERE item_id = ?", (row["id"],)).fetchone()
    assert take["text"] == "my take"
    assert not (env / "vault").exists()  # nothing wrote a note


def test_add_reports_ask_when_gate_fires(env, monkeypatch):
    url = "https://www.youtube.com/watch?v=abcdefghijk"
    b = clean_bundle("youtube", url)
    b.transcript = []
    b.transcript_origin = "none"
    b.transcript_status = "none"
    monkeypatch.setitem(evidence.GATHERERS, "youtube", lambda u, t: b)
    result = CliRunner().invoke(cli, ["add", url])
    assert result.exit_code == 0, result.output
    assert "transcript junk" in result.output
    conn = ledger.connect()
    row = conn.execute("SELECT id FROM items").fetchone()
    assert ledger.item_state(conn, row["id"]) == "asking"


def test_add_survives_gatherer_failure_with_capture_kept(env, monkeypatch):
    url = "https://www.youtube.com/watch?v=abcdefghijk"

    def boom(u, t):
        raise RuntimeError("network down")

    monkeypatch.setitem(evidence.GATHERERS, "youtube", boom)
    result = CliRunner().invoke(cli, ["add", url])
    assert result.exit_code == 0, result.output
    assert "network down" in result.output
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
