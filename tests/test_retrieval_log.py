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


def test_log_retrieval_empty_hits_writes_miss_row(tmp_path, monkeypatch):
    # #96 inverted A4's original silence: a zero-hit search IS the
    # recall-failure signal, and before this row misses were invisible
    log = tmp_path / "retrieval_log.jsonl"
    monkeypatch.setenv("YTK_RETRIEVAL_LOG", str(log))
    store.log_retrieval("videos", "q", [])
    (row,) = read_lines(log)
    assert row["doc_id"] is None and row["rank"] == 0 and row["results"] == 0
    assert row["surface"] == "videos" and row["query"] == "q"


def test_log_retrieval_actor_defaults_to_system(tmp_path, monkeypatch):
    # untagged callers are pipelines; an omission must never inflate
    # user/agent use evidence (#96 outcome model)
    log = tmp_path / "retrieval_log.jsonl"
    monkeypatch.setenv("YTK_RETRIEVAL_LOG", str(log))
    store.log_retrieval("all", "q", [("d", 0.1)])
    (row,) = read_lines(log)
    assert row["actor"] == "system" and "session" not in row


def test_log_retrieval_records_actor_and_session(tmp_path, monkeypatch):
    log = tmp_path / "retrieval_log.jsonl"
    monkeypatch.setenv("YTK_RETRIEVAL_LOG", str(log))
    store.log_retrieval("all", "q", [("d", 0.1)], actor="agent", session="abc123")
    (row,) = read_lines(log)
    assert row["actor"] == "agent" and row["session"] == "abc123"


def test_vault_read_logs_event(tmp_path, monkeypatch):
    from ytk import mcp_server

    log = tmp_path / "vault_read.jsonl"
    monkeypatch.setenv("YTK_READ_LOG", str(log))
    mcp_server._log_read("sources/youtube/example.md")
    (row,) = read_lines(log)
    assert row["path"] == "sources/youtube/example.md"
    assert row["actor"] == "agent"
    assert row["session"] == mcp_server._SESSION_ID
    assert row["ts"]


def test_vault_read_log_off_switch(tmp_path, monkeypatch):
    from ytk import mcp_server

    monkeypatch.setenv("YTK_READ_LOG", "off")
    mcp_server._log_read("wiki/hot.md")
    assert not (tmp_path / "vault_read.jsonl").exists()
