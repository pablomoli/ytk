import numpy as np

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
        vecs,
        c3,
        themes,
        dates,
        ["alpha", "beta"],
        paths,
        thumbs,
        titles,
        radial_pos=galaxy_radial(c3),
        lattice_pos=None,
        tex_dir=tmp_path / "tex",
        cache_path=tmp_path / "cache.json",
        epoch="v2",
        moon_boot=6,
        moon_null=8,
        n_perm=100,
    )
    assert out["k_deg"] == 3.0 and out["epoch"] == "v2"
    assert len(out["planets"]) == 2
    p = out["planets"][0]
    assert (tmp_path / "tex" / p["tex"]).exists()
    assert set(p) >= {
        "theme",
        "label",
        "n",
        "pos",
        "radius_deg",
        "cls",
        "hue",
        "cohesion",
        "activity",
        "tex",
        "rings",
        "spin",
        "moons",
    }
    assert "member_paths" not in p and "hash" not in p


def galaxy_radial(c3):
    v = np.asarray(c3, float) - np.asarray(c3, float).mean(axis=0)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def test_attach_payload_normalizes_vecs_before_ring_gate(tmp_path, monkeypatch):
    """ring_gate's v @ v.T assumes unit vectors; a caller handing attach_payload
    raw (non-unit) embeddings must get the same rings a normalized caller
    would, not a magnitude-biased nearest-neighbor set. Spies on ring_gate to
    (a) prove the array it actually receives is unit-norm regardless of what
    attach_payload was handed, and (b) prove the full rings statistics --
    not just the coarse earned/partners view a small fixture may leave
    unchanged -- are identical whether the caller normalized first or not."""
    rng = np.random.default_rng(11)
    n = 24
    vecs = rng.normal(0, 1, (n, 8))
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    c3 = np.concatenate([rng.normal([2, 0, 0], 0.3, (12, 3)), rng.normal([-2, 0, 0], 0.3, (12, 3))])
    themes = np.array([0] * 12 + [1] * 12)
    dates = ["2026-08-01"] * n
    paths = [f"notes/n{i}.md" for i in range(n)]
    thumbs = [f"thumbs/t{i}.jpg" for i in range(n)]
    titles = [f"note {i}" for i in range(n)]
    # mixed per-row magnitudes, direction unchanged -- a caller passing raw
    # (non-unit) store embeddings, which is the real production shape
    scale = rng.uniform(0.2, 5.0, size=(n, 1))
    scaled_vecs = vecs * scale

    real_ring_gate = galaxy.ring_gate
    seen: list[tuple[np.ndarray, dict]] = []

    def spy_ring_gate(vecs_arg, *a, **k):
        result = real_ring_gate(vecs_arg, *a, **k)
        seen.append((np.linalg.norm(vecs_arg, axis=1).copy(), result))
        return result

    monkeypatch.setattr(galaxy, "ring_gate", spy_ring_gate)

    def run(v, tag):
        return galaxy.attach_payload(
            v,
            c3,
            themes,
            dates,
            ["alpha", "beta"],
            paths,
            thumbs,
            titles,
            radial_pos=galaxy_radial(c3),
            lattice_pos=None,
            tex_dir=tmp_path / f"tex_{tag}",
            cache_path=tmp_path / f"cache_{tag}.json",
            epoch="v2",
            moon_boot=6,
            moon_null=8,
            n_perm=100,
        )

    out_unit = run(vecs, "unit")
    out_scaled = run(scaled_vecs, "scaled")

    assert len(seen) == 2
    norms_unit, ring_result_unit = seen[0]
    norms_scaled, ring_result_scaled = seen[1]
    assert np.allclose(norms_unit, 1.0)
    assert np.allclose(norms_scaled, 1.0), "attach_payload must normalize vecs before ring_gate"
    for t in ring_result_unit:
        assert ring_result_unit[t]["max_z"] == ring_result_scaled[t]["max_z"]
        assert ring_result_unit[t]["earned"] == ring_result_scaled[t]["earned"]

    rings_unit = [p["rings"] for p in out_unit["planets"]]
    rings_scaled = [p["rings"] for p in out_scaled["planets"]]
    assert rings_unit == rings_scaled


def test_bake_cached_rebakes_on_filename_mismatch_or_missing_file(tmp_path):
    """Theme ids are rebuild-scoped: a reshuffle can leave a member-set hash
    that already has a cache entry, but pointing at a filename from a prior
    build's theme id. A cache hit must require the entry's stored filename to
    match the caller's current expected name AND the file to still exist."""
    cache_path = tmp_path / "cache.json"
    tex_dir = tmp_path / "tex"
    tex_dir.mkdir()
    calls = {"n": 0}

    def bake_0():
        calls["n"] += 1
        (tex_dir / "0.png").write_bytes(b"first")
        return {"coast_deg": 1.0}

    galaxy._bake_cached(cache_path, "abc123", "0.png", tex_dir / "0.png", bake_0)
    assert calls["n"] == 1
    assert (tex_dir / "0.png").read_bytes() == b"first"

    # same hash, same expected name, file untouched -> real cache hit
    galaxy._bake_cached(cache_path, "abc123", "0.png", tex_dir / "0.png", bake_0)
    assert calls["n"] == 1

    # same hash, but a theme-id reshuffle now expects "5.png" -- the cached
    # entry still says "0.png", so this must be treated as a miss
    def bake_5():
        calls["n"] += 1
        (tex_dir / "5.png").write_bytes(b"second")
        return {"coast_deg": 1.0}

    galaxy._bake_cached(cache_path, "abc123", "5.png", tex_dir / "5.png", bake_5)
    assert calls["n"] == 2
    assert (tex_dir / "5.png").read_bytes() == b"second"

    # deleting the file for an otherwise-current hash+name entry also forces
    # a rebake -- the cache entry alone is not proof the file is on disk
    (tex_dir / "5.png").unlink()
    galaxy._bake_cached(cache_path, "abc123", "5.png", tex_dir / "5.png", bake_5)
    assert calls["n"] == 3
    assert (tex_dir / "5.png").exists()
