"""Tests for ytk/triage.py — action item extraction via Claude Agent SDK."""

from __future__ import annotations

from unittest.mock import patch

from ytk.triage import ActionItem, extract_action_items


def test_extract_returns_items():
    fake = {
        "items": [
            {
                "title": "Fix settings page drawer layout",
                "description": "Redesign as vertical drawer with right column.",
                "priority": "high",
                "suggested_route": "gh-issue",
                "suggested_repo": None,
            }
        ]
    }
    with patch("ytk.triage.run_structured", return_value=fake):
        items = extract_action_items("Fix the settings page drawer for Epic Map.")
    assert len(items) == 1
    assert items[0].title == "Fix settings page drawer layout"
    assert items[0].priority == "high"
    assert items[0].suggested_route == "gh-issue"


def test_extract_returns_empty_list():
    with patch("ytk.triage.run_structured", return_value={"items": []}):
        items = extract_action_items("Had a nice walk today.")
    assert items == []


def test_action_item_priority_values():
    for priority in ["high", "medium", "low"]:
        item = ActionItem(
            title="Test",
            description="Desc.",
            priority=priority,
            suggested_route="idea",
        )
        assert item.priority == priority


def test_action_item_route_values():
    for route in ["gh-issue", "idea", "investigate"]:
        item = ActionItem(
            title="Test",
            description="Desc.",
            priority="medium",
            suggested_route=route,
        )
        assert item.suggested_route == route


def test_action_item_suggested_repo_defaults_none():
    item = ActionItem(title="T", description="D.", priority="low", suggested_route="gh-issue")
    assert item.suggested_repo is None


def test_action_item_suggested_repo_set():
    item = ActionItem(
        title="T", description="D.", priority="high",
        suggested_route="gh-issue", suggested_repo="pablomoli/epicmap",
    )
    assert item.suggested_repo == "pablomoli/epicmap"


def test_extract_passes_repos_to_system_prompt():
    with patch("ytk.triage.run_structured", return_value={"items": []}) as mock_run:
        extract_action_items("note text", repos=["owner/repo-a", "owner/repo-b"])
    system_arg = mock_run.call_args.args[0]
    assert "owner/repo-a" in system_arg
    assert "owner/repo-b" in system_arg


def test_extract_no_repos_omits_hint():
    with patch("ytk.triage.run_structured", return_value={"items": []}) as mock_run:
        extract_action_items("note text", repos=None)
    system_arg = mock_run.call_args.args[0]
    assert "Available GitHub repos" not in system_arg
