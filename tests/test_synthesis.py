import numpy as np
import pytest

from ytk.config import InterestConfig
from ytk.profile_grounding import check_profile_grounding_text
from ytk.synthesis import (
    PortraitClaimOutput, ProfileGroundingError, ProfileSynthesis, ThemeLabel,
    assemble_snapshot,
    build_synthesis_prompt, render_profile, _slug,
    choose_k, cluster_embeddings,
)


def test_choose_k_clamps_small_corpus():
    cfg = InterestConfig()
    assert choose_k(2, cfg) == 2          # n <= cluster_min -> n
    assert choose_k(0, cfg) == 1          # never zero


def test_choose_k_scales_and_caps():
    cfg = InterestConfig(cluster_min=3, cluster_max=24)
    assert choose_k(50, cfg) == 5         # round(sqrt(50/2)) = 5
    assert choose_k(100000, cfg) == 24    # capped at cluster_max


def test_cluster_embeddings_separates_two_blobs():
    blob_a = np.tile([0.0, 0.0, 1.0], (5, 1)) + np.linspace(0, 0.01, 15).reshape(5, 3)
    blob_b = np.tile([1.0, 0.0, 0.0], (5, 1)) + np.linspace(0, 0.01, 15).reshape(5, 3)
    embeddings = np.vstack([blob_a, blob_b])

    labels = cluster_embeddings(embeddings, k=2)

    assert len(labels) == 10
    assert len(set(labels[:5])) == 1      # first blob is one cluster
    assert len(set(labels[5:])) == 1      # second blob is one cluster
    assert labels[0] != labels[5]         # the two blobs differ


def test_clustering_keeps_k_regardless_of_timestamp_coverage():
    """Taxonomy dimensionality never shrinks because clusters lack fresh
    anchors: the k-reduction mechanism (#94 first attempt) is gone and
    clustering is purely geometric."""
    embeddings = np.asarray([[0.0], [0.01], [10.0], [10.01]])

    labels = cluster_embeddings(embeddings, k=2)

    assert len(set(labels)) == 2
    assert not hasattr(
        __import__("ytk.synthesis", fromlist=["synthesis"]),
        "cluster_groundable_embeddings",
    )


def _notes():
    return [
        {"id": "a", "title": "Shader Tricks", "thesis": "GPU shader demo.",
         "summary": "s", "tags": ["gpu"], "embedding": [0.0],
         "captured_at": "2026-06-01T00:00:00+00:00"},
        {"id": "b", "title": "WGSL Intro", "thesis": "WGSL basics.",
         "summary": "s", "tags": ["gpu"], "embedding": [0.0],
         "captured_at": "2026-05-31T00:00:00+00:00"},
        {"id": "c", "title": "Cold Brew", "thesis": "Coffee method.",
         "summary": "s", "tags": ["coffee"], "embedding": [1.0],
         "captured_at": "2026-05-30T00:00:00+00:00"},
    ]


def _synthesis(gpu_label="GPU Graphics", gpu_summary="gpu stuff",
               claim_evidence=("a", "c")):
    return ProfileSynthesis(
        themes=[
            ThemeLabel(cluster_index=0, label=gpu_label, summary=gpu_summary,
                       evidence_ids=["a"]),
            ThemeLabel(cluster_index=1, label="Coffee", summary="coffee stuff",
                       evidence_ids=["c"]),
        ],
        claims=[PortraitClaimOutput(
            text="You keep returning to GPU techniques and coffee methods.",
            evidence_ids=list(claim_evidence),
        )],
    )


def test_build_synthesis_prompt_groups_by_cluster():
    prompt = build_synthesis_prompt(_notes(), [0, 0, 1], levels=[0, 1, 2])
    assert "Cluster 0 (2 notes)" in prompt
    assert "Cluster 1 (1 note)" in prompt
    assert "Shader Tricks" in prompt and "Cold Brew" in prompt
    assert "signal: r=0 passive exposure" in prompt
    assert "signal: r=1 deliberate save" in prompt
    assert "signal: r=2 authored thought" in prompt


def test_build_synthesis_prompt_rejects_mismatched_signal_levels():
    with pytest.raises(ValueError, match="levels and notes"):
        build_synthesis_prompt(_notes(), [0, 0, 1], levels=[0])


def test_build_synthesis_prompt_handles_empty_title():
    notes = [{"id": "m", "title": "", "thesis": "A boxing footwork drill.",
              "summary": "", "tags": ["boxing"], "embedding": [0.0],
              "captured_at": "2026-06-01T00:00:00+00:00"}]
    prompt = build_synthesis_prompt(notes, [0])
    assert "[m] A boxing footwork drill." in prompt
    assert "  -  — " not in prompt


def test_assemble_snapshot_maps_clusters_to_themes():
    synth = _synthesis()
    snap = assemble_snapshot(_notes(), [0, 0, 1], synth, "2026-06-02T00:00:00+00:00")

    assert snap.note_count == 3
    gpu = next(t for t in snap.themes if t.label == "GPU Graphics")
    assert gpu.note_ids == ["a", "b"]
    assert gpu.weight == round(2 / 3, 4)
    assert snap.themes[0].label == "GPU Graphics"   # sorted by weight desc
    assert snap.profile_markdown == (
        "You keep returning to GPU techniques and coffee methods."
    )
    assert snap.portrait_claims[0].evidence_ids == ["a", "c"]
    assert gpu.fresh_note_count == 2                # all captures within half-life
    assert set(snap.evidence_signals) == {"a", "c"}


def test_render_profile_has_frontmatter_and_xml_themes():
    snap = assemble_snapshot(
        _notes(), [0, 0, 1],
        _synthesis(gpu_summary="gpu"),
        "2026-06-02T00:00:00+00:00",
    )
    out = render_profile(snap)
    assert out.startswith("---")
    assert "type: interest-profile" in out
    assert '<interest-profile generated="2026-06-02T00:00:00+00:00" notes="3" themes="2"' in out
    assert "<portrait>" in out
    assert "You keep returning to GPU techniques and coffee methods." in out
    assert '<claim evidence="a c">' in out
    assert 'fresh-notes="2"' in out
    assert '<theme rank="1" id="gpu-graphics"' in out  # heaviest theme first
    assert "<label>GPU Graphics</label>" in out
    assert "<exemplar>Shader Tricks</exemplar>" in out  # exemplar titles surfaced


def test_render_profile_escapes_xml_special_chars():
    snap = assemble_snapshot(
        _notes(), [0, 0, 1],
        _synthesis(gpu_label="GPU & Shaders", gpu_summary="a < b"),
        "2026-06-02T00:00:00+00:00",
    )
    out = render_profile(snap)
    assert "<label>GPU &amp; Shaders</label>" in out
    assert "a &lt; b" in out
    assert "You keep returning to GPU techniques and coffee methods." in out


def test_grounding_rejects_wrong_cluster_and_stale_only_claim_evidence():
    wrong = _synthesis()
    wrong.themes[0].evidence_ids = ["c"]
    with pytest.raises(ProfileGroundingError, match="outside its allowed set"):
        assemble_snapshot(
            _notes(), [0, 0, 1], wrong, "2026-06-02T00:00:00+00:00"
        )

    stale = _notes()
    stale[2]["captured_at"] = "2025-01-01T00:00:00+00:00"
    with pytest.raises(ProfileGroundingError, match="decay half-life"):
        assemble_snapshot(
            stale, [0, 0, 1], _synthesis(claim_evidence=("c",)),
            "2026-06-02T00:00:00+00:00",
        )


def test_unknown_timestamps_do_not_erase_categories():
    """A theme whose notes all lack capture times survives with its summary;
    freshness is reported as an overlay (fresh_note_count=0), never a gate."""
    notes = _notes()
    notes[0]["captured_at"] = ""
    notes[1]["captured_at"] = ""
    synth = _synthesis(claim_evidence=("c",))  # claim anchored on the fresh note

    snap = assemble_snapshot(notes, [0, 0, 1], synth, "2026-06-02T00:00:00+00:00")

    gpu = next(t for t in snap.themes if t.label == "GPU Graphics")
    assert gpu.summary == "gpu stuff"
    assert gpu.fresh_note_count == 0
    coffee = next(t for t in snap.themes if t.label == "Coffee")
    assert coffee.fresh_note_count == 1


def test_portrait_prompt_contract_abstract_person_not_media():
    """The register contract: the portrait describes the person abstractly —
    no named tools/items (they break the #83 time series and cosplay
    familiarity with merely-queued material), attraction verbs only."""
    from ytk.synthesis import _PROFILE_SYSTEM

    assert "no claims of expertise" in _PROFILE_SYSTEM
    assert "NEVER name a tool" in _PROFILE_SYSTEM
    assert "time series" in _PROFILE_SYSTEM
    assert "only queued" in _PROFILE_SYSTEM
    assert "capture system itself" in _PROFILE_SYSTEM
    assert "second person" in _PROFILE_SYSTEM


def test_prompt_lists_clusters_newest_first_and_carries_previous_portrait():
    notes = _notes()  # a: 06-01, b: 05-31, c: 05-30
    prompt = build_synthesis_prompt(
        notes, [0, 0, 1], previous_portrait="You are an engineer-maker."
    )
    assert prompt.index("[a]") < prompt.index("[b]")  # newest capture first
    assert "Previous portrait (evolve, do not rewrite):" in prompt
    assert "You are an engineer-maker." in prompt
    assert "[a]" not in prompt[prompt.index("Previous portrait"):]

    without = build_synthesis_prompt(notes, [0, 0, 1])
    assert "Previous portrait" not in without


def test_exemplars_are_nearest_centroid_not_insertion_order():
    """Insertion order used to make every theme showcase the oldest videos;
    exemplars must instead be the members closest to the theme centroid."""
    notes = [
        {"id": f"n{i}", "title": f"t{i}", "thesis": "x", "summary": "s",
         "tags": [], "embedding": None,
         "captured_at": "2026-06-01T00:00:00+00:00"}
        for i in range(4)
    ]
    # n0 is an outlier; n1-n3 sit together, so the centroid favors them.
    emb = np.asarray([[0.0, 1.0], [1.0, 0.0], [1.0, 0.05], [1.0, -0.05]])
    synth = ProfileSynthesis(
        themes=[ThemeLabel(cluster_index=0, label="A", summary="a",
                           evidence_ids=["n0"])],
        claims=[PortraitClaimOutput(text="You return to A.",
                                    evidence_ids=["n1"])],
    )
    snap = assemble_snapshot(
        notes, [0, 0, 0, 0], synth, "2026-06-02T00:00:00+00:00",
        embeddings=emb, weights=[1.0] * 4, levels=[0] * 4,
    )
    assert "t0" not in snap.themes[0].exemplar_titles
    assert len(snap.themes[0].exemplar_titles) == 3


def test_rendered_profile_passes_standalone_grounding_checker():
    snap = assemble_snapshot(
        _notes(), [0, 0, 1], _synthesis(), "2026-06-02T00:00:00+00:00"
    )
    assert check_profile_grounding_text(render_profile(snap)) == []

    broken = render_profile(snap).replace(' evidence="a c"', '', 1)
    assert any("no evidence refs" in e for e in check_profile_grounding_text(broken))


def test_checker_allows_stale_theme_summary_but_enforces_claim_freshness():
    notes = _notes()
    notes[2]["captured_at"] = ""  # Coffee's only evidence has no capture time
    snap = assemble_snapshot(
        notes, [0, 0, 1], _synthesis(), "2026-06-02T00:00:00+00:00"
    )
    out = render_profile(snap)
    assert check_profile_grounding_text(out) == []  # category survives

    # A claim citing only the unknown-time item fails the freshness rule.
    stale_claim = out.replace('<claim evidence="a c">', '<claim evidence="c">')
    errors = check_profile_grounding_text(stale_claim)
    assert any("decay half-life" in e for e in errors)


def test_slug():
    assert _slug("GPU Graphics & Shaders!") == "gpu-graphics-shaders"
