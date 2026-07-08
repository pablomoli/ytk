from ytk.enrich import BASE_SKELETON


def test_no_flat_cap_of_eight():
    assert "Max 8" not in BASE_SKELETON
    assert "max 8" not in BASE_SKELETON.lower()


def test_has_densification_instruction():
    low = BASE_SKELETON.lower()
    assert "dense" in low or "densif" in low
    assert "missed" in low or "missing" in low  # the CoD "entities you left out" pass


def test_scales_to_content_length():
    assert "scale" in BASE_SKELETON.lower() or "as many as" in BASE_SKELETON.lower()
