"""Tests for ytk.reddit_feed — subreddit browsing (never saved posts)."""

import sqlite3

import pytest

from ytk.reddit_feed import (
    RedditAuthError,
    build_content_block,
    fetch_comments,
    fetch_listing,
    is_external,
    parse_posts,
    post_to_reelitem,
    reddit_cookie_header,
    sync_subreddits,
    top_comments,
)
from ytk.reels import ReelsState, load_state, save_state


def _listing(*posts):
    return {"data": {"children": [{"kind": "t3", "data": p} for p in posts]}}


def _post(pid, title="A post", is_self=False, url=None, domain="example.com", sub="TouchDesigner"):
    return {
        "id": pid,
        "name": f"t3_{pid}",
        "permalink": f"/r/{sub}/comments/{pid}/slug/",
        "title": title,
        "subreddit": sub,
        "author": "someone",
        "score": 42,
        "num_comments": 10,
        "is_self": is_self,
        "selftext": "body text" if is_self else "",
        "url": url
        if url is not None
        else (
            f"https://old.reddit.com/r/{sub}/comments/{pid}/slug/"
            if is_self
            else "https://example.com/x"
        ),
        "domain": ("self." + sub) if is_self else domain,
        "thumbnail": "https://b.thumbs.redditmedia.com/x.jpg",
        "created_utc": 1752900000,
        "over_18": False,
    }


class TestParsePosts:
    def test_extracts_fields(self):
        (p,) = parse_posts(_listing(_post("abc", title="Hello")))
        assert p["id"] == "abc"
        assert p["fullname"] == "t3_abc"
        assert p["permalink"] == "https://old.reddit.com/r/TouchDesigner/comments/abc/slug/"
        assert p["title"] == "Hello"
        assert p["thumbnail"] == "https://b.thumbs.redditmedia.com/x.jpg"

    def test_skips_non_t3_and_missing_ids(self):
        listing = {
            "data": {
                "children": [
                    {"kind": "t1", "data": {"id": "c1"}},
                    {"kind": "t3", "data": {"title": "no id"}},
                ]
            }
        }
        assert parse_posts(listing) == []

    def test_non_http_thumbnail_becomes_none(self):
        post = _post("abc")
        post["thumbnail"] = "self"
        (p,) = parse_posts(_listing(post))
        assert p["thumbnail"] is None


class TestIsExternalAndMapping:
    def test_external_link_post_uses_native_url_and_source(self):
        (p,) = parse_posts(_listing(_post("abc", url="https://youtu.be/xyz", domain="youtu.be")))
        assert is_external(p) is True
        item = post_to_reelitem(p)
        assert item.url == "https://youtu.be/xyz"
        assert item.source == "youtube"
        assert item.author == "r/TouchDesigner"

    def test_self_post_uses_permalink_and_reddit_source(self):
        (p,) = parse_posts(_listing(_post("abc", is_self=True)))
        assert is_external(p) is False
        item = post_to_reelitem(p)
        assert item.source == "reddit"
        assert item.url.endswith("/comments/abc/slug/")

    def test_reddit_hosted_media_stays_reddit(self):
        (p,) = parse_posts(_listing(_post("abc", url="https://v.redd.it/xyz", domain="v.redd.it")))
        assert is_external(p) is False
        assert post_to_reelitem(p).source == "reddit"


class TestFetchListingGuards:
    def test_rejects_bad_subreddit_names(self):
        for bad in ["user/pablomoli", "../saved", "a b", "", "x/y"]:
            with pytest.raises(ValueError):
                fetch_listing(bad, "cookie=1")

    def test_rejects_bad_sort_and_window(self):
        with pytest.raises(ValueError):
            fetch_listing("TouchDesigner", "c=1", sort="saved")
        with pytest.raises(ValueError):
            fetch_listing("TouchDesigner", "c=1", sort="top", window="forever")

    def test_fetch_comments_refuses_non_r_permalink(self):
        with pytest.raises(ValueError):
            fetch_comments("https://old.reddit.com/user/pablomoli/saved/", "c=1")


class TestTopComments:
    def _thread(self, *comments):
        kids = [{"kind": "t1", "data": c} for c in comments]
        return [{"data": {"children": []}}, {"data": {"children": kids}}]

    def test_orders_by_score_and_filters(self):
        thread = self._thread(
            {"author": "a", "score": 5, "body": "good"},
            {"author": "AutoModerator", "score": 99, "body": "bot"},
            {"author": "b", "score": 20, "body": "best"},
            {"author": "c", "score": 0, "body": "low"},
            {"author": "d", "score": 3, "body": "[deleted]"},
        )
        out = top_comments(thread, n=5, min_score=1)
        assert [c["author"] for c in out] == ["b", "a"]

    def test_handles_malformed_thread(self):
        assert top_comments([]) == []
        assert top_comments([{"data": {}}]) == []


class TestBuildContentBlock:
    def test_self_post_block_has_body_and_comments(self):
        (p,) = parse_posts(_listing(_post("abc", is_self=True)))
        block = build_content_block(p, [{"author": "z", "score": 9, "body": "insight"}])
        assert "Subreddit: r/TouchDesigner" in block
        assert "Body:" in block and "body text" in block
        assert "u/z (9): insight" in block

    def test_link_post_block_names_target(self):
        (p,) = parse_posts(
            _listing(_post("abc", url="https://example.com/x", domain="example.com"))
        )
        block = build_content_block(p, [])
        assert "Links to: https://example.com/x" in block


class TestSyncSubreddits:
    def test_dedupes_and_records_seen(self, monkeypatch):
        listings = {
            "TouchDesigner": _listing(
                _post("a1", url="https://ex.com/1", domain="ex.com"), _post("a2", is_self=True)
            ),
            "LocalLLaMA": _listing(_post("b1", url="https://ex.com/2", domain="ex.com")),
        }
        monkeypatch.setattr(
            "ytk.reddit_feed.fetch_listing",
            lambda sub, cookie, **kw: listings[sub],
        )
        state = ReelsState()
        added = sync_subreddits(state, "c=1", ["TouchDesigner", "LocalLLaMA"])
        assert added == 3
        assert set(state.reddit_seen) == {"t3_a1", "t3_a2", "t3_b1"}
        # second run: everything already seen
        assert sync_subreddits(state, "c=1", ["TouchDesigner", "LocalLLaMA"]) == 0

    def test_one_failing_subreddit_does_not_sink_others(self, monkeypatch):
        def fake(sub, cookie, **kw):
            if sub == "Broken":
                raise RuntimeError("boom")
            return _listing(_post("ok1", is_self=True))

        monkeypatch.setattr("ytk.reddit_feed.fetch_listing", fake)
        state = ReelsState()
        assert sync_subreddits(state, "c=1", ["Broken", "Fine"]) == 1

    def test_dedupes_against_extra_known_urls(self, monkeypatch):
        monkeypatch.setattr(
            "ytk.reddit_feed.fetch_listing",
            lambda sub, cookie, **kw: _listing(
                _post("a1", url="https://ex.com/1", domain="ex.com")
            ),
        )
        state = ReelsState()
        added = sync_subreddits(state, "c=1", ["Sub"], extra_known={"https://ex.com/1"})
        assert added == 0
        assert state.reddit_seen == ["t3_a1"]


def _cookie_db(path, rows):
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE moz_cookies (name TEXT, value TEXT, host TEXT, path TEXT,"
        " expiry INTEGER, isSecure INTEGER, isHttpOnly INTEGER, sameSite INTEGER)"
    )
    con.executemany("INSERT INTO moz_cookies (name, value, host) VALUES (?,?,?)", rows)
    con.commit()
    con.close()


class TestCookieHeader:
    def test_builds_header_when_session_present(self, tmp_path):
        db = tmp_path / "cookies.sqlite"
        _cookie_db(
            db, [("reddit_session", "abc", ".reddit.com"), ("token_v2", "xyz", ".reddit.com")]
        )
        hdr = reddit_cookie_header(db)
        assert "reddit_session=abc" in hdr and "token_v2=xyz" in hdr

    def test_missing_session_raises(self, tmp_path):
        db = tmp_path / "cookies.sqlite"
        _cookie_db(db, [("edgebucket", "e", ".reddit.com")])
        with pytest.raises(RedditAuthError):
            reddit_cookie_header(db)


class TestStateRoundTrip:
    def test_reddit_seen_persists(self, tmp_path):
        state = ReelsState(reddit_seen=["t3_a", "t3_b"])
        path = tmp_path / "state.json"
        save_state(state, path)
        assert load_state(path).reddit_seen == ["t3_a", "t3_b"]


class TestHubRegistration:
    def test_reddit_pull_registered(self):
        from ytk.ui import hub

        assert hub.REDDIT_PULL is hub._reddit_pull

    def test_disabled_without_allowlist(self, monkeypatch):
        from ytk.ui import hub

        class Cfg:
            reddit_subreddits = []

        monkeypatch.setattr("ytk.config.load_config", lambda: Cfg())
        assert hub._reddit_pull(ReelsState()) == 0
