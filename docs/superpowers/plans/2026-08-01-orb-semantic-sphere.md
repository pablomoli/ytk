# /orb Semantic Sphere Gallery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `/orb` route rendering the 505 content notes as an inside-a-sphere
tile gallery, positioned semantically from the embedding layout, with
drag+inertia navigation and a zoom-into-tile handoff to the existing
NoteViewer.

**Architecture:** Sphere layouts (radial / haversine / lattice) are computed
in a new pure module `ytk/spheremap.py`, attached to `~/.ytk/map.json` by
`scripts/build_map.py --attach-sphere` (precedent: `attach_terrain`), served
thin by `GET /api/orb`, and rendered by a self-owned Three.js scene under
`web/src/lib/orb/` (one InstancedBufferGeometry draw, one 4096 canvas atlas).
Spec: `docs/superpowers/specs/2026-08-01-orb-semantic-sphere-design.md`.

**Tech Stack:** Python (numpy, umap-learn, scikit-learn, FastAPI), TypeScript
(three 0.185, gsap via `web/src/lib/motion.ts`, TanStack router/query, vitest
browser mode in real Chromium).

## Global Constraints

- Execute in a worktree (wt skill). Commit per task. NEVER merge — the user
  merges on explicit go.
- No emojis anywhere. Code comments 1-2 lines, constraints only; narrative
  goes in commit messages.
- No new rules in `web/src/styles.css` or any route CSS (#136 ratchet).
  Style with Tailwind utilities only. Page controls render in-page, never in
  the nav bar (nav is links only).
- gsap is imported ONLY from `web/src/lib/motion.ts` (`import { gsap, DUR,
  reducedMotion } from "../motion"`). Every JS animation checks
  `reducedMotion()` and jumps to end state when true.
- Frontend tests: `cd web && vp exec vitest run <file>` (real Chromium).
  Python tests: `uv run pytest <file> -v` — narrowest selection, never the
  full suite unasked (16 GB machine, parallel sessions).
- Python quality gate for touched files: `uv run ruff check <files>` and
  `uv run ruff format <files>`. Frontend: `cd web && vp lint` and
  `pnpm exec tsc -b`.
- Do not restart the user's hub (launchd `com.ytk.hub`) without checking
  `curl -s http://127.0.0.1:6969/api/ingest/status` shows no active job.
- `~/.ytk/map.json` is a local data artifact — never committed.
- The retrieval eval gate is NOT touched by this work (no `ytk/store.py` /
  `ytk/retrieval_gate.py` / `eval/retrieval/` changes allowed).
- **Visual checkpoints are mandatory, not decorative.** Every task that
  computes geometry or picks a motion/physics constant renders a matplotlib
  artifact to the scratchpad, OPENS it (Read the PNG), and judges it before
  committing — a checkpoint that is generated but not looked at is not a
  checkpoint. Rules are simulated in Python before they are coded in
  TypeScript or GLSL: corrections are free in a plot and expensive in a
  shader. Checkpoint PNGs/mp4s are working artifacts: scratchpad only,
  never committed, sent to the user with SendUserFile at review points.
  Scratchpad root for all of them:
  `/private/tmp/claude-501/-Users-melocoton-Developer-ytk/a880b851-b1c2-4d8c-a41c-6109fa752743/scratchpad/`
  (referred to as `$SCRATCH` below).
- **Checkpoints wear the incumbent house style — `docs/assets/README.md` is
  the contract.** Import from `scripts/plot_assets.py` (`figure()`,
  `panel_title`, `style_axes`, `frame_panels`, the palette constants);
  never restate hex values or fonts. Save with `frame_panels(fig)` then
  `fig.savefig(out, dpi=200, facecolor=BG)`. Manim scenes take their colors
  from `scripts.plot_assets` too (reference consumer:
  `scripts/manim/semantic_domains.py`), use `Text` never `MathTex` (no
  dvisvgm on this machine), and verify motion by pixel-diff per the README.

## Data contracts (read before any task)

`~/.ytk/map.json` (v2) relevant shape:

```
{ "v": 2,
  "points": [ {"x","y","z3","t","c","u","d","g","dom","p","r","img",
               // content members additionally:
               "cx","cy","c3":[x,y,z],"th":int, // + this plan adds "thumb"
              }, ... ],                          // 4880 points, 505 content
  "content": { "params": {...}, "groups": [{label,...} x17], "terrain": ...,
               // this plan adds:
               "sphere": { "radial": [[x,y,z] x N], "haversine": [[x,y,z] x N] | null,
                           "lattice": [[x,y,z] x N],
                           "scores": { "<layout>": {"trustworthiness": float,
                                        "mean_nn_deg": float, "overlap": int,
                                        "overlap_frac": float} },
                           "chosen": "radial"|"haversine"|"lattice" } },
  "all": {...} }
```

Ordering contract used everywhere: sphere arrays index the content points in
`[p for p in points if "c3" in p]` order. `/api/orb` serves them in that same
order; the client never re-sorts.

`GET /api/orb` response:

```
{ "points": [{"p": vault-rel path, "t": title, "c": category, "u": url|null,
              "d": date|null, "th": theme index, "thumb": rel path|null}],
  "themes": ["label" x17],          // from content.groups[i].label
  "sphere": {as above} }
```

---

### Task 1: Haversine spike (gate for the layout work)

Verify `output_metric="haversine"` converges on the real 505 content vectors
before anything is built on it. Discovery task: no TDD, no commit of code;
the deliverable is numbers reported back.

**Files:**
- Create: `/private/tmp/claude-501/-Users-melocoton-Developer-ytk/a880b851-b1c2-4d8c-a41c-6109fa752743/scratchpad/haversine_spike.py` (scratchpad, NOT committed)

**Interfaces:**
- Produces: a report (stdout numbers) deciding whether Task 2 implements
  `haversine()` for real or as a recorded failure returning `None`.

- [ ] **Step 1: Check the Chroma server is up**

Run: `just chroma-status`
Expected: running. If not, STOP and report — do not start servers blind.

- [ ] **Step 2: Write the spike script**

```python
"""Spike: does UMAP haversine converge on the real content vectors?"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path("scripts").resolve()))
import numpy as np
from build_map import CONTENT_CATS, load_points

vecs, meta, _docs = load_points()
cidx = [i for i, m in enumerate(meta) if m["cat"] in CONTENT_CATS]
cvecs = vecs[cidx]
print(f"content vectors: {cvecs.shape}")

import umap
from sklearn.manifold import trustworthiness

emb = umap.UMAP(
    n_neighbors=30, min_dist=0.05, n_components=2,
    metric="cosine", output_metric="haversine", random_state=42,
).fit_transform(cvecs)
print(f"embedded: {emb.shape}, lat range {emb[:,0].min():.2f}..{emb[:,0].max():.2f}, "
      f"lon range {emb[:,1].min():.2f}..{emb[:,1].max():.2f}")
# documented UMAP sphere mapping: emb[:,0]=theta (polar), emb[:,1]=phi
xyz = np.stack([
    np.sin(emb[:, 0]) * np.cos(emb[:, 1]),
    np.sin(emb[:, 0]) * np.sin(emb[:, 1]),
    np.cos(emb[:, 0]),
], axis=1)
print("unit check:", np.abs(np.linalg.norm(xyz, axis=1) - 1).max())
print("NaNs:", int(np.isnan(xyz).sum()))
t = trustworthiness(cvecs, xyz, n_neighbors=15, metric="cosine")
print(f"trustworthiness: {t:.4f}")
# angular nearest-neighbour stats (overlap threshold ~ tile radius)
dots = np.clip(xyz @ xyz.T, -1, 1)
np.fill_diagonal(dots, -1)
nn_ang = np.degrees(np.arccos(dots.max(axis=1)))
theta_deg = np.degrees(0.5 * np.sqrt(4 * np.pi / len(xyz)))
print(f"mean NN angle: {nn_ang.mean():.2f} deg, tile radius {theta_deg:.2f} deg, "
      f"overlapping tiles: {int((nn_ang < theta_deg).sum())} "
      f"({100 * (nn_ang < theta_deg).mean():.1f}%)")
```

- [ ] **Step 3: Run it**

Run: `uv run python /private/tmp/claude-501/-Users-melocoton-Developer-ytk/a880b851-b1c2-4d8c-a41c-6109fa752743/scratchpad/haversine_spike.py`
Expected: completes in under ~2 min. Record every printed number.

- [ ] **Step 4: Matplotlib checkpoint — look at the sphere, not just the score**

Append to the spike script (or run as a second script) and re-run:

```python
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from build_map import assign_themes  # theme colors need the snapshot
import json
snapshot = json.loads((Path.home() / ".ytk" / "interest" / "latest.json").read_text())
themes = assign_themes(cvecs, snapshot)

lon = np.arctan2(xyz[:, 1], xyz[:, 0])
lat = np.arcsin(np.clip(xyz[:, 2], -1, 1))
fig, ax = plt.subplots(subplot_kw={"projection": "mollweide"}, figsize=(10, 5))
ax.scatter(lon, lat, c=themes, cmap="tab20", s=10)
bad = nn_ang < theta_deg
ax.scatter(lon[bad], lat[bad], facecolors="none", edgecolors="red", s=60, linewidths=0.8)
ax.set_title(f"haversine, trust={t:.3f}, overlap={int(bad.sum())} (red rings)")
ax.grid(alpha=0.2)
fig.savefig("/private/tmp/claude-501/-Users-melocoton-Developer-ytk/a880b851-b1c2-4d8c-a41c-6109fa752743/scratchpad/spike-haversine-mollweide.png", dpi=110)
print("wrote spike-haversine-mollweide.png")
```

Then READ the PNG (Read tool) and answer in the report: do theme colors
form coherent regions, or salt-and-pepper? Is the sphere covered, or is
half of it bald? A trustworthiness number cannot answer either question.

- [ ] **Step 5: Verdict**

PASS if: no exception, no NaNs, unit check < 1e-6, trustworthiness > 0, AND
the Mollweide plot shows usable coverage (theme regions visible, no
dominant bald hemisphere). Report all numbers plus the plot verdict, and
send the PNG to the user with SendUserFile. If it raises or NaNs: report
the traceback verbatim — Task 2 then implements `haversine()` to catch the
failure and return `None`, and the plan proceeds with radial + lattice
only.

---

### Task 2: `ytk/spheremap.py` — pure layouts and scoring

**Files:**
- Create: `ytk/spheremap.py`
- Test: `tests/test_spheremap.py`

**Interfaces:**
- Consumes: nothing from other tasks (pure numpy/umap/sklearn).
- Produces (Task 3 calls these exact signatures):
  - `radial(c3: np.ndarray) -> np.ndarray` — (n,3) → unit (n,3)
  - `fibonacci(n: int) -> np.ndarray` — unit (n,3) in spiral order
  - `lattice(themes: list[int], radial_dirs: np.ndarray) -> np.ndarray`
  - `haversine(vecs: np.ndarray, n_neighbors: int, min_dist: float) -> np.ndarray | None`
  - `score(vecs: np.ndarray, pos: np.ndarray) -> dict` — keys
    `trustworthiness, mean_nn_deg, overlap, overlap_frac`
  - `choose(scores: dict[str, dict], max_overlap_frac: float = 0.05) -> str`
  - `sphere_block(vecs, c3, themes) -> dict` — the full
    `content.sphere` JSON block from the data contract

- [ ] **Step 1: Write the failing tests**

```python
"""Sphere layouts are unit-norm, deterministic, and scored on two axes."""
import numpy as np
import pytest

from ytk.spheremap import choose, fibonacci, lattice, radial, score, sphere_block


def _unit(a: np.ndarray) -> None:
    assert not np.isnan(a).any()
    assert np.abs(np.linalg.norm(a, axis=1) - 1).max() < 1e-9


def test_radial_normalizes_and_centers():
    rng = np.random.default_rng(0)
    c3 = rng.normal(size=(50, 3)) + 5.0  # offset centroid must be removed
    pos = radial(c3)
    _unit(pos)
    # a point at the centroid direction extreme keeps its direction
    assert pos.shape == (50, 3)


def test_radial_zero_vector_survives():
    c3 = np.zeros((3, 3))
    c3[1] = [1.0, 0, 0]
    c3[2] = [-1.0, 0, 0]
    pos = radial(c3)  # centroid-coincident row must not become NaN
    _unit(pos)


def test_fibonacci_even_coverage():
    pos = fibonacci(500)
    _unit(pos)
    # even coverage: every octant populated, z spread across [-1, 1]
    assert pos[:, 2].min() < -0.95 and pos[:, 2].max() > 0.95
    octants = set(map(tuple, (pos > 0).astype(int)))
    assert len(octants) == 8


def test_lattice_themes_contiguous_and_complete():
    rng = np.random.default_rng(1)
    dirs = radial(rng.normal(size=(40, 3)))
    themes = [0] * 10 + [1] * 20 + [2] * 10
    pos = lattice(themes, dirs)
    _unit(pos)
    assert pos.shape == (40, 3)
    # every input index appears exactly once (it is a permutation of slots)
    assert len({tuple(np.round(p, 6)) for p in pos}) == 40


def test_score_shape_and_perfect_layout():
    # identical spaces: trustworthiness is 1, no overlaps on a lattice
    pos = fibonacci(100)
    s = score(pos, pos)
    assert set(s) == {"trustworthiness", "mean_nn_deg", "overlap", "overlap_frac"}
    assert s["trustworthiness"] == pytest.approx(1.0)
    assert s["overlap"] == 0


def test_score_counts_overlaps():
    pos = fibonacci(100)
    pos[1] = pos[0]  # two coincident tiles
    s = score(pos, pos)
    assert s["overlap"] >= 2


def test_choose_prefers_fidelity_within_overlap_bound():
    scores = {
        "radial": {"trustworthiness": 0.95, "overlap_frac": 0.30},
        "lattice": {"trustworthiness": 0.80, "overlap_frac": 0.0},
        "haversine": {"trustworthiness": 0.90, "overlap_frac": 0.04},
    }
    assert choose(scores) == "haversine"  # best trust among overlap <= 5%


def test_choose_ignores_missing_layouts():
    scores = {"radial": {"trustworthiness": 0.9, "overlap_frac": 0.5},
              "lattice": {"trustworthiness": 0.7, "overlap_frac": 0.0}}
    assert choose(scores) == "lattice"  # radial over bound, haversine absent


def test_sphere_block_schema_without_umap():
    rng = np.random.default_rng(2)
    vecs = rng.normal(size=(30, 8))
    c3 = rng.normal(size=(30, 3))
    themes = [i % 3 for i in range(30)]
    block = sphere_block(vecs, c3, themes, run_haversine=False)
    assert block["haversine"] is None
    assert len(block["radial"]) == 30 and len(block["lattice"]) == 30
    assert block["chosen"] in ("radial", "lattice")
    assert "haversine" not in block["scores"]
    # JSON-safe: plain lists of floats, rounded
    assert isinstance(block["radial"][0][0], float)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_spheremap.py -v`
Expected: FAIL — `ModuleNotFoundError: ytk.spheremap` (or ImportError).

- [ ] **Step 3: Implement `ytk/spheremap.py`**

```python
"""Sphere layouts for the /orb gallery: three candidate projections of the
content embedding onto the unit sphere, scored on fidelity (trustworthiness,
same metric as map.json's trustworthiness_3d) and legibility (angular
overlap). All layouts index the content points in map.json order."""

from __future__ import annotations

import numpy as np

GOLDEN = np.pi * (3.0 - np.sqrt(5.0))


def radial(c3: np.ndarray) -> np.ndarray:
    """Unit directions from the layout centroid; radius discarded."""
    v = np.asarray(c3, dtype=float) - np.asarray(c3, dtype=float).mean(axis=0)
    n = np.linalg.norm(v, axis=1, keepdims=True)
    # centroid-coincident rows get an arbitrary fixed direction, not NaN
    v = np.where(n < 1e-12, np.array([1.0, 0.0, 0.0]), v / np.maximum(n, 1e-12))
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def fibonacci(n: int) -> np.ndarray:
    i = np.arange(n, dtype=float)
    z = 1.0 - 2.0 * (i + 0.5) / n
    r = np.sqrt(np.maximum(0.0, 1.0 - z * z))
    phi = GOLDEN * i
    return np.stack([r * np.cos(phi), r * np.sin(phi), z], axis=1)


def lattice(themes: list[int], radial_dirs: np.ndarray) -> np.ndarray:
    """Fibonacci slots assigned theme-block first: theme runs are contiguous
    along the spiral, sequenced by a greedy nearest-neighbour walk over theme
    centroid directions; within a theme, members follow their radial azimuth
    so local neighbours stay related."""
    themes_arr = np.asarray(themes)
    slots = fibonacci(len(themes))
    ids = sorted(set(themes))
    cents = {t: radial_dirs[themes_arr == t].mean(axis=0) for t in ids}
    for t in ids:
        n = np.linalg.norm(cents[t])
        cents[t] = cents[t] / n if n > 1e-12 else np.array([1.0, 0.0, 0.0])
    # greedy walk from the largest theme through nearest centroids
    order = [max(ids, key=lambda t: int((themes_arr == t).sum()))]
    rest = [t for t in ids if t != order[0]]
    while rest:
        last = cents[order[-1]]
        nxt = max(rest, key=lambda t: float(cents[t] @ last))
        order.append(nxt)
        rest.remove(nxt)
    out = np.zeros((len(themes), 3))
    cursor = 0
    for t in order:
        members = np.flatnonzero(themes_arr == t)
        c = cents[t]
        # azimuth around the theme centroid axis orders members in-run
        ref = np.array([0.0, 0.0, 1.0]) if abs(c[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
        e1 = np.cross(c, ref)
        e1 /= np.linalg.norm(e1)
        e2 = np.cross(c, e1)
        az = np.arctan2(radial_dirs[members] @ e2, radial_dirs[members] @ e1)
        for k, m in enumerate(members[np.argsort(az)]):
            out[m] = slots[cursor + k]
        cursor += len(members)
    return out


def haversine(vecs: np.ndarray, n_neighbors: int, min_dist: float) -> np.ndarray | None:
    """UMAP fitted directly on the 2-sphere; None on failure (recorded, not
    raised — the caller ships the surviving layouts)."""
    import umap

    try:
        emb = umap.UMAP(
            n_neighbors=n_neighbors, min_dist=min_dist, n_components=2,
            metric="cosine", output_metric="haversine", random_state=42,
        ).fit_transform(np.asarray(vecs, dtype=float))
        xyz = np.stack([
            np.sin(emb[:, 0]) * np.cos(emb[:, 1]),
            np.sin(emb[:, 0]) * np.sin(emb[:, 1]),
            np.cos(emb[:, 0]),
        ], axis=1)
        if np.isnan(xyz).any():
            return None
        return xyz
    except Exception as exc:  # noqa: BLE001 — any UMAP failure is a data point
        print(f"haversine layout failed: {exc!r}")
        return None


def score(vecs: np.ndarray, pos: np.ndarray) -> dict:
    from sklearn.manifold import trustworthiness

    n = len(pos)
    dots = np.clip(pos @ pos.T, -1.0, 1.0)
    np.fill_diagonal(dots, -1.0)
    nn_deg = np.degrees(np.arccos(dots.max(axis=1)))
    # one tile's angular radius: half the side of an equal-area cell
    theta_deg = np.degrees(0.5 * np.sqrt(4.0 * np.pi / n))
    overlap = int((nn_deg < theta_deg).sum())
    return {
        "trustworthiness": float(trustworthiness(vecs, pos, n_neighbors=15, metric="cosine")),
        "mean_nn_deg": float(nn_deg.mean()),
        "overlap": overlap,
        "overlap_frac": float(overlap / n),
    }


def choose(scores: dict[str, dict], max_overlap_frac: float = 0.05) -> str:
    ok = {k: v for k, v in scores.items() if v["overlap_frac"] <= max_overlap_frac}
    pool = ok or scores  # nothing legible: fall back to raw fidelity
    return max(pool, key=lambda k: pool[k]["trustworthiness"])


def _round(a: np.ndarray) -> list[list[float]]:
    return [[round(float(x), 4) for x in row] for row in a]


def sphere_block(
    vecs: np.ndarray,
    c3: np.ndarray,
    themes: list[int],
    n_neighbors: int = 30,
    min_dist: float = 0.05,
    run_haversine: bool = True,
) -> dict:
    rad = radial(c3)
    lat = lattice(themes, rad)
    layouts: dict[str, np.ndarray | None] = {"radial": rad, "lattice": lat}
    layouts["haversine"] = (
        haversine(vecs, n_neighbors, min_dist) if run_haversine else None
    )
    scores = {k: score(vecs, v) for k, v in layouts.items() if v is not None}
    return {
        "radial": _round(rad),
        "haversine": _round(layouts["haversine"]) if layouts["haversine"] is not None else None,
        "lattice": _round(lat),
        "scores": scores,
        "chosen": choose(scores),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_spheremap.py -v`
Expected: all PASS. Note: `sphere_block` rounds to 4 decimals, so the
lattice uniqueness test uses rounded tuples — 40 distinct slots survive
rounding.

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check ytk/spheremap.py tests/test_spheremap.py && uv run ruff format ytk/spheremap.py tests/test_spheremap.py
git add ytk/spheremap.py tests/test_spheremap.py
git commit -m "feat(orb): sphere layout module — radial/haversine/lattice, scored on two axes"
```

---

### Task 3: `--attach-sphere` in `scripts/build_map.py` + `thumb` field

**Files:**
- Modify: `scripts/build_map.py` (new `attach_sphere()` near `attach_terrain()` ~line 450; new CLI flag in `main()` ~line 487; call at end of `main()` after `attach_terrain()` ~line 635)
- Test: `tests/test_spheremap_attach.py`

**Interfaces:**
- Consumes: `ytk.spheremap.sphere_block(vecs, c3, themes, n_neighbors, min_dist, run_haversine)` (Task 2).
- Produces: `content.sphere` block and per-content-point `thumb` in
  `~/.ytk/map.json` per the data contract; `_content_alignment(points,
  meta, content_cats) -> list[int]` (raises `SystemExit` on mismatch) —
  used only inside the script but unit-tested.

- [ ] **Step 1: Write the failing test**

```python
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from build_map import _content_alignment


def _points():
    return [
        {"t": "a", "c": "youtube", "c3": [0, 0, 1]},
        {"t": "b", "c": "memory"},
        {"t": "c", "c": "instagram", "c3": [1, 0, 0]},
    ]


def _meta():
    return [
        {"title": "a", "cat": "youtube"},
        {"title": "b", "cat": "memory"},
        {"title": "c", "cat": "instagram"},
    ]


def test_alignment_returns_content_indices():
    assert _content_alignment(_points(), _meta(), {"youtube", "instagram"}) == [0, 2]


def test_alignment_rejects_count_drift():
    with pytest.raises(SystemExit):
        _content_alignment(_points()[:2], _meta(), {"youtube", "instagram"})


def test_alignment_rejects_title_drift():
    meta = _meta()
    meta[0]["title"] = "renamed since map build"
    with pytest.raises(SystemExit):
        _content_alignment(_points(), meta, {"youtube", "instagram"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_spheremap_attach.py -v`
Expected: FAIL — `ImportError: cannot import name '_content_alignment'`.

- [ ] **Step 3: Implement in `scripts/build_map.py`**

Add after `attach_terrain()` (keep its style: read `OUT`, compute, write
back, never re-run the 2D/3D UMAP):

```python
def _content_alignment(points: list[dict], meta: list[dict], content_cats) -> list[int]:
    """Store rows must still match map.json rows one-to-one; the sphere pass
    is index-aligned, so any drift means a stale map — rebuild, not guess."""
    if len(points) != len(meta):
        raise SystemExit(
            f"map.json has {len(points)} points but the store has {len(meta)} — "
            "stale map; run the full build first"
        )
    for i, (p, m) in enumerate(zip(points, meta)):
        if p["t"] != m["title"]:
            raise SystemExit(
                f"map.json point {i} is {p['t']!r} but store row is "
                f"{m['title']!r} — stale map; run the full build first"
            )
    cidx = [i for i, m in enumerate(meta) if m["cat"] in content_cats]
    map_cidx = [i for i, p in enumerate(points) if "c3" in p]
    if cidx != map_cidx:
        raise SystemExit("content membership drifted since the map build — rebuild")
    return cidx


def attach_sphere() -> None:
    """Compute the /orb sphere layouts (ytk/spheremap.py) from the stored c3
    coordinates plus live store vectors, and attach thumbnail paths. Aligned
    by index to the existing map.json; aborts loudly on drift."""
    from ytk.spheremap import sphere_block
    from ytk.store import _get_client

    data = json.loads(OUT.read_text())
    vecs, meta, _docs = load_points()
    cidx = _content_alignment(data["points"], meta, CONTENT_CATS)
    cpts = [data["points"][i] for i in cidx]
    c3 = np.array([p["c3"] for p in cpts])
    themes = [p.get("th", -1) for p in cpts]
    nn = int(data["content"]["params"].get("n_neighbors", 30))
    md = float(data["content"]["params"].get("min_dist", 0.05))
    print(f"sphere: {len(cpts)} content points, nn={nn} min_dist={md}")
    block = sphere_block(vecs[cidx], c3, themes, n_neighbors=nn, min_dist=md)
    for name, s in block["scores"].items():
        mark = " <- chosen" if name == block["chosen"] else ""
        print(
            f"  {name}: trust={s['trustworthiness']:.4f} "
            f"meanNN={s['mean_nn_deg']:.2f}deg overlap={s['overlap']} "
            f"({100 * s['overlap_frac']:.1f}%){mark}"
        )
    data["content"]["sphere"] = block
    client = _get_client()
    thumbs = {
        m["url"]: m["image_path"]
        for m in client.get_collection("ytk_visual").get(include=["metadatas"])["metadatas"]
        if m.get("url") and m.get("image_path")
    }
    n_thumbs = 0
    for p in cpts:
        t = thumbs.get(p.get("u"))
        if t:
            p["thumb"] = t
            n_thumbs += 1
    print(f"  thumbs: {n_thumbs}/{len(cpts)}; sample: {[p.get('thumb') for p in cpts[:3]]}")
    OUT.write_text(json.dumps(data))
```

In `main()`, add the flag next to `--attach-terrain`:

```python
    ap.add_argument(
        "--attach-sphere",
        action="store_true",
        help="only (re)compute the /orb sphere layouts over the existing map.json",
    )
```

and immediately after the existing `if args.attach_terrain:` block:

```python
    if args.attach_sphere:
        attach_sphere()
        return
```

At the very end of `main()`, after `attach_terrain()`:

```python
    attach_sphere()
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_spheremap_attach.py tests/test_build_map_assemble.py -v`
Expected: all PASS (the assemble tests guard against accidental breakage of
the module import path).

- [ ] **Step 5: Run against the real map**

Run: `just chroma-status` (must be up), then
`uv run python scripts/build_map.py --attach-sphere`
Expected: prints the score table for the (up to) three layouts and a thumbs
count around 380-460 of 505. VERIFY the printed thumb samples start with
`sources/` (they feed `/vault-media/<rel>`); if they are absolute paths,
STOP and report — the atlas URL scheme in Task 6 depends on this.
Record the full score table in your report; it decides nothing here but the
user reads it at review.

- [ ] **Step 6: Matplotlib checkpoint — all three real layouts, side by side**

Write and run `$SCRATCH/layouts_checkpoint.py`:

```python
"""Render every sphere layout from the real map.json for eyeball review.
House style per docs/assets/README.md: imported, never restated."""
import json
import subprocess
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path("scripts").resolve()))
from plot_assets import BG, FRAME, MARGIN, MUTED, PANEL, RED, TICK_SIZE, figure, frame_panels, panel_title

plt.style.use("dark_background")

SCRATCH = Path("/private/tmp/claude-501/-Users-melocoton-Developer-ytk/a880b851-b1c2-4d8c-a41c-6109fa752743/scratchpad")
data = json.loads((Path.home() / ".ytk" / "map.json").read_text())
sphere = data["content"]["sphere"]
cpts = [p for p in data["points"] if "c3" in p]
themes = np.array([p.get("th", -1) for p in cpts])
names = [k for k in ("radial", "haversine", "lattice") if sphere.get(k)]
stamp = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
meta = "  ·  ".join(
    f"{n}: trust {sphere['scores'][n]['trustworthiness']:.3f}, "
    f"overlap {100 * sphere['scores'][n]['overlap_frac']:.0f}%"
    for n in names
)
fig, top = figure(
    12.6,
    4.9 * len(names) + 2.2,
    2,
    "orb checkpoint",
    "Three sphere layouts over the live content embedding",
    f"{len(cpts)} notes  ·  chosen: {sphere['chosen']}  ·  {meta}  ·  {stamp}",
)
for k, name in enumerate(names):
    xyz = np.array(sphere[name])
    lon, lat = np.arctan2(xyz[:, 1], xyz[:, 0]), np.arcsin(np.clip(xyz[:, 2], -1, 1))
    dots = np.clip(xyz @ xyz.T, -1, 1)
    np.fill_diagonal(dots, -1)
    nn = np.degrees(np.arccos(dots.max(axis=1)))
    theta = np.degrees(0.5 * np.sqrt(4 * np.pi / len(xyz)))
    bad = nn < theta
    ax = fig.add_subplot(len(names), 1, k + 1, projection="mollweide")
    ax.set_facecolor(PANEL)
    ax.scatter(lon, lat, c=themes, cmap="tab20", s=11, linewidths=0)
    ax.scatter(lon[bad], lat[bad], facecolors="none", edgecolors=RED, s=60, linewidths=0.8)
    chosen = "  [CHOSEN]" if sphere["chosen"] == name else ""
    panel_title(ax, f"{name}{chosen} — red rings mark tiles closer than one tile radius", width=86)
    ax.grid(alpha=0.22, color=FRAME)
    ax.tick_params(colors=MUTED, labelsize=TICK_SIZE - 1)
fig.subplots_adjust(left=MARGIN, right=1 - MARGIN, top=top, bottom=MARGIN + 0.01, hspace=0.24)
frame_panels(fig)
fig.savefig(SCRATCH / "layouts-real.png", dpi=200, facecolor=BG)
print(f"wrote {SCRATCH / 'layouts-real.png'}")
```

READ the PNG. Judge each layout: theme regions coherent? radial's clumps as
bad as predicted? lattice's theme runs contiguous (contiguous color bands
along the spiral — broken bands mean the greedy walk is buggy even if every
test passes)? Send the PNG to the user with SendUserFile and record your
verdict next to the score table. If the eye and the score disagree about
`chosen`, say so explicitly — that disagreement goes to the user, not under
the rug.

- [ ] **Step 7: Lint and commit**

```bash
uv run ruff check scripts/build_map.py tests/test_spheremap_attach.py && uv run ruff format scripts/build_map.py tests/test_spheremap_attach.py
git add scripts/build_map.py tests/test_spheremap_attach.py
git commit -m "feat(orb): attach sphere layouts + thumb paths to map.json"
```

---

### Task 4: `GET /api/orb`

**Files:**
- Modify: `ytk/ui/server.py` (add endpoint next to `map_data_api`, ~line 943; add module constant near it)
- Test: `tests/ui/test_orb_api.py`

**Interfaces:**
- Consumes: `content.sphere` + point `thumb` from Task 3 (reads the file
  only — no imports from spheremap).
- Produces: the `/api/orb` response per the data contract. Frontend Task 5
  fetches exactly `{points, themes, sphere}`.

- [ ] **Step 1: Write the failing test**

```python
import json

from fastapi.testclient import TestClient

import ytk.ui.server as server

client = TestClient(server.app)


def _map(tmp_path, with_sphere=True):
    content = {
        "params": {},
        "groups": [{"label": "ai-tools"}, {"label": "design"}],
    }
    if with_sphere:
        content["sphere"] = {
            "radial": [[0, 0, 1], [1, 0, 0]],
            "haversine": None,
            "lattice": [[0, 1, 0], [0, 0, -1]],
            "scores": {"radial": {"trustworthiness": 0.9, "mean_nn_deg": 40.0,
                                  "overlap": 0, "overlap_frac": 0.0}},
            "chosen": "radial",
        }
    data = {
        "v": 2,
        "points": [
            {"t": "vid", "c": "youtube", "u": "https://y", "d": "2026-01-01",
             "p": "second-brain/sources/youtube/vid.md", "c3": [0, 0, 1],
             "th": 0, "thumb": "sources/youtube/thumbnails/x-thumb.jpg"},
            {"t": "atom", "c": "memory", "p": "second-brain/inbox/a.md"},
            {"t": "gram", "c": "instagram", "u": "https://i", "d": None,
             "p": "second-brain/sources/instagram/g.md", "c3": [1, 0, 0], "th": 1},
        ],
        "content": content,
        "all": {},
    }
    p = tmp_path / "map.json"
    p.write_text(json.dumps(data))
    return p


def test_orb_serves_content_points_in_c3_order(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_ORB_MAP", _map(tmp_path))
    r = client.get("/api/orb")
    assert r.status_code == 200
    body = r.json()
    assert [p["t"] for p in body["points"]] == ["vid", "gram"]  # memory excluded
    assert body["points"][0]["thumb"] == "sources/youtube/thumbnails/x-thumb.jpg"
    assert body["points"][1]["thumb"] is None
    assert body["themes"] == ["ai-tools", "design"]
    assert body["sphere"]["chosen"] == "radial"
    assert len(body["sphere"]["radial"]) == 2


def test_orb_404_without_sphere_block(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_ORB_MAP", _map(tmp_path, with_sphere=False))
    r = client.get("/api/orb")
    assert r.status_code == 404
    assert "attach-sphere" in r.json()["detail"]


def test_orb_404_without_map(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_ORB_MAP", tmp_path / "missing.json")
    assert client.get("/api/orb").status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/ui/test_orb_api.py -v`
Expected: FAIL — `AttributeError: ... has no attribute '_ORB_MAP'` (the
monkeypatch target) or 404-vs-missing-route errors.

- [ ] **Step 3: Implement the endpoint**

In `ytk/ui/server.py`, directly above `map_data_api` (~line 943):

```python
# module-level so tests monkeypatch the path; /api/map resolves its own copy
_ORB_MAP = Path.home() / ".ytk" / "map.json"


@app.get("/api/orb")
async def orb_api():
    """The /orb sphere gallery: content points + precomputed sphere layouts.
    Thin by design — every coordinate comes from build_map.py --attach-sphere."""
    if not _ORB_MAP.exists():
        raise HTTPException(status_code=404, detail="No map built yet")
    data = json.loads(_ORB_MAP.read_text())
    sphere = (data.get("content") or {}).get("sphere")
    if not sphere:
        raise HTTPException(
            status_code=404,
            detail="No sphere block — run: uv run python scripts/build_map.py --attach-sphere",
        )
    points = [
        {"p": p.get("p", ""), "t": p.get("t", ""), "c": p.get("c", ""),
         "u": p.get("u") or None, "d": p.get("d") or None,
         "th": p.get("th", -1), "thumb": p.get("thumb") or None}
        for p in data["points"] if "c3" in p
    ]
    themes = [g.get("label", "") for g in data["content"].get("groups", [])]
    return {"points": points, "themes": themes, "sphere": sphere}
```

Check the file's imports: `json`, `Path`, `HTTPException` are already
imported at the top of server.py — do not re-import.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/ui/test_orb_api.py tests/ui/test_spa_mount.py -v`
Expected: all PASS.

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check ytk/ui/server.py tests/ui/test_orb_api.py && uv run ruff format ytk/ui/server.py tests/ui/test_orb_api.py
git add ytk/ui/server.py tests/ui/test_orb_api.py
git commit -m "feat(orb): /api/orb — thin content-points + sphere layouts endpoint"
```

---

### Task 5: `web/src/api/orb.ts`

**Files:**
- Create: `web/src/api/orb.ts`
- Test: `web/src/api/orb.test.ts`

**Interfaces:**
- Consumes: `apiGet` from `./client` (exists), `useQuery` from
  `@tanstack/react-query`.
- Produces (Tasks 6-10 import these): types `OrbPoint`, `OrbSphere`,
  `OrbData`, `LayoutName`; `fetchOrb(): Promise<OrbData>`; `useOrb()`.

- [ ] **Step 1: Write the failing test**

```typescript
import { expect, test, vi } from "vitest";
import { fetchOrb } from "./orb";

test("fetchOrb hits /api/orb and returns the payload", async () => {
  const payload = {
    points: [{ p: "a.md", t: "a", c: "youtube", u: null, d: null, th: 0, thumb: null }],
    themes: ["ai-tools"],
    sphere: { radial: [[0, 0, 1]], haversine: null, lattice: [[0, 1, 0]],
              scores: {}, chosen: "radial" },
  };
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(payload), { status: 200 }),
  );
  vi.stubGlobal("fetch", fetchMock);
  const data = await fetchOrb();
  expect(fetchMock).toHaveBeenCalledWith("/api/orb");
  expect(data.sphere.chosen).toBe("radial");
  expect(data.points[0].p).toBe("a.md");
  vi.unstubAllGlobals();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && vp exec vitest run src/api/orb.test.ts`
Expected: FAIL — cannot resolve `./orb`.

- [ ] **Step 3: Implement `web/src/api/orb.ts`** (mirror `map.ts` style)

```typescript
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "./client";

export type OrbPoint = {
  p: string; // vault-relative note path — NoteViewer's key
  t: string;
  c: string;
  u?: string | null;
  d?: string | null;
  th: number;
  thumb?: string | null; // vault-relative, served at /vault-media/<thumb>
};

export type LayoutName = "radial" | "haversine" | "lattice";

export type OrbScores = Partial<
  Record<LayoutName, { trustworthiness: number; mean_nn_deg: number; overlap: number; overlap_frac: number }>
>;

export type OrbSphere = {
  radial: number[][];
  haversine: number[][] | null;
  lattice: number[][];
  scores: OrbScores;
  chosen: LayoutName;
};

export type OrbData = { points: OrbPoint[]; themes: string[]; sphere: OrbSphere };

export const fetchOrb = () => apiGet<OrbData>("/api/orb");

export const useOrb = () => useQuery({ queryKey: ["orb"], queryFn: fetchOrb });
```

- [ ] **Step 4: Run test**

Run: `cd web && vp exec vitest run src/api/orb.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/api/orb.ts web/src/api/orb.test.ts
git commit -m "feat(orb): typed /api/orb client wrapper"
```

---

### Task 6: `web/src/lib/orb/atlas.ts` — texture atlas

**Files:**
- Create: `web/src/lib/orb/atlas.ts`
- Test: `web/src/lib/orb/atlas.test.ts`

**Interfaces:**
- Consumes: `OrbPoint` from `../../api/orb` (Task 5); `CanvasTexture` from
  `three`.
- Produces (scene.ts consumes): constants `ATLAS_SIZE = 4096`, `TILE = 128`,
  `COLS = 32`; `uvRect(i: number): { u: number; v: number; s: number }`
  (bottom-left UV origin, `s` = tile span); `themeColor(th: number, n:
  number): string`; `buildAtlas(points: OrbPoint[], nThemes: number,
  onUpdate: () => void): AtlasHandle` where `AtlasHandle = { texture:
  CanvasTexture; dispose(): void; idle: Promise<void> }`.

- [ ] **Step 1: Write the failing test**

```typescript
import { expect, test } from "vitest";
import type { OrbPoint } from "../../api/orb";
import { ATLAS_SIZE, buildAtlas, COLS, themeColor, TILE, uvRect } from "./atlas";

test("uvRect flips v for three.js bottom-left origin", () => {
  // slot 0: canvas top-left tile -> UV origin at its BOTTOM edge
  expect(uvRect(0)).toEqual({ u: 0, v: 1 - TILE / ATLAS_SIZE, s: TILE / ATLAS_SIZE });
  // slot 33: row 1, col 1
  expect(uvRect(33)).toEqual({
    u: TILE / ATLAS_SIZE,
    v: 1 - (2 * TILE) / ATLAS_SIZE,
    s: TILE / ATLAS_SIZE,
  });
  expect(COLS).toBe(ATLAS_SIZE / TILE);
});

test("themeColor is a stable hsl ramp", () => {
  expect(themeColor(0, 17)).toBe(themeColor(0, 17));
  expect(themeColor(0, 17)).not.toBe(themeColor(1, 17));
});

test("buildAtlas paints placeholders immediately and resolves idle", async () => {
  const points: OrbPoint[] = [
    { p: "a.md", t: "a", c: "youtube", th: 0, thumb: null },
    { p: "b.md", t: "b", c: "instagram", th: 1, thumb: "missing/nope.jpg" },
  ];
  const atlas = buildAtlas(points, 17, () => {});
  const canvas = atlas.texture.image as HTMLCanvasElement;
  expect(canvas.width).toBe(ATLAS_SIZE);
  const px = canvas.getContext("2d")!.getImageData(TILE / 2, TILE / 2, 1, 1).data;
  expect(px[3]).toBe(255); // placeholder painted, not transparent
  await atlas.idle; // missing image resolves (failure keeps placeholder)
  atlas.dispose();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && vp exec vitest run src/lib/orb/atlas.test.ts`
Expected: FAIL — cannot resolve `./atlas`.

- [ ] **Step 3: Implement `web/src/lib/orb/atlas.ts`**

```typescript
import { CanvasTexture, SRGBColorSpace } from "three";
import type { OrbPoint } from "../../api/orb";

export const ATLAS_SIZE = 4096;
export const TILE = 128;
export const COLS = ATLAS_SIZE / TILE; // 32 -> 1024 slots; design breaks at ~1024 notes

export function uvRect(i: number): { u: number; v: number; s: number } {
  const col = i % COLS;
  const row = Math.floor(i / COLS);
  const s = TILE / ATLAS_SIZE;
  // canvas rows grow downward; UV v grows upward — flip to the tile's bottom edge
  return { u: col * s, v: 1 - (row + 1) * s, s };
}

export function themeColor(th: number, n: number): string {
  const hue = ((th < 0 ? n : th) * 360) / Math.max(1, n + 1);
  return `hsl(${hue.toFixed(0)} 35% 22%)`;
}

export type AtlasHandle = { texture: CanvasTexture; dispose(): void; idle: Promise<void> };

export function buildAtlas(
  points: OrbPoint[],
  nThemes: number,
  onUpdate: () => void,
): AtlasHandle {
  const canvas = document.createElement("canvas");
  canvas.width = ATLAS_SIZE;
  canvas.height = ATLAS_SIZE;
  const ctx = canvas.getContext("2d")!;
  points.forEach((p, i) => {
    const col = (i % COLS) * TILE;
    const row = Math.floor(i / COLS) * TILE;
    ctx.fillStyle = themeColor(p.th, nThemes);
    ctx.fillRect(col, row, TILE, TILE);
  });
  const texture = new CanvasTexture(canvas);
  texture.colorSpace = SRGBColorSpace;
  let disposed = false;
  const loads = points.map((p, i) => {
    if (!p.thumb) return Promise.resolve();
    return new Promise<void>((resolve) => {
      const img = new Image();
      img.onload = () => {
        if (disposed) return resolve();
        // cover-crop into the square slot
        const side = Math.min(img.naturalWidth, img.naturalHeight);
        const sx = (img.naturalWidth - side) / 2;
        const sy = (img.naturalHeight - side) / 2;
        const col = (i % COLS) * TILE;
        const row = Math.floor(i / COLS) * TILE;
        ctx.drawImage(img, sx, sy, side, side, col, row, TILE, TILE);
        texture.needsUpdate = true;
        onUpdate();
        resolve();
      };
      img.onerror = () => resolve(); // failed load keeps the theme placeholder
      img.src = `/vault-media/${p.thumb}`;
    });
  });
  return {
    texture,
    idle: Promise.all(loads).then(() => undefined),
    dispose() {
      disposed = true;
      texture.dispose();
    },
  };
}
```

- [ ] **Step 4: Run test**

Run: `cd web && vp exec vitest run src/lib/orb/atlas.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/orb/atlas.ts web/src/lib/orb/atlas.test.ts
git commit -m "feat(orb): canvas atlas — 1024 slots, theme placeholders, incremental image fill"
```

---

### Task 7: `web/src/lib/orb/controls.ts` — drag, inertia, tap

**Files:**
- Create: `web/src/lib/orb/controls.ts`
- Test: `web/src/lib/orb/controls.test.ts`

**Interfaces:**
- Consumes: nothing (pure state machine — no DOM, no three).
- Produces (scene.ts consumes): `createControls(): OrbControls` with
  `down(x, y): void`, `move(x, y): void`, `up(): { tap: boolean }`,
  `wheel(dy: number): void`, `step(dt: number): { yaw: number; pitch:
  number }`, `setTarget(yaw: number, pitch: number): void` (focus tween
  writes through this), `dragging: boolean`. Angles in radians. Pitch
  clamped to +-75 deg. `SENS = 0.0022` rad/px. Tap threshold 6 px total
  travel.

- [ ] **Step 0: Simulate the spring in Python first (matplotlib checkpoint)**

The constants `STIFFNESS = 60` and `FRICTION = 4` below are proposals, not
facts. Prove them in a plot before coding TypeScript — a wrong-feeling
spring found here costs one re-run; found in the browser it costs a build
cycle. Write and run `$SCRATCH/spring_sim.py`:

```python
"""Simulate the orb camera spring: drag-follow, throw inertia, settle."""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

SENS, STIFFNESS, FRICTION = 0.0022, 60.0, 10.0
DT = 1 / 60


def simulate(gesture):
    """gesture: list of (kind, x) per frame; returns yaw trace."""
    yaw = tyaw = vyaw = 0.0
    dragging = False
    last_x = last_dx = 0.0
    trace = []
    for kind, x in gesture:
        if kind == "down":
            dragging, last_x, vyaw = True, x, 0.0
        elif kind == "move" and dragging:
            last_dx = x - last_x
            last_x = x
            tyaw += last_dx * SENS
        elif kind == "up" and dragging:
            dragging = False
            vyaw = last_dx * SENS * 60
        if not dragging:
            tyaw += vyaw * DT
            vyaw *= np.exp(-FRICTION * DT)
        yaw += (tyaw - yaw) * (1 - np.exp(-STIFFNESS * DT))
        trace.append(yaw)
    return np.array(trace)


frames = lambda n, kind="idle": [(kind, 0.0)] * n
# gesture 1: slow 200px drag over 0.5s, hold, release
slow = [("down", 0.0)] + [("move", x) for x in np.linspace(6, 200, 30)] + \
       frames(12, ) + [("up", 200.0)] + frames(120)
# gesture 2: fast 300px flick over 6 frames, release mid-motion
flick = [("down", 0.0)] + [("move", x) for x in np.linspace(50, 300, 6)] + \
        [("up", 300.0)] + frames(180)

# house style per docs/assets/README.md — imported, never restated
sys.path.insert(0, str(Path("scripts").resolve()))
from plot_assets import BG, BLUE, DIM, GOLD, MARGIN, MUTED, figure, frame_panels, panel_title, style_axes

plt.style.use("dark_background")
fig, top = figure(
    12.6,
    6.4,
    3,
    "orb checkpoint",
    "The camera spring under two gestures, before a line of TypeScript",
    f"SENS {SENS}  ·  STIFFNESS {STIFFNESS:.0f}  ·  FRICTION {FRICTION:.0f}  ·  60 fps steps",
)
for k, (name, g, color) in enumerate(
    [("slow drag + hold", slow, GOLD), ("flick + coast", flick, BLUE)]
):
    ax = fig.add_subplot(1, 2, k + 1)
    tr = simulate(g)
    t = np.arange(len(tr)) * DT
    ax.plot(t, np.degrees(tr), color=color, lw=2.0)
    style_axes(ax)
    ax.set_ylabel("yaw deg")
    ax.grid(alpha=0.25, color=DIM)
    # settle time: last frame where |yaw - final| > 0.05 deg
    final = tr[-1]
    moving = np.abs(tr - final) > np.radians(0.05)
    settle = (np.max(np.flatnonzero(moving)) + 1) * DT if moving.any() else 0.0
    release = next(i for i, (kk, _) in enumerate(g) if kk == "up") * DT
    ax.axvline(release, color=MUTED, ls="--", lw=0.9)
    ax.set_xlabel(f"s   (settles {settle - release:.2f}s after release)")
    panel_title(ax, name)
    print(f"{name}: travel {np.degrees(final):.1f} deg, "
          f"settle {settle - release:.2f}s after release")
SCRATCH = Path("/private/tmp/claude-501/-Users-melocoton-Developer-ytk/a880b851-b1c2-4d8c-a41c-6109fa752743/scratchpad")
fig.subplots_adjust(left=MARGIN + 0.03, right=1 - MARGIN, top=top, bottom=0.16, wspace=0.26)
frame_panels(fig)
fig.savefig(SCRATCH / "spring-sim.png", dpi=200, facecolor=BG)
print(f"wrote {SCRATCH / 'spring-sim.png'}")
```

(Add `import sys` next to `from pathlib import Path` at the top of the
script.)

READ the PNG and check the lenis criteria: drag tracks with no visible lag
ramp (the follow curve hugs the input during drag), the flick coasts
noticeably past release (a visible curve, not a wall), and both settle
0.3-0.8s after release with NO overshoot oscillation (a damped spring that
wiggles is under-damped — raise STIFFNESS or lower the throw velocity
factor). If constants change here, carry the changed values into the
TypeScript below AND into this plan file (edit it), so Step 3's code and
the simulation never disagree. Report the final constants and settle times.

- [ ] **Step 1: Write the failing test**

```typescript
import { expect, test } from "vitest";
import { createControls, PITCH_MAX, SENS } from "./controls";

test("drag maps pixel deltas to yaw/pitch at SENS", () => {
  const c = createControls();
  c.down(100, 100);
  c.move(200, 100); // 100px right
  c.up();
  // settle the spring
  let out = { yaw: 0, pitch: 0 };
  for (let i = 0; i < 600; i++) out = c.step(1 / 60);
  expect(out.yaw).toBeCloseTo(100 * SENS, 3);
  expect(out.pitch).toBeCloseTo(0, 5);
});

test("pitch clamps at +-75deg", () => {
  const c = createControls();
  c.down(0, 0);
  c.move(0, 100000);
  c.up();
  let out = { yaw: 0, pitch: 0 };
  for (let i = 0; i < 600; i++) out = c.step(1 / 60);
  expect(Math.abs(out.pitch)).toBeLessThanOrEqual(PITCH_MAX + 1e-6);
});

test("release keeps momentum then settles (inertia)", () => {
  const c = createControls();
  c.down(0, 0);
  for (let i = 1; i <= 5; i++) {
    c.move(i * 20, 0);
    c.step(1 / 60); // velocity accumulates between moves
  }
  c.up();
  const atRelease = c.step(1 / 60).yaw;
  for (let i = 0; i < 120; i++) c.step(1 / 60);
  const later = c.step(1 / 60).yaw;
  expect(later).toBeGreaterThan(atRelease); // coasted past the release point
  const settled = (() => { let o = c.step(1 / 60); for (let i = 0; i < 900; i++) o = c.step(1 / 60); return o; })();
  const next = c.step(1 / 60);
  expect(Math.abs(next.yaw - settled.yaw)).toBeLessThan(1e-4); // spring at rest
});

test("tap vs drag threshold at 6px travel", () => {
  const c = createControls();
  c.down(10, 10);
  c.move(13, 12); // ~3.6px
  expect(c.up().tap).toBe(true);
  c.down(10, 10);
  c.move(16, 14); // ~7.2px
  expect(c.up().tap).toBe(false);
});

test("setTarget overrides pointer state for the focus tween", () => {
  const c = createControls();
  c.setTarget(1.0, 0.5);
  let out = { yaw: 0, pitch: 0 };
  for (let i = 0; i < 600; i++) out = c.step(1 / 60);
  expect(out.yaw).toBeCloseTo(1.0, 3);
  expect(out.pitch).toBeCloseTo(0.5, 3);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && vp exec vitest run src/lib/orb/controls.test.ts`
Expected: FAIL — cannot resolve `./controls`.

- [ ] **Step 3: Implement `web/src/lib/orb/controls.ts`**

```typescript
/* Pointer-drag camera state: target angles chase the pointer while down,
   coast on inertia after release, and settle on a critically damped spring —
   the lenis-style easing the reference names, without the dependency. */

export const SENS = 0.0022; // rad per px
export const PITCH_MAX = (75 * Math.PI) / 180;
const TAP_PX = 6;
const STIFFNESS = 60; // spring toward target; ~0.3s to settle
const FRICTION = 10; // exponential decay of thrown velocity; 4 settled 2-3x too slow in the T7 sim

export type OrbControls = {
  down(x: number, y: number): void;
  move(x: number, y: number): void;
  up(): { tap: boolean };
  wheel(dy: number): void;
  step(dt: number): { yaw: number; pitch: number };
  setTarget(yaw: number, pitch: number): void;
  readonly dragging: boolean;
};

export function createControls(): OrbControls {
  let yaw = 0, pitch = 0; // rendered angles
  let tyaw = 0, tpitch = 0; // spring targets
  let vyaw = 0, vpitch = 0; // throw velocity (rad/s), post-release only
  let dragging = false;
  let lastX = 0, lastY = 0, travel = 0;
  let lastDX = 0, lastDY = 0;

  const clamp = () => { tpitch = Math.max(-PITCH_MAX, Math.min(PITCH_MAX, tpitch)); };

  return {
    get dragging() { return dragging; },
    down(x, y) {
      dragging = true;
      vyaw = vpitch = 0;
      lastX = x; lastY = y; travel = 0; lastDX = 0; lastDY = 0;
    },
    move(x, y) {
      if (!dragging) return;
      lastDX = x - lastX; lastDY = y - lastY;
      travel += Math.hypot(lastDX, lastDY);
      lastX = x; lastY = y;
      tyaw += lastDX * SENS;
      tpitch += lastDY * SENS;
      clamp();
    },
    up() {
      if (!dragging) return { tap: false };
      dragging = false;
      const tap = travel <= TAP_PX;
      if (!tap) { // throw: last frame's delta becomes velocity
        vyaw = lastDX * SENS * 60;
        vpitch = lastDY * SENS * 60;
      }
      return { tap };
    },
    wheel(dy) { tyaw += dy * SENS * 0.5; },
    setTarget(y, p) { tyaw = y; tpitch = p; vyaw = vpitch = 0; clamp(); },
    step(dt) {
      if (!dragging) {
        const decay = Math.exp(-FRICTION * dt);
        tyaw += vyaw * dt; tpitch += vpitch * dt;
        vyaw *= decay; vpitch *= decay;
        clamp();
      }
      // critically damped approach of rendered angles toward targets
      const k = 1 - Math.exp(-STIFFNESS * dt);
      yaw += (tyaw - yaw) * k;
      pitch += (tpitch - pitch) * k;
      return { yaw, pitch };
    },
  };
}
```

- [ ] **Step 4: Run test**

Run: `cd web && vp exec vitest run src/lib/orb/controls.test.ts`
Expected: PASS. If the inertia test is flaky on exact values, the assertions
above are ordinal (greater-than / settles), not exact — do not weaken them
further; fix the implementation instead.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/orb/controls.ts web/src/lib/orb/controls.test.ts
git commit -m "feat(orb): drag/inertia/tap state machine with damped-spring settle"
```

---

### Task 8: `web/src/lib/orb/pick.ts` — picking and screen projection

**Files:**
- Create: `web/src/lib/orb/pick.ts`
- Test: `web/src/lib/orb/pick.test.ts`

**Interfaces:**
- Consumes: `PerspectiveCamera`, `Vector3` from `three`.
- Produces (scene.ts and the route consume):
  - `pickTile(ndcX, ndcY, camera, centers: Float32Array, half: number): number | null`
    — nearest tile whose plane-local hit falls inside +-half; centers is a
    flat xyz array of tile centers on the unit sphere.
  - `tileScreenRect(camera, center: Vector3, half: number, vw: number, vh: number): DOMRect`
    — the tile quad's screen-space bounding rect.

- [ ] **Step 1: Write the failing test**

```typescript
import { PerspectiveCamera, Vector3 } from "three";
import { expect, test } from "vitest";
import { pickTile, tileScreenRect } from "./pick";

function camera(): PerspectiveCamera {
  const cam = new PerspectiveCamera(60, 800 / 600, 0.01, 10);
  cam.position.set(0, 0, 0);
  cam.lookAt(0, 0, -1);
  cam.updateMatrixWorld();
  return cam;
}

test("tileScreenRect projects a known quad to known pixels", () => {
  const rect = tileScreenRect(camera(), new Vector3(0, 0, -1), 0.1, 800, 600);
  // half=0.1 at distance 1, fov 60: half-height px = 0.1 / tan(30deg) * 300
  const expectHalf = (0.1 / Math.tan(Math.PI / 6)) * 300;
  expect(rect.width / 2).toBeCloseTo(expectHalf, 0);
  expect(rect.left + rect.width / 2).toBeCloseTo(400, 0);
  expect(rect.top + rect.height / 2).toBeCloseTo(300, 0);
});

test("pickTile hits the centered tile and misses empty space", () => {
  const centers = new Float32Array([0, 0, -1, 1, 0, 0]);
  expect(pickTile(0, 0, camera(), centers, 0.08)).toBe(0);
  // straight up at the sphere's pole: no tile there
  expect(pickTile(0, 0.99, camera(), centers, 0.08)).toBeNull();
});

test("pickTile prefers the nearer of stacked tiles", () => {
  // both tiles straight ahead; the one on the near hemisphere side wins
  const centers = new Float32Array([0, 0, -1, 0, 0, 1]);
  expect(pickTile(0, 0, camera(), centers, 0.08)).toBe(0);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && vp exec vitest run src/lib/orb/pick.test.ts`
Expected: FAIL — cannot resolve `./pick`.

- [ ] **Step 3: Implement `web/src/lib/orb/pick.ts`**

```typescript
import { PerspectiveCamera, Vector3 } from "three";

/* Tiles are shader-positioned quads, invisible to three's Raycaster; picking
   is ray-vs-plane per tile in JS. 505 tiles is trivially cheap per frame. */

const UP = new Vector3(0, 1, 0);
const ALT = new Vector3(1, 0, 0);

function basis(center: Vector3): { n: Vector3; e1: Vector3; e2: Vector3 } {
  const n = center.clone().negate().normalize(); // tiles face the origin
  const ref = Math.abs(n.y) > 0.9 ? ALT : UP;
  const e1 = new Vector3().crossVectors(ref, n).normalize();
  const e2 = new Vector3().crossVectors(n, e1);
  return { n, e1, e2 };
}

export function pickTile(
  ndcX: number,
  ndcY: number,
  camera: PerspectiveCamera,
  centers: Float32Array,
  half: number,
): number | null {
  const origin = camera.position.clone();
  const dir = new Vector3(ndcX, ndcY, 0.5).unproject(camera).sub(origin).normalize();
  let best: number | null = null;
  let bestT = Infinity;
  const c = new Vector3();
  for (let i = 0; i * 3 < centers.length; i++) {
    c.set(centers[i * 3], centers[i * 3 + 1], centers[i * 3 + 2]);
    const { n, e1, e2 } = basis(c);
    const denom = dir.dot(n);
    if (Math.abs(denom) < 1e-9) continue;
    const t = c.clone().sub(origin).dot(n) / denom;
    if (t <= 0 || t >= bestT) continue;
    const hit = origin.clone().addScaledVector(dir, t).sub(c);
    if (Math.abs(hit.dot(e1)) <= half && Math.abs(hit.dot(e2)) <= half) {
      best = i;
      bestT = t;
    }
  }
  return best;
}

export function tileScreenRect(
  camera: PerspectiveCamera,
  center: Vector3,
  half: number,
  vw: number,
  vh: number,
): DOMRect {
  const { e1, e2 } = basis(center);
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const [a, b] of [[-1, -1], [1, -1], [1, 1], [-1, 1]] as const) {
    const corner = center.clone().addScaledVector(e1, a * half).addScaledVector(e2, b * half);
    corner.project(camera);
    const x = ((corner.x + 1) / 2) * vw;
    const y = ((1 - corner.y) / 2) * vh;
    minX = Math.min(minX, x); maxX = Math.max(maxX, x);
    minY = Math.min(minY, y); maxY = Math.max(maxY, y);
  }
  return new DOMRect(minX, minY, maxX - minX, maxY - minY);
}
```

- [ ] **Step 4: Run test**

Run: `cd web && vp exec vitest run src/lib/orb/pick.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/orb/pick.ts web/src/lib/orb/pick.test.ts
git commit -m "feat(orb): manual tile picking and screen-rect projection"
```

---

### Task 9a: Manim previz of the focus choreography (gates Task 9's motion constants)

The spec carries an internal contradiction the implementation must not
inherit: it names both "dolly to 0.62 of the radius" and "tile subtends
~60% of viewport height", but at fov 60 with tile half-size 0.055 those
disagree — the on-screen full-height fraction is `f = 0.055 / (d * tan 30)`
where `d = 1 - DOLLY`, so DOLLY 0.62 gives f = 0.25 and f = 0.60 needs
DOLLY = 0.84. This task renders the candidate apexes as first-person motion
so the constant is chosen by eye before Task 9 hardcodes it. Discovery
task: nothing committed; deliverables are mp4s and a verdict.

**Files:**
- Create: `$SCRATCH/orb_previz.py` (scratchpad, NOT committed)

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: the chosen `DOLLY` value and confirmation (or revision) of
  `DUR.reveal` (0.6s) + dim 0.25 — Task 9 copies these into `scene.ts`.

- [ ] **Step 1: Invoke the manim skill, then write the previz scene**

Invoke the `manimce-best-practices` skill before writing manim code.
Constraint from measured experience (memory: cairo static partition): the
cairo renderer bakes mobjects added before the first animated one into a
frozen background per play — everything that must move or dim in a play
must itself be animated in that play, and motion must be verified by
pixel-diffing frames, not by the render exiting 0.

`$SCRATCH/orb_previz.py`:

```python
"""First-person previz of the /orb focus zoom: tile grows to APEX of the
viewport height on the house ease while the wall dims to 0.25.
Colors from scripts.plot_assets per docs/assets/README.md."""
import os
import sys

import numpy as np
from manim import Scene, Square, Text, VGroup, config

sys.path.insert(0, "/Users/melocoton/Developer/ytk.feature-orb")
from scripts.plot_assets import BG, DIM, GOLD


def house(t: float) -> float:
    # CustomEase "0.25,0.1,0.25,1" from web/src/lib/motion.ts, sampled
    u = np.linspace(0, 1, 256)
    x = 3 * u * (1 - u) ** 2 * 0.25 + 3 * u**2 * (1 - u) * 0.25 + u**3
    y = 3 * u * (1 - u) ** 2 * 0.10 + 3 * u**2 * (1 - u) * 1.0 + u**3
    return float(np.interp(t, x, y))


class ApexBase(Scene):
    APEX = 0.60  # tile height as fraction of viewport height at zoom apex

    def construct(self):
        self.camera.background_color = BG
        gap = 1.15
        wall = VGroup(
            *[
                Square(0.62, fill_opacity=1, fill_color=DIM, stroke_width=0)
                .move_to([x * gap, y * gap, 0])
                for x in range(-4, 5)
                for y in range(-3, 4)
            ]
        )
        focus = wall[len(wall) // 2]
        focus.set_fill(GOLD)
        others = VGroup(*[t for t in wall if t is not focus])
        dolly = 1 - 0.055 / (self.APEX * np.tan(np.pi / 6))
        label = Text(f"apex {self.APEX:.0%}  dolly {dolly:.2f}", font_size=22)
        label.to_corner(np.array([-1, 1, 0]))
        self.add(wall, label)
        target_h = config.frame_height * self.APEX
        self.play(
            focus.animate.set(height=target_h),
            others.animate.set_opacity(0.25).scale(1.0 + self.APEX * 0.55),
            run_time=0.6,
            rate_func=house,
        )
        self.wait(0.4)
        self.play(
            focus.animate.set(height=0.62),
            others.animate.set_opacity(1.0).scale(1 / (1.0 + self.APEX * 0.55)),
            run_time=0.3,
            rate_func=house,
        )
        self.wait(0.2)


class Apex25(ApexBase):
    APEX = 0.25  # the spec's DOLLY=0.62 in disguise


class Apex40(ApexBase):
    APEX = 0.40


class Apex60(ApexBase):
    APEX = 0.60  # the spec's stated viewport fraction
```

- [ ] **Step 2: Render all three variants**

```bash
cd "$SCRATCH" && uv run --with manim manim -ql --media_dir "$SCRATCH/media" orb_previz.py Apex25 Apex40 Apex60
```
Expected: three mp4s under `$SCRATCH/media/videos/orb_previz/480p15/`.

- [ ] **Step 3: Verify motion by pixel-diff (a clean exit proves nothing)**

```bash
cd "$SCRATCH" && for v in Apex25 Apex40 Apex60; do
  f="media/videos/orb_previz/480p15/$v.mp4"
  ffmpeg -loglevel error -y -ss 0.05 -i "$f" -frames:v 1 "$v-a.png" -ss 0.45 -i "$f" -frames:v 1 "$v-b.png"
done && uv run --with pillow python -c "
from PIL import Image, ImageChops
for v in ('Apex25', 'Apex40', 'Apex60'):
    a, b = Image.open(f'{v}-a.png'), Image.open(f'{v}-b.png')
    bbox = ImageChops.difference(a, b).getbbox()
    print(v, 'moves' if bbox else 'STATIC - render is a frozen frame')
    assert bbox, v
"
```
Expected: three lines of `moves`. A STATIC result means the cairo baking
trap fired — fix the scene (everything that changes must be inside the
play) before proceeding.

- [ ] **Step 4: Watch and decide**

Send the three mp4s to the user with SendUserFile, naming each variant and
its implied DOLLY (Apex25 -> 0.62, Apex40 -> 0.76, Apex60 -> 0.84). State
a recommendation with a reason (judge: does the apex leave enough dimmed
context around the tile for the NoteViewer to visibly grow out of it, or
does the tile already fill the frame?). The chosen APEX fixes `DOLLY = 1 -
0.055 / (APEX * tan 30 deg)` in Task 9. If the user does not reply at this
checkpoint, proceed with Apex40 (DOLLY 0.76) as the middle reading of the
contradictory spec and flag it as provisional in the Task 9 commit message.

---

### Task 9: `web/src/lib/orb/scene.ts` — the sphere scene

**Files:**
- Create: `web/src/lib/orb/scene.ts`
- Test: `web/src/lib/orb/scene.test.ts`

**Interfaces:**
- Consumes: `buildAtlas`, `uvRect` (Task 6); `createControls` (Task 7);
  `pickTile`, `tileScreenRect` (Task 8); `OrbData`, `LayoutName` (Task 5);
  `gsap, DUR, reducedMotion` from `../motion`.
- Produces (route consumes):

```typescript
export type OrbHandle = {
  setLayout(name: LayoutName): void;
  setThemeFilter(th: number | null): void;
  focus(i: number): void;   // zoom to tile; fires onOpen(i, rect) at apex
  blur(): void;             // reverse the zoom after NoteViewer closes
  dispose(): void;
};
export function mountOrb(
  canvas: HTMLCanvasElement,
  data: OrbData,
  cb: { onHover(i: number | null): void; onOpen(i: number, rect: DOMRect): void },
): OrbHandle;
```

Behavior spec (from the design doc): fov 60 camera at origin; one draw call
(InstancedBufferGeometry, custom shader orienting each quad tangent to the
sphere, per-instance atlas UV + index); tile half-size 0.055 at radius 1
(near the ~4.5 deg cell radius); hover scale 1.06 via uniform; tap → zoom:
controls target tween to the tile's yaw/pitch + dolly along the tile
direction to the DOLLY chosen in Task 9a's previz, others dim to 0.25,
`DUR.reveal` on HOUSE ease (repo register — the spec's ~0.5s power2.inOut
maps here), then `onOpen` with the projected rect; `reducedMotion()` skips
straight to `onOpen`. Theme filter dims non-matching tiles to 0.15. Drag
suppresses hover and tap. Before writing code: read Task 9a's verdict and
set `DOLLY` accordingly; also carry any constants revised by Task 7's
Step 0 spring simulation.

- [ ] **Step 1: Write the failing test**

```typescript
import { expect, test, vi } from "vitest";
import type { OrbData } from "../../api/orb";
import { mountOrb } from "./scene";

function data(): OrbData {
  return {
    points: [
      { p: "a.md", t: "a", c: "youtube", th: 0, thumb: null },
      { p: "b.md", t: "b", c: "instagram", th: 1, thumb: null },
      { p: "c.md", t: "c", c: "web", th: 0, thumb: null },
    ],
    themes: ["one", "two"],
    sphere: {
      radial: [[0, 0, -1], [1, 0, 0], [0, 1, 0]],
      haversine: null,
      lattice: [[0, 0, 1], [0, -1, 0], [-1, 0, 0]],
      scores: {},
      chosen: "radial",
    },
  };
}

test("mounts, renders one instanced draw, disposes clean", async () => {
  const canvas = document.createElement("canvas");
  canvas.width = 400;
  canvas.height = 300;
  document.body.appendChild(canvas);
  const handle = mountOrb(canvas, data(), { onHover: vi.fn(), onOpen: vi.fn() });
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  handle.setLayout("lattice"); // must not throw; haversine absent is a no-op guard
  handle.setLayout("haversine");
  handle.dispose();
  canvas.remove();
});

test("focus fires onOpen with a viewport rect (reduced motion path)", async () => {
  window.matchMedia = vi.fn().mockReturnValue({ matches: true }) as never; // reducedMotion
  const canvas = document.createElement("canvas");
  canvas.width = 400;
  canvas.height = 300;
  document.body.appendChild(canvas);
  const onOpen = vi.fn();
  const handle = mountOrb(canvas, data(), { onHover: vi.fn(), onOpen });
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  handle.focus(0);
  await vi.waitFor(() => expect(onOpen).toHaveBeenCalled());
  const [i, rect] = onOpen.mock.calls[0];
  expect(i).toBe(0);
  expect(rect.width).toBeGreaterThan(0);
  handle.dispose();
  canvas.remove();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && vp exec vitest run src/lib/orb/scene.test.ts`
Expected: FAIL — cannot resolve `./scene`.

- [ ] **Step 3: Implement `web/src/lib/orb/scene.ts`**

```typescript
import {
  DoubleSide,
  GLSL3,
  InstancedBufferAttribute,
  InstancedBufferGeometry,
  Mesh,
  PerspectiveCamera,
  PlaneGeometry,
  RawShaderMaterial,
  Scene,
  Vector3,
  WebGLRenderer,
} from "three";
import { DUR, gsap, reducedMotion } from "../motion";
import type { LayoutName, OrbData } from "../../api/orb";
import { buildAtlas, uvRect } from "./atlas";
import { createControls } from "./controls";
import { pickTile, tileScreenRect } from "./pick";

export const TILE_HALF = 0.055; // ~4.5deg cell radius at 505 tiles
// From Task 9a's previz verdict: DOLLY = 1 - 0.055/(APEX * tan 30deg).
// 0.76 is the Apex40 default; replace with the user's chosen apex.
const DOLLY = 0.76;
const DIM_FOCUS = 0.25;
const DIM_FILTER = 0.15;

const VERT = /* glsl */ `
precision highp float;
in vec3 position;
in vec2 uv;
in vec3 iPos;   // tile center on the unit sphere
in vec3 iUv;    // atlas u, v, span
in float iIdx;
uniform mat4 modelViewMatrix, projectionMatrix;
uniform float uHovered, uHoverScale;
out vec2 vUv;
out float vIdx;
void main() {
  vec3 n = normalize(-iPos); // tiles face the origin
  vec3 ref = abs(n.y) > 0.9 ? vec3(1.0, 0.0, 0.0) : vec3(0.0, 1.0, 0.0);
  vec3 e1 = normalize(cross(ref, n));
  vec3 e2 = cross(n, e1);
  float s = (abs(iIdx - uHovered) < 0.5) ? uHoverScale : 1.0;
  vec3 world = iPos + (e1 * position.x + e2 * position.y) * s;
  vUv = vec2(iUv.x + uv.x * iUv.z, iUv.y + uv.y * iUv.z);
  vIdx = iIdx;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(world, 1.0);
}`;

const FRAG = /* glsl */ `
precision highp float;
uniform sampler2D uAtlas;
uniform float uFocused, uDim;      // focus dimming: everyone but uFocused
uniform float uTheme, uThemeDim;   // theme filter dim factor
in vec2 vUv;
in float vIdx;
uniform float uThemes[1024];       // per-instance theme id, uploaded once
out vec4 outColor;
void main() {
  vec3 c = texture(uAtlas, vUv).rgb;
  float dim = 1.0;
  if (uFocused >= 0.0 && abs(vIdx - uFocused) >= 0.5) dim *= uDim;
  if (uTheme >= 0.0 && abs(uThemes[int(vIdx)] - uTheme) >= 0.5) dim *= uThemeDim;
  outColor = vec4(c * dim, 1.0);
}`;

export type OrbHandle = {
  setLayout(name: LayoutName): void;
  setThemeFilter(th: number | null): void;
  focus(i: number): void;
  blur(): void;
  dispose(): void;
};

export function mountOrb(
  canvas: HTMLCanvasElement,
  data: OrbData,
  cb: { onHover(i: number | null): void; onOpen(i: number, rect: DOMRect): void },
): OrbHandle {
  const n = data.points.length;
  const renderer = new WebGLRenderer({ canvas, antialias: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  const camera = new PerspectiveCamera(60, canvas.clientWidth / Math.max(1, canvas.clientHeight), 0.01, 10);
  const scene = new Scene();
  const atlas = buildAtlas(data.points, data.themes.length, () => {});

  const centers = new Float32Array(n * 3);
  const writeLayout = (name: LayoutName) => {
    const arr = data.sphere[name] ?? data.sphere[data.sphere.chosen];
    if (!arr) return;
    for (let i = 0; i < n; i++) centers.set(arr[i], i * 3);
  };
  writeLayout(data.sphere.chosen);

  const plane = new PlaneGeometry(TILE_HALF * 2, TILE_HALF * 2);
  const geo = new InstancedBufferGeometry();
  geo.index = plane.index;
  geo.setAttribute("position", plane.getAttribute("position"));
  geo.setAttribute("uv", plane.getAttribute("uv"));
  const iPos = new InstancedBufferAttribute(centers, 3);
  geo.setAttribute("iPos", iPos);
  const uvs = new Float32Array(n * 3);
  data.points.forEach((_, i) => {
    const r = uvRect(i);
    uvs.set([r.u, r.v, r.s], i * 3);
  });
  geo.setAttribute("iUv", new InstancedBufferAttribute(uvs, 3));
  geo.setAttribute("iIdx", new InstancedBufferAttribute(Float32Array.from({ length: n }, (_, i) => i), 1));
  geo.instanceCount = n;

  const themeArr = new Float32Array(1024).fill(-1);
  data.points.forEach((p, i) => { themeArr[i] = p.th; });
  const material = new RawShaderMaterial({
    glslVersion: GLSL3,
    vertexShader: VERT,
    fragmentShader: FRAG,
    side: DoubleSide,
    uniforms: {
      uAtlas: { value: atlas.texture },
      uHovered: { value: -1 }, uHoverScale: { value: 1.06 },
      uFocused: { value: -1 }, uDim: { value: 1 },
      uTheme: { value: -1 }, uThemeDim: { value: DIM_FILTER },
      uThemes: { value: themeArr },
    },
  });
  scene.add(new Mesh(geo, material));

  const controls = createControls();
  const zoom = { dolly: 0 }; // 0 at rest, 1 at apex
  let focused = -1;
  let hovered: number | null = null;
  let pointerNdc: [number, number] | null = null;
  const dir = new Vector3();

  const onDown = (e: PointerEvent) => { canvas.setPointerCapture(e.pointerId); controls.down(e.clientX, e.clientY); };
  const onMove = (e: PointerEvent) => {
    const r = canvas.getBoundingClientRect();
    pointerNdc = [((e.clientX - r.left) / r.width) * 2 - 1, -(((e.clientY - r.top) / r.height) * 2 - 1)];
    controls.move(e.clientX, e.clientY);
  };
  const onUp = (e: PointerEvent) => {
    const { tap } = controls.up();
    if (tap && hovered !== null && focused < 0) focusTile(hovered);
    canvas.releasePointerCapture(e.pointerId);
  };
  const onWheel = (e: WheelEvent) => controls.wheel(e.deltaY);
  canvas.addEventListener("pointerdown", onDown);
  canvas.addEventListener("pointermove", onMove);
  canvas.addEventListener("pointerup", onUp);
  canvas.addEventListener("wheel", onWheel, { passive: true });

  const apexRect = (i: number) => {
    dir.set(centers[i * 3], centers[i * 3 + 1], centers[i * 3 + 2]);
    return tileScreenRect(camera, dir.clone(), TILE_HALF, canvas.clientWidth, canvas.clientHeight);
  };

  function focusTile(i: number) {
    focused = i;
    material.uniforms.uFocused.value = i;
    const x = centers[i * 3], y = centers[i * 3 + 1], z = centers[i * 3 + 2];
    const yaw = Math.atan2(x, -z); // camera looks down -Z at yaw 0
    const pitch = Math.asin(y);
    if (reducedMotion()) {
      controls.setTarget(yaw, pitch);
      zoom.dolly = 1;
      material.uniforms.uDim.value = DIM_FOCUS;
      // one frame so the camera pose lands before projecting
      requestAnimationFrame(() => requestAnimationFrame(() => cb.onOpen(i, apexRect(i))));
      return;
    }
    controls.setTarget(yaw, pitch);
    gsap.to(zoom, { dolly: 1, duration: DUR.reveal, onComplete: () => cb.onOpen(i, apexRect(i)) });
    gsap.to(material.uniforms.uDim, { value: DIM_FOCUS, duration: DUR.reveal });
  }

  let raf = 0;
  let last = performance.now();
  const loop = (now: number) => {
    raf = requestAnimationFrame(loop);
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    const { yaw, pitch } = controls.step(dt);
    // orbit-from-origin: camera rotates in place, dollies toward the focused tile
    camera.position.set(0, 0, 0);
    if (focused >= 0 && zoom.dolly > 0) {
      dir.set(centers[focused * 3], centers[focused * 3 + 1], centers[focused * 3 + 2]);
      camera.position.addScaledVector(dir, zoom.dolly * DOLLY);
    }
    camera.rotation.set(0, 0, 0);
    camera.rotateY(-yaw);
    camera.rotateX(pitch);
    camera.updateMatrixWorld();
    if (!controls.dragging && focused < 0 && pointerNdc) {
      const hit = pickTile(pointerNdc[0], pointerNdc[1], camera, centers, TILE_HALF);
      if (hit !== hovered) { hovered = hit; material.uniforms.uHovered.value = hit ?? -1; cb.onHover(hit); }
    }
    renderer.render(scene, camera);
  };
  raf = requestAnimationFrame(loop);

  const resize = new ResizeObserver(() => {
    const w = canvas.clientWidth, h = Math.max(1, canvas.clientHeight);
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  });
  resize.observe(canvas);

  return {
    setLayout(name) {
      writeLayout(name);
      iPos.needsUpdate = true;
    },
    setThemeFilter(th) { material.uniforms.uTheme.value = th ?? -1; },
    focus: focusTile,
    blur() {
      const done = () => { focused = -1; material.uniforms.uFocused.value = -1; };
      if (reducedMotion()) { zoom.dolly = 0; material.uniforms.uDim.value = 1; done(); return; }
      gsap.to(zoom, { dolly: 0, duration: DUR.morph, onComplete: done });
      gsap.to(material.uniforms.uDim, { value: 1, duration: DUR.morph });
    },
    dispose() {
      cancelAnimationFrame(raf);
      resize.disconnect();
      canvas.removeEventListener("pointerdown", onDown);
      canvas.removeEventListener("pointermove", onMove);
      canvas.removeEventListener("pointerup", onUp);
      canvas.removeEventListener("wheel", onWheel);
      gsap.killTweensOf(zoom);
      gsap.killTweensOf(material.uniforms.uDim);
      plane.dispose();
      geo.dispose();
      material.dispose();
      atlas.dispose();
      renderer.dispose();
    },
  };
}
```

Note (amended in review): the original `uThemes` 1024-float uniform array was
DISPROVED — GLSL ES packs it as 1024 vec4 registers against a WebGL2
guaranteed minimum of 224, and three.js swallows the link failure into
console.error, so the failure mode on real GPUs is a silently empty scene.
Theme identity ships as a per-instance `iTheme` attribute instead (same
plumbing as `iIdx`), and instance count clamps to the atlas ceiling
(`COLS * COLS`) with a loud console.warn when points are dropped.

- [ ] **Step 4: Run test**

Run: `cd web && vp exec vitest run src/lib/orb/scene.test.ts`
Expected: PASS. If WebGL2 context creation fails in headless Chromium,
report it — do NOT mock the renderer; the repo's convention is real-browser
tests and Chromium ships SwiftShader.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/orb/scene.ts web/src/lib/orb/scene.test.ts
git commit -m "feat(orb): instanced sphere scene — one draw call, hover, zoom, dispose"
```

---

### Task 10: `/orb` route, nav link, NoteViewer handoff

**Files:**
- Create: `web/src/routes/orb.tsx`
- Create: `web/src/lib/orb/note.ts` and `web/src/lib/orb/note.test.ts`
- Modify: `web/src/routes/__root.tsx` (one nav link after the `/map` link,
  lines ~35-37)

**Interfaces:**
- Consumes: `useOrb`, `OrbData`, `OrbPoint`, `LayoutName` (Task 5);
  `mountOrb`, `OrbHandle` (Task 9); `NoteViewer` (existing — props `{ note:
  FreshNote; onClose: () => void; originRect?: DOMRect | undefined }`);
  `FreshNote` from `../api/fresh`.
- Produces: the user-facing route.

- [ ] **Step 1: Write the failing test for the FreshNote bridge**

```typescript
import { expect, test } from "vitest";
import type { OrbPoint } from "../../api/orb";
import { orbPointToFreshNote } from "./note";

test("maps an orb point onto the NoteViewer contract", () => {
  const p: OrbPoint = {
    p: "second-brain/sources/youtube/some-video.md",
    t: "Some Video", c: "youtube", u: "https://youtu.be/x", d: "2026-01-02",
    th: 3, thumb: "sources/youtube/thumbnails/x-thumb.jpg",
  };
  const note = orbPointToFreshNote(p);
  expect(note.path).toBe(p.p);
  expect(note.stem).toBe("some-video");
  expect(note.title).toBe("Some Video");
  expect(note.source).toBe("youtube");
  expect(note.url).toBe("https://youtu.be/x");
  expect(note.thumbnail).toBe(p.thumb);
  expect(note.tags).toEqual([]);
});

test("nulls stay null and stem survives odd paths", () => {
  const note = orbPointToFreshNote({ p: "a.md", t: "a", c: "web", th: -1 });
  expect(note.stem).toBe("a");
  expect(note.url).toBeNull();
  expect(note.date).toBeNull();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && vp exec vitest run src/lib/orb/note.test.ts`
Expected: FAIL — cannot resolve `./note`.

- [ ] **Step 3: Implement `web/src/lib/orb/note.ts`**

```typescript
import type { FreshNote } from "../../api/fresh";
import type { OrbPoint } from "../../api/orb";

/* NoteViewer's real key is note.path (useNote/useSimilarNotes); the rest of
   FreshNote is display fallback. Tags and has_take are absent from map data
   and default empty — the viewer fetches full content by path anyway. */
export function orbPointToFreshNote(p: OrbPoint): FreshNote {
  const base = p.p.split("/").pop() ?? p.p;
  return {
    path: p.p,
    stem: base.replace(/\.md$/, ""),
    title: p.t,
    url: p.u ?? null,
    source: p.c,
    date: p.d ?? null,
    added: p.d ?? "",
    thumbnail: p.thumb ?? null,
    tags: [],
    has_take: false,
  };
}
```

- [ ] **Step 4: Run test, then implement the route**

Run: `cd web && vp exec vitest run src/lib/orb/note.test.ts` — PASS first.

`web/src/routes/orb.tsx` (Tailwind only, controls in-page, no styles.css):

```tsx
import { useEffect, useRef, useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import type { LayoutName } from "../api/orb";
import { useOrb } from "../api/orb";
import { NoteViewer } from "../components/NoteViewer";
import { ErrorState } from "../components/StateViews";
import type { OrbHandle } from "../lib/orb/scene";
import { mountOrb } from "../lib/orb/scene";
import { orbPointToFreshNote } from "../lib/orb/note";

export const Route = createFileRoute("/orb")({ component: OrbPage });

const LAYOUTS: LayoutName[] = ["radial", "haversine", "lattice"];

function OrbPage() {
  const orb = useOrb();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const handleRef = useRef<OrbHandle | null>(null);
  const [layout, setLayout] = useState<LayoutName | null>(null);
  const [theme, setTheme] = useState<number | null>(null);
  const [hovered, setHovered] = useState<number | null>(null);
  const [open, setOpen] = useState<{ i: number; rect: DOMRect } | null>(null);
  const data = orb.data;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !data) return;
    const handle = mountOrb(canvas, data, {
      onHover: setHovered,
      onOpen: (i, rect) => setOpen({ i, rect }),
    });
    handleRef.current = handle;
    setLayout(data.sphere.chosen);
    return () => {
      handleRef.current = null;
      handle.dispose();
    };
  }, [data]);

  if (orb.isError) return <ErrorState error={orb.error} onRetry={() => void orb.refetch()} />;

  const scores = data?.sphere.scores;
  return (
    {/* amended in review: --nav-h exists nowhere and nav height is not a
        nameable constant (#134) — full-bleed routes fill via the
        .hub-outlet flex column, as .map-page does */}
    <div className="relative flex-1 min-h-0 overflow-hidden">
      <canvas ref={canvasRef} className="h-full w-full cursor-grab active:cursor-grabbing" />
      {data ? (
        <div className="absolute left-4 top-4 flex flex-col gap-2 text-xs">
          <div className="flex gap-1">
            {LAYOUTS.map((name) => {
              const missing = name === "haversine" && !data.sphere.haversine;
              const s = scores?.[name];
              return (
                <button
                  key={name}
                  type="button"
                  disabled={missing}
                  title={s ? `trust ${s.trustworthiness.toFixed(3)} overlap ${(100 * s.overlap_frac).toFixed(1)}%` : "unavailable"}
                  className={`rounded px-2 py-1 ${layout === name ? "bg-white/20" : "bg-white/5 hover:bg-white/10"} disabled:opacity-30`}
                  onClick={() => {
                    setLayout(name);
                    handleRef.current?.setLayout(name);
                  }}
                >
                  {name}
                </button>
              );
            })}
          </div>
          <select
            className="rounded bg-white/5 px-2 py-1"
            value={theme ?? ""}
            onChange={(e) => {
              const v = e.target.value === "" ? null : Number(e.target.value);
              setTheme(v);
              handleRef.current?.setThemeFilter(v);
            }}
          >
            <option value="">all themes</option>
            {data.themes.map((label, i) => (
              <option key={label} value={i}>{label}</option>
            ))}
          </select>
        </div>
      ) : null}
      {data && hovered !== null && !open ? (
        <div className="pointer-events-none absolute bottom-4 left-1/2 -translate-x-1/2 rounded bg-black/60 px-3 py-1 text-sm">
          {data.points[hovered].t}
          {data.points[hovered].d ? <span className="ml-2 opacity-60">{data.points[hovered].d}</span> : null}
        </div>
      ) : null}
      {data && open ? (
        <NoteViewer
          note={orbPointToFreshNote(data.points[open.i])}
          originRect={open.rect}
          onClose={() => {
            setOpen(null);
            handleRef.current?.blur();
          }}
        />
      ) : null}
    </div>
  );
}
```

- [ ] **Step 5: Add the nav link**

In `web/src/routes/__root.tsx`, after the `/map` Link (lines ~35-37), insert
exactly the neighbouring pattern:

```tsx
          <Link to="/orb" activeProps={{ className: "active" }}>
            orb
          </Link>
```

- [ ] **Step 6: Typecheck, lint, run the orb suites**

```bash
cd web && pnpm exec tsc -b && vp lint && vp exec vitest run src/lib/orb src/api/orb.test.ts
```
Expected: clean. The route registers itself in `routeTree.gen.ts` on the
next `vp dev`/`vp build` — do not hand-edit that file; if tsc complains
about the missing route type, run `vp build` once to regenerate.

- [ ] **Step 7: Commit**

```bash
git add web/src/routes/orb.tsx web/src/routes/__root.tsx web/src/lib/orb/note.ts web/src/lib/orb/note.test.ts web/src/routeTree.gen.ts
git commit -m "feat(orb): /orb route — sphere gallery with NoteViewer handoff"
```

---

### Task 11: Integration QA against the real hub

**Files:** none created (verification only; screenshots to scratchpad).

**Interfaces:**
- Consumes: everything. This task decides whether the branch is ready for
  the user's review.

- [ ] **Step 1: Data pass**

`just chroma-status`, then `uv run python scripts/build_map.py --attach-sphere`
(idempotent if Task 3 already ran it; refreshes after any interim ingests —
if it aborts on drift, run the full rebuild ONLY with user go, it costs
minutes and calls Haiku).
Verify: `python3 -c "import json,pathlib; d=json.load((pathlib.Path.home()/'.ytk'/'map.json').open()); s=d['content']['sphere']; print(s['chosen'], {k:v['trustworthiness'] for k,v in s['scores'].items()})"`

- [ ] **Step 2: Full frontend gate**

```bash
cd web && pnpm exec tsc -b && vp lint && vp exec vitest run
```
Expected: clean — the whole web suite, not just orb (Card/NoteViewer tests
guard the handoff contract). Python side:
`uv run pytest tests/test_spheremap.py tests/test_spheremap_attach.py tests/ui/test_orb_api.py -v`.

- [ ] **Step 3: Serve the branch build**

```bash
just build-web
```
Then start the source hub in a visible tmux pane (list panes first, per
using-tmux; do NOT touch the launchd hub):
`uv run uvicorn ytk.ui.server:app --port 8877`
The source server prefers `web/dist` when no packaged webdist exists — verify
`curl -s http://127.0.0.1:8877/api/orb | head -c 200` returns points.

- [ ] **Step 4: Headless visual check**

Puppeteer MCP, headless from the first navigate. Screenshot:
1. `http://127.0.0.1:8877/orb` at 1280x800 — expect a tile wall, in-page
   layout buttons top-left, no nav-bar controls.
2. Flip to each available layout via clicks; screenshot each. Radial should
   show visible clumping; lattice should be even — if they look identical,
   the layout switch is broken.
3. Click a center tile; screenshot after ~1s — expect NoteViewer open over
   a dimmed, zoomed sphere.
Save all screenshots under the scratchpad; send them to the user with
SendUserFile.

- [ ] **Step 5: Report, do not merge**

Summarize: score table, chosen layout, screenshot verdicts, any deviation
from the spec. Leave the worktree branch committed and pushed nowhere; the
user reviews and gives the merge go explicitly.

---

## Self-review notes (already applied)

- Spec coverage: layouts+scoring (T2), map.json attach+thumb (T3), /api/orb
  (T4), client (T5), atlas (T6), controls incl. wheel (T7), pick+rect (T8),
  scene incl. hover/zoom/dim/dispose (T9), route+nav+theme filter+NoteViewer
  handoff (T10), QA incl. layout-flip eyeball (T11). Haversine-verified-first
  is T1. Reduced-motion path covered in T9 code and test.
- Visual checkpoints: Mollweide plot in the T1 spike, three-layout
  comparison on real data in T3, spring simulation before the TS port in
  T7 Step 0, manim first-person previz of the zoom in T9a (chooses DOLLY),
  headless screenshots in T11. Every checkpoint is read/watched and
  verdicted, and its artifact goes to the user via SendUserFile.
- Spec deviations, deliberate: zoom uses the house ease register
  (`DUR.reveal`, 0.6s) instead of the spec's ~0.5s power2.inOut — repo
  convention wins; overlap threshold is the equal-area formula (~4.5 deg at
  505) rather than the spec's ~4.2 approximation. Both flagged for review.
- Spec contradiction found while planning, resolved by measurement: the
  spec's "dolly to 0.62" and "tile subtends ~60% of viewport height"
  disagree (0.62 -> 25% height at fov 60, tile half 0.055; 60% needs
  0.84). T9a renders the candidates and the eye decides; the plan defaults
  to the middle reading (Apex40, DOLLY 0.76) if the checkpoint goes
  unanswered.
- Types consistent across tasks: `OrbPoint{p,t,c,u,d,th,thumb}` (T4 JSON =
  T5 type), `uvRect{u,v,s}` (T6 = T9 usage), `createControls` surface (T7 =
  T9 usage), `OrbHandle` (T9 = T10 usage), `FreshNote` bridge fields match
  `web/src/api/fresh.ts`.
