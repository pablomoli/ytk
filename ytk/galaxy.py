"""Production home of the E32/E33 galaxy machinery; the experiments in
scripts/ are the committed record.

Ported from `scripts/e31_theme_planets.py` (`CLASSES`, `classify`) and
`scripts/e32_galaxy.py` (`arm_a`, `all_planets`) — same precedent as
`ytk/coast.py`. `galaxy_block` mirrors `all_planets()` but takes data as
arguments (no map.json reads), and adds `median_age_days` and the
`member_paths`/`hash` cache-key fields the moon and texture caches key off.
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

# galaxy_block's own schema/version tag for member_hash — deliberately not
# the embedding epoch (ytk.store), so this module stays numpy+stdlib only;
# bump on a member_hash payload format change
BLOCK_EPOCH = "v1"

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
                "hash": member_hash(member_paths, BLOCK_EPOCH),
            }
        )
    return out
