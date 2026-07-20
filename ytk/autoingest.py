"""Profile-matched auto-ingest: pull a small, diverse batch of pending items
that best match the interest profile, on a heavily-debounced schedule.

The selection is stratified by interest theme rather than pure top-k: pure
top-k collapses onto the single largest theme, so slots are spread across
themes (proportional to theme weight, with a floor) and the best-matching
items are taken within each. A loved creator's items get a score boost; a
muted creator's are excluded outright.

This module owns the pure selection algorithm; scoring (embedding pending text
against theme centroids) and the ingest/run glue live alongside it and are the
only parts that touch the encoder and the ingest pipeline.
"""

from __future__ import annotations

from collections import defaultdict

# A run never ingests more than this, whatever config or a caller asks for —
# auto-ingest bypasses human triage, so the blast radius stays bounded.
HARD_CAP = 50

# Additive bonus applied to a loved creator's items, on the cosine-similarity
# scale (roughly [-1, 1]); large enough to float a loved item over a modestly
# better-matching stranger, small enough not to swamp a strong theme match.
LOVED_BOOST = 0.15


def allocate_slots(theme_weights: dict[str, float], themes: list[str], count: int) -> dict[str, int]:
    """Split `count` slots across the present themes, proportional to weight
    with a floor of 1 each. Largest-remainder rounding; may over/undershoot
    count slightly, which the selection step reconciles against availability.
    """
    present = [t for t in themes if t in theme_weights] or themes
    total = sum(theme_weights.get(t, 0.0) for t in present) or float(len(present))
    raw = {t: count * (theme_weights.get(t, 0.0) or (1.0 / len(present))) / total for t in present}
    alloc = {t: max(1, int(raw[t])) for t in present}
    # distribute leftover by largest fractional remainder
    used = sum(alloc.values())
    if used < count:
        order = sorted(present, key=lambda t: raw[t] - int(raw[t]), reverse=True)
        for t in order[: count - used]:
            alloc[t] += 1
    return alloc


def stratify_select(
    scored: list[dict],
    count: int,
    theme_weights: dict[str, float],
    loved_keys: frozenset[str] | set[str] = frozenset(),
    muted_keys: frozenset[str] | set[str] = frozenset(),
) -> list[dict]:
    """Choose up to `count` items, stratified across themes, loved-boosted.

    `scored` items are dicts with at least: `url` (identity), `theme_id`,
    `score` (float), and optional `channel_key`. Returns the chosen scored
    dicts (not the raw items), each annotated with `eff_score`, ordered by
    effective score descending.
    """
    if count <= 0:
        return []

    pool = []
    for s in scored:
        if s.get("channel_key") in muted_keys:
            continue
        eff = s["score"] + (LOVED_BOOST if s.get("channel_key") in loved_keys else 0.0)
        pool.append({**s, "eff_score": eff})
    if not pool:
        return []

    by_theme: dict[str, list[dict]] = defaultdict(list)
    for s in pool:
        by_theme[s["theme_id"]].append(s)
    for lst in by_theme.values():
        lst.sort(key=lambda x: x["eff_score"], reverse=True)

    alloc = allocate_slots(theme_weights, list(by_theme), count)

    chosen: list[dict] = []
    chosen_urls: set[str] = set()
    for theme, lst in by_theme.items():
        for s in lst[: alloc.get(theme, 1)]:
            chosen.append(s)
            chosen_urls.add(s["url"])

    chosen.sort(key=lambda x: x["eff_score"], reverse=True)
    if len(chosen) > count:
        # proportional rounding overshot: keep the globally strongest
        return chosen[:count]

    # undershot (themes ran out of items): backfill from the strongest leftovers
    if len(chosen) < count:
        leftover = [s for s in pool if s["url"] not in chosen_urls]
        leftover.sort(key=lambda x: x["eff_score"], reverse=True)
        chosen.extend(leftover[: count - len(chosen)])
        chosen.sort(key=lambda x: x["eff_score"], reverse=True)
    return chosen


def _theme_vectors(snapshot) -> list[tuple]:
    """(theme, centroid ndarray) pairs, centroids in the CURRENT embedding space.

    A stored centroid is only comparable in the space it was built in. If the
    snapshot's encoder differs from the live one, its stored centroids are
    dropped and rebuilt from the themes' note_ids with the current embedder;
    otherwise the stored centroids are used directly.
    """
    from ytk import store, synthesis

    if snapshot.embedding_model and snapshot.embedding_model != store._TEXT_MODEL:
        themes = [t.model_copy(update={"centroid": None}) for t in snapshot.themes]
        snap = snapshot.model_copy(update={"themes": themes})
    else:
        snap = snapshot
    cents = synthesis._theme_centroids(snap)
    return [(t, c) for t, c in zip(snapshot.themes, cents) if c is not None]


def score_pending(pending: list, theme_vecs: list[tuple], ingested: set) -> list[dict]:
    """Score each pending item that has usable text against the theme centroids.

    Items without text (most non-TikTok/Reddit sources carry no caption at
    discovery time) and already-ingested urls are skipped — auto-ingest only
    picks from what it can actually assess. Embedding uses the DOCUMENT path
    (store._get_ef), matching how the centroids were built, so the dot product
    of two normalized vectors is a true cosine.
    """
    import numpy as np

    from ytk import store
    from ytk.channels import channel_key

    cand = [
        it for it in pending
        if (getattr(it, "text", None) or "").strip() and it.url not in ingested
    ]
    if not cand or not theme_vecs:
        return []

    ef = store._get_ef()
    vecs = ef([(it.text or "").strip()[:2000] for it in cand])
    mat = np.asarray([c for _, c in theme_vecs], dtype=float)  # (T, D)
    ids = [t.id for t, _ in theme_vecs]

    scored = []
    for it, v in zip(cand, vecs):
        sims = mat @ np.asarray(v, dtype=float)
        bi = int(np.argmax(sims))
        key = channel_key(it.source, it.author) if it.author else None
        scored.append({
            "url": it.url, "item": it, "theme_id": ids[bi],
            "score": float(sims[bi]), "channel_key": key,
        })
    return scored


def _ingest_one(hub, item, thought: str):
    """Ingest one pending item through the existing pipeline, tag it, unqueue it."""
    import time

    from ytk import vault

    started = time.time()
    if item.source == "imessage":
        note = hub.INGEST_TEXT(item, thought)
    else:
        hub.INGEST(item.url, thought)
        note = hub.find_note_by_url(item.url, since=started - 5)
    if note:
        vault.annotate_note(note, ["auto-ingested"], thought)
    hub._remove_from_queue(item.url)
    return note


def run_autoingest(count: int | None = None, dry_run: bool = False) -> dict:
    """Select and (unless dry_run) ingest a profile-matched batch of pending items.

    Returns a report: {selected:[...], candidates:int, ingested:[url...], error?}.
    """
    from ytk import channels, interest, reels, store
    from ytk.config import load_config
    from ytk.ui import hub

    cfg = load_config()
    n = max(0, min(count or cfg.autoingest_count, HARD_CAP))

    snapshot = interest.load_latest()
    if snapshot is None:
        return {"error": "no interest profile — run `ytk profile` first", "selected": [], "candidates": 0, "ingested": []}
    theme_vecs = _theme_vectors(snapshot)
    if not theme_vecs:
        return {"error": "profile has no usable theme centroids", "selected": [], "candidates": 0, "ingested": []}

    weights = {t.id: t.weight for t, _ in theme_vecs}
    labels = {t.id: t.label for t, _ in theme_vecs}
    state = reels.load_state()
    ingested = hub.ingested_urls()

    store.warm_text_encoder()
    scored = score_pending(state.pending, theme_vecs, ingested)
    selected = stratify_select(
        scored, n, weights,
        loved_keys=channels.loved_channels(),
        muted_keys=channels.muted_channels(),
    )

    picks = [{
        "url": s["url"],
        "title": (s["item"].text or s["item"].author or s["url"])[:70],
        "source": s["item"].source,
        "theme": labels.get(s["theme_id"], s["theme_id"]),
        "score": round(s["eff_score"], 3),
    } for s in selected]

    if dry_run:
        return {"selected": picks, "candidates": len(scored), "ingested": []}

    ingested_urls: list[str] = []
    failures: list[dict] = []
    for s in selected:
        item = s["item"]
        thought = f"auto-ingested · matched {labels.get(s['theme_id'], '')}"
        try:
            _ingest_one(hub, item, thought)
            ingested_urls.append(item.url)
        except Exception as exc:
            failures.append({"url": item.url, "error": str(exc)})
    return {"selected": picks, "candidates": len(scored), "ingested": ingested_urls, "failures": failures}
