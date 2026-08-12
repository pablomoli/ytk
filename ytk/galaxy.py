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
