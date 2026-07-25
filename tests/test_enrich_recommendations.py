"""Recommendation extraction: schema, kind validation, and derived tags."""

from ytk.enrich import Enrichment, Recommendation


def _enrichment(tags, recs):
    return Enrichment(
        thesis="t",
        summary="s",
        key_concepts=[],
        insights=[],
        interest_tags=list(tags),
        key_moments=[],
        recommendations=recs,
    )


class TestRecommendationKind:
    def test_known_kinds_pass(self):
        for k in ("movie", "show", "anime", "book", "manga"):
            assert Recommendation(kind=k, title="x").kind == k

    def test_case_and_whitespace_normalized(self):
        assert Recommendation(kind=" Anime ", title="x").kind == "anime"

    def test_unknown_kind_falls_back_to_movie(self):
        assert Recommendation(kind="documentary", title="x").kind == "movie"


class TestDerivedTags:
    def test_rec_tags_appended_per_kind(self):
        e = _enrichment(
            ["touchdesigner"],
            [
                Recommendation(kind="movie", title="Dune"),
                Recommendation(kind="anime", title="Frieren"),
            ],
        )
        assert "movie-rec" in e.interest_tags
        assert "anime-rec" in e.interest_tags
        # content tag preserved, not replaced
        assert "touchdesigner" in e.interest_tags

    def test_no_recommendations_no_rec_tags(self):
        e = _enrichment(["ai", "go"], [])
        assert e.interest_tags == ["ai", "go"]

    def test_rec_tag_not_duplicated(self):
        e = _enrichment(
            ["movie-rec"],
            [Recommendation(kind="movie", title="Dune")],
        )
        assert e.interest_tags.count("movie-rec") == 1

    def test_multiple_same_kind_one_tag(self):
        e = _enrichment(
            [],
            [
                Recommendation(kind="book", title="Dune"),
                Recommendation(kind="book", title="Blindsight"),
            ],
        )
        assert e.interest_tags.count("book-rec") == 1


class TestSchemaAndDefaults:
    def test_recommendations_defaults_empty(self):
        e = Enrichment(
            thesis="t",
            summary="s",
            key_concepts=[],
            insights=[],
            interest_tags=[],
            key_moments=[],
        )
        assert e.recommendations == []

    def test_schema_exposes_recommendations(self):
        from ytk.enrich import _SCHEMA

        assert "recommendations" in _SCHEMA["properties"]
