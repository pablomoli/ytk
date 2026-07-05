"""sdk.structured: dual-path transport contract for all cheap classifiers.

No API key -> straight to the Agent SDK. Key present -> direct API first,
SDK only on API failure. Input truncated before either path."""

from __future__ import annotations

from pydantic import BaseModel

from ytk import sdk


class Toy(BaseModel):
    label: str


def test_no_key_uses_sdk(monkeypatch):
    calls = []
    monkeypatch.setattr(sdk, "run_structured", lambda *a, **k: calls.append(a) or {"label": "x"})
    monkeypatch.setattr(sdk, "_structured_via_api", lambda *a: (_ for _ in ()).throw(AssertionError("must not be called")))

    out = sdk.structured("sys", "user", Toy)
    assert out == Toy(label="x")
    assert len(calls) == 1


def test_key_prefers_api(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setattr(sdk, "_structured_via_api", lambda *a: {"label": "api"})
    monkeypatch.setattr(sdk, "run_structured", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not be called")))

    assert sdk.structured("sys", "user", Toy).label == "api"


def test_api_failure_falls_back_to_sdk(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setattr(sdk, "_structured_via_api", lambda *a: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(sdk, "run_structured", lambda *a, **k: {"label": "fallback"})

    assert sdk.structured("sys", "user", Toy).label == "fallback"


def test_input_truncated(monkeypatch):
    seen = {}
    def fake(system, user, schema, model=None):
        seen["user"] = user
        return {"label": "x"}
    monkeypatch.setattr(sdk, "run_structured", fake)

    sdk.structured("sys", "u" * 50_000, Toy, max_input_chars=100)
    assert len(seen["user"]) == 100
