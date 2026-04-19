from __future__ import annotations

from unittest.mock import patch


def _mock_enrichment():
    from ytk.enrich import Enrichment
    return Enrichment(
        thesis="test thesis",
        summary="test summary",
        key_concepts=["tool: used here"],
        insights=["non-obvious thing"],
        interest_tags=["art"],
        key_moments=[],
    )


def test_enrich_text_only_user_content_is_string():
    from ytk.enrich import enrich

    with patch("ytk.enrich._get_client") as mock_get:
        mock_get.return_value.messages.parse.return_value.parsed_output = _mock_enrichment()
        enrich("transcript text", {"title": "T", "uploader": "U", "duration": 60, "tags": []})

    call_kwargs = mock_get.return_value.messages.parse.call_args.kwargs
    assert isinstance(call_kwargs["messages"][0]["content"], str)


def test_enrich_with_visual_blocks_user_content_is_list():
    from ytk.enrich import enrich

    visual = [{"type": "image", "source": {"type": "url", "url": "https://example.com/img.jpg"}}]
    with patch("ytk.enrich._get_client") as mock_get:
        mock_get.return_value.messages.parse.return_value.parsed_output = _mock_enrichment()
        enrich(
            "caption text",
            {"title": "T", "uploader": "U", "duration": 0, "tags": []},
            visual_blocks=visual,
        )

    call_kwargs = mock_get.return_value.messages.parse.call_args.kwargs
    content = call_kwargs["messages"][0]["content"]
    assert isinstance(content, list)
    assert any(b.get("type") == "image" for b in content)
    assert any(b.get("type") == "text" for b in content)


def test_enrich_visual_system_prompt_includes_image_note():
    from ytk.enrich import enrich

    visual = [{"type": "image", "source": {"type": "url", "url": "https://example.com/img.jpg"}}]
    with patch("ytk.enrich._get_client") as mock_get:
        mock_get.return_value.messages.parse.return_value.parsed_output = _mock_enrichment()
        enrich(
            "caption",
            {"title": "T", "uploader": "U", "duration": 0, "tags": []},
            visual_blocks=visual,
        )

    call_kwargs = mock_get.return_value.messages.parse.call_args.kwargs
    system_text = call_kwargs["system"][0]["text"]
    assert "images" in system_text or "frames" in system_text


def test_enrich_none_visual_blocks_behaves_identically_to_no_arg():
    from ytk.enrich import enrich

    enrichment = _mock_enrichment()
    contents = []
    with patch("ytk.enrich._get_client") as mock_get:
        mock_get.return_value.messages.parse.return_value.parsed_output = enrichment
        enrich("t", {"title": "T", "uploader": "U", "duration": 0, "tags": []})
        contents.append(
            mock_get.return_value.messages.parse.call_args.kwargs["messages"][0]["content"]
        )
        enrich("t", {"title": "T", "uploader": "U", "duration": 0, "tags": []}, visual_blocks=None)
        contents.append(
            mock_get.return_value.messages.parse.call_args.kwargs["messages"][0]["content"]
        )

    assert isinstance(contents[0], str)
    assert isinstance(contents[1], str)
