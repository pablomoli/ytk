"""Does warm-starting the daily KMeans refit cut identity churn? (#83, section 38)

The #83 threshold sweep measured the post-fit matcher's ceiling: ~5-7
lifecycle events on quiet daily transitions, caused by the refit itself.
This experiment asks whether seeding each day's KMeans with the previous
day's fitted centroids (the demoted warm-start half of the PCM plan) reduces
that churn, and what it costs in partition quality.

Design: the last snapshot of each calendar day from 2026-07-18 on gives 10
corpora (live-embedding coverage ~100%). Per seed, two chains over the same
corpora: cold = production behavior, fresh KMeans(n_init=10) daily (seed 0 IS
production, other seeds probe init sensitivity); warm = identical day 0, then
init from the previous day's centroids, farthest-point-extended when k grows,
n_init=1. Consecutive partitions run through the real identity.reconcile
(centroid fallback included), so the outcome is the production event count.
Guards: silhouette (cosine) and inertia — the 2026-07-17 sample-weight lesson
says interventions here can collapse the partition, so quality is measured,
never assumed. Paired per-seed deltas, 20 seeds.

Run: uv run python experiments/warmstart_identity.py
Writes experiments/warmstart_identity_results.json.
"""

from __future__ import annotations

import json
import subprocess
from collections import Counter
from pathlib import Path

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

from ytk import identity
from ytk.config import load_config
from ytk.interest import InterestSnapshot, Theme
from ytk.synthesis import _embeddings_by_id, choose_k

SEEDS = 20
OUT = Path(__file__).with_name("warmstart_identity_results.json")


def day_corpora() -> list[tuple[str, list[str]]]:
    """(day, note_ids) for the last snapshot of each day from 2026-07-18 on."""
    d = Path.home() / ".ytk" / "interest"
    by_day: dict[str, Path] = {}
    for p in sorted(d.glob("snapshot-*.json")):
        day = p.name[9:17]
        if day >= "20260718":
            by_day[day] = p
    out = []
    for day, p in sorted(by_day.items()):
        snap = json.loads(p.read_text())
        out.append((day, [i for t in snap["themes"] for i in t["note_ids"]]))
    return out


def farthest_extend(X: np.ndarray, centroids: np.ndarray, k: int) -> np.ndarray:
    """Grow the centroid set to k by greedy max-min-distance points of X."""
    cents = list(centroids)
    d2 = np.min(((X[:, None, :] - np.asarray(cents)[None]) ** 2).sum(-1), axis=1)
    while len(cents) < k:
        idx = int(np.argmax(d2))
        cents.append(X[idx])
        d2 = np.minimum(d2, ((X - X[idx]) ** 2).sum(-1))
    return np.asarray(cents)


def shrink(centroids: np.ndarray, labels: np.ndarray, k: int) -> np.ndarray:
    """Drop the least-populated centroids down to k."""
    counts = Counter(labels)
    keep = [c for c, _ in counts.most_common(k)]
    return centroids[sorted(keep)]


def fit_cold(X: np.ndarray, k: int, seed: int) -> KMeans:
    return KMeans(n_clusters=k, random_state=seed, n_init=10).fit(X)


def fit_warm(X: np.ndarray, k: int, prev: KMeans) -> KMeans:
    init = prev.cluster_centers_
    if len(init) < k:
        init = farthest_extend(X, init, k)
    elif len(init) > k:
        init = shrink(init, prev.labels_, k)
    return KMeans(n_clusters=k, init=init, n_init=1).fit(X)


def to_snapshot(day: str, ids: list[str], labels: np.ndarray) -> InterestSnapshot:
    themes = [
        Theme(
            id=str(c),
            label=f"c{c}",
            summary="",
            weight=0.0,
            note_ids=[ids[i] for i in np.flatnonzero(labels == c)],
            exemplar_titles=[],
        )
        for c in sorted(set(labels.tolist()))
    ]
    return InterestSnapshot(
        generated_at=day, note_count=len(ids), themes=themes, profile_markdown="x"
    )


def unit_centroids(X: np.ndarray, labels: np.ndarray) -> list[np.ndarray | None]:
    out: list[np.ndarray | None] = []
    for c in sorted(set(labels.tolist())):
        m = X[labels == c].mean(axis=0)
        n = np.linalg.norm(m)
        out.append(m / n if n else m)
    return out


def run_chain(corpora, embs, ks, seed: int, warm: bool) -> list[dict]:
    """Fit the 10-day chain, reconcile consecutive days, return per-transition rows."""
    rows = []
    prev_fit = prev_snap = prev_cents = None
    prev_map: dict[str, str] = {}
    for t, ((day, ids), X, k) in enumerate(zip(corpora, embs, ks)):
        fit = fit_warm(X, k, prev_fit) if warm and prev_fit is not None else fit_cold(X, k, seed)
        snap = to_snapshot(day, ids, fit.labels_)
        cents = unit_centroids(X, fit.labels_)
        if prev_snap is None:
            identity.reconcile(None, snap)  # mint day-0 ids so churn compares lineages
        else:
            identity.reconcile(prev_snap, snap, old_centroids=prev_cents, new_centroids=cents)
            id_map = {i: t_.theme_id for t_ in snap.themes for i in t_.note_ids}
            shared = [i for i in prev_map if i in id_map]
            churn = sum(1 for i in shared if id_map[i] != prev_map[i]) / len(shared)
            rows.append(
                {
                    "day": day,
                    "events": len(snap.events),
                    "event_kinds": dict(Counter(e.kind for e in snap.events)),
                    "churn": round(churn, 4),
                    "silhouette": round(
                        float(silhouette_score(X, fit.labels_, metric="cosine")), 4
                    ),
                    "inertia": round(float(fit.inertia_), 2),
                    "max_share": round(max(Counter(fit.labels_.tolist()).values()) / len(ids), 4),
                }
            )
        prev_fit, prev_snap, prev_cents = fit, snap, cents
        prev_map = {i: t_.theme_id for t_ in snap.themes for i in t_.note_ids}
    return rows


def main() -> None:
    cfg = load_config()
    emb = _embeddings_by_id()
    corpora = [(d, [i for i in ids if i in emb]) for d, ids in day_corpora()]
    embs = [np.asarray([emb[i] for i in ids], dtype=float) for _, ids in corpora]
    ks = [choose_k(len(ids), cfg.interest) for _, ids in corpora]
    print("days:", [(d, len(ids), k) for (d, ids), k in zip(corpora, ks)])

    results = {"cold": [], "warm": []}
    for seed in range(SEEDS):
        for cond in ("cold", "warm"):
            rows = run_chain(corpora, embs, ks, seed, warm=(cond == "warm"))
            results[cond].append({"seed": seed, "transitions": rows})
        c = np.mean([r["events"] for r in results["cold"][-1]["transitions"]])
        w = np.mean([r["events"] for r in results["warm"][-1]["transitions"]])
        print(f"seed {seed:2d}  events/transition  cold {c:.1f}  warm {w:.1f}")

    sha = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    OUT.write_text(
        json.dumps(
            {
                "commit": sha,
                "seeds": SEEDS,
                "days": [d for d, _ in corpora],
                "n_per_day": [len(ids) for _, ids in corpora],
                "k_per_day": ks,
                "results": results,
            },
            indent=1,
        )
    )
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
