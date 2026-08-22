"""Per-latent seed agreement for the wall badges (#183 rung 2).

For every latent of the s0 dictionary: max decoder-row cosine against the
full s1 and s2 dictionaries. The badge a tile wears is the min of the two —
"the concept a latent names survives retraining or it does not".
stability.json holds the global summary; this is the same measure per latent.

    uv run --with torch python experiments/sae_qwen/seed_agreement.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import torch
from paths import CKPT

HERE = Path(__file__).resolve().parent


def dec(seed: int) -> np.ndarray:
    blob = torch.load(CKPT / f"final_d2048_k32_s{seed}.pt", map_location="cpu")
    W = blob["state"]["W_dec"].numpy()
    return W / np.maximum(np.linalg.norm(W, axis=1, keepdims=True), 1e-9)


def main() -> None:
    W0, W1, W2 = dec(0), dec(1), dec(2)
    m1 = (W0 @ W1.T).max(axis=1)
    m2 = (W0 @ W2.T).max(axis=1)
    badge = np.minimum(m1, m2)
    out = {
        "measure": "min over seeds 1,2 of max decoder-row cosine with the s0 row",
        "badge": [round(float(b), 4) for b in badge],
        "max_cos_s1": [round(float(b), 4) for b in m1],
        "max_cos_s2": [round(float(b), 4) for b in m2],
    }
    (HERE / "seed_agreement.json").write_text(json.dumps(out))
    print(
        f"badge: median {np.median(badge):.3f}, frac >= 0.8: {(badge >= 0.8).mean():.3f}, "
        f"frac >= 0.5: {(badge >= 0.5).mean():.3f}"
    )


if __name__ == "__main__":
    main()
