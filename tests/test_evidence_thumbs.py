"""Thumbnail durability (#202 follow-up): local evidence thumbnails resolve
to the guarded hub route; URLs pass through; dead paths yield nothing."""

from ytk import evidence


def test_url_passes_through():
    assert (
        evidence.resolve_thumbnail(5, "https://i.ytimg.com/vi/x/hq720.jpg")
        == "https://i.ytimg.com/vi/x/hq720.jpg"
    )


def test_local_file_maps_to_route(tmp_path, monkeypatch):
    monkeypatch.setenv("YTK_EVIDENCE", str(tmp_path))
    f = tmp_path / "thumbs" / "abc.jpg"
    f.parent.mkdir(parents=True)
    f.write_bytes(b"img")
    assert evidence.resolve_thumbnail(7, str(f)) == "/api/evidence/thumb/7"


def test_missing_file_and_junk_yield_none(tmp_path):
    assert evidence.resolve_thumbnail(7, str(tmp_path / "gone.jpg")) is None
    assert evidence.resolve_thumbnail(7, None) is None
    assert evidence.resolve_thumbnail(7, "") is None
