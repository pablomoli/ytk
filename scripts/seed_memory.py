#!/usr/bin/env python3
"""
Seed the Obsidian vault with project summaries scraped from ~/.claude session JSONLs.

For each project in ~/.claude/projects/, reads the most recent sessions,
calls Claude Haiku to produce a brief summary, and writes it as an atomic
memory note in inbox/memories/ (indexed in ChromaDB via vault_remember).

Usage:
    uv run scripts/seed_memory.py [--max-sessions N] [--force] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

CLAUDE_DIR = Path.home() / ".claude" / "projects"

_SKIP_PREFIXES = (
    "Base directory for this skill:",
    "# Brainstorming",
    "# RTK",
    "# ytk",
    "You have been invoked",
    "Called the Read tool",
    "Called the Bash tool",
    "Result of calling",
    "<system-reminder>",
    "<EXTREMELY_IMPORTANT>",
    "SessionStart hook",
)


def _extract_text(content) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", "").strip())
        return "\n".join(parts).strip()
    return ""


def _is_injected(text: str) -> bool:
    if not text:
        return True
    if len(text) > 2000 and text.lstrip().startswith(("#", "<", "You have")):
        return True
    for prefix in _SKIP_PREFIXES:
        if text.strip().startswith(prefix):
            return True
    return False


def read_session(path: Path) -> list[dict]:
    turns = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                t = obj.get("type")
                if t not in ("user", "assistant"):
                    continue
                msg = obj.get("message", {})
                if not msg:
                    continue
                role = msg.get("role", t)
                text = _extract_text(msg.get("content", ""))
                if not text:
                    continue
                if role == "user" and _is_injected(text):
                    continue
                if role == "assistant" and len(text) < 30:
                    continue
                turns.append({"role": role, "text": text})
    except Exception:
        pass
    return turns


def project_name_from_dir(dir_name: str) -> str:
    parts = dir_name.lstrip("-").split("-")
    filtered = [p for p in parts if p and p.lower() not in ("users", "melocoton")]
    if not filtered:
        return dir_name
    if len(filtered) == 1:
        return filtered[0]
    return f"{filtered[-1]} ({'/'.join(filtered[:-1])})"


def summarize_project(project_display: str, turns: list[dict], client) -> str:
    transcript_parts = []
    budget = 4000
    for turn in turns:
        snippet = f"[{turn['role'].upper()}]: {turn['text'][:600]}"
        if budget - len(snippet) < 0:
            break
        transcript_parts.append(snippet)
        budget -= len(snippet)

    transcript = "\n\n".join(transcript_parts)

    prompt = f"""You are summarizing Claude Code session history for a project named '{project_display}'.

Below are excerpts from recent Claude Code sessions. Write a 3-5 sentence summary covering:
1. What this project is (purpose/domain)
2. What has been actively worked on recently
3. Current state or open questions (if evident)

Rules:
- Plain prose, third person, past tense
- No markdown headers, bullets, or code blocks
- Start with the project name and purpose
- Be specific about technologies and what was built

SESSION EXCERPTS:
{transcript}

SUMMARY:"""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


def _memory_exists(vault_path: Path, project_key: str) -> bool:
    """Check if a memory note already exists for this project key."""
    mem_dir = vault_path / "inbox" / "memories"
    slug = re.sub(r"[^a-z0-9]+", "-", project_key.lower()).strip("-")
    return any(mem_dir.glob(f"*-project-{slug}*.md")) if mem_dir.exists() else False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-sessions", type=int, default=3)
    parser.add_argument("--force", action="store_true", help="Re-generate existing memories")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not CLAUDE_DIR.exists():
        print(f"ERROR: {CLAUDE_DIR} does not exist", file=sys.stderr)
        sys.exit(1)

    from dotenv import load_dotenv
    load_dotenv()

    import os
    vault_raw = os.getenv("OBSIDIAN_VAULT_PATH")
    if not vault_raw:
        print("ERROR: OBSIDIAN_VAULT_PATH not set in .env", file=sys.stderr)
        sys.exit(1)
    vault_path = Path(vault_raw).expanduser()

    if not args.dry_run:
        import anthropic
        from ytk.vault import remember
        from ytk.store import upsert_memory
        client = anthropic.Anthropic()
    else:
        client = remember = upsert_memory = None

    projects = [d for d in CLAUDE_DIR.iterdir() if d.is_dir()]
    print(f"Found {len(projects)} project directories")

    for proj_dir in sorted(projects):
        dir_name = proj_dir.name
        project_display = project_name_from_dir(dir_name)

        jsonl_files = sorted(
            proj_dir.glob("*.jsonl"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not jsonl_files:
            continue

        if not args.force and _memory_exists(vault_path, dir_name):
            print(f"  SKIP (exists): {project_display}")
            continue

        all_turns: list[dict] = []
        for jf in jsonl_files[: args.max_sessions]:
            all_turns.extend(read_session(jf))

        if not all_turns:
            print(f"  SKIP (no content): {project_display}")
            continue

        print(f"  Processing: {project_display} ({len(all_turns)} turns from {min(len(jsonl_files), args.max_sessions)} sessions)")

        if args.dry_run:
            for t in all_turns[:2]:
                print(f"    [{t['role']}] {t['text'][:120]!r}")
            continue

        try:
            summary = summarize_project(project_display, all_turns, client)
            tags = ["project-context", re.sub(r"[^a-z0-9]+", "-", project_display.lower()).strip("-")]
            note_path, doc_id = remember(summary, tags)
            upsert_memory(doc_id, summary, tags, str(note_path))
            print(f"    Written: {note_path.name}")
            print(f"    Summary: {summary[:120]}...")
        except Exception as exc:
            print(f"    ERROR: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
