# pyright: basic
# Not strict-clean yet (#122). Delete these two lines once the module
# passes strict — the list of files carrying them only shrinks.
"""Interactive tag consolidation (hub /tags route).

The 439-tag vocabulary is ~83% singletons, much of it synonym drift
(ai-coding / agentic-coding / coding-agents). Cleanup pipeline:

1. Embed every tag with the store's sentence-transformer and single-link
   cluster at high cosine similarity. Empirically (2026-07-05): 0.92 yields
   ~33 high-precision groups; 0.88 chains unrelated tags into one blob;
   below that, short strings cluster by surface form (mcp | cpp).
2. One batched Haiku pass refines the clusters: splits over-merged groups,
   vetoes false neighbors (3d-printing vs 3d-animation), and nominates the
   canonical spelling. Output is clamped to the proposed clusters — the
   model picks, it never invents.
3. The user reviews in the hub and batch-applies. Accepted merges rewrite
   note frontmatter + Chroma metadata and persist to the alias map, which
   _normalize_tag and the Enrichment validator consult forever after.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from . import store
from .config import save_tag_aliases
from .sdk import structured

SIM_THRESHOLD = 0.92


class MergeGroup(BaseModel):
    canonical: str
    variants: list[str] = Field(default_factory=list)  # retired into canonical
    counts: dict[str, int] = Field(default_factory=dict)


class _Refinement(BaseModel):
    groups: list[MergeGroup]


def _clusters(tags: list[str]) -> list[list[str]]:
    """Single-link groups of embedding-similar tags at SIM_THRESHOLD."""
    import numpy as np

    vecs = np.array(store._get_ef()(tags))
    vecs = vecs / np.linalg.norm(vecs, axis=1, keepdims=True)
    sim = vecs @ vecs.T
    np.fill_diagonal(sim, 0)

    parent = list(range(len(tags)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, j in zip(*np.where(sim > SIM_THRESHOLD)):
        if i < j:
            parent[find(i)] = find(j)

    groups: dict[int, list[str]] = {}
    for i in range(len(tags)):
        groups.setdefault(find(i), []).append(tags[i])
    return [g for g in groups.values() if len(g) > 1]


_SYSTEM = """You refine candidate tag-merge groups for a personal knowledge vault.

Each CANDIDATE GROUP contains tags whose embeddings are similar. Some groups are true synonym families that should merge; some mix distinct topics and must be split into smaller groups or rejected entirely.

For every set of tags that genuinely mean the same topic, emit one group:
- canonical: the best spelling, preferring the most-used tag (usage counts are shown) unless a variant is clearly better English.
- variants: the other tags in that set, to be retired into canonical.

Rules: only use tags exactly as listed, never invent tags, never put tags from different candidate groups into one output group. Distinct topics (e.g. 3d-printing vs 3d-animation) must NOT merge even if lexically similar. When in doubt, keep tags separate — a wrong merge destroys information."""


def propose_merges() -> list[MergeGroup]:
    """Cluster + Haiku-refine. Returns [] when the vocabulary is clean."""
    counts = store.tag_counts()
    if not counts:
        return []
    clusters = _clusters(list(counts))
    if not clusters:
        return []

    listing = "\n\n".join(
        "CANDIDATE GROUP:\n" + "\n".join(f"- {t} (used {counts[t]}x)" for t in c) for c in clusters
    )
    refined = structured(_SYSTEM, listing, _Refinement, max_input_chars=60_000)

    # clamp: every output group must live inside one proposed cluster
    out: list[MergeGroup] = []
    for g in refined.groups:
        members = [t for t in [g.canonical, *g.variants] if any(t in c for c in clusters)]
        home = next((set(c) for c in clusters if g.canonical in c), set())
        members = [t for t in dict.fromkeys(members) if t in home]
        if len(members) < 2:
            continue
        canonical = g.canonical if g.canonical in members else members[0]
        variants = [t for t in members if t != canonical]
        out.append(
            MergeGroup(
                canonical=canonical,
                variants=variants,
                counts={t: counts[t] for t in members},
            )
        )
    return out


def apply_merges(mapping: dict[str, str]) -> dict:
    """Apply accepted {variant: canonical} merges everywhere tags live.

    Order matters: alias map first (future ingests), then note frontmatter
    (source of truth), then Chroma metadata (search index).
    """
    mapping = {v: c for v, c in mapping.items() if v and c and v != c}
    if not mapping:
        return {"aliases": 0, "notes": 0, "videos": 0}
    save_tag_aliases(mapping)
    notes = _rewrite_frontmatter(mapping)
    videos = _rewrite_chroma(mapping)
    return {"aliases": len(mapping), "notes": notes, "videos": videos}


def _rewrite_frontmatter(mapping: dict[str, str]) -> int:
    from . import vault

    changed = 0
    sources = vault._get_brain_path() / "sources"
    if not sources.exists():
        return 0
    for md in sources.glob("**/*.md"):
        text = md.read_text(encoding="utf-8")
        if not text.startswith("---"):
            continue
        fm_end = text.index("---", 4)
        fm = text[:fm_end]
        new_fm = fm
        for variant, canonical in mapping.items():
            if f"  - {variant}\n" not in new_fm:
                continue
            if f"  - {canonical}\n" in new_fm:
                new_fm = new_fm.replace(f"  - {variant}\n", "")
            else:
                new_fm = new_fm.replace(f"  - {variant}\n", f"  - {canonical}\n")
        if new_fm != fm:
            md.write_text(new_fm + text[fm_end:], encoding="utf-8")
            changed += 1
    return changed


def _rewrite_chroma(mapping: dict[str, str]) -> int:
    col = store._videos_collection()
    if col.count() == 0:
        return 0
    res = col.get(include=["metadatas"])
    ids, metas = [], []
    for doc_id, meta in zip(res["ids"], store.chroma_field(res["metadatas"], "metadatas")):
        tags = [t for t in store.meta_str(meta, "tags").split(", ") if t]
        new = list(dict.fromkeys(mapping.get(t, t) for t in tags))
        if new != tags:
            ids.append(doc_id)
            metas.append({**meta, "tags": ", ".join(new)})
    if ids:
        col.update(ids=ids, metadatas=metas)
    return len(ids)
