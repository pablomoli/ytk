"""Bucket loader: user-authored topic axis for the grove.

A bucket is a topic, not a directory. Assignment is rule-based (projects,
themes, path prefixes), first bucket wins, and unmatched notes stay
unmatched (-1) — there is no catch-all bucket.
"""

import textwrap

from scripts.grove_lab.buckets import Note, assign, load_buckets

YAML = textwrap.dedent(
    """
    version: 1
    seed_floor: 0.62
    buckets:
      - name: epicmap
        projects: [epicmap]
      - name: ai-building
        projects: [ytk, tts]
        themes: [AI-augmented building]
        paths: [second-brain/projects/ytk]
      - name: visual-craft
        palette: ultraviolet
        themes: [Visual math & 3D craft]
    """
)


def _load(tmp_path):
    f = tmp_path / "grove_buckets.yaml"
    f.write_text(YAML)
    return load_buckets(f)


def test_load_buckets_parses_yaml(tmp_path):
    cfg = _load(tmp_path)
    assert cfg.seed_floor == 0.62
    assert [b.name for b in cfg.buckets] == ["epicmap", "ai-building", "visual-craft"]
    assert cfg.buckets[1].projects == ["ytk", "tts"]
    assert cfg.buckets[1].themes == ["AI-augmented building"]
    assert cfg.buckets[2].palette == "ultraviolet"
    # missing keys default to empty, not KeyError
    assert cfg.buckets[0].themes == []
    assert cfg.buckets[0].paths == []
    assert cfg.buckets[0].palette is None


def test_assign_by_project_slug(tmp_path):
    cfg = _load(tmp_path)
    notes = [Note(cat="memory", project="epicmap", theme=None, path="x/y.md")]
    assert assign(notes, cfg) == [0]


def test_assign_by_theme(tmp_path):
    cfg = _load(tmp_path)
    notes = [Note(cat="youtube", project=None, theme="Visual math & 3D craft", path="")]
    assert assign(notes, cfg) == [2]


def test_assign_by_path_prefix(tmp_path):
    cfg = _load(tmp_path)
    notes = [
        Note(
            cat="project-note",
            project=None,
            theme=None,
            path="second-brain/projects/ytk/session-019-brief.md",
        )
    ]
    assert assign(notes, cfg) == [1]


def test_first_bucket_wins(tmp_path):
    """A note matching several buckets goes to the earliest one — bucket
    order in the YAML is the user's priority order."""
    cfg = _load(tmp_path)
    notes = [
        Note(cat="youtube", project="epicmap", theme="AI-augmented building", path="")
    ]
    assert assign(notes, cfg) == [0]


def test_unmatched_is_minus_one_never_other(tmp_path):
    cfg = _load(tmp_path)
    notes = [
        Note(cat="memory", project="niloc", theme=None, path="inbox/memories/niloc/a.md"),
        Note(cat="memory", project=None, theme=None, path=""),
    ]
    assert assign(notes, cfg) == [-1, -1]


def test_dedupe_keeps_first_of_each_key():
    from scripts.grove_lab.buckets import dedupe_indices

    # chroma double-indexes some notes (2026-07-12 finding: 3.6% of corpus);
    # identity is the note key, first occurrence wins
    keys = ["a", "b", "a", "", "", "c"]
    assert dedupe_indices(keys) == [0, 1, 3, 4, 5]


def test_project_worktree_variant_folds_into_base(tmp_path):
    """epicmap-claude-worktrees-fix is epicmap work; slug variants fold into
    the declared bucket project (mapdomains.normalize_slug semantics)."""
    cfg = _load(tmp_path)
    notes = [
        Note(cat="memory", project="epicmap-claude-worktrees-fix", theme=None, path="")
    ]
    assert assign(notes, cfg) == [0]
