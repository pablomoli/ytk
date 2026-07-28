"""reindex_vault scans the whole vault, minus named exclusions (#147).

The bug this pins: scan_dirs was an allowlist, so notes/, me/, study/, and
vision-board/ were never indexed and `ytk reindex` still reported success. An
allowlist fails silently every time a tree is added; these tests assert the
inverse policy -- everything is in scope unless it has a stated reason not to be.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ytk.vault import ReindexReport, scan_exclusion


@pytest.mark.parametrize(
    "rel",
    [
        "notes/ai/AI Hub.md",
        "notes/sound/Visualizing-Sound.md",
        "me/profile.md",
        "study/mastery.md",
        "study/sessions/2026-07-27-the-bitter-lesson.md",
        "vision-board/7 - Discovery.md",
        "projects/ytk/session-047-brief.md",
        "sources/web/the-bitter-lesson.md",
        "sources/instagram/whatever.md",
        "inbox/ideas.md",
        "inbox/memories/2026-05-30-mandalart.md",
        "wiki/hot.md",
        "hub/Hub.md",
        "tools/something.md",
    ],
)
def test_in_scope(rel: str) -> None:
    assert scan_exclusion(Path(rel)) is None, f"{rel} should be indexed"


@pytest.mark.parametrize(
    ("rel", "reason"),
    [
        # Another writer owns the id. Scanning duplicates or fights it.
        ("sources/youtube/some-video.md", "owned-elsewhere"),
        ("sources/screenshots/20260705-112225.md", "owned-elsewhere"),
        ("inbox/memos/2026-07-05-0335-remember-to.md", "owned-elsewhere"),
        # Deliberately unsearchable (#93).
        ("inbox/archived/old-thing.md", "not-searchable"),
        ("inbox/memories/index.md", "not-searchable"),
        ("inbox/memories/ytk/archived/stale-atom.md", "not-searchable"),
        # Indexing an index makes it the answer to everything.
        ("wiki/index.md", "generated"),
    ],
)
def test_excluded_with_reason(rel: str, reason: str) -> None:
    assert scan_exclusion(Path(rel)) == reason


def test_memos_are_excluded_because_memo_py_owns_them() -> None:
    """The regression that recursion would have introduced.

    memo.py upserts each memo as ``memo_<stem>``; a path-derived scan would add
    a *second* vector for the same text as ``note_inbox_memos_<stem>``. The old
    directory allowlist excluded memos only by omission -- nothing recorded why,
    so a recursive rewrite would have silently double-indexed them.
    """
    assert scan_exclusion(Path("inbox/memos/anything.md")) == "owned-elsewhere"


def test_prefix_match_does_not_leak_to_sibling_dirs() -> None:
    """`inbox/memos` must not swallow `inbox/memos-archive` or `notes/memos`."""
    assert scan_exclusion(Path("inbox/memos-archive/x.md")) is None
    assert scan_exclusion(Path("notes/memos/x.md")) is None


def test_report_accounts_for_every_file() -> None:
    """considered + excluded == total_md, so "0 indexed" can never hide a gap."""
    report = ReindexReport(
        indexed=3,
        unchanged=10,
        empty=1,
        excluded={"owned-elsewhere": 5, "generated": 1},
        total_md=20,
    )
    assert report.considered + sum(report.excluded.values()) == report.total_md
    summary = report.summary()
    assert "20 notes under the vault" in summary
    assert "3 indexed" in summary
    assert "5 owned-elsewhere" in summary
