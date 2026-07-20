"""Tests for ytk.tiktok_fav — favorites discovery via session replay."""

import sqlite3

import pytest

from ytk.reels import ReelItem, ReelsState, load_state, save_state
from ytk.tiktok_fav import (
    TikTokAuthError,
    favorites_to_reelitems,
    load_tiktok_cookies,
    parse_favorites_response,
    queue_new,
    zen_cookie_db,
)


def _response(entries):
    return {"itemList": entries, "hasMore": True}


def _entry(video_id, author="maker", desc="a video", cover="https://cdn/c.jpg"):
    return {
        "id": video_id,
        "desc": desc,
        "createTime": 1752900000,
        "author": {"uniqueId": author, "nickname": author.title()},
        "video": {"cover": cover, "duration": 30},
    }


class TestParseFavoritesResponse:
    def test_maps_items(self):
        items = parse_favorites_response(_response([_entry("111"), _entry("222", author="other")]))
        assert [i["id"] for i in items] == ["111", "222"]
        assert items[0]["url"] == "https://www.tiktok.com/@maker/video/111"
        assert items[0]["author"] == "maker"
        assert items[0]["desc"] == "a video"
        assert items[0]["cover"] == "https://cdn/c.jpg"

    def test_missing_author_gets_placeholder_url(self):
        entry = _entry("333")
        entry["author"] = None
        (item,) = parse_favorites_response(_response([entry]))
        assert item["url"] == "https://www.tiktok.com/@_/video/333"
        assert item["author"] is None

    def test_photo_mode_without_video_block(self):
        entry = _entry("444")
        del entry["video"]
        (item,) = parse_favorites_response(_response([entry]))
        assert item["cover"] is None

    def test_blank_desc_becomes_none(self):
        (item,) = parse_favorites_response(_response([_entry("555", desc="  ")]))
        assert item["desc"] is None

    def test_skips_entries_without_id(self):
        entry = _entry("")
        assert parse_favorites_response(_response([entry])) == []

    def test_empty_and_missing_item_list(self):
        assert parse_favorites_response({}) == []
        assert parse_favorites_response({"itemList": None}) == []


class TestFavoritesToReelItems:
    def test_builds_tiktok_reelitems(self):
        items = parse_favorites_response(_response([_entry("111")]))
        (reel,) = favorites_to_reelitems(items)
        assert reel.source == "tiktok"
        assert reel.url == "https://www.tiktok.com/@maker/video/111"
        assert reel.text == "a video"
        assert reel.preview_url == "https://cdn/c.jpg"


def _cookie_db(path, rows):
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE moz_cookies (name TEXT, value TEXT, host TEXT, path TEXT,"
        " expiry INTEGER, isSecure INTEGER, isHttpOnly INTEGER, sameSite INTEGER)"
    )
    con.executemany("INSERT INTO moz_cookies VALUES (?,?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()


class TestCookies:
    def test_loads_tiktok_cookies_only(self, tmp_path):
        db = tmp_path / "cookies.sqlite"
        _cookie_db(
            db,
            [
                ("sessionid", "abc", ".tiktok.com", "/", 2000000000, 1, 1, 0),
                ("theme", "dark", ".example.com", "/", 2000000000, 0, 0, 1),
            ],
        )
        cookies = load_tiktok_cookies(db)
        assert len(cookies) == 1
        (c,) = cookies
        assert c["name"] == "sessionid"
        assert c["domain"] == ".tiktok.com"
        assert c["secure"] is True and c["httpOnly"] is True
        assert c["sameSite"] == "None"

    def test_session_cookie_expiry_zero_maps_to_minus_one(self, tmp_path):
        db = tmp_path / "cookies.sqlite"
        _cookie_db(db, [("sessionid", "abc", ".tiktok.com", "/", 0, 1, 1, 0)])
        (c,) = load_tiktok_cookies(db)
        assert c["expires"] == -1.0

    def test_millisecond_epoch_expiry_normalized_to_seconds(self, tmp_path):
        db = tmp_path / "cookies.sqlite"
        _cookie_db(db, [("sessionid", "abc", ".tiktok.com", "/", 1800060071694, 1, 1, 0)])
        (c,) = load_tiktok_cookies(db)
        assert c["expires"] == pytest.approx(1800060071.694)

    def test_missing_sessionid_raises_auth_error(self, tmp_path):
        db = tmp_path / "cookies.sqlite"
        _cookie_db(db, [("tt_csrf_token", "x", ".tiktok.com", "/", 0, 1, 0, 1)])
        with pytest.raises(TikTokAuthError, match="sessionid"):
            load_tiktok_cookies(db)

    def test_zen_cookie_db_picks_newest_profile(self, tmp_path):
        old = tmp_path / "old.default" / "cookies.sqlite"
        new = tmp_path / "new.default" / "cookies.sqlite"
        for p in (old, new):
            p.parent.mkdir()
            p.write_bytes(b"")
        import os

        os.utime(old, (1, 1))
        assert zen_cookie_db(tmp_path) == new

    def test_zen_cookie_db_missing_raises(self, tmp_path):
        with pytest.raises(TikTokAuthError, match="Zen"):
            zen_cookie_db(tmp_path / "nope")


class TestQueueNew:
    def _fetched(self, *ids):
        return parse_favorites_response(_response([_entry(i) for i in ids]))

    def test_appends_and_marks_seen(self):
        state = ReelsState()
        added = queue_new(state, self._fetched("111", "222"))
        assert added == 2
        assert [i.url for i in state.pending] == [
            "https://www.tiktok.com/@maker/video/111",
            "https://www.tiktok.com/@maker/video/222",
        ]
        assert state.tiktok_seen == ["111", "222"]

    def test_dedupes_against_pending_but_still_marks_seen(self):
        state = ReelsState(
            pending=[ReelItem(url="https://www.tiktok.com/@maker/video/111", source="tiktok")]
        )
        added = queue_new(state, self._fetched("111", "222"))
        assert added == 1
        assert state.tiktok_seen == ["111", "222"]

    def test_dedupes_against_ingested_urls(self):
        state = ReelsState()
        added = queue_new(
            state,
            self._fetched("111"),
            extra_known={"https://www.tiktok.com/@maker/video/111"},
        )
        assert added == 0
        assert state.tiktok_seen == ["111"]

    def test_tiktok_seen_survives_state_round_trip(self, tmp_path):
        state = ReelsState(tiktok_seen=["111", "222"])
        path = tmp_path / "state.json"
        save_state(state, path)
        assert load_state(path).tiktok_seen == ["111", "222"]


class TestHubPull:
    def test_tt_pull_registered_in_refresh_sources(self):
        from ytk.ui import hub

        assert hub.TT_PULL is hub._tt_pull

    def test_tt_pull_disabled_without_username(self, monkeypatch):
        from ytk.ui import hub

        class Cfg:
            tiktok_username = None

        monkeypatch.setattr("ytk.config.load_config", lambda: Cfg())
        assert hub._tt_pull(ReelsState()) == 0
