"""execute_route() creates the right artifacts per kind."""

from unittest.mock import patch

from ytk.memo import MemoResult, execute_route
from ytk.triage import ActionItem


def _memory_result():
    return MemoResult(kind="memory", summary="s", tags=["ytk"], items=[])


def _action_result(route="gh-issue", repo="pablomoli/ytk"):
    return MemoResult(
        kind="action",
        summary="s",
        items=[
            ActionItem(
                title="Fix filters",
                description="Grid re-renders fully.",
                priority="high",
                suggested_route=route,
                suggested_repo=repo,
            )
        ],
    )


def test_memory_routes_to_remember(tmp_path):
    with (
        patch("ytk.memo.remember", return_value=(tmp_path / "atom.md", "memory_x")) as rem,
        patch("ytk.store.upsert_memory") as ups,
    ):
        lines = execute_route(_memory_result(), "the transcript", [])
    rem.assert_called_once_with("the transcript", ["ytk"])
    ups.assert_called_once()
    assert "memory ->" in lines[0]


def test_action_gh_issue_success(tmp_path):
    fake = type(
        "R",
        (),
        {"returncode": 0, "stdout": "https://github.com/pablomoli/ytk/issues/99\n", "stderr": ""},
    )()
    with (
        patch("ytk.memo._get_brain_path", return_value=tmp_path),
        patch("ytk.memo.subprocess.run", return_value=fake) as run,
    ):
        lines = execute_route(_action_result(), "t", ["pablomoli/ytk"])
    cmd = run.call_args.args[0]
    assert cmd[:3] == ["gh", "issue", "create"]
    assert "issues/99" in lines[0]


def test_action_gh_failure_downgrades_to_idea(tmp_path):
    fake = type("R", (), {"returncode": 1, "stdout": "", "stderr": "boom"})()
    with (
        patch("ytk.memo._get_brain_path", return_value=tmp_path),
        patch("ytk.memo.subprocess.run", return_value=fake),
    ):
        lines = execute_route(_action_result(), "t", ["pablomoli/ytk"])
    ideas = (tmp_path / "inbox" / "ideas.md").read_text()
    assert "- [ ] Fix filters" in ideas
    assert "idea (gh failed)" in lines[0]


def test_action_gh_missing_binary_downgrades_to_idea(tmp_path):
    with (
        patch("ytk.memo._get_brain_path", return_value=tmp_path),
        patch("ytk.memo.subprocess.run", side_effect=FileNotFoundError("gh")),
    ):
        lines = execute_route(_action_result(), "t", ["pablomoli/ytk"])
    ideas = (tmp_path / "inbox" / "ideas.md").read_text()
    assert "- [ ] Fix filters" in ideas
    assert "idea (gh failed)" in lines[0]


def test_action_unknown_repo_goes_to_ideas(tmp_path):
    with patch("ytk.memo._get_brain_path", return_value=tmp_path):
        lines = execute_route(_action_result(repo=None), "t", ["pablomoli/ytk"])
    assert (tmp_path / "inbox" / "ideas.md").exists()
    assert "idea ->" in lines[0]


def test_investigate_tagged_in_ideas(tmp_path):
    with patch("ytk.memo._get_brain_path", return_value=tmp_path):
        execute_route(_action_result(route="investigate", repo=None), "t", [])
    ideas = (tmp_path / "inbox" / "ideas.md").read_text()
    assert "(investigate)" in ideas


def test_thought_produces_no_artifacts():
    lines = execute_route(MemoResult(kind="thought", summary="s"), "t", [])
    assert lines == []


def test_mixed_routing_thought_with_stated_asks(tmp_path):
    """A musing-dominant memo still files its stated action items."""
    result = MemoResult(
        kind="thought",
        summary="brainstorm",
        items=[
            ActionItem(
                title="Add loading indicator to inbox",
                description="Spinner or stage display for in-flight ingests.",
                priority="medium",
                suggested_route="idea",
                suggested_repo=None,
            )
        ],
    )
    with patch("ytk.memo._get_brain_path", return_value=tmp_path):
        lines = execute_route(result, "t", [])
    assert len(lines) == 1
    assert "Add loading indicator" in (tmp_path / "inbox" / "ideas.md").read_text()
