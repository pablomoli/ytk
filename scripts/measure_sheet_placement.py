"""Sheet placement measurement (#212, the one number the model does not settle).

Protocol (e501375 lineage): for every bundle on disk that carries a contact
sheet, build the packet under each sheet placement (none, openable, shown),
run the enricher's real prompt through the SDK REPS times per condition, and
count structured-output failures. Nothing is written to the ledger or the
evidence tree; views are built in memory, attempts never saved.

    uv run python scripts/measure_sheet_placement.py [reps] [out.json]

Calls = bundles x 3 x reps. Say the number before running it.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from ytk import sdk
from ytk.attempt import Attempt
from ytk.enrich import build_system
from ytk.enricher import _V2_ADDENDUM, ENRICHER_MODEL, SCHEMA_V2, _bias_source, build_prompt
from ytk.evidence import evidence_dir, load_bundle
from ytk.view import Budget, build_view

CONDITIONS = ("none", "openable", "shown")


def pool() -> list[tuple[int, Path]]:
    out: list[tuple[int, Path]] = []
    for p in sorted(evidence_dir().glob("*.json")):
        if not p.stem.isdigit():
            continue
        b = load_bundle(p)
        if b.sheet and Path(b.sheet).is_file():
            out.append((int(p.stem), p))
    return out


def one_call(item_id: int, path: Path, cond: str) -> dict[str, object]:
    v = build_view(item_id, path, Budget(sheet=cond))
    a = Attempt(item_id=item_id, n=1, view_hash=v.view_hash, take=None, previous_draft=None)
    system = build_system(_bias_source(v)) + _V2_ADDENDUM
    user = build_prompt(v, a)
    t0 = time.monotonic()
    row: dict[str, object] = {
        "item": item_id,
        "condition": cond,
        "shown": [u["id"] for u in v.shown],
        "openable": len(v.openable),
        "mounts": v.mounts,
    }
    try:
        res = sdk.call_structured(system, user, SCHEMA_V2, add_dirs=v.mounts, model=ENRICHER_MODEL)
        row.update(ok=True, tokens=res.tokens, seconds=round(time.monotonic() - t0, 1))
        concepts = res.data.get("key_concepts") if isinstance(res.data, dict) else None
        row["frame_cites"] = sum("[frame:" in c or "[sheet]" in c for c in (concepts or []))
    except Exception as exc:  # the failure is the measurement
        msg = str(exc)
        row.update(
            ok=False,
            structured="structured" in msg.lower(),
            error=msg[:160],
            seconds=round(time.monotonic() - t0, 1),
        )
    return row


def main() -> None:
    reps = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("sheet-placement.json")
    items = pool()
    print(
        f"{len(items)} bundles with a sheet: {[i for i, _ in items]}; {len(items) * 3 * reps} calls"
    )
    rows: list[dict[str, object]] = []
    for rep in range(reps):
        for item_id, path in items:
            for cond in CONDITIONS:
                row = one_call(item_id, path, cond)
                row["rep"] = rep
                rows.append(row)
                print(json.dumps(row))
                out.write_text(json.dumps(rows, indent=1))
    print()
    print(
        f"{'condition':10} {'calls':>5} {'ok':>3} {'structured fail':>15} {'other fail':>10} {'frame cites':>11}"
    )
    for cond in CONDITIONS:
        rs = [r for r in rows if r["condition"] == cond]
        ok = sum(1 for r in rs if r["ok"])
        sf = sum(1 for r in rs if not r["ok"] and r.get("structured"))
        cites = sum(int(r.get("frame_cites") or 0) for r in rs)
        print(f"{cond:10} {len(rs):>5} {ok:>3} {sf:>15} {len(rs) - ok - sf:>10} {cites:>11}")


if __name__ == "__main__":
    main()
