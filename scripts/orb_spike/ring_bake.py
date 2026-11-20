"""Spike helper: bake the pending ring from a queue snapshot (queue.json, a
GET of /api/queue). Writes ring.json (one row per pending item, newest first)
and ring.jpg (square crops of the covers already cached in ~/.ytk/covers).
Read-only on the queue and the cover cache: nothing is downloaded."""

import hashlib
import json
import math
from pathlib import Path

from PIL import Image

here = Path.home() / ".ytk" / "orb-spike"
items = json.loads((here / "queue.json").read_text())["items"]
covers = Path.home() / ".ytk" / "covers"
ATLAS = 4096


def cover(url: str) -> Path:
    return covers / (hashlib.sha1(url.encode(), usedforsecurity=False).hexdigest()[:20] + ".jpg")


# newest first; undated last, queue order inside a day
items.sort(key=lambda i: (i.get("shared_at") or "", -i["n"]), reverse=True)
have = [i for i in items if cover(i["url"]).exists()]
cols = math.ceil(math.sqrt(len(have)))
cell = ATLAS // cols
sheet = Image.new("RGB", (ATLAS, ATLAS), (10, 10, 12))
slot: dict[str, int] = {}
bad = 0
for i in have:
    try:
        im = Image.open(cover(i["url"])).convert("RGB")
    except Exception:
        bad += 1
        continue
    w, h = im.size
    s = min(w, h)
    im = im.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s)).resize(
        (cell, cell), Image.LANCZOS
    )
    k = len(slot)
    sheet.paste(im, ((k % cols) * cell, (k // cols) * cell))
    slot[i["url"]] = k
sheet.save(here / "ring.jpg", quality=82)


def text(i: dict) -> str:
    t = (i.get("title") or i.get("text") or "").strip().replace("\n", " ")
    return t[:180]


rows = [
    {
        "u": i["url"],
        "s": i.get("source") or "",
        "a": i.get("author") or "",
        "t": text(i),
        "d": i.get("shared_at") or "",
        "q": 1 if i.get("reflection_question") and not i.get("reflection_answered") else 0,
        "k": slot.get(i["url"], -1),
    }
    for i in items
]
(here / "ring.json").write_text(
    json.dumps({"cols": cols, "cell": cell, "size": ATLAS, "items": rows})
)
print(
    f"{len(rows)} pending, {len(slot)} with a cover in the atlas ({bad} unreadable), {cols} cols x {cell}px"
)
print("with text:", sum(bool(r["t"]) for r in rows), "open question:", sum(r["q"] for r in rows))
