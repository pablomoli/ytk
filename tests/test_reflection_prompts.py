"""The reflection prompting layer (#98): stable flagging, answer store, API."""

from fastapi.testclient import TestClient

from ytk.ui import hub
from ytk.ui.server import app

client = TestClient(app)


def test_reflection_question_is_deterministic_and_sparse():
    urls = [f"https://example.com/v/{i}" for i in range(400)]
    first = [hub.reflection_question(u) for u in urls]
    second = [hub.reflection_question(u) for u in urls]
    assert first == second
    flagged = [q for q in first if q]
    # md5 % 10 over 400 urls: expect ~40, generously bounded
    assert 15 <= len(flagged) <= 80
    assert set(flagged) <= set(hub.REFLECTION_POOL)


def test_answer_store_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(hub, "REFLECTIONS_PATH", tmp_path / "reflections.json")
    hub.store_reflection_answer("https://a", "because it maps to my thesis")
    assert hub.reflection_answers() == {"https://a": "because it maps to my thesis"}
    hub.store_reflection_answer("https://a", "")
    assert hub.reflection_answers() == {}


def test_reflect_answer_endpoint(tmp_path, monkeypatch):
    monkeypatch.setattr(hub, "REFLECTIONS_PATH", tmp_path / "reflections.json")
    resp = client.post("/api/reflect-answer", json={"url": "https://a", "answer": "words"})
    assert resp.status_code == 200 and resp.json()["stored"] is True
    assert hub.reflection_answers()["https://a"] == "words"
    resp = client.post("/api/reflect-answer", json={"url": "https://a", "answer": " "})
    assert resp.json()["stored"] is False
    assert hub.reflection_answers() == {}


def test_queue_api_carries_reflection_fields(tmp_path, monkeypatch):
    from ytk import reels

    monkeypatch.setattr(hub, "REFLECTIONS_PATH", tmp_path / "reflections.json")
    flagged_url = next(
        u for u in (f"https://example.com/v/{i}" for i in range(200)) if hub.reflection_question(u)
    )
    item = reels.ReelItem(url=flagged_url, author="a", shared_at="", preview_url="", source="web")
    monkeypatch.setattr(hub, "queue_items", lambda: [item])
    hub.store_reflection_answer(flagged_url, "an answer")
    data = client.get("/api/queue").json()["items"][0]
    assert data["reflection_question"] in hub.REFLECTION_POOL
    assert data["reflection_answered"] is True
