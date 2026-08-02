"""The reflect rewrite contract (#98): additive, surgical, never generative."""

from ytk.enrich import Enrichment, KeyMoment
from ytk.reflect import (
    _split_frontmatter,
    append_reflection_section,
    rewrite_sections,
    stamp_reflection,
)

NEW = Enrichment(
    thesis="NEW THESIS",
    summary="NEW SUMMARY",
    key_concepts=["concept-a", "concept-b"],
    insights=["insight-x"],
    interest_tags=["ai", "new-tag"],
    key_moments=[KeyMoment(timestamp="1:23", description="the moment")],
)

YT_NOTE = """\
---
url: https://www.youtube.com/watch?v=abc12345678
title: A Video
uploader: Someone
date: 2026-01-01
captured: 2026-07-01
tags:
  - ai
  - old-tag
duration: 00:10:00
image_paths: []
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
- **0:01** — old moment

## My take
my handwritten take

## Transcript
<details>
<summary>Raw transcript</summary>

**[0:00](x)** hello world
</details>
"""

WEB_NOTE = """\
---
url: https://example.com/a
title: An Article
author: Writer
date: 2026-01-01
captured: 2026-07-01
tags:
  - ai
type: web
---

## Thesis
old thesis

## Summary
old summary

## Key Concepts
- old concept

## Insights
- old insight
"""


def test_rewrite_replaces_every_present_section():
    _, body = _split_frontmatter(YT_NOTE)
    out = rewrite_sections(body, NEW)
    assert "NEW THESIS" in out and "NEW SUMMARY" in out
    assert "- concept-a" in out and "- insight-x" in out
    assert "- **1:23** — the moment" in out
    for old in ("old thesis", "old commentary", "old concept", "old insight", "old moment"):
        assert old not in out


def test_rewrite_preserves_non_enrichment_content():
    _, body = _split_frontmatter(YT_NOTE)
    out = rewrite_sections(body, NEW)
    assert "my handwritten take" in out
    assert "**[0:00](x)** hello world" in out
    assert "<details>" in out


def test_rewrite_handles_summary_heading_variant():
    _, body = _split_frontmatter(WEB_NOTE)
    out = rewrite_sections(body, NEW)
    assert "NEW SUMMARY" in out
    assert "old summary" not in out
    # web notes have no Key Moments section; none is invented
    assert "Key Moments" not in out


def test_rewrite_missing_section_is_not_added():
    _, body = _split_frontmatter(WEB_NOTE)
    out = rewrite_sections(body, NEW)
    assert out.count("## ") == body.count("## ")


def test_stamp_adds_and_replaces_reflection_keys():
    fm, _ = _split_frontmatter(YT_NOTE)
    once = stamp_reflection(fm, 'why "this"?', "because", "2026-08-02")
    assert 'reflection_question: "why \\"this\\"?"' in once
    assert "reflected: true" in once
    assert once.endswith("---\n")
    twice = stamp_reflection(once, "again?", "still", "2026-08-03")
    assert twice.count("reflected: true") == 1
    assert "again?" in twice and "why" not in twice
    # every original key survives
    for key in ("url:", "title:", "uploader:", "date:", "captured:", "duration:"):
        assert key in twice


def test_reflection_section_lands_before_raw_tail():
    _, body = _split_frontmatter(YT_NOTE)
    out = append_reflection_section(body, "q?", "a", "2026-08-02")
    assert out.index("## Reflection") < out.index("## Transcript")


def test_reflection_section_appends_when_no_tail():
    _, body = _split_frontmatter(WEB_NOTE)
    out = append_reflection_section(body, "q?", "a", "2026-08-02")
    assert out.rstrip().endswith("a")
    assert "## Reflection" in out
