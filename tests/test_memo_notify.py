"""Focus-aware dispatch: terminal visible -> tmux; hidden -> macos; sketchybar always."""

from unittest.mock import MagicMock, patch

from ytk.memo import notify


def _aerospace(visible_apps):
    out = MagicMock(returncode=0, stdout="\n".join(visible_apps))
    return patch("ytk.memo.subprocess.run", return_value=out)


def test_terminal_visible_fires_tmux_and_sketchybar():
    with (
        patch("ytk.memo.shutil.which", return_value="/opt/bin/x"),
        _aerospace(["Ghostty", "Zen Browser"]),
    ):
        fired = notify("routed", "memory")
    assert fired == ["tmux", "sketchybar"]


def test_terminal_hidden_fires_macos_and_sketchybar():
    with patch("ytk.memo.shutil.which", return_value="/opt/bin/x"), _aerospace(["Zen Browser"]):
        fired = notify("routed", "memory")
    assert fired == ["macos", "sketchybar"]


def test_no_aerospace_falls_back_to_tmux_env(monkeypatch):
    monkeypatch.setenv("TMUX", "/tmp/tmux-1/default,1,0")
    with (
        patch("ytk.memo.shutil.which", side_effect=lambda b: None if b == "aerospace" else "/x"),
        patch("ytk.memo.subprocess.run"),
    ):
        fired = notify("routed", "thought")
    assert fired == ["tmux", "sketchybar"]


def test_explicit_backends_override_smart_dispatch():
    with patch("ytk.memo.subprocess.run"), patch("ytk.memo.shutil.which", return_value="/x"):
        fired = notify("routed", "action", backends=["macos"])
    assert fired == ["macos"]


def test_backend_failure_is_silent(monkeypatch):
    monkeypatch.delenv("TMUX", raising=False)
    with (
        patch("ytk.memo.shutil.which", return_value="/x"),
        patch("ytk.memo.subprocess.run", side_effect=OSError("gone")),
    ):
        fired = notify("routed", "memory")  # must not raise
    assert fired == []
