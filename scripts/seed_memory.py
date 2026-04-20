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
import time
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

ATOM_TEMPLATES = {
    "purpose": 'One sentence: "{project} is a [what] that [does what] for [whom/why]."',
    "tech": "One bullet per tool/library, max 8. Use [[wikilink]] for tool names.\n  Format: '- [[tool-name]] — [how used in this project specifically]'",
    "state": "Three optional bullet types:\n  '- Working: [what functions correctly]'\n  '- In progress: [what is partially built]'\n  '- Blocked: [what is blocked and why]  (omit if nothing blocked)'",
    "questions": "Bullet list of open decisions/blockers:\n  '- ? [unresolved question]'\n  Write `_no signal_` if none.",
    "recent": "What happened this session (ALWAYS required):\n  '- [action taken]'\n  '- [decision or finding]'\n  '- [outcome or next step]'",
}


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
    filtered = [p for p in parts if p and p.lower() not in ("users", Path.home().name.lower())]
    if not filtered:
        return dir_name
    if len(filtered) == 1:
        return filtered[0]
    return f"{filtered[-1]} ({'/'.join(filtered[:-1])})"


def update_project_atoms(
    project_display: str,
    existing: dict[str, str | None],
    turns: list[dict],
    client,
) -> dict[str, dict]:
    """
    Call Haiku with existing atom content + session turns.
    Returns { atom_name: { "changed": bool, "content": str | None } }.
    """
    transcript_parts = []
    budget = 5000
    for turn in turns:
        snippet = f"[{turn['role'].upper()}]: {turn['text'][:600]}"
        if budget - len(snippet) < 0:
            break
        transcript_parts.append(snippet)
        budget -= len(snippet)
    session_excerpt = "\n\n".join(transcript_parts)

    existing_block = ""
    for atom, content in existing.items():
        existing_block += f"\n### {atom}\n{content if content else '_missing — treat as first run_'}\n"

    atom_template_block = ""
    for atom, template in ATOM_TEMPLATES.items():
        atom_template_block += f"\n{atom}:\n  {template}\n"

    prompt = f"""You are updating the knowledge base for the project '{project_display}'.

Below are the EXISTING atomic notes and excerpts from the most recent Claude Code session.

TASK: For each atom, decide whether the session introduces materially new information
that warrants updating it. If yes, return the complete updated content following the
template exactly. If no, mark it unchanged.

RULES:
- Follow each atom's template exactly. Do not add extra sections or prose.
- Be specific: tool names, CLI commands, decision rationale. Never vague summaries.
- Use [[wikilink]] syntax for tool names in tech.
- `recent` MUST always be updated — it reflects what happened in this session.
- For all other atoms: only update if the session introduces genuinely new information.
  A session about an unrelated topic does not update purpose, tech, state, or questions.
- If a section cannot be filled from actual session content, write `_no signal_`.
  Do not infer. Do not hallucinate.

ATOM TEMPLATES:
{atom_template_block}

EXISTING ATOM CONTENT:
{existing_block}

SESSION EXCERPTS:
{session_excerpt}

Respond with valid JSON only. No markdown wrapper. No explanation outside the JSON.
{{
  "purpose":   {{ "changed": false }} or {{ "changed": true, "content": "..." }},
  "tech":      {{ "changed": false }} or {{ "changed": true, "content": "..." }},
  "state":     {{ "changed": false }} or {{ "changed": true, "content": "..." }},
  "questions": {{ "changed": false }} or {{ "changed": true, "content": "..." }},
  "recent":    {{ "changed": true,  "content": "..." }}
}}"""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("`").strip()
    result = json.loads(raw)
    # Enforce recent always updates regardless of model response
    if not result.get("recent", {}).get("changed"):
        result["recent"] = {"changed": True, "content": result.get("recent", {}).get("content", "_no signal_")}
    return result


def _infer_status(most_recent_mtime: float) -> str:
    age_days = (time.time() - most_recent_mtime) / 86400
    if age_days < 14:
        return "active"
    if age_days < 90:
        return "paused"
    return "archived"


def _session_refs(vault_path: Path, project_slug: str) -> list[tuple[str, str]]:
    """Return list of (wikilink_path, stem) for session briefs of a single project, newest first."""
    briefs_dir = vault_path / "second-brain" / "projects"
    proj_dir = briefs_dir / project_slug
    refs = []
    if proj_dir.exists() and proj_dir.is_dir():
        for brief in sorted(proj_dir.glob("session-*.md"), reverse=True)[:5]:
            stem = brief.stem
            refs.append((f"second-brain/projects/{project_slug}/{stem}", stem))
    return refs


def _memory_exists(vault_path: Path, project_slug: str) -> bool:
    """Check if a memory atom folder already exists for this pre-slugified project key."""
    atom_dir = vault_path / "second-brain" / "inbox" / "memories" / project_slug
    return (atom_dir / "recent.md").exists()


def _migrate_flat_memories(vault_path: Path) -> None:
    """Delete old flat project-*.md files after new folder structure exists."""
    mem_dir = vault_path / "second-brain" / "inbox" / "memories"
    if not mem_dir.exists():
        return
    deleted = 0
    for f in mem_dir.glob("project-*.md"):
        if f.is_file():
            f.unlink()
            deleted += 1
    if deleted:
        print(f"Migrated: deleted {deleted} flat project-*.md files")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-sessions", type=int, default=3)
    parser.add_argument("--max-turns", type=int, default=0,
                        help="Cap turns sent to Haiku (0 = no cap). Use ~50 for stop-hook runs.")
    parser.add_argument("--force", action="store_true", help="Re-generate existing memories")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--recent",
        action="store_true",
        help="Re-seed only the project whose JSONL was most recently modified (session-end use).",
    )
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
        client = anthropic.Anthropic()
    else:
        client = None

    projects = [d for d in CLAUDE_DIR.iterdir() if d.is_dir()]

    if args.recent:
        # Skip meta-directories (observer, config tools) — they have "--" in their
        # name from empty path components, e.g. -Users-<username>--claude-mem-observer
        real_projects = [p for p in projects if "--" not in p.name]
        all_jsonls = [
            (jf.stat().st_mtime, proj_dir)
            for proj_dir in real_projects
            for jf in proj_dir.glob("*.jsonl")
        ]
        if not all_jsonls:
            print("--recent: no JSONL files found.")
            return
        most_recent_mtime, most_recent_proj = max(all_jsonls, key=lambda x: x[0])
        if time.time() - most_recent_mtime > 300:
            print("--recent: last session > 5 minutes ago, skipping.")
            return
        projects = [most_recent_proj]
        args.force = True
        print(f"--recent: reseeding {project_name_from_dir(most_recent_proj.name)}")

    print(f"Found {len(projects)} project directories")

    processed_projects: list[dict] = []

    for proj_dir in sorted(projects):
        dir_name = proj_dir.name
        dir_name_slug = re.sub(r"[^a-z0-9]+", "-", dir_name.lower()).strip("-")
        project_display = project_name_from_dir(dir_name)

        jsonl_files = sorted(
            proj_dir.glob("*.jsonl"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not jsonl_files:
            continue

        if not args.force and _memory_exists(vault_path, dir_name_slug):
            print(f"  SKIP (exists): {project_display}")
            continue

        all_turns: list[dict] = []
        for jf in jsonl_files[: args.max_sessions]:
            all_turns.extend(read_session(jf))

        if not all_turns:
            print(f"  SKIP (no content): {project_display}")
            continue

        if args.max_turns and len(all_turns) > args.max_turns:
            all_turns = all_turns[-args.max_turns:]

        print(f"  Processing: {project_display} ({len(all_turns)} turns from {min(len(jsonl_files), args.max_sessions)} sessions)")

        if args.dry_run:
            for t in all_turns[:2]:
                print(f"    [{t['role']}] {t['text'][:120]!r}")
            continue

        try:
            from ytk.vault import (
                write_atom, read_atom, write_project_hub,
                _get_vault_path,
            )

            existing = {
                atom: read_atom(dir_name_slug, atom)
                for atom in ("purpose", "tech", "state", "questions", "recent")
            }

            updates = update_project_atoms(project_display, existing, all_turns, client)

            atoms_written = []
            for atom, result in updates.items():
                if result.get("changed") and result.get("content"):
                    write_atom(dir_name_slug, atom, result["content"])
                    atoms_written.append(atom)

            most_recent_mtime = max(jf.stat().st_mtime for jf in jsonl_files[:args.max_sessions])
            status = _infer_status(most_recent_mtime)
            last_active = datetime.fromtimestamp(most_recent_mtime, tz=timezone.utc).strftime("%Y-%m-%d")

            tech_content = updates.get("tech", {}).get("content") or existing.get("tech") or ""
            tech_tags = re.findall(r"\[\[([^\]]+)\]\]", tech_content)

            vault_path_obj = _get_vault_path()
            refs = _session_refs(vault_path_obj, dir_name_slug)

            write_project_hub(
                dir_name_slug, project_display, status, tech_tags,
                last_active, refs,
            )

            print(f"    Updated atoms: {', '.join(atoms_written) if atoms_written else 'none'}")
            print(f"    Hub written: {status}, {len(tech_tags)} tech links")

            purpose_line = (updates.get("purpose", {}).get("content") or existing.get("purpose") or "")
            purpose_line = purpose_line.split("\n")[0][:80].rstrip(".")
            processed_projects.append({
                "slug": dir_name_slug,
                "display": project_display,
                "status": status,
                "purpose_line": purpose_line,
            })

        except Exception as exc:
            print(f"    ERROR: {exc}", file=sys.stderr)
            import traceback; traceback.print_exc(file=sys.stderr)


    if processed_projects and not args.dry_run:
        try:
            from ytk.vault import write_memories_moc
            moc_path = write_memories_moc(processed_projects)
            print(f"\nMOC written: {moc_path}")
        except Exception as exc:
            print(f"MOC ERROR: {exc}", file=sys.stderr)

    if not args.dry_run:
        from ytk.vault import _get_vault_path
        _migrate_flat_memories(_get_vault_path())


if __name__ == "__main__":
    main()
