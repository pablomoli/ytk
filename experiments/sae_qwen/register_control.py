"""Controls on section 52's register axis. NOT registered — disclosure only.

The registered axis separates a video's transcript segments from that video's
enrichment note at held-out AUC 0.995. The gate says the separation is real
and generalizes to unseen videos; it does not say the separated property is
*register*. Two rival readings survive it:

  length   the probe reads document size. Segment chunking caps near ~1,200
           characters and enrichment notes begin above it, so the poles are
           nearly disjoint in length and a classifier seeing only character
           count already scores AUC 0.977. The pre-registration called the two
           "comparable in length" on a median-to-median look; that was wrong,
           and it is the claim that let the design through.
  format   the probe reads chunk-vs-summary, which would make the honest name
           VERBATIM <-> COMPOSED rather than SPOKEN <-> WRITTEN.

Control 1, caliper matching: pair each note with a segment of near-identical
length so that length-alone AUC collapses to chance by construction, then
re-fit. Survival means register; collapse means a length detector.
Control 2, independent judge: Haiku, which never sees a row's kind, labels
segment text for register — a check on the pole definitions themselves.

A voice-memo control (verbatim speech stored as a note, separating register
from format outright) was not available: the corpus holds one such note.

    YTK_VISUAL_INDEX=off uv run python experiments/sae_qwen/register_control.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from paths import DATA

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from semantic_axes import auc  # noqa: E402
from semantic_axes_regrow import SEED, register_pools, run_axis  # noqa: E402

CALIPER = np.log(1.10)  # a match is within 10% on length


def doc_lengths(rows: list[dict], idx: np.ndarray) -> dict[int, int]:
    """True document lengths from Chroma; rows.jsonl carries a 900-char head."""
    from ytk import store

    by_kind: dict[str, list[int]] = defaultdict(list)
    for i in idx:
        by_kind[rows[i]["kind"]].append(int(i))
    coll = {"video": store._videos_collection, "segment": store._segments_collection}
    out: dict[int, int] = {}
    for kind, members in by_kind.items():
        c = coll[kind]()
        for s in range(0, len(members), 500):
            chunk = members[s : s + 500]
            got = c.get(ids=[rows[i]["id"] for i in chunk], include=["documents"])
            found = {k: len(v or "") for k, v in zip(got["ids"], got["documents"])}
            for i in chunk:
                out[i] = found.get(rows[i]["id"], 0)
    return out


def caliper_match(L: np.ndarray, y: np.ndarray, rng) -> np.ndarray:
    """Nearest-length segment for each note, without replacement."""
    notes = np.where(y == 0)[0]
    segs = np.where(y == 1)[0]
    logL = np.log(np.maximum(L, 1))
    used: set[int] = set()
    keep: list[int] = []
    order = notes[np.argsort(logL[notes])[::-1]]  # longest notes first: scarcest matches
    for n in order:
        cand = [s for s in segs if s not in used and abs(logL[s] - logL[n]) <= CALIPER]
        if not cand:
            continue
        best = min(cand, key=lambda s: abs(logL[s] - logL[n]))
        used.add(int(best))
        keep += [int(n), int(best)]
    return np.array(sorted(keep))


def main() -> None:
    rows = [json.loads(x) for x in (DATA / "rows.jsonl").read_text().splitlines()]
    X = np.load(DATA / "vectors.npz")["X"].astype(np.float32)
    X /= np.maximum(np.linalg.norm(X, axis=1, keepdims=True), 1e-9)

    blob = np.load(DATA / "semantic_axes_regrow.npz", allow_pickle=True)
    names = [str(n) for n in blob["names"]]
    v = blob["axes"][names.index("spoken-written")]

    pool, y, groups = register_pools(rows)
    lens = doc_lengths(rows, pool)
    L = np.array([lens[int(i)] for i in pool], dtype=float)
    sp, wr = L[y == 1], L[y == 0]

    rng = np.random.default_rng(SEED)
    sel = caliper_match(L, y, rng)
    ym, Lm = y[sel], L[sel]

    matched, _ = run_axis("spoken-written", X, pool[sel], ym, groups[sel], rng)

    out = {
        "note": "controls on the registered register axis; not gated, not a bar",
        "length_confound": {
            "spoken_p10_median_p90": [
                int(np.percentile(sp, 10)),
                int(np.median(sp)),
                int(np.percentile(sp, 90)),
            ],
            "written_p10_median_p90": [
                int(np.percentile(wr, 10)),
                int(np.median(wr)),
                int(np.percentile(wr, 90)),
            ],
            "length_alone_auc_full": round(auc(-sp, -wr), 4),
            "pearson_proj_vs_log_len": round(float(np.corrcoef(X[pool] @ v, np.log(L))[0, 1]), 4),
        },
        "caliper_matched": {
            "caliper": "within 10% on character length",
            "n_pairs": int((ym == 0).sum()),
            "n_notes_unmatched": int((y == 0).sum() - (ym == 0).sum()),
            "length_alone_auc_matched": round(auc(-Lm[ym == 1], -Lm[ym == 0]), 4),
            "probe_auc_matched": matched["auc"],
            "probe_p_matched": matched["p_value"],
            "null_mean": matched["null_auc_mean"],
        },
    }

    seg_path = DATA / "register_labels_segments.json"
    if seg_path.exists():
        seg = [x for x in json.loads(seg_path.read_text()).values() if "error" not in x]
        doc = [
            x
            for x in json.loads((DATA / "register_labels.json").read_text()).values()
            if "error" not in x
        ]
        out["independent_judge"] = {
            "segments": dict(Counter(x["speech_register"] for x in seg)),
            "doc_notes": dict(Counter(x["speech_register"] for x in doc)),
            "n_segments": len(seg),
            "n_doc_notes": len(doc),
        }
    else:
        out["independent_judge"] = "segment labels not yet available"

    # raw lengths travel with the result: the figure draws the confound as two
    # distributions, which p10/median/p90 cannot reconstruct.
    np.savez_compressed(
        DATA / "register_control.npz",
        len_all=L,
        y_all=y,
        len_matched=Lm,
        y_matched=ym,
    )
    (HERE / "register_control.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
