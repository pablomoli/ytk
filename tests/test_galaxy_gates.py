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
        [mk(d) for d in rng.integers(1, 10, 40)]  # theme 0: very fresh
        + [mk(d) for d in rng.integers(700, 900, 40)]  # theme 1: dormant
        + [mk(d) for d in rng.integers(1, 900, 40)]  # theme 2: mixed
    )
    out = galaxy.spin_gate(themes, dates, [0, 1, 2], n_perm=300)
    assert out[0]["earned"] and out[0]["side"] == "fast"
    assert out[1]["earned"] and out[1]["side"] == "dormant"
    assert not out[2]["earned"]
