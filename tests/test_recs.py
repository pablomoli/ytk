"""Tests for ytk.recs — recommendation resolution + growing deduped store.

All network is mocked by monkeypatching the two transport functions
(`_http_get` / `_http_post_json`); no test hits the real network. The Haiku
extractor is tested against a monkeypatched `run_structured`.
"""

import json

import pytest

from ytk import recs


# --------------------------------------------------------------------------- #
# Fake HTTP transports
# --------------------------------------------------------------------------- #


class FakeGet:
    """Routes GET urls to canned JSON by substring match. Unmatched -> None."""

    def __init__(self, routes: dict):
        self.routes = routes
        self.calls: list[str] = []

    def __call__(self, url, headers=None):
        self.calls.append(url)
        for needle, payload in self.routes.items():
            if needle in url:
                return payload
        return None


class FakePost:
    def __init__(self, payload):
        self.payload = payload
        self.calls: list[tuple] = []

    def __call__(self, url, payload, headers=None):
        self.calls.append((url, payload))
        return self.payload


@pytest.fixture
def store_path(tmp_path):
    return tmp_path / "recs.json"


# --------------------------------------------------------------------------- #
# Movie resolver (TMDb)
# --------------------------------------------------------------------------- #


class TestResolveMovie:
    def _routes(self):
        return {
            "/search/movie": {
                "results": [
                    {
                        "id": 438631,
                        "title": "Dune",
                        "release_date": "2021-09-15",
                        "poster_path": "/dune.jpg",
                        "vote_average": 7.8,
                        "overview": "Paul Atreides.",
                    }
                ]
            },
            "/movie/438631/credits": {
                "crew": [
                    {"job": "Editor", "name": "Joe Walker"},
                    {"job": "Director", "name": "Denis Villeneuve"},
                ]
            },
        }

    def test_happy_path(self, monkeypatch):
        monkeypatch.setattr(recs, "_http_get", FakeGet(self._routes()))
        out = recs.resolve("movie", "Dune", year=2021)
        assert out["canonical_key"] == "tmdb:movie:438631"
        assert out["kind"] == "movie"
        assert out["title"] == "Dune"
        assert out["year"] == 2021
        assert out["creator"] == "Denis Villeneuve"
        assert out["poster"] == "https://image.tmdb.org/t/p/w342/dune.jpg"
        assert out["rating"] == 7.8
        assert out["overview"] == "Paul Atreides."
        assert out["external_url"] == "https://www.themoviedb.org/movie/438631"

    def test_no_results_returns_none(self, monkeypatch):
        monkeypatch.setattr(recs, "_http_get", FakeGet({"/search/movie": {"results": []}}))
        assert recs.resolve("movie", "Nonexistent") is None

    def test_network_failure_returns_none(self, monkeypatch):
        monkeypatch.setattr(recs, "_http_get", FakeGet({}))  # everything -> None
        assert recs.resolve("movie", "Dune") is None

    def test_null_poster(self, monkeypatch):
        routes = self._routes()
        routes["/search/movie"]["results"][0]["poster_path"] = None
        monkeypatch.setattr(recs, "_http_get", FakeGet(routes))
        assert recs.resolve("movie", "Dune")["poster"] is None

    def test_prefers_bearer_token(self, monkeypatch):
        fake = FakeGet(self._routes())
        monkeypatch.setattr(recs, "_http_get", fake)
        monkeypatch.setenv("TMDB_READ_TOKEN", "bearer-xyz")
        recs.resolve("movie", "Dune")
        # api_key must not leak into the URL when a bearer token is present
        assert all("api_key" not in c for c in fake.calls)


# --------------------------------------------------------------------------- #
# Show resolver (TMDb)
# --------------------------------------------------------------------------- #


class TestResolveShow:
    def test_happy_path(self, monkeypatch):
        routes = {
            "/search/tv": {
                "results": [
                    {
                        "id": 1396,
                        "name": "Breaking Bad",
                        "first_air_date": "2008-01-20",
                        "poster_path": "/bb.jpg",
                        "vote_average": 8.9,
                        "overview": "Chemistry teacher.",
                    }
                ]
            }
        }
        monkeypatch.setattr(recs, "_http_get", FakeGet(routes))
        out = recs.resolve("show", "Breaking Bad")
        assert out["canonical_key"] == "tmdb:tv:1396"
        assert out["kind"] == "show"
        assert out["year"] == 2008
        assert out["creator"] is None
        assert out["external_url"] == "https://www.themoviedb.org/tv/1396"

    def test_miss(self, monkeypatch):
        monkeypatch.setattr(recs, "_http_get", FakeGet({"/search/tv": {"results": []}}))
        assert recs.resolve("show", "x") is None


# --------------------------------------------------------------------------- #
# Anime + manga resolvers (AniList)
# --------------------------------------------------------------------------- #


class TestResolveAnime:
    def test_happy_path(self, monkeypatch):
        payload = {
            "data": {
                "Media": {
                    "id": 154587,
                    "title": {"romaji": "Sousou no Frieren", "english": "Frieren"},
                    "coverImage": {"large": "https://img/frieren.jpg"},
                    "seasonYear": 2023,
                    "averageScore": 92,
                    "siteUrl": "https://anilist.co/anime/154587",
                    "studios": {"nodes": [{"name": "Madhouse"}]},
                }
            }
        }
        fake = FakePost(payload)
        monkeypatch.setattr(recs, "_http_post_json", fake)
        out = recs.resolve("anime", "Frieren")
        assert out["canonical_key"] == "anilist:154587"
        assert out["kind"] == "anime"
        assert out["title"] == "Frieren"
        assert out["creator"] == "Madhouse"
        assert out["year"] == 2023
        assert out["rating"] == 92
        assert out["poster"] == "https://img/frieren.jpg"
        assert out["external_url"] == "https://anilist.co/anime/154587"
        # verify it asked for ANIME
        assert "ANIME" in fake.calls[0][1]["query"]

    def test_falls_back_to_romaji(self, monkeypatch):
        payload = {
            "data": {
                "Media": {
                    "id": 1,
                    "title": {"romaji": "Romaji Only", "english": None},
                    "coverImage": {"large": None},
                    "seasonYear": None,
                    "averageScore": None,
                    "siteUrl": "u",
                    "studios": {"nodes": []},
                }
            }
        }
        monkeypatch.setattr(recs, "_http_post_json", FakePost(payload))
        out = recs.resolve("anime", "x")
        assert out["title"] == "Romaji Only"
        assert out["creator"] is None

    def test_miss(self, monkeypatch):
        monkeypatch.setattr(recs, "_http_post_json", FakePost({"data": {"Media": None}}))
        assert recs.resolve("anime", "x") is None

    def test_network_failure(self, monkeypatch):
        monkeypatch.setattr(recs, "_http_post_json", FakePost(None))
        assert recs.resolve("anime", "x") is None


class TestResolveManga:
    def test_happy_path(self, monkeypatch):
        payload = {
            "data": {
                "Media": {
                    "id": 30013,
                    "title": {"romaji": "One Piece", "english": "One Piece"},
                    "coverImage": {"large": "https://img/op.jpg"},
                    "seasonYear": 1997,
                    "averageScore": 90,
                    "siteUrl": "https://anilist.co/manga/30013",
                    "staff": {"nodes": [{"name": {"full": "Eiichiro Oda"}}]},
                }
            }
        }
        fake = FakePost(payload)
        monkeypatch.setattr(recs, "_http_post_json", fake)
        out = recs.resolve("manga", "One Piece")
        assert out["canonical_key"] == "anilist:30013"
        assert out["kind"] == "manga"
        assert out["creator"] == "Eiichiro Oda"
        assert "MANGA" in fake.calls[0][1]["query"]


# --------------------------------------------------------------------------- #
# Book resolver (Open Library)
# --------------------------------------------------------------------------- #


class TestResolveBook:
    def test_isbn_key(self, monkeypatch):
        routes = {
            "openlibrary.org/search.json": {
                "docs": [
                    {
                        "title": "Neuromancer",
                        "author_name": ["William Gibson"],
                        "first_publish_year": 1984,
                        "cover_i": 12345,
                        "isbn": ["0441569595", "9780441569595"],
                        "key": "/works/OL123W",
                    }
                ]
            }
        }
        monkeypatch.setattr(recs, "_http_get", FakeGet(routes))
        out = recs.resolve("book", "Neuromancer", creator="William Gibson")
        assert out["canonical_key"] == "isbn:0441569595"
        assert out["kind"] == "book"
        assert out["creator"] == "William Gibson"
        assert out["year"] == 1984
        assert out["poster"] == "https://covers.openlibrary.org/b/id/12345-M.jpg"
        assert out["rating"] is None
        assert out["external_url"] == "https://openlibrary.org/works/OL123W"

    def test_ol_key_when_no_isbn(self, monkeypatch):
        routes = {
            "openlibrary.org/search.json": {
                "docs": [{"title": "T", "key": "/works/OL9W", "author_name": ["A"]}]
            }
        }
        monkeypatch.setattr(recs, "_http_get", FakeGet(routes))
        out = recs.resolve("book", "T")
        assert out["canonical_key"] == "ol:/works/OL9W"
        assert out["poster"] is None

    def test_miss(self, monkeypatch):
        monkeypatch.setattr(recs, "_http_get", FakeGet({"openlibrary.org/search.json": {"docs": []}}))
        assert recs.resolve("book", "x") is None


# --------------------------------------------------------------------------- #
# Dispatch guards
# --------------------------------------------------------------------------- #


class TestResolveDispatch:
    def test_unknown_kind(self):
        assert recs.resolve("podcast", "x") is None

    def test_empty_title(self):
        assert recs.resolve("movie", "   ") is None


# --------------------------------------------------------------------------- #
# Store: load / save round-trip + corruption tolerance
# --------------------------------------------------------------------------- #


class TestLoadSave:
    def test_missing_file(self, store_path):
        assert recs.load_recs(store_path) == {}

    def test_round_trip_atomic(self, store_path):
        data = {"tmdb:movie:1": {"title": "X", "count": 2}}
        recs.save_recs(data, store_path)
        assert store_path.exists()
        assert recs.load_recs(store_path) == data
        # temp sibling cleaned up by replace()
        assert not store_path.with_suffix(store_path.suffix + ".tmp").exists()

    def test_corrupt_file_tolerated(self, store_path):
        store_path.write_text("{not valid json")
        assert recs.load_recs(store_path) == {}

    def test_non_dict_json_tolerated(self, store_path):
        store_path.write_text("[1, 2, 3]")
        assert recs.load_recs(store_path) == {}


# --------------------------------------------------------------------------- #
# record(): create, dedupe, count, unresolved bucket
# --------------------------------------------------------------------------- #


class TestRecord:
    def _movie_routes(self):
        return {
            "/search/movie": {"results": [{"id": 1, "title": "Dune", "release_date": "2021-01-01"}]},
            "/movie/1/credits": {"crew": [{"job": "Director", "name": "DV"}]},
        }

    def test_empty_title_returns_none(self, store_path):
        assert recs.record("movie", "  ", None, "note.md", path=store_path) is None

    def test_create_entry(self, monkeypatch, store_path):
        monkeypatch.setattr(recs, "_http_get", FakeGet(self._movie_routes()))
        entry = recs.record("movie", "Dune", None, "notes/a.md", path=store_path)
        assert entry["canonical_key"] == "tmdb:movie:1"
        assert entry["sources"] == ["notes/a.md"]
        assert entry["count"] == 1
        assert entry["status"] is None
        assert entry["first_seen"] is None
        # persisted
        assert "tmdb:movie:1" in recs.load_recs(store_path)

    def test_same_note_deduped(self, monkeypatch, store_path):
        monkeypatch.setattr(recs, "_http_get", FakeGet(self._movie_routes()))
        recs.record("movie", "Dune", None, "a.md", path=store_path)
        entry = recs.record("movie", "Dune", None, "a.md", path=store_path)
        assert entry["sources"] == ["a.md"]
        assert entry["count"] == 1

    def test_two_notes_bump_count(self, monkeypatch, store_path):
        monkeypatch.setattr(recs, "_http_get", FakeGet(self._movie_routes()))
        recs.record("movie", "Dune", None, "a.md", path=store_path)
        entry = recs.record("movie", "Dune", None, "b.md", path=store_path)
        assert entry["count"] == 2
        assert entry["sources"] == ["a.md", "b.md"]

    def test_unresolved_bucket(self, monkeypatch, store_path):
        monkeypatch.setattr(recs, "_http_get", FakeGet({}))  # everything misses
        entry = recs.record("book", "Some Obscure Zine!", "Nobody", "n.md", path=store_path)
        assert entry["canonical_key"] == "unresolved:book:some-obscure-zine"
        assert entry["kind"] == "book"
        assert entry["title"] == "Some Obscure Zine!"
        assert entry["creator"] == "Nobody"
        assert entry["poster"] is None
        assert entry["rating"] is None
        assert entry["count"] == 1
        assert entry["canonical_key"] in recs.load_recs(store_path)

    def test_unresolved_then_dedupe(self, monkeypatch, store_path):
        monkeypatch.setattr(recs, "_http_get", FakeGet({}))
        recs.record("book", "Zine", None, "n.md", path=store_path)
        entry = recs.record("book", "Zine", None, "n.md", path=store_path)
        assert entry["count"] == 1


# --------------------------------------------------------------------------- #
# set_status
# --------------------------------------------------------------------------- #


class TestSetStatus:
    def _seed(self, store_path):
        recs.save_recs({"k": {"canonical_key": "k", "kind": "movie", "title": "X",
                              "sources": ["a"], "count": 1, "status": None}}, store_path)

    def test_valid(self, store_path):
        self._seed(store_path)
        entry = recs.set_status("k", "seen", path=store_path)
        assert entry["status"] == "seen"
        assert recs.load_recs(store_path)["k"]["status"] == "seen"

    def test_none_is_valid(self, store_path):
        self._seed(store_path)
        assert recs.set_status("k", None, path=store_path)["status"] is None

    def test_invalid_status(self, store_path):
        self._seed(store_path)
        with pytest.raises(ValueError):
            recs.set_status("k", "bogus", path=store_path)

    def test_missing_key(self, store_path):
        self._seed(store_path)
        with pytest.raises(KeyError):
            recs.set_status("nope", "seen", path=store_path)


# --------------------------------------------------------------------------- #
# entries(): sorting + filtering
# --------------------------------------------------------------------------- #


class TestEntries:
    def _seed(self, store_path):
        recs.save_recs(
            {
                "a": {"canonical_key": "a", "kind": "movie", "title": "Beta", "count": 1},
                "b": {"canonical_key": "b", "kind": "movie", "title": "Alpha", "count": 3},
                "c": {"canonical_key": "c", "kind": "book", "title": "Zed", "count": 3},
            },
            store_path,
        )

    def test_sorted_count_then_title(self, store_path):
        self._seed(store_path)
        out = recs.entries(path=store_path)
        # count desc first (b,c at 3), tie broken by title asc (Alpha < Zed), then Beta
        assert [e["canonical_key"] for e in out] == ["b", "c", "a"]

    def test_filter_by_kind(self, store_path):
        self._seed(store_path)
        out = recs.entries(kind="book", path=store_path)
        assert [e["canonical_key"] for e in out] == ["c"]

    def test_empty(self, store_path):
        assert recs.entries(path=store_path) == []


# --------------------------------------------------------------------------- #
# extract_recommendations (Haiku mocked)
# --------------------------------------------------------------------------- #


class TestExtract:
    def test_shapes_output(self, monkeypatch):
        def fake_run(system, user, schema):
            return {
                "recommendations": [
                    {"kind": "movie", "title": "Dune", "creator": "DV", "reason": "cited"},
                    {"kind": "anime", "title": "Frieren"},
                ]
            }

        monkeypatch.setattr(recs, "run_structured", fake_run)
        out = recs.extract_recommendations("some note mentioning Dune and Frieren")
        assert out == [
            {"kind": "movie", "title": "Dune", "creator": "DV", "reason": "cited"},
            {"kind": "anime", "title": "Frieren", "creator": None, "reason": None},
        ]

    def test_empty_text_skips_model(self, monkeypatch):
        called = []
        monkeypatch.setattr(recs, "run_structured", lambda *a, **k: called.append(1) or {})
        assert recs.extract_recommendations("   ") == []
        assert called == []

    def test_empty_list(self, monkeypatch):
        monkeypatch.setattr(recs, "run_structured", lambda s, u, sc: {"recommendations": []})
        assert recs.extract_recommendations("nothing here") == []

    def test_bad_kind_coerced(self, monkeypatch):
        # Recommendation validator coerces an unknown kind to "movie"
        monkeypatch.setattr(
            recs, "run_structured",
            lambda s, u, sc: {"recommendations": [{"kind": "vhs", "title": "X"}]},
        )
        assert recs.extract_recommendations("x")[0]["kind"] == "movie"
