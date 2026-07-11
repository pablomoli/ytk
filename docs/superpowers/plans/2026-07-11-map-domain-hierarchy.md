# Map Domain Hierarchy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the /map everything-view around a controlled domain → subtopic hierarchy with uniform-driven, organically growing focus transitions, fixing the mis-pick, hover-dim, and legend-order bugs.

**Architecture:** `build_map.py` derives a deterministic domain per point (session filenames, memory-folder slugs, interest themes for content) and runs HDBSCAN per domain for subtopics, emitting schema v2. The WebGL renderer moves group dimming from baked vertex alphas into per-group uniform arrays swept by a clamped-cosine growth ramp against a per-point phase attribute; focus/hover changes become pure uniform animation (no buffer rebuild). The route gains a two-level legend, clickable canvas labels, and hash-persisted focus.

**Tech Stack:** Python 3.13 (uv, chromadb, umap-learn, scikit-learn, pytest), TypeScript + React 19 + TanStack Router (Vite, vitest), raw WebGL1 GLSL ES 1.00, Playwright (headless smoke).

**Spec:** `docs/superpowers/specs/2026-07-11-map-domain-hierarchy-design.md`

## Global Constraints

- No emojis anywhere. No conversational comments in code — document normally.
- Domain threshold: domains with fewer than **40** points merge into `other`.
- Per-domain clustering only for domains with **>= 120** points; `min_cluster_size = max(20, n // 50)`, `min_samples = 10`.
- Uniform caps: **32 domains**, **96 subtopics** — build warns beyond these.
- Content categories: `youtube, instagram, tiktok, pinterest, web, screenshots`; theme confidence floor stays the 25th percentile.
- Schema v2 marker: top-level `"v": 2`. The UI requires it — no compatibility shim.
- Growth ramp (GLSL and TS): `ramp(p) = 0.5 - 0.5 * cos(clamp(p, 0, 1) * PI)`; group-state sweep uses `ramp(t * 1.6 - phase * 0.6)`.
- Intro plays on hard document load only (module-level flag), skipped when the URL has a `#d:` focus hash. Duration ~1.5 s.
- Commit after every green test cycle. Existing suites must stay green: `uv run pytest`, `cd web && npx vitest run && npm run build`.

---

### Task 1: Domain derivation module (`ytk/mapdomains.py`)

**Files:**
- Create: `ytk/mapdomains.py`
- Test: `tests/test_mapdomains.py`

**Interfaces:**
- Consumes: nothing from other tasks. Point meta dicts have the same shape `load_points` emits in `scripts/build_map.py`: `{"cat": str, "title": str, "path": str, ...}`.
- Produces (Task 2 imports all of these from `ytk.mapdomains`):
  - `project_from_path(source_path: str) -> str | None`
  - `normalize_slug(slug: str, established: set[str]) -> str`
  - `domain_labels(metas: list[dict], content_theme: dict[int, int], theme_labels: list[str], min_size: int = 40) -> list[str]` — per-point domain label, small domains merged into `"other"`.
  - `index_domains(labels: list[str]) -> tuple[list[int], list[dict]]` — per-point domain index + domain meta `[{"label": str, "n": int}]` ordered by count descending.
  - `CONTENT_CATS: frozenset[str]`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_mapdomains.py
from ytk.mapdomains import (
    domain_labels,
    index_domains,
    normalize_slug,
    project_from_path,
)


def test_project_from_summary_filename():
    p = "second-brain/inbox/memories/claude-mem/summaries/summary-2026-02-19-epicmap-503.md"
    assert project_from_path(p) == "epicmap"


def test_project_from_summary_with_hyphenated_name():
    p = "second-brain/inbox/memories/claude-mem/summaries/summary-2026-03-01-Hacklytics-GoldenByte-77.md"
    assert project_from_path(p) == "hacklytics-goldenbyte"


def test_project_from_memories_folder():
    assert project_from_path("second-brain/inbox/memories/ytk/state.md") == "ytk"


def test_project_from_projects_folder():
    assert project_from_path("second-brain/projects/ytk/session-019-brief.md") == "ytk"


def test_project_from_claude_mem_non_summary_is_claude_mem():
    p = "second-brain/inbox/memories/claude-mem/other/note.md"
    assert project_from_path(p) == "claude-mem"


def test_project_from_unrelated_path_is_none():
    assert project_from_path("second-brain/sources/youtube/foo.md") is None
    assert project_from_path("") is None


def test_normalize_slug_strips_user_prefixes():
    assert normalize_slug("users-melocoton-developer-tts", set()) == "tts"
    assert normalize_slug("users-melocoton-config", set()) == "config"


def test_normalize_slug_collapses_worktrees_to_established_project():
    established = {"epicmap"}
    slug = "users-melocoton-developer-epicmap-claude-worktrees-silly-shaw-fb5548"
    assert normalize_slug(slug, established) == "epicmap"
    assert normalize_slug("epicmap-port-tanstack-start", established) == "epicmap"


def test_normalize_slug_no_collapse_without_established_match():
    assert normalize_slug("epicmap-port-tanstack-start", set()) == "epicmap-port-tanstack-start"


def test_domain_labels_end_to_end():
    metas = (
        [{"cat": "memory", "path": f"second-brain/inbox/memories/claude-mem/summaries/summary-2026-01-0{i % 9 + 1}-epicmap-{i}.md", "title": ""} for i in range(50)]
        + [{"cat": "memory", "path": f"second-brain/inbox/memories/claude-mem/summaries/summary-2026-01-0{i % 9 + 1}-tinyproj-{i}.md", "title": ""} for i in range(3)]
        + [{"cat": "youtube", "path": "", "title": "video"} for _ in range(45)]
        + [{"cat": "memo", "path": "second-brain/inbox/memos/m.md", "title": ""}]
    )
    # first 40 youtube points themed to theme 1, remaining 5 unthemed
    content_theme = {50 + 3 + i: (1 if i < 40 else -1) for i in range(45)}
    labels = domain_labels(metas, content_theme, ["go", "creative coding"], min_size=40)
    assert labels[:50] == ["epicmap"] * 50
    assert labels[50] == "other"          # tinyproj: 3 points, below min_size
    assert labels[53] == "creative coding"  # themed content
    assert labels[93] == "other"          # unthemed content
    assert labels[98] == "other"          # memo category


def test_index_domains_orders_by_count_desc():
    dom, meta = index_domains(["a", "b", "b", "b", "other", "a", "b"])
    assert [m["label"] for m in meta] == ["b", "a", "other"]
    assert [m["n"] for m in meta] == [4, 2, 1]
    assert dom == [1, 0, 0, 0, 2, 1, 0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_mapdomains.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ytk.mapdomains'`

- [ ] **Step 3: Write the implementation**

```python
# ytk/mapdomains.py
"""Deterministic domain assignment for the brain map's everything view.

A domain is the controlled top-level grouping axis: the owning project for
session/memory notes (parsed from paths — no LLM), the interest-profile theme
for consumed content, and `other` for the small residue. Pure functions;
scripts/build_map.py wires them to real vectors and the theme snapshot.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

CONTENT_CATS = frozenset(
    {"youtube", "instagram", "tiktok", "pinterest", "web", "screenshots"}
)
OTHER = "other"
_SUMMARY_RE = re.compile(r"^summary-\d{4}-\d{2}-\d{2}-(.+?)-\d+\.md$")
_USER_PREFIX_RE = re.compile(r"^users-melocoton(?:-developer)?-")


def project_from_path(source_path: str) -> str | None:
    """Owning project of a note, from its vault path.

    claude-mem session summaries encode it in the filename
    (summary-YYYY-MM-DD-{project}-{id}.md); memory atoms and project notes
    carry it as their folder slug.
    """
    if not source_path:
        return None
    parts = Path(source_path).parts
    for anchor in ("memories", "projects"):
        if anchor in parts:
            i = parts.index(anchor)
            if i + 1 >= len(parts) - 1:
                return None
            slug = parts[i + 1].lower()
            m = _SUMMARY_RE.match(parts[-1])
            if slug == "claude-mem" and m:
                return m.group(1).lower()
            return slug
    return None


def normalize_slug(slug: str, established: set[str]) -> str:
    """Canonical project name for a raw folder slug.

    Strips the absolute-path prefix seeded by the session scraper and folds
    worktree/branch variants (epicmap-claude-worktrees-...) into their base
    project when that project is already established (frequent enough on its
    own). Longest established prefix wins.
    """
    slug = _USER_PREFIX_RE.sub("", slug.lower()).lstrip(".")
    for base in sorted(established, key=len, reverse=True):
        if slug != base and slug.startswith(base + "-"):
            return base
    return slug


def domain_labels(
    metas: list[dict],
    content_theme: dict[int, int],
    theme_labels: list[str],
    min_size: int = 40,
) -> list[str]:
    """Per-point domain label.

    content_theme maps point index -> theme index (-1 for below the
    confidence floor) for content-category points. Two passes: raw project
    counts establish the collapse targets, then everything below min_size
    merges into `other`.
    """
    raw: list[str | None] = []
    for i, m in enumerate(metas):
        if m["cat"] in CONTENT_CATS:
            theme = content_theme.get(i, -1)
            raw.append(theme_labels[theme] if theme >= 0 else None)
        else:
            raw.append(project_from_path(m.get("path", "")))
    counts = Counter(p for p in raw if p)
    established = {p for p, n in counts.items() if n >= min_size}
    normalized = [normalize_slug(p, established) if p else None for p in raw]
    final_counts = Counter(p for p in normalized if p)
    return [
        p if p and final_counts[p] >= min_size else OTHER for p in normalized
    ]


def index_domains(labels: list[str]) -> tuple[list[int], list[dict]]:
    """Stable indexing: domains ordered by size descending, `other` never first
    unless it truly is the largest. Returns (per-point index, domain meta)."""
    counts = Counter(labels)
    ordered = [label for label, _ in counts.most_common()]
    index = {label: i for i, label in enumerate(ordered)}
    meta = [{"label": label, "n": counts[label]} for label in ordered]
    return [index[label] for label in labels], meta
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_mapdomains.py -v`
Expected: all PASS. Note `test_project_from_summary_with_hyphenated_name` expects lowercase (`hacklytics-goldenbyte`) — `project_from_path` lowercases.

- [ ] **Step 5: Run the full Python suite**

Run: `uv run pytest -q`
Expected: PASS (plus any pre-existing known failures, unchanged).

- [ ] **Step 6: Commit**

```bash
git add ytk/mapdomains.py tests/test_mapdomains.py
git commit -m "feat(map): deterministic domain derivation for the everything view"
```

---

### Task 2: Per-domain subtopics + schema v2 (`scripts/build_map.py`)

**Files:**
- Modify: `scripts/build_map.py` (replace `derive_clusters`, extend `main`)
- Test: `tests/test_build_map_assemble.py`

**Interfaces:**
- Consumes: everything in `ytk.mapdomains` (Task 1 signatures).
- Produces: `~/.ytk/map.json` v2 —
  - top level `{"v": 2, "generated", "content", "all", "points"}`
  - `all = {"params", "domains": [{"label", "n", "x", "y"}], "groups": [{"label", "domain": int, "n", "x", "y", "terms", "weight"}]}`
  - every point gains `"dom": int`; `"g"` becomes the global subtopic index or -1.
  - Pure helper `assemble_all_view(domains_meta, group_meta, doms, clabels, axy) -> dict` (unit-tested).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_build_map_assemble.py
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from build_map import assemble_all_view  # noqa: E402


def test_assemble_all_view_schema():
    domains_meta = [{"label": "epicmap", "n": 3}, {"label": "other", "n": 1}]
    group_meta = [{"label": "county gis", "domain": 0, "terms": "county, gis", "weight": 0.5}]
    doms = [0, 0, 0, 1]
    clabels = [0, 0, -1, -1]
    axy = np.array([[0.0, 0.0], [1.0, 1.0], [0.5, 0.5], [-1.0, -1.0]])
    out = assemble_all_view(domains_meta, group_meta, doms, clabels, axy)
    assert [d["label"] for d in out["domains"]] == ["epicmap", "other"]
    # domain centroid = mean of member positions
    assert out["domains"][0]["x"] == 0.5 and out["domains"][0]["y"] == 0.5
    assert out["groups"][0]["domain"] == 0
    assert out["groups"][0]["n"] == 2
    assert out["groups"][0]["x"] == 0.5  # centroid of its two members


def test_assemble_all_view_warns_over_caps(capsys):
    domains_meta = [{"label": f"d{i}", "n": 1} for i in range(33)]
    doms = list(range(33))
    axy = np.zeros((33, 2))
    assemble_all_view(domains_meta, [], doms, [-1] * 33, axy)
    assert "exceeds the 32-domain uniform cap" in capsys.readouterr().out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_build_map_assemble.py -v`
Expected: FAIL with `ImportError: cannot import name 'assemble_all_view'`

- [ ] **Step 3: Implement the pipeline changes**

In `scripts/build_map.py`:

3a. Add import: `from ytk.mapdomains import CONTENT_CATS as _CATS, domain_labels, index_domains` and delete the local `CONTENT_CATS` set (keep the name by aliasing: `CONTENT_CATS = _CATS`).

3b. Replace `derive_clusters` with a per-domain version plus the extracted assembler:

```python
def _ctfidf_names(cluster_docs: list[str]) -> list[str]:
    """c-TF-IDF top-5 terms per cluster document blob."""
    from sklearn.feature_extraction.text import CountVectorizer

    vec = CountVectorizer(stop_words="english", max_features=20_000, min_df=2)
    tf = vec.fit_transform(cluster_docs).toarray().astype(float)
    tf = tf / tf.sum(axis=1, keepdims=True).clip(1)
    idf = np.log(1 + len(cluster_docs) / (1 + (tf > 0).sum(axis=0)))
    scores = tf * idf
    terms = np.array(vec.get_feature_names_out())
    return [", ".join(terms[np.argsort(scores[k])[::-1][:5]]) for k in range(len(cluster_docs))]


def derive_subtopics(
    vecs: np.ndarray, docs: list[str], doms: list[int], n_domains: int
) -> tuple[list[int], list[str], list[int]]:
    """HDBSCAN within each large domain. Returns (per-point global subtopic
    index or -1, subtopic term-names, owning domain per subtopic)."""
    import umap
    from sklearn.cluster import HDBSCAN

    dom_arr = np.array(doms)
    clabels = np.full(len(doms), -1, dtype=int)
    term_names: list[str] = []
    owners: list[int] = []
    for d in range(n_domains):
        idx = np.flatnonzero(dom_arr == d)
        if len(idx) < 120:
            continue
        reduced = umap.UMAP(
            n_neighbors=30, n_components=15, min_dist=0.0, metric="cosine",
            random_state=42,
        ).fit_transform(vecs[idx])
        local = HDBSCAN(
            min_cluster_size=max(20, len(idx) // 50), min_samples=10
        ).fit_predict(reduced)
        n_local = local.max() + 1
        if n_local < 1:
            continue
        cluster_docs = [
            " ".join(docs[i] for i in idx[local == k])[:400_000]
            for k in range(n_local)
        ]
        base = len(term_names)
        term_names.extend(_ctfidf_names(cluster_docs))
        owners.extend([d] * n_local)
        for k in range(n_local):
            clabels[idx[local == k]] = base + k
        print(f"domain {d}: {n_local} subtopics over {len(idx)} points")
    return clabels.tolist(), term_names, owners


def assemble_all_view(
    domains_meta: list[dict],
    group_meta: list[dict],
    doms: list[int],
    clabels: list[int],
    axy: np.ndarray,
) -> dict:
    """Everything-view payload: domain and subtopic centroids over the 2D
    layout, with uniform-cap warnings (renderer arrays are fixed-size)."""
    if len(domains_meta) > 32:
        print(f"warning: {len(domains_meta)} domains exceeds the 32-domain uniform cap")
    if len(group_meta) > 96:
        print(f"warning: {len(group_meta)} subtopics exceeds the 96-subtopic uniform cap")
    return {
        "domains": group_positions(axy, doms, domains_meta),
        "groups": group_positions(axy, clabels, group_meta),
    }
```

3c. In `main()`, replace the all-view block (currently `clabels, term_names = derive_clusters(...)` through the `group_meta = ...` assignment) with:

```python
    # --- all view: domain hierarchy + per-domain subtopics -------------------
    print(f"all view: {len(meta)} points")
    content_theme = {g: cthemes[k] for k, g in enumerate(cidx)}
    labels_str = domain_labels(meta, content_theme, [t["label"] for t in snapshot["themes"]])
    doms, domains_meta = index_domains(labels_str)
    clabels, term_names, owners = derive_subtopics(vecs, docs, doms, len(domains_meta))
    exemplars = [
        [meta[i]["title"] for i in np.flatnonzero(np.array(clabels) == k)[:5]]
        for k in range(len(term_names))
    ]
    anchored = anchor_names(clabels, meta, len(term_names), load_previous_clusters())
    fresh = [k for k in range(len(term_names)) if k not in anchored]
    print(f"name anchoring: {len(anchored)} kept, {len(fresh)} new")
    if fresh and not args.no_llm:
        fresh_names = polish_names(
            [f"{domains_meta[owners[k]]['label']} | {term_names[k]}" for k in fresh],
            [exemplars[k] for k in fresh],
            taken=sorted(set(anchored.values())),
        )
        for k, nm in zip(fresh, fresh_names):
            anchored[k] = nm
    names = [anchored.get(k, term_names[k]) for k in range(len(term_names))]
    weights = [
        float((np.array(clabels) == k).sum()) / len(clabels) for k in range(len(names))
    ]
    group_meta = [
        {"label": nm, "domain": d, "weight": w, "terms": tn}
        for nm, d, w, tn in zip(names, owners, weights, term_names)
    ]
```

3d. Sweep scoring uses domains: change `fit_params(vecs, clabels, (10, 30, 50))` to `fit_params(vecs, doms, (10, 30, 50))` and `layout(vecs, clabels, ann, amd)` to `layout(vecs, doms, ann, amd)`.

3e. In the point-dict loop add `"dom": doms[i],` after `"g": clabels[i],`.

3f. In `OUT.write_text`, replace the `"all"` entry and add the version marker:

```python
            {
                "v": 2,
                "generated": snapshot["generated_at"],
                "content": {"params": cparams, "groups": group_positions(cxy, cthemes, theme_meta)},
                "all": {"params": aparams, **assemble_all_view(domains_meta, group_meta, doms, clabels, axy)},
                "points": points,
            }
```

3g. `load_previous_clusters` reads `prev["all"]["groups"]` and per-point `g` — both still exist in v1 and v2; no change needed.

- [ ] **Step 4: Run the new test**

Run: `uv run pytest tests/test_build_map_assemble.py -v`
Expected: PASS

- [ ] **Step 5: Dry-run the real build**

Run: `uv run python scripts/build_map.py --no-llm`
Expected: prints `domain d: N subtopics over M points` lines; epicmap should dominate one domain (~2000 points, ~8-12 subtopics); final line `wrote ... map.json: 4532 points, ...`. Spot-check: `uv run python -c "import json,pathlib;d=json.loads((pathlib.Path.home()/'.ytk'/'map.json').read_text());print(d['v'],[x['label'] for x in d['all']['domains']][:10],len(d['all']['groups']))"` — expect `2`, domain labels led by `epicmap`, subtopic count under 96.

- [ ] **Step 6: Commit**

```bash
git add scripts/build_map.py tests/test_build_map_assemble.py
git commit -m "feat(map): schema v2 with domain hierarchy and per-domain subtopics"
```

---

### Task 3: Frontend types + v2 gate (`api/map.ts`, `map.tsx`)

**Files:**
- Modify: `web/src/api/map.ts`
- Modify: `web/src/routes/map.tsx` (guard only in this task)
- Test: `web/src/api/map.test.ts`

**Interfaces:**
- Produces (Tasks 4-6 rely on these types):

```ts
export type MapDomain = { label: string; n: number; x: number; y: number }
export type MapGroup = { label: string; n: number; x?: number; y?: number; weight?: number; domain?: number }
export type MapLayout = { groups: MapGroup[]; params: Record<string, number> }
export type MapAllLayout = MapLayout & { domains: MapDomain[] }
export type MapData = { v?: number; points: MapPoint[]; all: MapAllLayout; content: MapLayout }
// MapPoint gains: dom: number
export const isMapV2 = (data: MapData): boolean => data.v === 2 && Array.isArray(data.all.domains)
```

- [ ] **Step 1: Write the failing test**

```ts
// web/src/api/map.test.ts
import { describe, expect, it } from 'vitest'
import { isMapV2 } from './map'
import type { MapData } from './map'

const base = { points: [], content: { groups: [], params: {} } }

describe('isMapV2', () => {
  it('accepts a v2 payload with domains', () => {
    const data = { ...base, v: 2, all: { groups: [], params: {}, domains: [] } } as unknown as MapData
    expect(isMapV2(data)).toBe(true)
  })
  it('rejects a legacy payload', () => {
    const data = { ...base, all: { groups: [], params: {} } } as unknown as MapData
    expect(isMapV2(data)).toBe(false)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run src/api/map.test.ts`
Expected: FAIL — `isMapV2` is not exported.

- [ ] **Step 3: Implement types + guard**

Apply the Interfaces block above to `web/src/api/map.ts` (extend, do not remove existing fields; add `dom: number` to `MapPoint`). Then in `web/src/routes/map.tsx`, after the `map.isError` early return, add:

```tsx
  if (map.data && !isMapV2(map.data)) return <div className="map-state">map data predates the domain hierarchy - run `uv run python scripts/build_map.py`</div>
```

with `import { isMapV2 } from '../api/map'` added to the imports.

- [ ] **Step 4: Run tests + build**

Run: `cd web && npx vitest run && npm run build`
Expected: PASS, build clean. (`map.tsx` still compiles because `MapAllLayout` extends `MapLayout`.)

- [ ] **Step 5: Commit**

```bash
git add web/src/api/map.ts web/src/api/map.test.ts web/src/routes/map.tsx
git commit -m "feat(map): v2 payload types and stale-data gate"
```

---

### Task 4: Pure hierarchy helpers (`web/src/lib/mapGroups.ts`)

**Files:**
- Create: `web/src/lib/mapGroups.ts`
- Test: `web/src/lib/mapGroups.test.ts`

**Interfaces:**
- Consumes: `MapData`, `MapDomain`, `MapGroup`, `MapPoint` from `../api/map` (Task 3).
- Produces (Tasks 5-6 import from `./mapGroups`):

```ts
export type MapFocus = { dom?: number; sub?: number }
export const ramp = (p: number): number
export const focusLevel = (f: MapFocus): 'overview' | 'domain' | 'sub'
// Target alpha factor per domain / per subtopic given focus + hover + hidden.
// Hover overrides focus (never dim both); hidden always wins with 0.
export function groupTargets(nDom: number, groups: MapGroup[], focus: MapFocus, hover: MapFocus | undefined, hiddenDoms: Set<number>): { dom: Float32Array; sub: Float32Array }
// Legend rows: domains sorted by n desc; when `focus.dom` is set, that row
// carries its subtopics sorted by n desc.
export function legendRows(domains: MapDomain[], groups: MapGroup[], focus: MapFocus): Array<{ dom: number; label: string; n: number; subs: Array<{ sub: number; label: string; n: number }> }>
export function parseFocusHash(hash: string, domains: MapDomain[], groups: MapGroup[]): MapFocus
export function focusHash(focus: MapFocus, domains: MapDomain[], groups: MapGroup[]): string
export const slug = (label: string): string
// Per-point growth phase: normalized distance from its subtopic centroid
// (domain centroid for subtopic noise) in the all-view 3D layout.
export function pointPhases(points: MapPoint[]): Float32Array
```

- [ ] **Step 1: Write the failing tests**

```ts
// web/src/lib/mapGroups.test.ts
import { describe, expect, it } from 'vitest'
import { focusHash, focusLevel, groupTargets, legendRows, parseFocusHash, pointPhases, ramp } from './mapGroups'
import type { MapDomain, MapGroup, MapPoint } from '../api/map'

const domains: MapDomain[] = [
  { label: 'epicmap', n: 2000, x: 0, y: 0 },
  { label: 'ytk', n: 300, x: 1, y: 1 },
  { label: 'other', n: 100, x: -1, y: -1 },
]
const groups: MapGroup[] = [
  { label: 'County GIS', n: 200, domain: 0, x: 0, y: 0 },
  { label: 'Modal Components', n: 150, domain: 0, x: 0.2, y: 0 },
  { label: 'Vault Search', n: 80, domain: 1, x: 1, y: 1 },
]

describe('ramp', () => {
  it('is a clamped cosine ease from 0 to 1', () => {
    expect(ramp(-1)).toBe(0)
    expect(ramp(0)).toBe(0)
    expect(ramp(0.5)).toBeCloseTo(0.5)
    expect(ramp(1)).toBe(1)
    expect(ramp(2)).toBe(1)
  })
})

describe('focusLevel', () => {
  it('classifies focus depth', () => {
    expect(focusLevel({})).toBe('overview')
    expect(focusLevel({ dom: 0 })).toBe('domain')
    expect(focusLevel({ dom: 0, sub: 1 })).toBe('sub')
  })
})

describe('groupTargets', () => {
  it('overview: everything full', () => {
    const t = groupTargets(3, groups, {}, undefined, new Set())
    expect([...t.dom]).toEqual([1, 1, 1])
    expect([...t.sub]).toEqual([1, 1, 1])
  })
  it('domain focus dims other domains', () => {
    const t = groupTargets(3, groups, { dom: 0 }, undefined, new Set())
    expect(t.dom[0]).toBe(1)
    expect(t.dom[1]).toBeCloseTo(0.08)
    expect(t.sub[2]).toBeCloseTo(0.08) // subtopic of another domain
  })
  it('sub focus dims sibling subtopics but keeps them above other domains', () => {
    const t = groupTargets(3, groups, { dom: 0, sub: 0 }, undefined, new Set())
    expect(t.sub[0]).toBe(1)
    expect(t.sub[1]).toBeCloseTo(0.25) // sibling within focused domain
    expect(t.dom[1]).toBeCloseTo(0.08)
  })
  it('hover overrides focus - never dim both', () => {
    const t = groupTargets(3, groups, { dom: 0 }, { dom: 1 }, new Set())
    expect(t.dom[1]).toBe(1) // hovered wins
    expect(t.dom[0]).toBeCloseTo(0.08) // focused recedes while hover is live
  })
  it('hidden domains are 0 regardless', () => {
    const t = groupTargets(3, groups, {}, { dom: 1 }, new Set([1]))
    expect(t.dom[1]).toBe(0)
  })
})

describe('legendRows', () => {
  it('sorts domains by size and nests subs only for the focused domain', () => {
    const rows = legendRows(domains, groups, { dom: 0 })
    expect(rows.map((r) => r.label)).toEqual(['epicmap', 'ytk', 'other'])
    expect(rows[0].subs.map((s) => s.label)).toEqual(['County GIS', 'Modal Components'])
    expect(rows[1].subs).toEqual([])
  })
})

describe('focus hash round-trip', () => {
  it('serializes with slugified labels and parses back', () => {
    expect(focusHash({ dom: 0, sub: 1 }, domains, groups)).toBe('#d:epicmap:modal-components')
    expect(parseFocusHash('#d:epicmap:modal-components', domains, groups)).toEqual({ dom: 0, sub: 1 })
    expect(parseFocusHash('#d:nope', domains, groups)).toEqual({})
    expect(focusHash({}, domains, groups)).toBe('')
  })
})

describe('pointPhases', () => {
  it('normalizes distance from the subtopic centroid per group', () => {
    const points = [
      { z3: [0, 0, 0], g: 0, dom: 0 },
      { z3: [3, 0, 0], g: 0, dom: 0 },
      { z3: [1, 0, 0], g: 0, dom: 0 },
      { z3: [0.5, 0, 0], g: -1, dom: 2 },
    ] as unknown as MapPoint[]
    // group-0 centroid x = 4/3: distances 4/3, 5/3, 1/3 -> phases 0.8, 1.0, 0.2
    const phases = pointPhases(points)
    expect(phases[1]).toBe(1) // farthest in its group
    expect(phases[0]).toBeCloseTo(0.8)
    expect(phases[2]).toBeCloseTo(0.2)
    expect(phases[3]).toBe(0) // sole noise point of its domain sits on its own centroid
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd web && npx vitest run src/lib/mapGroups.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

```ts
// web/src/lib/mapGroups.ts
import type { MapDomain, MapGroup, MapPoint } from '../api/map'

// Hierarchy state helpers for the everything view: domains are the controlled
// top level, subtopics the per-domain HDBSCAN children. All pure - the
// renderer consumes the Float32Array targets as uniform arrays.

export type MapFocus = { dom?: number; sub?: number }

export const DIM = 0.08
export const SIBLING = 0.25

export const ramp = (p: number): number => 0.5 - 0.5 * Math.cos(Math.max(0, Math.min(1, p)) * Math.PI)

export const focusLevel = (f: MapFocus): 'overview' | 'domain' | 'sub' => (f.dom === undefined ? 'overview' : f.sub === undefined ? 'domain' : 'sub')

export function groupTargets(nDom: number, groups: MapGroup[], focus: MapFocus, hover: MapFocus | undefined, hiddenDoms: Set<number>): { dom: Float32Array; sub: Float32Array } {
  const active = hover?.dom !== undefined ? hover : focus
  const dom = new Float32Array(nDom)
  for (let d = 0; d < nDom; d++) dom[d] = hiddenDoms.has(d) ? 0 : active.dom === undefined || active.dom === d ? 1 : DIM
  const sub = new Float32Array(groups.length)
  for (let s = 0; s < groups.length; s++) {
    const owner = groups[s].domain ?? -1
    if (hiddenDoms.has(owner)) { sub[s] = 0; continue }
    if (active.dom === undefined) { sub[s] = 1; continue }
    if (owner !== active.dom) { sub[s] = DIM; continue }
    sub[s] = active.sub === undefined || active.sub === s ? 1 : SIBLING
  }
  return { dom, sub }
}

export function legendRows(domains: MapDomain[], groups: MapGroup[], focus: MapFocus) {
  return domains
    .map((domain, dom) => ({ dom, label: domain.label, n: domain.n }))
    .filter((row) => row.n > 0)
    .sort((a, b) => b.n - a.n)
    .map((row) => ({
      ...row,
      subs: focus.dom === row.dom
        ? groups
            .map((group, sub) => ({ sub, label: group.label, n: group.n, domain: group.domain }))
            .filter((s) => s.domain === row.dom && s.n)
            .sort((a, b) => b.n - a.n)
            .map(({ sub, label, n }) => ({ sub, label, n }))
        : [],
    }))
}

export const slug = (label: string): string => label.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')

export function focusHash(focus: MapFocus, domains: MapDomain[], groups: MapGroup[]): string {
  if (focus.dom === undefined) return ''
  const dom = slug(domains[focus.dom]?.label ?? '')
  if (!dom) return ''
  if (focus.sub === undefined) return `#d:${dom}`
  const sub = slug(groups[focus.sub]?.label ?? '')
  return sub ? `#d:${dom}:${sub}` : `#d:${dom}`
}

export function parseFocusHash(hash: string, domains: MapDomain[], groups: MapGroup[]): MapFocus {
  const m = /^#d:([^:]+)(?::(.+))?$/.exec(hash)
  if (!m) return {}
  const dom = domains.findIndex((d) => slug(d.label) === m[1])
  if (dom < 0) return {}
  if (!m[2]) return { dom }
  const sub = groups.findIndex((g, i) => g.domain === dom && slug(groups[i].label) === m[2])
  return sub < 0 ? { dom } : { dom, sub }
}

export function pointPhases(points: MapPoint[]): Float32Array {
  // Centroids in the all-view 3D layout; group payload centroids are 2D, so
  // accumulate from the points themselves.
  const acc = new Map<string, { x: number; y: number; z: number; n: number }>()
  const key = (p: MapPoint) => (p.g >= 0 ? `s${p.g}` : `d${p.dom}`)
  for (const p of points) {
    const a = acc.get(key(p)) ?? { x: 0, y: 0, z: 0, n: 0 }
    a.x += p.z3[0]; a.y += p.z3[1]; a.z += p.z3[2]; a.n++
    acc.set(key(p), a)
  }
  const dist = points.map((p) => {
    const a = acc.get(key(p))!
    return Math.hypot(p.z3[0] - a.x / a.n, p.z3[1] - a.y / a.n, p.z3[2] - a.z / a.n)
  })
  const max = new Map<string, number>()
  points.forEach((p, i) => max.set(key(p), Math.max(max.get(key(p)) ?? 0, dist[i])))
  return new Float32Array(points.map((p, i) => { const m = max.get(key(p))!; return m > 0 ? dist[i] / m : 0 }))
}
```

- [ ] **Step 4: Run tests**

Run: `cd web && npx vitest run src/lib/mapGroups.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/mapGroups.ts web/src/lib/mapGroups.test.ts
git commit -m "feat(map): pure hierarchy helpers - targets, legend rows, hash, phases"
```

---

### Task 5: Renderer — uniform-driven focus, growth ramp, intro, garnish

**Files:**
- Modify: `web/src/lib/mapRenderer.ts` (shader + buffer layout + API)
- Modify: `web/src/lib/mapAggregation.ts` (`pointGroup` gains focus level)
- Test: `web/src/lib/mapAggregation.test.ts` (extend), build + headless screenshot for the visual half

**Interfaces:**
- Consumes: `groupTargets`, `ramp`, `pointPhases`, `focusLevel`, `MapFocus` from `./mapGroups` (Task 4); `MapData` v2 types (Task 3).
- Produces (Task 6 relies on this exact API):

```ts
export type MapRenderer = {
  setView(view: 'all' | 'content'): void
  setDimension(flat: boolean): void
  setFilters(signal: boolean, recent: boolean): void
  setFocus(focus: MapFocus): void            // replaces setGroupFocus
  setHover(hover?: MapFocus): void           // replaces setGroupHover
  setHiddenDomains(doms: Set<number>): void  // replaces setHiddenGroups
  setLegendOpen(open: boolean): void
  destroy(): void
}
export function mountMapRenderer(canvas, data, onHover?, labels?, onFocus?: (focus: MapFocus) => void, leaders?, opts?: { intro?: boolean }): MapRenderer
export function mapDomainColor(data: MapData, index: number): string
export function mapSubColor(data: MapData, index: number): string
```

Content view compatibility: in the `content` view themes act as single-level domains (`MapFocus.dom` = theme index, `sub` always undefined). `pointGroup(point, view)` keeps returning the render group (theme for content); a new `pointDomain(point, view)` returns `point.dom` for `all`, theme for `content`.

- [ ] **Step 1: Extend the aggregation tests (failing first)**

Append to `web/src/lib/mapAggregation.test.ts`:

```ts
import { pointDomain } from './mapAggregation'

describe('pointDomain', () => {
  it('returns dom for the all view and theme for the content view', () => {
    const point = { g: 5, dom: 2, th: 1, c3: [0, 0, 0] } as unknown as MapPoint
    expect(pointDomain(point, 'all')).toBe(2)
    expect(pointDomain(point, 'content')).toBe(1)
  })
  it('subCells key on domain for the all view', () => {
    const points = [
      { g: 0, dom: 1, z3: [0, 0, 0] },
      { g: 3, dom: 1, z3: [0.01, 0, 0] },
    ] as unknown as MapPoint[]
    const cells = subCells(points, 'all')
    expect(cells).toHaveLength(1)
    expect(cells[0].group).toBe(1)
  })
})
```

Run: `cd web && npx vitest run src/lib/mapAggregation.test.ts` — expected FAIL (`pointDomain` not exported; subCells currently keys on `g`).

- [ ] **Step 2: Update `mapAggregation.ts`**

```ts
// The domain a point belongs to: controlled hierarchy level for the
// everything view, theme for the content view.
export function pointDomain(point: MapPoint, view: 'all' | 'content'): number {
  if (view === 'content') return point.c3 !== undefined ? point.th ?? -1 : -1
  return point.dom
}
```

and change `subCells`/`groupStats` call sites to aggregate on `pointDomain` for the `all` view overview (pass the grouping function in: `subCells(points, view, cell = 0.13, groupOf: (p: MapPoint) => number = (p) => pointDomain(p, view))`). `pointGroup` (subtopic for `all`) stays exported for label bucketing and picking.

Run the aggregation tests again: PASS. Commit checkpoint:

```bash
git add web/src/lib/mapAggregation.ts web/src/lib/mapAggregation.test.ts
git commit -m "feat(map): aggregation keys on domains in the everything view"
```

- [ ] **Step 3: Rewrite the vertex shader and buffer layout**

New vertex shader (replaces the `vertex` constant; fragment gains fresnel + fog):

```ts
const vertex = `attribute vec3 p0; attribute vec3 p1; attribute vec2 q0; attribute vec2 q1;
attribute vec3 color0; attribute vec3 color1; attribute vec3 colorSub;
attribute float alpha0; attribute float alpha1; attribute float size;
attribute float grp; attribute float dm; attribute float phase;
uniform float morph; uniform float dim; uniform float zoom; uniform vec2 pan;
uniform float theta; uniform float phi; uniform float dpr;
uniform float aggDom[32]; uniform float aggSub[96];
uniform float focDomA[32]; uniform float focDomB[32];
uniform float focSubA[96]; uniform float focSubB[96];
uniform float focusT; uniform float level; uniform float subColorT;
uniform float introT; uniform float time;
varying vec3 c; varying float a; varying float depthV;
float rampf(float p){ return .5 - .5*cos(clamp(p,0.,1.)*3.14159265); }
void main(){
  vec3 p3=mix(p0,p1,morph); vec2 p2=mix(q0,q1,morph); vec3 q=mix(vec3(p2,0.),p3,dim);
  float ct=cos(theta),st=sin(theta),cp=cos(phi),sp=sin(phi);
  q=vec3(ct*q.x+st*q.z,sp*(st*q.x-ct*q.z)+cp*q.y,-cp*(st*q.x-ct*q.z)+sp*q.y);
  float depth=1.35-q.z*.24; depthV=q.z;
  gl_Position=vec4(q.xy*.88*zoom/depth+pan,q.z*.12,1.);
  int di=int(dm+.5); int si=int(max(grp,0.)+.5);
  float r=rampf(focusT*1.6-phase*.6);
  float fa=grp<0. ? mix(focDomA[di],focDomB[di],r) : mix(focSubA[si],focSubB[si],r);
  float agg=grp<0. ? 1. : (level<.5 ? aggDom[di] : aggSub[si]);
  float grow=rampf(introT*1.8-phase*.8);
  gl_PointSize=clamp(size*zoom/depth*dpr,1.8,26.*dpr)*grow;
  c=mix(mix(color0,colorSub,subColorT*step(.5,level)),color1,morph);
  float pulse=1.+.12*sin(time*2.2-phase*5.)*step(1.5,level+focusT);
  a=mix(alpha0,alpha1,morph)*fa*agg*grow*pulse; }`
```

Notes for the implementer: `dm` not `dom` (`dom` shadows nothing but keep names distinct from JS); `grp` is the global subtopic index or -1; `level` uniform is 0 at overview, 1 when a domain or subtopic is focused (drives aggregation keying and the sub-color blend); `subColorT` eases the recolor; `introT` starts at 1 when the intro is skipped. GLSL ES 1.00 requires constant array indexing only through `int()` of a uniform-derived value on some drivers — if `gl.getShaderInfoLog` complains, index via a helper `float pick(float arr[96], int i)` loop; verify on the target machine first before adding the workaround.

Fragment shader change (rim + fog), replacing the shaded line:

```ts
const fragment = `precision mediump float; varying vec3 c; varying float a; varying float depthV;
void main(){ vec2 p=gl_PointCoord*2.-1.; float d2=dot(p,p); float edge=smoothstep(1.,.82,sqrt(d2)); if(edge<=0.) discard;
 float z=sqrt(max(0.,1.-d2)); vec3 n=vec3(p.x,-p.y,z); vec3 light=normalize(vec3(-.45,.55,.72));
 float wrap=(dot(n,light)+.6)/1.6; float diff=.35+.65*clamp(wrap,0.,1.);
 float spec=pow(max(dot(reflect(-light,n),vec3(0.,0.,1.)),0.),12.)*.10;
 float rim=pow(1.-z,2.5)*.35;
 vec3 shaded=c*diff*(.75+.25*z)+vec3(spec)+c*rim;
 float fog=smoothstep(-1.2,1.,depthV)*.35+.65;
 float alpha=a*edge*fog; gl_FragColor=vec4(shaded*alpha,alpha); }`
```

Buffer layout becomes 25 floats, stride 100: `p0(3) p1(3) q0(2) q1(2) color0(3) color1(3) colorSub(3) alpha0 alpha1 size grp dm phase` with offsets `0 12 24 32 40 52 64 76 80 84 88 92 96`. `alpha0/alpha1` no longer bake `dimOf` — only base alpha (dust 0.4, grouped 1, content 0.95/0) times the signal/recent factor. Colors: `color0` = domain color (`rampColor(rank(dom))`), `colorSub` = subtopic color (domain hue shifted: `rampColor` of the subtopic's index-within-domain spread across ±0.08 around the domain's ramp position, clamped), `color1` = theme color (unchanged). `phase` comes from `pointPhases(data.points)` computed once at mount.

- [ ] **Step 4: Replace focus/hover state with uniform animation**

Inside `mountMapRenderer`, replace `focusedGroup/hoveredGroup/hiddenGroups` with:

```ts
  let focus: MapFocus = {}
  let hover: MapFocus | undefined
  let hiddenDoms = new Set<number>()
  const nDom = data.all.domains.length
  const nSub = data.all.groups.length
  let focA = { dom: new Float32Array(nDom).fill(1), sub: new Float32Array(nSub).fill(1) }
  let focB = { dom: new Float32Array(nDom).fill(1), sub: new Float32Array(nSub).fill(1) }
  let focusT = 1
  let subColorT = 0
  let introT = opts?.intro ? 0 : 1
  const retarget = () => {
    // Freeze the currently displayed value as the new A so mid-flight
    // retargets do not jump: A' = mix(A, B, ramp-evaluated-at-phase-0..1 is
    // per-point, so approximate with the group-level ramp(focusT).
    const t = ramp(Math.max(0, Math.min(1, focusT)))
    for (let i = 0; i < nDom; i++) focA.dom[i] = focA.dom[i] + (focB.dom[i] - focA.dom[i]) * t
    for (let i = 0; i < nSub; i++) focA.sub[i] = focA.sub[i] + (focB.sub[i] - focA.sub[i]) * t
    const view2 = view === 'content'
    focB = view2
      ? contentTargets()   // themes as single-level domains, see below
      : groupTargets(nDom, data.all.groups, focus, hover, hiddenDoms)
    focusT = 0
  }
```

`contentTargets()` treats themes as single-level domains:

```ts
  const contentTargets = () => {
    const n = data.content.groups.length
    const dom = new Float32Array(nDom).fill(1)
    for (let d = 0; d < n && d < nDom; d++) dom[d] = focus.dom === undefined || (hover?.dom ?? focus.dom) === d ? 1 : DIM
    if (hover?.dom !== undefined) for (let d = 0; d < n && d < nDom; d++) dom[d] = hover.dom === d ? 1 : DIM
    return { dom, sub: new Float32Array(nSub).fill(1) }
  }
```

(In the content view the shader's `dm` attribute is unused — theme alpha rides `alpha1`/`color1` exactly as today, so `contentTargets` only needs to neutralize the arrays; the simple version above keeps hover/focus parity for the theme legend.) In `render(now)` advance the clocks (`focusT = Math.min(1, focusT + dt / 0.9)`, `introT = Math.min(1, introT + dt / 1.5)`, `subColorT` eases toward `focus.dom !== undefined ? 1 : 0`), and upload uniforms every frame (`gl.uniform1fv(focDomAU, focA.dom)` etc. — arrays this small are fine per-frame). Aggregation `galpha` splits into `aggDom`/`aggSub` computed exactly as today but over domain stats at overview and subtopic stats when `level >= 1`. `geometryDirty` is now set ONLY by `setView` and `setFilters`.

Public API wiring:

```ts
  setFocus: (next) => { focus = next; retarget(); labelsDirty = true },
  setHover: (next) => { hover = next; retarget() },
  setHiddenDomains: (doms) => { hiddenDoms = new Set(doms); retarget(); labelsDirty = true },
```

At mount, check `gl.getParameter(gl.MAX_VERTEX_UNIFORM_VECTORS) >= 512` and `console.warn` if not.

- [ ] **Step 5: Hierarchy-aware labels, picking, and clicks**

- `placeLabels` buckets by `pointDomain` at overview (label text from `data.all.domains`), by `pointGroup` filtered to `focus.dom` when a domain is focused (top 10 by n), single label when `focus.sub` set. Content view: themes, as today.
- Label nodes become clickable: in the label build loop add `node.style.pointerEvents = 'auto'; node.style.cursor = 'pointer'; node.onclick = () => { onFocus?.(labelFocus) }` where `labelFocus` is `{ dom }` for domain labels and `{ dom, sub }` for subtopic labels. (The route owns focus state; the renderer only reports.)
- `click` handler drill-down: overview click on a point -> `onFocus?.({ dom: hoveredPoint.dom })`; domain focused -> `onFocus?.({ dom, sub: hoveredPoint.g >= 0 ? hoveredPoint.g : undefined })` (noise points keep domain focus); sub focused or empty click -> pop one level: `onFocus?.(focus.sub !== undefined ? { dom: focus.dom } : {})`. Fly-to (`flyItem`) only on subtopic-level point clicks, as today.
- `hover` picking skips points whose current target alpha is below 0.2 (`focB` lookup) instead of the old focused/hidden checks.
- Export colors: `mapDomainColor(data, i)` = ramp by domain size rank; `mapSubColor(data, i)` = the within-domain hue shift used in the buffer (single source of truth: compute both in one exported helper used by buffer fill and legend).

- [ ] **Step 6: Intro gate**

Module level in `mapRenderer.ts`:

```ts
let introPlayed = false
```

In `mountMapRenderer`, the route passes `opts.intro`; renderer additionally guards: `const intro = (opts?.intro ?? false) && !introPlayed; if (intro) introPlayed = true`. While `introT < 1`, set `canvas.dataset.intro = '1'`, delete it after — the smoke test reads this.

- [ ] **Step 7: Verify — build, unit tests, headless screenshots**

Run: `cd web && npx vitest run && npm run build`
Expected: PASS + clean build.

Then rebuild the served bundle and visually verify (server already running on :6969 picks up `~/.ytk/map.json`; the dev server or a reinstall serves the new JS — use `npm run dev` on a spare port or `uv tool install --reinstall .`):

```bash
uv run --with playwright python - <<'EOF'
from playwright.sync_api import sync_playwright
EXE='/Users/melocoton/Library/Caches/ms-playwright/chromium_headless_shell-1217/chrome-headless-shell-mac-arm64/chrome-headless-shell'
with sync_playwright() as p:
    b=p.chromium.launch(headless=True, executable_path=EXE); pg=b.new_page(viewport={'width':1600,'height':1000})
    pg.goto('http://localhost:6969/map'); pg.wait_for_load_state('networkidle'); pg.wait_for_timeout(500)
    assert pg.eval_on_selector('canvas','e=>e.dataset.intro')== '1', 'intro should be running on hard load'
    pg.wait_for_timeout(2500)
    pg.screenshot(path='/tmp/map_overview.png'); b.close()
EOF
```

Expected: assertion passes; screenshot shows domain labels (epicmap, ytk, ...) not 33 subtopic labels. Inspect the screenshot.

- [ ] **Step 8: Commit**

```bash
git add web/src/lib/mapRenderer.ts web/src/lib/mapAggregation.ts
git commit -m "feat(map): uniform-driven hierarchical focus with growth transitions"
```

---

### Task 6: Route + legend UI (`map.tsx`, `styles.css`)

**Files:**
- Modify: `web/src/routes/map.tsx`
- Modify: `web/src/styles.css`

**Interfaces:**
- Consumes: renderer API from Task 5, `legendRows`/`parseFocusHash`/`focusHash`/`MapFocus` from Task 4, `mapDomainColor`/`mapSubColor` from Task 5.
- Produces: user-facing behavior only.

- [ ] **Step 1: Rewire route state**

Replace `focus/hoverGroupIndex/hidden` state with:

```tsx
  const [focus, setFocusState] = useState<MapFocus>({})
  const [hover, setHover] = useState<MapFocus>()
  const [hiddenDoms, setHiddenDoms] = useState<Set<number>>(new Set())
  const setFocus = (next: MapFocus) => {
    setFocusState(next)
    const h = focusHash(next, map.data!.all.domains, map.data!.all.groups)
    history.replaceState(null, '', h || location.pathname + (flat ? '#2d' : ''))
  }
```

Mount effect: `parseFocusHash(location.hash, ...)` seeds initial focus; pass `opts: { intro: !location.hash.startsWith('#d:') }` to `mountMapRenderer`; renderer effects call `setFocus`, `setHover`, `setHiddenDomains`. The `#2d`/`#content` hash flags keep working — `parseFocusHash` returns `{}` for them.

- [ ] **Step 2: Two-level legend**

Replace the legend group mapping with:

```tsx
  const rows = legendRows(view === 'content' ? contentAsDomains(map.data!) : map.data!.all.domains, view === 'content' ? [] : map.data!.all.groups, focus)
```

where `contentAsDomains` maps `content.groups` to `MapDomain[]`. Render:

```tsx
  {rows.map((row) => (
    <div key={row.dom}>
      <button className={hiddenDoms.has(row.dom) || (focus.dom !== undefined && focus.dom !== row.dom && hover?.dom !== row.dom) ? 'off' : ''}
        onMouseEnter={() => setHover({ dom: row.dom })} onMouseLeave={() => setHover(undefined)}
        onClick={(e) => { if (e.altKey) setHiddenDoms((cur) => { const next = new Set(cur); next.has(row.dom) ? next.delete(row.dom) : next.add(row.dom); return next }); else setFocus(focus.dom === row.dom && focus.sub === undefined ? {} : { dom: row.dom }) }}>
        <i style={{ background: mapDomainColor(map.data!, row.dom) }} />{row.label}<span>{row.n}</span>
      </button>
      {row.subs.map((s) => (
        <button key={s.sub} className={`sub${focus.sub !== undefined && focus.sub !== s.sub ? ' off' : ''}`}
          onMouseEnter={() => setHover({ dom: row.dom, sub: s.sub })} onMouseLeave={() => setHover(undefined)}
          onClick={() => setFocus(focus.sub === s.sub ? { dom: row.dom } : { dom: row.dom, sub: s.sub })}>
          <i style={{ background: mapSubColor(map.data!, s.sub) }} />{s.label}<span>{s.n}</span>
        </button>
      ))}
    </div>
  ))}
```

Tooltip line gains the hierarchy: `{hover.point.c} · {domainLabel} · {subLabel}` (subLabel only when `g >= 0`). Collapsed legend dots show domains.

- [ ] **Step 3: CSS**

Append to `web/src/styles.css`:

```css
.map-legend button.sub { padding-left: 1.4rem; font-size: .85em; }
.map-label { pointer-events: auto; cursor: pointer; }
.map-label:hover { color: #f0eee7; }
```

(`.map-labels` keeps `pointer-events: none`; individual labels opt back in.)

- [ ] **Step 4: Verify + commit**

Run: `cd web && npx vitest run && npm run build`
Expected: PASS. Manual: `npm run dev`, click through overview -> domain -> subtopic -> empty-click pops.

```bash
git add web/src/routes/map.tsx web/src/styles.css
git commit -m "feat(map): hierarchical legend, clickable labels, hash-persisted focus"
```

---

### Task 7: Playwright smoke (`scripts/smoke_map.py`)

**Files:**
- Create: `scripts/smoke_map.py`

**Interfaces:**
- Consumes: the running hub on `http://localhost:6969` with a v2 `map.json` and the reinstalled bundle. `canvas.dataset.intro` flag from Task 5.

- [ ] **Step 1: Write the smoke script**

```python
"""Headless smoke for the /map hierarchy. Run against a live hub:
uv run --with playwright python scripts/smoke_map.py [--base http://localhost:6969]
Asserts, in both 3D and 2D: legend sorted by size, clicking a domain label
focuses that domain (not a neighbor), drill-down and pop, intro gating."""
import argparse
import sys

from playwright.sync_api import sync_playwright

EXE = "/Users/melocoton/Library/Caches/ms-playwright/chromium_headless_shell-1217/chrome-headless-shell-mac-arm64/chrome-headless-shell"


def legend(page):
    return page.eval_on_selector_all(
        ".map-legend button:not(.map-legend-toggle):not(.sub)",
        "els => els.map(e => ({label: e.textContent.replace(/\\d+$/, ''), n: +e.querySelector('span').textContent, off: e.classList.contains('off')}))",
    )


def run(page, base, suffix, name):
    page.goto(f"{base}/map{suffix}")
    page.wait_for_load_state("networkidle")
    page.wait_for_selector(".map-label")
    page.wait_for_timeout(2500)
    rows = legend(page)
    ns = [r["n"] for r in rows]
    assert ns == sorted(ns, reverse=True), f"[{name}] legend not size-sorted: {ns}"
    lab = page.eval_on_selector(".map-label", "e => ({t: e.textContent, x: parseFloat(e.style.left), y: parseFloat(e.style.top)})")
    page.mouse.click(lab["x"], lab["y"])
    page.wait_for_timeout(1400)
    on = [r["label"] for r in legend(page) if not r["off"]]
    assert on == [lab["t"]], f"[{name}] clicked label '{lab['t']}' but selected {on}"
    subs = page.locator(".map-legend button.sub")
    drilled = subs.count() > 0
    if drilled:
        subs.first.click()
        page.wait_for_timeout(1200)
        page.mouse.click(200, 850)  # empty corner: pop subtopic -> domain
        page.wait_for_timeout(1200)
        on = [r["label"] for r in legend(page) if not r["off"]]
        assert on == [lab["t"]], f"[{name}] empty click should pop to domain focus, got {on}"
    page.mouse.click(200, 850)  # pop domain -> overview
    page.wait_for_timeout(1200)
    assert all(not r["off"] for r in legend(page)), f"[{name}] final empty click should clear focus"
    print(f"[{name}] ok: sorted legend, label click, drill-down={drilled}, pop")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:6969")
    args = ap.parse_args()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=EXE)
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.goto(f"{args.base}/map")
        page.wait_for_selector("canvas")
        assert page.eval_on_selector("canvas", "e => e.dataset.intro") == "1", "intro should run on hard load"
        page.click("text=inbox"); page.wait_for_timeout(300); page.click("text=map")
        page.wait_for_selector("canvas")
        assert page.eval_on_selector("canvas", "e => e.dataset.intro") is None, "intro must not replay on SPA navigation"
        run(page, args.base, "", "3d")
        run(page, args.base, "#2d", "2d")
        browser.close()
    print("smoke passed")


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it against the live hub**

Precondition: Task 8 step 1-2 done (fresh map.json + reinstall) or a dev server with the new bundle. Run:
`uv run --with playwright python scripts/smoke_map.py`
Expected: `[3d] ok ... [2d] ok ... smoke passed`. Fix regressions before committing.

- [ ] **Step 3: Commit**

```bash
git add scripts/smoke_map.py
git commit -m "test(map): headless smoke for hierarchy, sorted legend, and intro gating"
```

---

### Task 8: Rebuild, ship, verify live

**Files:** none (ops)

- [ ] **Step 1: Full rebuild with LLM naming**

Run: `uv run python scripts/build_map.py`
Expected: anchoring reuses v1 names for matching epicmap subtopics; Haiku names only fresh clusters. Check domains: epicmap, interview/content themes, niloc, usf, ytk, other, ...

- [ ] **Step 2: Ship the bundle**

Run: `cd web && npm run build && cd .. && uv tool install --reinstall .`
Then hard-refresh check: `curl -s localhost:6969/api/map | head -c 200` shows `"v": 2`.

- [ ] **Step 3: Full verification**

Run: `uv run pytest -q` and `cd web && npx vitest run` and `uv run --with playwright python scripts/smoke_map.py`
Expected: all green.

- [ ] **Step 4: Screenshots for review**

Capture `/map` overview, domain-focused, and subtopic-focused states (3D) plus a 2D overview via the smoke browser; send to the user for the look-and-feel gate (growth feel, fresnel/fog subtlety) before closing out.

- [ ] **Step 5: Commit any final tweaks + session rituals**

Working tree clean, push, then vault session brief + `vault_remember` per CLAUDE.md.
