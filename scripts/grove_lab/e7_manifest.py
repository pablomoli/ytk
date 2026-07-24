"""E7 readback manifest generator (preregistered protocol, Codex G1/G4/G6).

Builds the immutable trial manifest for /grove?readback=1 from the three
large-bucket snapshots. Controls are constrained shuffles: parent
assignments are permuted WITHIN each depth level, respecting every
parent's child capacity — preserving node count, root degree, depth
histogram, and child-count structure while breaking which subtrees are
adjacent. Each node keeps its own mass/persistence payload. Seeded, no
hand-selection; a control that moves no subtree is rejected and redrawn.

The manifest carries the left/right truth; the hub endpoint strips it
before serving the subject. Refuses to overwrite an existing manifest
without --force (which voids naive-subject status in the log).

Usage:
    uv run --extra dev python -m scripts.grove_lab.e7_manifest [--force]
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

GROVE_DIR = Path.home() / ".ytk" / "grove"
MANIFEST = GROVE_DIR / "e7-manifest.json"  # public, truth-free (H1)
ANSWER_KEY = GROVE_DIR / "e7-answer-key.json"  # private, never served
BUCKETS = ("epicmap", "ai-building", "visual-craft")
TASK1_TRIALS_PER_BUCKET = 3
TASK2_TRIALS_PER_BUCKET = 3
TASK3_TRIALS_PER_BUCKET = 2
ANALYSIS_VERSION = "e7-prereg-2"


# --------------------------------------------------------------------------
# pure topology functions (tested)
# --------------------------------------------------------------------------


def _depths(nodes: list[dict]) -> dict[int, int]:
    parent = {n["id"]: n["parent"] for n in nodes}
    depth: dict[int, int] = {}

    def d(i: int) -> int:
        if i not in depth:
            depth[i] = 0 if parent[i] == -1 else d(parent[i]) + 1
        return depth[i]

    for n in nodes:
        d(n["id"])
    return depth


def topology_stats(nodes: list[dict]) -> dict:
    """The invariants the constrained shuffle must preserve."""
    depth = _depths(nodes)
    kids: dict[int, int] = {}
    for n in nodes:
        if n["parent"] != -1:
            kids[n["parent"]] = kids.get(n["parent"], 0) + 1
    hist: dict[int, int] = {}
    for i in depth:
        hist[depth[i]] = hist.get(depth[i], 0) + 1
    root = next(n["id"] for n in nodes if n["parent"] == -1)
    by_depth: dict[int, list[int]] = {}
    for n in nodes:
        by_depth.setdefault(depth[n["id"]], []).append(kids.get(n["id"], 0))
    return {
        "n_nodes": len(nodes),
        "root_degree": kids.get(root, 0),
        "depth_histogram": dict(sorted(hist.items())),
        "child_counts_by_depth": {d: sorted(c) for d, c in sorted(by_depth.items())},
    }


def shuffle_topology(nodes: list[dict], rng, max_draws: int = 50) -> list[dict]:
    """Constrained control, two move types (both preserve every
    preregistered stratum exactly):

    1. parent permutation within a depth level, respecting each parent's
       child capacity — moves subtrees between limbs;
    2. (mass, persistence) payload permutation within a depth level —
       identical wire topology, but which data occupies which position
       moves (preregistration amendment 2; needed where move 1 is
       identity-locked, e.g. all of a level's children under one parent).

    Both break the joint mass-by-position signature, which is the semantic
    content the control must remove. Raises when nothing can move."""
    depth = _depths(nodes)
    max_depth = max(depth.values())
    if max_depth < 1 or len(nodes) < 5:
        raise ValueError("topology too small for a constrained shuffle")
    capacity: dict[int, int] = {}
    for n in nodes:
        if n["parent"] != -1:
            capacity[n["parent"]] = capacity.get(n["parent"], 0) + 1
    orig_parent = {n["id"]: n["parent"] for n in nodes}
    orig_payload = {n["id"]: (n["mass"], n["persistence"]) for n in nodes}

    best_payload_only = None
    for _ in range(max_draws):
        new_parent: dict[int, int] = {}
        new_payload: dict[int, tuple] = {}
        for level in range(1, max_depth + 1):
            children = [n["id"] for n in nodes if depth[n["id"]] == level]
            slots: list[int] = []
            for pid, cap in capacity.items():
                if depth[pid] == level - 1:
                    slots.extend([pid] * cap)
            perm = rng.permutation(len(slots))
            for child, s in zip(children, perm):
                new_parent[child] = slots[int(s)]
            payloads = [orig_payload[c] for c in children]
            pperm = rng.permutation(len(payloads))
            for child, s in zip(children, pperm):
                new_payload[child] = payloads[int(s)]
        control = []
        for n in nodes:
            mass, persistence = new_payload.get(n["id"], orig_payload[n["id"]])
            control.append(
                {
                    **n,
                    "parent": new_parent.get(n["id"], n["parent"]),
                    "mass": mass,
                    "persistence": persistence,
                }
            )
        parents_moved = any(n["parent"] != orig_parent[n["id"]] for n in control)
        payload_moved = any((n["mass"], n["persistence"]) != orig_payload[n["id"]] for n in control)
        # adjacency-breaking controls are the stronger construct (Codex H8):
        # accept the first parent-moving draw; keep a payload-only draw as
        # fallback for identity-locked topologies
        if parents_moved:
            return control
        if payload_moved and best_payload_only is None:
            best_payload_only = control
    if best_payload_only is not None:
        return best_payload_only
    raise ValueError("no moving shuffle found (topology may be a path)")


def parents_differ(a: list[dict], b: list[dict]) -> bool:
    """True when the two node lists disagree on any parent link — i.e. the
    control breaks adjacency, not just payload placement (Codex H8)."""
    pa = {n["id"]: n["parent"] for n in a}
    return any(pa[n["id"]] != n["parent"] for n in b)


# --------------------------------------------------------------------------
# manifest assembly
# --------------------------------------------------------------------------


def _synthetic_practice(rng) -> list[dict]:
    """Two small random trees unrelated to any bucket, for warm-up."""
    trees = []
    for t in range(2):
        nodes = [{"id": 0, "parent": -1, "mass": 40, "persistence": 0.3}]
        nid = 1
        for limb in range(int(3 + rng.integers(0, 2))):
            nodes.append(
                {
                    "id": nid,
                    "parent": 0,
                    "mass": int(10 + rng.integers(0, 15)),
                    "persistence": float(0.4 + rng.random() * 0.6),
                }
            )
            limb_id = nid
            nid += 1
            for _ in range(int(rng.integers(0, 3))):
                nodes.append(
                    {
                        "id": nid,
                        "parent": limb_id,
                        "mass": int(3 + rng.integers(0, 6)),
                        "persistence": float(0.2 + rng.random() * 0.4),
                    }
                )
                nid += 1
        trees.append(nodes)
    return trees


def build_manifest(snapshots: dict[str, dict], seed: int = 71) -> tuple[dict, dict]:
    """Returns (public_manifest, answer_key). Deterministic given seed.

    Codex v3 contract: the public manifest carries opaque stimulus ids
    (s<N>) and NO correctness anywhere; answers + the opaque-to-private id
    map live only in the answer key. Trials run in blocks (H2/H6/H7):
    practice -> one primary task-1 exposure per bucket -> task-1 repeats
    -> task 2 -> exploratory identification. Task-1 pairs share geometry
    seed and camera azimuth (H5: only structure may differ); task-2
    stimuli get distinct geometry seeds (rerender invariance IS the
    construct) with explicit azimuths.
    """
    rng = np.random.default_rng(seed)
    private: list[dict] = []  # {label, nodes, n_notes, geometry_seed, camera_azimuth}
    answers: dict[str, str] = {}

    def add_stim(label, nodes, n_notes, geometry_seed=None, azimuth=None):
        private.append(
            {
                "label": label,
                "nodes": nodes,
                "n_notes": n_notes,
                "geometry_seed": int(
                    geometry_seed if geometry_seed is not None else rng.integers(1, 1_000_000)
                ),
                "camera_azimuth": round(
                    float(azimuth if azimuth is not None else rng.random() * 2 * np.pi), 4
                ),
            }
        )
        return label

    def balanced_sides(n):
        sides = ["left"] * ((n + 1) // 2) + ["right"] * (n // 2)
        return [sides[int(i)] for i in rng.permutation(n)]

    strip = lambda ns: [{k: n[k] for k in ("id", "parent", "mass", "persistence")} for n in ns]

    # practice (synthetic, unscored)
    practice: list[dict] = []
    for i, tree in enumerate(_synthetic_practice(rng)):
        gseed, az = int(rng.integers(1, 1_000_000)), float(rng.random() * 2 * np.pi)
        a = add_stim(f"practice{i}-a", tree, 40, gseed, az)
        b = add_stim(f"practice{i}-b", shuffle_topology(tree, rng), 40, gseed, az)
        flip = rng.random() < 0.5
        practice.append(
            {
                "trial": f"P{i}",
                "task": "practice",
                "bucket": None,
                "left": b if flip else a,
                "right": a if flip else b,
                "prompt": "warm-up: pick either tree",
            }
        )

    # task 1: 9 trials, sides balanced; pairs share geometry seed + azimuth
    t1_sides = balanced_sides(len(BUCKETS) * TASK1_TRIALS_PER_BUCKET)
    t1_by_bucket: dict[str, list[dict]] = {}
    side_i = 0
    for bucket in BUCKETS:
        snap = snapshots[bucket]
        true_nodes = strip(snap["nodes"])
        n = snap["n_notes"]
        t1_by_bucket[bucket] = []
        for k in range(TASK1_TRIALS_PER_BUCKET):
            gseed = int(rng.integers(1, 1_000_000))
            az = float(rng.random() * 2 * np.pi)
            true_id = add_stim(f"{bucket}-t1-{k}-true", true_nodes, n, gseed, az)
            control = shuffle_topology(true_nodes, rng)
            ctrl_id = add_stim(f"{bucket}-t1-{k}-ctrl", control, n, gseed, az)
            side = t1_sides[side_i]
            side_i += 1
            trial_id = f"T1-{bucket}-{k}"
            answers[trial_id] = side
            t1_by_bucket[bucket].append(
                {
                    "trial": trial_id,
                    "task": "semantic-readback",
                    "bucket": bucket,
                    "primary": k == 0,
                    "construct": "adjacency" if parents_differ(true_nodes, control) else "payload",
                    "left": true_id if side == "left" else ctrl_id,
                    "right": ctrl_id if side == "left" else true_id,
                    "prompt": f"which is your {bucket} tree?",
                }
            )

    # task 2: anchor + rerender vs control; three distinct geometry seeds
    t2_sides = balanced_sides(len(BUCKETS) * TASK2_TRIALS_PER_BUCKET)
    t2: list[dict] = []
    side_i = 0
    for bucket in BUCKETS:
        snap = snapshots[bucket]
        true_nodes = strip(snap["nodes"])
        n = snap["n_notes"]
        for k in range(TASK2_TRIALS_PER_BUCKET):
            anchor = add_stim(f"{bucket}-t2-{k}-anchor", true_nodes, n)
            rerender = add_stim(f"{bucket}-t2-{k}-rerender", true_nodes, n)
            ctrl = add_stim(f"{bucket}-t2-{k}-ctrl", shuffle_topology(true_nodes, rng), n)
            side = t2_sides[side_i]
            side_i += 1
            trial_id = f"T2-{bucket}-{k}"
            answers[trial_id] = side
            t2.append(
                {
                    "trial": trial_id,
                    "task": "topology-invariance",
                    "bucket": bucket,
                    "top": anchor,
                    "left": rerender if side == "left" else ctrl,
                    "right": ctrl if side == "left" else rerender,
                    "prompt": "which candidate shares the anchor's structure?",
                }
            )

    # task 3: exploratory 3-AFC identification, strictly last
    t3: list[dict] = []
    for bucket in BUCKETS:
        snap = snapshots[bucket]
        for k in range(TASK3_TRIALS_PER_BUCKET):
            sid = add_stim(f"{bucket}-t3-{k}", strip(snap["nodes"]), snap["n_notes"])
            trial_id = f"T3-{bucket}-{k}"
            answers[trial_id] = bucket
            t3.append(
                {
                    "trial": trial_id,
                    "task": "identification-exploratory",
                    "bucket": bucket,
                    "single": sid,
                    "options": list(BUCKETS),
                    "prompt": "which of your topics is this tree?",
                }
            )

    # block order (H2/H6): primaries first in randomized bucket order, then
    # remaining task-1 repeats, then task 2, then exploratory — randomized
    # within each block only
    def shuffled(items):
        return [items[int(i)] for i in rng.permutation(len(items))]

    bucket_order = shuffled(list(BUCKETS))
    primaries = [t1_by_bucket[b][0] for b in bucket_order]
    repeats = shuffled([t for b in BUCKETS for t in t1_by_bucket[b][1:]])
    ordered = practice + primaries + repeats + shuffled(t2) + shuffled(t3)

    # opaque public ids (H1): seeded permutation over creation order
    perm = rng.permutation(len(private))
    public_id = {private[int(p)]["label"]: f"s{i:02d}" for i, p in enumerate(perm)}
    stimuli = [
        {
            "id": public_id[s["label"]],
            "nodes": s["nodes"],
            "n_notes": s["n_notes"],
            "geometry_seed": s["geometry_seed"],
            "camera_azimuth": s["camera_azimuth"],
        }
        for s in sorted(private, key=lambda s: public_id[s["label"]])
    ]
    for t in ordered:
        for field in ("left", "right", "top", "single"):
            if field in t and t[field] is not None:
                t[field] = public_id[t[field]]

    public = {
        "version": 2,
        "analysis_version": ANALYSIS_VERSION,
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
        "seed": seed,
        "buckets": {
            b: {
                "built": snapshots[b].get("built"),
                "embedding_model": snapshots[b].get("embedding_model"),
            }
            for b in BUCKETS
        },
        "render": {
            "neutral_tint": True,
            "normalized_scale": True,
            "note": "task-1 pairs share geometry seed + camera azimuth "
            "so only structure differs; task-2 stimuli carry "
            "independent geometry seeds (render invariance is "
            "the construct) - preregistration amendment 4",
        },
        "stimuli": stimuli,
        "trials": ordered,
    }
    public["sha256"] = hashlib.sha256(json.dumps(public, sort_keys=True).encode()).hexdigest()
    key = {
        "public_sha256": public["sha256"],
        "seed": seed,
        "answers": answers,
        "id_map": {v: k for k, v in public_id.items()},
    }
    return public, key


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--force",
        action="store_true",
        help="overwrite an existing manifest (voids naive-subject status)",
    )
    ap.add_argument("--seed", type=int, default=71)
    args = ap.parse_args()

    if (MANIFEST.exists() or ANSWER_KEY.exists()) and not args.force:
        raise SystemExit(f"{MANIFEST} exists; --force voids naive-subject status")
    snapshots = {}
    for b in BUCKETS:
        p = GROVE_DIR / f"{b}.tree.json"
        if not p.exists():
            raise SystemExit(f"missing snapshot {p}; run scripts.grove_lab.dendro first")
        snapshots[b] = json.loads(p.read_text())
    public, key = build_manifest(snapshots, seed=args.seed)
    forced = " (FORCED - naive status voided)" if MANIFEST.exists() else ""
    MANIFEST.write_text(json.dumps(public))
    ANSWER_KEY.write_text(json.dumps(key))
    n_main = sum(1 for t in public["trials"] if t["task"] != "practice")
    print(
        f"wrote {MANIFEST}{forced} + answer key: {len(public['stimuli'])} stimuli, "
        f"{n_main} scored trials + practice, sha256 {public['sha256'][:16]}"
    )


if __name__ == "__main__":
    main()
