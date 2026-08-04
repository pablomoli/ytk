"""Cross-linking between a Reddit note and the YouTube video it links to (#163)."""

from __future__ import annotations

from ytk import vault


def test_cross_link_notes_appends_wikilinks_both_ways(tmp_path):
    reddit_note = tmp_path / "reddit-post.md"
    video_note = tmp_path / "video.md"
    reddit_note.write_text("---\nurl: https://old.reddit.com/r/x/1\n---\nbody\n")
    video_note.write_text("---\nurl: https://youtu.be/abc123DEF45\n---\nbody\n")

    vault._cross_link_notes(reddit_note, "https://youtu.be/abc123DEF45", search_dir=tmp_path)
    assert "[[video]]" in reddit_note.read_text()
    assert "[[reddit-post]]" in video_note.read_text()

    # idempotent: a second call adds nothing new
    vault._cross_link_notes(reddit_note, "https://youtu.be/abc123DEF45", search_dir=tmp_path)
    assert reddit_note.read_text().count("[[video]]") == 1
    assert video_note.read_text().count("[[reddit-post]]") == 1


def test_cross_link_notes_no_match_is_a_noop(tmp_path):
    reddit_note = tmp_path / "reddit-post.md"
    reddit_note.write_text("---\nurl: https://old.reddit.com/r/x/1\n---\nbody\n")

    vault._cross_link_notes(reddit_note, "https://youtu.be/nomatch12345", search_dir=tmp_path)
    assert "## Related" not in reddit_note.read_text()
