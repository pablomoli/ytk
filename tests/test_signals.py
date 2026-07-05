"""Taste-profile v2 signal weighting (issue #16, E2): r levels read from disk,
confidence weights w = 1 + alpha*r, weighted centroids, gated explicit channel."""

from __future__ import annotations

import numpy as np
import pytest

from ytk import signals
from ytk.synthesis import ProfileSynthesis, ThemeLabel, assemble_snapshot, weighted_centroid


def test_classify_ladder():
    assert signals.classify("youtube", "---\nurl: u\n---\nbody") == 0
    assert signals.classify("instagram", "---\n---\nbody") == 1
    assert signals.classify("screenshots", "---\n---\nsnap") == 1
    assert signals.classify("youtube", "---\n---\n## My take\n\nloved this") == 2
    assert signals.classify("instagram", "---\n---\n## My take\nx\n\nRelated: [[note]]\n") == 3


def test_weights_shape():
    assert signals.weights([0, 1, 2, 3], alpha=1.0) == [1.0, 2.0, 3.0, 4.0]
    assert signals.weights([0, 3], alpha=0.0) == [1.0, 1.0]  # alpha=0 disables


def test_weighted_centroid_pulls_toward_heavy():
    emb = np.array([[1.0, 0.0], [0.0, 1.0]])
    c = np.array(weighted_centroid(emb, [1.0, 3.0]))
    assert c[1] > c[0]
    assert abs(np.linalg.norm(c) - 1.0) < 1e-9  # unit norm


def _synth():
    return ProfileSynthesis(
        themes=[ThemeLabel(cluster_index=0, label="A", summary=""),
                ThemeLabel(cluster_index=1, label="B", summary="")],
        profile_markdown="p",
    )


def _notes(n):
    return [{"id": f"n{i}", "title": f"t{i}"} for i in range(n)]


def test_snapshot_v2_weighted_theme_share_and_centroids():
    emb = np.array([[1.0, 0.0], [1.0, 0.1], [0.0, 1.0], [0.1, 1.0]])
    labels = [0, 0, 1, 1]
    weights = [1.0, 1.0, 3.0, 3.0]  # theme B carries the signal
    snap = assemble_snapshot(_notes(4), labels, _synth(), "now",
                             embeddings=emb, weights=weights,
                             levels=[0, 0, 2, 2], alpha=1.0, explicit_min=5)
    assert snap.themes[0].label == "B"          # weighted share ranks B first
    assert snap.themes[0].weight == 0.75        # 6 / 8
    assert snap.themes[0].centroid is not None
    assert snap.alpha == 1.0
    assert snap.signal_counts == {0: 2, 2: 2}
    assert snap.explicit is None                # only 2 thought items < gate of 5


def test_explicit_channel_activates_at_gate():
    emb = np.tile(np.array([[1.0, 0.0]]), (6, 1))
    snap = assemble_snapshot(_notes(6), [0] * 6,
                             ProfileSynthesis(themes=[ThemeLabel(cluster_index=0, label="A", summary="")],
                                              profile_markdown="p"),
                             "now", embeddings=emb, weights=[1.0] * 6,
                             levels=[2, 2, 2, 2, 2, 0], alpha=1.0, explicit_min=5)
    assert snap.explicit is not None
    assert len(snap.explicit.note_ids) == 5


def test_snapshot_v1_call_still_works():
    snap = assemble_snapshot(_notes(2), [0, 1], _synth(), "now")
    assert snap.themes[0].centroid is None and snap.explicit is None
    assert snap.signal_counts == {}
