"""Retrieval eval gate (#85): pure-logic unit tests + query-path guard.

The live gate (`ytk eval`, pytest -m eval) talks to the real store; these
tests exercise the evaluation/baseline logic with injected searchers so they
run in the fast suite with no model or chroma access.
"""

import ast
import json
from pathlib import Path

import pytest

from ytk.retrieval_gate import (
    compare_to_baseline,
    evaluate,
    load_queries,
    make_baseline,
)

YTK_ROOT = Path(__file__).resolve().parents[1] / "ytk"


def _searchers(results_by_query: dict[str, list[str]]):
    """All buckets share one fake searcher returning a fixed ranked key list."""
    def search(query: str) -> list[str]:
        return results_by_query.get(query, [])
    return {"videos": search, "memories": search, "segments": search}


def test_evaluate_ranks_and_hits():
    queries = [
        {"query": "q1", "gold_id": "vid::a", "bucket": "videos"},
        {"query": "q2", "gold_id": "mem::b", "bucket": "memories"},
        {"query": "q3", "gold_id": "vid::c", "bucket": "videos"},
    ]
    searchers = _searchers({
        "q1": ["vid::a", "vid::x"],                     # rank 0
        "q2": ["mem::x", "mem::y", "mem::z", "mem::w", "mem::b"],  # rank 4
        "q3": ["vid::x", "vid::y"],                     # absent
    })
    report = evaluate(queries, searchers, resolve_gold=lambda g: g, top_k=10)

    assert report["n_queries"] == 3
    assert report["n_evaluated"] == 3
    assert report["overall"]["hit@1"] == pytest.approx(1 / 3)
    assert report["overall"]["hit@5"] == pytest.approx(2 / 3)
    assert report["overall"]["hit@10"] == pytest.approx(2 / 3)
    assert report["per_bucket"]["videos"]["n"] == 2
    assert report["per_bucket"]["memories"]["hit@5"] == 1.0


def test_evaluate_missing_gold_excluded_from_metrics():
    queries = [
        {"query": "q1", "gold_id": "vid::a", "bucket": "videos"},
        {"query": "q2", "gold_id": "mem::gone", "bucket": "memories"},
    ]
    searchers = _searchers({"q1": ["vid::a"]})
    report = evaluate(
        queries, searchers,
        resolve_gold=lambda g: None if g == "mem::gone" else g,
    )

    assert report["n_evaluated"] == 1
    assert report["missing_gold"] == ["mem::gone"]
    assert report["overall"]["hit@5"] == 1.0
    assert "memories" not in report["per_bucket"]


def test_evaluate_misses_include_slipped_and_absent():
    queries = [
        {"query": "q1", "gold_id": "vid::a", "bucket": "videos"},
        {"query": "q2", "gold_id": "vid::b", "bucket": "videos"},
        {"query": "q3", "gold_id": "vid::c", "bucket": "videos"},
    ]
    searchers = _searchers({
        "q1": ["vid::a"],                                # rank 0: not a miss
        "q2": ["vid::x"] * 7 + ["vid::b"],               # rank 7: out of top-5
        "q3": ["vid::x"],                                # absent
    })
    report = evaluate(queries, searchers, resolve_gold=lambda g: g)

    misses = {m["gold_id"]: m["rank"] for m in report["misses"]}
    assert misses == {"vid::b": 7, "vid::c": None}


def test_load_queries_skips_blank_lines(tmp_path):
    p = tmp_path / "queries.jsonl"
    p.write_text(
        json.dumps({"query": "a", "gold_id": "vid::a", "bucket": "videos"})
        + "\n\n"
        + json.dumps({"query": "b", "gold_id": "mem::b", "bucket": "memories"})
        + "\n",
        encoding="utf-8",
    )
    queries = load_queries(p)
    assert [q["query"] for q in queries] == ["a", "b"]


def test_make_baseline_stamps_provenance():
    report = {
        "top_k": 10, "n_queries": 3, "n_evaluated": 3, "missing_gold": [],
        "overall": {"hit@1": 0.5, "hit@5": 0.9, "hit@10": 0.95},
        "per_bucket": {"videos": {"hit@1": 0.5, "hit@5": 0.9, "hit@10": 0.95, "n": 3}},
        "misses": [],
    }
    baseline = make_baseline(report, epoch="v2", authored="2026-07-17")
    assert baseline["epoch"] == "v2"
    assert baseline["authored"] == "2026-07-17"
    assert baseline["overall"] == report["overall"]
    assert baseline["per_bucket"] == report["per_bucket"]
    assert baseline["tolerance"] > 0


def _report(hit5=0.9, hit10=0.95, n=100, missing=()):
    return {
        "top_k": 10, "n_queries": n + len(missing), "n_evaluated": n,
        "missing_gold": list(missing),
        "overall": {"hit@1": 0.5, "hit@5": hit5, "hit@10": hit10},
        "per_bucket": {}, "misses": [],
    }


def _baseline(hit5=0.9, hit10=0.95, tolerance=0.02):
    return {
        "epoch": "v2", "authored": "2026-07-17", "top_k": 10, "n_queries": 100,
        "tolerance": tolerance,
        "overall": {"hit@1": 0.5, "hit@5": hit5, "hit@10": hit10},
        "per_bucket": {},
    }


def test_compare_passes_within_tolerance():
    assert compare_to_baseline(_report(hit5=0.89), _baseline()) == []


def test_compare_passes_on_improvement():
    assert compare_to_baseline(_report(hit5=0.95, hit10=1.0), _baseline()) == []


def test_compare_fails_on_hit5_regression():
    failures = compare_to_baseline(_report(hit5=0.85), _baseline())
    assert any("hit@5" in f for f in failures)


def test_compare_fails_on_hit10_regression():
    failures = compare_to_baseline(_report(hit10=0.90), _baseline())
    assert any("hit@10" in f for f in failures)


def test_compare_fails_when_query_set_rots():
    # >10% of gold docs gone from the store: the fixture needs repair, and
    # shrinking denominators would otherwise hide real regressions.
    failures = compare_to_baseline(
        _report(missing=[f"mem::{i}" for i in range(15)], n=85), _baseline()
    )
    assert any("missing" in f.lower() for f in failures)


def _cli_report(hit5=0.9):
    return _report(hit5=hit5)


@pytest.fixture
def eval_cli(monkeypatch, tmp_path):
    """CliRunner + mocked live gate: returns (runner, invoke, baseline_path)."""
    from click.testing import CliRunner

    from ytk import cli as cli_mod
    from ytk import retrieval_gate

    baseline_path = tmp_path / "baseline.json"
    monkeypatch.setattr(retrieval_gate, "BASELINE_PATH", baseline_path)
    monkeypatch.setattr(retrieval_gate, "run_live_gate", lambda top_k=10: _cli_report())
    runner = CliRunner()

    def invoke(*args):
        return runner.invoke(cli_mod.cli, ["eval", *args])

    return invoke, baseline_path


def test_eval_cli_passes_against_baseline(eval_cli):
    invoke, baseline_path = eval_cli
    baseline_path.write_text(json.dumps(_baseline()))
    result = invoke()
    assert result.exit_code == 0, result.output
    assert "hit@5" in result.output


def test_eval_cli_fails_on_regression(eval_cli, monkeypatch):
    from ytk import retrieval_gate

    invoke, baseline_path = eval_cli
    baseline_path.write_text(json.dumps(_baseline()))
    monkeypatch.setattr(
        retrieval_gate, "run_live_gate", lambda top_k=10: _cli_report(hit5=0.80)
    )
    result = invoke()
    assert result.exit_code == 1
    assert "regressed" in result.output


def test_eval_cli_requires_baseline(eval_cli):
    invoke, _ = eval_cli
    result = invoke()
    assert result.exit_code == 2
    assert "--update-baseline" in result.output


def test_eval_cli_json_output_is_parseable(eval_cli, monkeypatch, tmp_path):
    # scripts pipe --json; spinner and verdict chrome must stay off stdout
    from click.testing import CliRunner

    from ytk import cli as cli_mod

    _, baseline_path = eval_cli
    baseline_path.write_text(json.dumps(_baseline()))
    runner = CliRunner()
    result = runner.invoke(cli_mod.cli, ["eval", "--json"])
    assert result.exit_code == 0, result.output
    report = json.loads(result.stdout)
    assert report["overall"]["hit@5"] == 0.9


def test_eval_cli_update_baseline_writes_stamped_file(eval_cli):
    invoke, baseline_path = eval_cli
    result = invoke("--update-baseline")
    assert result.exit_code == 0, result.output
    baseline = json.loads(baseline_path.read_text())
    assert baseline["epoch"]
    assert baseline["authored"]
    assert baseline["overall"]["hit@5"] == 0.9


@pytest.mark.eval
def test_live_gate_passes_against_baseline():
    """The one-command check, end to end: real store, real encoder.

    Runs in a subprocess so the fast suite's epoch pin (conftest) cannot
    leak in — the CLI must see production config exactly as a user would.
    Deselected by default (addopts -m 'not eval'); run: pytest -m eval
    """
    import subprocess

    result = subprocess.run(
        ["uv", "run", "ytk", "eval"],
        cwd=YTK_ROOT.parent, capture_output=True, text=True, timeout=600,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_no_query_texts_outside_graph():
    """User queries must go through embed_query()/query_embeddings.

    chroma's query_texts kwarg embeds on the document path — for the
    instruction-aware v2 encoder that silently drops the query prefix
    (measured: 3.8/10 top-10 overlap vs the correct path). graph.py is the
    one legitimate caller: doc-to-doc similarity queries with document text.
    """
    allowed = {"graph.py"}
    offenders = []
    for py in YTK_ROOT.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for kw in node.keywords:
                if kw.arg == "query_texts" and py.name not in allowed:
                    offenders.append(f"{py.relative_to(YTK_ROOT.parent)}:{node.lineno}")
    assert not offenders, f"query_texts used on a user-query path: {offenders}"
