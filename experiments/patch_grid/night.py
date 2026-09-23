"""Shared state for the patch-grid night (#218, sections 54-58).

The ten images, their queries, the per-image cache under ~/.ytk/patch_grid/night,
and the SigLIP-2 geometry every section maps SAM masks onto.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SECTION_ROOT = ROOT / "docs" / "assets"
QUERIES = HERE / "queries.json"
CACHE = Path(os.path.expanduser("~/.ytk/patch_grid/night"))
SPIKES = Path(os.path.expanduser("~/.ytk/patch_grid/spikes"))
VAULT = Path(
    os.path.expanduser(
        "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Vault/second-brain/sources"
    )
)

SIDE = 24  # patches per side at 384 / 16
INPUT = 384

# Order fixed by docs/design/patch-grid-night/README.md: the four spike images
# first, then the six drawn from ytk_visual by random.Random(54).
IMAGES: dict[str, str] = {
    "goat": "instagram/slides/DH7a_cmuzlqA6O7uVAxnX3b5A3zovuZnFPSo_s0-img-1.jpg",
    "keyboard-render": "pinterest/306174474692151881-img.jpg",
    "skull-moon": "instagram/slides/DatQD1jjpJ--img-1.jpg",
    "woman-river": "instagram/slides/DcGVYrukZ6g-img-1.jpg",
    "keyboard-photo": "pinterest/306174474692067382-img.jpg",
    "anime-window": "instagram/slides/DbEzhk1DhUl-img-1.jpg",
    "sewing-cabinet": "instagram/slides/DaATV4rlCC2-img-1.jpg",
    "barn-owl": "instagram/slides/Da5KllRjZRu-img-1.jpg",
    "sunglasses-selfie": "instagram/slides/DaICTFUAeI_-img-1.jpg",
    "kasai-art": "pinterest/422281212512353-img.jpg",
}

# SAM automatic-mask settings that produced the spike's 46 objects.
SAM_MODEL = "facebook/sam-vit-base"
SAM_KW = {"points_per_batch": 32, "pred_iou_thresh": 0.80, "stability_score_thresh": 0.85}
AREA_MIN, AREA_MAX = 0.0015, 0.85


def image_path(name: str) -> Path:
    return VAULT / IMAGES[name]


def queries() -> dict[str, list[str]]:
    """Three per image: small unique object, frame-filling object, absent object."""
    return json.loads(QUERIES.read_text())


def cache_file(name: str) -> Path:
    return CACHE / f"{name}.npz"


def load(name: str) -> dict[str, np.ndarray]:
    return dict(np.load(cache_file(name), allow_pickle=True))


def patch_grid_from_mask(mask: np.ndarray) -> np.ndarray:
    """Pixel mask -> (24, 24) bool: a patch belongs to the region if at least
    half of it is covered, after the processor's squash to 384 x 384."""
    from PIL import Image

    m = Image.fromarray(mask.astype(np.uint8) * 255).resize((INPUT, INPUT), Image.BILINEAR)
    a = np.asarray(m, dtype=np.float32) / 255.0
    k = INPUT // SIDE
    return a.reshape(SIDE, k, SIDE, k).mean(axis=(1, 3)) >= 0.5
