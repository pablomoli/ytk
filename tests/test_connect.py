"""The connect verb (#197 P6): candidates from the store below the dup
line, one-clause arguments from one Sonnet call, an ask the owner answers.
Writes nothing to the vault; fully stubbed — no model or store work here."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ytk import asks, connect, ledger
from ytk.capture import capture
from ytk.sdk import StructuredResult


@pytest.fixture
def conn():
    c = ledger.connect()
    yield c
    c.close()


def _item(conn, url="https://www.youtube.com/watch?v=abc123xyz00") -> int:
    return capture(conn, source="youtube", url=url, surface="cli", log=False).item_id


def _result(video_id, title, distance, url=None):
    return SimpleNamespace(
        video_id=video_id,
        title=title,
        url=url or f"https://y/{video_id}",
        uploader="u",
        date="",
        tags=[],
        thesis=f"thesis of {title}",
        summary="",
        distance=distance,
    )


def _stub_store(monkeypatch, results):
    monkeypatch.setattr("ytk.store.search_videos", lambda *a, **k: results)


def _stub_vault(monkeypatch, mapping):
    monkeypatch.setattr("ytk.vault.find_note_by_url", lambda url, thresh=0.0: mapping.get(url))


class TestFindCandidates:
    def test_band_filter_dedup_line_floor_and_cap(self, monkeypatch, tmp_path):
        results = [
            _result("dup", "same item again", distance=0.05),  # cosine 0.95 >= dup line
            _result("good1", "close neighbor", distance=0.25),  # 0.75
            _result("good2", "second neighbor", distance=0.35),  # 0.65
            _result("floor", "background noise", distance=0.50),  # 0.50 < floor
        ]
        _stub_store(monkeypatch, results)
        notes = {r.url: tmp_path / f"{r.video_id}-note.md" for r in results}
        _stub_vault(monkeypatch, notes)
        got = connect.find_candidates("q", exclude_media_id=None)
        assert [c.target for c in got] == ["good1-note", "good2-note"]
        assert got[0].cosine == pytest.approx(0.75)

    def test_excludes_self_and_unresolvable_notes(self, monkeypatch, tmp_path):
        results = [
            _result("me", "the note itself", distance=0.2),
            _result("orphan", "no note on disk", distance=0.25),
            _result("good", "resolvable", distance=0.3),
        ]
        _stub_store(monkeypatch, results)
        _stub_vault(monkeypatch, {"https://y/good": tmp_path / "good-note.md"})
        got = connect.find_candidates("q", exclude_media_id="me")
        assert [c.target for c in got] == ["good-note"]

    def test_store_down_returns_empty(self, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("chroma down")

        monkeypatch.setattr("ytk.store.search_videos", boom)
        assert connect.find_candidates("q", exclude_media_id=None) == []

    def test_cap_is_respected(self, monkeypatch, tmp_path):
        results = [_result(f"v{i}", f"t{i}", distance=0.2 + i * 0.01) for i in range(9)]
        _stub_store(monkeypatch, results)
        _stub_vault(monkeypatch, {r.url: tmp_path / f"{r.video_id}.md" for r in results})
        got = connect.find_candidates("q", exclude_media_id=None)
        assert len(got) == connect.MAX_CANDIDATES


def _argue_stub(monkeypatch, links, tokens=500):
    calls = []

    def fake(system, user, schema, **kw):
        calls.append({"system": system, "user": user, "kw": kw})
        return StructuredResult(
            data={"links": links},
            model=kw.get("model"),
            tokens=tokens,
            duration_ms=1200,
            usage=None,
        )

    monkeypatch.setattr("ytk.sdk.call_structured", fake)
    return calls


class TestPropose:
    def _candidates(self, monkeypatch, tmp_path, n=2):
        results = [_result(f"v{i}", f"t{i}", distance=0.25) for i in range(n)]
        _stub_store(monkeypatch, results)
        _stub_vault(monkeypatch, {r.url: tmp_path / f"v{i}-note.md" for i, r in enumerate(results)})

    def test_no_candidates_records_activity_and_no_ask(self, conn, monkeypatch):
        _stub_store(monkeypatch, [])
        item = _item(conn)
        assert connect.propose(conn, item, "thesis", "summary", exclude_media_id=None) is None
        row = conn.execute(
            "SELECT actor, action, reason FROM activity WHERE item_id = ? AND action = 'connect'",
            (item,),
        ).fetchone()
        assert row["actor"] == "connect"
        assert "no candidates" in row["reason"]
        assert asks._open_ask_id(conn, item) is None

    def test_argued_links_raise_the_connections_ask(self, conn, monkeypatch, tmp_path):
        self._candidates(monkeypatch, tmp_path)
        _argue_stub(
            monkeypatch,
            [{"target": "v0-note", "argument": "both build a grader wall"}],
        )
        item = _item(conn)
        ask_id = connect.propose(conn, item, "thesis", "summary", exclude_media_id=None)
        assert ask_id is not None
        ask = conn.execute("SELECT kind, proposal FROM asks WHERE id = ?", (ask_id,)).fetchone()
        assert ask["kind"] == "connections"
        prop = json.loads(ask["proposal"])
        assert prop["options"] == ["approve", "strike some", "none"]
        assert prop["links"] == [
            {
                "target": "v0-note",
                "target_title": "t0",
                "argument": "both build a grader wall",
            }
        ]
        act = conn.execute(
            "SELECT model, tokens, duration_ms FROM activity WHERE item_id = ? AND action = 'connect'",
            (item,),
        ).fetchone()
        assert act["tokens"] == 500
        assert act["duration_ms"] == 1200

    def test_model_cannot_invent_targets(self, conn, monkeypatch, tmp_path):
        self._candidates(monkeypatch, tmp_path)
        _argue_stub(
            monkeypatch,
            [
                {"target": "v0-note", "argument": "real"},
                {"target": "made-up-note", "argument": "hallucinated"},
            ],
        )
        item = _item(conn)
        ask_id = connect.propose(conn, item, "thesis", "summary", exclude_media_id=None)
        prop = json.loads(
            conn.execute("SELECT proposal FROM asks WHERE id = ?", (ask_id,)).fetchone()["proposal"]
        )
        assert [link["target"] for link in prop["links"]] == ["v0-note"]

    def test_model_declining_every_candidate_raises_no_ask(self, conn, monkeypatch, tmp_path):
        self._candidates(monkeypatch, tmp_path)
        _argue_stub(monkeypatch, [])
        item = _item(conn)
        assert connect.propose(conn, item, "thesis", "summary", exclude_media_id=None) is None
        assert asks._open_ask_id(conn, item) is None

    def test_argue_prompt_carries_no_rubric(self, conn, monkeypatch, tmp_path):
        """Connect is enricher-tier: the wall between it and the grader is
        the rubric file (same pin as the enricher's)."""
        self._candidates(monkeypatch, tmp_path)
        calls = _argue_stub(monkeypatch, [])
        item = _item(conn)
        connect.propose(conn, item, "thesis", "summary", exclude_media_id=None)
        joined = (calls[0]["system"] + calls[0]["user"]).lower()
        assert "rubric" not in joined


def _landed_item(conn, tmp_path, links):
    """An item at kept with a real note on disk, a connections ask carrying
    the given links, and no answer yet."""
    item = _item(conn)
    note = tmp_path / "the-note.md"
    note.write_text("---\nurl: https://y/x\n---\n\n## Thesis\nA thesis.\n\n## Commentary\nProse.\n")
    ledger.insert_activity(
        conn,
        item,
        actor="loop",
        action="keep",
        from_state="enriched",
        to_state="kept",
        output_ref=str(note),
    )
    ask_id = asks.raise_ask(
        conn,
        item,
        proposal={
            "kind": "connections",
            "why": "2 related notes argued",
            "options": ["approve", "strike some", "none"],
            "links": links,
        },
        actor="connect",
    )
    return item, note, ask_id


LINKS = [
    {"target": "a-note", "target_title": "A", "argument": "shares the grader wall"},
    {"target": "b-note", "target_title": "B", "argument": "same loop shape"},
]


class TestApplyLinks:
    def _answer(self, conn, item, ask_id, choice, text=None):
        asks.answer_ask(conn, ask_id, choice=choice, text=text)
        ledger.insert_activity(
            conn, item, actor="owner", action="answer", from_state="asking", to_state="answered"
        )

    def test_approve_snapshots_writes_and_records_connected(self, conn, tmp_path, monkeypatch):
        monkeypatch.setenv("YTK_SNAPSHOTS", str(tmp_path / "snaps"))
        item, note, ask_id = _landed_item(conn, tmp_path, LINKS)
        self._answer(conn, item, ask_id, "approve")
        connect.apply_links(conn, item)
        text = note.read_text()
        assert "- [[a-note]] — shares the grader wall" in text
        assert "- [[b-note]] — same loop shape" in text
        assert text.index("## Thesis") < text.index("## Connections") < text.index("## Commentary")
        assert ledger.item_state(conn, item) == "connected"
        snap = conn.execute("SELECT * FROM snapshots WHERE item_id = ?", (item,)).fetchone()
        assert snap is not None
        assert "## Connections" not in Path(snap["before_ref"]).read_text()
        row = conn.execute(
            "SELECT detail FROM activity WHERE item_id = ? AND action = 'connect-apply'", (item,)
        ).fetchone()
        assert [x["target"] for x in json.loads(row["detail"])["links"]] == ["a-note", "b-note"]

    def test_none_writes_nothing_and_returns_to_kept(self, conn, tmp_path):
        item, note, ask_id = _landed_item(conn, tmp_path, LINKS)
        before = note.read_text()
        self._answer(conn, item, ask_id, "none")
        connect.apply_links(conn, item)
        assert note.read_text() == before
        assert ledger.item_state(conn, item) == "kept"
        assert conn.execute("SELECT count(*) AS n FROM snapshots").fetchone()["n"] == 0

    def test_strike_some_keeps_only_survivors(self, conn, tmp_path, monkeypatch):
        monkeypatch.setenv("YTK_SNAPSHOTS", str(tmp_path / "snaps"))
        item, note, ask_id = _landed_item(conn, tmp_path, LINKS)
        self._answer(conn, item, ask_id, "strike some", text=json.dumps(["b-note"]))
        connect.apply_links(conn, item)
        text = note.read_text()
        assert "a-note" not in text
        assert "- [[b-note]] — same loop shape" in text
        assert ledger.item_state(conn, item) == "connected"

    def test_strike_all_behaves_as_none(self, conn, tmp_path):
        item, note, ask_id = _landed_item(conn, tmp_path, LINKS)
        self._answer(conn, item, ask_id, "strike some", text=json.dumps([]))
        connect.apply_links(conn, item)
        assert "## Connections" not in note.read_text()
        assert ledger.item_state(conn, item) == "kept"

    def test_missing_note_raises_into_the_loop_error_path(self, conn, tmp_path):
        item, note, ask_id = _landed_item(conn, tmp_path, LINKS)
        note.unlink()
        self._answer(conn, item, ask_id, "approve")
        with pytest.raises(RuntimeError):
            connect.apply_links(conn, item)
