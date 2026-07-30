"""E3 (#149): MCP surface audit — usage vs definition cost per ytk tool.

Parses every session JSONL under ~/.claude/projects (the ytk MCP server is
registered globally), counts invocations and errors per mcp__ytk__* tool, and
estimates each tool's definition cost (name + docstring + input schema,
chars/4). Figure: e3-tool-usage.png — the kill/merge shortlist falls out of
the high-cost / low-use quadrant.

    uv run --with matplotlib python scripts/e3_tool_audit.py
"""

from __future__ import annotations

import glob
import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from memory_field_audits import figure, footer, save, stamp
from plot_assets import BLUE, GOLD, MARGIN, RED, TEXT, panel_title, style_axes


def scan_sessions() -> tuple[Counter, Counter, int]:
    calls: Counter = Counter()
    errors: Counter = Counter()
    id_to_tool: dict[str, str] = {}
    sessions = 0
    for f in glob.glob(os.path.expanduser("~/.claude/projects/*/*.jsonl")):
        sessions += 1
        try:
            for line in open(f, encoding="utf-8", errors="replace"):
                if "mcp__ytk__" not in line and "tool_result" not in line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                for c in (d.get("message") or {}).get("content") or []:
                    if not isinstance(c, dict):
                        continue
                    if c.get("type") == "tool_use" and str(c.get("name", "")).startswith(
                        "mcp__ytk__"
                    ):
                        name = c["name"].removeprefix("mcp__ytk__")
                        calls[name] += 1
                        id_to_tool[c.get("id", "")] = name
                    elif c.get("type") == "tool_result" and c.get("is_error"):
                        tool = id_to_tool.get(c.get("tool_use_id", ""))
                        if tool:
                            errors[tool] += 1
        except OSError:
            continue
    return calls, errors, sessions


def definition_costs() -> dict[str, int]:
    """Approx tokens each tool's definition occupies in every session."""
    import asyncio

    from ytk import mcp_server

    tools = asyncio.run(mcp_server.app.list_tools())
    out = {}
    for t in tools:
        blob = t.name + (t.description or "") + json.dumps(t.inputSchema or {})
        out[t.name] = round(len(blob) / 4)
    return out


def main() -> None:
    calls, errors, sessions = scan_sessions()
    defs = definition_costs()
    names = sorted(defs, key=lambda n: -calls.get(n, 0))
    total_calls = sum(calls.values()) or 1

    print(f"{sessions} session files scanned · {total_calls} ytk tool calls")
    print(f"{'tool':<22}{'calls':>7}{'share':>8}{'errors':>8}{'def-tok':>9}")
    cum = 0
    for n in names:
        cum += calls.get(n, 0)
        print(
            f"{n:<22}{calls.get(n, 0):>7}{calls.get(n, 0) / total_calls:>8.0%}"
            f"{errors.get(n, 0):>8}{defs[n]:>9}"
        )
    top3 = sum(calls.get(n, 0) for n in names[:3]) / total_calls
    dead = [n for n in names if calls.get(n, 0) <= 2]
    always_paid = sum(defs.values())
    print(f"\ntop-3 tools carry {top3:.0%} of calls (registered: ~80%)")
    print(f"definition cost paid every session: ~{always_paid} tokens across {len(defs)} tools")
    print(f"kill/merge quadrant (<=2 lifetime calls): {', '.join(dead) or 'none'}")

    meta = (
        f"{sessions} session files, {total_calls} calls · top-3 tools carry {top3:.0%} "
        f"(registered ~80%) · every session pays ~{always_paid} def tokens for {len(defs)} tools · "
        f"<=2 lifetime calls: {len(dead)} tools"
    )
    fig, top_frac = figure(
        10.5,
        6.6,
        9,
        "#149 E3 — MCP surface audit",
        "Tool usage vs definition cost, all sessions",
        meta,
    )
    ax = fig.add_axes([MARGIN + 0.06, 0.16, 1 - 2 * MARGIN - 0.10, top_frac - 0.20])
    style_axes(ax)
    for n in names:
        c = calls.get(n, 0)
        color = RED if c <= 2 else (GOLD if errors.get(n, 0) > 0.15 * max(c, 1) else BLUE)
        ax.scatter(defs[n], c + 0.5, s=42, color=color, edgecolors="none", zorder=3)
        ax.annotate(
            n, (defs[n], c + 0.5), textcoords="offset points", xytext=(6, 3), fontsize=8, color=TEXT
        )
    ax.set_yscale("log")
    ax.set_xlabel("definition cost (approx tokens, paid every session)")
    ax.set_ylabel("lifetime calls (log, +0.5)")
    panel_title(ax, "Red: <=2 lifetime calls (kill/merge candidates) · gold: error-prone")
    footer(
        fig,
        f"{stamp()} · definition cost = name + docstring + input schema at chars/4 · confound: JSONL history "
        "spans tool ages unevenly — newer tools have had less time to accrue calls; check birth dates before killing",
    )
    save(fig, "e3-tool-usage.png")


if __name__ == "__main__":
    main()
