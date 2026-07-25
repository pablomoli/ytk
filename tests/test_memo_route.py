"""route() classifies a transcript via sdk.structured (SDK path mocked here)."""

from unittest.mock import patch

from ytk.memo import MemoResult, route


def _fake_structured(payload):
    return patch("ytk.sdk.run_structured", return_value=payload)


def test_route_memory_kind():
    payload = {
        "kind": "memory",
        "summary": "Prefers SigLIP-2 for visual embeddings",
        "tags": ["ytk", "embeddings"],
        "items": [],
    }
    with _fake_structured(payload):
        result = route("remember that siglip two won our encoder eval")
    assert isinstance(result, MemoResult)
    assert result.kind == "memory"
    assert result.tags == ["ytk", "embeddings"]
    assert result.items == []


def test_route_action_kind_with_items():
    payload = {
        "kind": "action",
        "summary": "Fix hub filter latency",
        "tags": [],
        "items": [
            {
                "title": "Fix hub filter latency",
                "description": "Filtering on /inbox re-renders the whole grid.",
                "priority": "high",
                "suggested_route": "gh-issue",
                "suggested_repo": "pablomoli/ytk",
            }
        ],
    }
    with _fake_structured(payload):
        result = route("the inbox filters are slow, file an issue", repos=["pablomoli/ytk"])
    assert result.kind == "action"
    assert len(result.items) == 1
    assert result.items[0].suggested_repo == "pablomoli/ytk"


def test_route_passes_repos_into_system_prompt():
    payload = {"kind": "thought", "summary": "x", "tags": [], "items": []}
    with _fake_structured(payload) as mocked:
        route("just thinking out loud", repos=["pablomoli/ytk", "pablomoli/epicmap"])
    system = mocked.call_args.args[0]
    assert "pablomoli/ytk" in system
    assert "pablomoli/epicmap" in system


def test_route_thought_kind_default():
    payload = {
        "kind": "thought",
        "summary": "Loose musing about embeddings",
        "tags": [],
        "items": [],
    }
    with _fake_structured(payload):
        result = route("embeddings are so mathematically pretty")
    assert result.kind == "thought"
