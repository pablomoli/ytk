"""Tests for ytk.reddit_feed — subreddit browsing (never saved posts)."""

import json
import sqlite3

import pytest

from ytk.reddit_feed import (
    RedditAuthError,
    browse_subreddits,
    build_content_block,
    external_video_url,
    fetch_comments,
    fetch_listing,
    is_external,
    parse_posts,
    post_to_reelitem,
    reddit_cookie_header,
    top_comments,
)
from ytk.reels import ReelsState, load_state, save_state


def _listing(*posts):
    return {"data": {"children": [{"kind": "t3", "data": p} for p in posts]}}


def _post(
    pid,
    title="A post",
    is_self=False,
    url=None,
    domain="example.com",
    sub="TouchDesigner",
    selftext=None,
):
    if selftext is None:
        selftext = "body text" if is_self else ""
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
        "selftext": selftext,
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
    def test_external_link_post_stays_reddit(self):
        (p,) = parse_posts(_listing(_post("abc", url="https://youtu.be/xyz", domain="youtu.be")))
        assert is_external(p) is True
        item = post_to_reelitem(p)
        assert item.source == "reddit"
        assert item.url.endswith("/comments/abc/slug/")
        assert item.title == "A post"
        assert item.author == "r/TouchDesigner"
        assert {"url": "https://youtu.be/xyz", "kind": "link"} in (item.attachments or [])

    def test_selftext_capped(self):
        (p,) = parse_posts(_listing(_post("abc", is_self=True, selftext="x" * 5000)))
        item = post_to_reelitem(p)
        assert len(item.text) == 2000

    def test_self_post_has_no_link_attachment(self):
        (p,) = parse_posts(_listing(_post("abc", is_self=True, selftext="body")))
        item = post_to_reelitem(p)
        assert not item.attachments

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


class TestGalleryAndVideoAttachments:
    def _gallery_post(self, pid="gal1"):
        post = _post(pid, is_self=True, selftext="")
        post["is_gallery"] = True
        post["media_metadata"] = {
            "img2id": {
                "status": "valid",
                "e": "Image",
                "m": "image/jpg",
                "s": {
                    "u": "https://preview.redd.it/img2id.jpg?width=1080&amp;format=pjpg&amp;s=bbb"
                },
            },
            "img1id": {
                "status": "valid",
                "e": "Image",
                "m": "image/jpg",
                "s": {
                    "u": "https://preview.redd.it/img1id.jpg?width=1080&amp;format=pjpg&amp;s=aaa"
                },
            },
        }
        post["gallery_data"] = {
            "items": [{"media_id": "img1id", "id": 1}, {"media_id": "img2id", "id": 2}]
        }
        return post

    def test_gallery_post_extracts_ordered_unescaped_image_attachments(self):
        (p,) = parse_posts(_listing(self._gallery_post()))
        item = post_to_reelitem(p)
        assert item.attachments == [
            {
                "url": "https://preview.redd.it/img1id.jpg?width=1080&format=pjpg&s=aaa",
                "kind": "image",
            },
            {
                "url": "https://preview.redd.it/img2id.jpg?width=1080&format=pjpg&s=bbb",
                "kind": "image",
            },
        ]

    def test_gallery_post_animated_item_becomes_video_kind(self):
        post = self._gallery_post()
        post["media_metadata"]["img1id"]["s"] = {
            "gif": "https://preview.redd.it/img1id.gif?s=aaa",
            "mp4": "https://preview.redd.it/img1id.mp4?s=aaa",
        }
        (p,) = parse_posts(_listing(post))
        item = post_to_reelitem(p)
        assert item.attachments[0] == {
            "url": "https://preview.redd.it/img1id.mp4?s=aaa",
            "kind": "video",
        }

    def test_reddit_video_post_becomes_single_video_attachment(self):
        post = _post("vid1", url="https://v.redd.it/xyz", domain="v.redd.it")
        post["is_video"] = True
        post["media"] = {
            "reddit_video": {
                "fallback_url": "https://v.redd.it/xyz/DASH_480.mp4?source=fallback&amp;a=1",
                "height": 480,
            }
        }
        (p,) = parse_posts(_listing(post))
        item = post_to_reelitem(p)
        assert item.attachments == [
            {"url": "https://v.redd.it/xyz/DASH_480.mp4?source=fallback&a=1", "kind": "video"}
        ]

    def test_external_link_and_selftext_posts_have_no_gallery_attachments(self):
        (p,) = parse_posts(_listing(_post("abc", url="https://youtu.be/xyz", domain="youtu.be")))
        item = post_to_reelitem(p)
        assert item.attachments == [{"url": "https://youtu.be/xyz", "kind": "link"}]

        (p2,) = parse_posts(_listing(_post("abc2", is_self=True, selftext="body")))
        item2 = post_to_reelitem(p2)
        assert item2.attachments is None


class TestExternalVideoUrl:
    def test_external_video_url_detects_youtube(self):
        post = _post("abc", url="https://youtu.be/abc123DEF45", domain="youtu.be", is_self=False)
        assert external_video_url(post) == "https://youtu.be/abc123DEF45"

    def test_external_video_url_none_for_articles(self):
        post = _post(
            "abc", url="https://blog.example.com/post", domain="blog.example.com", is_self=False
        )
        assert external_video_url(post) is None

    def test_external_video_url_none_for_self_posts(self):
        post = _post("abc", is_self=True)
        assert external_video_url(post) is None


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


class TestBrowseSubreddits:
    def test_returns_every_post_across_subreddits(self, monkeypatch):
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
        items = browse_subreddits("c=1", ["TouchDesigner", "LocalLLaMA"])
        assert len(items) == 3
        # An API repeats itself: a second call returns the same three rather
        # than going quiet the way the deduping loop did.
        assert len(browse_subreddits("c=1", ["TouchDesigner", "LocalLLaMA"])) == 3

    def test_writes_nothing_to_the_queue(self, monkeypatch):
        """The whole point of the demotion: Reddit cannot reach the inbox."""
        monkeypatch.setattr(
            "ytk.reddit_feed.fetch_listing",
            lambda sub, cookie, **kw: _listing(_post("a1", is_self=True)),
        )
        state = ReelsState()
        items = browse_subreddits("c=1", ["Sub"])
        assert items and state.pending == []

    def test_one_failing_subreddit_does_not_sink_others(self, monkeypatch):
        def fake(sub, cookie, **kw):
            if sub == "Broken":
                raise RuntimeError("boom")
            return _listing(_post("ok1", is_self=True))

        monkeypatch.setattr("ytk.reddit_feed.fetch_listing", fake)
        assert len(browse_subreddits("c=1", ["Broken", "Fine"])) == 1

    def test_dedupes_within_a_single_call(self, monkeypatch):
        """The same post crossposted to two allowlisted subs returns once."""
        monkeypatch.setattr(
            "ytk.reddit_feed.fetch_listing",
            lambda sub, cookie, **kw: _listing(_post("a1", is_self=True)),
        )
        assert len(browse_subreddits("c=1", ["Sub", "OtherSub"])) == 1


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
    def test_reddit_seen_is_gone(self, tmp_path):
        """Loop bookkeeping. A stale key on disk must not resurrect the field."""
        path = tmp_path / "state.json"
        save_state(ReelsState(), path)
        path.write_text(
            json.dumps({**json.loads(path.read_text()), "reddit_seen": ["t3_a"]}),
            encoding="utf-8",
        )
        assert not hasattr(load_state(path), "reddit_seen")


class TestHubRegistration:
    """Reddit is an API, not a loop — no code path may enqueue it."""

    def test_not_a_pull_source(self):
        from ytk.ui import hub

        assert "reddit" not in hub.PULL_SOURCES
        assert "reddit" not in hub.PULL_SEAMS
        assert not hasattr(hub, "REDDIT_PULL")
        assert not hasattr(hub, "_reddit_pull")

    def test_source_refresh_has_no_reddit_adapter(self):
        from ytk.ui import source_refresh

        assert not hasattr(source_refresh, "pull_reddit")

    def test_refresh_never_reports_reddit(self, monkeypatch):
        from ytk.ui import hub

        monkeypatch.setattr(hub, "PULL_SOURCES", frozenset())
        result = hub.refresh_sources(only=set())
        assert "reddit" not in result
