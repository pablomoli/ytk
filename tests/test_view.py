"""The exam packet (#212): one view per bundle, hashed and immutable, with
one rendered block every reader receives and one grounding string the
deterministic checks tokenize."""

import json
from dataclasses import asdict
from pathlib import Path

from ytk import view as V
from ytk.evidence import EvidenceBundle, evidence_dir


def _bundle(**overrides) -> EvidenceBundle:
    base = {
        "source": "youtube",
        "url": "https://y/1",
        "title": "T",
        "transcript": [
            {"start": 0, "duration": 3, "text": "we built a three-file loop for agents"},
            {"start": 3, "duration": 3, "text": "the grader cannot edit the work script"},
            {"start": 400, "duration": 3, "text": "ripgrep scans the rules markdown fast"},
        ],
        "transcript_origin": "api-manual",
        "transcript_language": "en",
        "transcript_status": "ok",
        "description": "Video about claude-agent-sdk loops.",
        "duration": 613,
        "uploader": "Someone",
    }
    base.update(overrides)
    return EvidenceBundle(**base)


def _write(bundle: EvidenceBundle, item_id: int = 7) -> Path:
    out = evidence_dir() / f"{item_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(asdict(bundle)))
    return out


def test_one_view_per_bundle_hashed_and_reused():
    p = _write(_bundle())
    a = V.ensure_view(7, p)
    b = V.ensure_view(7, p)
    assert a.view_hash == b.view_hash and len(a.view_hash) == 12
    assert a.path.exists() and a.path.name == f"7-{a.bundle_hash}.json"
    other = V.ensure_view(8, _write(_bundle(title="Other"), item_id=8))
    assert other.view_hash != a.view_hash


def test_rendered_transcript_lines_are_timestamped_and_units_are_seconds():
    v = V.build_view(7, _write(_bundle()))
    assert "[0:00] we built a three-file loop for agents" in v.rendered
    assert "[6:40] ripgrep scans the rules markdown fast" in v.rendered
    assert "Uploader: Someone" in v.rendered and "Duration: 613s" in v.rendered
    assert v.has_unit("t:3") and v.has_unit("t:400")
    assert not v.has_unit("t:5000") and not v.has_unit("frame:001") and not v.has_unit("sheet")
    assert [u["id"] for u in v.shown if u["kind"] == "transcript"] == ["t:0-400"]
    assert v.transcript[-1]["text"].startswith("ripgrep")


def test_cap_cuts_the_transcript_and_announces_it():
    seg = [{"start": i, "duration": 1, "text": "word " * 20} for i in range(9000)]
    v = V.build_view(7, _write(_bundle(transcript=seg)))
    assert len(v.rendered) <= V.DEFAULT_BUDGET.evidence_cap_chars + 1000
    assert "not in this packet" in v.rendered
    assert any("transcript" in s for s in v.not_shown)
    last = int(v.transcript[-1]["start"])
    assert v.has_unit(f"t:{last}") and not v.has_unit(f"t:{last + 100}")
    assert len(v.transcript) < len(seg)
    small = V.build_view(7, _write(_bundle(transcript=seg[:3000])))
    assert "not in this packet" not in small.rendered and small.not_shown == []


def test_frames_one_numbering_shown_then_the_box(tmp_path):
    key = tmp_path / "k"
    (key / "shown").mkdir(parents=True)
    (key / "dense").mkdir()
    sparse = []
    for i in range(4):
        p = key / "shown" / f"frame-{i}.jpg"
        p.write_bytes(b"jpeg")
        sparse.append(str(p))
    dense = []
    for i in range(3):
        p = key / "dense" / f"f-{i:03d}.jpg"
        p.write_bytes(b"jpeg")
        dense.append({"t": i * 2.0, "path": str(p)})
    sheet = key / "sheet.jpg"
    sheet.write_bytes(b"jpeg")
    b = _bundle(frames=sparse, dense_frames=dense, sheet=str(sheet))
    p = _write(b)

    v = V.build_view(7, p, budget=V.Budget(sheet="none"))
    assert [u["id"] for u in v.shown if u["kind"] == "frame"] == ["frame:001", "frame:002"]
    assert v.openable == []
    assert v.mounts == [str(key / "shown")]
    assert any("frames 3 to 7" in s for s in v.not_shown)
    assert any("sheet" in s for s in v.not_shown)
    assert f"frame:001 {sparse[0]}" in v.rendered and sparse[2] not in v.rendered
    assert not v.has_unit("frame:005")

    vo = V.build_view(7, p, budget=V.Budget(sheet="openable"))
    assert {u["id"] for u in vo.openable} == {"sheet", *(f"frame:{i:03d}" for i in range(3, 8))}
    assert str(key) in vo.mounts
    assert vo.has_unit("frame:005") and vo.has_unit("sheet")
    assert vo.view_hash != v.view_hash
    assert "In the box" in vo.rendered and str(sheet) in vo.rendered

    vs = V.build_view(7, p)  # the measured default: shown
    assert V.DEFAULT_BUDGET.sheet == "shown"
    assert "sheet" in {u["id"] for u in vs.shown}
    assert "sheet" not in {u["id"] for u in vs.openable}
    assert str(sheet) in vs.rendered and "Frames shown" in vs.rendered


def test_missing_frames_on_disk_are_not_units(tmp_path):
    v = V.build_view(7, _write(_bundle(frames=[str(tmp_path / "gone.jpg")])))
    assert [u for u in v.shown if u["kind"] == "frame"] == [] and v.mounts == []


def test_grounding_text_is_what_was_shown_only():
    b = _bundle(caption="cap words", text="body words")
    v = V.build_view(7, _write(b))
    for s in ("claude-agent-sdk", "cap words", "body words", "ripgrep scans"):
        assert s in v.grounding_text
    assert "frame:" not in v.grounding_text and "Not in this packet" not in v.grounding_text
    assert v.tokenizer == V.TOKENIZER


def test_cites_are_parsed_and_stripped():
    name, cites = V.split_cites("GaussianSplat node: seen on the node graph [frame:002]")
    assert name == "GaussianSplat node: seen on the node graph" and cites == ["frame:002"]
    assert V.split_cites("plain: text") == ("plain: text", [])
    assert V.strip_cites("x [sheet] y [t:12]") == "x y"


def test_load_roundtrip_and_latest():
    v = V.ensure_view(7, _write(_bundle()))
    w = V.load_view(v.path)
    assert w.view_hash == v.view_hash and w.rendered == v.rendered and w.mounts == v.mounts
    assert V.latest_view(7).view_hash == v.view_hash
    assert V.view_by_hash(7, v.view_hash).path == v.path
    assert V.latest_view(99) is None
