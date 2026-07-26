"""Shared test fixtures."""

import os
import traceback

import pytest

# Strip color-forcing vars BEFORE any ytk module import: ytk.cli builds its
# rich Console at import time, and under FORCE_COLOR (tmux sessions) rich
# injects highlight codes inside tokens like dates in captured CliRunner
# output — splitting the substrings CLI tests assert on.
for _var in ("FORCE_COLOR", "CLICOLOR_FORCE", "COLORTERM"):
    os.environ.pop(_var, None)

# test_test_hygiene runs throwaway suites in-process to prove the guards below
# actually fail a test, rather than only asserting they were installed.
pytest_plugins = ["pytester"]


@pytest.fixture(autouse=True)
def _no_real_instagram_session(monkeypatch):
    """Keep tests hermetic: a developer's real session cookie (loaded into the
    process env by ytk.cli's load_dotenv) must never reach Instagram from a test."""
    monkeypatch.delenv("INSTAGRAM_SESSIONID", raising=False)
    monkeypatch.delenv("INSTAGRAM_PEER", raising=False)


@pytest.fixture(autouse=True)
def _isolate_config(tmp_path_factory, monkeypatch):
    """Point every test at a throwaway config, never the developer's real one.

    ytk.config.load_config falls back to ~/.ytk/config.yaml, so an unstubbed
    code path under test reads live credentials and source settings: that is
    what turned a missing test stub into a real TikTok browser session (#114).
    Tests needing a config of their own still set YTK_CONFIG themselves.
    """
    monkeypatch.setenv("YTK_CONFIG", str(tmp_path_factory.mktemp("cfg") / "config.yaml"))


@pytest.fixture(autouse=True)
def _no_browser(monkeypatch):
    """Make it impossible for a unit test to drive a real browser.

    Raising alone is not enough: hub.refresh_sources catches per-source
    exceptions by design, so a guard that only raised would be swallowed and
    the test would still report green while a browser had already launched
    (#114). Reaches are recorded and failed at teardown instead, outside any
    try/except in the code under test.

    Yields the reach log, so a test deliberately tripping the guard can assert
    on it and clear it; the log is per-test state rather than a module global.
    """
    reaches: list[str] = []
    try:
        from playwright import sync_api
    except ImportError:  # nothing to guard against
        yield reaches
        return

    def _blocked(*args, **kwargs):
        reaches.append("".join(traceback.format_stack(limit=12)))
        raise RuntimeError("blocked: test reached sync_playwright()")

    monkeypatch.setattr(sync_api, "sync_playwright", _blocked)
    yield reaches
    if reaches:
        stacks = "\n".join(reaches)
        pytest.fail(f"test reached Playwright; stub the source that got there:\n{stacks}")


# Offline stand-ins for every seam named in hub.PULL_SEAMS, matching each real
# puller's return shape. A seam with no entry here is a hard failure rather
# than an untouched attribute that still points at the live implementation.
_SEAM_STUBS = {
    "IG_PULL": lambda: lambda state: 0,
    "TT_PULL": lambda: lambda state: 0,
    "REDDIT_PULL": lambda: lambda state: 0,
    "YT_FETCH": lambda: list,
    "YT_IS_PROCESSED": lambda: lambda vid: False,
    "PIN_FETCH": lambda: list,
    "IM_FETCH": lambda: list,
}


def seam_coverage_error(hub_mod) -> str | None:
    """Why the hub's sources cannot all be stubbed offline, or None if they can.

    Split out of the fixture so the drift check is itself testable.
    """
    missing = set(hub_mod.PULL_SOURCES) - set(hub_mod.PULL_SEAMS)
    if missing:
        return (
            f"hub.PULL_SOURCES gained {sorted(missing)} with no hub.PULL_SEAMS entry: "
            "register the seam(s) it pulls through so tests can stub it offline"
        )
    for source, seams in sorted(hub_mod.PULL_SEAMS.items()):
        for name in seams:
            if name not in _SEAM_STUBS:
                return (
                    f"seam {name!r} (source {source!r}) has no offline stub in "
                    "tests/conftest.py::_SEAM_STUBS"
                )
    return None


@pytest.fixture
def stub_pullers(monkeypatch):
    """Neutralise every discovery source hub.refresh_sources can route through.

    Driven off hub.PULL_SEAMS so the stub set cannot drift behind the source
    list; individual tests still override single seams afterwards, since a
    test's own monkeypatch runs after fixture setup.
    """
    import ytk.ui.hub as hub

    problem = seam_coverage_error(hub)
    if problem:
        pytest.fail(problem)
    for seams in hub.PULL_SEAMS.values():
        for name in seams:
            monkeypatch.setattr(hub, name, _SEAM_STUBS[name]())


@pytest.fixture(autouse=True)
def _no_direct_api(monkeypatch):
    """Force sdk.structured onto its (mocked) SDK path: a real ANTHROPIC_API_KEY
    in the developer's env must never make a test hit the network."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


@pytest.fixture(autouse=True)
def _pin_v1_epoch(monkeypatch):
    """Pin unit tests to the v1 epoch regardless of the production default.

    Both epochs are exercised explicitly where it matters (test_store_epochs
    overrides this); everything else would otherwise follow production's
    EMBEDDING_EPOCH and silently start loading Qwen3 onto MPS mid-suite the
    day the default flips."""
    import ytk.store as store

    monkeypatch.setattr(store, "EMBEDDING_EPOCH", "v1")


@pytest.fixture(autouse=True)
def _enable_visual_index(monkeypatch):
    """Keep the production visual circuit breaker out of unit-test behavior.

    Tests that exercise disabled mode override the environment explicitly.
    Marking the probe healthy also prevents unrelated unit tests from probing
    the developer's live Chroma store.
    """
    monkeypatch.setenv("YTK_VISUAL_INDEX", "on")
    import ytk.store as store

    monkeypatch.setattr(store, "_VISUAL_PROBE", True)


@pytest.fixture(autouse=True)
def _close_chroma_clients_between_tests():
    """Release Rust/SQLite handles before pytest removes each tmp store.

    Chroma caches every PersistentClient system process-wide. The store tests
    intentionally create many isolated tmp databases; without explicit close,
    the suite eventually exhausts SQLite handles and cascades with code 14.
    """
    import ytk.store as store

    yield

    client = getattr(store, "_client", None)
    if client is not None:
        try:
            client.close()
        finally:
            store._client = None
