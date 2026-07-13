"""E7 manifest: constrained-shuffle controls (Codex G4) + manifest contract.

The control must preserve node count, root degree, depth histogram, and
each parent-slot's child capacity per depth — while actually moving
subtrees (breaking which are adjacent). No hand-selection; seeded.
"""

import numpy as np
import pytest

from scripts.grove_lab.e7_manifest import shuffle_topology, topology_stats

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
