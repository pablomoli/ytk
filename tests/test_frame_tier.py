"""The dense frame tier and the contact sheet (#202): one ruler per medium,
one ffmpeg pass, a sheet that reads a whole reel in one look."""

from __future__ import annotations

import io
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from ytk import vision
from ytk.vision import FramePlan, TimedFrame, contact_sheet, frame_plan, nearest_frames

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def _jpeg(w: int = 64, h: int = 36, color=(200, 40, 40)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="JPEG")
    return buf.getvalue()


# --- the ruler -----------------------------------------------------------


def test_reel_gets_the_time_ruler_every_two_seconds():
    plan = frame_plan(45.0)
    assert plan == FramePlan(ruler="time", every_s=2.0, cap=60)


def test_time_ruler_holds_until_it_would_exceed_the_cap():
    assert frame_plan(120.0).ruler == "time"
    assert frame_plan(121.0).ruler == "scene"


def test_unknown_duration_falls_back_to_the_time_ruler():
    assert frame_plan(None).ruler == "time"


# --- baseline picks come from the tier, not a second ffmpeg pass ----------


def test_nearest_frames_picks_one_tier_frame_per_timestamp_without_duplicates():
    tier = [TimedFrame(t=float(t), data=bytes([t])) for t in (0, 2, 4, 6, 8)]
    picks = nearest_frames(tier, [1.9, 2.1, 7.2])
    assert [p.t for p in picks] == [2.0, 8.0]


# --- the contact sheet ----------------------------------------------------


def test_contact_sheet_tiles_six_across_with_a_label_strip():
    tier = [TimedFrame(t=2.0 * i, data=_jpeg()) for i in range(8)]
    sheet = Image.open(io.BytesIO(contact_sheet(tier, label="ABC", tile_w=64, label_h=10)))
    # 8 frames: two rows, six across; every tile is 64 wide and 36 tall plus its strip
    assert sheet.size == (6 * 64, 2 * (36 + 10))
    # the strip is painted, not left as image data: top-left pixel is the strip's ground
    assert max(sheet.getpixel((0, 0))) < 40  # near-black after JPEG
    assert sheet.getpixel((0, 10))[0] > 150  # the red tile starts below the strip


def test_contact_sheet_of_nothing_is_none():
    assert contact_sheet([], label="x") is None


# --- one ffmpeg pass over a real file ------------------------------------


def _synth(path: Path, seconds: int, colors: list[str]) -> Path:
    """A tiny video made of equal-length solid-color segments (hard cuts)."""
    seg = seconds / len(colors)
    inputs: list[str] = []
    for c in colors:
        inputs += ["-f", "lavfi", "-i", f"color=c={c}:s=160x120:r=5:d={seg}"]
    chain = "".join(f"[{i}:v]" for i in range(len(colors)))
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            *inputs,
            "-filter_complex",
            f"{chain}concat=n={len(colors)}:v=1:a=0[v]",
            "-map",
            "[v]",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path


@needs_ffmpeg
def test_time_ruler_yields_one_frame_every_two_seconds(tmp_path):
    video = _synth(tmp_path / "reel.mp4", 10, ["red"])
    tier = vision.extract_frame_tier(video, frame_plan(10.0), duration=10.0)
    assert [f.t for f in tier] == [0.0, 2.0, 4.0, 6.0, 8.0]
    assert all(Image.open(io.BytesIO(f.data)).width == 160 for f in tier)


@needs_ffmpeg
def test_scene_ruler_keeps_the_frames_where_the_picture_changed(tmp_path):
    # black/white alternation: every boundary is a maximal scene score; softer
    # colour pairs (yellow to white) fall under the threshold and would read as a talk
    colors = ["black", "white"] * 5
    video = _synth(tmp_path / "cast.mp4", 130, colors)
    tier = vision.extract_frame_tier(video, frame_plan(130.0), duration=130.0)
    # the first frame plus one per cut, each landing at a segment boundary (13 s apart)
    assert len(tier) == len(colors)
    assert tier[0].t == 0.0
    for k, f in enumerate(tier[1:], start=1):
        assert abs(f.t - 13.0 * k) < 0.5


@needs_ffmpeg
def test_scene_ruler_on_a_still_picture_falls_back_to_a_dozen_spaced_frames(tmp_path):
    video = _synth(tmp_path / "talk.mp4", 130, ["red"])
    tier = vision.extract_frame_tier(video, frame_plan(130.0), duration=130.0)
    assert len(tier) == vision.TALK_FRAMES
    assert tier[0].t == 0.0


def test_scene_ruler_thins_to_the_cap(monkeypatch, tmp_path):
    # 200 cuts detected: the cap keeps 60, spread evenly, first and last kept
    fake = [TimedFrame(t=float(i), data=b"x") for i in range(200)]
    monkeypatch.setattr(vision, "_scene_pass", lambda video, width: fake)
    tier = vision.extract_frame_tier(tmp_path / "v.mp4", frame_plan(400.0), duration=400.0)
    assert len(tier) == 60
    assert tier[0].t == 0.0 and tier[-1].t == 199.0
