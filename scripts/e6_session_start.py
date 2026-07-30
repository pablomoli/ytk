"""E6 (#149): session-start bootstrap — voluntary reads vs injected context.

Baseline from history: per ytk session, the vault bootstrap calls actually
made (vault_read hot/index/memories, vault_list, early vault_search) — their
round-trips and result tokens. Arm: a SessionStart hook injecting hot.md +
the ytk memory atoms once, zero round-trips. Also measured: how often the
CLAUDE.md contract was simply skipped — the registered "interesting number".

    uv run --with matplotlib python scripts/e6_session_start.py
"""

from __future__ import annotations

import glob
import json
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from memory_field_audits import figure, footer, save, stamp
from plot_assets import BLUE, GOLD, MARGIN, TEXT, panel_title, style_axes

BOOT_HINTS = ("hot.md", "index.md", "memories", "wiki")
FIRST_N_TOOLS = 15


def toks(text: str) -> int:
    return round(len(text) / 4)


def session_bootstrap(path: str) -> tuple[int, int] | None:
    """(round_trips, result_tokens) for vault bootstrap in the first tools."""
    id_is_boot: dict[str, bool] = {}
    trips = 0
    tokens = 0
    seen_tools = 0
    try:
        for line in open(path, encoding="utf-8", errors="replace"):
            if '"tool_use"' not in line and '"tool_result"' not in line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            for c in (d.get("message") or {}).get("content") or []:
                if not isinstance(c, dict):
                    continue
                if c.get("type") == "tool_use":
                    seen_tools += 1
                    if seen_tools > FIRST_N_TOOLS:
                        return (trips, tokens)
                    name = str(c.get("name", ""))
                    if name.startswith("mcp__ytk__vault_"):
                        arg = json.dumps(c.get("input") or {})
                        boot = name.endswith(("vault_list", "vault_search")) or any(
                            h in arg for h in BOOT_HINTS
                        )
                        if boot:
                            id_is_boot[c.get("id", "")] = True
                            trips += 1
                elif c.get("type") == "tool_result" and id_is_boot.get(c.get("tool_use_id", "")):
                    content = c.get("content")
                    text = json.dumps(content) if not isinstance(content, str) else content
                    tokens += toks(text)
    except OSError:
        return None
    return (trips, tokens)


def injection_cost() -> int:
    """What the SessionStart hook injects: hot.md + the ytk memory atoms."""
    from ytk.vault import _get_brain_path

    brain = _get_brain_path()
    total = 0
    for rel in ("wiki/hot.md", "inbox/memories/users-melocoton-developer-ytk"):
        p = brain / rel
        if p.is_file():
            total += toks(p.read_text(encoding="utf-8", errors="replace"))
        elif p.is_dir():
            for f in p.glob("*.md"):
                total += toks(f.read_text(encoding="utf-8", errors="replace"))
    return total


def main() -> None:
    files = sorted(
        glob.glob(os.path.expanduser("~/.claude/projects/-Users-melocoton-Developer-ytk/*.jsonl")),
        key=os.path.getmtime,
        reverse=True,
    )[:60]
    rows = [r for r in (session_bootstrap(f) for f in files) if r is not None]
    trips = np.array([r[0] for r in rows], dtype=float)
    tokens = np.array([r[1] for r in rows], dtype=float)
    did = trips > 0
    skipped = 1 - did.mean()
    inj = injection_cost()

    print(f"{len(rows)} recent ytk sessions analyzed")
    print(f"bootstrap skipped entirely: {skipped:.0%} of sessions (the registered number)")
    print(
        f"when done: median {np.median(trips[did]):.0f} round-trips, "
        f"median {np.median(tokens[did]):.0f} result tokens"
    )
    print(f"injection arm: {inj} tokens, 0 round-trips, every session")

    meta = (
        f"{len(rows)} recent ytk sessions · CLAUDE.md bootstrap skipped in {skipped:.0%} · "
        f"when followed: median {np.median(trips[did]):.0f} round-trips / {np.median(tokens[did]):.0f} tokens · "
        f"hook injection: {inj} tokens, 0 trips, 100% coverage"
    )
    fig, top_frac = figure(
        10.5,
        6.6,
        10,
        "#149 E6 — session-start context",
        "Voluntary vault bootstrap vs SessionStart injection",
        meta,
    )
    ax = fig.add_axes([MARGIN + 0.05, 0.16, 1 - 2 * MARGIN - 0.09, top_frac - 0.20])
    style_axes(ax)
    order = np.argsort(tokens)[::-1]
    x = np.arange(len(rows))
    ax.bar(
        x,
        tokens[order],
        0.8,
        color=BLUE,
        alpha=0.85,
        label="bootstrap result tokens (per session, first 15 tools)",
    )
    ax.axhline(
        inj,
        color=GOLD,
        linewidth=1.2,
        linestyle="--",
        label=f"injection cost ({inj} tokens, every session)",
    )
    ax.set_xlabel("session (sorted by bootstrap spend; zero bars = contract skipped)")
    ax.set_ylabel("tokens")
    ax.legend(loc="upper right", frameon=False, labelcolor=TEXT, fontsize=9)
    panel_title(
        ax, "Zero-height bars are sessions that started blind — injection's real payoff is coverage"
    )
    footer(
        fig,
        f"{stamp()} · bootstrap = ytk vault reads of hot/index/memories in the first {FIRST_N_TOOLS} tool calls · "
        "counts chars/4 · confound: injection cost recurs in 100% of sessions including trivial ones — net token "
        "direction depends on the skip rate, and the quality effect of never starting blind is unmeasured here",
    )
    save(fig, "e6-session-start.png")


if __name__ == "__main__":
    main()
