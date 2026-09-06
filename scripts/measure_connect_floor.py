"""Top-1 non-self cosine on connect's query path, 30 random content notes.

The number CANDIDATE_FLOOR is pinned to. Runs against the live store and
the live vault; prints the distribution for the shipped path (thesis +
one query per key concept, unioned) and for the old blob path on the same
notes, then how many candidates each floor and each relative rule would
admit. Usage: uv run python scripts/measure_connect_floor.py [seed] [n]
"""

from __future__ import annotations

import random
import re
import statistics
import sys
import time
from pathlib import Path

from ytk import connect, vault


def parse(p: Path) -> tuple[str | None, str, str, list[str]]:
    text = p.read_text(encoding="utf-8")
    url = re.search(r"^url:\s*(\S+)", text, re.MULTILINE)
    _, thesis = connect._note_identity(p, p.stem, "")  # pyright: ignore[reportPrivateUsage]
    m = re.search(r"^## Summary\s*\n+(.+?)(?:\n## |\Z)", text, re.MULTILINE | re.DOTALL)
    summary = " ".join(m.group(1).split()) if m else ""
    m = re.search(r"^## Key Concepts\s*\n(.+?)(?:\n## |\Z)", text, re.MULTILINE | re.DOTALL)
    bullets = m.group(1).splitlines() if m else []
    concepts = [ln[2:].strip() for ln in bullets if ln.startswith("- ")]
    return url.group(1) if url else None, thesis, summary, concepts


def quartiles(xs: list[float]) -> str:
    xs = sorted(xs)
    n = len(xs)
    return (
        f"min {xs[0]:.3f} p25 {xs[n // 4]:.3f} median {statistics.median(xs):.3f} "
        f"p75 {xs[3 * n // 4]:.3f} max {xs[-1]:.3f}"
    )


def main() -> None:
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 210
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    brain = vault.get_brain_path()
    notes = sorted(
        p for sub in ("youtube", "instagram", "web") for p in (brain / "sources" / sub).glob("*.md")
    )
    random.seed(seed)
    sample = random.sample(notes, n)

    connect.CANDIDATE_FLOOR = 0.0
    connect.MAX_CANDIDATES = 8
    union_tops: list[list[float]] = []
    blob_tops: list[float] = []
    t0 = time.time()
    for p in sample:
        url, thesis, summary, concepts = parse(p)
        if not thesis:
            continue
        union = connect.find_candidates(
            connect.build_queries(thesis, concepts),
            exclude_media_id=None,
            exclude_url=url,
            exclude_path=p,
        )
        blob = connect.find_candidates(
            [("blob", f"{thesis}\n\n{summary}")],
            exclude_media_id=None,
            exclude_url=url,
            exclude_path=p,
        )
        u1 = union[0].cosine if union else 0.0
        b1 = blob[0].cosine if blob else 0.0
        print(
            f"{p.parent.name:9} {p.stem[:44]:44} concepts={len(concepts):2} union={u1:.3f} blob={b1:.3f}"
        )
        if union:
            union_tops.append([c.cosine for c in union[:5]])
        if blob:
            blob_tops.append(b1)
    print(f"\n{time.time() - t0:.0f}s for {len(sample)} notes")
    print("union top-1:", quartiles([t[0] for t in union_tops]))
    print("blob  top-1:", quartiles(blob_tops))
    for delta in (0.05, 0.08, 0.10):
        admitted = [sum(1 for c in t if c >= t[0] - delta) for t in union_tops]
        print(
            f"relative {delta}: mean admitted {statistics.mean(admitted):.2f}, {sorted(admitted)}"
        )
    for floor in (0.45, 0.48, 0.50, 0.52, 0.55):
        admitted = [sum(1 for c in t if c >= floor) for t in union_tops]
        print(
            f"floor {floor}: notes with any {sum(a > 0 for a in admitted)}/{len(admitted)}, "
            f"mean admitted {statistics.mean(admitted):.2f}"
        )


if __name__ == "__main__":
    main()
