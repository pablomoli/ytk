"""Tests for the pure stratified-selection algorithm."""

from ytk.autoingest import LOVED_BOOST, allocate_slots, stratify_select


def _s(url, theme, score, channel=None):
    return {"url": url, "theme_id": theme, "score": score, "channel_key": channel}


class TestAllocateSlots:
    def test_proportional_with_floor(self):
        alloc = allocate_slots({"a": 0.8, "b": 0.2}, ["a", "b"], 10)
        assert sum(alloc.values()) == 10
        assert alloc["a"] > alloc["b"]
        assert alloc["b"] >= 1  # floor

    def test_sums_to_count(self):
        alloc = allocate_slots({"a": 0.5, "b": 0.3, "c": 0.2}, ["a", "b", "c"], 7)
        assert sum(alloc.values()) == 7

    def test_unknown_theme_weights_fall_back_to_even(self):
        alloc = allocate_slots({}, ["a", "b"], 4)
        assert sum(alloc.values()) == 4
        assert alloc["a"] >= 1 and alloc["b"] >= 1


class TestStratifySelect:
    def test_spreads_across_themes_not_just_biggest(self):
        # theme a dominates weight, but pure top-k would take all a's; stratify
        # must still surface a b even though a's scores are higher
        scored = [_s(f"a{i}", "a", 0.9 - i * 0.01) for i in range(20)]
        scored += [_s(f"b{i}", "b", 0.5 - i * 0.01) for i in range(20)]
        picked = stratify_select(scored, 10, {"a": 0.8, "b": 0.2})
        themes = {p["theme_id"] for p in picked}
        assert "b" in themes
        assert len(picked) == 10

    def test_respects_count(self):
        scored = [_s(f"x{i}", "a", 0.5) for i in range(50)]
        assert len(stratify_select(scored, 30, {"a": 1.0})) == 30

    def test_muted_channel_excluded(self):
        scored = [_s("keep", "a", 0.5, channel="youtube:ok"),
                  _s("drop", "a", 0.99, channel="youtube:muted")]
        picked = stratify_select(scored, 5, {"a": 1.0}, muted_keys={"youtube:muted"})
        urls = {p["url"] for p in picked}
        assert "keep" in urls and "drop" not in urls

    def test_loved_channel_boosted_over_better_stranger(self):
        scored = [_s("stranger", "a", 0.60, channel="youtube:x"),
                  _s("loved", "a", 0.50, channel="youtube:fav")]
        picked = stratify_select(scored, 1, {"a": 1.0}, loved_keys={"youtube:fav"})
        assert picked[0]["url"] == "loved"
        assert picked[0]["eff_score"] == 0.50 + LOVED_BOOST

    def test_backfills_when_a_theme_runs_dry(self):
        # allocate wants 2 from b but b has only 1 item; total still reaches count
        scored = [_s(f"a{i}", "a", 0.9 - i * 0.01) for i in range(10)]
        scored += [_s("b0", "b", 0.5)]
        picked = stratify_select(scored, 6, {"a": 0.5, "b": 0.5})
        assert len(picked) == 6
        assert any(p["theme_id"] == "b" for p in picked)

    def test_empty_inputs(self):
        assert stratify_select([], 10, {"a": 1.0}) == []
        assert stratify_select([_s("x", "a", 0.5)], 0, {"a": 1.0}) == []
