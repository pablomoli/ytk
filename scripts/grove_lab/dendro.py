"""Data-native tree topology per grove bucket (E2).

Renders the bucket's cluster hierarchy AS the branch structure: average-
linkage agglomerative clustering on cosine distances in native 384-dim
gte-small space. Branch length = persistence in dendrogram height (the span
between the merge that forms a cluster and the merge that absorbs it),
girth = point mass, every note lands on a branch.

Method choice is experimental, not aesthetic (2026-07-12 shootout, transfer
ARI on random halves): agglo-cosine 0.75/0.88 on ai-building/visual-craft vs
HDBSCAN-native 0.10/0.34 and HDBSCAN-on-UMAP15 0.53/0.25 — HDBSCAN's density
estimator is unreliable in 384 dims. epicmap fails under every method at
every granularity (ARI <= 0.25): its 2,066 session summaries have no
reproducible sub-structure, so its branches are cached decoration and are
reported as such.

Cache contract (standing decision, 2026-07-12): trees grow, never reshuffle.
  default   - incremental: new notes attach to the nearest existing node
  --rebuild - re-derive, then anchor node ids to the previous snapshot by
              member overlap (Jaccard, greedy best-first — the map's
              anchor_names precedent)

Snapshots: ~/.ytk/grove/{bucket}.tree.json, stamped with the embedding model;
a model swap invalidates the cache (standing decision 3).

Stability gate: split-half cross-transfer ARI (temporal halves where the
bucket spans >= 21 days, bootstrap halves otherwise — labeled, not hidden).

Usage:
    uv run --extra dev python -m scripts.grove_lab.dendro [--rebuild] [--stability]
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from ytk.store import _TEXT_MODEL

GROVE_DIR = Path.home() / ".ytk" / "grove"
MIN_CLUSTER_NOTES = 30   # below this a tree is a trunk + n leaves (sapling)
MIN_SPAN_DAYS = 21       # temporal halves only where real time passed
SAPLING_ROOT = 0


def _unit(m: np.ndarray) -> np.ndarray:
    return m / np.linalg.norm(m, axis=1, keepdims=True).clip(1e-12)


# --------------------------------------------------------------------------
# pure topology functions (tested)
# --------------------------------------------------------------------------

def _formation_heights(Z: np.ndarray, labels: np.ndarray) -> dict[int, float]:
    """Height at which each labeled cluster finishes forming: the highest
    merge whose two sides both lie entirely inside that cluster's label."""
    n = len(labels)
    span: dict[int, set] = {i: {int(labels[i])} for i in range(n)}
    form = {int(c): 0.0 for c in set(labels.tolist())}
    for m, (a, b, h, _) in enumerate(Z):
        s = span.pop(int(a)) | span.pop(int(b))
        span[n + m] = s
        if len(s) == 1:
            c = next(iter(s))
            form[c] = max(form[c], float(h))
    return form


def fit_nodes(vecs: np.ndarray):
    """Two-level linkage topology for one bucket: root -> main limbs ->
    sub-branches where a limb has the mass to support them.
    Saplings (n < MIN_CLUSTER_NOTES) skip clustering."""
    n = len(vecs)
    if n < MIN_CLUSTER_NOTES:
        return (
            [{"id": SAPLING_ROOT, "parent": -1, "mass": n, "persistence": 1.0}],
            {i: SAPLING_ROOT for i in range(n)},
            {"kind": "sapling"},
        )
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import pdist

    u = _unit(vecs)
    Z = linkage(pdist(u, metric="cosine"), method="average")
    k = int(np.clip(n // 80, 3, 9))
    main = fcluster(Z, k, criterion="maxclust")
    root_h = float(Z[-1, 2])
    form = _formation_heights(Z, main)

    nodes = [{"id": 0, "parent": -1, "mass": n, "persistence": root_h * 0.15}]
    membership: dict[int, int] = {}
    next_id = 1
    for c in sorted(set(main.tolist())):
        idx = np.flatnonzero(main == c)
        limb_id = next_id
        next_id += 1
        nodes.append({
            "id": limb_id, "parent": 0, "mass": int(len(idx)),
            "persistence": max(root_h - form[c], root_h * 0.05),
        })
        if len(idx) >= 60:
            Zl = linkage(pdist(u[idx], metric="cosine"), method="average")
            k_sub = int(np.clip(len(idx) // 60, 2, 5))
            sub = fcluster(Zl, k_sub, criterion="maxclust")
            limb_h = float(Zl[-1, 2])
            sub_form = _formation_heights(Zl, sub)
            for sc in sorted(set(sub.tolist())):
                sidx = idx[np.flatnonzero(sub == sc)]
                nodes.append({
                    "id": next_id, "parent": limb_id, "mass": int(len(sidx)),
                    "persistence": max(limb_h - sub_form[sc], limb_h * 0.05),
                })
                for p in sidx:
                    membership[int(p)] = next_id
                next_id += 1
        else:
            for p in idx:
                membership[int(p)] = limb_id
    return nodes, membership, {
        "kind": "linkage", "method": "average-cosine", "k_main": k,
    }


def attach_new_notes(nodes, members, vecs: np.ndarray, keys: list[str]) -> int:
    """Attach unknown notes to their nearest node by centroid similarity.
    Mass grows along the whole ancestor chain. Returns notes added."""
    by_id = {n["id"]: n for n in nodes}
    cents = _unit(np.array([n["centroid"] for n in nodes]))
    u = _unit(np.asarray(vecs))
    added = 0
    for vec, key in zip(u, keys):
        if key in members:
            continue
        node = nodes[int(np.argmax(cents @ vec))]
        members[key] = node["id"]
        nid = node["id"]
        while nid != -1:
            by_id[nid]["mass"] += 1
            nid = by_id[nid]["parent"]
        added += 1
    return added


def anchor_nodes(old_members: dict, new_members: dict) -> dict[int, int]:
    """{new_node_id: old_node_id} by greedy best-first member Jaccard.
    Each old id is claimed at most once (anchor_names precedent)."""
    old_sets: dict[int, set] = {}
    for k, nid in old_members.items():
        old_sets.setdefault(nid, set()).add(k)
    new_sets: dict[int, set] = {}
    for k, nid in new_members.items():
        new_sets.setdefault(nid, set()).add(k)
    candidates = []
    for ni, ns in new_sets.items():
        for oi, os in old_sets.items():
            union = len(ns | os)
            if union:
                candidates.append((len(ns & os) / union, ni, oi))
    mapping: dict[int, int] = {}
    used: set[int] = set()
    for jac, ni, oi in sorted(candidates, reverse=True):
        if jac < 0.3:
            break
        if ni in mapping or oi in used:
            continue
        mapping[ni] = oi
        used.add(oi)
    return mapping


# --------------------------------------------------------------------------
# stability (integration; exercised by the driver)
# --------------------------------------------------------------------------

def _labels_of(membership: dict[int, int], n: int) -> np.ndarray:
    return np.array([membership.get(i, -1) for i in range(n)])


def _transfer_ari(va: np.ndarray, vb: np.ndarray) -> float:
    """Fit trees on both halves; label B's points by A's node centroids and
    compare with B's own labels (and vice versa). Chance-corrected."""
    from sklearn.metrics import adjusted_rand_score

    scores = []
    for src, dst in ((va, vb), (vb, va)):
        nodes_s, mem_s, _ = fit_nodes(src)
        nodes_d, mem_d, _ = fit_nodes(dst)
        if len(nodes_s) < 2 or len(nodes_d) < 2:
            return float("nan")  # one half degenerated to a sapling
        cents, ids = [], []
        us = _unit(src)
        lab_s = _labels_of(mem_s, len(src))
        for node in nodes_s:
            mask = lab_s == node["id"]
            if mask.any():
                cents.append(us[mask].mean(axis=0))
                ids.append(node["id"])
        cents = _unit(np.array(cents))
        inherited = np.array(ids)[np.argmax(_unit(dst) @ cents.T, axis=1)]
        scores.append(adjusted_rand_score(_labels_of(mem_d, len(dst)), inherited))
    return float(np.mean(scores))


def stability(vecs: np.ndarray, dates: list[str], rng) -> dict:
    """Split-half transfer ARI. Temporal split where the span is honest,
    bootstrap otherwise — the kind is recorded, never hidden."""
    dated = sorted((d, i) for i, d in enumerate(dates) if d)
    span = 0
    if len(dated) >= 2:
        span = (np.datetime64(dated[-1][0]) - np.datetime64(dated[0][0])).astype(int)
    if span >= MIN_SPAN_DAYS and len(dated) >= 2 * MIN_CLUSTER_NOTES:
        mid = len(dated) // 2
        a = np.array([i for _, i in dated[:mid]])
        b = np.array([i for _, i in dated[mid:]])
        kind = "temporal"
    else:
        perm = rng.permutation(len(vecs))
        a, b = perm[: len(perm) // 2], perm[len(perm) // 2 :]
        kind = "bootstrap"
    if min(len(a), len(b)) < MIN_CLUSTER_NOTES:
        return {"kind": kind, "ari": None, "note": "halves below clustering floor"}
    ari = _transfer_ari(vecs[a], vecs[b])
    return {"kind": kind, "ari": None if np.isnan(ari) else round(ari, 3),
            "span_days": int(span)}


# --------------------------------------------------------------------------
# snapshot driver
# --------------------------------------------------------------------------

def _note_key(m: dict) -> str:
    return m.get("url") or m.get("path") or m.get("title") or ""


def _exemplars(meta_idx, membership, meta, k=3):
    out: dict[int, list[str]] = {}
    for local_i, global_i in enumerate(meta_idx):
        nid = membership.get(local_i)
        if nid is None:
            continue
        titles = out.setdefault(nid, [])
        if len(titles) < k and meta[global_i]["title"]:
            titles.append(meta[global_i]["title"][:80])
    return out


def build_bucket(name, vecs, meta_idx, meta, rebuild, run_stability, rng,
                 palette=None):
    """Build or update one bucket snapshot; returns a status line."""
    GROVE_DIR.mkdir(parents=True, exist_ok=True)
    path = GROVE_DIR / f"{name}.tree.json"
    keys = [_note_key(meta[i]) for i in meta_idx]
    u = _unit(vecs)

    prev = None
    if path.exists():
        prev = json.loads(path.read_text())
        if prev.get("embedding_model") != _TEXT_MODEL:
            prev = None  # model swap invalidates the cache
    if prev and not rebuild:
        nodes, members = prev["nodes"], prev["members"]
        added = attach_new_notes(nodes, members, u, keys)
        # Decorative metadata is deliberately outside the topology cache key:
        # changing taste must not reshuffle the measured tree structure.
        prev["palette"] = palette
        prev["n_notes"] = len(members)
        prev["updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        path.write_text(json.dumps(prev))
        return f"{name}: +{added} attached ({len(members)} total)"

    nodes, membership, params = fit_nodes(vecs)
    members = {keys[i]: nid for i, nid in membership.items()}
    # per-node centroids (attach targets) + exemplar titles (hover/naming)
    lab = _labels_of(membership, len(vecs))
    ex = _exemplars(meta_idx, membership, meta)
    for node in nodes:
        mask = lab == node["id"]
        cent = u[mask].mean(axis=0) if mask.any() else u.mean(axis=0)
        node["centroid"] = [round(float(x), 5) for x in cent]
        node["exemplars"] = ex.get(node["id"], [])
    if prev:  # anchored rebuild: keep old node ids where members overlap
        mapping = anchor_nodes(
            {k: v for k, v in prev["members"].items()},
            members,
        )
        taken = set(mapping.values())
        fresh = (i for i in range(10**6) if i not in taken)
        rename = {n["id"]: mapping.get(n["id"], next(fresh)) for n in nodes}
        for node in nodes:
            node["id"] = rename[node["id"]]
            if node["parent"] != -1:
                node["parent"] = rename[node["parent"]]
        members = {k: rename[v] for k, v in members.items()}

    snap = {
        "version": 1,
        "bucket": name,
        "palette": palette,
        "embedding_model": _TEXT_MODEL,
        "built": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_notes": len(keys),
        "params": params,
        "stability": stability(
            vecs, [meta[i]["date"] for i in meta_idx], rng
        ) if run_stability else None,
        "nodes": nodes,
        "members": members,
    }
    path.write_text(json.dumps(snap))
    anchored = " (anchored to previous)" if prev else ""
    return (f"{name}: {len(nodes)} nodes, {len(keys)} notes, "
            f"{params['kind']}{anchored}, stability={snap['stability']}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true",
                    help="re-derive topology (anchored to previous snapshot)")
    ap.add_argument("--stability", action="store_true",
                    help="run the split-half transfer-ARI gate")
    ap.add_argument("--bucket", help="only this bucket")
    args = ap.parse_args()

    from scripts.grove_lab.buckets import DEFAULT_CONFIG, assign, load_buckets, resolve_notes

    rng = np.random.default_rng(42)
    cfg = load_buckets(DEFAULT_CONFIG)
    vecs, meta, notes = resolve_notes()
    labels = assign(notes, cfg)
    for i, b in enumerate(cfg.buckets):
        if args.bucket and b.name != args.bucket:
            continue
        idx = [k for k, x in enumerate(labels) if x == i]
        if not idx:
            print(f"{b.name}: empty, skipped")
            continue
        print(build_bucket(b.name, vecs[idx], idx, meta, args.rebuild,
                           args.stability, rng, b.palette))


if __name__ == "__main__":
    main()
