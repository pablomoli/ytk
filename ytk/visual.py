"""SigLIP-2 visual embeddings — one vector per saved item (issue #12).

Runs google/siglip2-so400m-patch16-384 on Metal via torch + transformers
(already in ytk's environment). Chosen over DINOv2 and mlx-embeddings after
the eval in experiments/visual_encoder_eval.py: SigLIP-2 won both the
instance-level and semantic metric on the real save corpus, and
mlx-embeddings pins transformers<5 which conflicts with sentence-transformers.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

MODEL_ID = "google/siglip2-so400m-patch16-384"

_model = None
_processor = None
_device = None


def _download_weights():
    """Fetch model weights in a clean subprocess: store.py sets HF_HUB_OFFLINE=1
    process-wide at import, which huggingface_hub bakes in at import time."""
    import subprocess
    import sys

    env = {k: v for k, v in os.environ.items() if k != "HF_HUB_OFFLINE"}
    subprocess.run(
        [sys.executable, "-c",
         "from huggingface_hub import snapshot_download; "
         f"snapshot_download('{MODEL_ID}')"],
        check=True,
        env=env,
    )


def _load():
    global _model, _processor, _device
    if _model is None:
        import torch
        from transformers import AutoModel, AutoProcessor

        _device = "mps" if torch.backends.mps.is_available() else "cpu"
        dtype = torch.float16 if _device == "mps" else torch.float32
        try:
            _model = AutoModel.from_pretrained(
                MODEL_ID, dtype=dtype, local_files_only=True
            )
        except OSError:
            logger.info("downloading %s (~4.5GB, one time)", MODEL_ID)
            _download_weights()
            _model = AutoModel.from_pretrained(
                MODEL_ID, dtype=dtype, local_files_only=True
            )
        _model = _model.to(_device).eval()
        _processor = AutoProcessor.from_pretrained(MODEL_ID, local_files_only=True)
    return _model, _processor, _device


def embed_images(paths: list[Path], batch_size: int = 8) -> list[list[float]]:
    """Embed images into SigLIP-2 space. Order matches input order."""
    import torch
    from PIL import Image

    model, processor, device = _load()
    out: list[list[float]] = []
    for i in range(0, len(paths), batch_size):
        pil = [Image.open(p).convert("RGB") for p in paths[i : i + batch_size]]
        inputs = processor(images=pil, return_tensors="pt").to(device)
        with torch.no_grad():
            feats = model.get_image_features(**inputs)
        feats = getattr(feats, "pooler_output", feats)
        out.extend(feats.float().cpu().numpy().tolist())
    return out


def embed_text(query: str) -> list[float]:
    """Embed a text query into the same space (SigLIP-2 text tower)."""
    import torch

    model, processor, device = _load()
    inputs = processor(
        text=[query], padding="max_length", max_length=64, return_tensors="pt"
    ).to(device)
    with torch.no_grad():
        feats = model.get_text_features(**inputs)
    feats = getattr(feats, "pooler_output", feats)
    return feats.float().cpu().numpy()[0].tolist()


@dataclass
class CoverItem:
    item_id: str
    image_path: Path
    source: str
    title: str = ""
    url: str = ""
    note_path: str = ""


def _vault() -> Path:
    return Path(
        os.environ.get(
            "OBSIDIAN_VAULT_PATH",
            os.path.expanduser(
                "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Vault"
            ),
        )
    )


_FM_URL = re.compile(r"^url:\s*(\S+)", re.M)
_FM_TITLE = re.compile(r"^title:\s*(.+)$", re.M)


def _frontmatter(note: Path) -> tuple[str, str]:
    try:
        text = note.read_text(errors="ignore")[:2000]
    except OSError:
        return "", ""
    url = m.group(1) if (m := _FM_URL.search(text)) else ""
    title = m.group(1).strip() if (m := _FM_TITLE.search(text)) else ""
    return url, title


def iter_covers() -> list[CoverItem]:
    """One canonical cover per save across all sources.

    Id scheme matches experiments/visual_encoder_eval.py: yt:/ig:/tt:/cover:.
    """
    sources = _vault() / "second-brain" / "sources"
    items: list[CoverItem] = []

    yt_notes: dict[str, Path] = {}
    for note in (sources / "youtube").glob("*.md"):
        url, _ = _frontmatter(note)
        if m := re.search(r"[?&]v=([\w-]{11})", url):
            yt_notes[m.group(1)] = note
    for p in sorted((sources / "youtube" / "thumbnails").glob("*-thumb.jpg")):
        vid = p.name.removesuffix("-thumb.jpg")
        note = yt_notes.get(vid)
        url, title = _frontmatter(note) if note else ("", "")
        items.append(CoverItem(
            item_id=f"yt:{vid}", image_path=p, source="youtube",
            title=title, url=url or f"https://www.youtube.com/watch?v={vid}",
            note_path=str(note) if note else "",
        ))

    ig_notes = list((sources / "instagram").glob("*.md"))
    seen_ig: set[str] = set()
    for p in sorted((sources / "instagram").glob("*-img-*.jpg")):
        shortcode = re.sub(r"-img-\d+\.jpg$", "", p.name)
        if shortcode in seen_ig or not p.name.endswith("-img-1.jpg"):
            continue
        seen_ig.add(shortcode)
        note = next((n for n in ig_notes if shortcode in n.name), None)
        url, title = _frontmatter(note) if note else ("", "")
        items.append(CoverItem(
            item_id=f"ig:{shortcode}", image_path=p, source="instagram",
            title=title, url=url, note_path=str(note) if note else "",
        ))

    tt_thumbs = sources / "tiktok" / "thumbnails"
    if tt_thumbs.exists():
        for p in sorted(tt_thumbs.iterdir()):
            if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
                items.append(CoverItem(
                    item_id=f"tt:{p.stem}", image_path=p, source="tiktok",
                ))

    shots = sources / "screenshots"
    if shots.exists():
        for p in sorted(shots.glob("*.png")):
            note = p.with_suffix(".md")
            items.append(CoverItem(
                item_id=f"shot:{p.stem}", image_path=p, source="screenshot",
                note_path=str(note) if note.exists() else "",
            ))

    covers_dir = Path.home() / ".ytk" / "covers"
    if covers_dir.exists():
        for p in sorted(covers_dir.glob("*.jpg")):
            items.append(CoverItem(
                item_id=f"cover:{p.stem}", image_path=p, source="reel-cover",
            ))

    return items


def index_covers(limit: int | None = None, progress=None) -> int:
    """Backfill/refresh the visual collection. Idempotent. Returns count indexed."""
    from . import store

    items = iter_covers()
    if limit:
        items = items[:limit]
    done = 0
    batch = 16
    for i in range(0, len(items), batch):
        chunk = [it for it in items[i : i + batch] if it.image_path.exists()]
        if not chunk:
            continue
        try:
            embeddings = embed_images([it.image_path for it in chunk])
        except Exception:
            logger.exception("visual embedding batch failed")
            continue
        for it, emb in zip(chunk, embeddings):
            store.upsert_visual(it.item_id, emb, {
                "source": it.source,
                "title": it.title,
                "url": it.url,
                "image_path": str(it.image_path),
                "note_path": it.note_path,
            })
            done += 1
        if progress:
            progress(done, len(items))
    return done


def embed_cover_for_save(image_path: Path, item_id: str, metadata: dict) -> bool:
    """Ingest-time hook: embed one cover. Never raises; returns success."""
    from . import store

    try:
        emb = embed_images([image_path])[0]
        store.upsert_visual(item_id, emb, {"image_path": str(image_path), **metadata})
        return True
    except Exception:
        logger.exception("visual embed failed for %s", image_path)
        return False
