"""Method-neutral transfer + hierarchy-aware agreement (Codex F1/F2).

knn_transfer: assign held-out points by majority vote of their k nearest
neighbors in the fitted half — no centroid-compactness assumption.
triplet_agreement: do two dendrograms agree which pair of a sampled triplet
is closest? Chance is 1/3; identical structure should score near 1.
"""

import numpy as np

from scripts.grove_lab.shootout import knn_transfer, triplet_agreement


def _blobs(n_per=30, dim=8, seed=0, sep=8.0):
    rng = np.random.default_rng(seed)
    out, labels = [], []
    for b in range(3):
        c = np.zeros(dim)
        c[b] = sep
        out.append(rng.normal(0, 0.4, (n_per, dim)) + c)
        labels += [b] * n_per
    return np.vstack(out), np.array(labels)


def test_knn_transfer_recovers_blob_labels():
    src, src_labels = _blobs(seed=1)
    dst, dst_true = _blobs(seed=2)
    inherited = knn_transfer(src, src_labels, dst, k=5)
    # blobs are well separated: transfer should match dst's true blobs
    # up to label naming — check exact since src/dst share blob order
    assert (inherited == dst_true).mean() > 0.95


def test_triplet_agreement_high_for_same_structure_low_for_shuffled():
    from scipy.cluster.hierarchy import linkage
    from scipy.spatial.distance import pdist

    a, _ = _blobs(seed=3)
    b, _ = _blobs(seed=4)
    Za, Zb = linkage(pdist(a, "cosine"), "average"), linkage(pdist(b, "cosine"), "average")
    rng = np.random.default_rng(0)
    same = triplet_agreement(Za, a, Zb, b, n_triplets=500, rng=rng)
    # v2 metric (symmetric, injective, tie-skipping) is stricter than the
    # retired one-way version; the property is "far above the 1/3 chance
    # floor", with the shuffled gap carrying the discriminative assertion
    assert same > 0.65
    perm = rng.permutation(len(b))
    shuffled = triplet_agreement(Za, a, Zb, b[perm], n_triplets=500, rng=rng)
    assert shuffled < same - 0.2


def test_triplet_agreement_is_symmetric_and_reports_stats():
    """Codex G3: score both directions; reject non-injective triplets; skip
    ties on either side; expose collision + usage stats."""
    from scipy.cluster.hierarchy import linkage
    from scipy.spatial.distance import pdist

    a, _ = _blobs(seed=5)
    b, _ = _blobs(seed=6)
    Za, Zb = linkage(pdist(a, "cosine"), "average"), linkage(pdist(b, "cosine"), "average")
    rng = np.random.default_rng(1)
    score, stats = triplet_agreement(Za, a, Zb, b, n_triplets=500, rng=rng, return_stats=True)
    assert score > 0.75
    # both directions were scored and averaged
    assert set(stats) >= {"collision_rate", "used", "rejected_noninjective", "tie_skipped"}
    assert 0.0 <= stats["collision_rate"] < 1.0
    assert stats["used"] > 100


def test_structure_null_is_near_chance():
    """Codex G5: with tree SHAPE kept and leaf identities permuted (mapping
    intact), agreement must collapse toward 1/3 — this isolates whether the
    fitted hierarchy, not raw embedding neighborhoods, carries the signal."""
    from scipy.cluster.hierarchy import linkage
    from scipy.spatial.distance import pdist

    from scripts.grove_lab.shootout import structure_null

    a, _ = _blobs(seed=7)
    b, _ = _blobs(seed=8)
    Za, Zb = linkage(pdist(a, "cosine"), "average"), linkage(pdist(b, "cosine"), "average")
    rng = np.random.default_rng(2)
    real = triplet_agreement(Za, a, Zb, b, n_triplets=500, rng=rng)
    null = structure_null(Za, a, Zb, b, n_triplets=500, rng=rng)
    assert null < 0.5
    assert real - null > 0.25
