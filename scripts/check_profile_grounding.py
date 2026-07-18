#!/usr/bin/env python3
"""Fail closed when a rendered profile contains ungrounded or stale claims."""

from __future__ import annotations

import argparse
from pathlib import Path

from ytk.profile_grounding import check_profile_grounding
from ytk.vault import _get_brain_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "profile",
        nargs="?",
        type=Path,
        default=_get_brain_path() / "me" / "profile.md",
        help="rendered profile (default: configured vault me/profile.md)",
    )
    args = parser.parse_args()
    errors = check_profile_grounding(args.profile)
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print(f"PASS: {args.profile} is evidence-grounded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
