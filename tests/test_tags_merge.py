"""Tag consolidation guardrails: Haiku output clamped to proposed clusters,
merges are append-safe rewrites, aliases hold at every tag entry point."""

from __future__ import annotations

import pytest

from ytk import config, tags, vault


@pytest.fixture
def alias_file(tmp_path, monkeypatch):
    path = tmp_path / "tag-aliases.yaml"
    monkeypatch.setenv("YTK_TAG_ALIASES", str(path))
    monkeypatch.setattr(config, "_alias_cache", None)
    return path


def test_alias_roundtrip_and_chain_collapse(alias_file):
    config.save_tag_aliases({"agentic-coding": "ai-coding"})
    config.save_tag_aliases({"ai-coding": "coding-agents"})
    aliases = config.tag_aliases()
    # earlier decision re-resolves through the newer one, lookups stay 1-hop
    assert aliases["agentic-coding"] == "coding-agents"
    assert aliases["ai-coding"] == "coding-agents"


def test_normalize_tag_consults_aliases(alias_file):
    config.save_tag_aliases({"developer-tools": "dev-tools"})
    assert vault._normalize_tag("Developer Tools") == "dev-tools"
    assert vault._normalize_tag("falconry") == "falconry"


def test_enrichment_tags_born_canonical(alias_file):
    from ytk.enrich import Enrichment

    config.save_tag_aliases({"artificial-intelligence": "ai"})
    e = Enrichment(thesis="t", summary="s", key_concepts=[], insights=[],
                   interest_tags=["Artificial Intelligence", "ai", "go"],
                   key_moments=[])
    assert e.interest_tags == ["ai", "go"]


def test_propose_clamps_to_clusters(monkeypatch):
    from collections import Counter

    monkeypatch.setattr(tags.store, "tag_counts",
                        lambda: Counter({"llm": 1, "llms": 1, "mma": 6}))
    monkeypatch.setattr(tags, "_clusters", lambda t: [["llm", "llms"]])
    monkeypatch.setattr(tags, "structured", lambda *a, **k: tags._Refinement(groups=[
        tags.MergeGroup(canonical="llm", variants=["llms", "mma", "invented-tag"]),
        tags.MergeGroup(canonical="alone", variants=[]),
    ]))

    out = tags.propose_merges()
    assert len(out) == 1
    assert out[0].canonical == "llm"
    assert out[0].variants == ["llms"]  # mma is another cluster, invented-tag is fake
    assert out[0].counts == {"llm": 1, "llms": 1}


def test_apply_rewrites_frontmatter(alias_file, tmp_path, monkeypatch):
    monkeypatch.setattr(vault, "_get_vault_path", lambda: tmp_path)
    note = tmp_path / "second-brain" / "sources" / "youtube" / "a.md"
    note.parent.mkdir(parents=True)
    note.write_text("---\ntags:\n  - llms\n  - go\n---\n\nbody llms stays\n")
    dupe = note.parent / "b.md"
    dupe.write_text("---\ntags:\n  - llm\n  - llms\n---\n\nbody\n")

    class _EmptyCol:
        def count(self):
            return 0

    monkeypatch.setattr(tags.store, "_videos_collection", lambda: _EmptyCol())
    summary = tags.apply_merges({"llms": "llm", "same": "same"})

    assert summary["notes"] == 2
    assert "  - llm\n" in note.read_text() and "llms" not in note.read_text().split("---")[1]
    assert "body llms stays" in note.read_text()  # only frontmatter is touched
    assert dupe.read_text().split("---")[1].count("llm") == 1  # deduped, not doubled
    assert config.tag_aliases() == {"llms": "llm"}
