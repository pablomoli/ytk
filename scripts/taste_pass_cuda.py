"""One pass over a folder of taste test frames: the bank, the map statistics and SigLIP together.

Each frame is decoded once, off the main thread, and every reading is taken from that one
decode. Readings are cached per frame in cache/ beside this file, keyed by the frame's bytes and by
the source of the code that made them, so a frame is measured again only when it or its
measure changed. Nothing per-pixel is written.
Standalone for a CUDA machine: torch, numpy, scipy, PIL, transformers.

    python taste_pass_cuda.py <flat_dir> <order.json> <out_dir> [--one-per-item] [--no-siglip]

Writes bank.npz, together.npz, siglip.npz and order.json (the rows they hold) to <out_dir>.
--one-per-item reads the middle frame of each item, for trying a measure before a full pass.
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import taste_bank_cuda as bank
import taste_maps_cuda as maps
import torch
from PIL import Image

HERE = Path(__file__).resolve().parent
AHEAD = 6  # decoded frames held at once; a 4K frame is 25 MB decoded


def version(*files: str) -> str:
    return hashlib.sha256(b"".join((HERE / f).read_bytes() for f in files)).hexdigest()[:10]


def main() -> None:
    flat, order_path, dst = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    order = json.loads(order_path.read_text())
    if "--one-per-item" in sys.argv:
        by_item = defaultdict(list)
        for o in order:
            by_item[o["item"]].append(o)
        order = [v[len(v) // 2] for v in by_item.values()]
    want_sig = "--no-siglip" not in sys.argv
    cache = HERE / "cache"
    parts = {
        "bank": cache / f"bank-{version('taste_bank_cuda.py')}",
        "maps": cache / f"maps-{version('taste_maps_cuda.py')}",
    }
    if want_sig:
        import taste_embed_cuda as embed

        parts["siglip"] = cache / f"siglip-{version('taste_embed_cuda.py')}"
        proc = embed.processor()
    for d in (dst, *parts.values()):
        d.mkdir(parents=True, exist_ok=True)
    spent = defaultdict(float)

    def load(o: dict) -> tuple:
        """Off the main thread: read, hash, and decode only if some reading is missing."""
        t = time.perf_counter()
        raw = (flat / o["name"]).read_bytes()
        key = hashlib.sha256(raw).hexdigest()[:20]
        missing = [p for p, d in parts.items() if not (d / f"{key}.npz").exists()]
        rgb = bpp = px = None
        if missing:
            with Image.open(io.BytesIO(raw)) as im:
                im = im.convert("RGB")
                if "bank" in missing or "maps" in missing:
                    rgb = np.asarray(im).copy()
                if "bank" in missing:
                    bpp = bank.jpeg_bits(im)
                if "siglip" in missing:
                    px = embed.prepare(proc, im)
        return key, missing, rgb, bpp, px, time.perf_counter() - t

    keys, waiting, fresh = [], [], defaultdict(int)
    start = time.perf_counter()
    with ThreadPoolExecutor(4) as pool:
        queue = deque()
        for o in order:
            queue.append(pool.submit(load, o))
            if len(queue) < AHEAD:
                continue
            _take(queue, keys, waiting, parts, spent, fresh)
        while queue:
            _take(queue, keys, waiting, parts, spent, fresh)
    if waiting:
        t = time.perf_counter()
        tower = embed.Tower()
        for i in range(0, len(waiting), embed.BATCH):
            chunk = waiting[i : i + embed.BATCH]
            rows = tower.read(torch.stack([px for _, px in chunk]))
            for (key, _), row in zip(chunk, rows, strict=True):
                np.savez(parts["siglip"] / f"{key}.npz", **row)
        spent["siglip"] += time.perf_counter() - t
        fresh["siglip"] = len(waiting)
    for part, name in (("bank", "bank.npz"), ("maps", "together.npz"), ("siglip", "siglip.npz")):
        if part not in parts:
            continue
        rows = [np.load(parts[part] / f"{k}.npz") for k in keys]
        fams = list(rows[0].files)
        extra = {"families": np.array(fams)} if part != "siglip" else {}
        if part == "maps":
            extra["channels"] = np.array(maps.NAMES)
        np.savez_compressed(
            dst / name, **extra, **{f: np.stack([r[f] for r in rows]) for f in fams}
        )
    (dst / "order.json").write_text(json.dumps(order))
    total = time.perf_counter() - start
    print(
        f"DONE {len(order)} frames in {total:.1f} s  ·  measured now: "
        + ", ".join(f"{p} {fresh[p]}" for p in parts)
        + "  ·  seconds: "
        + ", ".join(f"{k} {v:.1f}" for k, v in spent.items()),
        flush=True,
    )


def _take(queue, keys, waiting, parts, spent, fresh) -> None:
    key, missing, rgb, bpp, px, decode = queue.popleft().result()
    keys.append(key)
    spent["decode (threads)"] += decode
    if rgb is not None:
        t = time.perf_counter()
        x = torch.from_numpy(rgb).to(bank.DEV).permute(2, 0, 1).float() / 255
        if "bank" in missing:
            row = {k: np.nan_to_num(v) for k, v in bank.measure(x, bpp).items()}
            np.savez(parts["bank"] / f"{key}.npz", **row)
            if bank.DEV == "cuda":
                torch.cuda.synchronize()
            spent["bank"] += time.perf_counter() - t
            fresh["bank"] += 1
            t = time.perf_counter()
        if "maps" in missing:
            np.savez(parts["maps"] / f"{key}.npz", **maps.measure(x))
            if bank.DEV == "cuda":
                torch.cuda.synchronize()
                torch.cuda.empty_cache()
            spent["maps"] += time.perf_counter() - t
            fresh["maps"] += 1
    if px is not None:
        waiting.append((key, px))
    if len(keys) % 50 == 0:
        print(f"{len(keys)} frames", flush=True)


if __name__ == "__main__":
    main()
