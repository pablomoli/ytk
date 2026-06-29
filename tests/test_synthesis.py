import numpy as np

from ytk.config import InterestConfig
from ytk.synthesis import (
    ProfileSynthesis, ThemeLabel, assemble_snapshot,
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


def _notes():
    return [
        {"id": "a", "title": "Shader Tricks", "thesis": "GPU shader demo.",
         "summary": "s", "tags": ["gpu"], "embedding": [0.0]},
        {"id": "b", "title": "WGSL Intro", "thesis": "WGSL basics.",
         "summary": "s", "tags": ["gpu"], "embedding": [0.0]},
        {"id": "c", "title": "Cold Brew", "thesis": "Coffee method.",
         "summary": "s", "tags": ["coffee"], "embedding": [1.0]},
    ]


def test_build_synthesis_prompt_groups_by_cluster():
    prompt = build_synthesis_prompt(_notes(), [0, 0, 1])
    assert "Cluster 0 (2 notes)" in prompt
    assert "Cluster 1 (1 note)" in prompt
    assert "Shader Tricks" in prompt and "Cold Brew" in prompt


def test_build_synthesis_prompt_handles_empty_title():
    notes = [{"id": "m", "title": "", "thesis": "A boxing footwork drill.",
              "summary": "", "tags": ["boxing"], "embedding": [0.0]}]
    prompt = build_synthesis_prompt(notes, [0])
    assert "  - A boxing footwork drill. [tags: boxing]" in prompt
    assert "  -  — " not in prompt


def test_assemble_snapshot_maps_clusters_to_themes():
    synth = ProfileSynthesis(
        themes=[ThemeLabel(cluster_index=0, label="GPU Graphics", summary="gpu stuff"),
                ThemeLabel(cluster_index=1, label="Coffee", summary="coffee stuff")],
        profile_markdown="You like GPUs and coffee.",
    )
    snap = assemble_snapshot(_notes(), [0, 0, 1], synth, "2026-06-02T00:00:00+00:00")

    assert snap.note_count == 3
    gpu = next(t for t in snap.themes if t.label == "GPU Graphics")
    assert gpu.note_ids == ["a", "b"]
    assert gpu.weight == round(2 / 3, 4)
    assert snap.themes[0].label == "GPU Graphics"   # sorted by weight desc
    assert snap.profile_markdown == "You like GPUs and coffee."


def test_render_profile_has_frontmatter_and_xml_themes():
    snap = assemble_snapshot(
        _notes(), [0, 0, 1],
        ProfileSynthesis(
            themes=[ThemeLabel(cluster_index=0, label="GPU Graphics", summary="gpu"),
                    ThemeLabel(cluster_index=1, label="Coffee", summary="coffee")],
            profile_markdown="Profile prose.",
        ),
        "2026-06-02T00:00:00+00:00",
    )
    out = render_profile(snap)
    assert out.startswith("---")
    assert "type: interest-profile" in out
    assert '<interest-profile generated="2026-06-02T00:00:00+00:00" notes="3" themes="2">' in out
    assert "<portrait>" in out and "Profile prose." in out
    assert '<theme rank="1" id="gpu-graphics"' in out  # heaviest theme first
    assert "<label>GPU Graphics</label>" in out
    assert "<exemplar>Shader Tricks</exemplar>" in out  # exemplar titles surfaced


def test_render_profile_escapes_xml_special_chars():
    snap = assemble_snapshot(
        _notes(), [0, 0, 1],
        ProfileSynthesis(
            themes=[ThemeLabel(cluster_index=0, label="GPU & Shaders", summary="a < b"),
                    ThemeLabel(cluster_index=1, label="Coffee", summary="c")],
            profile_markdown="Tools & taste.",
        ),
        "2026-06-02T00:00:00+00:00",
    )
    out = render_profile(snap)
    assert "<label>GPU &amp; Shaders</label>" in out
    assert "a &lt; b" in out
    assert "Tools &amp; taste." in out


def test_slug():
    assert _slug("GPU Graphics & Shaders!") == "gpu-graphics-shaders"
