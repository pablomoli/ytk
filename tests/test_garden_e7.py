"""E7 manifest: constrained-shuffle controls (Codex G4) + manifest contract.

The control must preserve node count, root degree, depth histogram, and
each parent-slot's child capacity per depth — while actually moving
subtrees (breaking which are adjacent). No hand-selection; seeded.
"""

import numpy as np
import pytest

from scripts.garden_lab.e7_manifest import shuffle_topology, topology_stats

# A 3-level topology: root(0) -> limbs 1,2,3 (child counts 2,1,0) ->
# leaves 4..6. Masses/persistence distinct so payload moves are visible.
NODES = [
    {"id": 0, "parent": -1, "mass": 60, "persistence": 0.2},
    {"id": 1, "parent": 0, "mass": 30, "persistence": 1.0},
    {"id": 2, "parent": 0, "mass": 20, "persistence": 0.8},
    {"id": 3, "parent": 0, "mass": 10, "persistence": 0.5},
    {"id": 4, "parent": 1, "mass": 15, "persistence": 0.6},
    {"id": 5, "parent": 1, "mass": 10, "persistence": 0.4},
    {"id": 6, "parent": 2, "mass": 12, "persistence": 0.3},
]


def test_shuffle_preserves_constrained_stats():
    rng = np.random.default_rng(3)
    control = shuffle_topology(NODES, rng)
    a, b = topology_stats(NODES), topology_stats(control)
    assert a["n_nodes"] == b["n_nodes"]
    assert a["root_degree"] == b["root_degree"]
    assert a["depth_histogram"] == b["depth_histogram"]
    assert a["child_counts_by_depth"] == b["child_counts_by_depth"]
    # every node keeps its own mass/persistence payload
    assert sorted(n["mass"] for n in control) == sorted(n["mass"] for n in NODES)


def test_shuffle_actually_moves_subtrees():
    rng = np.random.default_rng(3)
    moved = 0
    for _ in range(10):
        control = shuffle_topology(NODES, rng)
        orig = {n["id"]: n["parent"] for n in NODES}
        moved += sum(1 for n in control if orig[n["id"]] != n["parent"])
    assert moved > 0  # across 10 seeded draws, parents change


def test_shuffle_rejects_degenerate_topologies():
    sapling = [{"id": 0, "parent": -1, "mass": 5, "persistence": 1.0}]
    with pytest.raises(ValueError):
        shuffle_topology(sapling, np.random.default_rng(0))


# --- manifest v2: Codex v3 blocking fixes (H1/H2/H5/H6/H7/H8) --------------


def _fake_snapshots():
    def snap(nodes, n):
        return {"bucket": "x", "n_notes": n, "built": "t", "embedding_model": "m", "nodes": nodes}

    spread = [  # subs across two limbs: adjacency shuffle possible
        {"id": 0, "parent": -1, "mass": 100, "persistence": 0.2},
        {"id": 1, "parent": 0, "mass": 50, "persistence": 1.0},
        {"id": 2, "parent": 0, "mass": 30, "persistence": 0.8},
        {"id": 3, "parent": 0, "mass": 20, "persistence": 0.5},
        {"id": 4, "parent": 1, "mass": 25, "persistence": 0.6},
        {"id": 5, "parent": 2, "mass": 15, "persistence": 0.4},
    ]
    locked = [  # both subs under one limb: only payload can move (visual-craft)
        {"id": 0, "parent": -1, "mass": 80, "persistence": 0.2},
        {"id": 1, "parent": 0, "mass": 40, "persistence": 1.0},
        {"id": 2, "parent": 0, "mass": 25, "persistence": 0.8},
        {"id": 3, "parent": 0, "mass": 15, "persistence": 0.5},
        {"id": 4, "parent": 1, "mass": 20, "persistence": 0.6},
        {"id": 5, "parent": 1, "mass": 12, "persistence": 0.4},
    ]
    return {
        "epicmap": snap(spread, 2000),
        "ai-building": snap(spread, 400),
        "visual-craft": snap(locked, 80),
    }


def _built():

    from scripts.garden_lab.e7_manifest import build_manifest

    return build_manifest(_fake_snapshots(), seed=9)


def test_public_manifest_leaks_no_roles():
    import json

    public, key = _built()
    for s in public["stimuli"]:
        assert s["id"].startswith("s") and s["id"][1:].isdigit()
    blob = json.dumps(public)
    for marker in ("ctrl", "rerender", '"answer"'):
        assert marker not in blob
    # every scored pair trial has its answer only in the private key
    scored = [t for t in public["trials"] if t["task"] != "practice"]
    assert all(t["trial"] in key["answers"] for t in scored)


def test_blocks_isolate_primary_exposures():
    public, _ = _built()
    tasks = [t["task"] for t in public["trials"]]
    # practice strictly first
    assert tasks[0] == tasks[1] == "practice"
    # the first scored exposure of each bucket is a primary task-1 trial,
    # and all three primaries precede every repeat/T2/T3
    scored = [t for t in public["trials"] if t["task"] != "practice"]
    primaries = [i for i, t in enumerate(scored) if t.get("primary")]
    assert len(primaries) == 3
    assert max(primaries) == 2  # positions 0,1,2 of the scored list
    # exploratory identification runs last
    t3 = [i for i, t in enumerate(scored) if t["task"] == "identification-exploratory"]
    assert min(t3) == len(scored) - len(t3)


def test_left_right_balance_within_pair_blocks():
    public, key = _built()
    for block in ("t1", "t2"):
        pair = [
            t
            for t in public["trials"]
            if t["task"] != "practice" and t["trial"].lower().startswith(block)
        ]
        lefts = sum(1 for t in pair if key["answers"][t["trial"]] == "left")
        assert abs(lefts - (len(pair) - lefts)) <= 1


def test_task1_pairs_share_geometry_and_azimuth_task2_distinct():
    public, _ = _built()
    stim = {s["id"]: s for s in public["stimuli"]}
    for t in public["trials"]:
        if t["task"] == "semantic-readback":
            a, b = stim[t["left"]], stim[t["right"]]
            assert a["geometry_seed"] == b["geometry_seed"]
            assert a["camera_azimuth"] == b["camera_azimuth"]
        if t["task"] == "topology-invariance":
            seeds = {stim[t[k]]["geometry_seed"] for k in ("top", "left", "right")}
            assert len(seeds) == 3


def test_visual_craft_is_payload_construct():
    public, _ = _built()
    t1 = [t for t in public["trials"] if t["task"] == "semantic-readback"]
    assert all(t["construct"] == "payload" for t in t1 if t["bucket"] == "visual-craft")
    assert all(t["construct"] == "adjacency" for t in t1 if t["bucket"] == "epicmap")


# --- scoring: post-run only, per preregistered bands -----------------------


def _fake_run(tmp_path, n_answered=None):
    import json

    public, key = _built()
    scored = [t for t in public["trials"] if t["task"] != "practice"]
    answered = scored if n_answered is None else scored[:n_answered]
    rows = []
    for t in answered:
        rows.append(
            {
                "trial": t["trial"],
                "choice": key["answers"][t["trial"]],
                "confidence": 4,
                "rt_ms": 3000,
                "manifest_sha": public["sha256"],
                "ts": "t",
            }
        )
    (tmp_path / "e7-manifest.json").write_text(json.dumps(public))
    (tmp_path / "e7-answer-key.json").write_text(json.dumps(key))
    (tmp_path / "e7-responses.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return public, key


def test_score_refuses_partial_runs(tmp_path):
    import pytest

    from scripts.garden_lab.e7_score import score

    _fake_run(tmp_path, n_answered=5)
    with pytest.raises(SystemExit):
        score(tmp_path)


def test_score_reports_primaries_and_constructs_separately(tmp_path):
    from scripts.garden_lab.e7_score import score

    _fake_run(tmp_path)  # all answers correct
    result = score(tmp_path)
    t1 = result["semantic_readback"]
    assert t1["primary"]["correct"] == 3 and t1["primary"]["n"] == 3
    # adjacency and payload constructs never pool
    assert t1["adjacency"]["n"] + t1["payload"]["n"] == 9
    assert t1["payload"]["n"] >= 3  # visual-craft trials at minimum
    assert result["topology_invariance"]["correct"] == 9
    assert result["identification_exploratory"]["correct"] == 6
