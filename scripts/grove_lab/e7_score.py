"""E7 scoring — post-run only, per the preregistered bands.

Refuses to score a partial run (showing correctness mid-run would break
the no-feedback contract); --partial exists for salvage analysis after an
aborted session and is labeled as such in the output.

Reporting order follows the preregistration: the three PRIMARY task-1
exposures are the only uncontaminated semantic observations and lead the
report; repeats are secondary learning/consistency data; adjacency- and
payload-construct trials never pool; task 2 gates only the rendering
claim; task 3 is exploratory. Exact binomial tails are conditional
summaries for a single-subject case study, not population inference.

Usage (after the run):
    uv run --extra dev python -m scripts.grove_lab.e7_score
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

GROVE_DIR = Path.home() / ".ytk" / "grove"

BANDS = {3: "clear read", 2: "weak", 1: "no read", 0: "no read"}


def _binom_tail(k: int, n: int, p: float) -> float:
    from math import comb

    return sum(comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k, n + 1))


def _cell(trials, responses, answers) -> dict:
    correct = sum(1 for t in trials if responses[t["trial"]]["choice"] == answers[t["trial"]])
    conf = [responses[t["trial"]]["confidence"] for t in trials]
    rt = [responses[t["trial"]]["rt_ms"] for t in trials]
    return {
        "n": len(trials),
        "correct": correct,
        "mean_confidence": round(sum(conf) / len(conf), 2) if conf else None,
        "median_rt_ms": sorted(rt)[len(rt) // 2] if rt else None,
    }


def score(grove_dir: Path = GROVE_DIR, partial: bool = False) -> dict:
    manifest = json.loads((grove_dir / "e7-manifest.json").read_text())
    key = json.loads((grove_dir / "e7-answer-key.json").read_text())
    if key["public_sha256"] != manifest["sha256"]:
        raise SystemExit("answer key does not match the manifest")
    rows = [
        json.loads(line)
        for line in (grove_dir / "e7-responses.jsonl").read_text().splitlines()
        if line.strip()
    ]
    responses = {r["trial"]: r for r in rows if r.get("manifest_sha") == manifest["sha256"]}
    scored = [t for t in manifest["trials"] if t["task"] != "practice"]
    missing = [t["trial"] for t in scored if t["trial"] not in responses]
    if missing and not partial:
        raise SystemExit(
            f"run incomplete ({len(missing)} unanswered: {missing[:4]}...); "
            "scoring now would break the no-feedback contract. "
            "Use --partial only for salvage analysis of an aborted session."
        )
    scored = [t for t in scored if t["trial"] in responses]
    answers = key["answers"]

    t1 = [t for t in scored if t["task"] == "semantic-readback"]
    t2 = [t for t in scored if t["task"] == "topology-invariance"]
    t3 = [t for t in scored if t["task"] == "identification-exploratory"]

    per_bucket = {}
    for bucket in sorted({t["bucket"] for t in t1}):
        bt = [t for t in t1 if t["bucket"] == bucket]
        cell = _cell(bt, responses, answers)
        cell["band"] = BANDS.get(cell["correct"], "?") if cell["n"] == 3 else "partial"
        cell["construct"] = bt[0]["construct"]
        per_bucket[bucket] = cell

    result = {
        "manifest_sha": manifest["sha256"],
        "partial": bool(missing),
        "semantic_readback": {
            "primary": _cell([t for t in t1 if t.get("primary")], responses, answers),
            "secondary": _cell([t for t in t1 if not t.get("primary")], responses, answers),
            "adjacency": _cell(
                [t for t in t1 if t["construct"] == "adjacency"], responses, answers
            ),
            "payload": _cell([t for t in t1 if t["construct"] == "payload"], responses, answers),
            "per_bucket": per_bucket,
        },
        "topology_invariance": _cell(t2, responses, answers),
        "identification_exploratory": _cell(t3, responses, answers),
    }
    # conditional binomial tails (single-subject summaries, not inference)
    sr = result["semantic_readback"]
    for name, cell, p0 in (
        ("primary", sr["primary"], 0.5),
        ("adjacency", sr["adjacency"], 0.5),
        ("topology_invariance", result["topology_invariance"], 0.5),
        ("identification_exploratory", result["identification_exploratory"], 1 / 3),
    ):
        if cell["n"]:
            cell["binom_tail"] = round(_binom_tail(cell["correct"], cell["n"], p0), 4)
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--partial", action="store_true", help="salvage analysis of an aborted session")
    args = ap.parse_args()
    result = score(partial=args.partial)
    out = Path(__file__).resolve().parents[2] / "docs" / "grove-lab" / "e7-results.json"
    out.write_text(json.dumps(result, indent=1))
    # archive the raw log next to the results (preregistration amendment 3)
    archive = out.parent / "e7-responses.jsonl"
    archive.write_text((GROVE_DIR / "e7-responses.jsonl").read_text())
    print(json.dumps(result, indent=1))
    print(f"\nwrote {out} and archived responses")


if __name__ == "__main__":
    main()
