"""Tests for the suite's own safety rails (#114).

A missing test stub once let `pytest` open a real TikTok browser session and
scroll forever. These cover the two guards that make that class of bug loud:
the seam registry that stops the stub list drifting behind the source list,
and the browser guard that fails any test reaching Playwright.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import _SEAM_STUBS, seam_coverage_error

REPO_ROOT = Path(__file__).resolve().parent.parent


class _FakeHub:
    def __init__(self, sources, seams):
        self.PULL_SOURCES = frozenset(sources)
        self.PULL_SEAMS = seams


def test_every_pull_source_is_stubbable():
    import ytk.ui.hub as hub

    assert seam_coverage_error(hub) is None


def test_every_registered_seam_exists_on_the_hub():
    import ytk.ui.hub as hub

    for source, seams in hub.PULL_SEAMS.items():
        for name in seams:
            assert hasattr(hub, name), f"{source} names a seam {name!r} the hub does not define"


def test_a_new_source_without_a_seam_fails_the_suite():
    """The acceptance criterion: adding a source breaks tests until stubbed."""
    hub = _FakeHub(
        sources={"instagram", "carrier_pigeon"},
        seams={"instagram": ("IG_PULL",)},
    )

    problem = seam_coverage_error(hub)

    assert problem is not None
    assert "carrier_pigeon" in problem


def test_a_seam_without_an_offline_stub_fails_the_suite():
    hub = _FakeHub(sources={"instagram"}, seams={"instagram": ("PIGEON_PULL",)})

    problem = seam_coverage_error(hub)

    assert problem is not None
    assert "PIGEON_PULL" in problem


def test_every_stub_matches_a_registered_seam():
    """Stubs and seams stay in step in both directions, so removing a source
    does not leave a stub behind that quietly stops matching anything."""
    import ytk.ui.hub as hub

    registered = {name for seams in hub.PULL_SEAMS.values() for name in seams}
    assert set(_SEAM_STUBS) == registered


def test_browser_guard_blocks_sync_playwright(_no_browser):
    from playwright import sync_api

    with pytest.raises(RuntimeError, match="blocked"):
        sync_api.sync_playwright()

    # The reach was recorded for teardown; clear it so this test, which
    # tripped the guard deliberately, is not itself failed by it.
    assert _no_browser
    _no_browser.clear()


def test_browser_guard_fails_a_test_that_swallows_the_error(pytester):
    """The guard must survive the swallow that hid #114 for so long.

    hub.refresh_sources catches per-source exceptions, so a guard that only
    raised would leave the test green. Reaching Playwright has to fail the
    test even when nothing propagates out of the call.
    """
    pytester.makeconftest(f"""
        import sys
        sys.path.insert(0, {str(REPO_ROOT)!r})
        from tests.conftest import _no_browser  # noqa: F401
    """)
    pytester.makepyfile("""
        def test_swallows():
            from playwright import sync_api
            try:
                sync_api.sync_playwright()
            except Exception:
                pass  # exactly what refresh_sources does
            assert True
    """)

    result = pytester.runpytest("-p", "no:cacheprovider")

    # The body passed; the guard fails it during teardown, which pytest
    # reports as an error rather than a failure.
    result.assert_outcomes(passed=1, errors=1)
    result.stdout.fnmatch_lines(["*reached Playwright*"])
