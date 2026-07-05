"""Shared test fixtures."""

import pytest


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
