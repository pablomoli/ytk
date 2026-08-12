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
