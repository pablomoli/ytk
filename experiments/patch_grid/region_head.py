"""The region-masked pooling head (section 54, #218; TextRegion, arXiv 2505.23769).

SigLIP-2 pools 576 patch tokens with one learned probe through a multi-head
attention, then a layernorm and a residual MLP. Running that same head with
the attention logits set to minus infinity outside one region's patches gives
a vector for the region in the text tower's space, at the cost of one tiny
head pass per region and no extra encoder pass.
"""

from __future__ import annotations

import numpy as np
import torch


def region_vectors(head: torch.nn.Module, tokens: np.ndarray, grids: np.ndarray) -> np.ndarray:
    """One pooled vector per region.

    head:   the production `vision_model.head`, float32 on CPU.
    tokens: (576, D) last hidden state of one image.
    grids:  (R, 24, 24) bool, the patches each region owns. A region that
            owns no patch falls back to its single best-covered patch, which
            the caller supplies by making that one patch true.
    Returns (R, D) float32, unnormalised, in the same space as `head(tokens)`.
    """
    h = torch.as_tensor(np.asarray(tokens), dtype=torch.float32)[None]  # (1, 576, D)
    keep = torch.as_tensor(np.asarray(grids).reshape(len(grids), -1), dtype=torch.bool)  # (R, 576)
    if not bool(keep.any(dim=1).all()):
        raise ValueError("every region must own at least one patch")
    r = keep.shape[0]
    probe = head.probe.repeat(r, 1, 1)  # (R, 1, D)
    hk = h.expand(r, -1, -1)
    # nn.MultiheadAttention: a float mask is added to the logits; (R*heads, 1, 576).
    mask = torch.zeros(r, 1, keep.shape[1], dtype=torch.float32)
    mask[~keep[:, None, :]] = float("-inf")
    mask = mask.repeat_interleave(head.attention.num_heads, dim=0)
    with torch.no_grad():
        x = head.attention(probe, hk, hk, attn_mask=mask, need_weights=False)[0]
        x = x + head.mlp(head.layernorm(x))
    return x[:, 0].numpy()


def region_attention(head: torch.nn.Module, tokens: np.ndarray, grid: np.ndarray) -> np.ndarray:
    """The probe's attention over the 576 patches when confined to one region,
    averaged over heads: (24, 24), zero outside the region."""
    h = torch.as_tensor(np.asarray(tokens), dtype=torch.float32)[None]
    keep = torch.as_tensor(np.asarray(grid).reshape(-1), dtype=torch.bool)
    mask = torch.zeros(1, keep.shape[0], dtype=torch.float32)
    mask[0, ~keep] = float("-inf")
    with torch.no_grad():
        _, w = head.attention(
            head.probe, h, h, attn_mask=mask, need_weights=True, average_attn_weights=True
        )
    side = int(keep.shape[0] ** 0.5)
    return w[0, 0].numpy().reshape(side, side)


def ensure_one_patch(
    grids: np.ndarray, masks: np.ndarray, side: int = 24, inp: int = 384
) -> tuple[np.ndarray, int]:
    """Give every empty region its single best-covered patch. Returns the
    repaired grids and how many regions needed it."""
    from PIL import Image

    out = grids.copy()
    fixed = 0
    k = inp // side
    for i in np.where(grids.reshape(len(grids), -1).sum(1) == 0)[0]:
        m = Image.fromarray(masks[i].astype(np.uint8) * 255).resize((inp, inp), Image.BILINEAR)
        cov = (np.asarray(m, dtype=np.float32) / 255.0).reshape(side, k, side, k).mean(axis=(1, 3))
        out[i].flat[int(cov.argmax())] = True
        fixed += 1
    return out, fixed
