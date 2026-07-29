"""A4 (#150): retrieval-hit logging is instrumentation only — it must record
the served ranking and must never be able to break a search."""

import json

from ytk import store


def read_lines(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_log_retrieval_appends_one_line_per_hit(tmp_path, monkeypatch):
    log = tmp_path / "retrieval_log.jsonl"
    monkeypatch.setenv("YTK_RETRIEVAL_LOG", str(log))
    store.log_retrieval("videos", "television cli", [("vid-a", 0.12), ("vid-b", 0.47)])
    store.log_retrieval("all", "television cli", [("mem-1", 0.30)])

    lines = read_lines(log)
    assert [ln["doc_id"] for ln in lines] == ["vid-a", "vid-b", "mem-1"]
    assert [ln["rank"] for ln in lines] == [1, 2, 1]
    assert lines[0]["surface"] == "videos"
    assert lines[2]["surface"] == "all"
    assert lines[0]["query"] == "television cli"
    assert lines[0]["distance"] == 0.12
    assert lines[0]["ts"]  # ISO timestamp present


def test_log_retrieval_off_switch_writes_nothing(tmp_path, monkeypatch):
    log = tmp_path / "retrieval_log.jsonl"
    monkeypatch.setenv("YTK_RETRIEVAL_LOG", "off")
    store.log_retrieval("videos", "q", [("vid-a", 0.1)])
    assert not log.exists()


def test_log_retrieval_swallows_write_failures(tmp_path, monkeypatch):
    # an unwritable path must not raise into the search path
    monkeypatch.setenv("YTK_RETRIEVAL_LOG", str(tmp_path / "no" / "such" / "dir" / "x.jsonl"))
    store.log_retrieval("videos", "q", [("vid-a", 0.1)])


def test_log_retrieval_empty_hits_writes_nothing(tmp_path, monkeypatch):
    # zero-hit searches are not logged: A4 measures what was served, and
    # nothing was
    log = tmp_path / "retrieval_log.jsonl"
    monkeypatch.setenv("YTK_RETRIEVAL_LOG", str(log))
    store.log_retrieval("videos", "q", [])
    assert not log.exists()
