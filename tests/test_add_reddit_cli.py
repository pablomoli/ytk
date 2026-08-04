"""add-reddit CLI: linked-video ingest dispatch + cross-linking wiring (#163).

Follows the CliRunner+monkeypatch template from test_add_instagram_cli.py:
stub every side-effecting collaborator (fetch/write/upsert, _get_brain_path)
and drive the command through click, no network.
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

import ytk.cli as cli_mod
import ytk.config as config_mod
import ytk.db as db_mod
import ytk.enrich as enrich_mod
import ytk.reddit_feed as reddit_feed_mod
import ytk.store as store_mod
import ytk.vault as vault_mod
from ytk.enrich import Enrichment

_ENR = Enrichment(
    thesis="t",
    summary="s",
    key_concepts=[],
    insights=[],
    interest_tags=["ai"],
    key_moments=[],
)


def _post(url=None, domain="example.com", is_self=False, title="A post"):
    return {
        "id": "abc",
        "fullname": "t3_abc",
        "permalink": "https://old.reddit.com/r/x/comments/abc/slug/",
        "title": title,
        "subreddit": "x",
        "author": "someone",
        "score": 1,
        "num_comments": 0,
        "is_self": is_self,
        "selftext": "body" if is_self else "",
        "url": url if url is not None else "https://old.reddit.com/r/x/comments/abc/slug/",
        "domain": ("self.x" if is_self else domain),
        "thumbnail": None,
        "created_utc": 1752900000,
        "over_18": False,
    }


class _Hub:
    enrich_tone = "default"


class _Cfg:
    hub = _Hub()


@pytest.fixture
def calls(monkeypatch, tmp_path):
    """Mock every side-effecting collaborator; record how add_reddit drives them."""
    rec = {
        "write": None,
        "upsert": None,
        "cross_link": None,
        "add_invoked": None,
        "add_raises": None,
        "processed": False,
    }

    monkeypatch.setattr(vault_mod, "_get_brain_path", lambda: tmp_path)
    note_dir = tmp_path / "sources" / "reddit"
    note_dir.mkdir(parents=True)

    def fake_write(post, enrichment, comments):
        note = note_dir / "a-post.md"
        note.write_text("---\nurl: https://old.reddit.com/r/x/1\n---\nbody\n", encoding="utf-8")
        rec["write"] = {"post": post, "comments": comments}
        return note

    def fake_upsert(doc_id, body, meta):
        rec["upsert"] = doc_id

    def fake_cross_link(reddit_note, video_url, search_dir=None):
        rec["cross_link"] = {"reddit_note": reddit_note, "video_url": video_url}

    def fake_add(url, note="", force=False):
        rec["add_invoked"] = {"url": url, "note": note}
        if rec["add_raises"] is not None:
            raise rec["add_raises"]

    monkeypatch.setattr(reddit_feed_mod, "reddit_cookie_header", lambda: "cookie")
    monkeypatch.setattr(reddit_feed_mod, "fetch_comments", lambda url, cookie: ["thread"])
    monkeypatch.setattr(reddit_feed_mod, "post_from_thread", lambda thread: rec["post"])
    monkeypatch.setattr(reddit_feed_mod, "top_comments", lambda thread: [])
    monkeypatch.setattr(reddit_feed_mod, "build_content_block", lambda post, comments: "block")
    monkeypatch.setattr(enrich_mod, "enrich_content", lambda *a, **kw: _ENR)
    monkeypatch.setattr(config_mod, "load_config", lambda: _Cfg())

    monkeypatch.setattr(vault_mod, "write_reddit_note", fake_write)
    monkeypatch.setattr(vault_mod, "_cross_link_notes", fake_cross_link)
    monkeypatch.setattr(store_mod, "upsert_doc", fake_upsert)
    monkeypatch.setattr(cli_mod.add, "callback", fake_add)
    monkeypatch.setattr(db_mod, "is_processed", lambda vid: rec["processed"])

    rec["post"] = _post()
    return rec


def _run(*args):
    return CliRunner().invoke(cli_mod.cli, ["add-reddit", *args])


def test_no_external_video_skips_invoke_and_cross_link(calls):
    calls["post"] = _post(url="https://blog.example.com/x", domain="blog.example.com")
    result = _run("https://old.reddit.com/r/x/comments/abc/slug/")
    assert result.exit_code == 0, result.output
    assert calls["add_invoked"] is None
    assert calls["cross_link"] is None


def test_external_video_not_processed_invokes_add_and_cross_links(calls):
    calls["post"] = _post(url="https://youtu.be/abc123DEF45", domain="youtu.be")
    calls["processed"] = False
    result = _run("https://old.reddit.com/r/x/comments/abc/slug/")
    assert result.exit_code == 0, result.output
    assert calls["add_invoked"] == {"url": "https://youtu.be/abc123DEF45", "note": ""}
    assert calls["cross_link"]["video_url"] == "https://youtu.be/abc123DEF45"
    assert calls["cross_link"]["reddit_note"].name == "a-post.md"


def test_external_video_already_processed_skips_invoke_but_cross_links(calls):
    calls["post"] = _post(url="https://youtu.be/abc123DEF45", domain="youtu.be")
    calls["processed"] = True
    result = _run("https://old.reddit.com/r/x/comments/abc/slug/")
    assert result.exit_code == 0, result.output
    assert calls["add_invoked"] is None
    assert calls["cross_link"]["video_url"] == "https://youtu.be/abc123DEF45"


def test_add_failure_still_cross_links_and_exits_clean(calls):
    calls["post"] = _post(url="https://youtu.be/abc123DEF45", domain="youtu.be")
    calls["processed"] = False
    calls["add_raises"] = RuntimeError("no captions")
    result = _run("https://old.reddit.com/r/x/comments/abc/slug/")
    assert result.exit_code == 0, result.output
    assert calls["add_invoked"] is not None
    assert "failed" in result.output.lower()
    assert calls["cross_link"]["video_url"] == "https://youtu.be/abc123DEF45"
