"""Tests for the `ytk reels` CLI command (picker wiring, no network)."""

import pytest
from click.testing import CliRunner

import ytk.cli as cli_mod
import ytk.reels as reels_mod

LINKS = [
    "https://www.instagram.com/reel/aaa/",
    "https://www.instagram.com/reel/bbb/",
    "https://www.instagram.com/p/ccc/",
]


def _items():
    return [
        reels_mod.ReelItem(
            url=LINKS[0],
            author="author_a",
            shared_at="2026-07-01",
            preview_url="https://cdn.example/a.jpg",
        ),
        reels_mod.ReelItem(url=LINKS[1], author="author_b", shared_at="2026-07-02"),
        reels_mod.ReelItem(url=LINKS[2]),
    ]


@pytest.fixture
def harness(monkeypatch, tmp_path):
    """Stub the discovery layer and the add pipeline; record what gets called."""
    calls = {"added": [], "saved": [], "peer": "unset", "refresh_state": None}

    monkeypatch.setenv("INSTAGRAM_SESSIONID", "sess-123")
    monkeypatch.setattr(reels_mod, "get_client", lambda sessionid: object())
    monkeypatch.setattr(
        reels_mod,
        "load_state",
        lambda: reels_mod.ReelsState(thread_id="ts", last_seen_message_id="5"),
    )
    monkeypatch.setattr(reels_mod, "GALLERY_PATH", tmp_path / "gallery.html")

    def fake_refresh(client, state, peer=None):
        calls["peer"] = peer
        calls["refresh_state"] = state
        return reels_mod.ReelsState(thread_id="ts", last_seen_message_id="9", pending=_items())

    monkeypatch.setattr(reels_mod, "refresh", fake_refresh)
    monkeypatch.setattr(
        reels_mod,
        "save_state",
        lambda st: calls["saved"].append([i.url for i in st.pending]),
    )
    monkeypatch.setattr(
        cli_mod,
        "_capture_and_read",
        lambda url, note, surface, source=None: calls["added"].append(url),
    )
    monkeypatch.setattr(cli_mod.time, "sleep", lambda s: None)
    return calls


def test_reels_all_ingests_everything_and_empties_pending(harness):
    result = CliRunner().invoke(cli_mod.cli, ["reels", "--all"])
    assert result.exit_code == 0, result.output
    assert harness["added"] == LINKS
    assert harness["saved"][-1] == []


def test_reels_dry_run_lists_without_ingesting_or_saving(harness):
    result = CliRunner().invoke(cli_mod.cli, ["reels", "--dry-run"])
    assert result.exit_code == 0, result.output
    for link in LINKS:
        assert link in result.output
    assert harness["added"] == []
    assert harness["saved"] == []


def test_reels_all_with_limit_keeps_rest_pending(harness):
    result = CliRunner().invoke(cli_mod.cli, ["reels", "--all", "--limit", "2"])
    assert result.exit_code == 0, result.output
    assert harness["added"] == LINKS[:2]
    assert harness["saved"][-1] == [LINKS[2]]


def test_reels_interactive_pick_ingests_selection(harness):
    result = CliRunner().invoke(cli_mod.cli, ["reels"], input="2\n")
    assert result.exit_code == 0, result.output
    assert harness["added"] == [LINKS[1]]
    assert harness["saved"][-1] == [LINKS[0], LINKS[2]]


def test_reels_interactive_none_keeps_everything_pending(harness):
    result = CliRunner().invoke(cli_mod.cli, ["reels"], input="none\n")
    assert result.exit_code == 0, result.output
    assert harness["added"] == []
    # discovery is still persisted
    assert harness["saved"][-1] == LINKS


def test_reels_interactive_reprompts_on_bad_selection(harness):
    result = CliRunner().invoke(cli_mod.cli, ["reels"], input="banana\n1\n")
    assert result.exit_code == 0, result.output
    assert harness["added"] == [LINKS[0]]


def test_reels_forwards_peer_from_env(harness, monkeypatch):
    monkeypatch.setenv("INSTAGRAM_PEER", "integratederivate")
    result = CliRunner().invoke(cli_mod.cli, ["reels", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert harness["peer"] == "integratederivate"


def test_reels_interactive_shows_author_and_date(harness):
    result = CliRunner().invoke(cli_mod.cli, ["reels"], input="none\n")
    assert result.exit_code == 0, result.output
    assert "author_a" in result.output
    assert "2026-07-01" in result.output


def test_reels_gallery_writes_html_and_opens_browser(harness, monkeypatch):
    opened = []
    monkeypatch.setattr("webbrowser.open", lambda target: opened.append(target))
    result = CliRunner().invoke(cli_mod.cli, ["reels", "--gallery"], input="none\n")
    assert result.exit_code == 0, result.output
    html = reels_mod.GALLERY_PATH.read_text(encoding="utf-8")
    assert "https://cdn.example/a.jpg" in html
    assert len(opened) == 1


def test_reels_rebuild_starts_from_blank_state(harness):
    result = CliRunner().invoke(cli_mod.cli, ["reels", "--rebuild"], input="none\n")
    assert result.exit_code == 0, result.output
    assert harness["refresh_state"].last_seen_message_id is None
    assert harness["refresh_state"].pending == []


def test_reels_no_pending(harness, monkeypatch):
    monkeypatch.setattr(
        reels_mod,
        "refresh",
        lambda client, state, peer=None: reels_mod.ReelsState(
            thread_id="ts", last_seen_message_id="9"
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
