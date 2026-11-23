"""Altered copies of the taste test frames, to ask which readings follow the look and which follow the file.

Three alterations that leave what a person sees almost unchanged:
  jpeg   saved again as JPEG at quality 40
  half   resampled to half its width and height
  crop   the central 90% of the frame
Standalone: PIL only.

    python taste_perturb.py <flat_dir> <out_root>
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image


def main() -> None:
    flat, root = Path(sys.argv[1]), Path(sys.argv[2])
    for kind in ("jpeg", "half", "crop"):
        (root / kind).mkdir(parents=True, exist_ok=True)
    for n, p in enumerate(sorted(flat.glob("*.jpg")), 1):
        with Image.open(p) as im:
            im = im.convert("RGB")
            w, h = im.size
            im.save(root / "jpeg" / p.name, quality=40)
            im.resize((max(8, w // 2), max(8, h // 2)), Image.BICUBIC).save(
                root / "half" / p.name, quality=95
            )
            im.crop((round(w * 0.05), round(h * 0.05), round(w * 0.95), round(h * 0.95))).save(
                root / "crop" / p.name, quality=95
            )
        if n % 100 == 0:
            print(n, flush=True)
    print("DONE")


if __name__ == "__main__":
    main()
