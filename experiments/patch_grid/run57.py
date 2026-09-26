"""Section 57 (#218): SAM 3 on the M3 through transformers, timed on MPS.

HF_HUB_OFFLINE=1 uv run python experiments/patch_grid/run57.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import night as N

MODEL = "facebook/sam3"
IMAGE = "woman-river"
QUERIES = [
    "sunglasses",
    "a woman wearing sunglasses",
    "the whole woman",
    "woman",
    "printed caption text",
    "text",
    "a stone wall",
]
THRESHOLD = 0.5


def main() -> None:
    from transformers import Sam3Model, Sam3Processor

    device = "mps"
    t0 = time.time()
    model = (
        Sam3Model.from_pretrained(MODEL, dtype=torch.float16, local_files_only=True)
        .to(device)
        .eval()
    )
    processor = Sam3Processor.from_pretrained(MODEL, local_files_only=True)
    t_load = time.time() - t0
    print(
        f"loaded in {t_load:.1f}s; params {sum(p.numel() for p in model.parameters()) / 1e9:.2f}B",
        flush=True,
    )
    pil = Image.open(N.image_path(IMAGE)).convert("RGB")
    out: dict[str, np.ndarray] = {"queries": np.array(QUERIES), "load_seconds": np.array(t_load)}
    times, peaks = [], []
    for k, q in enumerate(QUERIES):
        torch.mps.synchronize()
        torch.mps.reset_peak_memory_stats() if hasattr(
            torch.mps, "reset_peak_memory_stats"
        ) else None
        t1 = time.time()
        inputs = processor(images=pil, text=q, return_tensors="pt").to(device)
        with torch.no_grad():
            o = model(**inputs)
        res = processor.post_process_instance_segmentation(
            o,
            threshold=THRESHOLD,
            mask_threshold=0.5,
            target_sizes=[(pil.size[1], pil.size[0])],
        )[0]
        torch.mps.synchronize()
        dt = time.time() - t1
        peak = torch.mps.driver_allocated_memory() / 2**30
        times.append(dt)
        peaks.append(peak)
        masks = (
            res["masks"].cpu().numpy().astype(bool)
            if len(res["masks"])
            else np.zeros((0, pil.size[1], pil.size[0]), bool)
        )
        scores = res["scores"].float().cpu().numpy() if len(res["scores"]) else np.zeros(0)
        out[f"q{k}/masks"] = masks
        out[f"q{k}/scores"] = scores
        print(
            f"{q:28} {dt:5.2f}s  {len(masks)} masks above {THRESHOLD}  scores {np.round(scores, 2).tolist()[:6]}  areas {[round(float(m.mean()), 3) for m in masks][:6]}  mps {peak:.2f} GB",
            flush=True,
        )
    out["seconds"] = np.array(times)
    out["peak_gb"] = np.array(peaks)
    np.savez_compressed(N.CACHE / "57_sam3.npz", **out)
    print(
        f"per image after warm-up: {np.mean(times[1:]):.2f}s  peak driver memory {max(peaks):.2f} GB"
    )


if __name__ == "__main__":
    main()
