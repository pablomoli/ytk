"""E6 (#149): distilled session-start brief, injected by the SessionStart hook.

E6 measured 87% of sessions skipping the voluntary vault bootstrap, and that
wholesale hot.md+atoms injection (2,279 tokens) costs more than the voluntary
reads it replaces. This emits the supported middle: a fixed-shape skeleton —
project state (R3's live slice) + hot.md's head — hard-capped at BUDGET chars
(~400 tokens), deterministic, no LLM. Prints nothing on any failure: a broken
brief must never block a session start.
"""

from __future__ import annotations

BUDGET = 1600


def distill(state: str, hot: str, budget: int = BUDGET) -> str:
    """Fixed shape: current project state first, hot-cache head with the rest."""
    state = state.strip()
    hot = hot.strip()
    parts = []
    if state:
        parts.append("## ytk state (current slice)\n" + state[: budget * 2 // 3])
    if hot:
        used = sum(len(p) for p in parts)
        room = budget - used
        if room > 200:
            parts.append("## hot cache (head)\n" + hot[:room])
    return "\n\n".join(parts)[:budget]


def main() -> None:
    try:
        from ytk.vault import _get_brain_path, read_atom

        state = read_atom("users-melocoton-developer-ytk", "recent") or ""
        hot_path = _get_brain_path() / "wiki" / "hot.md"
        hot = hot_path.read_text(encoding="utf-8", errors="replace") if hot_path.exists() else ""
        brief = distill(state, hot)
        if brief:
            print("# Vault brief (auto-injected, E6/#149 — full detail: vault_read wiki/hot.md)")
            print(brief)
    except Exception:
        pass


if __name__ == "__main__":
    main()
