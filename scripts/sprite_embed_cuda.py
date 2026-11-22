"""SigLIP-2 over every sprite tile, on a CUDA machine. Standalone: no ytk import.

Same checkpoint and revision as ytk/visual.py, so tile vectors live in the
cover vectors' space. Writes <out>/<video_id>.npy (float16, one row per tile,
unit length). Resumable.

    python sprite_embed_cuda.py <sprites_dir> <out_dir>
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from transformers import AutoModel, AutoProcessor

MODEL_ID = "google/siglip2-so400m-patch16-384"
MODEL_REVISION = "dd658faac399427308559e2c3ac1e99cbe43845d"
BATCH = 96


def tiles(d: Path) -> list[Image.Image]:
    grid = json.loads((d / "grid.json").read_text())
    per, out = grid["rows"] * grid["cols"], []
    for sheet in sorted(d.glob("[0-9]*.jpg")):
        with Image.open(sheet) as im:
            im = im.convert("RGB")
            w, h = im.width // grid["cols"], im.height // grid["rows"]
            for k in range(per):
                r, c = divmod(k, grid["cols"])
                out.append(im.crop((c * w, r * h, (c + 1) * w, (r + 1) * h)))
    return out[: grid["tiles"]]


def main() -> None:
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    (out / "DONE").unlink(missing_ok=True)
    model = AutoModel.from_pretrained(MODEL_ID, revision=MODEL_REVISION, dtype=torch.float16)
    model = model.to("cuda").eval()
    proc = AutoProcessor.from_pretrained(MODEL_ID, revision=MODEL_REVISION)
    dirs = sorted(d for d in src.iterdir() if (d / "grid.json").exists())
    t0, done = time.monotonic(), 0
    for n, d in enumerate(dirs, 1):
        target = out / f"{d.name}.npy"
        if target.exists():
            continue
        ims, rows = tiles(d), []
        for i in range(0, len(ims), BATCH):
            batch = proc(images=ims[i : i + BATCH], return_tensors="pt").to("cuda")
            with torch.inference_mode():
                f = model.get_image_features(pixel_values=batch["pixel_values"].half())
            f = getattr(f, "pooler_output", f)
            rows.append(torch.nn.functional.normalize(f.float(), dim=-1).cpu().numpy())
        np.save(target, np.concatenate(rows).astype(np.float16))
        done += len(ims)
        el = time.monotonic() - t0
        print(
            f"[{n}/{len(dirs)}] {d.name}  {len(ims)} tiles  {done / el:.0f} tiles/s  ({el:.0f} s)",
            flush=True,
        )
    (out / "DONE").write_text(f"{len(dirs)}\n")
    print(f"DONE {len(dirs)} videos")


if __name__ == "__main__":
    main()
