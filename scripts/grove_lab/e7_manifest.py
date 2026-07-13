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
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

GROVE_DIR = Path.home() / ".ytk" / "grove"
MANIFEST = GROVE_DIR / "e7-manifest.json"
BUCKETS = ("epicmap", "ai-building", "visual-craft")
TASK1_TRIALS_PER_BUCKET = 3
TASK2_TRIALS_PER_BUCKET = 3
TASK3_TRIALS_PER_BUCKET = 2
ANALYSIS_VERSION = "e7-prereg-1"


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
            control.append({**n, "parent": new_parent.get(n["id"], n["parent"]),
                            "mass": mass, "persistence": persistence})
        moved = sum(
            1 for n in control
            if n["parent"] != orig_parent[n["id"]]
            or (n["mass"], n["persistence"]) != orig_payload[n["id"]]
        )
        if moved > 0:
            return control
    raise ValueError("no moving shuffle found (topology may be a path)")


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
            nodes.append({"id": nid, "parent": 0, "mass": int(10 + rng.integers(0, 15)),
                          "persistence": float(0.4 + rng.random() * 0.6)})
            limb_id = nid
            nid += 1
            for _ in range(int(rng.integers(0, 3))):
                nodes.append({"id": nid, "parent": limb_id,
                              "mass": int(3 + rng.integers(0, 6)),
                              "persistence": float(0.2 + rng.random() * 0.4)})
                nid += 1
        trees.append(nodes)
    return trees


def _stimulus(sid: str, nodes: list[dict], n_notes: int, render_seed: int) -> dict:
    return {"id": sid, "nodes": nodes, "n_notes": n_notes, "render_seed": render_seed}


def build_manifest(snapshots: dict[str, dict], seed: int = 71) -> dict:
    """snapshots: bucket -> loaded tree.json. Deterministic given seed."""
    rng = np.random.default_rng(seed)
    stimuli: list[dict] = []
    trials: list[dict] = []

    def add_stim(sid, nodes, n_notes):
        stimuli.append(_stimulus(sid, nodes, n_notes, int(rng.integers(1, 1_000_000))))
        return sid

    # practice (synthetic, excluded from analysis)
    for i, tree in enumerate(_synthetic_practice(rng)):
        true_id = add_stim(f"practice{i}-true", tree, 40)
        ctrl_id = add_stim(f"practice{i}-ctrl", shuffle_topology(tree, rng), 40)
        trials.append({"trial": f"P{i}", "task": "practice", "bucket": None,
                       "left": true_id if rng.random() < 0.5 else ctrl_id,
                       "prompt": "warm-up: pick either tree"})
    for t in trials:  # fill right side for practice
        pair = [s["id"] for s in stimuli if s["id"].startswith(t["trial"].replace("P", "practice"))]
        t["right"] = pair[1] if t["left"] == pair[0] else pair[0]

    strip = lambda ns: [{k: n[k] for k in ("id", "parent", "mass", "persistence")} for n in ns]

    # task 1 (semantic readback) + task 2 (topology invariance)
    for bucket in BUCKETS:
        snap = snapshots[bucket]
        true_nodes = strip(snap["nodes"])
        n = snap["n_notes"]
        for k in range(TASK1_TRIALS_PER_BUCKET):
            true_id = add_stim(f"{bucket}-t1-{k}-true", true_nodes, n)
            ctrl_id = add_stim(f"{bucket}-t1-{k}-ctrl", shuffle_topology(true_nodes, rng), n)
            left_is_true = bool(rng.random() < 0.5)
            trials.append({
                "trial": f"T1-{bucket}-{k}", "task": "semantic-readback",
                "bucket": bucket,
                "left": true_id if left_is_true else ctrl_id,
                "right": ctrl_id if left_is_true else true_id,
                "answer": "left" if left_is_true else "right",
                "prompt": f"which is your {bucket} tree?",
            })
        for k in range(TASK2_TRIALS_PER_BUCKET):
            anchor = add_stim(f"{bucket}-t2-{k}-anchor", true_nodes, n)
            rerender = add_stim(f"{bucket}-t2-{k}-rerender", true_nodes, n)
            ctrl = add_stim(f"{bucket}-t2-{k}-ctrl", shuffle_topology(true_nodes, rng), n)
            left_is_rerender = bool(rng.random() < 0.5)
            trials.append({
                "trial": f"T2-{bucket}-{k}", "task": "topology-invariance",
                "bucket": bucket, "anchor": anchor,
                "left": rerender if left_is_rerender else ctrl,
                "right": ctrl if left_is_rerender else rerender,
                "answer": "left" if left_is_rerender else "right",
                "prompt": "which candidate shares the anchor's structure?",
            })

    # task 3: exploratory 3-AFC identification (isolated true trees)
    for bucket in BUCKETS:
        snap = snapshots[bucket]
        for k in range(TASK3_TRIALS_PER_BUCKET):
            sid = add_stim(f"{bucket}-t3-{k}", strip(snap["nodes"]), snap["n_notes"])
            trials.append({
                "trial": f"T3-{bucket}-{k}", "task": "identification-exploratory",
                "bucket": bucket, "single": sid, "answer": bucket,
                "options": list(BUCKETS),
                "prompt": "which of your topics is this tree?",
            })

    # order: practice first, then main tasks interleaved by seeded shuffle,
    # balanced early/late per (task, bucket) by alternating block draw
    main = [t for t in trials if t["task"] != "practice"]
    practice = [t for t in trials if t["task"] == "practice"]
    order = rng.permutation(len(main))
    ordered = practice + [main[int(i)] for i in order]

    manifest = {
        "version": 1,
        "analysis_version": ANALYSIS_VERSION,
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seed": seed,
        "buckets": {b: {"built": snapshots[b].get("built"),
                        "embedding_model": snapshots[b].get("embedding_model")}
                    for b in BUCKETS},
        "render": {"neutral_tint": True, "normalized_scale": True,
                   "note": "single-bucket payloads render scale-normalized and "
                           "identically tinted by construction; per-stimulus "
                           "render_seed doubles as azimuth randomization "
                           "(isotropic fork azimuths) - preregistration amendment 1"},
        "stimuli": stimuli,
        "trials": ordered,
    }
    canonical = json.dumps(manifest, sort_keys=True).encode()
    manifest["sha256"] = hashlib.sha256(canonical).hexdigest()
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="overwrite an existing manifest (voids naive-subject status)")
    ap.add_argument("--seed", type=int, default=71)
    args = ap.parse_args()

    if MANIFEST.exists() and not args.force:
        raise SystemExit(f"{MANIFEST} exists; --force voids naive-subject status")
    snapshots = {}
    for b in BUCKETS:
        p = GROVE_DIR / f"{b}.tree.json"
        if not p.exists():
            raise SystemExit(f"missing snapshot {p}; run scripts.grove_lab.dendro first")
        snapshots[b] = json.loads(p.read_text())
    manifest = build_manifest(snapshots, seed=args.seed)
    forced = " (FORCED - naive status voided)" if MANIFEST.exists() else ""
    MANIFEST.write_text(json.dumps(manifest))
    n_main = sum(1 for t in manifest["trials"] if t["task"] != "practice")
    print(f"wrote {MANIFEST}{forced}: {len(manifest['stimuli'])} stimuli, "
          f"{n_main} scored trials + practice, sha256 {manifest['sha256'][:16]}")


if __name__ == "__main__":
    main()
