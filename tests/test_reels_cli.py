"""Tests for the `ytk reels` CLI command (discovery wiring, no network)."""

import pytest
from click.testing import CliRunner

import ytk.cli as cli_mod
import ytk.reels as reels_mod

LINKS = [
    "https://www.instagram.com/reel/aaa/",
    "https://www.instagram.com/reel/bbb/",
    "https://www.instagram.com/p/ccc/",
]


@pytest.fixture
def harness(monkeypatch):
    """Stub the discovery layer and the add pipeline; record what gets called."""
    calls = {"added": [], "saved": []}

    monkeypatch.setenv("INSTAGRAM_SESSIONID", "sess-123")
    monkeypatch.setattr(reels_mod, "get_client", lambda sessionid: object())
    monkeypatch.setattr(reels_mod, "load_state", lambda: reels_mod.ReelsState())
    monkeypatch.setattr(
        reels_mod,
        "fetch_new_links",
        lambda client, state: (
            list(LINKS),
            reels_mod.ReelsState(thread_id="ts", last_seen_message_id="9"),
        ),
    )
    monkeypatch.setattr(reels_mod, "save_state", lambda st: calls["saved"].append(st))
    monkeypatch.setattr(
        cli_mod.add, "callback", lambda url, force=False: calls["added"].append(url)
    )
    monkeypatch.setattr(cli_mod.time, "sleep", lambda s: None)
    return calls


def test_reels_ingests_all_links_and_saves_cursor(harness):
    result = CliRunner().invoke(cli_mod.cli, ["reels"])
    assert result.exit_code == 0, result.output
    assert harness["added"] == LINKS
    assert len(harness["saved"]) == 1
    assert harness["saved"][0].last_seen_message_id == "9"


def test_reels_dry_run_lists_without_ingesting(harness):
    result = CliRunner().invoke(cli_mod.cli, ["reels", "--dry-run"])
    assert result.exit_code == 0, result.output
    for link in LINKS:
        assert link in result.output
    assert harness["added"] == []
    assert harness["saved"] == []


def test_reels_limit_truncates_and_keeps_cursor(harness):
    result = CliRunner().invoke(cli_mod.cli, ["reels", "--limit", "2"])
    assert result.exit_code == 0, result.output
    assert harness["added"] == LINKS[:2]
    # cursor must not advance past unprocessed messages
    assert harness["saved"] == []


def test_reels_no_new_links(harness, monkeypatch):
    monkeypatch.setattr(
        reels_mod,
        "fetch_new_links",
        lambda client, state: (
            [],
            reels_mod.ReelsState(thread_id="ts", last_seen_message_id="9"),
        ),
    )
    result = CliRunner().invoke(cli_mod.cli, ["reels"])
    assert result.exit_code == 0, result.output
    assert harness["added"] == []
    assert len(harness["saved"]) == 1


def test_reels_missing_sessionid_exits_with_help(monkeypatch):
    monkeypatch.delenv("INSTAGRAM_SESSIONID", raising=False)
    result = CliRunner().invoke(cli_mod.cli, ["reels"])
    assert result.exit_code == 1
    assert "INSTAGRAM_SESSIONID" in result.output
