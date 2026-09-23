"""The region-masked head with a full mask must reproduce the production embedding."""

from __future__ import annotations

import copy
import os
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "experiments" / "patch_grid"))

NIGHT = Path(os.path.expanduser("~/.ytk/patch_grid/night/goat.npz"))
pytestmark = pytest.mark.skipif(
    not NIGHT.exists() or os.environ.get("HF_HUB_OFFLINE") != "1",
    reason="needs the night cache and the local SigLIP-2 weights (HF_HUB_OFFLINE=1)",
)


def test_full_mask_reproduces_production_embedding() -> None:
    import torch
    from region_head import region_vectors

    from ytk import visual

    model, _, _ = visual._load()
    head = copy.deepcopy(model.vision_model.head).float().cpu()
    d = np.load(NIGHT)
    full = np.ones((1, 24, 24), dtype=bool)
    v = region_vectors(head, d["tokens"], full)[0]
    ref = d["pooled"]
    cos = float(v @ ref / (np.linalg.norm(v) * np.linalg.norm(ref)))
    assert cos > 0.9999, cos
    # A half mask must give a different vector, or the mask is not reaching the logits.
    half = np.zeros((1, 24, 24), dtype=bool)
    half[0, :12] = True
    v2 = region_vectors(head, d["tokens"], half)[0]
    cos2 = float(v2 @ ref / (np.linalg.norm(v2) * np.linalg.norm(ref)))
    assert cos2 < 0.999, cos2
    assert torch.isfinite(torch.as_tensor(v2)).all()
