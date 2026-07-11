from ytk.mapdomains import (
    domain_labels,
    index_domains,
    normalize_slug,
    project_from_path,
)


def test_project_from_summary_filename():
    p = "second-brain/inbox/memories/claude-mem/summaries/summary-2026-02-19-epicmap-503.md"
    assert project_from_path(p) == "epicmap"


def test_project_from_summary_with_hyphenated_name():
    p = "second-brain/inbox/memories/claude-mem/summaries/summary-2026-03-01-Hacklytics-GoldenByte-77.md"
    assert project_from_path(p) == "hacklytics-goldenbyte"


def test_project_from_memories_folder():
    assert project_from_path("second-brain/inbox/memories/ytk/state.md") == "ytk"


def test_project_from_projects_folder():
    assert project_from_path("second-brain/projects/ytk/session-019-brief.md") == "ytk"


def test_project_from_claude_mem_non_summary_is_claude_mem():
    p = "second-brain/inbox/memories/claude-mem/other/note.md"
    assert project_from_path(p) == "claude-mem"


def test_project_from_unrelated_path_is_none():
    assert project_from_path("second-brain/sources/youtube/foo.md") is None
    assert project_from_path("") is None


def test_project_from_untitled_session_summary_is_none():
    p = "second-brain/inbox/memories/claude-mem/summaries/summary-2026-02-28-session-895.md"
    assert project_from_path(p) is None


def test_normalize_slug_strips_user_prefixes():
    assert normalize_slug("users-melocoton-developer-tts", set()) == "tts"
    assert normalize_slug("users-melocoton-config", set()) == "config"


def test_normalize_slug_collapses_worktrees_to_established_project():
    established = {"epicmap"}
    slug = "users-melocoton-developer-epicmap-claude-worktrees-silly-shaw-fb5548"
    assert normalize_slug(slug, established) == "epicmap"
    assert normalize_slug("epicmap-port-tanstack-start", established) == "epicmap"


def test_normalize_slug_no_collapse_without_established_match():
    assert normalize_slug("epicmap-port-tanstack-start", set()) == "epicmap-port-tanstack-start"


def test_domain_labels_end_to_end():
    metas = (
        [{"cat": "memory", "path": f"second-brain/inbox/memories/claude-mem/summaries/summary-2026-01-0{i % 9 + 1}-epicmap-{i}.md", "title": ""} for i in range(50)]
        + [{"cat": "memory", "path": f"second-brain/inbox/memories/claude-mem/summaries/summary-2026-01-0{i % 9 + 1}-tinyproj-{i}.md", "title": ""} for i in range(3)]
        + [{"cat": "youtube", "path": "", "title": "video"} for _ in range(45)]
        + [{"cat": "memo", "path": "second-brain/inbox/memos/m.md", "title": ""}]
    )
    # first 40 youtube points themed to theme 1, remaining 5 unthemed
    content_theme = {50 + 3 + i: (1 if i < 40 else -1) for i in range(45)}
    labels = domain_labels(metas, content_theme, ["go", "creative coding"], min_size=40)
    assert labels[:50] == ["epicmap"] * 50
    assert labels[50] == "other"          # tinyproj: 3 points, below min_size
    assert labels[53] == "creative coding"  # themed content
    assert labels[93] == "other"          # unthemed content
    assert labels[98] == "other"          # memo category


def test_index_domains_orders_by_count_desc():
    dom, meta = index_domains(["a", "b", "b", "b", "other", "a", "b"])
    assert [m["label"] for m in meta] == ["b", "a", "other"]
    assert [m["n"] for m in meta] == [4, 2, 1]
    assert dom == [1, 0, 0, 0, 2, 1, 0]
