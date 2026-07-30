"""E2 (#149): progressive disclosure — tokens per retrieval cycle, fat vs layered.

Replays real vault_search queries (harvested from session JSONLs into
~/.ytk/e2_queries.json — kept local, the repo is public) under two contracts:

  fat:     vault_search text (excerpts) + vault_read of the top hit's raw file
  layered: vault_search_index stubs     + vault_fetch of the top hit's stored text

Counts are chars/4 — no API credentials on this machine, and the
approximation cancels in a two-arm ratio. Figure: e2-progressive-disclosure.png.

    uv run --with matplotlib python scripts/e2_disclosure.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from memory_field_audits import figure, footer, save, stamp
from plot_assets import BLUE, MARGIN, RED, TEXT, panel_title, style_axes

QUERIES_PATH = Path.home() / ".ytk" / "e2_queries.json"
N = 5  # matches the default vault_search the sessions actually ran


def harvest() -> list[str]:
    import glob
    import os

    files = sorted(
        glob.glob(os.path.expanduser("~/.claude/projects/*/*.jsonl")),
        key=os.path.getmtime,
        reverse=True,
    )
    queries: list[str] = []
    seen: set[str] = set()
    for f in files:
        if len(queries) >= 20:
            break
        try:
            for line in open(f, encoding="utf-8", errors="replace"):
                if '"mcp__ytk__vault_search"' not in line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                for c in (d.get("message") or {}).get("content") or []:
                    if (
                        isinstance(c, dict)
                        and c.get("type") == "tool_use"
                        and c.get("name") == "mcp__ytk__vault_search"
                    ):
                        q = (c.get("input") or {}).get("query", "").strip()
                        if q and q.lower() not in seen:
                            seen.add(q.lower())
                            queries.append(q)
        except OSError:
            continue
    return queries[:20]


def fat_search_text(results) -> str:
    lines = []
    for r in results:
        lines.append(
            f"[{r.type}] {r.title}  ({(1 - r.distance):.0%} match)\n{r.excerpt}\nsource: {r.source}"
        )
    return "\n\n".join(lines) if lines else "No results found."


def index_text(results) -> str:
    from ytk.store import memory_captured_at

    return "\n".join(
        f"{(1 - r.distance):.0%}  [{r.type}] {r.doc_id}  {memory_captured_at(None, r.doc_id) or '-'}"
        for r in results
    )


def raw_file_text(top) -> str | None:
    """What vault_read of the top hit costs today: the raw note file."""
    from ytk.vault import _get_brain_path

    brain = _get_brain_path()
    if top.type == "memory":
        p = Path(top.source)
        return p.read_text(encoding="utf-8", errors="replace") if p.exists() else None
    for p in (brain / "sources" / "youtube").glob("*.md"):
        head = p.read_text(encoding="utf-8", errors="replace")
        if top.doc_id in head[:400]:
            return head
    return None


def main() -> None:
    from ytk.store import fetch_docs, search_all

    if QUERIES_PATH.exists():
        queries = json.loads(QUERIES_PATH.read_text())
    else:
        queries = harvest()
        QUERIES_PATH.write_text(json.dumps(queries, indent=1))
    print(f"{len(queries)} replayed queries (local file, not committed)")

    # No API credentials on this machine (enrichment rides the Agent SDK's
    # subscription auth), so counts are chars/4 — a ratio between two arms of
    # the same text distribution, where the approximation cancels out.
    def toks(text: str) -> int:
        return round(len(text) / 4)

    rows = []
    for q in queries:
        results = search_all(q, n=N)
        if not results:
            continue
        top = results[0]
        raw = raw_file_text(top)
        fetched = fetch_docs([top.doc_id])
        if raw is None or not fetched:
            continue
        rows.append(
            {
                "fat_s1": toks(fat_search_text(results)),
                "fat_s2": toks(raw),
                "lay_s1": toks(index_text(results)),
                "lay_s2": toks(fetched[0][1]),
                "type": top.type,
            }
        )
    print(f"{len(rows)} cycles measured (both arms resolvable)")

    fat = np.array([r["fat_s1"] + r["fat_s2"] for r in rows], dtype=float)
    lay = np.array([r["lay_s1"] + r["lay_s2"] for r in rows], dtype=float)
    s1_fat = np.array([r["fat_s1"] for r in rows], dtype=float)
    s1_lay = np.array([r["lay_s1"] for r in rows], dtype=float)
    savings = 1 - lay.sum() / fat.sum()
    rng = np.random.default_rng(0)
    per = 1 - lay / fat
    boots = np.array([rng.choice(per, len(per)).mean() for _ in range(10_000)])
    lo, hi = np.percentile(boots, [2.5, 97.5])
    print(
        f"cycle savings: {savings:.0%} pooled; per-cycle mean {per.mean():.0%}, CI [{lo:.0%}, {hi:.0%}]"
    )
    print(
        f"stage-1 only: fat median {np.median(s1_fat):.0f} -> index median {np.median(s1_lay):.0f} tokens"
    )

    meta = (
        f"{len(rows)} real retrieval cycles · tokens/cycle: fat median {np.median(fat):.0f}, "
        f"layered median {np.median(lay):.0f} · per-cycle savings mean {per.mean():.0%}, "
        f"95% CI [{lo:.0%}, {hi:.0%}] (registered: >=50%)"
    )
    fig, top_frac = figure(
        10.5,
        6.6,
        8,
        "#149 E2 — progressive disclosure",
        "Tokens per retrieval cycle: fat contract vs index+fetch",
        meta,
    )
    ax = fig.add_axes([MARGIN + 0.05, 0.16, 1 - 2 * MARGIN - 0.09, top_frac - 0.20])
    style_axes(ax)
    order = np.argsort(fat)
    x = np.arange(len(rows))
    ax.bar(
        x - 0.2, fat[order], 0.4, color=RED, alpha=0.85, label="fat: search text + raw file read"
    )
    ax.bar(
        x + 0.2,
        lay[order],
        0.4,
        color=BLUE,
        alpha=0.85,
        label="layered: index stubs + stored-text fetch",
    )
    ax.set_yscale("log")
    ax.set_xlabel("retrieval cycle (sorted by fat cost)")
    ax.set_ylabel("tokens (log)")
    ax.legend(loc="upper left", frameon=False, labelcolor=TEXT, fontsize=9)
    panel_title(ax, "Per-cycle token cost, both contracts, top-1 selected in each")
    footer(
        fig,
        f"{stamp()} · queries are real session vault_search calls (kept local — public repo) · counts are chars/4 "
        "(no API key on-machine; the approximation cancels in a ratio) · confound: selection behavior untested",
    )
    save(fig, "e2-progressive-disclosure.png")


if __name__ == "__main__":
    main()
