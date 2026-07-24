import pytest

from ytk.enrich import BASE_SKELETON, SOURCE_BIAS, _build_system

SOURCES = ["youtube", "tiktok", "instagram", "instagram_reel", "web", "journal", "reddit"]


def test_every_source_has_a_bias_fragment():
    assert set(SOURCE_BIAS) == set(SOURCES)


@pytest.mark.parametrize("source", SOURCES)
def test_build_system_includes_skeleton_and_bias(source):
    sys = _build_system(source)
    assert BASE_SKELETON in sys
    assert SOURCE_BIAS[source] in sys


def test_tone_prefaces_system_above_skeleton():
    sys = _build_system("youtube", tone="terse and technical")
    assert sys.index("terse and technical") < sys.index(BASE_SKELETON)


def test_no_tone_omits_preamble():
    assert _build_system("web") == _build_system("web", tone="   ")


def test_youtube_bias_keeps_selective_frame_reading():
    assert "ONLY when" in SOURCE_BIAS["youtube"]


def test_instagram_bias_reads_every_slide_and_empties_moments():
    assert "EVERY slide" in SOURCE_BIAS["instagram"]
    assert "empty" in SOURCE_BIAS["instagram"].lower()


def test_unknown_source_raises():
    with pytest.raises(KeyError):
        _build_system("podcast")
