"""Tests for the scorer and run guardrails (encoder/profile mocked)."""

from types import SimpleNamespace

import numpy as np

from ytk import autoingest


def _item(url, text, source="tiktok", author="bob"):
    return SimpleNamespace(url=url, text=text, source=source, author=author)


class TestScorePending:
    def test_filters_textless_and_ingested_then_assigns_best_theme(self, monkeypatch):
        # a 2-D toy space: "ai" aligns with axis 0, everything else axis 1
        def fake_ef(texts):
            return [[1.0, 0.0] if "ai" in t else [0.0, 1.0] for t in texts]

        monkeypatch.setattr("ytk.store._get_ef", lambda: fake_ef)
        theme_vecs = [
            (SimpleNamespace(id="ai"), np.array([1.0, 0.0])),
            (SimpleNamespace(id="art"), np.array([0.0, 1.0])),
        ]
        pending = [
            _item("u1", "ai agents", author="bob"),
            _item("u2", "pretty art", source="reddit", author="r/art"),
            _item("u3", ""),  # no text -> skipped
            _item("u4", "ai stuff", author="y"),  # already ingested -> skipped
        ]
        scored = autoingest.score_pending(pending, theme_vecs, ingested={"u4"})

        by_url = {s["url"]: s for s in scored}
        assert set(by_url) == {"u1", "u2"}
        assert by_url["u1"]["theme_id"] == "ai"
        assert by_url["u2"]["theme_id"] == "art"
        assert by_url["u1"]["channel_key"] == "tiktok:bob"
        assert by_url["u2"]["channel_key"] == "reddit:r/art"
        assert by_url["u1"]["score"] > 0.9  # cosine with aligned centroid

    def test_no_candidates_returns_empty(self, monkeypatch):
        monkeypatch.setattr("ytk.store._get_ef", lambda: lambda texts: [[1.0]] * len(texts))
        assert (
            autoingest.score_pending(
                [_item("u", "")], [(SimpleNamespace(id="a"), np.array([1.0]))], set()
            )
            == []
        )

    def test_missing_author_yields_no_channel_key(self, monkeypatch):
        monkeypatch.setattr("ytk.store._get_ef", lambda: lambda texts: [[1.0, 0.0] for _ in texts])
        tv = [(SimpleNamespace(id="a"), np.array([1.0, 0.0]))]
        (s,) = autoingest.score_pending([_item("u", "hi", author=None)], tv, set())
        assert s["channel_key"] is None
