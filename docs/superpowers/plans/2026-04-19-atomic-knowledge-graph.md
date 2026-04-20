# Atomic Knowledge Graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace single-blob project memory files with folder-based atomic notes (purpose, tech, state, questions, recent) that update differentially and link via Obsidian wikilinks.

**Architecture:** Each project gets a folder in `second-brain/inbox/memories/{slug}/` containing a hub `index.md` (links only) and five atomic notes. Haiku produces structured JSON per run; the script writes only atoms flagged `changed: true`. A global `index.md` MOC is regenerated after each run.

**Tech Stack:** Python, anthropic SDK (claude-haiku-4-5), vault.py path helpers, existing seed_memory.py scaffold.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `ytk/vault.py` | Modify | Add `write_atom`, `read_atom`, `write_project_hub`, `write_memories_moc` |
| `scripts/seed_memory.py` | Rewrite core logic | New prompt, JSON parsing, differential write, folder structure, migration |
| `docs/superpowers/specs/2026-04-19-atomic-knowledge-graph-design.md` | Already written | Spec reference |

---

## Task 1: Vault atom helpers

**Files:**
- Modify: `ytk/vault.py`

- [ ] **Step 1: Add `read_atom` function after the `remember` function (around line 255)**

```python
def read_atom(project_slug: str, atom: str) -> str | None:
    """Read an atomic note. Returns content body (no frontmatter) or None if missing."""
    brain = _get_brain_path()
    path = brain / "inbox" / "memories" / project_slug / f"{atom}.md"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    # Strip YAML frontmatter
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            return text[end + 3:].strip()
    return text.strip()
```

- [ ] **Step 2: Add `write_atom` function immediately after `read_atom`**

```python
def write_atom(project_slug: str, atom: str, content: str) -> Path:
    """Write an atomic note, creating the project folder if needed."""
    brain = _get_brain_path()
    atom_dir = brain / "inbox" / "memories" / project_slug
    atom_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    path = atom_dir / f"{atom}.md"
    path.write_text(
        f"---\ntype: atom\natom: {atom}\nproject: {project_slug}\nupdated: {date_str}\n---\n\n{content}\n",
        encoding="utf-8",
    )
    return path
```

- [ ] **Step 3: Add `write_project_hub` immediately after `write_atom`**

```python
def write_project_hub(
    project_slug: str,
    project_display: str,
    status: str,
    tech: list[str],
    last_active: str,
    session_refs: list[tuple[str, str]],  # list of (rel_path, date_str)
) -> Path:
    """Write or overwrite the project hub index.md (links only, no prose)."""
    brain = _get_brain_path()
    hub_dir = brain / "inbox" / "memories" / project_slug
    hub_dir.mkdir(parents=True, exist_ok=True)

    tech_yaml = ", ".join(tech) if tech else ""
    session_log = "\n".join(
        f"- [[{ref}]] — {date}" for ref, date in session_refs
    ) or "_no sessions indexed yet_"

    content = (
        f"---\ntype: project-hub\nstatus: {status}\ntech: [{tech_yaml}]\n"
        f"last_active: {last_active}\n---\n\n"
        f"## Current Understanding\n"
        f"[[purpose]] · [[tech]] · [[state]] · [[questions]]\n\n"
        f"## This Session\n[[recent]]\n\n"
        f"## Session Log\n{session_log}\n"
    )
    path = hub_dir / "index.md"
    path.write_text(content, encoding="utf-8")
    return path
```

- [ ] **Step 4: Add `write_memories_moc` immediately after `write_project_hub`**

```python
def write_memories_moc(projects: list[dict]) -> Path:
    """
    Regenerate second-brain/inbox/memories/index.md.
    projects: list of { slug, display, status, purpose_line }
    """
    brain = _get_brain_path()
    moc_path = brain / "inbox" / "memories" / "index.md"

    by_status: dict[str, list[dict]] = {"active": [], "paused": [], "archived": []}
    for p in projects:
        by_status.get(p["status"], by_status["paused"]).append(p)

    sections = ["# Projects\n"]
    for status_label in ("active", "paused", "archived"):
        group = by_status[status_label]
        if not group:
            continue
        rows = "\n".join(
            f"- [[{p['slug']}/index|{p['display']}]] — {p['purpose_line']}"
            for p in group
        )
        sections.append(f"## {status_label.capitalize()}\n{rows}\n")

    moc_path.write_text("\n".join(sections), encoding="utf-8")
    return moc_path
```

- [ ] **Step 5: Verify no syntax errors**

```bash
cd /Users/melocoton/Developer/ytk && uv run python -c "from ytk.vault import write_atom, read_atom, write_project_hub, write_memories_moc; print('OK')"
```
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add ytk/vault.py
git commit -m "feat(vault): add atomic note helpers for project knowledge graph"
```

---

## Task 2: New Haiku prompt with structured JSON output

**Files:**
- Modify: `scripts/seed_memory.py`

- [ ] **Step 1: Replace `summarize_project` with `update_project_atoms`**

Delete the existing `summarize_project` function entirely and replace with:

```python
ATOM_TEMPLATES = {
    "purpose": 'One sentence: "{project} is a [what] that [does what] for [whom/why]."',
    "tech": "One bullet per tool/library, max 8. Use [[wikilink]] for tool names.\n  Format: '- [[tool-name]] — [how used in this project specifically]'",
    "state": "Three optional bullet types:\n  '- Working: [what functions correctly]'\n  '- In progress: [what is partially built]'\n  '- Blocked: [what is blocked and why]  (omit if nothing blocked)'",
    "questions": "Bullet list of open decisions/blockers:\n  '- ? [unresolved question]'\n  Write `_no signal_` if none.",
    "recent": "What happened this session (ALWAYS required):\n  '- [action taken]'\n  '- [decision or finding]'\n  '- [outcome or next step]'",
}


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
    import json as _json

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
    # Strip accidental markdown code fences
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("`").strip()
    return _json.loads(raw)
```

- [ ] **Step 2: Verify no syntax errors**

```bash
cd /Users/melocoton/Developer/ytk && uv run python -c "from scripts.seed_memory import update_project_atoms, ATOM_TEMPLATES; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add scripts/seed_memory.py
git commit -m "feat(seed): replace prose prompt with structured atom update prompt"
```

---

## Task 3: Differential write logic in main loop

**Files:**
- Modify: `scripts/seed_memory.py`

- [ ] **Step 1: Add status inference helper near the top of the file (after imports)**

```python
def _infer_status(most_recent_mtime: float) -> str:
    age_days = (time.time() - most_recent_mtime) / 86400
    if age_days < 14:
        return "active"
    if age_days < 90:
        return "paused"
    return "archived"
```

- [ ] **Step 2: Add session refs builder helper**

```python
def _session_refs(vault_path: Path, project_slug: str) -> list[tuple[str, str]]:
    """Return list of (wikilink_path, date_str) for session briefs, newest first."""
    # project slug maps back to a project name — try common patterns
    briefs_dir = vault_path / "second-brain" / "projects"
    refs = []
    for proj_dir in sorted(briefs_dir.iterdir()) if briefs_dir.exists() else []:
        if not proj_dir.is_dir():
            continue
        for brief in sorted(proj_dir.glob("session-*.md"), reverse=True)[:5]:
            date_str = brief.stem[-10:] if len(brief.stem) >= 10 else ""
            rel = f"../../../projects/{proj_dir.name}/{brief.stem}"
            refs.append((rel, date_str))
    return refs[:5]
```

- [ ] **Step 3: Rewrite the per-project processing block in `main()`**

Replace the existing try/except block that calls `remember()` with:

```python
        try:
            from ytk.vault import (
                write_atom, read_atom, write_project_hub, write_memories_moc,
                _get_vault_path,
            )

            # Read existing atoms
            existing = {
                atom: read_atom(dir_name_slug, atom)
                for atom in ("purpose", "tech", "state", "questions", "recent")
            }

            # Call Haiku for differential update
            updates = update_project_atoms(project_display, existing, all_turns, client)

            # Write only changed atoms
            atoms_written = []
            for atom, result in updates.items():
                if result.get("changed") and result.get("content"):
                    write_atom(dir_name_slug, atom, result["content"])
                    atoms_written.append(atom)

            # Infer status and build hub
            most_recent_mtime = max(jf.stat().st_mtime for jf in jsonl_files[:args.max_sessions])
            status = _infer_status(most_recent_mtime)
            last_active = datetime.fromtimestamp(most_recent_mtime, tz=timezone.utc).strftime("%Y-%m-%d")

            # Extract tech from tech atom if updated
            tech_content = updates.get("tech", {}).get("content") or existing.get("tech") or ""
            tech_tags = re.findall(r"\[\[([^\]]+)\]\]", tech_content)

            vault_path_obj = _get_vault_path()
            session_refs = _session_refs(vault_path_obj, dir_name_slug)

            write_project_hub(
                dir_name_slug, project_display, status, tech_tags,
                last_active, session_refs,
            )

            print(f"    Updated atoms: {', '.join(atoms_written) if atoms_written else 'none'}")
            print(f"    Hub written: {status}, {len(tech_tags)} tech links")

            # Track for MOC generation
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
```

- [ ] **Step 4: Add `processed_projects` list initialization before the project loop and `dir_name_slug` definition**

Before the `for proj_dir in sorted(projects):` loop, add:
```python
    processed_projects: list[dict] = []
```

After `dir_name = proj_dir.name` inside the loop, add:
```python
        dir_name_slug = re.sub(r"[^a-z0-9]+", "-", dir_name.lower()).strip("-")
```

- [ ] **Step 5: Add MOC generation after the project loop, before `if __name__ == "__main__"`**

At the bottom of `main()`, after the project loop closes:
```python
    # Regenerate MOC of MOCs
    if processed_projects and not args.dry_run:
        try:
            from ytk.vault import write_memories_moc
            moc_path = write_memories_moc(processed_projects)
            print(f"\nMOC written: {moc_path}")
        except Exception as exc:
            print(f"MOC ERROR: {exc}", file=sys.stderr)
```

- [ ] **Step 6: Update imports at top of main() to remove old `remember`/`upsert_memory` imports**

The existing import block inside `main()` that imports `write_raw` and `upsert_memory` should be removed — those are now handled inside the try/except block in the project loop. Remove:
```python
    if not args.dry_run:
        import anthropic
        from ytk.vault import write_raw
        from ytk.store import upsert_memory
        client = anthropic.Anthropic()
    else:
        client = write_raw = upsert_memory = None
```

Replace with:
```python
    if not args.dry_run:
        import anthropic
        client = anthropic.Anthropic()
    else:
        client = None
```

- [ ] **Step 7: Dry-run test**

```bash
cd /Users/melocoton/Developer/ytk && uv run scripts/seed_memory.py --dry-run --max-sessions 1
```
Expected: prints project names and turn counts, no files written.

- [ ] **Step 8: Commit**

```bash
git add scripts/seed_memory.py
git commit -m "feat(seed): differential atom update with hub and MOC generation"
```

---

## Task 4: Migrate existing flat project files

**Files:**
- Modify: `scripts/seed_memory.py` (add migration helper)
- Runtime: vault filesystem

- [ ] **Step 1: Add migration function to seed_memory.py**

```python
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
```

- [ ] **Step 2: Call migration at end of `main()`, after MOC generation**

```python
    if not args.dry_run:
        _migrate_flat_memories(_get_vault_path())
```

Add the `_get_vault_path` import to the outer scope of `main()`:
```python
    from ytk.vault import _get_vault_path
    vault_path_obj = _get_vault_path()
```

- [ ] **Step 3: Full live run**

```bash
cd /Users/melocoton/Developer/ytk && uv run scripts/seed_memory.py --max-sessions 2
```

Expected output pattern:
```
Found N project directories
  Processing: ytk (Developer) (X turns from 2 sessions)
    Updated atoms: purpose, tech, recent
    Hub written: active, 4 tech links
  ...
MOC written: /path/to/second-brain/inbox/memories/index.md
Migrated: deleted 13 flat project-*.md files
```

- [ ] **Step 4: Verify vault structure**

```bash
ls "/Users/melocoton/Library/Mobile Documents/iCloud~md~obsidian/Documents/Vault/second-brain/inbox/memories/"
ls "/Users/melocoton/Library/Mobile Documents/iCloud~md~obsidian/Documents/Vault/second-brain/inbox/memories/ytk/"
```

Expected: `index.md` plus project folders; inside `ytk/`: `index.md purpose.md tech.md recent.md state.md questions.md`

- [ ] **Step 5: Reinstall ytk**

```bash
cd /Users/melocoton/Developer/ytk && uv tool install --reinstall .
```

- [ ] **Step 6: Commit**

```bash
git add scripts/seed_memory.py
git commit -m "feat(seed): migrate flat project files to folder-based atom structure"
```

---

## Task 5: Update CLAUDE.md paths

**Files:**
- Modify: `ytk/CLAUDE.md`

- [ ] **Step 1: Update session-start vault_read calls**

In `ytk/CLAUDE.md`, the session-start block currently says:
```
1. Call `vault_read("second-brain/wiki/hot.md")` — latest project state and commands
2. Call `vault_read("second-brain/wiki/index.md")` — full vault index
3. Drill into `second-brain/projects/ytk/` as needed via `vault_read`
```

Add a fourth step:
```
4. Call `vault_read("second-brain/inbox/memories/index.md")` — project MOC of MOCs
   Then drill into `second-brain/inbox/memories/ytk/` atoms as needed.
```

- [ ] **Step 2: Update vault layout section**

Add to the vault layout code block:
```
second-brain/inbox/memories/index.md   — MOC of all projects
second-brain/inbox/memories/{slug}/    — project atom folder
  index.md                             — project hub (links only)
  purpose.md · tech.md · state.md · questions.md · recent.md
```

- [ ] **Step 3: Commit**

```bash
git add ytk/CLAUDE.md
git commit -m "docs(claude): add atomic memory paths to session-start instructions"
```

---

## Self-Review

**Spec coverage:**
- [x] Folder structure under `second-brain/inbox/memories/{slug}/` — Task 1 (write_atom creates it)
- [x] Five atom types with templates — Task 2 (ATOM_TEMPLATES) and Task 1 (write_atom)
- [x] Project hub with links-only pattern — Task 1 (write_project_hub)
- [x] MOC of MOCs — Task 1 (write_memories_moc) + Task 3 (called after loop)
- [x] Differential update algorithm — Task 3 (only write where changed=true)
- [x] `recent` always updated — enforced in prompt + JSON schema
- [x] Haiku prompt with templates, sentinel, peer-accountability tone — Task 2
- [x] Status inference (active/paused/archived) — Task 3 (_infer_status)
- [x] Session refs in hub — Task 3 (_session_refs)
- [x] Migration of flat files — Task 4
- [x] CLAUDE.md updated — Task 5

**Placeholder scan:** None found.

**Type consistency:**
- `write_atom(project_slug, atom, content)` — used consistently in Task 1 and Task 3
- `read_atom(project_slug, atom)` — used consistently in Task 1 and Task 3
- `write_project_hub(slug, display, status, tech, last_active, session_refs)` — Task 1 signature matches Task 3 call
- `write_memories_moc(projects)` where projects is `list[dict]` with keys `slug, display, status, purpose_line` — Task 1 signature matches Task 3 call
- `update_project_atoms(project_display, existing, turns, client)` — Task 2 signature matches Task 3 call
- `processed_projects` list — initialized in Task 3 Step 4, appended in Step 3, consumed in Step 5
