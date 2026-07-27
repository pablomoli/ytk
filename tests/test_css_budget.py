"""Hand-written CSS is on a one-way ratchet (#136).

web/css-budget.json records a line ceiling per tracked stylesheet. Growth fails
outright: new chrome styles itself with Tailwind utilities against the theme
tokens, never with new rules in these files. Shrinking below the ceiling also
fails — run scripts/ratchet_css.py to lock the gain in, so deleted weight
cannot quietly come back. theme.css is exempt: it is the deliberately bespoke
identity layer.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BUDGET = REPO / "web" / "css-budget.json"


def test_css_never_grows() -> None:
    ceilings: dict[str, int] = json.loads(BUDGET.read_text())
    assert ceilings, "css-budget.json lists no files"
    for rel, ceiling in ceilings.items():
        lines = len((REPO / "web" / rel).read_text().splitlines())
        assert lines <= ceiling, (
            f"{rel} grew to {lines} lines (ceiling {ceiling}). The ratchet only "
            f"goes down (#136): style new work with Tailwind utilities, or cut "
            f"an equal weight of existing CSS first."
        )
        assert lines == ceiling, (
            f"{rel} shrank to {lines} lines (ceiling {ceiling}). Lock it in: "
            f"uv run python scripts/ratchet_css.py"
        )
