"""Path-dependence replay v2 (post Codex design review, P1-P7)."""

import numpy as np

from scripts.garden_lab.replay import (
    descendant_mass_metric,
    lca_distance_table,
    replay_cell,
)

NODES = [
    {"id": 0, "parent": -1, "mass": 60, "persistence": 0.2},
    {"id": 1, "parent": 0, "mass": 30, "persistence": 1.0},
    {"id": 2, "parent": 0, "mass": 20, "persistence": 0.8},
    {"id": 3, "parent": 1, "mass": 15, "persistence": 0.6},
    {"id": 4, "parent": 1, "mass": 10, "persistence": 0.4},
]


def test_lca_distance_orders_by_tree_closeness():
    d = lca_distance_table(NODES)
    assert d[(3, 4)] < d[(3, 2)]
    assert d[(3, 3)] == 0
    assert d[(2, 4)] == d[(4, 2)]


def test_descendant_mass_metric_reports_coverage_and_magnitude():
    """P4: rank order can be perfect while scales are wrong - L1 must see it."""
    a = [
        {"id": 0, "parent": -1, "mass": 100, "persistence": 1.0},
        {"id": 1, "parent": 0, "mass": 60, "persistence": 1.0},
        {"id": 2, "parent": 0, "mass": 40, "persistence": 1.0},
    ]
    # same members, same rank order, badly rescaled masses
    b = [
        {"id": 0, "parent": -1, "mass": 100, "persistence": 1.0},
        {"id": 1, "parent": 0, "mass": 95, "persistence": 1.0},
        {"id": 2, "parent": 0, "mass": 5, "persistence": 1.0},
    ]
    members_a = {str(i): (1 if i < 60 else 2) for i in range(100)}
    members_b = dict(members_a)
    m = descendant_mass_metric(a, members_a, b, members_b)
    assert m["matched_nodes"] >= 2
    assert m["coverage"] > 0.9
    assert m["spearman"] == 1.0
    assert m["mass_l1"] > 0.3  # |0.6-0.95| + |0.4-0.05| shares


def _blobs(n=200, dim=12, seed=5):
    rng = np.random.default_rng(seed)
    out = [rng.normal(0, 0.5, (n // 2, dim)) + np.eye(dim)[b] * 8 for b in range(2)]
    v = np.vstack(out)
    return v[rng.permutation(len(v))]


def _cell(theta, policy="rebuild", base_frac=0.5, n=200):
    vecs = _blobs(n)
    return replay_cell(
        vecs,
        order=list(range(n)),
        theta=theta,
        policy=policy,
        checkpoints=(0.8, 1.0),
        base_frac=base_frac,
        rng=np.random.default_rng(0),
    )


def test_trigger_positions_use_last_rebuild_denominator():
    """P1: debt = attached_since / n_at_last_rebuild, fires on >= theta.
    n=200, base 100: theta=0.5 fires at attach #50 (n=150), then next at
    150*0.5=75 more -> only one more possible by n=200 (fires exactly at
    the 75th attach... which is position 225 > 200, so exactly 1 rebuild).
    theta=1.0 fires at attach #100 = position 200 (the final note)."""
    c05 = _cell(theta=0.5)
    assert [e["n"] for e in c05["rebuild_events"]] == [150]
    c10 = _cell(theta=1.0)
    assert [e["n"] for e in c10["rebuild_events"]] == [200]
    cnever = _cell(theta=None)
    assert cnever["rebuild_events"] == []


def test_rebuild_events_record_pre_and_post_divergence():
    c = _cell(theta=0.5)
    e = c["rebuild_events"][0]
    assert "pre" in e and "post" in e
    assert e["post"]["assignment_ari"] >= e["pre"]["assignment_ari"] - 0.05


def test_centroid_maintenance_moves_attach_targets():
    """P6: the cm policy updates node centroids online; the frozen policy
    does not. Same data, same order - centroids must differ at the end."""
    frozen = _cell(theta=None, policy="rebuild")
    cm = _cell(theta=None, policy="centroid-maintain")
    assert cm["rebuild_events"] == []
    ca = np.array(frozen["final_centroids"])
    cb = np.array(cm["final_centroids"])
    assert ca.shape == cb.shape
    assert not np.allclose(ca, cb)


def test_checkpoints_carry_both_references_and_triplet_accounting():
    c = _cell(theta=None)
    for cp in c["checkpoints"]:
        assert "production" in cp and "matched_capacity" in cp
        for ref in ("production", "matched_capacity"):
            t = cp[ref]["triplets"]
            assert t["attempted"] == t["usable"] + t["ties"] + t["noninjective"]
            assert cp[ref]["k_main_requested"] >= 3
        # matched-capacity freezes k to the base tree's k
        assert c["base_k_main"] == cp["matched_capacity"]["k_main_used"]


# --- Codex v5 corrections (K2 init bug, K6 floor policy) --------------------


def test_internal_node_centroids_init_from_descendants():
    """K2: a node with no DIRECT members (e.g. a limb whose notes all live
    in its sub-branches) must start with the centroid of its descendant
    mass, never a global-mean pseudo-observation."""
    from scripts.garden_lab.replay import _stamp_centroids, fit_nodes_capacity

    vecs = _blobs(n=200)
    nodes, membership, _ = fit_nodes_capacity(vecs)
    _stamp_centroids(vecs, nodes, membership, mode="descendant")
    by_id = {n["id"]: n for n in nodes}
    kids = {}
    for n in nodes:
        if n["parent"] != -1:
            kids.setdefault(n["parent"], []).append(n["id"])
    for n in nodes:
        if kids.get(n["id"]):
            child_counts = sum(by_id[c]["_count"] for c in kids[n["id"]])
            direct = sum(1 for v in membership.values() if v == n["id"])
            assert n["_count"] == child_counts + direct
            # centroid is the (unnormalized-mean) of descendant sums
            expect = sum((by_id[c]["_sum"] for c in kids[n["id"]]), np.zeros_like(n["_sum"]))
            assert np.allclose(n["_sum"], expect, atol=1e-6) or direct > 0


def test_absolute_debt_floor_delays_small_triggers():
    """K6: hybrid trigger max(theta*n_at_last, floor). n=200, base 100,
    theta=0.25 alone fires at attached=25 (n=125); with floor=40 the first
    fire needs attached>=40 (n=140)."""
    vecs = _blobs(n=200)
    from scripts.garden_lab.replay import replay_cell

    pure = replay_cell(
        vecs,
        order=list(range(200)),
        theta=0.25,
        checkpoints=(1.0,),
        base_frac=0.5,
        rng=np.random.default_rng(0),
    )
    hybrid = replay_cell(
        vecs,
        order=list(range(200)),
        theta=0.25,
        floor=40,
        checkpoints=(1.0,),
        base_frac=0.5,
        rng=np.random.default_rng(0),
    )
    assert pure["rebuild_events"][0]["n"] == 125
    assert hybrid["rebuild_events"][0]["n"] == 140


# --- replay v3 (Codex v6: one engine, production semantics, new arms) -------


def test_production_centroid_mode_matches_dendro_semantics():
    """v6 finding 1: production mode = direct-member means, empty nodes get
    the global mean - exactly what dendro.build_bucket ships. Descendant
    mode exists only for the centroid-maintenance alternative."""
    from scripts.garden_lab.replay import _stamp_centroids, fit_nodes_capacity

    vecs = _blobs(n=200)
    nodes, membership, _ = fit_nodes_capacity(vecs)
    prod = [dict(n) for n in nodes]
    _stamp_centroids(vecs, prod, membership, mode="production")
    from scripts.garden_lab.dendro import _labels_of, _unit

    u = _unit(vecs)
    lab = _labels_of(membership, len(vecs))
    for n in prod:
        mask = lab == n["id"]
        expect = u[mask].mean(axis=0) if mask.any() else u.mean(axis=0)
        assert np.allclose(n["centroid"], expect, atol=1e-6)


def test_terminal_only_attach_never_targets_internal_nodes():
    """v6 finding 9: fresh fits assign notes to terminal nodes only;
    the terminal policy must do the same."""
    from scripts.garden_lab.replay import replay_cell

    vecs = _blobs(n=200)
    cell = replay_cell(
        vecs,
        order=list(range(200)),
        theta=None,
        policy="terminal",
        checkpoints=(1.0,),
        base_frac=0.5,
        rng=np.random.default_rng(0),
    )
    # every attached note must live on a node with no children
    final = cell["checkpoints"][-1]
    assert final["production"]["incremental_nodes"] >= 3
    assert cell["attach_internal_targets"] == 0


def test_persistence_staleness_metric_present():
    """v6 finding 3: branch length (persistence) drift measured across
    matched nodes - rank correlation + normalized L1."""
    from scripts.garden_lab.replay import replay_cell

    vecs = _blobs(n=200)
    cell = replay_cell(
        vecs,
        order=list(range(200)),
        theta=None,
        checkpoints=(1.0,),
        base_frac=0.5,
        rng=np.random.default_rng(0),
    )
    p = cell["checkpoints"][-1]["production"]["persistence"]
    assert set(p) >= {"spearman", "l1_mean", "matched"}
    assert p["matched"] >= 2
    assert p["l1_mean"] >= 0.0


def test_cells_carry_schema_and_engine_stamp():
    from scripts.garden_lab.replay import SCHEMA_VERSION, replay_cell

    vecs = _blobs(n=200)
    cell = replay_cell(
        vecs,
        order=list(range(200)),
        theta=None,
        checkpoints=(1.0,),
        base_frac=0.5,
        rng=np.random.default_rng(0),
    )
    assert cell["schema_version"] == SCHEMA_VERSION >= 3
