"""Layer 3 of the linking plan: nearby notes for any note, and the owner's
tap that links one through the connections apply path. Store, model and
vault are all stubbed or under tmp."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ytk import asks, connect, ledger, notes
from ytk.sdk import StructuredResult


@pytest.fixture
def conn():
    c = ledger.connect()
    yield c
    c.close()


@pytest.fixture(autouse=True)
def brain(tmp_path, monkeypatch):
    b = tmp_path / "brain"
    (b / "sources" / "instagram").mkdir(parents=True)
    monkeypatch.setattr("ytk.vault._get_brain_path", lambda: b)
    monkeypatch.setenv("YTK_SNAPSHOTS", str(tmp_path / "snaps"))
    monkeypatch.setattr("ytk.store.upsert_doc", lambda *a: None)
    return b


def _note(brain: Path, rel: str, *, url: str | None = None, body: str = "") -> Path:
    path = brain / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    fm = "---\n" + (f"url: {url}\n" if url else "") + f"title: {path.stem} title\n---\n"
    text = body or (f"\n## Thesis\nThesis of {path.stem}.\n\n## Summary\nSummary of {path.stem}.\n")
    path.write_text(fm + text)
    return path


def _memory(path: Path, distance: float):
    return SimpleNamespace(
        type="memory",
        doc_id=path.stem,
        title=path.stem,
        excerpt="excerpt",
        source=str(path),
        distance=distance,
    )


def _space(monkeypatch, own: Path, hits: list[tuple[Path, float]]):
    """The note has a stored position; its doc-to-doc hits are `hits`."""
    monkeypatch.setattr("ytk.store.note_vector", lambda **k: [1.0, 0.0])
    monkeypatch.setattr(
        "ytk.store.search_vector",
        lambda vec, n=5: [_memory(own, 0.0)] + [_memory(p, d) for p, d in hits],
    )


def _argue(monkeypatch, links, calls=None):
    def fake(system, user, schema, **kw):
        if calls is not None:
            calls.append(user)
        return StructuredResult(
            data={"links": links}, model=kw.get("model"), tokens=300, duration_ms=900, usage=None
        )

    monkeypatch.setattr("ytk.sdk.call_structured", fake)


def _grandfathered(conn, brain: Path, note: Path) -> int:
    rel = str(note.relative_to(brain))
    item = ledger.insert_item(
        conn,
        source="instagram",
        url=f"note://{rel}",
        provenance="grandfathered",
        payload_ref=rel,
    )
    assert item is not None
    ledger.insert_activity(
        conn, item, actor="loop", action="grandfather", to_state="kept-unlabeled"
    )
    return item


class TestLinkedTargets:
    def test_wikilinks_by_basename_and_embeds_ignored(self):
        text = "![[abc-thumb.jpg]]\n- [[a-note]] — x\nsee [[sources/web/b-note|B]] and [[c#h]]"
        assert connect.linked_targets(text) == {"a-note", "b-note", "c"}

    def test_embed_at_start_of_text_is_ignored(self):
        assert connect.linked_targets("![[x.png]]") == set()


class TestNearby:
    def test_band_self_and_already_linked_are_excluded(self, monkeypatch, brain):
        own = _note(
            brain, "sources/instagram/own.md", body="\n## Thesis\nT.\n\n- [[linked]] — before\n"
        )
        linked = _note(brain, "sources/instagram/linked.md")
        near = _note(brain, "sources/instagram/near.md")
        far = _note(brain, "sources/instagram/far.md")
        dup = _note(brain, "sources/instagram/dup.md")
        _space(monkeypatch, own, [(linked, 0.2), (near, 0.3), (far, 0.6), (dup, 0.05)])
        got = connect.nearby(own)
        assert [c.target for c in got] == ["near"]
        assert got[0].cosine == pytest.approx(0.7)
        assert got[0].via == connect.NOTE_LABEL

    def test_already_linked_does_not_eat_the_cap(self, monkeypatch, brain):
        links = "".join(f"- [[l{i}]] — x\n" for i in range(5))
        own = _note(brain, "sources/instagram/own.md", body="\n## Thesis\nT.\n\n" + links)
        hits = [(_note(brain, f"sources/instagram/l{i}.md"), 0.2) for i in range(5)]
        hits += [(_note(brain, f"sources/instagram/n{i}.md"), 0.3) for i in range(5)]
        _space(monkeypatch, own, hits)
        assert [c.target for c in connect.nearby(own)] == [f"n{i}" for i in range(5)]

    def test_unlinkable_paths_are_never_nearby(self, monkeypatch, brain):
        own = _note(brain, "sources/instagram/own.md")
        listing = _note(brain, "wiki/index.md")
        brief = _note(brain, "projects/ytk/session-090-brief.md")
        near = _note(brain, "study/near.md")
        _space(monkeypatch, own, [(listing, 0.2), (brief, 0.2), (near, 0.3)])
        assert [c.target for c in connect.nearby(own)] == ["near"]

    def test_youtube_note_reads_its_vector_by_video_id(self, monkeypatch, brain):
        own = _note(
            brain, "sources/youtube/v.md", url="https://www.youtube.com/watch?v=abcdefghijk"
        )
        asked = {}

        def fake(**k):
            asked.update(k)
            return

        monkeypatch.setattr("ytk.store.note_vector", fake)
        assert connect.nearby(own) == []
        assert asked == {"source_path": str(own), "video_id": "abcdefghijk"}

    def test_no_vector_and_store_down_are_empty(self, monkeypatch, brain):
        own = _note(brain, "sources/instagram/own.md")
        monkeypatch.setattr("ytk.store.note_vector", lambda **k: None)
        assert connect.nearby(own) == []

        def down(**k):
            raise ConnectionError("chroma down")

        monkeypatch.setattr("ytk.store.note_vector", down)
        assert connect.nearby(own) == []


class TestAddConnections:
    def test_no_section_lands_after_thesis(self, tmp_path):
        p = tmp_path / "n.md"
        p.write_text("---\n---\n\n## Thesis\nT.\n\n## Summary\nS.\n")
        notes.add_connections(p, [("a", "why a")])
        text = p.read_text()
        assert text.index("## Thesis") < text.index("## Connections") < text.index("## Summary")

    def test_merge_keeps_other_writers_lines_and_replaces_same_target(self, tmp_path):
        p = tmp_path / "n.md"
        p.write_text(
            "## Thesis\nT.\n\n## Connections\n- [[a]] — old a\n- [[b]] — b stays\n"
            "a hand-written line\n\n## Summary\nS.\n"
        )
        notes.add_connections(p, [("a", "new a"), ("c", "why c")])
        text = p.read_text()
        assert text.count("## Connections") == 1
        section = text.split("## Connections\n")[1].split("\n## ")[0]
        assert section.splitlines() == [
            "- [[a]] — new a",
            "- [[b]] — b stays",
            "a hand-written line",
            "- [[c]] — why c",
        ]
        assert "why c\n\n## Summary" in text
        assert text.endswith("## Summary\nS.\n")

    def test_merge_is_idempotent(self, tmp_path):
        p = tmp_path / "n.md"
        p.write_text("## Thesis\nT.\n\n## Connections\n- [[a]] — x\n")
        notes.add_connections(p, [("b", "y")])
        once = p.read_text()
        notes.add_connections(p, [("b", "y")])
        assert p.read_text() == once
        assert once.endswith("- [[b]] — y\n")


class TestItemForNote:
    def test_curator_landing_grandfathered_url_and_none(self, conn, brain):
        landed = _note(brain, "sources/instagram/landed.md")
        item = ledger.insert_item(conn, source="instagram", url="https://i/landed")
        assert item is not None
        ledger.insert_activity(
            conn, item, actor="loop", action="keep", to_state="kept", output_ref=str(landed)
        )
        assert ledger.item_for_note(conn, landed, brain) == item

        old = _note(brain, "sources/instagram/old.md")
        old_item = _grandfathered(conn, brain, old)
        assert ledger.item_for_note(conn, old, brain) == old_item

        by_url = _note(brain, "sources/web/by-url.md", url="https://w/by-url")
        item_url = ledger.insert_item(conn, source="web", url="https://w/by-url")
        assert ledger.item_for_note(conn, by_url, brain) == item_url

        stray = _note(brain, "sources/journal/stray.md")
        assert ledger.item_for_note(conn, stray, brain) is None


class TestLinkNearby:
    def _setup(self, conn, monkeypatch, brain):
        own = _note(brain, "sources/instagram/own.md")
        near = _note(brain, "sources/instagram/near.md")
        _space(monkeypatch, own, [(near, 0.3)])
        return own, _grandfathered(conn, brain, own)

    def test_tap_argues_writes_reindexes_and_records_the_owner(self, conn, monkeypatch, brain):
        own, item = self._setup(conn, monkeypatch, brain)
        calls: list[str] = []
        _argue(monkeypatch, [{"target": "near", "argument": "both grow coral"}], calls)
        reindexed = []
        monkeypatch.setattr(
            "ytk.notes.reindex_connected", lambda p: reindexed.append(p) or "re-indexed"
        )

        out = connect.link_nearby(conn, own, "near", surface="hub")

        assert out.argument == "both grow coral" and out.cosine == pytest.approx(0.7)
        assert "- [[near]] — both grow coral" in own.read_text()
        assert reindexed == [own]
        assert len(calls) == 1 and "target=near" in calls[0] and "Thesis of own." in calls[0]
        assert conn.execute("SELECT count(*) AS n FROM snapshots").fetchone()["n"] == 1
        rows = conn.execute(
            "SELECT actor, action, to_state, detail, reason FROM activity"
            " WHERE item_id = ? ORDER BY id",
            (item,),
        ).fetchall()
        assert [(r["actor"], r["action"]) for r in rows] == [
            ("loop", "grandfather"),
            ("connect", "connect"),
            ("owner", "nearby-link"),
        ]
        owner = json.loads(rows[-1]["detail"])
        assert owner["surface"] == "hub" and owner["target"] == "near"
        assert owner["argument"] == "both grow coral" and owner["reindex"] == "re-indexed"
        assert json.loads(rows[1]["detail"])["trigger"] == "nearby"
        # A link on an old note is an edit, not a lifecycle step.
        assert ledger.item_state(conn, item) == "kept-unlabeled"
        assert conn.execute("SELECT count(*) AS n FROM asks").fetchone()["n"] == 0
        lease = conn.execute("SELECT lease_until FROM items WHERE id = ?", (item,)).fetchone()
        assert lease["lease_until"] is None

    def test_written_link_leaves_the_nearby_list(self, conn, monkeypatch, brain):
        own, _ = self._setup(conn, monkeypatch, brain)
        _argue(monkeypatch, [{"target": "near", "argument": "x"}])
        connect.link_nearby(conn, own, "near", surface="hub")
        assert connect.nearby(own) == []

    def test_note_without_an_item_is_refused_and_untouched(self, conn, monkeypatch, brain):
        own = _note(brain, "sources/journal/own.md")
        near = _note(brain, "sources/instagram/near.md")
        _space(monkeypatch, own, [(near, 0.3)])
        before = own.read_text()
        with pytest.raises(connect.NearbyRefused, match="no ledger item"):
            connect.link_nearby(conn, own, "near", surface="hub")
        assert own.read_text() == before
        assert conn.execute("SELECT count(*) AS n FROM activity").fetchone()["n"] == 0

    def test_target_no_longer_nearby_is_refused(self, conn, monkeypatch, brain):
        own, _ = self._setup(conn, monkeypatch, brain)
        with pytest.raises(connect.NearbyRefused, match="not among"):
            connect.link_nearby(conn, own, "somewhere-else", surface="hub")

    def test_unargued_tap_writes_nothing_but_records_the_judgment(self, conn, monkeypatch, brain):
        own, item = self._setup(conn, monkeypatch, brain)
        before = own.read_text()
        _argue(monkeypatch, [])
        out = connect.link_nearby(conn, own, "near", surface="hub")
        assert out.argument is None
        assert own.read_text() == before
        row = conn.execute(
            "SELECT reason, output_ref FROM activity WHERE item_id = ? AND action = 'nearby-link'",
            (item,),
        ).fetchone()
        assert "nothing written" in row["reason"] and row["output_ref"] is None

    def test_failed_argue_releases_the_lease_and_records_the_error(self, conn, monkeypatch, brain):
        own, item = self._setup(conn, monkeypatch, brain)

        def boom(*a, **k):
            raise RuntimeError("sdk down")

        monkeypatch.setattr("ytk.sdk.call_structured", boom)
        with pytest.raises(RuntimeError):
            connect.link_nearby(conn, own, "near", surface="hub")
        row = conn.execute(
            "SELECT detail FROM activity WHERE item_id = ? AND action = 'nearby-link'", (item,)
        ).fetchone()
        assert "sdk down" in json.loads(row["detail"])["error"]
        lease = conn.execute("SELECT lease_until FROM items WHERE id = ?", (item,)).fetchone()
        assert lease["lease_until"] is None

    def test_item_the_loop_holds_is_refused(self, conn, monkeypatch, brain):
        own, item = self._setup(conn, monkeypatch, brain)
        from ytk import loop

        assert loop.lease(conn, item)
        with pytest.raises(connect.NearbyRefused, match="loop"):
            connect.link_nearby(conn, own, "near", surface="hub")


class TestAskApplyKeepsTapLinks:
    def test_connections_ask_applied_after_a_tap_merges(self, conn, brain):
        own = _note(brain, "sources/instagram/own.md")
        item = ledger.insert_item(conn, source="instagram", url="https://i/own")
        assert item is not None
        ledger.insert_activity(
            conn, item, actor="loop", action="keep", to_state="kept", output_ref=str(own)
        )
        notes.add_connections(own, [("tapped", "the owner's tap")])
        ask_id = asks.raise_ask(
            conn,
            item,
            proposal={
                "kind": "connections",
                "why": "1",
                "options": ["approve"],
                "links": [{"target": "asked", "target_title": "A", "argument": "from the ask"}],
            },
        )
        assert ask_id is not None
        asks.answer_ask(conn, ask_id, choice="approve")
        connect.apply_links(conn, item)
        text = own.read_text()
        assert "- [[tapped]] — the owner's tap" in text
        assert "- [[asked]] — from the ask" in text


class TestApi:
    def test_nearby_lists_neighbours_and_linkability(self, conn, monkeypatch, brain):
        from fastapi.testclient import TestClient

        from ytk.ui.server import app

        own = _note(brain, "sources/instagram/own.md")
        near = _note(brain, "sources/instagram/near.md")
        _space(monkeypatch, own, [(near, 0.3)])
        client = TestClient(app)
        rel = "brain/sources/instagram/own.md"
        body = client.get("/api/nearby", params={"note": rel}).json()
        assert body["linkable"] is False
        assert body["nearby"] == [
            {
                "target": "near",
                "title": "near title",
                "cosine": 0.7,
                "path": "brain/sources/instagram/near.md",
            }
        ]
        _grandfathered(conn, brain, own)
        assert client.get("/api/nearby", params={"note": rel}).json()["linkable"] is True

    def test_link_refusals_are_409_and_escapes_are_400(self, monkeypatch, brain):
        from fastapi.testclient import TestClient

        from ytk.ui.server import app

        own = _note(brain, "sources/journal/own.md")
        _space(monkeypatch, own, [])
        client = TestClient(app)
        resp = client.post(
            "/api/nearby/link", json={"note": "brain/sources/journal/own.md", "target": "x"}
        )
        assert resp.status_code == 409 and "no ledger item" in resp.json()["detail"]
        resp = client.get("/api/nearby", params={"note": "../etc/passwd.md"})
        assert resp.status_code == 400

    def test_link_returns_the_clause(self, conn, monkeypatch, brain):
        from fastapi.testclient import TestClient

        from ytk.ui.server import app

        own = _note(brain, "sources/instagram/own.md")
        near = _note(brain, "sources/instagram/near.md")
        _space(monkeypatch, own, [(near, 0.3)])
        _grandfathered(conn, brain, own)
        _argue(monkeypatch, [{"target": "near", "argument": "same reef"}])
        resp = TestClient(app).post(
            "/api/nearby/link", json={"note": "brain/sources/instagram/own.md", "target": "near"}
        )
        assert resp.status_code == 200
        assert resp.json()["argument"] == "same reef"
