import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from build_map import _ctfidf_names, assemble_all_view  # noqa: E402


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


def test_ctfidf_names_single_cluster_does_not_raise():
    names = _ctfidf_names(["alpha beta alpha gamma"])
    assert len(names) == 1


def test_ctfidf_names_two_clusters_returns_distinct_terms():
    # Shared vocabulary (each term appears in both docs, satisfying min_df=2)
    # with different per-doc term frequencies, so the ranked term order -
    # and thus the joined string - differs between clusters.
    names = _ctfidf_names(
        ["alpha alpha alpha beta beta gamma", "beta beta beta gamma gamma alpha"]
    )
    assert len(names) == 2
    assert names[0] != names[1]
