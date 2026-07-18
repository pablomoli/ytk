"""Shared test fixtures."""

import os

import pytest

# Strip color-forcing vars BEFORE any ytk module import: ytk.cli builds its
# rich Console at import time, and under FORCE_COLOR (tmux sessions) rich
# injects highlight codes inside tokens like dates in captured CliRunner
# output — splitting the substrings CLI tests assert on.
for _var in ("FORCE_COLOR", "CLICOLOR_FORCE", "COLORTERM"):
    os.environ.pop(_var, None)


@pytest.fixture(autouse=True)
def _no_real_instagram_session(monkeypatch):
    """Keep tests hermetic: a developer's real session cookie (loaded into the
    process env by ytk.cli's load_dotenv) must never reach Instagram from a test."""
    monkeypatch.delenv("INSTAGRAM_SESSIONID", raising=False)
    monkeypatch.delenv("INSTAGRAM_PEER", raising=False)


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
