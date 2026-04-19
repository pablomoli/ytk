from __future__ import annotations


def test_write_instagram_note_creates_file(tmp_path, monkeypatch):
    from ytk.instagram import InstagramPost
    from ytk.enrich import Enrichment, KeyMoment
    from ytk.vault import write_instagram_note

    monkeypatch.setattr("ytk.vault._get_vault_path", lambda: tmp_path)

    post = InstagramPost(
        url="https://www.instagram.com/p/ABC123/",
        username="testuser",
        timestamp="2026-04-19",
        caption="Golden hour vibes in the canyon",
        images=["https://cdn.instagram.com/img.jpg"],
    )
    enrichment = Enrichment(
        thesis="Photographer captures golden hour light through a canyon.",
        summary="A striking image showing warm directional light filtering through sandstone walls.",
        key_concepts=["golden hour: warm diffuse light in the hour after sunrise"],
        insights=["Side lighting reveals texture that flat midday light would hide."],
        interest_tags=["photography", "landscape"],
        key_moments=[KeyMoment(timestamp="img-1", description="main composition")],
    )

    path = write_instagram_note(post, enrichment)

    assert path.exists()
    assert path.parent == tmp_path / "sources" / "instagram"
    content = path.read_text(encoding="utf-8")
    assert "url: https://www.instagram.com/p/ABC123/" in content
    assert "username: testuser" in content
    assert "date: 2026-04-19" in content
    assert "type: instagram" in content
    assert "photography" in content
    assert "golden hour light through a canyon" in content
    assert "img-1" in content
    assert "## Key Moments" in content


def test_write_instagram_note_filename_uses_username_date_slug(tmp_path, monkeypatch):
    from ytk.instagram import InstagramPost
    from ytk.enrich import Enrichment
    from ytk.vault import write_instagram_note

    monkeypatch.setattr("ytk.vault._get_vault_path", lambda: tmp_path)

    post = InstagramPost(
        url="https://www.instagram.com/p/XYZ/",
        username="artaccount",
        timestamp="2026-04-19",
        caption="My new painting: abstract blues",
        images=[],
    )
    enrichment = Enrichment(
        thesis="Abstract blue painting.",
        summary="Acrylic on canvas with layered blues.",
        key_concepts=[],
        insights=[],
        interest_tags=["art"],
        key_moments=[],
    )

    path = write_instagram_note(post, enrichment)
    # New format: {username}-{timestamp}-{shortcode}-{slug}
    assert path.stem.startswith("artaccount-2026-04-19-XYZ-")


def test_write_instagram_note_no_moments_omits_section(tmp_path, monkeypatch):
    from ytk.instagram import InstagramPost
    from ytk.enrich import Enrichment
    from ytk.vault import write_instagram_note

    monkeypatch.setattr("ytk.vault._get_vault_path", lambda: tmp_path)

    post = InstagramPost(
        url="https://www.instagram.com/p/NM/",
        username="user",
        timestamp="2026-04-19",
        caption="",
        images=[],
    )
    enrichment = Enrichment(
        thesis="t", summary="s", key_concepts=[], insights=[], interest_tags=[], key_moments=[]
    )

    path = write_instagram_note(post, enrichment)
    content = path.read_text(encoding="utf-8")
    assert "## Key Moments" not in content


def test_write_instagram_note_empty_caption_uses_username_fallback(tmp_path, monkeypatch):
    from ytk.instagram import InstagramPost
    from ytk.enrich import Enrichment
    from ytk.vault import write_instagram_note

    monkeypatch.setattr("ytk.vault._get_vault_path", lambda: tmp_path)

    post = InstagramPost(
        url="https://www.instagram.com/reel/ABC/",
        username="reelaccount",
        timestamp="2026-04-19",
        caption="",
        images=[],
    )
    enrichment = Enrichment(
        thesis="t", summary="s", key_concepts=[], insights=[], interest_tags=[], key_moments=[]
    )

    path = write_instagram_note(post, enrichment)
    assert "reelaccount" in path.stem


def test_write_instagram_note_shortcode_prevents_overwrite(tmp_path, monkeypatch):
    from ytk.instagram import InstagramPost
    from ytk.enrich import Enrichment
    from ytk.vault import write_instagram_note

    monkeypatch.setattr("ytk.vault._get_vault_path", lambda: tmp_path)

    base = dict(
        username="user",
        timestamp="2026-04-19",
        caption="same caption",
        images=[],
    )
    enrichment = Enrichment(
        thesis="t", summary="s", key_concepts=[], insights=[], interest_tags=[], key_moments=[]
    )

    post1 = InstagramPost(url="https://www.instagram.com/p/AAA111/", **base)
    post2 = InstagramPost(url="https://www.instagram.com/p/BBB222/", **base)

    path1 = write_instagram_note(post1, enrichment)
    path2 = write_instagram_note(post2, enrichment)

    assert path1 != path2
    assert path1.exists()
    assert path2.exists()
