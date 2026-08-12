# /galaxy MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A new hub route `/galaxy` where the 18 theme planets hang as coast-textured worlds on the E32 shell; the camera flies planet to planet; moons/rings/spin render only where E33's gates passed; galaxy data attaches to `map.json` at every build.

**Architecture:** Python side: `ytk/coast.py` (organic-field primitives + texture bake) and `ytk/galaxy.py` (arm-A block, ring/spin/moon gates, member-set-hash cache) feed a new `attach_galaxy()` in `scripts/build_map.py`; `ytk/ui/server.py` serves `/api/galaxy` + `/galaxy-tex/`. Web side: `web/src/lib/palette.ts` mirrors the matplotlib house palette; `web/src/lib/galaxy/` holds pure math, picking, and the three.js scene; `web/src/routes/galaxy.tsx` is the page; `orb.tsx` gains a `?theme=` search param for the dive-through.

**Tech Stack:** Python 3.13 / numpy / scipy / FastAPI / Pillow; three.js RawShaderMaterial (GLSL3) / gsap / TanStack Router / vitest in real Chromium (`vp exec vitest run`).

**Spec:** `docs/superpowers/specs/2026-08-12-galaxy-view-design.md` (committed). E32 record: `docs/assets/32-galaxy/`; E33 record: `docs/assets/33-channels/`.

## Global Constraints

- `GALAXY_K = 3.0` deg per n^(1/3); `TEX_W, TEX_H = 512, 256`; superplanet `1024x512`. Renderer consumes `radius_deg` verbatim (sync contract with `docs/assets/32-galaxy/galaxy.json`).
- Sudarsky classes (from `scripts/e31_theme_planets.py`, verbatim): V >= 0.50 hue `#ffb08a`, IV >= 0.30 `#8a5a3a`, III >= 0.15 `#5a8cff`, II >= 0.05 `#cfe0f0`, I else `#e0cfa0`; activity = share of dated members within 90 days.
- Palette mirror values (from `scripts/plot_assets.py`): BG `#08080a`, PANEL `#000000`, FRAME `#2e2e36`, TEXT `#eceae7`, MUTED `#9a968f`, GOLD `#f2b950`, DIM `#3a3a42`; punch gamma `0.72`; saturation rule `0.3 + 0.7 * norm(cohesion)` normalized over the 18-planet population. Sync-contract comments required on BOTH sides (`plot_assets.py` gains one pointing at `palette.ts`).
- No emojis anywhere. Code comments 1-2 lines, constraints only; narrative goes in commit messages.
- CSS: Tailwind utilities against existing tokens only. Zero new rules in `styles.css` or route CSS (budget ratchet enforces this). Page controls render in-page, never in the nav bar (nav takes exactly one new `<Link>`).
- No new frontend dependencies. Reuse `three`, `gsap` via `../motion` (`DUR`, `gsap`, `reducedMotion`), TanStack Router, `lib/orb/controls.ts`, `normalizeWheelDelta` from `lib/orb/scene.ts`.
- Python tests: narrowest pytest selection per task (`uv run --extra dev pytest tests/test_x.py -q`); full gates only on explicit request (16GB machine, parallel sessions). Frontend tests: `cd web && vp exec vitest run src/path/x.test.ts`.
- Git: commit after every task on `feature/galaxy-view` (this worktree). `git -C` with absolute paths, never `cd X && git`. Never merge — merge happens only on the user's explicit go via `wt merge`.
- All numerics that mirror the E-series must cite their source in a 1-line comment (e.g. `# E33 gate: docs/assets/33-channels/`).

## File Structure

- Create `ytk/coast.py` — perlin/fBm, softmin metaballs, area-pinned level, ocean radius, equirect field grid, per-planet + superplanet bake (pure numpy + Pillow write).
- Create `ytk/galaxy.py` — `classify()`, `galaxy_block()`, `ring_gate()`, `spin_gate()`, `moon_gate()`, `member_hash()`, `attach_payload()` (assembles the whole `content.galaxy` value).
- Create `tests/test_coast_bake.py`, `tests/test_galaxy_block.py`, `tests/test_galaxy_gates.py`, `tests/test_galaxy_attach.py`, `tests/test_galaxy_api.py`.
- Modify `scripts/build_map.py` — `attach_galaxy()` + `--no-galaxy` flag + main() call.
- Modify `ytk/ui/server.py` — `GET /api/galaxy`, `GET /galaxy-tex/{name}`.
- Create `web/src/lib/palette.ts` + `web/src/lib/palette.test.ts`.
- Create `web/src/api/galaxy.ts` (types + `useGalaxy`).
- Create `web/src/lib/galaxy/math.ts` + `math.test.ts` (pure: spin rate, world radius, ring normal, standoff, equirect uv).
- Create `web/src/lib/galaxy/pick.ts` + `pick.test.ts` (ray-sphere planet pick).
- Create `web/src/lib/galaxy/scene.ts` + `scene.test.ts` (mount/dispose, meshes, shader, travel).
- Create `web/src/routes/galaxy.tsx`; modify `web/src/routes/__root.tsx` (one link), `web/src/routes/orb.tsx` (`?theme=` search param).

---

### Task 1: `ytk/coast.py` — organic-field primitives and the per-planet bake

**Files:**
- Create: `ytk/coast.py`
- Test: `tests/test_coast_bake.py`

**Interfaces:**
- Consumes: `ytk.spheremap.fibonacci`, `radial`, `spread` (already in repo).
- Produces:
  - `grid(nlon: int = 512, nlat: int = 256) -> tuple[ll, tt, xyz]` — lon/lat mesh (radians) and unit vectors, shapes `(nlat, nlon)` and `(nlat, nlon, 3)`; lon spans `-pi..pi` inclusive so column 0 and column -1 are the same direction.
  - `fbm(xyz, seed, octaves=6, base=4, lacunarity=2.0, gain=0.5) -> ndarray` — ported verbatim from `scripts/e30b_fbm.py` (`_perlin3` + `fbm`, lines 33-73).
  - `softmin_field(xyz, pos, beta) -> ndarray` and `level_for_area(field, tt, target) -> float` — ported verbatim from `scripts/e30b_organic_coast.py`.
  - `ocean_radius(lattice: ndarray) -> float` — ported from `scripts/e30_coastlines.py` (p99 of fibonacci-probe gaps, `N_PROBES = 8192`).
  - `organic_sd(pos, xyz, tt, coast_deg) -> ndarray` — signed distance in degrees: softmin metaballs over a domain warped by 3-octave vector fBm plus 6-octave fBm roughness, shifted by `level_for_area` so land area equals the hard-rule area at `coast_deg` (composition copied from `organic_field()` + the `sd = field - level_for_area(...)` line in `scripts/e30_coastlines.py:main`, seeds 30/31 kept).
  - `bake_planet(member_c3: ndarray, out_path: Path) -> dict` — slice-arm positions `spread(radial(member_c3))`, `coast_deg = ocean_radius(fibonacci(len(pos)))`, field on `grid()`, texel `clamp(0.5 - sd / (5 * coast_deg), 0, 1)` written as 8-bit grayscale PNG via Pillow; returns `{"coast_deg": float, "land_frac": float}`.
  - `bake_superplanet(radial_pos: ndarray, lattice_pos: ndarray, out_path: Path) -> dict` — same, `grid(1024, 512)`, `coast_deg = ocean_radius(lattice_pos)`.
  - Texel semantics (the shader contract): `0.5` is the shoreline, `> 0.5` land (1.0 = deepest inland at `2.5 * coast_deg`), `< 0.5` ocean.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_coast_bake.py
import numpy as np
import pytest
from pathlib import Path

from ytk import coast
from ytk.spheremap import fibonacci


def _cluster(n: int, seed: int = 7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.normal([1.0, 0.2, -0.1], 0.3, (n, 3))


def test_grid_shapes_and_seam():
    ll, tt, xyz = coast.grid()
    assert ll.shape == tt.shape == (256, 512)
    assert xyz.shape == (256, 512, 3)
    # lon endpoints are the same direction: the baked seam must be continuous
    np.testing.assert_allclose(xyz[:, 0, :], xyz[:, -1, :], atol=1e-9)


def test_organic_sd_pins_land_area():
    ll, tt, xyz = coast.grid()
    pos = fibonacci(40)
    coast_deg = coast.ocean_radius(fibonacci(40))
    sd = coast.organic_sd(pos, xyz, tt, coast_deg)
    w = np.cos(tt)
    land = (w * (sd < 0)).sum() / w.sum()
    dist = np.degrees(np.arccos(np.clip(xyz @ pos.T, -1, 1))).min(axis=-1)
    target = (w * (dist < coast_deg)).sum() / w.sum()
    assert land == pytest.approx(target, abs=0.02)


def test_bake_planet_writes_texture(tmp_path: Path):
    out = tmp_path / "5.png"
    meta = coast.bake_planet(_cluster(30), out)
    from PIL import Image

    img = np.asarray(Image.open(out))
    assert img.shape == (256, 512)
    assert img.dtype == np.uint8
    # both land and sea present, and the seam columns agree
    assert (img > 140).any() and (img < 110).any()
    np.testing.assert_array_equal(img[:, 0], img[:, -1])
    assert 0 < meta["land_frac"] < 1 and meta["coast_deg"] > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_coast_bake.py -q`
Expected: FAIL — `ModuleNotFoundError: ytk.coast` (or ImportError).

- [ ] **Step 3: Implement `ytk/coast.py`**

Port the named functions from their `scripts/` sources verbatim (they are the committed record; `ytk/coast.py` is the production home — same precedent as `spread()` into `spheremap.py`). Module docstring states exactly that plus the texel contract. `bake_planet`:

```python
def bake_planet(member_c3, out_path):
    from PIL import Image

    pos = spread(radial(np.asarray(member_c3, dtype=float)))
    coast_deg = ocean_radius(fibonacci(len(pos)))
    ll, tt, xyz = grid()
    sd = organic_sd(pos, xyz, tt, coast_deg)
    texel = np.clip(0.5 - sd / (5.0 * coast_deg), 0.0, 1.0)
    texel[:, -1] = texel[:, 0]  # identical directions; guard float drift
    Image.fromarray((texel * 255).astype(np.uint8), mode="L").save(out_path)
    w = np.cos(tt)
    return {
        "coast_deg": float(coast_deg),
        "land_frac": float((w * (sd < 0)).sum() / w.sum()),
    }
```

Check `pyproject.toml`: `scipy` and `pillow` must be runtime deps (build_map imports this at build time). Add whichever is missing to `[project] dependencies` — check first, `umap-learn` is already there.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_coast_bake.py -q`
Expected: 3 passed (~30-60s; the organic field on the full grid is the cost).

- [ ] **Step 5: Commit**

```bash
git -C /Users/melocoton/Developer/ytk.feature-galaxy-view add ytk/coast.py tests/test_coast_bake.py pyproject.toml
git -C /Users/melocoton/Developer/ytk.feature-galaxy-view commit -m "feat(galaxy): coast primitives + per-planet texture bake in ytk/coast.py"
```

---

### Task 2: `ytk/galaxy.py` — classes, arm-A block, member hash

**Files:**
- Create: `ytk/galaxy.py`
- Test: `tests/test_galaxy_block.py`

**Interfaces:**
- Consumes: nothing beyond numpy + stdlib.
- Produces:
  - `GALAXY_K = 3.0` (module constant; comment cites `docs/assets/32-galaxy/`).
  - `CLASSES` + `classify(activity: float) -> tuple[cls, cls_label, hue]` — ported verbatim from `scripts/e31_theme_planets.py` (thresholds in Global Constraints).
  - `member_hash(paths: list[str], epoch: str) -> str` — sha256 hex of `epoch + "\n" + "\n".join(sorted(paths)) + f"\nK={GALAXY_K}\nv1"`; the cache key for moons and textures.
  - `galaxy_block(c3, themes, dates, labels, paths) -> list[dict]` — per theme id >= 0 sorted: `{"theme", "label", "n", "activity", "date_coverage", "median_age_days" (None if no dates), "cohesion_placeholder"— NO: cohesion needs vectors; galaxy_block takes `vecs` too}`.

  Exact signature: `galaxy_block(vecs, c3, themes, dates, labels, paths, today=None) -> list[dict]` where each dict is
  `{"theme": int, "label": str, "n": int, "activity": float, "date_coverage": float, "median_age_days": float | None, "cohesion": float, "cls": str, "cls_label": str, "hue": str, "radius_deg": float, "pos": [x, y, z], "member_paths": [str], "hash": str}`
  with `pos` = unit direction of the theme's mean c3 from the mean of ALL content c3 (E32 arm A), `radius_deg = GALAXY_K * n ** (1/3)`, `today` injectable for tests.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_galaxy_block.py
import datetime

import numpy as np
import pytest

from ytk import galaxy


def _fixture():
    rng = np.random.default_rng(3)
    c3 = np.concatenate([rng.normal([2, 0, 0], 0.2, (8, 3)), rng.normal([-2, 1, 0], 0.2, (5, 3))])
    vecs = np.concatenate([rng.normal(0, 1, (8, 16)), rng.normal(3, 1, (5, 16))])
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    themes = np.array([0] * 8 + [1] * 5)
    dates = ["2026-08-01"] * 8 + ["2024-01-01"] * 4 + [None]
    paths = [f"n{i}.md" for i in range(13)]
    return vecs, c3, themes, dates, ["alpha", "beta"], paths


def test_block_positions_and_radii():
    vecs, c3, themes, dates, labels, paths = _fixture()
    today = datetime.date(2026, 8, 12)
    block = galaxy.galaxy_block(vecs, c3, themes, dates, labels, paths, today=today)
    assert [p["theme"] for p in block] == [0, 1]
    a = block[0]
    np.testing.assert_allclose(np.linalg.norm(a["pos"]), 1.0, atol=1e-6)
    assert a["radius_deg"] == pytest.approx(galaxy.GALAXY_K * 8 ** (1 / 3))
    # theme 0 all dated within 90d -> class V; theme 1 all old -> class I
    assert a["cls"] == "V" and block[1]["cls"] == "I"
    assert block[1]["date_coverage"] == pytest.approx(4 / 5)
    assert a["median_age_days"] == pytest.approx(11)


def test_member_hash_stable_and_sensitive():
    h1 = galaxy.member_hash(["b.md", "a.md"], "v2")
    assert h1 == galaxy.member_hash(["a.md", "b.md"], "v2")
    assert h1 != galaxy.member_hash(["a.md"], "v2")
    assert h1 != galaxy.member_hash(["a.md", "b.md"], "v3")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_galaxy_block.py -q`
Expected: FAIL — module/function missing.

- [ ] **Step 3: Implement**

Module docstring: "Production home of the E32/E33 galaxy machinery; the experiments in scripts/ are the committed record." `galaxy_block` mirrors `all_planets()` from `scripts/e32_galaxy.py` but takes data as arguments (no map.json reads), adds `median_age_days` (median over dated members, None when zero dated) and `member_paths`/`hash`. Cohesion = mean cosine of unit member vecs to their unit mean (E31 rule).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_galaxy_block.py -q`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git -C /Users/melocoton/Developer/ytk.feature-galaxy-view add ytk/galaxy.py tests/test_galaxy_block.py
git -C /Users/melocoton/Developer/ytk.feature-galaxy-view commit -m "feat(galaxy): arm-A block, Sudarsky classes, member-set hash"
```

---

### Task 3: `ytk/galaxy.py` — ring and spin gates

**Files:**
- Modify: `ytk/galaxy.py`
- Test: `tests/test_galaxy_gates.py`

**Interfaces:**
- Produces:
  - `ring_gate(vecs, themes, ids, seed=433, knn=10, n_perm=1000) -> dict[int, dict]` — ported from `ring_stats()` in `scripts/e33_channels.py` (the corrected pair-excess gate: per-planet max-z over label permutations, bar = 99th of permuted max-z; partners = pairs with z > bar, top 3). Payload per theme: `{"max_z", "z_bar", "earned", "partners": [{"theme", "count", "z"}]}`. Drop the reported-only share_gate from the production payload.
  - `spin_gate(themes, dates, ids, seed=533, n_perm=1000) -> dict[int, dict]` — ported from `spin_stats()`: `{"median_age_days", "n_dated", "null_lo", "null_hi", "earned", "side"}` (two-sided 2.5/97.5, permutes ages preserving dated counts).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_galaxy_gates.py
import numpy as np

from ytk import galaxy


def test_ring_gate_finds_planted_partner():
    rng = np.random.default_rng(11)
    # theme 0 and 1 interleaved in one tight cloud (strong cross links);
    # theme 2 far away and self-contained
    a = rng.normal([5, 0, 0, 0], 0.05, (30, 4))
    b = rng.normal([5, 0.02, 0, 0], 0.05, (30, 4))
    c = rng.normal([-5, 0, 0, 0], 0.05, (30, 4))
    vecs = np.concatenate([a, b, c])
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    themes = np.array([0] * 30 + [1] * 30 + [2] * 30)
    out = galaxy.ring_gate(vecs, themes, [0, 1, 2], n_perm=300)
    assert out[0]["earned"] and out[0]["partners"][0]["theme"] == 1
    assert not out[2]["earned"]


def test_spin_gate_two_sided():
    rng = np.random.default_rng(5)
    themes = np.array([0] * 40 + [1] * 40 + [2] * 40)
    import datetime

    today = datetime.date(2026, 8, 12)
    mk = lambda days: (today - datetime.timedelta(days=int(days))).isoformat()
    dates = (
        [mk(d) for d in rng.integers(1, 10, 40)]          # theme 0: very fresh
        + [mk(d) for d in rng.integers(700, 900, 40)]     # theme 1: dormant
        + [mk(d) for d in rng.integers(1, 900, 40)]       # theme 2: mixed
    )
    out = galaxy.spin_gate(themes, dates, [0, 1, 2], n_perm=300)
    assert out[0]["earned"] and out[0]["side"] == "fast"
    assert out[1]["earned"] and out[1]["side"] == "dormant"
    assert not out[2]["earned"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_galaxy_gates.py -q`
Expected: FAIL — functions missing.

- [ ] **Step 3: Implement**

Port from `scripts/e33_channels.py::ring_stats` and `spin_stats`, parameterizing `n_perm`/`knn` and taking `today` from `datetime.date.today()` inside `spin_gate` (dates arrive as ISO strings; skip Nones). 1-line comment on each: `# E33 gate: docs/assets/33-channels/`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_galaxy_gates.py -q`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git -C /Users/melocoton/Developer/ytk.feature-galaxy-view add ytk/galaxy.py tests/test_galaxy_gates.py
git -C /Users/melocoton/Developer/ytk.feature-galaxy-view commit -m "feat(galaxy): ring and spin gates ported to production"
```

---

### Task 4: `ytk/galaxy.py` — moon gate with member-set cache

**Files:**
- Modify: `ytk/galaxy.py`
- Test: `tests/test_galaxy_moons.py` (new file; add to File Structure)

**Interfaces:**
- Produces:
  - `moon_gate(vn: ndarray, seed: int, n_boot=25, n_null=50) -> dict` — ported from `scripts/e33_channels.py` (`_coph`, `_triplets`, `_outliers`, `moon_stability`, `null_cloud`, `moon_cut`): `{"stability", "null_hi", "earned", "core_size", "moons": [{"member_idx": [int]}]}` where `member_idx` indexes INTO the passed array (caller maps to note paths).
  - `moons_cached(vn, member_paths, epoch, cache_path: Path, seed) -> dict` — wraps `moon_gate` with a JSON cache keyed by `member_hash(member_paths, epoch)`; on hit returns the stored result untouched.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_galaxy_moons.py
import json
import numpy as np

from ytk import galaxy


def _two_clusters(n_big=26, n_small=6, seed=9):
    rng = np.random.default_rng(seed)
    v = np.concatenate(
        [rng.normal([4, 0, 0, 0], 0.08, (n_big, 4)), rng.normal([0, 4, 0, 0], 0.08, (n_small, 4))]
    )
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def test_moon_gate_finds_planted_minority(tmp_path):
    out = galaxy.moon_gate(_two_clusters(), seed=1, n_boot=10, n_null=15)
    assert out["earned"]
    assert out["core_size"] == 26
    assert len(out["moons"]) == 1 and len(out["moons"][0]["member_idx"]) == 6


def test_unimodal_earns_nothing():
    rng = np.random.default_rng(2)
    v = rng.normal([4, 0, 0, 0], 0.3, (30, 4))
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    out = galaxy.moon_gate(v, seed=1, n_boot=10, n_null=15)
    assert not out["earned"] or not out["moons"]


def test_cache_hit_skips_compute(tmp_path, monkeypatch):
    vn = _two_clusters()
    paths = [f"p{i}.md" for i in range(len(vn))]
    cache = tmp_path / "cache.json"
    first = galaxy.moons_cached(vn, paths, "v2", cache, seed=1)
    calls = {"n": 0}
    real = galaxy.moon_gate
    monkeypatch.setattr(galaxy, "moon_gate", lambda *a, **k: calls.__setitem__("n", 1) or real(*a, **k))
    second = galaxy.moons_cached(vn, paths, "v2", cache, seed=1)
    assert calls["n"] == 0 and second == first
    assert galaxy.member_hash(paths, "v2") in json.loads(cache.read_text())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_galaxy_moons.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement**

Port the five helpers verbatim, parameterize `N_BOOT`/`N_NULL_MOON` as arguments (defaults 25/50). `moons_cached` reads/writes `{hash: result}` JSON (create parent dirs; tolerate a missing or corrupt file by recomputing).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_galaxy_moons.py -q`
Expected: 3 passed (planted-cluster gate takes ~20-40s).

- [ ] **Step 5: Commit**

```bash
git -C /Users/melocoton/Developer/ytk.feature-galaxy-view add ytk/galaxy.py tests/test_galaxy_moons.py
git -C /Users/melocoton/Developer/ytk.feature-galaxy-view commit -m "feat(galaxy): moon gate with member-set-hash cache"
```

---

### Task 5: `attach_galaxy()` in build_map + `--no-galaxy`

**Files:**
- Modify: `scripts/build_map.py` (new function + argparse flag + main() call; read the file first — follow `attach_terrain()`'s pattern of loading `~/.ytk/map.json`, mutating, writing back)
- Modify: `ytk/galaxy.py` (add `attach_payload()`)
- Test: `tests/test_galaxy_attach.py`

**Interfaces:**
- Consumes: Tasks 1-4 (`galaxy_block`, `ring_gate`, `spin_gate`, `moons_cached`, `bake_planet`, `bake_superplanet`, `member_hash`).
- Produces:
  - `galaxy.attach_payload(vecs, c3, themes, dates, labels, paths, thumbs, titles, radial_pos, lattice_pos, tex_dir: Path, cache_path: Path, epoch: str) -> dict` — the full `content.galaxy` value:
    ```
    {"epoch": str, "k_deg": 3.0, "generated": iso-date,
     "planets": [{...galaxy_block fields minus member_paths/hash,
                  "tex": "<theme>.png",
                  "rings": {"earned": bool, "partners": [{"theme", "z"}]},
                  "spin": {"earned": bool, "side": str|None, "median_age_days": float|None},
                  "moons": [{"size": int, "path": str, "title": str, "thumb": str|None}]}]}
    ```
    Moon exemplar = medoid member (max mean cosine within the moon); `path`/`title`/`thumb` come from the parallel per-point lists. Textures baked only when `member_hash` changed (store `{"hash": ..., "meta": ...}` per theme inside the same cache file, key `"tex:<theme-hash>"`); superplanet baked to `superplanet.png` keyed by hash of all content paths.
  - `build_map.attach_galaxy(no_galaxy: bool)` — loads map.json, rebuilds the per-point parallel arrays exactly as the sphere attach does (content points = those with `c3`), calls `attach_payload`, writes `data["content"]["galaxy"]`, saves. Wire `--no-galaxy` argparse flag; call after the sphere attach in `main()`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_galaxy_attach.py
import numpy as np
from pathlib import Path

from ytk import galaxy


def test_attach_payload_shape(tmp_path):
    rng = np.random.default_rng(4)
    n = 24
    vecs = rng.normal(0, 1, (n, 8))
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    c3 = np.concatenate([rng.normal([2, 0, 0], 0.3, (12, 3)), rng.normal([-2, 0, 0], 0.3, (12, 3))])
    themes = np.array([0] * 12 + [1] * 12)
    dates = ["2026-08-01"] * n
    paths = [f"notes/n{i}.md" for i in range(n)]
    thumbs = [f"thumbs/t{i}.jpg" for i in range(n)]
    titles = [f"note {i}" for i in range(n)]
    out = galaxy.attach_payload(
        vecs, c3, themes, dates, ["alpha", "beta"], paths, thumbs, titles,
        radial_pos=galaxy_radial(c3), lattice_pos=None,
        tex_dir=tmp_path / "tex", cache_path=tmp_path / "cache.json", epoch="v2",
        moon_boot=6, moon_null=8, n_perm=100,
    )
    assert out["k_deg"] == 3.0 and out["epoch"] == "v2"
    assert len(out["planets"]) == 2
    p = out["planets"][0]
    assert (tmp_path / "tex" / p["tex"]).exists()
    assert set(p) >= {"theme", "label", "n", "pos", "radius_deg", "cls", "hue",
                      "cohesion", "activity", "tex", "rings", "spin", "moons"}
    assert "member_paths" not in p and "hash" not in p


def galaxy_radial(c3):
    v = np.asarray(c3, float) - np.asarray(c3, float).mean(axis=0)
    return v / np.linalg.norm(v, axis=1, keepdims=True)
```

(Superplanet bake: when `lattice_pos is None`, skip it — the real build passes the sphere block's lattice; the test exercises the skip path. Expose `moon_boot`/`moon_null`/`n_perm` kwargs so tests stay fast.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev pytest tests/test_galaxy_attach.py -q`
Expected: FAIL — `attach_payload` missing.

- [ ] **Step 3: Implement `attach_payload`, then wire `attach_galaxy` + flag into build_map**

`attach_galaxy` mirrors the sphere-attach data path in `scripts/build_map.py` (read it; content points are `[p for p in data["points"] if "c3" in p]`, vectors via `load_points()` + `_content_alignment` with the url-match fallback). `radial_pos` = the sphere block's `radial`, `lattice_pos` = its `lattice`. Textures to `Path.home()/".ytk"/"galaxy_tex"`, cache `Path.home()/".ytk"/"galaxy-cache.json"`.

- [ ] **Step 4: Run the new test plus the build_map consumer suite**

Run: `uv run --extra dev pytest tests/test_galaxy_attach.py tests/test_build_map_assemble.py -q`
Expected: all pass (consumer suite still green — SDD covering-tests rule).

- [ ] **Step 5: Commit**

```bash
git -C /Users/melocoton/Developer/ytk.feature-galaxy-view add ytk/galaxy.py scripts/build_map.py tests/test_galaxy_attach.py
git -C /Users/melocoton/Developer/ytk.feature-galaxy-view commit -m "feat(galaxy): attach content.galaxy at map build, textures + cache keyed by member set"
```

---

### Task 6: server — `/api/galaxy` + `/galaxy-tex/{name}`

**Files:**
- Modify: `ytk/ui/server.py` (add next to `orb_api`, line ~1017; follow its exact style)
- Test: `tests/test_galaxy_api.py`

**Interfaces:**
- Consumes: `content.galaxy` shape from Task 5.
- Produces:
  - `GET /api/galaxy` → the `content.galaxy` value verbatim; 404 `"No map built yet"` when map.json missing; 404 `"No galaxy block — run: uv run python scripts/build_map.py"` when the key is absent.
  - `GET /galaxy-tex/{name}` → PNG `FileResponse` from `~/.ytk/galaxy_tex/<name>`; reject names containing `/` or `..` with 404; 404 when missing. Module-level `_GALAXY_TEX_DIR = Path.home() / ".ytk" / "galaxy_tex"` so tests monkeypatch it (same pattern as `_ORB_MAP`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_galaxy_api.py
import json

from fastapi.testclient import TestClient

import ytk.ui.server as server


def _client(tmp_path, monkeypatch, block):
    m = tmp_path / "map.json"
    m.write_text(json.dumps({"points": [], "content": ({"galaxy": block} if block else {})}))
    monkeypatch.setattr(server, "_ORB_MAP", m)
    tex = tmp_path / "tex"
    tex.mkdir()
    (tex / "0.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    monkeypatch.setattr(server, "_GALAXY_TEX_DIR", tex)
    return TestClient(server.app)


def test_galaxy_api_serves_block(tmp_path, monkeypatch):
    block = {"epoch": "v2", "k_deg": 3.0, "planets": []}
    c = _client(tmp_path, monkeypatch, block)
    assert c.get("/api/galaxy").json() == block


def test_galaxy_api_404_without_block(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch, None)
    r = c.get("/api/galaxy")
    assert r.status_code == 404 and "galaxy block" in r.json()["detail"]


def test_galaxy_tex_serves_and_guards(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch, {"planets": []})
    assert c.get("/galaxy-tex/0.png").status_code == 200
    assert c.get("/galaxy-tex/../secrets.png").status_code == 404
    assert c.get("/galaxy-tex/missing.png").status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_galaxy_api.py -q`
Expected: FAIL (404 route not found / attr missing).

- [ ] **Step 3: Implement the two endpoints**

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_galaxy_api.py -q`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git -C /Users/melocoton/Developer/ytk.feature-galaxy-view add ytk/ui/server.py tests/test_galaxy_api.py
git -C /Users/melocoton/Developer/ytk.feature-galaxy-view commit -m "feat(galaxy): /api/galaxy and /galaxy-tex endpoints"
```

---

### Task 7: `web/src/lib/palette.ts` — the record's palette, mirrored

**Files:**
- Create: `web/src/lib/palette.ts`, `web/src/lib/palette.test.ts`
- Modify: `scripts/plot_assets.py` (add the 1-line sync comment next to the color block: `# mirrored in web/src/lib/palette.ts — change both or change neither`)

**Interfaces:**
- Produces:
  ```ts
  export const BG = "#08080a"; export const PANEL = "#000000";
  export const FRAME = "#2e2e36"; export const TEXT = "#eceae7";
  export const MUTED = "#9a968f"; export const GOLD = "#f2b950";
  export const DIM = "#3a3a42";
  export const CLASS_HUES: Record<string, string>; // I..V per Global Constraints
  export const PUNCH_GAMMA = 0.72;
  export function punch(x: number): number;            // clamp01(x) ** PUNCH_GAMMA
  export function saturation(cohesion: number, lo: number, hi: number): number; // 0.3 + 0.7 * norm, guard hi === lo -> 1
  export function planetColor(hueHex: string, sat: number): [number, number, number]; // rgb 0..1: hue*sat + DIM*(1-sat), E31 gallery rule
  ```

- [ ] **Step 1: Write the failing test**

```ts
// web/src/lib/palette.test.ts
import { describe, expect, it } from "vitest";
import { BG, CLASS_HUES, DIM, GOLD, planetColor, punch, saturation } from "./palette";

describe("palette mirror", () => {
  it("carries the plot_assets constants", () => {
    expect(BG).toBe("#08080a");
    expect(GOLD).toBe("#f2b950");
    expect(DIM).toBe("#3a3a42");
    expect(CLASS_HUES.V).toBe("#ffb08a");
    expect(CLASS_HUES.III).toBe("#5a8cff");
  });
  it("punch lifts dim values (gamma 0.72)", () => {
    expect(punch(0.17)).toBeCloseTo(0.17 ** 0.72, 10);
    expect(punch(-1)).toBe(0);
    expect(punch(2)).toBe(1);
  });
  it("saturation spans 0.3..1.0 over the population", () => {
    expect(saturation(0.2, 0.2, 0.8)).toBeCloseTo(0.3);
    expect(saturation(0.8, 0.2, 0.8)).toBeCloseTo(1.0);
    expect(saturation(0.5, 0.5, 0.5)).toBe(1.0);
  });
  it("planetColor mixes hue toward DIM as cohesion drops", () => {
    const full = planetColor("#ffb08a", 1.0);
    const low = planetColor("#ffb08a", 0.3);
    expect(full[0]).toBeCloseTo(0xff / 255, 5);
    expect(low[0]).toBeLessThan(full[0]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/melocoton/Developer/ytk.feature-galaxy-view/web && vp exec vitest run src/lib/palette.test.ts`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `palette.ts` + the plot_assets sync comment**

Header comment: `// Mirror of scripts/plot_assets.py's house palette + E31 gallery color rules — change both or change neither.`

- [ ] **Step 4: Run test to verify it passes**

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git -C /Users/melocoton/Developer/ytk.feature-galaxy-view add web/src/lib/palette.ts web/src/lib/palette.test.ts scripts/plot_assets.py
git -C /Users/melocoton/Developer/ytk.feature-galaxy-view commit -m "feat(galaxy): palette.ts mirrors the record's palette (sync contract)"
```

---

### Task 8: `web/src/lib/galaxy/math.ts` — pure geometry + `web/src/api/galaxy.ts`

**Files:**
- Create: `web/src/lib/galaxy/math.ts`, `web/src/lib/galaxy/math.test.ts`, `web/src/api/galaxy.ts`

**Interfaces:**
- Produces (`math.ts`; plain number[] triples, no three.js imports — keeps it unit-testable):
  ```ts
  export type V3 = [number, number, number];
  export const worldRadius = (radiusDeg: number) => Math.sin((radiusDeg * Math.PI) / 180);
  // seconds-per-rotation = clamp(medianAgeDays, 20, 600): a 24-day world turns in 24s, a 380-day world is near-still
  export const spinRadPerSec = (medianAgeDays: number | null, populationMedian: number) => number;
  export const equirectUv = (n: V3) => [u, v];  // u = atan2(n.y, n.x)/2pi + 0.5, v = 0.5 + asin(clamp(n.z))/pi — MUST match ytk/coast.py grid orientation
  export const ringNormal = (center: V3, partner: V3, tiltRad?: number) => V3; // default tilt 30deg from radial toward the partner's tangent component
  export const standoff = (center: V3, radiusDeg: number) => V3; // center * (1 + 3.2 * worldRadius): visit camera position
  export const slerp = (a: V3, b: V3, t: number) => V3; // unit-vector slerp for travel arcs (handle near-parallel with lerp+normalize)
  ```
- Produces (`api/galaxy.ts`, mirroring `api/orb.ts` style):
  ```ts
  export type GalaxyMoon = { size: number; path: string; title: string; thumb: string | null };
  export type GalaxyPlanet = {
    theme: number; label: string; n: number; activity: number; cohesion: number;
    cls: string; hue: string; pos: [number, number, number]; radius_deg: number;
    tex: string; median_age_days: number | null;
    rings: { earned: boolean; partners: { theme: number; z: number }[] };
    spin: { earned: boolean; side: string | null; median_age_days: number | null };
    moons: GalaxyMoon[];
  };
  export type GalaxyData = { epoch: string; k_deg: number; planets: GalaxyPlanet[] };
  export const useGalaxy = () => useQuery({ queryKey: ["galaxy"], queryFn: () => apiGet<GalaxyData>("/api/galaxy") });
  ```

- [ ] **Step 1: Write the failing tests**

```ts
// web/src/lib/galaxy/math.test.ts
import { describe, expect, it } from "vitest";
import { equirectUv, ringNormal, slerp, spinRadPerSec, standoff, worldRadius } from "./math";

const len = (v: number[]) => Math.hypot(...v);

describe("galaxy math", () => {
  it("worldRadius keeps angular size honest", () => {
    expect(worldRadius(12)).toBeCloseTo(Math.sin((12 * Math.PI) / 180));
  });
  it("spin clamps 20..600 s/rot and falls back to the population median", () => {
    expect(spinRadPerSec(24, 55)).toBeCloseTo((2 * Math.PI) / 24);
    expect(spinRadPerSec(5, 55)).toBeCloseTo((2 * Math.PI) / 20);
    expect(spinRadPerSec(900, 55)).toBeCloseTo((2 * Math.PI) / 600);
    expect(spinRadPerSec(null, 55)).toBeCloseTo((2 * Math.PI) / 55);
  });
  it("equirectUv matches the bake orientation", () => {
    expect(equirectUv([1, 0, 0])).toEqual([0.5, 0.5]);       // lon 0, lat 0
    expect(equirectUv([0, 0, 1])[1]).toBeCloseTo(1.0);        // north pole -> top row
    expect(equirectUv([-1, 0, 0])[0]).toBeCloseTo(1.0);       // lon pi -> right edge
  });
  it("ringNormal tilts from radial toward the partner", () => {
    const n = ringNormal([1, 0, 0], [0, 1, 0]);
    expect(len(n)).toBeCloseTo(1);
    expect(n[0]).toBeCloseTo(Math.cos(Math.PI / 6));
    expect(n[1]).toBeCloseTo(Math.sin(Math.PI / 6));
  });
  it("standoff sits outside the planet along its radial", () => {
    const s = standoff([0, 0, 1], 12);
    expect(s[2]).toBeCloseTo(1 + 3.2 * worldRadius(12));
  });
  it("slerp stays on the unit sphere", () => {
    const m = slerp([1, 0, 0], [0, 1, 0], 0.5);
    expect(len(m)).toBeCloseTo(1);
    expect(m[0]).toBeCloseTo(m[1]);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail** — `cd web && vp exec vitest run src/lib/galaxy/math.test.ts` — FAIL.

- [ ] **Step 3: Implement `math.ts` and `api/galaxy.ts`** (api file has no test of its own; the route test in Task 11 consumes it).

- [ ] **Step 4: Run tests to verify they pass** — 6 passed.

- [ ] **Step 5: Commit**

```bash
git -C /Users/melocoton/Developer/ytk.feature-galaxy-view add web/src/lib/galaxy/math.ts web/src/lib/galaxy/math.test.ts web/src/api/galaxy.ts
git -C /Users/melocoton/Developer/ytk.feature-galaxy-view commit -m "feat(galaxy): pure scene math and the /api/galaxy client"
```

---

### Task 9: `web/src/lib/galaxy/pick.ts` — ray-sphere planet picking

**Files:**
- Create: `web/src/lib/galaxy/pick.ts`, `web/src/lib/galaxy/pick.test.ts`

**Interfaces:**
- Consumes: `worldRadius` from Task 8.
- Produces: `pickPlanet(ndcX, ndcY, camera: PerspectiveCamera, planets: {pos: V3; radius_deg: number}[]) -> number | null` — nearest ray-sphere intersection in front of the camera (standard quadratic; smallest positive t wins; no hit -> null). Import `PerspectiveCamera`/`Vector3`/`Raycaster` from three (pattern: `lib/orb/pick.ts`).

- [ ] **Step 1: Write the failing test**

```ts
// web/src/lib/galaxy/pick.test.ts
import { describe, expect, it } from "vitest";
import { PerspectiveCamera } from "three";
import { pickPlanet } from "./pick";

describe("pickPlanet", () => {
  const cam = new PerspectiveCamera(60, 1, 0.01, 10);
  cam.position.set(0, 0, 3);
  cam.lookAt(0, 0, 0);
  cam.updateMatrixWorld();
  const planets = [
    { pos: [0, 0, 1] as [number, number, number], radius_deg: 12 },
    { pos: [0, 0, -1] as [number, number, number], radius_deg: 12 },
  ];
  it("hits the near planet at screen center", () => {
    expect(pickPlanet(0, 0, cam, planets)).toBe(0);
  });
  it("misses off to the side", () => {
    expect(pickPlanet(0.95, 0.95, cam, planets)).toBeNull();
  });
});
```

- [ ] **Step 2: Run to verify FAIL** — `cd web && vp exec vitest run src/lib/galaxy/pick.test.ts`.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run to verify PASS** — 2 passed.
- [ ] **Step 5: Commit**

```bash
git -C /Users/melocoton/Developer/ytk.feature-galaxy-view add web/src/lib/galaxy/pick.ts web/src/lib/galaxy/pick.test.ts
git -C /Users/melocoton/Developer/ytk.feature-galaxy-view commit -m "feat(galaxy): ray-sphere planet picking"
```

---

### Task 10: `web/src/lib/galaxy/scene.ts` — the scene: worlds, paint, channels, travel

**Files:**
- Create: `web/src/lib/galaxy/scene.ts`, `web/src/lib/galaxy/scene.test.ts`

**Interfaces:**
- Consumes: Tasks 7-9; `createControls` from `../orb/controls`, `normalizeWheelDelta` from `../orb/scene`; `DUR, gsap, reducedMotion` from `../motion`; `GalaxyData` from `../../api/galaxy`.
- Produces:
  ```ts
  export type GalaxyHandle = {
    visit(theme: number): void;   // fly to a planet (travel arc if already visiting another)
    overview(): void;             // return to the constellation
    dispose(): void;
  };
  export type GalaxyCallbacks = {
    onHover(theme: number | null): void;
    onVisit(theme: number | null): void;                 // null = overview
    onMoonOpen(moon: { path: string; title: string }): void;
  };
  export function mountGalaxy(canvas: HTMLCanvasElement, data: GalaxyData, cb: GalaxyCallbacks): GalaxyHandle;
  ```
- Scene contents (all inside `mountGalaxy`):
  - Renderer/camera/ResizeObserver/pointer+wheel wiring copied from `mountOrb`'s shape (same dispose discipline: cancel rafs, kill tweens, dispose geometries/materials/renderer, remove listeners).
  - **Overview camera:** orb globe-mode semantics via `createControls()`: `r = 1.6 + zoom * (4.0 - 1.6)`, position `r * dir(yaw, pitch)`, lookAt origin.
  - **Visit camera:** gsap-tween a `flight = {t}` 0->1; position = `slerp(fromDir, toDir, t) * lerp(fromR, toR, t)` where `toDir/toR` come from `standoff(planet)`; lookAt the planet center. `reducedMotion()` jump-cuts.
  - **Planets:** per planet one `Mesh(SphereGeometry(worldRadius(radius_deg), 48, 24))` at `pos`, shared `RawShaderMaterial` cloned per planet with uniforms `{uField (Texture from /galaxy-tex/<tex>), uHue (vec3 planetColor), uSpin (float), uSeed (float theme), uCoastAmp (0.04)}`. Textures via `TextureLoader` with `LinearFilter`, `RepeatWrapping` on x only.
  - **Fragment shader** (GLSL3, mirrors the record's paint):
    ```glsl
    // equirect sample of the baked field; 0.5 = shoreline (ytk/coast.py contract)
    float lon = atan(vN.y, vN.x); float lat = asin(clamp(vN.z, -1.0, 1.0));
    vec2 uv = vec2(lon / 6.28318530718 + 0.5 + uSpin, 0.5 + lat / 3.14159265359);
    float d = texture(uField, uv).r + uCoastAmp * (fbm3(vN * 9.0 + uSeed) - 0.5);
    float land = smoothstep(0.5, 0.505, d);
    float depth = pow(clamp((d - 0.5) * 2.0, 0.0, 1.0), 0.72);   // punch, gamma from palette
    vec3 landCol = uHue * (0.35 + 0.65 * depth);
    vec3 seaCol = uHue * 0.08 * clamp(d * 2.0, 0.0, 1.0);
    float shore = smoothstep(0.012, 0.0, abs(d - 0.5)) * 0.35;   // faint TEXT-ish accent
    outColor = vec4(mix(seaCol, landCol, land) + vec3(0.93, 0.92, 0.9) * shore, 1.0);
    ```
    with `fbm3` = 3-octave hash-based value noise (implement in the shader; ~15 lines, standard `fract(sin(dot))` hash). Vertex shader passes the object-space normal as `vN`.
  - **Spin:** per frame `uSpin += spinRadPerSec(median_age_days, populationMedian) / (2 * PI) * dt` (uv offset is in turns). `reducedMotion()` freezes it.
  - **Rings:** for earned planets, `Mesh(RingGeometry(1.25 * R, 1.32 * R, 64))`, `MeshBasicMaterial({color: TEXT, transparent: true, opacity: 0.35, side: DoubleSide})`, oriented so its plane normal = `ringNormal(pos, partnerPos)` (three: `mesh.lookAt(normal added to position)`).
  - **Moons:** for planets with moons, one `Mesh(PlaneGeometry)` billboard per moon, `MeshBasicMaterial` with a `TextureLoader` texture from `/vault-media/<thumb>` (skip texture when `thumb` null — PANEL-colored quad), half-size `R * (0.18 + 0.02 * min(size, 10))`, orbiting in the planet's tangent plane at `1.6 * R`, period 45s, always facing the camera (`mesh.quaternion.copy(camera.quaternion)` each frame). Click (via `pickPlanet`-style ray against moon quads' bounding spheres — reuse `Raycaster.intersectObjects`) -> `cb.onMoonOpen`.
  - **Starfield:** `Points` of 600 fibonacci directions at radius 8, `PointsMaterial({color: DIM, size: 0.02})`, `frustumCulled = false`.
  - **Hover:** when not visiting, per-frame `pickPlanet` under the pointer -> `cb.onHover`; tap -> `visit(theme)`.
  - Background: `renderer.setClearColor(BG)`.

- [ ] **Step 1: Write the failing test**

```ts
// web/src/lib/galaxy/scene.test.ts
import { describe, expect, it, vi } from "vitest";
import { mountGalaxy } from "./scene";
import type { GalaxyData } from "../../api/galaxy";

const data: GalaxyData = {
  epoch: "v2",
  k_deg: 3,
  planets: [0, 1].map((i) => ({
    theme: i, label: `p${i}`, n: 20, activity: 0.5, cohesion: 0.6,
    cls: "V", hue: "#ffb08a", pos: i ? [0, 1, 0] : [1, 0, 0], radius_deg: 8,
    tex: `${i}.png`, median_age_days: 40,
    rings: { earned: i === 0, partners: i === 0 ? [{ theme: 1, z: 5 }] : [] },
    spin: { earned: false, side: null, median_age_days: 40 },
    moons: [],
  })),
};

describe("mountGalaxy", () => {
  it("mounts, reports hover/visit, and disposes clean", () => {
    const canvas = document.createElement("canvas");
    Object.defineProperty(canvas, "clientWidth", { value: 640 });
    Object.defineProperty(canvas, "clientHeight", { value: 480 });
    const cb = { onHover: vi.fn(), onVisit: vi.fn(), onMoonOpen: vi.fn() };
    const handle = mountGalaxy(canvas, data, cb);
    handle.visit(1);
    expect(cb.onVisit).toHaveBeenCalledWith(1);
    handle.overview();
    expect(cb.onVisit).toHaveBeenCalledWith(null);
    handle.dispose(); // must not throw, must cancel the raf loop
  });
});
```

(Real Chromium: WebGL context exists. Texture loads 404 in the test server — `TextureLoader` failures must be non-fatal by design: planet renders with `uField` bound to a 1x1 fallback `DataTexture` until load.)

- [ ] **Step 2: Run to verify FAIL** — `cd web && vp exec vitest run src/lib/galaxy/scene.test.ts`.
- [ ] **Step 3: Implement the scene.**
- [ ] **Step 4: Run scene + consumer suites** — `vp exec vitest run src/lib/galaxy/ src/lib/palette.test.ts` — all pass.
- [ ] **Step 5: Commit**

```bash
git -C /Users/melocoton/Developer/ytk.feature-galaxy-view add web/src/lib/galaxy/scene.ts web/src/lib/galaxy/scene.test.ts
git -C /Users/melocoton/Developer/ytk.feature-galaxy-view commit -m "feat(galaxy): the scene — coast-painted worlds, channels, travel"
```

---

### Task 11: route `/galaxy`, nav link, orb `?theme=` param

**Files:**
- Create: `web/src/routes/galaxy.tsx`
- Modify: `web/src/routes/__root.tsx` (one `<Link to="/galaxy">galaxy</Link>` after the orb link; update the nav comment's link count)
- Modify: `web/src/routes/orb.tsx` (validateSearch + apply)
- Test: extend `web/src/lib/galaxy/scene.test.ts`? No — route behavior test: `web/src/routes/orb-theme-param.test.ts` is overkill for a param read; instead assert the pure validator: create `web/src/routes/orbSearch.ts` with `export const validateOrbSearch = (s: Record<string, unknown>) => (typeof s.theme === "number" && Number.isInteger(s.theme) && s.theme >= 0 ? { theme: s.theme } : {});` + `web/src/routes/orbSearch.test.ts`.

**Interfaces:**
- Consumes: `useGalaxy`, `mountGalaxy`, `NoteViewer` (opened for moon exemplars via the same `orbPointToFreshNote`-style minimal note: `{p: path, t: title}` — read `lib/orb/note.ts` and pass what `NoteViewer` needs), `ErrorState`, `useChromeVisible`.
- Produces: the page. Layout mirrors `orb.tsx`: full-bleed canvas; when chrome visible, a top-left in-page control cluster (Tailwind, `text-xs`) showing: current state ("overview" or the visited planet's label + class + n + activity), an "overview" button while visiting, ring-partner buttons (each `visit(partner)`), and a "land" button navigating `useNavigate()({ to: "/orb", search: { theme } })`. Hover caption bar at bottom center exactly like orb's. Moon click -> NoteViewer.

- [ ] **Step 1: Write the failing validator test**

```ts
// web/src/routes/orbSearch.test.ts
import { describe, expect, it } from "vitest";
import { validateOrbSearch } from "./orbSearch";

describe("orb search param", () => {
  it("accepts a non-negative integer theme", () => {
    expect(validateOrbSearch({ theme: 3 })).toEqual({ theme: 3 });
  });
  it("drops junk", () => {
    expect(validateOrbSearch({ theme: "3" })).toEqual({});
    expect(validateOrbSearch({ theme: -1 })).toEqual({});
    expect(validateOrbSearch({})).toEqual({});
  });
});
```

- [ ] **Step 2: Run to verify FAIL**, then implement `orbSearch.ts`, wire into `orb.tsx` (`validateSearch: validateOrbSearch`; in the mount effect, after `setLayout(...)`: `const th = Route.useSearch().theme` read at component level, and if defined `setTheme(th); handle.setThemeFilter(th)`), build `galaxy.tsx`, add the nav link.

- [ ] **Step 3: Run validator test + full web suite** — `cd web && vp exec vitest run` — all green (routeTree regenerates on dev/build; run `vp build` once so `routeTree.gen.ts` includes `/galaxy` and typecheck sees it).

- [ ] **Step 4: Typecheck + lint gate for the frontend slice** — `cd web && vp exec tsc --noEmit` (or `just typecheck` if RAM allows; narrowest first).

- [ ] **Step 5: Commit**

```bash
git -C /Users/melocoton/Developer/ytk.feature-galaxy-view add web/src/routes/galaxy.tsx web/src/routes/orbSearch.ts web/src/routes/orbSearch.test.ts web/src/routes/orb.tsx web/src/routes/__root.tsx web/src/routeTree.gen.ts
git -C /Users/melocoton/Developer/ytk.feature-galaxy-view commit -m "feat(galaxy): /galaxy route, nav link, orb theme deep-link"
```

---

### Task 12: orb globe coastline layer (superplanet ocean sphere)

**Files:**
- Modify: `web/src/lib/orb/scene.ts` (add an optional coast sphere), `web/src/api/orb.ts` (no change to types needed — texture probed directly), `web/src/lib/orb/scene.test.ts` (extend)

**Interfaces:**
- Consumes: `/galaxy-tex/superplanet.png` (404 when never baked), the Task 10 fragment shader (reuse the same GLSL source string — export it from `lib/galaxy/scene.ts` as `PLANET_FRAG` so both scenes import one copy; GOLD hue at low saturation for the superplanet: `planetColor(GOLD, 0.55)`).
- Produces: in `mountOrb`, a `SphereGeometry(0.985, 64, 32)` mesh under the tiles, visible only in globe mode (`setView` toggles `coast.visible`), material = the shared shader with `uSpin` fixed 0, texture loaded lazily; on 404 the mesh simply never becomes visible (load callback gates it). Dispose with everything else.

- [ ] **Step 1: Extend the orb scene test**

```ts
// append to web/src/lib/orb/scene.test.ts — follow the file's existing mount fixture
it("globe mode toggles the coast sphere without leaking", () => {
  const { handle, scene } = mountFixture(); // reuse the file's existing helper for mounting
  handle.setView("globe");
  handle.setView("inside");
  handle.dispose();
});
```

(Read the existing test file first and reuse its fixture names — this step's snippet is the shape, the file's own helpers are the source of truth for setup. The real assertion: dispose after mode flips throws nothing and the added mesh's material/geometry are disposed — spy on `dispose` if the fixture exposes the scene.)

- [ ] **Step 2: FAIL** (setView untouched by coast yet — write the visibility assertion so it fails), **Step 3: implement**, **Step 4: run** `cd web && vp exec vitest run src/lib/orb/scene.test.ts` green plus `src/lib/galaxy/` still green.

- [ ] **Step 5: Commit**

```bash
git -C /Users/melocoton/Developer/ytk.feature-galaxy-view add web/src/lib/orb/scene.ts web/src/lib/orb/scene.test.ts web/src/lib/galaxy/scene.ts
git -C /Users/melocoton/Developer/ytk.feature-galaxy-view commit -m "feat(galaxy): superplanet coastline sphere under the globe tiles"
```

---

### Task 13: end-to-end — real build, live hub, pixel-proved motion

**Files:** none created (verification task; fixes land wherever the failure is)

- [ ] **Step 1: Attach for real** — `uv run python scripts/build_map.py` in the worktree (full rebuild + galaxy attach; moon gate cold ~2-4 min; confirm `content.galaxy` present: `python3 -c "import json,os;d=json.load(open(os.path.expanduser('~/.ytk/map.json')));print(len(d['content']['galaxy']['planets']), 'planets')"` and `ls ~/.ytk/galaxy_tex/` shows 18+1 PNGs).
- [ ] **Step 2: Build + run the hub from the worktree** — `just build-web`, then `just ui` in a visible tmux pane (list panes first; do NOT touch the user's installed hub at :6969).
- [ ] **Step 3: Headless screenshots** (Zen user — never open a browser): puppeteer headless from the first navigate against the dev hub's `/galaxy`: overview frame, then two frames 2s apart while visiting the fastest-spinning planet, then two frames mid-travel between two planets.
- [ ] **Step 4: Pixel-diff proof** — PIL `ImageChops.difference(...).getbbox()` non-None for the spin pair AND the travel pair; overview vs visit frames differ. A frozen pair fails the task (house rule: motion is proven by pixels, never exit codes).
- [ ] **Step 5: Send the user the overview + visit screenshots** (SendUserFile), fix anything broken, commit fixes.

```bash
git -C /Users/melocoton/Developer/ytk.feature-galaxy-view add -A
git -C /Users/melocoton/Developer/ytk.feature-galaxy-view commit -m "fix(galaxy): live-verification fixes"
```

- [ ] **Step 6: Full gate, RAM permitting** — check `memory_pressure` first; if >30% free run `just check` in the worktree; otherwise run the task-touched suites only and note the deferral.

---

## Execution notes for the dispatcher

- Tasks 1-4 are Python-sequential (same module); Tasks 7-9 are web-parallel with each other and with 5-6. Task 10 needs 7-9; Task 11 needs 8+10; Task 12 needs 10; Task 13 needs everything.
- Subagent model split: implementer subagents inherit the session model (these tasks are not mechanical); reviewer subagents likewise. No haiku here.
- Do not merge. On completion: report, leave the worktree clean and pushed (`wt step push` or `git push -u origin feature/galaxy-view`), wait for the user's merge go.
