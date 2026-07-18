"""Candidate-pool privacy and resumable judging (#91)."""

import json

from scripts import build_qrels


def _pool():
    return {
        "variants": ["base", "rerank"],
        "provenance": {"fingerprint": "abc"},
        "pairs": [
            {
                "query_id": "q1", "query": "query one", "bucket": "videos",
                "doc_id": "vid::a", "document": "private document a",
            },
            {
                "query_id": "q2", "query": "query two", "bucket": "memories",
                "doc_id": "mem::b", "document": "private document b",
            },
        ],
    }


def test_public_pool_never_writes_document_text():
    public = build_qrels.public_pool(_pool())
    assert all("document" not in pair for pair in public["pairs"])
    assert "private document" not in json.dumps(public)


def test_judge_pool_checkpoints_public_labels_and_private_reasons(
    tmp_path, monkeypatch,
):
    calls = []

    def fake_judge(batch, model):
        calls.append((len(batch), model))
        return [
            {"grade": 3, "reason": f"reason {i}", "confidence": "high"}
            for i, _ in enumerate(batch)
        ]

    monkeypatch.setattr(build_qrels, "_judge_batch", fake_judge)
    qrels_path = tmp_path / "qrels.json"
    review_path = tmp_path / "review.json"
    qrels = build_qrels.judge_pool(
        _pool(), qrels_path, "claude-test", review_path
    )

    assert calls == [(2, "claude-test")]
    assert all("reason" not in row for row in qrels["labels"])
    assert [row["reason"] for row in json.loads(review_path.read_text())] == [
        "reason 0", "reason 1",
    ]

    # A rerun with the same judge resumes without re-judging completed pairs.
    build_qrels.judge_pool(_pool(), qrels_path, "claude-test", review_path)
    assert calls == [(2, "claude-test")]
