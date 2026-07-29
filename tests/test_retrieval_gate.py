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
    searchers = _searchers(
        {
            "q1": ["vid::a", "vid::x"],  # rank 0
            "q2": ["mem::x", "mem::y", "mem::z", "mem::w", "mem::b"],  # rank 4
            "q3": ["vid::x", "vid::y"],  # absent
        }
    )
    report = evaluate(queries, searchers, resolve_gold=lambda g: g, top_k=10)

    assert report["n_queries"] == 3
    assert report["n_evaluated"] == 3
    assert report["overall"]["hit@1"] == pytest.approx(1 / 3)
    assert report["overall"]["hit@5"] == pytest.approx(2 / 3)
    assert report["overall"]["hit@10"] == pytest.approx(2 / 3)
    assert report["per_bucket"]["videos"]["n"] == 2
    assert report["per_bucket"]["memories"]["hit@5"] == 1.0
    assert report["rankings"]["vid::a"] == ["vid::a", "vid::x"]


def test_evaluate_missing_gold_excluded_from_metrics():
    queries = [
        {"query": "q1", "gold_id": "vid::a", "bucket": "videos"},
        {"query": "q2", "gold_id": "mem::gone", "bucket": "memories"},
    ]
    searchers = _searchers({"q1": ["vid::a"]})
    report = evaluate(
        queries,
        searchers,
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
    searchers = _searchers(
        {
            "q1": ["vid::a"],  # rank 0: not a miss
            "q2": ["vid::x"] * 7 + ["vid::b"],  # rank 7: out of top-5
            "q3": ["vid::x"],  # absent
        }
    )
    report = evaluate(queries, searchers, resolve_gold=lambda g: g)

    misses = {m["gold_id"]: m["rank"] for m in report["misses"]}
    assert misses == {"vid::b": 7, "vid::c": None}


def test_evaluate_ranks_within_the_frozen_corpus():
    # vid::new entered the store after the baseline was stamped. It outranks
    # the gold live, but must not cost the gold a rank position: growth is
    # not a regression.
    queries = [{"query": "q1", "gold_id": "vid::a", "bucket": "videos"}]
    searchers = _searchers({"q1": ["vid::new", "vid::a"]})
    report = evaluate(
        queries,
        searchers,
        resolve_gold=lambda g: g,
        frozen_ids={"vid::a", "vid::x"},
    )

    assert report["overall"]["hit@1"] == 1.0
    assert report["rankings"]["vid::a"] == ["vid::a"]


def test_evaluate_flags_queries_whose_frozen_window_ran_dry():
    # The searcher was asked for 6 and returned 6 — its ceiling — yet only 2
    # survive the freeze, so the top-5 window is unfillable and frozen docs
    # deeper than the fetch went unseen. A gold at frozen-rank 3 would score
    # as a miss it did not earn, so the degradation must be visible.
    queries = [{"query": "q1", "gold_id": "vid::a", "bucket": "videos"}]
    searchers = _searchers({"q1": ["vid::a", "n1", "n2", "vid::x", "n3", "n4"]})
    report = evaluate(
        queries,
        searchers,
        resolve_gold=lambda g: g,
        top_k=5,
        fetch_k=6,
        frozen_ids={"vid::a", "vid::x"},
    )

    assert report["freeze_starved"] == ["q1"]


def test_evaluate_does_not_flag_starvation_when_the_corpus_is_simply_small():
    # Same shortfall, but the searcher returned fewer than it was asked for:
    # the corpus is exhausted, not the window. Nothing deeper exists to find,
    # so this is not a degraded measurement.
    queries = [{"query": "q1", "gold_id": "vid::a", "bucket": "videos"}]
    searchers = _searchers({"q1": ["vid::a", "n1", "vid::x"]})
    report = evaluate(
        queries,
        searchers,
        resolve_gold=lambda g: g,
        top_k=5,
        fetch_k=50,
        frozen_ids={"vid::a", "vid::x"},
    )

    assert report["freeze_starved"] == []


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
        "top_k": 10,
        "n_queries": 3,
        "n_evaluated": 3,
        "missing_gold": [],
        "overall": {"hit@1": 0.5, "hit@5": 0.9, "hit@10": 0.95},
        "per_bucket": {"videos": {"hit@1": 0.5, "hit@5": 0.9, "hit@10": 0.95, "n": 3}},
        "misses": [],
        "provenance": {"corpus_fingerprint": "abc"},
    }
    baseline = make_baseline(report, epoch="v2", authored="2026-07-17")
    assert baseline["epoch"] == "v2"
    assert baseline["authored"] == "2026-07-17"
    assert baseline["overall"] == report["overall"]
    assert baseline["per_bucket"] == report["per_bucket"]
    assert baseline["tolerance"] > 0
    assert baseline["provenance"] == report["provenance"]


def test_make_baseline_documents_the_freeze():
    # #111 acceptance: the baseline must say what is frozen and how to
    # re-stamp, so the next person to hit a red gate does not reach for
    # --no-verify out of not knowing the alternative.
    baseline = make_baseline(
        {
            "top_k": 10,
            "n_queries": 3,
            "overall": {"hit@1": 0.5, "hit@5": 0.9, "hit@10": 0.95},
            "per_bucket": {},
        },
        epoch="v2",
        authored="2026-07-25",
    )

    note = baseline["frozen_corpus"]
    assert "frozen_corpus.json" in note
    assert "ytk eval --update-baseline" in note


def _report(hit5=0.9, hit10=0.95, n=100, missing=()):
    return {
        "top_k": 10,
        "n_queries": n + len(missing),
        "n_evaluated": n,
        "missing_gold": list(missing),
        "overall": {"hit@1": 0.5, "hit@5": hit5, "hit@10": hit10},
        "per_bucket": {},
        "misses": [],
    }


def _baseline(hit5=0.9, hit10=0.95, tolerance=0.02):
    return {
        "epoch": "v2",
        "authored": "2026-07-17",
        "top_k": 10,
        "n_queries": 100,
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


def test_compare_fails_closed_on_provenance_mismatch():
    report = _report()
    baseline = _baseline()
    report["provenance"] = {"query_file_sha256": "new"}
    baseline["provenance"] = {"query_file_sha256": "old"}
    failures = compare_to_baseline(report, baseline)
    assert any("query_file_sha256" in failure for failure in failures)


def test_compare_requires_provenance_on_both_sides():
    report = _report()
    report["provenance"] = {"query_file_sha256": "new"}
    failures = compare_to_baseline(report, _baseline())
    assert any("provenance" in failure for failure in failures)


def test_overfetch_scales_with_corpus_growth():
    from ytk.retrieval_gate import overfetch_factor

    # Once growth clears the floor, a 5x corpus needs a wider window than a
    # 2x one to still yield a full frozen top-k — the factor tracks growth
    # instead of a constant that silently rots as the vault fills up.
    assert overfetch_factor(frozen_size=1000, live_size=5000) > overfetch_factor(
        frozen_size=1000, live_size=2000
    )


def test_overfetch_has_a_floor_on_an_unchanged_corpus():
    from ytk.retrieval_gate import overfetch_factor

    # Even with zero growth the window must exceed top_k: deletions and
    # id churn still thin the frozen survivors.
    assert overfetch_factor(frozen_size=1000, live_size=1000) >= 3


def test_overfetch_is_capped_against_a_runaway_corpus():
    from ytk.retrieval_gate import overfetch_factor

    # An unbounded factor would turn one gate run into thousands of
    # full-collection scans; past the cap the honest answer is "re-stamp",
    # which freeze_starved reports.
    assert overfetch_factor(frozen_size=10, live_size=1_000_000) <= 20


def test_frozen_corpus_round_trips_and_hashes_order_independently(tmp_path):
    from ytk.retrieval_gate import frozen_corpus_sha256, load_frozen_ids, write_frozen_corpus

    path = tmp_path / "frozen_corpus.json"
    write_frozen_corpus({"vid::b", "mem::a", "seg::c"}, path)

    assert load_frozen_ids(path) == {"vid::b", "mem::a", "seg::c"}
    assert frozen_corpus_sha256({"seg::c", "vid::b", "mem::a"}) == frozen_corpus_sha256(
        {"mem::a", "vid::b", "seg::c"}
    )


def test_frozen_corpus_hash_changes_when_the_set_changes():
    from ytk.retrieval_gate import frozen_corpus_sha256

    assert frozen_corpus_sha256({"vid::a"}) != frozen_corpus_sha256({"vid::a", "vid::b"})


def test_load_frozen_ids_returns_none_when_never_stamped(tmp_path):
    from ytk.retrieval_gate import load_frozen_ids

    # No freeze on disk must not silently score against the live corpus —
    # it yields None so provenance mismatches and the gate says re-stamp.
    assert load_frozen_ids(tmp_path / "absent.json") is None


def _provenance(**overrides):
    prov = {
        "query_file_sha256": "q",
        "query_count": 100,
        "corpus_fingerprint": "fp",
        "frozen_corpus_sha256": "frozen",
        "collection_epoch": "v2",
        "embedding_model": "Qwen/Qwen3-Embedding-0.6B",
        "embedding_revision": "rev",
        "query_instruction": "Instruct: ",
        "max_seq_length": 3072,
        "top_k": 10,
    }
    prov.update(overrides)
    return prov


def test_compare_ignores_corpus_growth():
    # #111: the corpus grows every day by design. With the scored surface
    # frozen, a moved fingerprint says nothing about retrieval quality and
    # must not fail the gate — a gate that is always red carries no signal.
    report = _report()
    baseline = _baseline()
    report["provenance"] = _provenance(corpus_fingerprint="grown")
    baseline["provenance"] = _provenance(corpus_fingerprint="stamped")

    assert compare_to_baseline(report, baseline) == []


def test_compare_fails_when_the_frozen_corpus_itself_changes():
    # The freeze is what makes the numbers comparable, so redefining it
    # silently would launder a regression. This is the check that replaces
    # the fingerprint's role.
    report = _report()
    baseline = _baseline()
    report["provenance"] = _provenance(frozen_corpus_sha256="new")
    baseline["provenance"] = _provenance(frozen_corpus_sha256="old")

    failures = compare_to_baseline(report, baseline)
    assert any("frozen_corpus_sha256" in f for f in failures)


def test_compare_still_fails_on_encoder_change():
    # Freezing the corpus must not loosen the checks that genuinely
    # invalidate a comparison.
    report = _report()
    baseline = _baseline()
    report["provenance"] = _provenance(embedding_revision="new")
    baseline["provenance"] = _provenance(embedding_revision="old")

    failures = compare_to_baseline(report, baseline)
    assert any("embedding_revision" in f for f in failures)


def test_compare_fails_when_growth_starves_the_frozen_window():
    # Past this fraction the freeze is no longer being honoured: too many
    # queries had their window eaten by post-baseline documents, so the
    # scores understate retrieval rather than measuring it.
    report = _report(n=100)
    report["freeze_starved"] = [f"q{i}" for i in range(21)]

    failures = compare_to_baseline(report, _baseline())
    assert any("starved" in f.lower() or "over-fetch" in f.lower() for f in failures)


def test_compare_tolerates_a_few_starved_queries():
    report = _report(n=100)
    report["freeze_starved"] = ["q1", "q2"]

    assert compare_to_baseline(report, _baseline()) == []


def _cli_report(hit5=0.9):
    return _report(hit5=hit5)


@pytest.fixture
def eval_cli(monkeypatch, tmp_path):
    """CliRunner + mocked live gate: returns (runner, invoke, baseline_path)."""
    from click.testing import CliRunner

    from ytk import cli as cli_mod
    from ytk import retrieval_gate

    baseline_path = tmp_path / "baseline.json"
    frozen_path = tmp_path / "frozen_corpus.json"
    monkeypatch.setattr(retrieval_gate, "BASELINE_PATH", baseline_path)
    # Both store-touching doors must be shut, not just run_live_gate: the
    # re-stamp path snapshots the live corpus too, and the fast suite must
    # never read production chroma or write the real freeze file.
    monkeypatch.setattr(retrieval_gate, "FROZEN_CORPUS_PATH", frozen_path)
    monkeypatch.setattr(retrieval_gate, "snapshot_frozen_ids", lambda: {"vid::a", "mem::b"})
    monkeypatch.setattr(retrieval_gate, "run_live_gate", lambda top_k=10: _cli_report())
    runner = CliRunner()

    def invoke(*args):
        return runner.invoke(cli_mod.cli, ["eval", *args])

    return invoke, baseline_path, frozen_path


def test_eval_cli_passes_against_baseline(eval_cli):
    invoke, baseline_path, _ = eval_cli
    baseline_path.write_text(json.dumps(_baseline()))
    result = invoke()
    assert result.exit_code == 0, result.output
    assert "hit@5" in result.output


def test_eval_cli_fails_on_regression(eval_cli, monkeypatch):
    from ytk import retrieval_gate

    invoke, baseline_path, _ = eval_cli
    baseline_path.write_text(json.dumps(_baseline()))
    monkeypatch.setattr(retrieval_gate, "run_live_gate", lambda top_k=10: _cli_report(hit5=0.80))
    result = invoke()
    assert result.exit_code == 1
    assert "regressed" in result.output


def test_eval_cli_requires_baseline(eval_cli):
    invoke, _, _ = eval_cli
    result = invoke()
    assert result.exit_code == 2
    assert "--update-baseline" in result.output


def test_eval_cli_json_output_is_parseable(eval_cli, monkeypatch, tmp_path):
    # scripts pipe --json; spinner and verdict chrome must stay off stdout
    from click.testing import CliRunner

    from ytk import cli as cli_mod

    _, baseline_path, _ = eval_cli
    baseline_path.write_text(json.dumps(_baseline()))
    runner = CliRunner()
    result = runner.invoke(cli_mod.cli, ["eval", "--json"])
    assert result.exit_code == 0, result.output
    report = json.loads(result.stdout)
    assert report["overall"]["hit@5"] == 0.9


def test_eval_cli_update_baseline_writes_stamped_file(eval_cli):
    invoke, baseline_path, _ = eval_cli
    result = invoke("--update-baseline")
    assert result.exit_code == 0, result.output
    baseline = json.loads(baseline_path.read_text())
    assert baseline["epoch"]
    assert baseline["authored"]
    assert baseline["overall"]["hit@5"] == 0.9


def test_eval_cli_update_baseline_stamps_the_freeze_at_the_configured_path(eval_cli):
    # The path is resolved at call time, not captured as a default argument:
    # otherwise redirecting FROZEN_CORPUS_PATH is silently ignored and the
    # real eval/retrieval/ freeze is overwritten from under you.
    invoke, _, frozen_path = eval_cli
    result = invoke("--update-baseline")

    assert result.exit_code == 0, result.output
    assert frozen_path.exists()
    assert set(json.loads(frozen_path.read_text())["ids"]) == {"vid::a", "mem::b"}


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
        cwd=YTK_ROOT.parent,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_no_query_texts_outside_graph():
    """User queries must go through embed_query()/query_embeddings.

    chroma's query_texts kwarg embeds on the document path — for the
    instruction-aware v2 encoder that silently drops the query prefix
    (measured: 3.8/10 top-10 overlap vs the correct path). Legitimate callers
    are doc-to-doc similarity queries with document text: graph.py, and
    store.similar_memories (R1/#150 — a candidate memory is a document, and
    A1's duplicate thresholds were calibrated on plain-doc embeddings).
    """
    # per-file "all", or per-function within a file — store.py must stay
    # guarded overall because the user-query search functions live there
    allowed = {"graph.py": None, "store.py": {"similar_memories"}}
    offenders = []
    for py in YTK_ROOT.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        funcs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)]

        def enclosing(lineno: int) -> str | None:
            spans = [f for f in funcs if f.lineno <= lineno <= (f.end_lineno or f.lineno)]
            return (
                min(spans, key=lambda f: (f.end_lineno or f.lineno) - f.lineno).name
                if spans
                else None
            )

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for kw in node.keywords:
                if kw.arg != "query_texts":
                    continue
                names = allowed.get(py.name, set())
                if names is None or (names and enclosing(node.lineno) in names):
                    continue
                offenders.append(f"{py.relative_to(YTK_ROOT.parent)}:{node.lineno}")
    assert not offenders, f"query_texts used on a user-query path: {offenders}"
