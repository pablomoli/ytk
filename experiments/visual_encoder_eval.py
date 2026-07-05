"""SigLIP-2 vs DINOv2 on ytk's real saved imagery (issue #12).

Compares the two local-runnable visual encoders on the actual corpus of saved
covers, thumbnails, frames, and post images. Two quantitative signals plus a
side-by-side gallery for human judgment:

  1. same-group retrieval: frames of one video / images of one Instagram post
     should be mutual nearest neighbors (instance-level signal, favors DINOv2)
  2. tag precision@5: YouTube thumbnails whose top-5 neighbors share an
     interest tag (semantic signal, the one ytk actually needs)
  3. HTML gallery: top-5 neighbors per query under each model, side by side

Run inside a venv with mlx-embeddings>=0.1.0, mlx-image, transformers<5:

  python experiments/visual_encoder_eval.py --out /tmp/encoder-eval
"""

import argparse
import base64
import io
import json
import os
import re
from pathlib import Path

import mlx.core as mx
import numpy as np
from PIL import Image

VAULT = Path(
    os.environ.get(
        "OBSIDIAN_VAULT_PATH",
        os.path.expanduser(
            "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Vault"
        ),
    )
)
SOURCES = VAULT / "second-brain" / "sources"
COVERS = Path(os.path.expanduser("~/.ytk/covers"))

SIGLIP_REPO = "mlx-community/siglip2-so400m-patch16-384"
DINO_MODEL = "vit_base_patch14_518.dinov2"

IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def collect_corpus():
    """Return list of dicts: path, group (instance id), source, tags."""
    items = []

    def add(path, group, source, tags=frozenset()):
        items.append({"path": path, "group": group, "source": source, "tags": tags})

    # map video_id -> tags from youtube note frontmatter
    vid_tags = {}
    for note in (SOURCES / "youtube").glob("*.md"):
        text = note.read_text(errors="ignore")
        m = re.search(r"[?&]v=([\w-]{11})", text)
        if not m:
            continue
        fm = text.split("---")[1] if text.startswith("---") else ""
        tags = frozenset(re.findall(r"^\s+-\s+([\w-]+)\s*$", fm, re.M))
        vid_tags[m.group(1)] = tags

    for p in sorted((SOURCES / "youtube" / "thumbnails").glob("*-thumb.jpg")):
        vid = p.name.removesuffix("-thumb.jpg")
        add(p, f"yt:{vid}", "youtube-thumb", vid_tags.get(vid, frozenset()))
    for d in sorted((SOURCES / "youtube" / "frames").glob("*/")):
        for p in sorted(d.iterdir()):
            if p.suffix.lower() in IMG_EXTS:
                add(p, f"yt:{d.name}", "youtube-frame", vid_tags.get(d.name, frozenset()))

    for sub, src in [("thumbnails", "tiktok-thumb"), ("frames", "tiktok-frame")]:
        base = SOURCES / "tiktok" / sub
        if not base.exists():
            continue
        for p in sorted(base.rglob("*")):
            if p.suffix.lower() in IMG_EXTS:
                group = p.parent.name if sub == "frames" else p.stem
                add(p, f"tt:{group}", src)

    for p in sorted((SOURCES / "instagram").glob("*-img-*.jpg")):
        shortcode = re.sub(r"-img-\d+\.jpg$", "", p.name)
        add(p, f"ig:{shortcode}", "instagram-post")

    if COVERS.exists():
        for p in sorted(COVERS.glob("*.jpg")):
            add(p, f"cover:{p.stem}", "reel-cover")

    return items


def embed_siglip(paths, batch_size=16):
    from mlx_embeddings.utils import load

    model, processor = load(SIGLIP_REPO)
    proc = getattr(processor, "image_processor", processor)
    chunks = []
    for i in range(0, len(paths), batch_size):
        pil = [Image.open(p).convert("RGB") for p in paths[i : i + batch_size]]
        pixels = mx.array(proc(images=pil, return_tensors="np")["pixel_values"])
        feats = model.get_image_features(pixels)
        mx.eval(feats)
        chunks.append(np.array(feats, dtype=np.float32))
        print(f"  siglip2 {i + len(pil)}/{len(paths)}", flush=True)
    return np.concatenate(chunks)


def embed_dino(paths, batch_size=8):
    from mlxim.model import create_model
    from mlxim.transform import ImageNetTransform

    model = create_model(DINO_MODEL)
    model.eval()
    t = ImageNetTransform(train=False, img_size=518)
    chunks = []
    for i in range(0, len(paths), batch_size):
        arrs = [
            mx.array(t(np.array(Image.open(p).convert("RGB"))))
            for p in paths[i : i + batch_size]
        ]
        out = model(mx.stack(arrs))
        if isinstance(out, (tuple, list)):
            out = out[0]
        mx.eval(out)
        chunks.append(np.array(out, dtype=np.float32))
        print(f"  dinov2 {i + len(chunks[-1])}/{len(paths)}", flush=True)
    return np.concatenate(chunks)


def cosine_neighbors(emb):
    x = emb / (np.linalg.norm(emb, axis=1, keepdims=True) + 1e-8)
    sim = x @ x.T
    np.fill_diagonal(sim, -np.inf)
    order = np.argsort(-sim, axis=1)
    return sim, order


def same_group_recall(items, order, k):
    hits, evaluable = 0, 0
    groups = [it["group"] for it in items]
    counts = {}
    for g in groups:
        counts[g] = counts.get(g, 0) + 1
    for i, it in enumerate(items):
        if counts[it["group"]] < 2:
            continue
        evaluable += 1
        if any(groups[j] == it["group"] for j in order[i, :k]):
            hits += 1
    return hits / evaluable, evaluable


def tag_precision_at_k(items, order, k=5):
    """Among tagged YouTube thumbnails, fraction of tagged top-k neighbors
    (excluding same-video images) sharing at least one interest tag."""
    scores = []
    for i, it in enumerate(items):
        if it["source"] != "youtube-thumb" or not it["tags"]:
            continue
        taken, shared = 0, 0
        for j in order[i]:
            other = items[j]
            if other["group"] == it["group"] or not other["tags"]:
                continue
            taken += 1
            if it["tags"] & other["tags"]:
                shared += 1
            if taken == k:
                break
        if taken:
            scores.append(shared / taken)
    return float(np.mean(scores)), len(scores)


def thumb_b64(path, size=180):
    img = Image.open(path).convert("RGB")
    img.thumbnail((size, size))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=70)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def build_gallery(items, orders, out_path, n_queries=18, k=5, seed=7):
    rng = np.random.default_rng(seed)
    by_source = {}
    for i, it in enumerate(items):
        by_source.setdefault(it["source"], []).append(i)
    picks = []
    for src in ("reel-cover", "youtube-thumb", "instagram-post", "tiktok-thumb"):
        pool = by_source.get(src, [])
        take = min(len(pool), max(2, n_queries // 4))
        picks += list(rng.choice(pool, size=take, replace=False))
    picks = picks[:n_queries]

    cell = (
        '<figure><img src="{b64}" title="{name}">'
        "<figcaption>{cap}</figcaption></figure>"
    )
    rows = []
    for qi in picks:
        q = items[qi]
        row = [f'<div class="query">{cell.format(b64=thumb_b64(q["path"]), name=q["path"].name, cap=q["source"])}</div>']
        for model, order in orders.items():
            cells = "".join(
                cell.format(b64=thumb_b64(items[j]["path"]), name=items[j]["path"].name, cap="")
                for j in order[qi, :k]
            )
            row.append(f'<div class="hits"><span class="model">{model}</span>{cells}</div>')
        rows.append('<section class="row">' + "".join(row) + "</section>")

    html = (
        "<!doctype html><meta charset='utf-8'><title>SigLIP-2 vs DINOv2 — ytk saves</title>"
        "<style>body{background:#0d0e12;color:#d8d9de;font:14px/1.5 -apple-system,sans-serif;"
        "margin:2rem auto;max-width:1200px;padding:0 1rem}"
        "h1{font-weight:600;letter-spacing:-.02em}p.sub{color:#7c7f8a}"
        ".row{display:grid;grid-template-columns:200px 1fr;gap:1rem;align-items:start;"
        "border-top:1px solid #22242c;padding:1.2rem 0}"
        ".hits{grid-column:2;display:flex;gap:.5rem;align-items:center;margin-bottom:.4rem}"
        ".query figure{outline:2px solid #4a7dff;outline-offset:2px}"
        ".model{width:70px;color:#7c7f8a;font-size:12px;flex-shrink:0}"
        "figure{margin:0}img{display:block;height:120px;border-radius:6px;object-fit:cover}"
        ".query img{height:150px}figcaption{font-size:11px;color:#7c7f8a;margin-top:.25rem}"
        "</style><h1>SigLIP-2 vs DINOv2 on your saves</h1>"
        "<p class='sub'>Query on the left (blue). Each model's top-5 visually similar saves on the right. "
        "Judge which row feels like your taste.</p>" + "".join(rows)
    )
    Path(out_path).write_text(html)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/tmp/encoder-eval")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    items = collect_corpus()
    paths = [it["path"] for it in items]
    print(f"corpus: {len(items)} images")
    for src in sorted({it['source'] for it in items}):
        print(f"  {src}: {sum(1 for it in items if it['source'] == src)}")

    results = {"corpus": len(items)}
    orders = {}
    for name, fn in [("siglip2", embed_siglip), ("dinov2", embed_dino)]:
        print(f"embedding with {name}...")
        emb = fn(paths)
        np.save(out / f"{name}.npy", emb)
        _, order = cosine_neighbors(emb)
        orders[name] = order
        r1, n1 = same_group_recall(items, order, 1)
        r5, _ = same_group_recall(items, order, 5)
        tp, nt = tag_precision_at_k(items, order, 5)
        results[name] = {
            "dim": int(emb.shape[1]),
            "same_group_recall@1": round(r1, 3),
            "same_group_recall@5": round(r5, 3),
            "same_group_n": n1,
            "tag_precision@5": round(tp, 3),
            "tagged_thumbs_n": nt,
        }
        print(f"  {name}: {results[name]}")

    (out / "results.json").write_text(json.dumps(results, indent=2))
    build_gallery(items, orders, out / "gallery.html")
    print(f"wrote {out}/results.json and {out}/gallery.html")


if __name__ == "__main__":
    main()
