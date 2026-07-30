"""E6 (#149): the injected brief is fixed-shape and hard-capped."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from session_start_brief import BUDGET, distill


def test_distill_caps_at_budget_and_leads_with_state():
    brief = distill("state " * 400, "hot " * 800)
    assert len(brief) <= BUDGET
    assert brief.startswith("## ytk state")


def test_distill_empty_inputs_yield_empty_brief():
    assert distill("", "") == ""


def test_distill_hot_only_still_fits():
    brief = distill("", "hot cache line\n" * 300)
    assert 0 < len(brief) <= BUDGET
    assert brief.startswith("## hot cache")
