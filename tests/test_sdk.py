"""Tests for the Agent SDK options wrapper."""

from ytk.sdk import _build_options


def test_options_raise_stdout_buffer_for_image_reads():
    opts = _build_options("sys", {"type": "object"}, ["/tmp/frames"], max_turns=20)
    # a single base64-encoded carousel slide can exceed the SDK's 1MB default
    assert opts.max_buffer_size >= 10 * 1024 * 1024


def test_options_no_read_tool_without_dirs():
    opts = _build_options("sys", {"type": "object"}, [], max_turns=20)
    assert opts.allowed_tools == []
    assert opts.max_turns == 20
