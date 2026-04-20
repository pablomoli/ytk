"""Tests for ytk/triage.py — action item extraction."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from ytk.triage import ActionItem, extract_action_items


def test_extract_returns_items():
    mock_result = MagicMock()
    mock_result.parsed_output.items = [
        ActionItem(
            title="Fix settings page drawer layout",
            description="Redesign as vertical drawer with right column.",
            priority="high",
            suggested_route="gh-issue",
        )
    ]
    with patch("ytk.triage._client", None), \
         patch("ytk.triage.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.parse.return_value = mock_result
        items = extract_action_items("Fix the settings page drawer for Epic Map.")
    assert len(items) == 1
    assert items[0].title == "Fix settings page drawer layout"
    assert items[0].priority == "high"
    assert items[0].suggested_route == "gh-issue"


def test_extract_returns_empty_list():
    mock_result = MagicMock()
    mock_result.parsed_output.items = []
    with patch("ytk.triage._client", None), \
         patch("ytk.triage.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.parse.return_value = mock_result
        items = extract_action_items("Had a nice walk today.")
    assert items == []


def test_extract_reuses_client_singleton():
    mock_result = MagicMock()
    mock_result.parsed_output.items = []
    mock_client = MagicMock()
    mock_client.messages.parse.return_value = mock_result
    with patch("ytk.triage._client", mock_client):
        extract_action_items("first call")
        extract_action_items("second call")
    assert mock_client.messages.parse.call_count == 2


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
