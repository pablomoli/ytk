"""Lock in CSS shrinkage by lowering the ceilings in web/css-budget.json (#136).

Hand-written CSS is on a one-way ratchet: tests/test_css_budget.py fails when a
tracked file exceeds its recorded ceiling, and also when it drops below — the
gain must be locked in here so it cannot quietly regrow. This script only ever
lowers ceilings; raising one is a deliberate human act done by editing the JSON
in a reviewed diff, never by tooling.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BUDGET = REPO / "web" / "css-budget.json"


def main() -> int:
    ceilings: dict[str, int] = json.loads(BUDGET.read_text())
    grew: list[str] = []
    lowered: list[str] = []
    for rel, ceiling in ceilings.items():
        lines = len((REPO / "web" / rel).read_text().splitlines())
        if lines > ceiling:
            grew.append(f"{rel}: {lines} lines exceeds ceiling {ceiling}")
        elif lines < ceiling:
            ceilings[rel] = lines
            lowered.append(f"{rel}: {ceiling} -> {lines}")
    if grew:
        print("refusing to ratchet: CSS grew (#136 — the ratchet only goes down)")
        print("\n".join(grew))
        return 1
    if lowered:
        BUDGET.write_text(json.dumps(ceilings, indent=2, sort_keys=True) + "\n")
        print("\n".join(lowered))
    else:
        print("ceilings already match")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
