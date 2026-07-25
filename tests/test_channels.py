"""Tests for ytk.channels — creator aggregation + affinity."""

import pytest

from ytk.channels import (
    aggregate,
    channel_key,
    channel_of,
    load_affinity,
    loved_channels,
    merge_affinity,
    muted_channels,
    set_status,
)


class TestChannelOf:
    def test_youtube_uses_uploader(self):
        assert channel_of({"uploader": "Curtis Holt"}, "youtube") == "Curtis Holt"

    def test_tiktok_and_instagram_use_username(self):
        assert channel_of({"username": "thisguyvibecodes"}, "tiktok") == "thisguyvibecodes"
        assert channel_of({"username": "as.ws__"}, "instagram") == "as.ws__"

    def test_reddit_uses_subreddit_never_poster(self):
        meta = {"subreddit": "r/TouchDesigner", "author": "u/vtln_nltv"}
        assert channel_of(meta, "reddit") == "r/TouchDesigner"

    def test_reddit_without_subreddit_does_not_fall_back_to_author(self):
        # never attribute a subreddit's content to one poster
        assert (
            channel_of({"author": "u/someone", "url": "https://reddit.com/r/x/y"}, "reddit")
            == "reddit.com"
        )

    def test_web_uses_author_then_domain(self):
        assert channel_of({"author": "Jane Doe", "url": "https://blog.dev/x"}, "web") == "Jane Doe"
        assert (
            channel_of({"author": "", "url": "https://www.shopify.com/editions"}, "web")
            == "shopify.com"
        )

    def test_excluded_sources_have_no_channel(self):
        assert channel_of({"source": "voice"}, "memo") is None
        assert channel_of({}, "imessage") is None

    def test_no_resolvable_creator_returns_none(self):
        assert channel_of({}, "web") is None


class TestChannelKey:
    def test_case_insensitive(self):
        assert channel_key("YouTube", "Curtis Holt") == channel_key("youtube", "curtis holt")

    def test_namespaced_by_source(self):
        assert channel_key("tiktok", "x") != channel_key("instagram", "x")


class TestAggregate:
    def _card(self, source, channel, tags=(), title="t", added="2026-07-10"):
        return {
            "source": source,
            "channel": channel,
            "tags": list(tags),
            "title": title,
            "path": f"p/{title}",
            "added": added,
        }

    def test_groups_and_counts(self):
        cards = [
            self._card("youtube", "Curtis Holt", tags=["blender"]),
            self._card("youtube", "Curtis Holt", tags=["blender", "shaders"], added="2026-07-15"),
            self._card("tiktok", "vibecoder", tags=["ai"]),
        ]
        entries = aggregate(cards)
        assert entries[0]["channel"] == "Curtis Holt"
        assert entries[0]["count"] == 2
        assert entries[0]["last_seen"] == "2026-07-15"
        assert "blender" in entries[0]["top_tags"]
        assert entries[1]["count"] == 1

    def test_skips_channelless_cards(self):
        assert aggregate([{"source": "memo", "channel": None}]) == []

    def test_skips_memos_even_when_channel_set(self):
        # the memo card branch sets channel="voice"/"imessage" downstream
        assert (
            aggregate(
                [
                    {"source": "memo", "channel": "voice"},
                    {"source": "imessage", "channel": "imessage"},
                ]
            )
            == []
        )

    def test_case_insensitive_grouping(self):
        cards = [self._card("youtube", "Curtis Holt"), self._card("youtube", "curtis holt")]
        entries = aggregate(cards)
        assert len(entries) == 1 and entries[0]["count"] == 2

    def test_top_tags_capped_at_three(self):
        cards = [self._card("youtube", "X", tags=["a", "b", "c", "d", "e"])]
        assert len(aggregate(cards)[0]["top_tags"]) == 3


class TestAffinity:
    def test_set_and_load_roundtrip(self, tmp_path):
        p = tmp_path / "channels.json"
        set_status("youtube:curtis holt", "loved", p)
        assert load_affinity(p)["youtube:curtis holt"]["status"] == "loved"

    def test_clearing_status_removes_entry(self, tmp_path):
        p = tmp_path / "channels.json"
        set_status("k", "loved", p)
        set_status("k", None, p)
        assert "k" not in load_affinity(p)

    def test_invalid_status_rejected(self, tmp_path):
        with pytest.raises(ValueError):
            set_status("k", "adored", tmp_path / "c.json")

    def test_loved_and_muted_sets(self, tmp_path):
        p = tmp_path / "channels.json"
        set_status("a", "loved", p)
        set_status("b", "muted", p)
        aff = load_affinity(p)
        assert loved_channels(aff) == {"a"}
        assert muted_channels(aff) == {"b"}

    def test_corrupt_file_tolerated(self, tmp_path):
        p = tmp_path / "channels.json"
        p.write_text("{not json", encoding="utf-8")
        assert load_affinity(p) == {}


class TestMergeAffinity:
    def test_loved_sorts_first_then_count(self):
        entries = [
            {"key": "a", "count": 100, "status": None},
            {"key": "b", "count": 2, "status": None},
        ]
        merged = merge_affinity(entries, {"b": {"status": "loved"}})
        assert merged[0]["key"] == "b"  # loved beats higher count
        assert merged[0]["status"] == "loved"

    def test_muted_sorts_last(self):
        entries = [{"key": "a", "count": 5}, {"key": "b", "count": 5}]
        merged = merge_affinity(entries, {"a": {"status": "muted"}})
        assert merged[-1]["key"] == "a"
