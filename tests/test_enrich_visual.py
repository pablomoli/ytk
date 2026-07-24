"""Tests for ytk/enrich.py under the Claude Agent SDK path.

The enrichment now routes through `run_structured`. When visual_blocks are
present, image bytes are materialized into a temp dir and its path is added
to `add_dirs`. When absent, `add_dirs` is empty and no temp dir is created.
"""

from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import patch


def _fake_enrichment_dict() -> dict:
    return {
        "thesis": "test thesis",
        "summary": "test summary",
        "key_concepts": ["tool: used here"],
        "insights": ["non-obvious thing"],
        "interest_tags": ["art"],
        "key_moments": [],
    }


def _base64_image_block() -> dict:
    data = base64.standard_b64encode(b"\xff\xd8\xff\xe0fake-jpeg").decode()
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}}


def test_enrich_text_only_no_add_dirs():
    from ytk.enrich import enrich

    with patch("ytk.enrich.run_structured", return_value=_fake_enrichment_dict()) as mock_run:
        enrich("transcript text", {"title": "T", "uploader": "U", "duration": 60, "tags": []})

    kwargs = mock_run.call_args.kwargs
    assert kwargs["add_dirs"] == []


def test_enrich_with_visual_blocks_materializes_to_add_dirs():
    from ytk.enrich import enrich

    visual = [_base64_image_block(), _base64_image_block()]
    seen_dirs: list[Path] = []

    def fake_run(system, prompt, schema, add_dirs=None, max_turns=20):
        assert add_dirs, "expected add_dirs populated when visual_blocks present"
        for d in add_dirs:
            p = Path(d)
            assert p.exists(), f"staged image dir should exist during SDK call: {p}"
            jpgs = sorted(p.glob("*.jpg"))
            assert len(jpgs) == len(visual)
            seen_dirs.append(p)
        return _fake_enrichment_dict()

    with patch("ytk.enrich.run_structured", side_effect=fake_run):
        enrich(
            "caption text",
            {"title": "T", "uploader": "U", "duration": 0, "tags": []},
            visual_blocks=visual,
        )

    # Temp dir should be cleaned up once enrich returns
    for d in seen_dirs:
        assert not d.exists()


def test_enrich_prompt_lists_frame_paths_when_visual():
    from ytk.enrich import enrich

    visual = [_base64_image_block()]
    with patch("ytk.enrich.run_structured", return_value=_fake_enrichment_dict()) as mock_run:
        enrich(
            "caption",
            {"title": "T", "uploader": "U", "duration": 0, "tags": []},
            visual_blocks=visual,
        )
    prompt = mock_run.call_args.args[1]
    assert "Extracted frames" in prompt
    assert "frame-00.jpg" in prompt


def test_enrich_none_visual_blocks_behaves_like_no_arg():
    from ytk.enrich import enrich

    prompts: list[str] = []

    def fake_run(system, prompt, schema, add_dirs=None, max_turns=20):
        prompts.append(prompt)
        return _fake_enrichment_dict()

    with patch("ytk.enrich.run_structured", side_effect=fake_run):
        enrich("t", {"title": "T", "uploader": "U", "duration": 0, "tags": []})
        enrich("t", {"title": "T", "uploader": "U", "duration": 0, "tags": []}, visual_blocks=None)

    assert prompts[0] == prompts[1]
    assert "Extracted frames" not in prompts[0]
