# pyright: basic
# Not strict-clean yet (#122). Delete these two lines once the module
# passes strict — the list of files carrying them only shrinks.
"""Stable theme identity across profile snapshots (#83, phase 1).

Matching is membership-first: containment |old ∩ new| / |old| asks whether the
new cluster still holds the old theme's notes — the provenance question — and
needs no embedding space, so it survives the encoder swaps in the stored
history (MiniLM -> gte-small -> Qwen3). Centroid cosine is only a fallback for
pairs whose member ids did not survive; a fallback match keeps the id but is
recorded as a "restated" event because membership continuity was broken.

Lifecycle events (birth/death/merge/split/restated) are computed here, at
synthesis time, and persisted in the snapshot. Render layers replay them.
"""

from __future__ import annotations

import re

import numpy as np

from .interest import (
    InterestSnapshot,
    LifecycleEvent,
    SnapshotDiff,
    Theme,
    ThemeMatch,
)

# Below this share of surviving members, membership continuity is not credible.
# Calibrated on the 2026-06..08 replay: daily KMeans refits put same-label
# themes at 0.38-0.48 containment, while genuine re-clusterings sit <= 0.33.
CONTAINMENT_FLOOR = 0.35
# A fragment holding this share of an old theme is a spin-off, not churn.
SPLIT_FRACTION = 0.3
# Fallback cosine floor. Replay showed 0.75 lets an id chain across genuinely
# different content (0.77-0.83 band); credible restatements measured 0.86+.
CENTROID_FLOOR = 0.85

_ID_RE = re.compile(r"^T(\d+)$")

Pair = tuple[int, int, float]  # (old index, new index, match score)


def _next_counter(themes: list[Theme]) -> int:
    nums = [int(m.group(1)) for t in themes if t.theme_id and (m := _ID_RE.match(t.theme_id))]
    return max(nums, default=0) + 1


def _mint(theme: Theme, counter: int) -> int:
    theme.theme_id = f"T{counter:03d}"
    return counter + 1


def _containment(old: set[str], new: set[str]) -> float:
    return len(old & new) / len(old) if old else 0.0


def _cosine(a: np.ndarray | None, b: np.ndarray | None) -> float | None:
    """Cosine between two unit centroids; None when incomparable.

    Shape mismatch means different encoders — cosine across embedding spaces
    is meaningless, so the pair is incomparable rather than dissimilar.
    """
    if a is None or b is None or a.shape != b.shape:
        return None
    return float(a @ b)


def reconcile(
    previous: InterestSnapshot | None,
    snapshot: InterestSnapshot,
    old_centroids: list[np.ndarray | None] | None = None,
    new_centroids: list[np.ndarray | None] | None = None,
) -> list[Pair]:
    """Assign stable theme_ids to snapshot and record lifecycle events, in place.

    Returns the matched (old_index, new_index, score) pairs for drift rendering.
    Mutates ``previous`` only when it predates the identity layer, minting ids
    in theme order so a lineage can start from an unstamped snapshot.
    """
    events: list[LifecycleEvent] = []
    if previous is None:
        counter = 1
        for t in snapshot.themes:
            counter = _mint(t, counter)
            events.append(LifecycleEvent(kind="birth", theme_id=t.theme_id or "", label=t.label))
        snapshot.events = events
        snapshot.reconciled_from = None
        return []

    counter = _next_counter(previous.themes)
    for t in previous.themes:
        if t.theme_id is None:
            counter = _mint(t, counter)

    old_sets = [set(t.note_ids) for t in previous.themes]
    new_sets = [set(t.note_ids) for t in snapshot.themes]

    scored: list[Pair] = []
    for i, o in enumerate(old_sets):
        for j, n in enumerate(new_sets):
            c = _containment(o, n)
            if c > 0:
                scored.append((i, j, c))
    scored.sort(key=lambda p: (p[2], len(old_sets[p[0]] & new_sets[p[1]])), reverse=True)

    used_old: set[int] = set()
    used_new: set[int] = set()
    matched: list[Pair] = []

    def claim(i: int, j: int, score: float) -> None:
        used_old.add(i)
        used_new.add(j)
        snapshot.themes[j].theme_id = previous.themes[i].theme_id
        matched.append((i, j, score))

    for i, j, c in scored:
        if c < CONTAINMENT_FLOOR or i in used_old or j in used_new:
            continue
        claim(i, j, c)

    # Spin-offs: a matched old theme that also left a sizable fragment in an
    # unclaimed new theme split — the fragment is a spin-off, not a birth.
    for i, j0, _ in matched:
        o = old_sets[i]
        if not o:
            continue
        frags = [
            (c, j)
            for j in range(len(new_sets))
            if j not in used_new and (c := _containment(o, new_sets[j])) >= SPLIT_FRACTION
        ]
        if not frags:
            continue
        spun: list[str] = []
        for c, j in sorted(frags, reverse=True):
            counter = _mint(snapshot.themes[j], counter)
            used_new.add(j)
            spun.append(snapshot.themes[j].theme_id or "")
        events.append(
            LifecycleEvent(
                kind="split",
                theme_id=previous.themes[i].theme_id or "",
                label=snapshot.themes[j0].label,
                others=spun,
                detail=f"fragments {', '.join(f'{c:.2f}' for c, _ in sorted(frags, reverse=True))}",
            )
        )

    # Splits: an old theme whose members fragment into several unclaimed new
    # themes continues as its largest fragment; the rest are spin-offs.
    for i, o in enumerate(old_sets):
        if i in used_old or not o:
            continue
        fragments = sorted(
            ((_containment(o, new_sets[j]), j) for j in range(len(new_sets)) if j not in used_new),
            reverse=True,
        )
        fragments = [(c, j) for c, j in fragments if c >= SPLIT_FRACTION]
        if len(fragments) < 2:
            continue
        head_c, head_j = fragments[0]
        claim(i, head_j, head_c)
        spun: list[str] = []
        for c, j in fragments[1:]:
            counter = _mint(snapshot.themes[j], counter)
            used_new.add(j)
            spun.append(snapshot.themes[j].theme_id or "")
        events.append(
            LifecycleEvent(
                kind="split",
                theme_id=previous.themes[i].theme_id or "",
                label=snapshot.themes[head_j].label,
                others=spun,
                detail=f"fragments {', '.join(f'{c:.2f}' for c, _ in fragments)}",
            )
        )

    # Mergers: an unmatched old theme whose members dominantly land in an
    # already-claimed new theme was absorbed, not killed.
    absorbed: set[int] = set()
    for i, o in enumerate(old_sets):
        if i in used_old or not o:
            continue
        best_c, best_j = max(
            ((_containment(o, n), j) for j, n in enumerate(new_sets)), default=(0.0, -1)
        )
        if best_c >= CONTAINMENT_FLOOR and best_j in used_new:
            absorbed.add(i)
            events.append(
                LifecycleEvent(
                    kind="merge",
                    theme_id=snapshot.themes[best_j].theme_id or "",
                    label=snapshot.themes[best_j].label,
                    others=[previous.themes[i].theme_id or ""],
                    detail=f"absorbed {previous.themes[i].label} (containment {best_c:.2f})",
                )
            )

    # Centroid fallback for whatever membership could not settle: identity
    # continues, but the broken member trail is recorded as "restated".
    if old_centroids is not None and new_centroids is not None:
        cos_pairs = []
        for i in range(len(old_sets)):
            if i in used_old or i in absorbed:
                continue
            for j in range(len(new_sets)):
                if j in used_new:
                    continue
                sim = _cosine(old_centroids[i], new_centroids[j])
                if sim is not None and sim >= CENTROID_FLOOR:
                    cos_pairs.append((sim, i, j))
        cos_pairs.sort(reverse=True)
        for sim, i, j in cos_pairs:
            if i in used_old or j in used_new:
                continue
            claim(i, j, sim)
            events.append(
                LifecycleEvent(
                    kind="restated",
                    theme_id=previous.themes[i].theme_id or "",
                    label=snapshot.themes[j].label,
                    detail=f"membership lost, centroid cosine {sim:.2f}",
                )
            )

    for i, t in enumerate(previous.themes):
        if i not in used_old and i not in absorbed:
            events.append(LifecycleEvent(kind="death", theme_id=t.theme_id or "", label=t.label))
    for j, t in enumerate(snapshot.themes):
        if j not in used_new:
            counter = _mint(t, counter)
            events.append(LifecycleEvent(kind="birth", theme_id=t.theme_id or "", label=t.label))

    snapshot.events = events
    snapshot.reconciled_from = previous.generated_at
    return matched


def as_diff(
    previous: InterestSnapshot, snapshot: InterestSnapshot, pairs: list[Pair]
) -> SnapshotDiff:
    """SnapshotDiff view of a reconciliation, so drift prose and stored events
    can never disagree about what matched."""
    return SnapshotDiff(
        old_generated_at=previous.generated_at,
        new_generated_at=snapshot.generated_at,
        matched=[
            ThemeMatch(
                old_label=previous.themes[i].label,
                new_label=snapshot.themes[j].label,
                old_weight=previous.themes[i].weight,
                new_weight=snapshot.themes[j].weight,
                similarity=round(s, 3),
            )
            for i, j, s in pairs
        ],
        born=[e.label for e in snapshot.events if e.kind == "birth"],
        died=[e.label for e in snapshot.events if e.kind == "death"],
    )
