"""Graded qrels validation and nDCG@10 reporting (#91)."""

import json

import pytest

from ytk.relevance import load_qrels, ndcg_report


def _qrels(labels):
    return {
        "judge": {"model": "claude-test", "prompt_version": "v1"},
        "labels": labels,
    }


def test_load_qrels_requires_one_stamped_valid_judge(tmp_path):
    path = tmp_path / "qrels.json"
    path.write_text(json.dumps({"labels": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="judge"):
        load_qrels(path)

    path.write_text(
        json.dumps(
            _qrels(
                [
                    {"query_id": "q", "doc_id": "d", "grade": 4},
                ]
            )
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="0-3"):
        load_qrels(path)


def test_ndcg_report_rewards_ideal_order_and_reports_new_pairs():
    queries = [
        {"gold_id": "q1", "bucket": "videos"},
        {"gold_id": "q2", "bucket": "memories"},
    ]
    qrels = _qrels(
        [
            {"query_id": "q1", "doc_id": "a", "grade": 3},
            {"query_id": "q1", "doc_id": "b", "grade": 1},
            {"query_id": "q2", "doc_id": "c", "grade": 2},
        ]
    )
    report = ndcg_report(
        queries,
        {"q1": ["a", "b"], "q2": ["new", "c"]},
        qrels,
        k=10,
    )

    assert report["per_bucket"]["videos"]["ndcg@10"] == pytest.approx(1.0)
    assert 0 < report["per_bucket"]["memories"]["ndcg@10"] < 1
    assert report["label_coverage"] == pytest.approx(3 / 4)
    assert report["unjudged_pairs"] == [{"query_id": "q2", "doc_id": "new"}]
