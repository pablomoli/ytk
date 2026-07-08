"""ytk gc --prune-audio wiring: audio cache prunes even when no memories exist."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from ytk.cli import cli


def test_gc_prune_audio_runs_without_memories(tmp_path):
    """The audio prune must run before the 'no memories' early-return."""
    brain = tmp_path / "brain"
    (brain / "inbox").mkdir(parents=True)  # no memories/ dir at all
    fake_prune = MagicMock(return_value=[Path("yt_old.m4a")])
    with patch("ytk.vault._get_brain_path", return_value=brain), \
         patch("ytk.transcript.prune_audio_cache", fake_prune):
        result = CliRunner().invoke(cli, ["gc", "--prune-audio", "30"])
    assert result.exit_code == 0, result.output
    fake_prune.assert_called_once()
    assert fake_prune.call_args.kwargs["max_age_days"] == 30


def test_gc_prune_audio_dry_run_passes_flag(tmp_path):
    brain = tmp_path / "brain"
    (brain / "inbox" / "memories").mkdir(parents=True)
    fake_prune = MagicMock(return_value=[])
    with patch("ytk.vault._get_brain_path", return_value=brain), \
         patch("ytk.transcript.prune_audio_cache", fake_prune):
        result = CliRunner().invoke(cli, ["gc", "--prune-audio", "30", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert fake_prune.call_args.kwargs.get("dry_run") is True


def test_gc_prune_audio_exits_zero_when_vault_unconfigured(tmp_path):
    """The nightly standalone prune must exit 0 even if the vault isn't set up."""
    def _boom():
        raise EnvironmentError("OBSIDIAN_VAULT_PATH unset")
    fake_prune = MagicMock(return_value=[])
    with patch("ytk.vault._get_brain_path", side_effect=_boom), \
         patch("ytk.transcript.prune_audio_cache", fake_prune):
        result = CliRunner().invoke(cli, ["gc", "--prune-audio", "30"])
    assert result.exit_code == 0, result.output
    fake_prune.assert_called_once()
