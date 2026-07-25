import pytest

from ytk import enrich_eval as ev


def test_load_fixtures_parses_transcript_and_enrichment(tmp_path):
    note = tmp_path / "n.md"
    note.write_text(
        "---\nurl: u\ntitle: T\n---\n## Thesis\nx\n## Commentary\ny\n"
        "## Key Concepts\n- a: b\n## Transcript\n<details>\n<summary>Raw</summary>\n\nHELLO WORLD\n</details>\n",
        encoding="utf-8",
    )
    fx = ev.load_fixtures([note])
    assert len(fx) == 1
    assert "HELLO WORLD" in fx[0].transcript
    assert fx[0].enrichment.thesis == "x"


def test_faithfulness_counts_labels(monkeypatch):
    from ytk import enrich_eval as ev
    from ytk.enrich import Enrichment

    fake = ev._FaithResult(
        claims=[
            ev._ClaimVerdict(claim="uses wgpu", label="supported"),
            ev._ClaimVerdict(claim="builds a full OS", label="inflated"),
        ]
    )
    monkeypatch.setattr(ev, "structured", lambda s, u, r, **kw: fake)
    enr = Enrichment(
        thesis="t",
        summary="s",
        key_concepts=["wgpu: gpu"],
        insights=["builds a full OS"],
        interest_tags=[],
        key_moments=[],
    )
    score = ev.faithfulness(enr, "transcript mentions wgpu")
    assert score.supported == 1 and score.inflated == 1
    assert score.rate == 0.5


def test_judge_counts_win_only_if_consistent_across_orders(monkeypatch):
    from ytk import enrich_eval as ev
    from ytk.enrich import Enrichment

    enr = lambda t: Enrichment(
        thesis=t, summary="s", key_concepts=[], insights=[], interest_tags=[], key_moments=[]
    )
    calls = []

    def fake(system, user, result, **kw):
        # first call A-then-B => "A" wins; swapped call B-then-A => "B" is the same enrichment => "A" (position2)
        calls.append(user)
        return ev._JudgeResult(
            winner=("A" if len(calls) == 1 else "B"),
            specificity="x",
            faithfulness="x",
            nonredundancy="x",
            retrievability="x",
        )

    monkeypatch.setattr(ev, "structured", fake)
    v = ev.judge(enr("alpha"), enr("beta"), "transcript")
    assert v.winner == "A"  # A won in order 1, and won (as position B) in swapped order 2


def test_judge_inconsistent_is_tie(monkeypatch):
    from ytk import enrich_eval as ev
    from ytk.enrich import Enrichment

    enr = Enrichment(
        thesis="t", summary="s", key_concepts=[], insights=[], interest_tags=[], key_moments=[]
    )
    monkeypatch.setattr(
        ev,
        "structured",
        lambda s, u, r, **kw: ev._JudgeResult(
            winner="A", specificity="", faithfulness="", nonredundancy="", retrievability=""
        ),
    )
    # "A" both times means position-1 always wins => position bias => tie
    assert ev.judge(enr, enr, "t").winner == "tie"


def test_bootstrap_wider_interval_at_smaller_n():
    from ytk.enrich_eval import bootstrap_winrate

    small = bootstrap_winrate([1.0, 1.0, 0.0, 1.0, 0.0])
    large = bootstrap_winrate([1.0, 1.0, 0.0, 1.0, 0.0] * 20)
    assert 0.0 <= small[1] <= small[0] <= small[2] <= 1.0
    assert (small[2] - small[1]) > (large[2] - large[1])


def test_ledger_round_trip_and_tolerates_empty(tmp_path):
    from ytk import enrich_eval as ev

    p = tmp_path / "ledger.json"
    ev.ledger_append({"tone": "x", "winrate": 0.6}, p)
    ev.ledger_append({"tone": "y", "winrate": 0.4}, p)
    rows = ev.ledger_read(p)
    assert [r["tone"] for r in rows] == ["x", "y"]
    p.write_text("", encoding="utf-8")  # corrupt/empty
    assert ev.ledger_read(p) == []


def test_run_eval_aggregates_and_writes_ledger(monkeypatch, tmp_path):
    from ytk import enrich_eval as ev
    from ytk.enrich import Enrichment

    fx = [
        ev.Fixture(
            note_path=tmp_path / "n.md",
            source="web",
            transcript="T",
            enrichment=Enrichment(
                thesis="t",
                summary="s",
                key_concepts=[],
                insights=[],
                interest_tags=[],
                key_moments=[],
            ),
        )
    ]
    monkeypatch.setattr(ev, "enrich_content", lambda content, source, **kw: fx[0].enrichment)
    monkeypatch.setattr(
        ev, "judge", lambda a, b, t: ev.Verdict(winner="B", reasons={})
    )  # challenger (B) wins
    monkeypatch.setattr(ev, "faithfulness", lambda e, t: ev.FaithScore(2, 0, 0, 0.0))
    monkeypatch.setattr(ev, "LEDGER_PATH", tmp_path / "ledger.json")
    out = ev.run_eval("terse", fixtures=fx)
    assert out["n"] == 1 and out["winrate"] == 1.0
    assert ev.ledger_read(tmp_path / "ledger.json")[0]["winrate"] == 1.0


def test_run_eval_raises_when_no_fixtures_available(monkeypatch):
    from ytk import enrich_eval as ev

    monkeypatch.setattr(ev, "_default_fixtures", list)
    with pytest.raises(ValueError):
        ev.run_eval("terse", fixtures=None)


def test_faithfulness_never_truncates_enrichment(monkeypatch):
    from ytk import enrich_eval as ev
    from ytk.enrich import Enrichment

    captured = {}

    def fake_structured(system, user_prompt, result, **kw):
        captured["user_prompt"] = user_prompt
        captured["max_input_chars"] = kw.get("max_input_chars")
        return ev._FaithResult(claims=[])

    monkeypatch.setattr(ev, "structured", fake_structured)

    marker = "DISTINCTIVE_ENRICHMENT_MARKER_XYZ"
    enr = Enrichment(
        thesis="t",
        summary="s",
        key_concepts=[marker],
        insights=[],
        interest_tags=[],
        key_moments=[],
    )
    long_transcript = "x" * 50_000

    ev.faithfulness(enr, long_transcript)

    assert marker in captured["user_prompt"]
    assert len(captured["user_prompt"]) <= captured["max_input_chars"]


def test_judge_never_truncates_enrichments(monkeypatch):
    from ytk import enrich_eval as ev
    from ytk.enrich import Enrichment

    captured = []

    def fake_structured(system, user_prompt, result, **kw):
        captured.append({"user_prompt": user_prompt, "max_input_chars": kw.get("max_input_chars")})
        return ev._JudgeResult(
            winner="A", specificity="x", faithfulness="x", nonredundancy="x", retrievability="x"
        )

    monkeypatch.setattr(ev, "structured", fake_structured)

    marker_a = "DISTINCTIVE_MARKER_A_ABC"
    marker_b = "DISTINCTIVE_MARKER_B_DEF"
    enr_a = Enrichment(
        thesis=marker_a, summary="s", key_concepts=[], insights=[], interest_tags=[], key_moments=[]
    )
    enr_b = Enrichment(
        thesis=marker_b, summary="s", key_concepts=[], insights=[], interest_tags=[], key_moments=[]
    )
    long_transcript = "y" * 50_000

    ev.judge(enr_a, enr_b, long_transcript)

    assert len(captured) == 2
    for call in captured:
        assert marker_a in call["user_prompt"]
        assert marker_b in call["user_prompt"]
        assert len(call["user_prompt"]) <= call["max_input_chars"]
