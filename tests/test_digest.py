"""Tests for the recap core (ytk/digest.py) — no store, no API call.

Everything here runs with ground=False so the embedder is never touched; the
grounding path (store.search_all) is exercised separately and is best-effort by
design.
"""

from __future__ import annotations

import os

import pytest

from ytk import digest

NOTE = """---
url: {url}
title: {title}
date: 2026-07-10
tags:
  - alpha
  - beta
type: instagram
---

![[cover.jpg]]

## Summary
{summary}
"""


@pytest.fixture
def brain(tmp_path, monkeypatch):
    b = tmp_path / "brain"
    (b / "sources" / "instagram").mkdir(parents=True)
    (b / "inbox").mkdir(parents=True)
    (b / "me").mkdir(parents=True)
    monkeypatch.setattr("ytk.vault._get_brain_path", lambda: b)
    # Keep themes hermetic: the real interest snapshot lives outside tmp.
    monkeypatch.setattr("ytk.interest.load_latest", lambda: None)
    return b


def _write(brain, name, url, title, summary, mtime):
    p = brain / "sources" / "instagram" / name
    p.write_text(NOTE.format(url=url, title=title, summary=summary), encoding="utf-8")
    os.utime(p, (mtime, mtime))
    return p


def test_gather_recent_newest_first_and_parsed(brain):
    _write(brain, "a.md", "http://a", "Note A", "Summary A body.", mtime=1000)
    _write(brain, "b.md", "http://b", "Note B", "Summary B body.", mtime=2000)

    ctx = digest.gather_recent(n=5, ground=False)

    assert [i.title for i in ctx.ingests] == ["Note B", "Note A"]
    first = ctx.ingests[0]
    assert first.tags == ["alpha", "beta"]
    assert first.url == "http://b"
    assert first.source_type == "instagram"
    assert "Summary B body." in first.summary


def test_gather_recent_respects_n(brain):
    for i in range(4):
        _write(brain, f"n{i}.md", f"http://{i}", f"Note {i}", "s", mtime=1000 + i)

    ctx = digest.gather_recent(n=2, ground=False)

    assert [i.title for i in ctx.ingests] == ["Note 3", "Note 2"]


def test_render_context_lists_ingests_and_signals(brain):
    _write(brain, "a.md", "http://a", "Note A", "Alpha summary.", mtime=1000)
    (brain / "inbox" / "ideas.md").write_text("- build a thing", encoding="utf-8")

    md = digest.render_context(digest.gather_recent(n=5, ground=False))

    assert "Recently ingested (1)" in md
    assert "Note A" in md
    assert "Alpha summary." in md
    assert "build a thing" in md


def test_synthesize_empty_context_makes_no_call(brain):
    # No source notes -> no ingests -> canned message, never an API call.
    ctx = digest.gather_recent(n=5, ground=False)
    assert ctx.ingests == []
    assert "Nothing" in digest.synthesize(ctx)
