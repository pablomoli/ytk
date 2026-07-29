"""R3 (#150): state/recent atoms supersede, never overwrite.

Design locked by docs/assets/memory-field/r3-design-sim.png: new content is a
dated current section; a second write the same day replaces that day's section
(within-day churn is not history); older sections demote under a divider; cap
10 in-file, overflow appends to {atom}-archive.md. Other atoms keep overwrite."""

from __future__ import annotations

from datetime import datetime

import pytest


@pytest.fixture
def brain(tmp_path, monkeypatch):
    monkeypatch.setattr("ytk.vault._get_brain_path", lambda: tmp_path)
    return tmp_path


def freeze(monkeypatch, day: str):
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls.strptime(day, "%Y-%m-%d")

    monkeypatch.setattr("ytk.vault.datetime", FrozenDateTime)


def atom_path(brain, atom="state"):
    return brain / "inbox" / "memories" / "proj" / f"{atom}.md"


def test_first_state_write_creates_dated_current_section(brain, monkeypatch):
    from ytk.vault import write_atom

    freeze(monkeypatch, "2026-07-29")
    write_atom("proj", "state", "building the batch pipeline")
    content = atom_path(brain).read_text()
    assert "## 2026-07-29" in content
    assert "building the batch pipeline" in content


def test_same_day_rewrite_replaces_todays_section(brain, monkeypatch):
    from ytk.vault import SUPERSEDED_DIVIDER, write_atom

    freeze(monkeypatch, "2026-07-29")
    write_atom("proj", "state", "first draft")
    write_atom("proj", "state", "second draft, same day")
    content = atom_path(brain).read_text()
    assert "second draft, same day" in content
    assert "first draft" not in content  # within-day churn is not history
    assert SUPERSEDED_DIVIDER not in content
    assert content.count("## 2026-07-29") == 1


def test_new_day_demotes_previous_state_under_divider(brain, monkeypatch):
    from ytk.vault import SUPERSEDED_DIVIDER, write_atom

    freeze(monkeypatch, "2026-07-28")
    write_atom("proj", "state", "yesterday: blocked on chroma")
    freeze(monkeypatch, "2026-07-29")
    write_atom("proj", "state", "today: unblocked, building")
    content = atom_path(brain).read_text()
    assert content.index("today: unblocked") < content.index(SUPERSEDED_DIVIDER)
    assert content.index(SUPERSEDED_DIVIDER) < content.index("yesterday: blocked")
    assert "## 2026-07-28" in content and "## 2026-07-29" in content


def test_cap_overflows_oldest_sections_to_archive(brain, monkeypatch):
    from ytk.vault import ATOM_HISTORY_CAP, write_atom

    for i in range(ATOM_HISTORY_CAP + 2):
        freeze(monkeypatch, f"2026-06-{i + 1:02d}")
        write_atom("proj", "state", f"state on day {i + 1:02d}")
    content = atom_path(brain).read_text()
    archive = atom_path(brain).with_name("state-archive.md")
    assert content.count("## 2026-") == ATOM_HISTORY_CAP
    assert "state on day 01" not in content
    assert "state on day 02" not in content
    assert "state on day 03" in content  # oldest survivor at cap 10 of 12
    assert archive.exists()
    assert "state on day 01" in archive.read_text()
    assert "## 2026-06-01" in archive.read_text()


def test_read_atom_returns_only_the_current_slice(brain, monkeypatch):
    from ytk.vault import read_atom, write_atom

    freeze(monkeypatch, "2026-07-28")
    write_atom("proj", "state", "old state")
    freeze(monkeypatch, "2026-07-29")
    write_atom("proj", "state", "current state")
    body = read_atom("proj", "state")
    assert "current state" in body
    assert "old state" not in body
    assert "## 2026-07-29" not in body  # heading stripped: round-trips into write_atom


def test_legacy_blob_becomes_history_on_first_new_write(brain, monkeypatch):
    from ytk.vault import SUPERSEDED_DIVIDER, write_atom

    path = atom_path(brain)
    path.parent.mkdir(parents=True)
    path.write_text(
        "---\ntype: atom\natom: state\nproject: proj\nupdated: 2026-07-01\n---\n\nlegacy state blob\n",
        encoding="utf-8",
    )
    freeze(monkeypatch, "2026-07-29")
    write_atom("proj", "state", "fresh state")
    content = path.read_text()
    assert content.index("fresh state") < content.index(SUPERSEDED_DIVIDER)
    assert "legacy state blob" in content  # first recoverable transition, baseline was 0
    assert "## 2026-07-01" in content  # dated from the old updated: stamp


def test_non_history_atoms_keep_overwrite(brain, monkeypatch):
    from ytk.vault import SUPERSEDED_DIVIDER, write_atom

    freeze(monkeypatch, "2026-07-28")
    write_atom("proj", "purpose", "why the project exists")
    freeze(monkeypatch, "2026-07-29")
    write_atom("proj", "purpose", "revised purpose")
    content = atom_path(brain, "purpose").read_text()
    assert "revised purpose" in content
    assert "why the project exists" not in content
    assert SUPERSEDED_DIVIDER not in content


def test_live_slice_cuts_history_for_indexing():
    from ytk.store import live_slice

    body = "## 2026-07-29\ncurrent\n\n<!-- superseded -->\n\n## 2026-07-28\nold\n"
    assert "current" in live_slice(body)
    assert "old" not in live_slice(body)
    assert live_slice("plain body, no divider") == "plain body, no divider"
