"""Linking layer 1: creator and concept hubs, linked from frontmatter, written
only for names the owner approved, removed when a name is struck."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from ytk import hubs, ledger


@pytest.fixture
def conn():
    c = ledger.connect()
    yield c
    c.close()


@pytest.fixture
def brain(tmp_path, monkeypatch):
    b = tmp_path / "Vault" / "second-brain"
    (b / "sources" / "youtube").mkdir(parents=True)
    (b / "sources" / "web").mkdir(parents=True)
    monkeypatch.setattr("ytk.vault._get_brain_path", lambda: b)
    return b


def note(brain: Path, rel: str, *, title: str, creator_key="uploader", creator="", concepts=()):
    lines = ["---", "url: https://example.com/" + Path(rel).stem, f"title: {title}"]
    if creator:
        lines.append(f"{creator_key}: {creator}")
    lines += ["tags:", "  - manim", "---", "", "## Thesis", "A thesis.", ""]
    if concepts:
        lines.append("## Key Concepts")
        lines += [f"- {c}: what it did here" for c in concepts]
        lines.append("")
    lines += ["## Insights", "- one", ""]
    path = brain / "sources" / rel
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def approve(conn, *pairs):
    hubs.record_verdicts(conn, [(k, key, "approve") for k, key in pairs], surface="test")


def strike(conn, *pairs):
    hubs.record_verdicts(conn, [(k, key, "strike") for k, key in pairs], surface="test")


@pytest.fixture
def corpus(brain):
    return {
        "a": note(
            brain, "youtube/a.md", title="Alpha", creator="3Blue1Brown", concepts=["Manim", "Fable"]
        ),
        "b": note(
            brain,
            "youtube/b.md",
            title="Beta",
            creator="3Blue1Brown",
            concepts=["Manim", "Linear maps"],
        ),
        "c": note(
            brain,
            "web/c.md",
            title="Gamma",
            creator_key="author",
            creator="Ada",
            concepts=["MANIM!", "Fable"],
        ),
        "d": note(
            brain,
            "web/d.md",
            title="Delta",
            creator_key="author",
            creator="ada",
            concepts=["Measure μ"],
        ),
        "e": note(brain, "youtube/e.md", title="Epsilon", creator="Solo", concepts=["measure"]),
    }


def by_key(cands):
    return {(c.kind, c.key): c for c in cands}


def test_normalization_matches_the_measured_rule():
    assert hubs.normalize_concept("Cross-entropy  loss") == "cross entropy loss"
    assert hubs.normalize_concept("Measure μ") == hubs.normalize_concept("measure")
    assert hubs.normalize_concept("注意") == "注意"
    assert hubs.normalize_creator(" 3Blue1Brown ") == hubs.normalize_creator("3blue1brown")


def test_concept_names_take_the_text_before_the_first_colon():
    body = "## Key Concepts\n- **tmux**: panes: many\n- Bare name\n\n## Insights\n- x: y\n"
    assert hubs.concept_names(body) == ["tmux", "Bare name"]


def test_candidates_are_names_in_two_or_more_notes_sorted_by_count(conn, brain, corpus):
    cands = hubs.candidates(conn)
    keys = [(c.kind, c.key) for c in cands]
    assert keys[0] == ("concept", "manim")
    assert ("creator", "solo") not in keys  # one note
    assert ("concept", "linear maps") not in keys
    got = by_key(cands)
    assert got[("concept", "manim")].count == 3
    assert got[("concept", "manim")].name == "Manim"  # the most frequent surface form
    assert got[("concept", "measure")].count == 2
    assert got[("creator", "ada")].count == 2  # web notes name creators by `author`
    assert got[("creator", "3blue1brown")].examples == ["Alpha", "Beta"]
    assert all(c.verdict == "pending" for c in cands)


def test_pending_names_write_nothing(conn, brain, corpus):
    before = {p: p.read_bytes() for p in corpus.values()}
    report = hubs.apply(conn)
    assert report.pending == 5 and report.notes_changed == 0 and report.hubs_written == 0
    assert {p: p.read_bytes() for p in corpus.values()} == before
    assert not (brain / hubs.HUBS_DIR).exists()


def test_approved_names_link_from_frontmatter_and_get_a_generated_hub(conn, brain, corpus):
    a = corpus["a"]
    body_before = a.read_text().split("---\n", 2)[2]
    old = os.stat(a).st_mtime_ns - 10_000_000_000
    os.utime(a, ns=(old, old))
    approve(conn, ("concept", "manim"), ("creator", "3blue1brown"))
    report = hubs.apply(conn)

    text = a.read_text()
    assert 'creator: "[[3Blue1Brown]]"\n' in text
    assert 'concepts:\n  - "[[Manim]]"\n---\n' in text  # Fable is still pending
    assert text.split("---\n", 2)[2] == body_before
    assert os.stat(a).st_mtime_ns == old
    assert report.notes_linked == 3 and report.hubs_written == 2

    hub = brain / "links" / "concepts" / "Manim.md"
    hub_text = hub.read_text()
    assert "generated_by: ytk-hubs" in hub_text
    assert "[[Vault/second-brain/sources/youtube/a|Alpha]]" not in hub_text
    assert "[[second-brain/sources/youtube/a|Alpha]]" in hub_text
    assert (brain / "links" / "creators" / "3Blue1Brown.md").exists()


def test_apply_is_idempotent(conn, brain, corpus):
    approve(conn, ("concept", "manim"), ("concept", "fable"), ("creator", "ada"))
    hubs.apply(conn)
    snapshot = {p: p.read_bytes() for p in brain.rglob("*.md")}
    again = hubs.apply(conn)
    assert again.notes_changed == 0 and again.hubs_written == 0 and again.hubs_removed == 0
    assert {p: p.read_bytes() for p in brain.rglob("*.md")} == snapshot


def test_striking_a_name_removes_every_link_and_its_hub(conn, brain, corpus):
    originals = {p: p.read_text() for p in corpus.values()}
    approve(conn, ("concept", "manim"), ("creator", "3blue1brown"))
    hubs.apply(conn)
    strike(conn, ("concept", "manim"), ("creator", "3blue1brown"))
    report = hubs.apply(conn)
    assert report.hubs_removed == 2
    assert {p: p.read_text() for p in corpus.values()} == originals
    assert not list((brain / "links").rglob("*.md"))


def test_hand_made_note_is_the_target_and_is_never_written(conn, brain, corpus):
    people = brain / "notes" / "ai" / "people"
    people.mkdir(parents=True)
    hand = people / "3blue1brown.md"
    hand.write_text("# hand made\n")
    approve(conn, ("creator", "3blue1brown"))
    report = hubs.apply(conn)
    cand = by_key(hubs.candidates(conn))[("creator", "3blue1brown")]
    assert cand.hand_made and cand.target == "3blue1brown"
    assert cand.target_path == "second-brain/notes/ai/people/3blue1brown.md"
    assert 'creator: "[[3blue1brown]]"' in corpus["a"].read_text()
    assert hand.read_text() == "# hand made\n"
    assert report.hubs_written == 0 and report.hand_made_targets == 1


def test_basename_clashes_get_a_kind_suffix(conn, brain, corpus):
    # A source note and a note outside second-brain are not hub targets.
    note(brain, "web/Fable.md", title="Fable the source")
    (brain.parent / "JOURNAL").mkdir()
    (brain.parent / "JOURNAL" / "Manim.md").write_text("journal\n")
    note(brain, "web/f.md", title="Zeta", creator_key="author", creator="Manim")
    note(brain, "web/g.md", title="Eta", creator_key="author", creator="Manim")
    got = by_key(hubs.candidates(conn))
    assert got[("concept", "fable")].target == "Fable (concept)"
    assert got[("concept", "manim")].target == "Manim (concept)"
    assert "JOURNAL/Manim.md" in got[("concept", "manim")].collision
    # The creator shares the concept's name; concepts claim names first.
    assert got[("creator", "manim")].target == "Manim (creator)"


def test_generated_hubs_are_not_collisions_on_the_next_run(conn, brain, corpus):
    approve(conn, ("concept", "manim"))
    hubs.apply(conn)
    cand = by_key(hubs.candidates(conn))[("concept", "manim")]
    assert cand.target == "Manim" and not cand.collision


def test_a_hand_written_property_is_left_alone(conn, brain, corpus):
    a = corpus["a"]
    a.write_text(a.read_text().replace("tags:\n", "creator: Grant (hand typed)\ntags:\n", 1))
    approve(conn, ("creator", "3blue1brown"))
    report = hubs.apply(conn)
    assert "creator: Grant (hand typed)" in a.read_text()
    assert "[[3Blue1Brown]]" not in a.read_text()
    assert report.foreign_keys == ["second-brain/sources/youtube/a.md: creator"]


def test_obsidian_reformatted_links_are_still_owned():
    text = '---\ntitle: x\nconcepts: ["[[Old]]", "[[Manim]]"]\ncreator: "[[Gone]]"\n---\nbody\n'
    new, foreign = hubs.set_links(text, None, ["Manim"])
    assert foreign == []
    assert new == '---\ntitle: x\nconcepts:\n  - "[[Manim]]"\n---\nbody\n'


def test_tag_merges_never_touch_link_lines(conn, brain, corpus, monkeypatch):
    from ytk import tags

    approve(conn, ("concept", "manim"))
    hubs.apply(conn)
    monkeypatch.setenv("YTK_TAG_ALIASES", str(brain.parent / "aliases.yaml"))
    tags._rewrite_frontmatter({"manim": "manim-ce"})
    text = corpus["a"].read_text()
    assert "  - manim-ce\n" in text and '  - "[[Manim]]"\n' in text


def test_verdict_history_is_kept_and_the_latest_wins(conn):
    approve(conn, ("concept", "fable"))
    approve(conn, ("concept", "fable"))  # unchanged: no new row
    strike(conn, ("concept", "fable"))
    rows = conn.execute("SELECT verdict, judged_by, surface FROM hub_verdicts").fetchall()
    assert [tuple(r) for r in rows] == [
        ("approve", "owner", "test"),
        ("strike", "owner", "test"),
    ]
    assert hubs.current_verdicts(conn)[("concept", "fable")][0] == "strike"
    with pytest.raises(ValueError):
        hubs.record_verdicts(conn, [("concept", "fable", "maybe")], surface="test")


def test_landing_links_new_notes_and_new_names_arrive_pending(conn, brain, corpus):
    assert hubs.link_landed(conn) is None  # nothing approved: no scan, no write
    approve(conn, ("concept", "manim"))
    hubs.apply(conn)
    landed = note(
        brain, "youtube/new.md", title="New", creator="Solo", concepts=["Manim", "Linear maps"]
    )
    report = hubs.link_landed(conn)
    assert report is not None
    assert '  - "[[Manim]]"' in landed.read_text()
    assert (
        "[[second-brain/sources/youtube/new|New]]"
        in (brain / "links" / "concepts" / "Manim.md").read_text()
    )
    got = by_key(hubs.candidates(conn))
    assert got[("creator", "solo")].verdict == "pending"
    assert got[("concept", "linear maps")].verdict == "pending"
    assert "Linear maps" not in landed.read_text().split("---\n", 2)[1]


def test_api_lists_candidates_and_applies_verdicts(conn, brain, corpus):
    from fastapi.testclient import TestClient

    from ytk.ui.server import app

    client = TestClient(app)
    listed = client.get("/api/hubs").json()
    assert listed["threshold"] == 2
    assert listed["summary"]["concept"]["pending"] == 3
    first = listed["candidates"][0]
    assert first["key"] == "manim" and first["examples"] and first["target"] == "Manim"

    resp = client.post(
        "/api/hubs/apply",
        json={
            "verdicts": [
                {"kind": "concept", "key": "manim", "verdict": "approve"},
                {"kind": "concept", "key": "fable", "verdict": "strike"},
            ]
        },
    ).json()
    assert resp["recorded"] == 2 and resp["notes_linked"] == 3
    assert '  - "[[Manim]]"' in corpus["c"].read_text()
    assert "[[Fable]]" not in corpus["c"].read_text()
    bad = client.post(
        "/api/hubs/apply", json={"verdicts": [{"kind": "x", "key": "y", "verdict": "approve"}]}
    )
    assert bad.status_code == 422


def test_a_hand_made_target_names_its_duplicates(conn, brain, corpus):
    (brain / "notes").mkdir()
    (brain / "notes" / "Manim.md").write_text("# mine\n")
    (brain.parent / "Manim.md").write_text("# root copy\n")
    cand = by_key(hubs.candidates(conn))[("concept", "manim")]
    assert cand.hand_made and cand.target_path == "second-brain/notes/Manim.md"
    assert cand.collision == "Manim.md"
