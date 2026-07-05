"""Directive interpretation guardrails (issue #14): the LLM is a picker, never
an author — outputs are clamped to the candidate lists, user text is only ever
appended to, and a failing pass never fails an ingest."""

from __future__ import annotations

import pytest

from ytk import directives, vault


@pytest.fixture
def brain(tmp_path, monkeypatch):
    monkeypatch.setattr(vault, "_get_vault_path", lambda: tmp_path)
    return tmp_path / "second-brain"


def test_gate_fires_on_cue_verbs():
    assert directives.looks_like_directive("link this to epicmap")
    assert directives.looks_like_directive("add as a ref to the audiobooks video")
    assert directives.looks_like_directive("pin this to the css note")


def test_gate_ignores_musings():
    assert not directives.looks_like_directive("great flexbox trick, very cosmos-y")
    assert not directives.looks_like_directive("this belongs with the epicmap stuff")
    assert not directives.looks_like_directive("")
    assert not directives.looks_like_directive("   ")


def test_interpret_clamps_to_candidates(monkeypatch, brain):
    """Hallucinated stems/slugs are dropped; links capped at MAX_LINKS."""
    (brain / "inbox" / "memories" / "proj-a").mkdir(parents=True)
    monkeypatch.setattr(directives, "_candidate_stems", lambda t, n=8: ["real-note"])
    monkeypatch.setattr("ytk.sdk.run_structured", lambda *a, **k: {
        "is_directive": True,
        "wikilinks": ["real-note", "made-up-note", "another-fake"],
        "project": "made-up-project",
    })

    d = directives.interpret("link this to proj-a")
    assert d.wikilinks == ["real-note"]
    assert d.project is None


def test_interpret_all_hallucinated_means_no_directive(monkeypatch, brain):
    (brain / "inbox" / "memories" / "proj-a").mkdir(parents=True)
    monkeypatch.setattr(directives, "_candidate_stems", lambda t, n=8: ["real-note"])
    monkeypatch.setattr("ytk.sdk.run_structured", lambda *a, **k: {
        "is_directive": True, "wikilinks": ["fake"], "project": "also-fake",
    })

    assert directives.interpret("link this to nothing").is_directive is False


def test_apply_appends_without_rewriting(brain):
    note = brain / "sources" / "web" / "some-note.md"
    note.parent.mkdir(parents=True)
    original = "---\nurl: u\n---\n\n## My take\n\nlink it up\n"
    note.write_text(original)
    vault.write_atom("proj-a", "state", "- old line")

    d = directives.Directive(is_directive=True, wikilinks=["target"], project="proj-a")
    applied = directives.apply(note, d, "link it up")

    text = note.read_text()
    assert original.rstrip("\n") in text  # verbatim thought untouched
    assert "Related: [[target]]" in text
    assert "old line" in (state := vault.read_atom("proj-a", "state"))
    assert "[[some-note]]" in state
    assert len(applied) == 2


def test_apply_noop_when_not_directive(brain):
    note = brain / "note.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text("body\n")
    assert directives.apply(note, directives.Directive(), "whatever") == []
    assert note.read_text() == "body\n"


def test_process_never_raises(monkeypatch, brain):
    monkeypatch.setattr(directives, "interpret", lambda t: 1 / 0)
    assert directives.process(brain / "missing.md", "link this to x") == []
