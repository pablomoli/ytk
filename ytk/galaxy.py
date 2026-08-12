"""Production home of the E32/E33 galaxy machinery; the experiments in
scripts/ are the committed record.

Ported from `scripts/e31_theme_planets.py` (`CLASSES`, `classify`) and
`scripts/e32_galaxy.py` (`arm_a`, `all_planets`) — same precedent as
`ytk/coast.py`. `galaxy_block` mirrors `all_planets()` but takes data as
arguments (no map.json reads), and adds `median_age_days` and the
`member_paths`/`hash` fields. `hash` is the finished cache key the moon and
texture caches key off — `member_hash(member_paths, epoch)`, the caller's
embedding epoch threaded straight through, no default.
"""

from __future__ import annotations

import datetime
import hashlib
import itertools
import json
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

# shipped scale from docs/assets/32-galaxy/ (E32): arm A holds occlusion
# under the 5% bar out to K*=3.00 deg per n^(1/3), clear of map agreement
GALAXY_K = 3.0

ACTIVE_DAYS = 90

# Sudarsky albedo classes, translated: activity share of dated notes in the
# last ACTIVE_DAYS decides the class. Thresholds are stated, not fitted.
CLASSES = [
    ("V", 0.50, "silicate glow", "#ffb08a"),
    ("IV", 0.30, "alkali dark", "#8a5a3a"),
    ("III", 0.15, "clear rayleigh", "#5a8cff"),
    ("II", 0.05, "water cloud", "#cfe0f0"),
    ("I", 0.00, "ammonia bands", "#e0cfa0"),
]


def classify(activity: float) -> tuple[str, str, str]:
    for name, floor, label, hue in CLASSES:
        if activity >= floor:
            return name, label, hue
    return CLASSES[-1][0], CLASSES[-1][2], CLASSES[-1][3]


def member_hash(paths: list[str], epoch: str) -> str:
    """Cache key for moons and textures: sensitive to member-set and epoch."""
    payload = epoch + "\n" + "\n".join(sorted(paths)) + f"\nK={GALAXY_K}\nv1"
    return hashlib.sha256(payload.encode()).hexdigest()


def arm_a(theme_cent_c3: NDArray[Any], c3_all: NDArray[Any]) -> NDArray[Any]:
    """Members' centroid as a direction from the content cloud's own center —
    the same origin the tile layer's radial() uses (E32 arm A)."""
    v = np.asarray(theme_cent_c3) - np.asarray(c3_all).mean(axis=0)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def galaxy_block(
    vecs: NDArray[Any],
    c3: NDArray[Any],
    themes: NDArray[Any],
    dates: list[str | None],
    labels: list[str],
    paths: list[str],
    epoch: str,
    today: datetime.date | None = None,
) -> list[dict[str, Any]]:
    vecs = np.asarray(vecs)
    c3 = np.asarray(c3)
    themes = np.asarray(themes)
    today = today or datetime.date.today()

    ids = sorted(int(t) for t in np.unique(themes) if t >= 0)
    cent_c3 = np.asarray(
        [c3[themes == t].mean(axis=0) for t in ids],
    )
    pos_all = arm_a(cent_c3, c3)

    out: list[dict[str, Any]] = []
    for t, pos in zip(ids, pos_all):
        m = themes == t
        n = int(m.sum())
        member_dates = [d for d, keep in zip(dates, m) if keep and d]
        ages = [(today - datetime.date.fromisoformat(d)).days for d in member_dates]
        recent = sum(1 for age in ages if age <= ACTIVE_DAYS)
        activity = recent / len(ages) if ages else 0.0
        median_age = float(np.median(ages)) if ages else None

        vn = vecs[m] / np.linalg.norm(vecs[m], axis=1, keepdims=True)
        cent = vn.mean(axis=0)
        cent /= np.linalg.norm(cent)
        cohesion = float((vn @ cent).mean())

        cls, cls_label, hue = classify(activity)
        member_paths = [p for p, keep in zip(paths, m) if keep]

        out.append(
            {
                "theme": t,
                "label": labels[t],
                "n": n,
                "activity": activity,
                "date_coverage": len(ages) / n,
                "median_age_days": median_age,
                "cohesion": cohesion,
                "cls": cls,
                "cls_label": cls_label,
                "hue": hue,
                "radius_deg": GALAXY_K * n ** (1 / 3),
                "pos": pos.tolist(),
                "member_paths": member_paths,
                "hash": member_hash(member_paths, epoch),
            }
        )
    return out


def ring_gate(
    vecs: NDArray[Any],
    themes: NDArray[Any],
    ids: list[int],
    seed: int = 433,
    knn: int = 10,
    n_perm: int = 1000,
) -> dict[int, dict[str, Any]]:
    # E33 gate: docs/assets/33-channels/
    rng = np.random.default_rng(seed)
    vecs = np.asarray(vecs)
    themes = np.asarray(themes)
    mask = themes >= 0
    v = vecs[mask]
    th = themes[mask]
    sims: NDArray[Any] = v @ v.T
    np.fill_diagonal(sims, -np.inf)
    nn = np.argsort(-sims, axis=1)[:, :knn]
    nn_th = th[nn]

    pair = {t: {int(u): int((nn_th[th == t] == u).sum()) for u in ids if u != t} for t in ids}
    perm_pair: dict[int, dict[int, list[int]]] = {
        t: {int(u): [] for u in ids if u != t} for t in ids
    }
    for _ in range(n_perm):
        p = th[rng.permutation(len(th))]
        p_nn = p[nn]
        for t in ids:
            row = p_nn[p == t]
            for u in ids:
                if u != t:
                    perm_pair[t][u].append(int((row == u).sum()))
    out: dict[int, dict[str, Any]] = {}
    for t in ids:
        others = [u for u in ids if u != t]
        counts = np.asarray([perm_pair[t][u] for u in others], dtype=float)
        mean = counts.mean(axis=1)
        sd = np.maximum(counts.std(axis=1), 1.0)
        z_obs: NDArray[Any] = (np.asarray([pair[t][u] for u in others]) - mean) / sd
        z_perm_max: NDArray[Any] = ((counts - mean[:, None]) / sd[:, None]).max(axis=0)
        bar = float(np.quantile(z_perm_max, 0.99))
        partners = sorted(
            (
                {"theme": int(u), "count": pair[t][u], "z": float(z)}
                for u, z in zip(others, z_obs)
                if z > bar
            ),
            key=lambda d: -d["z"],
        )
        out[t] = {
            "max_z": float(z_obs.max()),
            "z_bar": bar,
            "z_null_lo": float(np.quantile(z_perm_max, 0.05)),
            "earned": bool(z_obs.max() > bar),
            "partners": partners[:3],
        }
    return out


def spin_gate(
    themes: NDArray[Any],
    dates: list[str | None],
    ids: list[int],
    seed: int = 533,
    n_perm: int = 1000,
) -> dict[int, dict[str, Any]]:
    # E33 gate: docs/assets/33-channels/
    rng = np.random.default_rng(seed)
    themes = np.asarray(themes)
    today = datetime.date.today()
    ages = np.array(
        [(today - datetime.date.fromisoformat(d)).days if d else -1 for d in dates],
        dtype=float,
    )
    dated = ages >= 0
    pool = ages[dated & (themes >= 0)]
    pool_themes = themes[dated & (themes >= 0)]
    out: dict[int, dict[str, Any]] = {}
    for t in ids:
        m = pool_themes == t
        k = int(m.sum())
        obs = float(np.median(pool[m])) if k else float("nan")
        meds = [
            float(np.median(pool[rng.choice(len(pool), k, replace=False)])) for _ in range(n_perm)
        ]
        lo, hi = float(np.quantile(meds, 0.025)), float(np.quantile(meds, 0.975))
        out[t] = {
            "median_age_days": obs,
            "n_dated": k,
            "null_lo": lo,
            "null_hi": hi,
            "earned": bool(k and (obs < lo or obs > hi)),
            "side": "fast" if k and obs < lo else ("dormant" if k and obs > hi else None),
        }
    return out


# ported from scripts/e33_channels.py — moon channel: gate on triplet
# agreement between dendrograms across subsamples vs a spectrum-matched
# unimodal cloud (anisotropy preserved, sub-structure destroyed)
N_TRIP = 4000  # triplets scored per subsample
GATE_Q = 0.95


def _coph(vn: NDArray[Any]) -> NDArray[Any]:
    from scipy.cluster.hierarchy import cophenet, linkage  # type: ignore[reportMissingTypeStubs]
    from scipy.spatial.distance import (  # type: ignore[reportMissingTypeStubs]
        pdist,
        squareform,
    )

    d: NDArray[Any] = pdist(vn, metric="cosine")
    z: NDArray[Any] = linkage(d, method="average")  # type: ignore[reportUnknownVariableType]
    coph: NDArray[Any] = cophenet(z, d)[1]  # type: ignore[reportUnknownVariableType]
    return squareform(coph)  # type: ignore[reportUnknownArgumentType]


def _triplets(m: int, rng: np.random.Generator, n_trip: int = N_TRIP) -> NDArray[Any]:
    trips = np.array(list(itertools.combinations(range(m), 3)))
    if len(trips) > n_trip:
        trips = trips[rng.choice(len(trips), n_trip, replace=False)]
    return trips


def _outliers(c: NDArray[Any], trips: NDArray[Any]) -> NDArray[Any]:
    """Odd-one-out per triplet: the point outside the pair that merges first
    (smallest cophenetic distance)."""
    d_jk = c[trips[:, 1], trips[:, 2]]
    d_ik = c[trips[:, 0], trips[:, 2]]
    d_ij = c[trips[:, 0], trips[:, 1]]
    return np.argmin(np.stack([d_jk, d_ik, d_ij]), axis=0)


def moon_stability(vn: NDArray[Any], seed: int, n_boot: int = 25) -> float:
    """Mean triplet agreement between the full dendrogram and 80% subsample
    dendrograms — hierarchy geometry, never a flat cut (E-series lesson)."""
    rng = np.random.default_rng(seed)
    n = len(vn)
    cfull = _coph(vn)
    scores: list[float] = []
    for _ in range(n_boot):
        idx = rng.choice(n, size=max(6, int(0.8 * n)), replace=False)
        trips = _triplets(len(idx), rng)
        o_full = _outliers(cfull[np.ix_(idx, idx)], trips)
        o_sub = _outliers(_coph(vn[idx]), trips)
        scores.append(float((o_full == o_sub).mean()))
    return float(np.mean(scores))


def null_cloud(vn: NDArray[Any], rng: np.random.Generator) -> NDArray[Any]:
    """Unimodal cloud matched to the member set's mean and full covariance
    spectrum (sampled in its own eigenbasis): the cone and the anisotropy
    survive, any sub-structure does not."""
    mu = vn.mean(axis=0)
    _u, s, vt = np.linalg.svd(vn - mu, full_matrices=False)  # type: ignore[reportUnknownVariableType]
    n_rows: NDArray[Any] = rng.normal(size=(len(vn), len(s)))  # type: ignore[reportUnknownArgumentType]
    z: NDArray[Any] = n_rows * (s / np.sqrt(max(len(vn) - 1, 1)))  # type: ignore[reportUnknownVariableType]
    y: NDArray[Any] = mu + z @ vt  # type: ignore[reportUnknownVariableType]
    return y / np.linalg.norm(y, axis=1, keepdims=True)  # type: ignore[reportUnknownVariableType,reportUnknownArgumentType]


def moon_cut(vn: NDArray[Any], seed: int, n_boot: int = 25) -> tuple[int, list[dict[str, Any]]]:
    """Descriptive flat cut for a gated planet: k in 2..4 by co-assignment
    stability across the same subsampling; moons need >= 3 members."""
    from scipy.cluster.hierarchy import fcluster, linkage  # type: ignore[reportMissingTypeStubs]
    from scipy.spatial.distance import pdist  # type: ignore[reportMissingTypeStubs]

    rng = np.random.default_rng(seed)
    n = len(vn)
    d_full: NDArray[Any] = pdist(vn, metric="cosine")
    z_full: NDArray[Any] = linkage(d_full, method="average")  # type: ignore[reportUnknownVariableType]
    best_k, best_s = 2, -1.0
    for k in (2, 3, 4):
        lab_full: NDArray[Any] = fcluster(z_full, k, criterion="maxclust")
        agree: list[float] = []
        for _ in range(n_boot):
            idx = rng.choice(n, size=max(6, int(0.8 * n)), replace=False)
            z_sub: NDArray[Any] = linkage(  # type: ignore[reportUnknownVariableType]
                pdist(vn[idx], metric="cosine"), method="average"
            )
            lab_sub: NDArray[Any] = fcluster(z_sub, k, criterion="maxclust")
            a, b = lab_full[idx], lab_sub
            co_a = a[:, None] == a[None, :]
            co_b = b[:, None] == b[None, :]
            iu = np.triu_indices(len(idx), 1)
            agree.append(float((co_a[iu] == co_b[iu]).mean()))
        if np.mean(agree) > best_s:
            best_k, best_s = k, float(np.mean(agree))
    labels: NDArray[Any] = fcluster(z_full, best_k, criterion="maxclust")
    sizes = {int(c): int((labels == c).sum()) for c in np.unique(labels)}
    core = max(sizes, key=lambda c: sizes[c])
    # the largest cluster is the planet's core, not a moon — a moon is a
    # minority sub-cluster with enough members to be a real object
    return sizes[core], [
        {"members": np.flatnonzero(labels == c).tolist()}
        for c in np.unique(labels)
        if c != core and (labels == c).sum() >= 3
    ]


def moon_gate(vn: NDArray[Any], seed: int, n_boot: int = 25, n_null: int = 50) -> dict[str, Any]:
    # E33 gate: docs/assets/33-channels/
    vn = np.asarray(vn)
    real = moon_stability(vn, seed=seed, n_boot=n_boot)
    rng = np.random.default_rng(seed + 100)
    null = [
        moon_stability(null_cloud(vn, rng), seed=seed + 200 + i, n_boot=n_boot)
        for i in range(n_null)
    ]
    hi = float(np.quantile(null, GATE_Q))
    earned = bool(real > hi)
    out: dict[str, Any] = {
        "stability": real,
        "null_hi": hi,
        "earned": earned,
        "core_size": None,
        "moons": [],
    }
    if earned:
        core_size, cut = moon_cut(vn, seed=seed + 300, n_boot=n_boot)
        out["core_size"] = core_size
        out["moons"] = [{"member_idx": c["members"]} for c in cut]
    return out


def moons_cached(
    vn: NDArray[Any],
    member_paths: list[str],
    epoch: str,
    cache_path: Path,
    seed: int,
    n_boot: int = 25,
    n_null: int = 50,
) -> dict[str, Any]:
    """Wraps moon_gate with a JSON cache keyed by member_hash, which sorts
    paths and is therefore order-insensitive. moon_gate's own "member_idx" is
    NOT order-insensitive -- it indexes into this call's vn/member_paths row
    order, which can change across builds (map.json point order shifting)
    even when the member SET, and so the hash, does not. A cache hit that
    returned raw member_idx would then resolve to the wrong notes. Every
    moon is therefore resolved to stable member paths (and a path exemplar,
    computed here since this is the last point that has both vn and
    member_paths in the same row order) before caching. An entry from before
    this fix has no "paths" on its moons and is treated as a miss."""
    key = member_hash(member_paths, epoch)
    try:
        cache: dict[str, Any] = json.loads(cache_path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        cache = {}
    cached = cache.get(key)
    if cached is not None and all("paths" in mo for mo in cached.get("moons", [])):
        return cached
    result = moon_gate(vn, seed, n_boot=n_boot, n_null=n_null)
    for mo in result["moons"]:
        idx = mo.pop("member_idx")
        sub = vn[idx]
        medoid_local = idx[int(np.argmax(sub @ sub.mean(axis=0)))]
        mo["paths"] = [member_paths[i] for i in idx]
        mo["exemplar"] = member_paths[medoid_local]
    cache[key] = result
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache))
    return result


def _bake_cached(cache_path: Path, h: str, name: str, out_path: Path, bake: Any) -> None:
    """Read-check-write like moons_cached, keyed by the same member-set hash.
    A hit is trusted only when the cached entry's filename still matches the
    caller's current expected name AND the file is still on disk -- theme ids
    are rebuild-scoped, so a reshuffle can leave an unchanged member-set hash
    pointing at a stale name/file from a prior build.

    A filename can have only one live cache owner. Without that invariant, an
    A->B->A member-set revert on the same theme id aliases: build A bakes
    hash h1 under "0.png"; build B reassigns "0.png" to a different member
    set (hash h2), overwriting the file; build C reverts to h1's member set
    -- h1's entry still says name="0.png" and the file still exists, so it
    would validate as a hit and return build B's geography forever. Every
    write here therefore drops any OTHER hash's entry claiming this name (so
    the revert's h1 lookup correctly misses and re-bakes), and — when this
    same hash's own prior bake lived under a different name (a reshuffle, not
    a revert) — deletes that now-orphaned file."""
    key = f"tex:{h}"
    try:
        cache: dict[str, Any] = json.loads(cache_path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        cache = {}
    entry = cache.get(key)
    if entry and entry.get("name") == name and out_path.exists():
        return
    meta = bake()
    if entry and entry.get("name") and entry["name"] != name:
        (out_path.parent / entry["name"]).unlink(missing_ok=True)
    for other_key in [k for k, v in cache.items() if k != key and v.get("name") == name]:
        del cache[other_key]
    cache[key] = {"hash": h, "name": name, "meta": meta}
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache))


def attach_payload(
    vecs: NDArray[Any],
    c3: NDArray[Any],
    themes: NDArray[Any],
    dates: list[str | None],
    labels: list[str],
    paths: list[str],
    thumbs: list[str | None],
    titles: list[str],
    radial_pos: NDArray[Any],
    lattice_pos: NDArray[Any] | None,
    tex_dir: Path,
    cache_path: Path,
    epoch: str,
    moon_boot: int = 25,
    moon_null: int = 50,
    n_perm: int = 1000,
) -> dict[str, Any]:
    """Assembles the full content.galaxy payload: galaxy_block's per-planet
    fields decorated with a baked coast texture and the E33 gates (rings,
    spin, moons), member_paths/hash stripped since callers never see the raw
    member set. Moon seed offset (33 + theme) matches scripts/e33_channels.py
    so a rebuild reproduces the same cut for an unchanged member set.
    Normalizes vecs once here (not just per-theme inside galaxy_block/moons):
    ring_gate's v @ v.T assumes unit vectors and does not normalize on its
    own, so this is the one place a raw (non-unit) caller input is made safe
    for every consumer below."""
    from ytk import coast

    vecs = np.asarray(vecs, dtype=float)
    vecs = vecs / np.linalg.norm(vecs, axis=1, keepdims=True)
    c3 = np.asarray(c3, dtype=float)
    themes = np.asarray(themes)

    blocks = galaxy_block(vecs, c3, themes, dates, labels, paths, epoch)
    ids = [p["theme"] for p in blocks]
    rings = ring_gate(vecs, themes, ids, n_perm=n_perm)
    spins = spin_gate(themes, dates, ids, n_perm=n_perm)
    # moons_cached returns member/exemplar paths, not indices (a cache hit's
    # indices would otherwise be stale against this call's point order) --
    # resolved back to a global row via this lookup, built once
    path_to_gi = {p: i for i, p in enumerate(paths)}

    tex_dir.mkdir(parents=True, exist_ok=True)
    # ~1KB and content-free of member data: rewritten every build rather than
    # cached, so a ramp change ships without a cache bust
    coast.bake_ramp(tex_dir / "ramp.png")
    planets: list[dict[str, Any]] = []
    for block in blocks:
        t = block["theme"]
        h = block.pop("hash")
        block.pop("member_paths")
        m = np.flatnonzero(themes == t)
        tex_name = f"{t}.png"
        tex_path = tex_dir / tex_name
        _bake_cached(
            cache_path,
            h,
            tex_name,
            tex_path,
            lambda m=m, tex_path=tex_path: coast.bake_planet(c3[m], tex_path),
        )
        block["tex"] = tex_name

        r = rings[t]
        block["rings"] = {
            "earned": r["earned"],
            "partners": [{"theme": pt["theme"], "z": pt["z"]} for pt in r["partners"]],
        }
        s = spins[t]
        block["spin"] = {
            "earned": s["earned"],
            "side": s["side"],
            "median_age_days": s["median_age_days"] if s["n_dated"] else None,
        }

        vn = vecs[m]
        vn = vn / np.linalg.norm(vn, axis=1, keepdims=True)
        member_paths = [paths[int(i)] for i in m]
        moon_result = moons_cached(
            vn, member_paths, epoch, cache_path, seed=33 + t, n_boot=moon_boot, n_null=moon_null
        )
        moons_out: list[dict[str, Any]] = []
        for moon in moon_result["moons"]:
            gi = path_to_gi[moon["exemplar"]]
            moons_out.append(
                {
                    "size": len(moon["paths"]),
                    "path": paths[gi],
                    "title": titles[gi],
                    "thumb": thumbs[gi] or None,
                }
            )
        block["moons"] = moons_out
        planets.append(block)

    if lattice_pos is not None:
        h_all = member_hash(paths, epoch)
        sp_path = tex_dir / "superplanet.png"
        _bake_cached(
            cache_path,
            h_all,
            "superplanet.png",
            sp_path,
            lambda: coast.bake_superplanet(radial_pos, lattice_pos, sp_path),
        )

    return {
        "epoch": epoch,
        "k_deg": GALAXY_K,
        "generated": datetime.date.today().isoformat(),
        "planets": planets,
    }
