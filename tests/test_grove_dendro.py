"""Condensed-tree topology: conversion, incremental attach, anchored rebuild.

The tree cache contract (standing decision, 2026-07-12): a grove tree may
grow between builds but never reshuffle. Default build attaches new notes to
existing branches; a full rebuild re-derives but keeps node identities via
member-overlap anchoring.
"""

import numpy as np

from scripts.grove_lab.dendro import (
    anchor_nodes,
    attach_new_notes,
    fit_nodes,
)


def _three_blob_data(n_per=40, dim=16, seed=3):
    """Three well-separated blobs on the unit sphere."""
    rng = np.random.default_rng(seed)
    blobs = []
    for axis in range(3):
        center = np.zeros(dim)
        center[axis] = 10.0
        blobs.append(rng.normal(0, 0.5, (n_per, dim)) + center)
    return np.vstack(blobs)


def test_fit_nodes_recovers_three_limbs():
    vecs = _three_blob_data()
    nodes, membership, params = fit_nodes(vecs)
    assert params["kind"] == "linkage"
    roots = [n for n in nodes if n["parent"] == -1]
    assert len(roots) == 1
    limbs = [n for n in nodes if n["parent"] == roots[0]["id"]]
    assert len(limbs) == 3
    assert sorted(l["mass"] for l in limbs) == [40, 40, 40]
    # every point has a home and limbs have positive length
    assert len(membership) == 120
    assert all(l["persistence"] > 0 for l in limbs)


def test_fit_nodes_membership_matches_blobs():
    vecs = _three_blob_data()
    _, membership, _ = fit_nodes(vecs)
    # points of one blob share a node
    first_blob_nodes = {membership[i] for i in range(40)}
    assert len(first_blob_nodes) <= 2  # one limb (or limb + its sub-branch)


def test_fit_nodes_sapling_below_floor():
    vecs = np.random.default_rng(0).normal(0, 1, (10, 8))
    nodes, membership, params = fit_nodes(vecs)
    assert params["kind"] == "sapling"
    assert len(nodes) == 1
    assert nodes[0]["mass"] == 10


def test_attach_new_notes_goes_to_nearest_node_and_grows_mass():
    rng = np.random.default_rng(0)
    a = rng.normal(0, 1, (4, 8)) + np.array([10] + [0] * 7)
    b = rng.normal(0, 1, (4, 8)) + np.array([0] * 7 + [10])
    nodes = [
        {"id": 0, "parent": -1, "mass": 8, "persistence": 1.0,
         "centroid": ((a.mean(0) + b.mean(0)) / 2).tolist()},
        {"id": 1, "parent": 0, "mass": 4, "persistence": 1.0, "centroid": a.mean(0).tolist()},
        {"id": 2, "parent": 0, "mass": 4, "persistence": 1.0, "centroid": b.mean(0).tolist()},
    ]
    members = {"old1": 1}
    new_vec = (a.mean(0) + rng.normal(0, 0.1, 8)).reshape(1, -1)
    added = attach_new_notes(nodes, members, new_vec, ["fresh-note"])
    assert added == 1
    assert members["fresh-note"] == 1
    assert nodes[1]["mass"] == 5
    # ancestors grow too
    assert nodes[0]["mass"] == 9


def test_attach_is_idempotent_for_known_notes():
    nodes = [{"id": 0, "parent": -1, "mass": 3, "persistence": 1.0,
              "centroid": [1.0, 0.0]}]
    members = {"known": 0}
    added = attach_new_notes(nodes, members, np.array([[1.0, 0.0]]), ["known"])
    assert added == 0
    assert nodes[0]["mass"] == 3


def test_anchor_nodes_keeps_ids_by_member_overlap():
    old_members = {f"n{i}": (1 if i < 10 else 2) for i in range(20)}
    # rebuild found the same two groups but numbered them differently,
    # with one note having switched sides
    new_members = {f"n{i}": (7 if i < 9 else 5) for i in range(20)}
    mapping = anchor_nodes(old_members, new_members)
    assert mapping[7] == 1
    assert mapping[5] == 2
