"""Description persistence: note section, enrichment prompt, and the backfill (#105, #106).

The invariant these tests defend is the 2026-07-24 decision: the raw description
is stored and fed to enrichment, but never lands in an embedded document.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

from ytk.enrich import DESCRIPTION_PROMPT_LIMIT, SOURCE_BIAS, _description_block
from ytk.vault import _build_description

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


backfill = _load("backfill_descriptions")
reenrich = _load("reenrich_with_descriptions")


NOTE = """\
---
url: https://youtu.be/abc
title: Example
tags:
  - go
---

## Thesis
old thesis

## Commentary
old commentary

## Key Concepts
- old concept

## Insights
- old insight

## Key Moments
- **0:00** — old moment

## Transcript
<details>
<summary>Raw transcript</summary>

hello world
</details>
"""


# --- note section ---------------------------------------------------------


def test_description_section_is_verbatim_and_collapsed():
    block = _build_description("Chapters:\n0:00 intro\n#golang #rust")
    assert block.startswith("## Description\n<details>")
    assert "#golang #rust" in block
    assert "0:00 intro" in block


def test_empty_description_writes_no_section():
    assert _build_description("") == ""
    assert _build_description("   \n ") == ""


def test_backfill_inserts_between_key_moments_and_transcript():
    out, outcome = backfill.insert_description(NOTE, "the description")
    assert outcome == "written"
    assert out.index("## Key Moments") < out.index("## Description")
    assert out.index("## Description") < out.index("## Transcript")
    assert "the description" in out


def test_backfill_is_idempotent():
    once, _ = backfill.insert_description(NOTE, "the description")
    twice, outcome = backfill.insert_description(once, "the description")
    assert outcome == "already"
    assert twice == once
    assert twice.count("## Description") == 1


def test_backfill_reports_missing_anchor_instead_of_guessing():
    _, outcome = backfill.insert_description("## Thesis\nx\n", "d")
    assert outcome == "no-anchor"


def test_backfill_preserves_every_other_section():
    out, _ = backfill.insert_description(NOTE, "d")
    for section in ("## Thesis", "## Commentary", "## Key Concepts",
                    "## Insights", "## Key Moments", "## Transcript"):
        assert section in out
    assert "hello world" in out
    assert out.startswith("---\nurl: https://youtu.be/abc")


def test_backfill_flags_headings_a_note_parser_would_misread():
    assert backfill.collides("intro\n## Summary\nsponsor") == ["## Summary"]
    assert backfill.collides("#shorts\n## Sponsors") == []


# --- enrichment prompt ----------------------------------------------------


def test_description_reaches_the_enrichment_prompt():
    block = _description_block("built with bevy 0.14")
    assert "bevy 0.14" in block
    assert "sponsor" in block.lower()


def test_empty_description_adds_nothing_to_the_prompt():
    assert _description_block("") == ""


def test_long_description_is_truncated_not_dropped():
    block = _description_block("x" * (DESCRIPTION_PROMPT_LIMIT + 5000))
    assert "truncated" in block
    assert len(block) < DESCRIPTION_PROMPT_LIMIT + 500


def test_youtube_bias_warns_against_sponsor_contamination():
    bias = SOURCE_BIAS["youtube"]
    assert "sponsor" in bias.lower()
    assert "boilerplate" in bias.lower()


# --- the invariant --------------------------------------------------------


def test_upsert_stores_description_in_metadata_but_never_in_the_document():
    from ytk import store

    captured = {}

    class FakeCol:
        name = "fake"

        def upsert(self, ids, documents, metadatas):
            captured["ids"] = ids
            captured["documents"] = documents
            captured["metadatas"] = metadatas

    class E:
        thesis = "T"
        summary = "S"
        key_concepts = ["c"]
        insights = ["i"]
        interest_tags = ["go"]
        key_moments = []

    fake = FakeCol()
    orig_col, orig_stamp = store._videos_collection, store._with_ingest_time
    store._videos_collection = lambda *a, **k: fake
    store._with_ingest_time = lambda col, ids, metas: metas
    try:
        store.upsert(
            {"id": "vid1", "title": "t", "url": "u",
             "description": "SPONSORED BY ACME, secret token xyzzy"},
            E(), [],
        )
    finally:
        store._videos_collection, store._with_ingest_time = orig_col, orig_stamp

    assert captured["metadatas"][0]["description"].startswith("SPONSORED BY ACME")
    for doc in captured["documents"]:
        assert "xyzzy" not in doc
        assert "ACME" not in doc


# --- re-enrich note surgery ----------------------------------------------


class _Enrichment:
    thesis = "new thesis"
    summary = "new commentary"
    key_concepts = ["new concept"]
    insights = ["new insight"]

    class _M:
        timestamp = "1:23"
        description = "new moment"

    key_moments = [_M()]


def test_reenrich_replaces_prose_and_keeps_everything_else():
    note, _ = backfill.insert_description(NOTE, "THE DESCRIPTION")
    note = note.replace("## Transcript", "## My take\nmine\n\n## Transcript")
    out, missed = reenrich.rewrite_note(note, _Enrichment())

    assert missed == []
    assert "new thesis" in out and "old thesis" not in out
    assert "new commentary" in out and "old commentary" not in out
    assert "- new concept" in out and "old concept" not in out
    assert "- **1:23** — new moment" in out

    # untouched territory
    assert "THE DESCRIPTION" in out
    assert "## My take\nmine" in out
    assert "hello world" in out
    assert "  - go" in out  # user-curated frontmatter tags round-trip
    assert out.index("## Key Moments") < out.index("## Description")
    assert out.index("## Description") < out.index("## Transcript")


def test_reenrich_reports_sections_it_could_not_find():
    _, missed = reenrich.rewrite_note("## Thesis\nx\n", _Enrichment())
    assert "Commentary" in missed and "Insights" in missed


@pytest.mark.parametrize("mod", [backfill, reenrich])
def test_ledger_round_trips_and_survives_corruption(mod, tmp_path):
    path = tmp_path / "ledger.json"
    ledger = mod.load_ledger(path)
    mod.record(ledger, "vid1", "ok", chars=12)
    mod.save_ledger(path, ledger)

    assert mod.load_ledger(path)["videos"]["vid1"]["status"] == "ok"
    path.write_text("{not json", encoding="utf-8")
    assert mod.load_ledger(path) == {"videos": {}}
