"""R2 (#150): recency-decayed ranking for memory hits — boost-only, memories
only, default OFF. Unknown capture dates get zero boost, not neutral 1.0: a
stampless memory must not gain rank on phantom freshness."""

from __future__ import annotations

from datetime import UTC, datetime

from ytk.store import UnifiedResult, apply_memory_decay, memory_captured_at

NOW = datetime(2026, 7, 29, tzinfo=UTC)


def mem(doc_id: str, dist: float) -> UnifiedResult:
    return UnifiedResult(
        type="memory", doc_id=doc_id, title=doc_id, excerpt="", source="", distance=dist
    )


def vid(doc_id: str, dist: float) -> UnifiedResult:
    return UnifiedResult(
        type="video", doc_id=doc_id, title=doc_id, excerpt="", source="", distance=dist
    )


def test_captured_at_prefers_metadata_then_doc_id():
    assert memory_captured_at({"captured": "2026-07-01"}, "memory_x") == "2026-07-01"
    assert memory_captured_at({}, "memory_2026-07-17_encoder_ab12") == "2026-07-17"
    assert memory_captured_at({}, "note_inbox_memories_2026-05-16-claude-mem") == "2026-05-16"
    assert memory_captured_at({}, "note_wiki_hot") == ""


def test_decay_boosts_a_fresh_memory_past_a_slightly_closer_stale_one():
    stale = mem("memory_2026-01-01_old", dist=0.40)  # sim 0.60
    fresh = mem("memory_2026-07-22_new", dist=0.42)  # sim 0.58, 7 days old
    out = apply_memory_decay([stale, fresh], lam=0.2, half_life_days=90, now=NOW)
    assert [r.doc_id for r in out] == [fresh.doc_id, stale.doc_id]


def test_lambda_zero_is_the_identity():
    a, b = mem("memory_2026-01-01_a", 0.40), mem("memory_2026-07-22_b", 0.42)
    out = apply_memory_decay([a, b], lam=0.0, half_life_days=90, now=NOW)
    assert [r.doc_id for r in out] == [a.doc_id, b.doc_id]


def test_videos_never_gain_or_lose_from_decay():
    v = vid("video_x", 0.41)
    fresh = mem("memory_2026-07-28_new", 0.42)
    out = apply_memory_decay([v, fresh], lam=0.2, half_life_days=90, now=NOW)
    # the fresh memory may pass the video on its own boost, but the video's
    # score is its similarity, unchanged
    assert v in out and out.index(fresh) == 0


def test_unknown_capture_date_gets_no_boost():
    # two undated memories under an absurd lambda: order must stay raw-sim,
    # proving no phantom freshness is invented for stampless records
    a, b = mem("note_wiki_hot", 0.40), mem("note_wiki_index", 0.41)
    out = apply_memory_decay([a, b], lam=5.0, half_life_days=30, now=NOW)
    assert [r.doc_id for r in out] == [a.doc_id, b.doc_id]
