"""Rerank module (#86): pure-logic tests with an injected scorer.

The real QwenReranker loads Qwen3-Reranker-0.6B lazily; nothing here touches
a model. Live behavior is measured by experiments/rerank_bench.py and,
once wired, the retrieval eval gate.
"""

import pytest

from ytk.rerank import build_prompt, rerank


def test_build_prompt_contains_instruct_query_and_doc():
    p = build_prompt("my query", "my document")
    assert "<Query>: my query" in p
    assert "<Document>: my document" in p
    assert "<Instruct>: " in p
    assert p.endswith("<|im_start|>assistant\n<think>\n\n</think>\n\n")


def test_rerank_orders_by_score_descending():
    items = ["a", "b", "c"]
    scores = {"ta": 0.1, "tb": 0.9, "tc": 0.5}
    out = rerank("q", items, ["ta", "tb", "tc"],
                 scorer=lambda q, docs: [scores[d] for d in docs])
    assert out == ["b", "c", "a"]


def test_rerank_is_deterministic_on_ties():
    # equal scores keep the first-stage (embedding) order — the bi-encoder
    # ranking is the tiebreak, not dict/hash order
    items = ["a", "b", "c", "d"]
    out = rerank("q", items, ["t"] * 4, scorer=lambda q, docs: [0.5] * 4)
    assert out == ["a", "b", "c", "d"]


def test_rerank_top_n_truncates_after_reordering():
    items = ["a", "b", "c"]
    out = rerank("q", items, ["ta", "tb", "tc"],
                 scorer=lambda q, docs: [0.1, 0.9, 0.5], top_n=2)
    assert out == ["b", "c"]


def test_rerank_empty_is_empty():
    assert rerank("q", [], [], scorer=lambda q, docs: []) == []


def test_rerank_rejects_mismatched_lengths():
    with pytest.raises(ValueError):
        rerank("q", ["a"], ["ta", "tb"], scorer=lambda q, docs: [0.5, 0.5])
