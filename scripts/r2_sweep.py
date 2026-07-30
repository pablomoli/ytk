"""R2 sweep (#150): recency decay for memory hits, measured.

Builds a current-state query set from organic memory pairs (same evolving
thing, 2+ dated docs; the newest is gold), sweeps lambda x half-life through
the production apply_memory_decay on over-fetched production search results,
and renders r2-decay-sweep.png. Kept OUTSIDE the frozen gate set.

    uv run --with matplotlib python scripts/r2_sweep.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from memory_field_audits import figure, footer, is_imported, memory_embeddings, save, stamp
from plot_assets import BLUE, GOLD, MARGIN, MUTED, RED, TEXT, panel_title, style_axes

QUERIES_PATH = (
    Path(__file__).resolve().parents[1] / "eval" / "retrieval" / "current_state_queries.jsonl"
)
DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
STOP = {
    "the",
    "a",
    "of",
    "to",
    "and",
    "in",
    "for",
    "on",
    "with",
    "is",
    "are",
    "was",
    "were",
    "at",
    "by",
    "an",
    "or",
    "it",
    "this",
    "that",
}


def doc_date(doc_id: str) -> str:
    m = DATE_RE.search(doc_id)
    return m.group(1) if m else ""


def topic_words(doc_id: str) -> list[str]:
    """Slug words from the whole doc id: drop structural prefixes, dates, and
    hash-like tails; keep the human topic vocabulary."""
    slug = re.sub(r"^(note|memory)_", "", doc_id)
    slug = re.sub(
        r"(inbox|memories|sources|projects|second-brain|summaries|claude-mem)_?", "", slug
    )
    slug = DATE_RE.sub("", slug)
    words = [w.lower() for w in re.split(r"[-_/]", slug)]
    return [
        w
        for w in words
        if w.isalpha() and w not in STOP and len(w) > 2 and not re.fullmatch(r"[0-9a-f]{6,}", w)
    ]


def build_queries() -> list[dict]:
    ids, embs = memory_embeddings()
    keep = [i for i, d in enumerate(ids) if not is_imported(d) and doc_date(d)]
    ids = [ids[i] for i in keep]
    embs = embs[keep]
    normed = embs / np.linalg.norm(embs, axis=1, keepdims=True)
    sims = normed @ normed.T
    iu = np.triu_indices(len(ids), k=1)
    order = np.argsort(sims[iu])[::-1]

    queries, used = [], set()
    for k in order[:400]:
        i, j = iu[0][k], iu[1][k]
        if sims[i, j] < 0.68:
            break
        a, b = ids[i], ids[j]
        da, db = doc_date(a), doc_date(b)
        if da == db or a in used or b in used:
            continue
        gold, older = (a, b) if da > db else (b, a)
        shared = [w for w in topic_words(gold) if w in set(topic_words(older))]
        if len(shared) < 2:
            continue
        queries.append(
            {
                "query": " ".join(dict.fromkeys(shared)),
                "gold": gold,
                "older": older,
                "sim": round(float(sims[i, j]), 3),
            }
        )
        used.update((a, b))
        if len(queries) >= 20:
            break
    return queries


def sweep(queries: list[dict]):
    from ytk.store import apply_memory_decay, search_all

    pools = []
    for q in queries:
        pools.append(list(search_all(q["query"], n=30, rerank=False)))

    def mrr(lam: float, half: float) -> float:
        rr = []
        for q, pool in zip(queries, pools):
            ranked = apply_memory_decay(pool, lam, half) if lam else pool
            rank = next((i + 1 for i, r in enumerate(ranked) if r.doc_id == q["gold"]), None)
            rr.append(1.0 / rank if rank else 0.0)
        return float(np.mean(rr))

    lams = [0.0, 0.05, 0.1, 0.2]
    halves = [30.0, 90.0, 180.0]
    grid = {(lam, h): mrr(lam, h) for lam in lams for h in halves}
    return lams, halves, grid


def main() -> None:
    if QUERIES_PATH.exists():
        queries = [json.loads(line) for line in QUERIES_PATH.read_text().splitlines()]
    else:
        queries = build_queries()
        QUERIES_PATH.write_text("\n".join(json.dumps(q) for q in queries) + "\n")
    print(f"{len(queries)} current-state queries:")
    for q in queries:
        print(f"  [{q['sim']}] '{q['query']}'  gold={q['gold'][:70]}")

    lams, halves, grid = sweep(queries)
    base = grid[(0.0, halves[0])]
    print(f"\nbaseline MRR (lambda=0): {base:.3f}")
    for (lam, h), v in sorted(grid.items()):
        if lam:
            print(f"  lam={lam:<5} half={h:>5.0f}d  MRR {v:.3f}  ({v - base:+.3f})")

    # paired bootstrap on per-query deltas for the best combo — a bare
    # aggregate mean on n=16 is exactly the agglo-vs-HDBSCAN trap
    from ytk.store import apply_memory_decay, search_all

    best = max(((lam, h) for lam in lams if lam for h in halves), key=lambda k: grid[k])
    rng = np.random.default_rng(0)
    deltas = []
    for q in queries:
        pool = search_all(q["query"], n=30, rerank=False)

        def rr(ranked):
            rank = next((i + 1 for i, r in enumerate(ranked) if r.doc_id == q["gold"]), None)
            return 1.0 / rank if rank else 0.0

        deltas.append(rr(apply_memory_decay(pool, *best)) - rr(pool))
    deltas = np.array(deltas)
    boots = np.array([rng.choice(deltas, len(deltas)).mean() for _ in range(10_000)])
    lo, hi = np.percentile(boots, [2.5, 97.5])
    ci_line = f"best combo lam={best[0]} half={best[1]:.0f}d: delta {deltas.mean():+.3f}, 95% CI [{lo:+.3f}, {hi:+.3f}]"
    print(ci_line)

    meta = f"{len(queries)} queries, gold = newest doc of an organic near-pair · baseline MRR {base:.3f} · {ci_line}"
    fig, top = figure(
        10.5,
        6.4,
        6,
        "memory-field R2 — decay sweep on the current-state set",
        "Recency decay: MRR by lambda and half-life",
        meta,
    )
    ax = fig.add_axes([MARGIN + 0.05, 0.16, 1 - 2 * MARGIN - 0.09, top - 0.20])
    style_axes(ax)
    colors = {30.0: GOLD, 90.0: BLUE, 180.0: RED}
    for h in halves:
        ax.plot(
            lams,
            [grid[(lam, h)] for lam in lams],
            marker="o",
            color=colors[h],
            label=f"half-life {h:.0f}d",
        )
    ax.axhline(base, color=MUTED, linewidth=0.9, linestyle="--")
    ax.set_xlabel("lambda (boost strength)")
    ax.set_ylabel("MRR, gold = newest")
    ax.legend(loc="best", frameon=False, labelcolor=TEXT, fontsize=9)
    panel_title(ax, "Boost-only blend on production search results; dashed line = no decay")
    footer(
        fig,
        f"{stamp()} · queries auto-built from shared slug tokens of near-pairs (topic-neutral by construction, "
        "printed and reviewed) · confounds: pool fixed at plain top-30, n=16 and the CI barely excludes zero — "
        "default stays OFF until the set grows and the gain survives",
    )
    save(fig, "r2-decay-sweep.png")


if __name__ == "__main__":
    main()
