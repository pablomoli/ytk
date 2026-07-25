# pyright: basic
# Not strict-clean yet (#122). Delete these two lines once the module
# passes strict — the list of files carrying them only shrinks.
"""Graded relevance metrics for the retrieval eval suite (#91)."""

from __future__ import annotations

import json
import math
from pathlib import Path


def load_qrels(path: Path | str) -> dict:
    """Load and validate one frozen, single-judge qrels artifact."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    judge = data.get("judge") or {}
    if not judge.get("model") or not judge.get("prompt_version"):
        raise ValueError("qrels must stamp judge.model and judge.prompt_version")
    seen: set[tuple[str, str]] = set()
    for row in data.get("labels", []):
        key = (row.get("query_id", ""), row.get("doc_id", ""))
        if not all(key) or key in seen:
            raise ValueError(f"invalid or duplicate qrel pair: {key}")
        seen.add(key)
        grade = row.get("grade")
        if not isinstance(grade, int) or not 0 <= grade <= 3:
            raise ValueError(f"qrel grade must be an integer 0-3: {key}")
    return data


def _dcg(grades: list[int]) -> float:
    return sum((2**grade - 1) / math.log2(rank + 2) for rank, grade in enumerate(grades))


def ndcg_report(
    queries: list[dict],
    rankings: dict[str, list[str]],
    qrels: dict,
    k: int = 10,
) -> dict:
    """Compute nDCG@k and label coverage for ranked results.

    New systems can surface documents outside the frozen candidate pool.
    Those pairs are listed as unjudged rather than silently accepted as
    irrelevant; callers can judge only those new pairs and rerun.
    """
    labels: dict[str, dict[str, int]] = {}
    for row in qrels.get("labels", []):
        labels.setdefault(row["query_id"], {})[row["doc_id"]] = row["grade"]

    rows: list[dict] = []
    unjudged: list[dict[str, str]] = []
    for query in queries:
        query_id = query["gold_id"]
        judged = labels.get(query_id)
        if not judged:
            continue
        ranking = rankings.get(query_id, [])[:k]
        grades: list[int] = []
        judged_count = 0
        for doc_id in ranking:
            if doc_id in judged:
                judged_count += 1
                grades.append(judged[doc_id])
            else:
                grades.append(0)
                unjudged.append({"query_id": query_id, "doc_id": doc_id})
        ideal = sorted(judged.values(), reverse=True)[:k]
        denom = _dcg(ideal)
        score = _dcg(grades) / denom if denom else 0.0
        rows.append(
            {
                "query_id": query_id,
                "bucket": query["bucket"],
                "ndcg": score,
                "judged": judged_count,
                "retrieved": len(ranking),
            }
        )

    def mean(selected: list[dict]) -> float:
        return sum(row["ndcg"] for row in selected) / len(selected) if selected else 0.0

    per_bucket = {}
    for bucket in sorted({row["bucket"] for row in rows}):
        selected = [row for row in rows if row["bucket"] == bucket]
        per_bucket[bucket] = {f"ndcg@{k}": mean(selected), "n": len(selected)}

    retrieved = sum(row["retrieved"] for row in rows)
    judged_count = sum(row["judged"] for row in rows)
    return {
        f"ndcg@{k}": mean(rows),
        "n_queries": len(rows),
        "label_coverage": judged_count / retrieved if retrieved else 0.0,
        "unjudged_pairs": unjudged,
        "judge": qrels["judge"],
        "per_bucket": per_bucket,
    }
