"""ytk memo wiring: pipeline order, dry-run, exit codes."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from ytk.cli import cli
from ytk.memo import MemoResult


def _patches(tmp_path, route_result=None, route_error=None):
    result = route_result or MemoResult(kind="thought", summary="a musing")
    route = MagicMock(side_effect=route_error) if route_error else MagicMock(return_value=result)
    return [
        patch("ytk.cli.memo_record", return_value=tmp_path / "m.wav"),
        patch("ytk.cli.memo_transcribe", return_value="a musing"),
        patch("ytk.cli.memo_write_note", return_value=tmp_path / "note.md"),
        patch("ytk.cli.memo_route", route),
        patch("ytk.cli.memo_execute", return_value=[]),
        patch("ytk.cli.memo_finalize"),
        patch("ytk.cli.memo_notify", return_value=["tmux"]),
        patch("ytk.cli.memo_index"),
    ]


def _run(args, patches):
    from contextlib import ExitStack

    with ExitStack() as stack:
        mocks = [stack.enter_context(p) for p in patches]
        result = CliRunner().invoke(cli, args)
    return result, mocks


def test_memo_happy_path_exit_0(tmp_path):
    result, mocks = _run(["memo"], _patches(tmp_path))
    assert result.exit_code == 0, result.output
    assert "a musing" in result.output


def test_memo_text_skips_recording(tmp_path):
    result, mocks = _run(["memo", "--text", "typed thought"], _patches(tmp_path))
    assert result.exit_code == 0
    mocks[0].assert_not_called()   # memo_record
    mocks[1].assert_not_called()   # memo_transcribe


def test_memo_dry_run_never_executes(tmp_path):
    result, mocks = _run(["memo", "--dry-run", "--text", "x"], _patches(tmp_path))
    assert result.exit_code == 0
    mocks[4].assert_not_called()   # memo_execute
    mocks[6].assert_not_called()   # memo_notify


def test_memo_routing_failure_exit_2(tmp_path):
    result, mocks = _run(
        ["memo", "--text", "x"],
        _patches(tmp_path, route_error=RuntimeError("claude down")),
    )
    assert result.exit_code == 2
    mocks[5].assert_called_once()  # memo_finalize with "failed"
    assert mocks[5].call_args.args[1] == "failed"
