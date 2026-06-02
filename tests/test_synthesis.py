import numpy as np

from ytk.config import InterestConfig
from ytk.synthesis import choose_k, cluster_embeddings


def test_choose_k_clamps_small_corpus():
    cfg = InterestConfig()
    assert choose_k(2, cfg) == 2          # n <= cluster_min -> n
    assert choose_k(0, cfg) == 1          # never zero


def test_choose_k_scales_and_caps():
    cfg = InterestConfig(cluster_min=3, cluster_max=24)
    assert choose_k(50, cfg) == 5         # round(sqrt(50/2)) = 5
    assert choose_k(100000, cfg) == 24    # capped at cluster_max


def test_cluster_embeddings_separates_two_blobs():
    blob_a = np.tile([0.0, 0.0, 1.0], (5, 1)) + np.linspace(0, 0.01, 15).reshape(5, 3)
    blob_b = np.tile([1.0, 0.0, 0.0], (5, 1)) + np.linspace(0, 0.01, 15).reshape(5, 3)
    embeddings = np.vstack([blob_a, blob_b])

    labels = cluster_embeddings(embeddings, k=2)

    assert len(labels) == 10
    assert len(set(labels[:5])) == 1      # first blob is one cluster
    assert len(set(labels[5:])) == 1      # second blob is one cluster
    assert labels[0] != labels[5]         # the two blobs differ
