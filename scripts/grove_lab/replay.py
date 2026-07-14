"""Grow-only cache path dependence, v2 (design review applied: P1-P7,
docs/grove-lab/path-dependence-design-review-codex.md).

Replays a bucket's arrival through the production derivation
(`fit_nodes`) and attach semantics, measuring divergence from fresh
references at checkpoints AND at every rebuild event (pre/post).

P1  debt = attached_since / n_at_last_rebuild, fires on >= theta
P2  two references per checkpoint: production-fresh (shipping frontier)
    and matched-capacity (k_main frozen to the base tree) to separate
    path dependence from capacity growth
P3  the date arm is DATE-ORDERED (no persisted ingest log exists): ties
    randomized within equal dates, undated notes interleaved uniformly at
    seeded random positions; coverage published per cell
P4  mass metric: descendant-set matching with coverage + L1 magnitude
P5  triplet accounting (attempted/usable/ties), shared samples when a
    refs bundle provides them, null under a usable floor
P6  base-fraction arms + the centroid-maintain policy (never rebuild,
    attach targets updated as running means up the ancestor chain)
P7  frozen input artifacts, precomputed shared references, deterministic
    per-cell seeds, atomic outputs, wall-time + sum(n^2) work proxy

Modes:
    --freeze                      write frozen inputs per bucket
    --refs   --bucket B --order O write shared checkpoint references
    (cell)   --bucket B --order O --theta T --policy P --base-frac F --out PATH
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np

from scripts.grove_lab.dendro import MIN_CLUSTER_NOTES, _unit, anchor_nodes

INPUT_DIR = Path.home() / ".ytk" / "grove" / "replay-input"
REFS_DIR = Path.home() / ".ytk" / "grove" / "replay-refs"
CHECKPOINTS = (0.6, 0.7, 0.8, 0.9, 1.0)
N_TRIPLETS = 3000
USABLE_FLOOR = 200


# --------------------------------------------------------------------------
# derivation with capacity control (P2)
# --------------------------------------------------------------------------

def fit_nodes_capacity(vecs: np.ndarray, k_main: int | None = None):
    """dendro.fit_nodes's linkage topology with an optional frozen k_main.
    Returns (nodes, membership, info) where info records requested vs used
    capacity so divergence can be attributed (P2)."""
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import pdist

    from scripts.grove_lab.dendro import _formation_heights

    n = len(vecs)
    requested = int(np.clip(n // 80, 3, 9))
    k = requested if k_main is None else k_main
    if n < MIN_CLUSTER_NOTES:
        return ([{"id": 0, "parent": -1, "mass": n, "persistence": 1.0}],
                {i: 0 for i in range(n)},
                {"k_main_requested": requested, "k_main_used": 1, "n": n})
    u = _unit(vecs)
    Z = linkage(pdist(u, metric="cosine"), method="average")
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
        nodes.append({"id": limb_id, "parent": 0, "mass": int(len(idx)),
                      "persistence": max(root_h - form[c], root_h * 0.05)})
        if len(idx) >= 60:
            Zl = linkage(pdist(u[idx], metric="cosine"), method="average")
            k_sub = int(np.clip(len(idx) // 60, 2, 5))
            sub = fcluster(Zl, k_sub, criterion="maxclust")
            limb_h = float(Zl[-1, 2])
            sub_form = _formation_heights(Zl, sub)
            for sc in sorted(set(sub.tolist())):
                sidx = idx[np.flatnonzero(sub == sc)]
                nodes.append({"id": next_id, "parent": limb_id,
                              "mass": int(len(sidx)),
                              "persistence": max(limb_h - sub_form[sc], limb_h * 0.05)})
                for p in sidx:
                    membership[int(p)] = next_id
                next_id += 1
        else:
            for p in idx:
                membership[int(p)] = limb_id
    return nodes, membership, {
        "k_main_requested": requested, "k_main_used": k, "n": n,
    }


def _stamp_centroids(vecs: np.ndarray, nodes, membership) -> None:
    """Centroids from DESCENDANT mass (Codex v5 K2): an internal node's
    centroid is the mean of every note under it, accumulated bottom-up —
    never a global-mean pseudo-observation."""
    u = _unit(vecs)
    lab = np.array([membership.get(i, -1) for i in range(len(vecs))])
    by_id = {n["id"]: n for n in nodes}
    for node in nodes:
        mask = lab == node["id"]
        node["_sum"] = u[mask].sum(axis=0) if mask.any() else np.zeros(u.shape[1])
        node["_count"] = int(mask.sum())
    # accumulate child sums into parents, deepest first
    depth: dict[int, int] = {}

    def d(i: int) -> int:
        if i not in depth:
            p = by_id[i]["parent"]
            depth[i] = 0 if p == -1 else d(p) + 1
        return depth[i]

    for n in nodes:
        d(n["id"])
    for n in sorted(nodes, key=lambda x: depth[x["id"]], reverse=True):
        p = n["parent"]
        if p != -1:
            by_id[p]["_sum"] = by_id[p]["_sum"] + n["_sum"]
            by_id[p]["_count"] += n["_count"]
    for node in nodes:
        if node["_count"] > 0:
            node["centroid"] = (node["_sum"] / node["_count"]).astype(float)
        else:  # empty node: fall back to global mean, marked by zero count
            node["centroid"] = u.mean(axis=0).astype(float)
            node["_sum"] = np.zeros(u.shape[1])


# --------------------------------------------------------------------------
# pure metric helpers (tested)
# --------------------------------------------------------------------------

def lca_distance_table(nodes: list[dict]) -> dict[tuple[int, int], float]:
    """Node-pair ultrametric: height (max_depth - depth) of the LCA; 0 for
    the same node. Ordinal only."""
    parent = {n["id"]: n["parent"] for n in nodes}
    depth: dict[int, int] = {}

    def d(i: int) -> int:
        if i not in depth:
            depth[i] = 0 if parent[i] == -1 else d(parent[i]) + 1
        return depth[i]

    for n in nodes:
        d(n["id"])
    max_depth = max(depth.values())
    anc: dict[int, list[int]] = {}
    for n in nodes:
        chain = [n["id"]]
        while parent[chain[-1]] != -1:
            chain.append(parent[chain[-1]])
        anc[n["id"]] = chain
    table: dict[tuple[int, int], float] = {}
    for a in anc:
        sa = set(anc[a])
        for b in anc:
            if a == b:
                table[(a, b)] = 0.0
            else:
                lca = next(x for x in anc[b] if x in sa)
                table[(a, b)] = float(max_depth - depth[lca])
    return table


def _triplets(labels_a, table_a, labels_b, table_b, samples) -> dict:
    """Triplet agreement with full accounting (P5). `samples` is an array
    of (i,j,k) note-index triplets - shared across policies for pairing."""
    hits = usable = ties = 0
    for i, j, k in samples:
        pairs = ((i, j), (i, k), (j, k))
        da = [table_a[(labels_a[p], labels_a[q])] for p, q in pairs]
        db = [table_b[(labels_b[p], labels_b[q])] for p, q in pairs]
        sa, sb = sorted(da), sorted(db)
        if sa[0] == sa[1] or sb[0] == sb[1]:
            ties += 1
            continue
        hits += int(int(np.argmin(da)) == int(np.argmin(db)))
        usable += 1
    return {
        "attempted": len(samples), "usable": usable, "ties": ties,
        "noninjective": 0,
        "agreement": round(hits / usable, 3) if usable >= USABLE_FLOOR else None,
    }


def _descendant_sets(nodes, members) -> dict[int, set]:
    kids: dict[int, list[int]] = {}
    for n in nodes:
        if n["parent"] != -1:
            kids.setdefault(n["parent"], []).append(n["id"])
    direct: dict[int, set] = {n["id"]: set() for n in nodes}
    for key, nid in members.items():
        direct[nid].add(key)
    out: dict[int, set] = {}

    def build(i: int) -> set:
        if i not in out:
            s = set(direct[i])
            for c in kids.get(i, []):
                s |= build(c)
            out[i] = s
        return out[i]

    for n in nodes:
        build(n["id"])
    return out


def descendant_mass_metric(nodes_a, members_a, nodes_b, members_b) -> dict:
    """P4: match ALL renderer-visible nodes by descendant-set Jaccard,
    report coverage, rank correlation AND magnitude (mass-share L1)."""
    from scipy.stats import spearmanr

    da, db = _descendant_sets(nodes_a, members_a), _descendant_sets(nodes_b, members_b)
    candidates = []
    for a, sa in da.items():
        for b, sb in db.items():
            union = len(sa | sb)
            if union:
                candidates.append((len(sa & sb) / union, a, b))
    matched: list[tuple[int, int]] = []
    ua, ub = set(), set()
    for jac, a, b in sorted(candidates, reverse=True):
        if jac < 0.3:
            break
        if a in ua or b in ub:
            continue
        matched.append((a, b))
        ua.add(a)
        ub.add(b)
    root_a = sum(1 for _ in members_a) or 1
    root_b = sum(1 for _ in members_b) or 1
    ma = {n["id"]: n["mass"] for n in nodes_a}
    mb = {n["id"]: n["mass"] for n in nodes_b}
    shares = [(ma[a] / root_a, mb[b] / root_b) for a, b in matched]
    l1 = float(sum(abs(x - y) for x, y in shares))
    if len(shares) >= 3:
        rho = spearmanr([x for x, _ in shares], [y for _, y in shares]).statistic
        rho = None if np.isnan(rho) else round(float(rho), 3)
    else:
        rho = None
    coverage = sum(len(da[a]) for a, _ in matched) / max(1, sum(len(s) for s in da.values()))
    return {"matched_nodes": len(matched), "coverage": round(float(coverage), 3),
            "spearman": rho, "mass_l1": round(l1, 3),
            "unmatched_a": len(da) - len(matched), "unmatched_b": len(db) - len(matched)}


# --------------------------------------------------------------------------
# replay
# --------------------------------------------------------------------------

def _attach(nodes, members, by_id, vec_unit, key, policy) -> int:
    """Production attach + optional online centroid maintenance (P6).
    Returns the target node's depth."""
    cents = np.array([n["centroid"] for n in nodes])
    cents = cents / np.linalg.norm(cents, axis=1, keepdims=True).clip(1e-12)
    target = nodes[int(np.argmax(cents @ vec_unit))]
    members[key] = target["id"]
    nid, depth = target["id"], 0
    while nid != -1:
        node = by_id[nid]
        node["mass"] += 1
        if policy == "centroid-maintain":
            node["_sum"] = node["_sum"] + vec_unit
            node["_count"] += 1
            node["centroid"] = node["_sum"] / node["_count"]
        nid = node["parent"]
        depth += 1
    return depth


def _compare(nodes, members, k, vecs, samples, ref) -> dict:
    """All three metrics (P2/P4/P5) of the incremental state vs one
    reference (nodes/membership/info)."""
    from sklearn.metrics import adjusted_rand_score

    ref_nodes, ref_membership, info = ref
    keys = [str(i) for i in range(k)]
    la = np.array([members[key] for key in keys])
    lb = np.array([ref_membership[i] for i in range(k)])
    ta, tb = lca_distance_table(nodes), lca_distance_table(ref_nodes)
    ref_members = {str(i): nid for i, nid in ref_membership.items()}
    return {
        "assignment_ari": round(float(adjusted_rand_score(la, lb)), 3),
        "triplets": _triplets(la, ta, lb, tb, samples),
        "mass": descendant_mass_metric(nodes, members, ref_nodes, ref_members),
        "k_main_requested": info["k_main_requested"],
        "k_main_used": info["k_main_used"],
        "ref_nodes": len(ref_nodes),
        "incremental_nodes": len(nodes),
    }


def replay_cell(vecs: np.ndarray, order: list[int], theta: float | None,
                policy: str = "rebuild", checkpoints=CHECKPOINTS,
                base_frac: float = 0.5, rng=None, refs: dict | None = None,
                floor: int = 0) -> dict:
    """One (order, theta, policy, base_frac) cell. refs may carry
    precomputed production references and shared triplet samples keyed by
    checkpoint n (P7); missing entries are computed locally."""
    rng = rng if rng is not None else np.random.default_rng(0)
    t0 = time.monotonic()
    seq = np.asarray(order)
    n = len(seq)
    k0 = max(int(n * base_frac), MIN_CLUSTER_NOTES)
    u_all = _unit(vecs[seq])

    nodes, membership, base_info = fit_nodes_capacity(vecs[seq[:k0]])
    _stamp_centroids(vecs[seq[:k0]], nodes, membership)
    members = {str(i): nid for i, nid in membership.items()}
    by_id = {nd["id"]: nd for nd in nodes}
    n_at_last, attached_since = k0, 0
    work = k0 * k0
    rebuild_events: list[dict] = []
    marks = {max(int(n * f), k0): f for f in checkpoints}

    def production_ref(k):
        if refs and str(k) in refs.get("production", {}):
            r = refs["production"][str(k)]
            return (r["nodes"], {int(i): v for i, v in r["membership"].items()},
                    r["info"])
        rn, rm, ri = fit_nodes_capacity(vecs[seq[:k]])
        return rn, rm, ri

    def sample_triplets(k):
        if refs and str(k) in refs.get("samples", {}):
            return np.array(refs["samples"][str(k)])
        r = np.random.default_rng(k * 7919 + 13)
        return np.array([r.choice(k, 3, replace=False) for _ in range(N_TRIPLETS)])

    checkpoints_out = []
    for pos in range(k0, n):
        depth = _attach(nodes, members, by_id, u_all[pos], str(pos), policy)
        attached_since += 1
        k = pos + 1

        # hybrid trigger (Codex v5 K6): debt threshold with an absolute
        # note floor - max(theta * n_at_last, floor) notes must accumulate
        if (policy == "rebuild" and theta is not None
                and attached_since >= max(theta * n_at_last, floor)):
            samples = sample_triplets(k)
            ref = production_ref(k)
            pre = _compare(nodes, members, k, vecs, samples, ref)
            fresh_nodes, fresh_membership, _ = fit_nodes_capacity(vecs[seq[:k]])
            _stamp_centroids(vecs[seq[:k]], fresh_nodes, fresh_membership)
            fresh_members = {str(i): nid for i, nid in fresh_membership.items()}
            mapping = anchor_nodes(members, fresh_members)
            taken = set(mapping.values())
            gen = (i for i in range(10**6) if i not in taken)
            rename = {fn["id"]: mapping.get(fn["id"], next(gen)) for fn in fresh_nodes}
            for fn in fresh_nodes:
                fn["id"] = rename[fn["id"]]
                if fn["parent"] != -1:
                    fn["parent"] = rename[fn["parent"]]
            nodes = fresh_nodes
            by_id = {nd["id"]: nd for nd in nodes}
            members = {kk: rename[v] for kk, v in fresh_members.items()}
            post = _compare(nodes, members, k, vecs, samples, ref)
            rebuild_events.append({"n": k, "pre": pre, "post": post})
            work += k * k
            n_at_last, attached_since = k, 0

        if k in marks:
            samples = sample_triplets(k)
            cp = {
                "frac": marks[k], "n": k,
                "production": _compare(nodes, members, k, vecs, samples,
                                       production_ref(k)),
                "matched_capacity": _compare(
                    nodes, members, k, vecs, samples,
                    fit_nodes_capacity(vecs[seq[:k]],
                                       k_main=base_info["k_main_used"])),
                "attach_depth_last": depth,
            }
            checkpoints_out.append(cp)

    prod_ari = [c["production"]["assignment_ari"] for c in checkpoints_out]
    prod_tri = [c["production"]["triplets"]["agreement"] for c in checkpoints_out
                if c["production"]["triplets"]["agreement"] is not None]
    return {
        "theta": theta, "policy": policy, "base_frac": base_frac, "n": n,
        "base_k_main": base_info["k_main_used"],
        "rebuild_events": rebuild_events,
        "rebuilds": len(rebuild_events),
        "checkpoints": checkpoints_out,
        "auc": {"assignment_ari": round(float(np.mean(prod_ari)), 3) if prod_ari else None,
                "triplet": round(float(np.mean(prod_tri)), 3) if prod_tri else None},
        "worst_pre_rebuild": min(
            (e["pre"]["assignment_ari"] for e in rebuild_events), default=None),
        "cost": {"wall_s": round(time.monotonic() - t0, 1), "work_n2": work},
        "final_centroids": [list(map(float, by_id[nd["id"]]["centroid"]))
                            for nd in sorted(nodes, key=lambda x: x["id"])],
    }


# --------------------------------------------------------------------------
# frozen inputs, shared refs, CLI (P7)
# --------------------------------------------------------------------------

def _order_indices(meta_dates: list[str], order: str, n: int, seed: int) -> list[int]:
    """P3: 'date' = date-ordered with randomized ties, undated interleaved
    uniformly at seeded positions; integers = random permutations."""
    rng = np.random.default_rng(seed)
    if order != "date":
        return [int(x) for x in np.random.default_rng(int(order)).permutation(n)]
    dated = [i for i in range(n) if meta_dates[i]]
    undated = [i for i in range(n) if not meta_dates[i]]
    dated.sort(key=lambda i: (meta_dates[i], rng.random()))
    out = list(dated)
    for i in undated:
        out.insert(int(rng.integers(0, len(out) + 1)), i)
    return out


def freeze() -> None:
    from scripts.grove_lab.buckets import DEFAULT_CONFIG, assign, load_buckets, resolve_notes
    from ytk.store import _TEXT_MODEL

    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    cfg = load_buckets(DEFAULT_CONFIG)
    vecs, meta, notes = resolve_notes()
    labels = assign(notes, cfg)
    for i, b in enumerate(cfg.buckets):
        idx = [k for k, x in enumerate(labels) if x == i]
        if len(idx) < 2 * MIN_CLUSTER_NOTES:
            continue
        v = np.asarray(vecs)[idx].astype(np.float32)
        dates = [meta[k]["date"] for k in idx]
        sha = hashlib.sha256(v.tobytes()).hexdigest()
        np.savez_compressed(INPUT_DIR / f"{b.name}.npz", vecs=v)
        (INPUT_DIR / f"{b.name}.json").write_text(json.dumps({
            "bucket": b.name, "n": len(idx), "dates": dates,
            "dated": sum(1 for d in dates if d),
            "embedding_model": _TEXT_MODEL, "vec_sha256": sha,
        }))
        print(f"froze {b.name}: n={len(idx)}, dated={sum(1 for d in dates if d)}, sha={sha[:12]}")


def build_refs(bucket: str, order: str) -> None:
    meta = json.loads((INPUT_DIR / f"{bucket}.json").read_text())
    vecs = np.load(INPUT_DIR / f"{bucket}.npz")["vecs"]
    seed = int(hashlib.sha256(f"{bucket}|{order}".encode()).hexdigest()[:8], 16)
    order_idx = _order_indices(meta["dates"], order, meta["n"], seed)
    seq = np.asarray(order_idx)
    refs: dict = {"production": {}, "samples": {}, "order_indices": order_idx,
                  "vec_sha256": meta["vec_sha256"]}
    ks = sorted({max(int(meta["n"] * f), MIN_CLUSTER_NOTES) for f in CHECKPOINTS})
    for k in ks:
        rn, rm, ri = fit_nodes_capacity(vecs[seq[:k]])
        refs["production"][str(k)] = {
            "nodes": [{kk: n[kk] for kk in ("id", "parent", "mass", "persistence")}
                      for n in rn],
            "membership": {str(i): v for i, v in rm.items()}, "info": ri}
        r = np.random.default_rng(k * 7919 + 13)
        refs["samples"][str(k)] = [
            [int(x) for x in r.choice(k, 3, replace=False)] for _ in range(N_TRIPLETS)]
    REFS_DIR.mkdir(parents=True, exist_ok=True)
    (REFS_DIR / f"{bucket}-{order}.json").write_text(json.dumps(refs))
    print(f"refs {bucket}-{order}: prefixes {ks}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze", action="store_true")
    ap.add_argument("--refs", action="store_true")
    ap.add_argument("--bucket")
    ap.add_argument("--order", help="'date' or an integer seed")
    ap.add_argument("--theta", default="never")
    ap.add_argument("--policy", default="rebuild",
                    choices=["rebuild", "centroid-maintain"])
    ap.add_argument("--base-frac", type=float, default=0.5)
    ap.add_argument("--floor", type=int, default=0,
                    help="absolute debt floor in notes (hybrid trigger, K6)")
    ap.add_argument("--out")
    args = ap.parse_args()

    if args.freeze:
        freeze()
        return
    if args.refs:
        build_refs(args.bucket, args.order)
        return

    meta = json.loads((INPUT_DIR / f"{args.bucket}.json").read_text())
    vecs = np.load(INPUT_DIR / f"{args.bucket}.npz")["vecs"]
    refs_path = REFS_DIR / f"{args.bucket}-{args.order}.json"
    refs = json.loads(refs_path.read_text()) if refs_path.exists() else None
    if refs and refs["vec_sha256"] != meta["vec_sha256"]:
        raise SystemExit("refs/input hash mismatch - refreeze")
    order_idx = (refs["order_indices"] if refs else _order_indices(
        meta["dates"], args.order, meta["n"],
        int(hashlib.sha256(f"{args.bucket}|{args.order}".encode()).hexdigest()[:8], 16)))
    theta = None if args.theta == "never" else float(args.theta)
    cell_seed = int(hashlib.sha256(
        f"{args.bucket}|{args.order}|{args.theta}|{args.policy}|{args.base_frac}|{args.floor}"
        .encode()).hexdigest()[:8], 16)
    cell = replay_cell(vecs, order_idx, theta, policy=args.policy,
                       base_frac=args.base_frac, floor=args.floor,
                       rng=np.random.default_rng(cell_seed))
    cell.pop("final_centroids", None)  # test/debug payload, not an artifact
    cell.update({"bucket": args.bucket, "order": args.order, "floor": args.floor,
                 "embedding_model": meta["embedding_model"],
                 "vec_sha256": meta["vec_sha256"],
                 "dated": meta["dated"], "undated": meta["n"] - meta["dated"]})
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(cell))
    tmp.rename(out)
    print(f"wrote {out}: rebuilds={cell['rebuilds']} auc={cell['auc']} "
          f"cost={cell['cost']}")


if __name__ == "__main__":
    main()
