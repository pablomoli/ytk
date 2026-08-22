"""Haiku register + code-bearing labels for every doc note (section 52).

Section 48 built both thin axes out of source folders: a note was WRITTEN only
if it came from sources/web/ (21 of them), and CODE only if a regex found a
fence in a 900-character head (10 of them). Both are proxies for the property
they claim to measure, which is why both poles were unusable. This asks Haiku
for the property directly, over the full note text pulled from Chroma rather
than the cached head, so a note that turns to code on line 40 is still visible.

    YTK_VISUAL_INDEX=off uv run python experiments/sae_qwen/register_labels.py \
        --sample 300                # feasibility pilot, stratified by source
    YTK_VISUAL_INDEX=off uv run python experiments/sae_qwen/register_labels.py

Labels cache to the run store keyed by row id; reruns resume and only call
Haiku for notes not already labeled.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from paths import DATA
from pydantic import BaseModel

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

OUT = DATA / "register_labels.json"
LABEL_CHARS = 6000
SEED = 52

SYSTEM = (
    "You label notes from a personal knowledge vault on two independent "
    "properties. Judge only what the text itself shows; you are never told "
    "where the note came from, and you must not guess a source.\n\n"
    "REGISTER — how the words were produced:\n"
    "  spoken: a transcript or recording of talk. Hallmarks: filler and "
    "restarts, direct address to a listener, run-on sentences, no headings or "
    "lists, references to what is on screen.\n"
    "  written: composed to be read. Hallmarks: headings, lists, punctuation "
    "that survives editing, footnotes, links, deliberate paragraphing.\n\n"
    "CODE-BEARING — whether the note substantively concerns software "
    "implementation: it shows code, names specific APIs, commands, files or "
    "libraries, or discusses how something is built. A passing mention of "
    "'AI' or 'an app' is NOT code-bearing; a discussion of a specific tool's "
    "flags or a shown snippet is.\n\n"
    "Give confidence high only when the text is unambiguous. Say low when the "
    "excerpt is too short, too generic, or genuinely mixed."
)


class Label(BaseModel):
    # not `register`: that name shadows ABCMeta.register on the model class
    # and perturbs the JSON schema Haiku is forced against.
    speech_register: str
    register_confidence: str
    code_bearing: bool
    code_confidence: str
    rationale: str


def fetch_texts(rows: list[dict], idx: list[int]) -> dict[int, str]:
    """Full documents from Chroma for the given doc rows, by kind."""
    from ytk import store

    by_kind: dict[str, list[int]] = defaultdict(list)
    for i in idx:
        by_kind[rows[i]["kind"]].append(i)

    coll = {
        "video": store._videos_collection,
        "memory": store._memories_collection,
        "segment": store._segments_collection,
    }
    out: dict[int, str] = {}
    for kind, members in by_kind.items():
        if kind not in coll:
            continue
        c = coll[kind]()
        for s in range(0, len(members), 200):
            chunk = members[s : s + 200]
            got = c.get(ids=[rows[i]["id"] for i in chunk], include=["documents"])
            found = dict(zip(got["ids"], got["documents"]))
            for i in chunk:
                out[i] = found.get(rows[i]["id"]) or rows[i]["text"]
    return out


def stratified(rows: list[dict], idx: list[int], n: int, rng) -> list[int]:
    """Proportional sample by source, with every source represented."""
    groups: dict[str, list[int]] = defaultdict(list)
    for i in idx:
        groups[rows[i]["source"]].append(i)
    pick: list[int] = []
    for src, members in sorted(groups.items()):
        take = min(len(members), max(5, round(n * len(members) / len(idx))))
        pick += list(rng.choice(members, size=take, replace=False))
    return [int(i) for i in pick]


def main() -> None:
    import numpy as np

    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=0, help="pilot size (0 = all notes)")
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument(
        "--segments",
        action="store_true",
        help="label transcript segments instead of doc notes (register control)",
    )
    a = ap.parse_args()

    from ytk.sdk import structured

    rows = [json.loads(x) for x in (DATA / "rows.jsonl").read_text().splitlines()]
    doc_idx = [i for i, r in enumerate(rows) if (r["kind"] == "segment") == a.segments]
    rng = np.random.default_rng(SEED)
    target = stratified(rows, doc_idx, a.sample, rng) if a.sample else doc_idx

    # segment labels are a control, kept out of the file the registered runner
    # reads so they cannot enter a pole or the disclosed label distribution.
    out = DATA / ("register_labels_segments.json" if a.segments else OUT.name)
    cache = json.loads(out.read_text()) if out.exists() else {}
    todo = [i for i in target if rows[i]["id"] not in cache]
    print(
        f"doc notes {len(doc_idx)} | target {len(target)} | cached {len(target) - len(todo)} | to label {len(todo)}"
    )
    if not todo:
        print("nothing to label")
        return

    texts = fetch_texts(rows, todo)
    print(f"fetched full text for {len(texts)} notes")

    def label_one(i: int) -> tuple[str, dict]:
        r = rows[i]
        body = (texts.get(i) or r["text"])[:LABEL_CHARS]
        try:
            res = structured(
                SYSTEM,
                f"Title: {r['title'][:120]}\n\nText:\n{body}\n\n"
                "Label REGISTER (spoken|written) and CODE-BEARING (true|false), "
                "each with confidence high|medium|low.",
                Label,
                max_tokens=400,
            )
            return r["id"], res.model_dump()
        except Exception as e:  # a failed call must not poison the pole
            return r["id"], {"error": str(e)[:200]}

    def save() -> None:
        # write-then-rename: an interrupt mid-write must not truncate hours of
        # labels into a half-file that the next run reads as valid cache.
        tmp = out.with_suffix(".tmp")
        tmp.write_text(json.dumps(cache, indent=0))
        tmp.replace(out)

    t0 = time.time()
    done = 0
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for cid, res in ex.map(label_one, todo):
            cache[cid] = res
            done += 1
            if done % 25 == 0:
                save()
                rate = done / (time.time() - t0)
                print(
                    f"  {done}/{len(todo)}  {rate:.2f}/s  eta {(len(todo) - done) / rate / 60:.1f}m",
                    flush=True,
                )
    elapsed = time.time() - t0
    save()

    ok = {k: v for k, v in cache.items() if "error" not in v}
    errs = len(cache) - len(ok)
    print(
        f"\nlabeled {done} in {elapsed / 60:.1f}m ({done / elapsed:.2f}/s, {elapsed / max(done, 1):.1f}s/note)"
    )
    print(f"errors: {errs}")
    print("speech register:", Counter(v["speech_register"] for v in ok.values()).most_common())
    print(
        "register confidence:", Counter(v["register_confidence"] for v in ok.values()).most_common()
    )
    print("code-bearing:", Counter(v["code_bearing"] for v in ok.values()).most_common())
    print("code confidence:", Counter(v["code_confidence"] for v in ok.values()).most_common())

    hi = {k: v for k, v in ok.items() if v["register_confidence"] != "low"}
    hic = {k: v for k, v in ok.items() if v["code_confidence"] != "low"}
    print("\nconfidence-filtered poles (this run's target only):")
    print("  written:", sum(1 for v in hi.values() if v["speech_register"] == "written"))
    print("  spoken: ", sum(1 for v in hi.values() if v["speech_register"] == "spoken"))
    print("  code:   ", sum(1 for v in hic.values() if v["code_bearing"]))
    print("  prose:  ", sum(1 for v in hic.values() if not v["code_bearing"]))

    if a.sample:
        scale = len(doc_idx) / len(target)
        print(f"\nprojected to all {len(doc_idx)} notes (x{scale:.1f}):")
        print(
            f"  written ~{sum(1 for v in hi.values() if v['speech_register'] == 'written') * scale:.0f}"
        )
        print(f"  code    ~{sum(1 for v in hic.values() if v['code_bearing']) * scale:.0f}")
        print(f"  full-run wall clock ~{elapsed * scale / 3600:.1f}h at {a.workers} workers")


if __name__ == "__main__":
    main()
