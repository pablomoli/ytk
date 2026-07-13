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
    assert same > 0.75
    # shuffled mapping destroys agreement toward the 1/3 chance floor
    perm = rng.permutation(len(b))
    shuffled = triplet_agreement(Za, a, Zb, b[perm], n_triplets=500, rng=rng)
    assert shuffled < same - 0.2
