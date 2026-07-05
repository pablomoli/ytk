"""Shared test fixtures."""

import pytest


@pytest.fixture(autouse=True)
def _no_real_instagram_session(monkeypatch):
    """Keep tests hermetic: a developer's real session cookie (loaded into the
    process env by ytk.cli's load_dotenv) must never reach Instagram from a test."""
    monkeypatch.delenv("INSTAGRAM_SESSIONID", raising=False)
    monkeypatch.delenv("INSTAGRAM_PEER", raising=False)
