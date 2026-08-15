# LLM operating guide — how to use ytk and the second brain

This is the contract for any Claude session working in or around this vault.
CLAUDE.md tells you what the project is; this file tells you how to behave
inside the second brain without corrupting it. When this guide and habit
disagree, the guide wins.

## 1. The vault structure contract

Vault root: `$OBSIDIAN_VAULT_PATH` (iCloud Obsidian vault). All ytk content
lives under `second-brain/`. Every `vault_write`/`vault_read` path is
**relative to the vault root and must start with `second-brain/`**.

| Path | What goes there | What NEVER goes there |
|---|---|---|
| `second-brain/wiki/hot.md` | Latest project state + commands. Overwrite, keep short. | History, briefs, anything you'd want to keep |
| `second-brain/wiki/index.md` | One-line pointers to vault content. Update when you add files. | Content itself |
| `second-brain/projects/<slug>/` | Session briefs, specs, decision docs | Ingested media, memories |
| `second-brain/me/profile.md` | Generated interest profile (`ytk profile` owns it) | Hand-written notes — regeneration overwrites |
| `second-brain/inbox/memories/<slug>/` | Atomic memory notes (`vault_remember` writes here) | Session briefs, source notes |
| `second-brain/sources/{youtube,instagram}/` | Pipeline-written ingest notes | Anything hand-authored — the pipeline owns these |
| `second-brain/decisions/`, `debugging/`, `tools/` | ADRs, bug patterns, tool notes | Session logs, transient scratch |

Never create new top-level folders under `second-brain/` without the user
asking for one.

## 2. Which MCP tool for which job

| Job | Tool | Not |
|---|---|---|
| Load context at session start | `vault_read` on hot.md, index.md, memory MOC | Globbing the vault filesystem |
| Find a past decision / note / video | `vault_search` (semantic, all collections) | Grepping the vault |
| Capture a decision, learning, or fact | `vault_remember` (writes the atom AND indexes it) | `vault_write` into inbox/memories by hand |
| Write/overwrite a specific note (brief, spec, wiki) | `vault_write` (also indexes) | Writing files directly with Write/Bash — that skips the index |
| After bulk out-of-band edits to vault files | `vault_reindex` | Assuming Chroma noticed |
| Keep the index current after adding files | `vault_update_index` | Editing index.md content by hand via Bash |

`vault_remember` tags: tags are the project slug plus topic words
(e.g. `["ytk", "profile"]`). They become the atom's folder routing — pick the
project slug correctly or the atom lands in the wrong project folder.

## 3. When to write a note — and when not to

A note must serve a defined purpose (issue #13): it will be searched for
later, linked from elsewhere, or it records a decision/learning that is not
derivable from code or git history. Before writing, ask:

- Would a future session search for this? If not, don't write it.
- Is it already recorded (CLAUDE.md, git log, an existing atom, the session
  brief you're about to write anyway)? Then don't duplicate it.
- Is it transient (an intermediate result, a scratch table, a progress dump)?
  Use the repo `docs/` or the scratchpad, not the vault.

One fact per memory atom. Prefer updating an existing atom over creating a
near-duplicate — search first (`vault_search`), then write.

## 4. Naming, frontmatter, wikilinks

- Filenames: kebab-case, descriptive, no dates in the name unless the note is
  inherently dated (`session-016-brief.md`, `review-2026-07-05.md`).
- Frontmatter: always include `type`, `project` (when applicable), `date`,
  `tags` (list, lowercase-hyphenated). Reuse the canonical tag vocabulary
  (`ytk tags` shows it); aliases in `~/.ytk/tag-aliases.yaml` are enforced at
  write time — do not coin a synonym for an existing tag.
- Wikilinks: `[[relative-note-name]]` without extension. Link liberally
  between atoms, briefs, and source notes — the graph is the product.
- Session briefs: `second-brain/projects/ytk/session-NNN-brief.md`, mirrored
  to repo `docs/session-NNN-brief.md`.

## 5. Session rituals

Start (in order):
1. `vault_read("second-brain/wiki/hot.md")`
2. `vault_read("second-brain/wiki/index.md")`
3. `vault_read("second-brain/inbox/memories/index.md")`, drill into the
   relevant project atoms
4. `vault_search` for anything the task mentions that you don't recognize

End (non-negotiable):
1. Write the session brief (vault + repo mirror), or a planning brief for
   planning sessions. The brief carries a **Sources consulted** section:
   every vault note read this session, as `[[wikilinks]]`. This is the
   citation rung of #96's evidence ladder — before it existed, 56 briefs
   held one source reference, and reuse was only visible through claude-mem
   exhaust. Omit the section only if no notes were read.
2. Update `wiki/index.md` if you added vault files; refresh `wiki/hot.md` if
   project state changed.
3. `vault_remember` a 2–5 sentence summary of decisions/learnings, tagged
   with the project slug.
4. Clean git tree: commit in coherent logical commits, push. Nothing
   uncommitted, ever.

## 6. Failure exhibits (real incidents — do not repeat)

**Exhibit A — the rogue root (session 016).** A `vault_write` call used the
path `Vault/me/profile.md`. The tool wrote it literally, creating a new
`Vault/` tree inside the vault instead of updating `second-brain/me/`.
Lesson: paths are relative to the vault root; there is no fuzzy resolution.
Always start with `second-brain/` and verify against the layout table above
before writing.

**Exhibit B — folder paths masquerading as tags (session 016).** The
`ytk_memories` Chroma collection stores each atom's *folder path segments*
in its `tags` metadata (e.g. `project-context, sessions-claude-mem-observer`).
These are routing artifacts, NOT interest tags. A tag-vocabulary pass that
read them as topics polluted the analysis until scoped to `ytk_videos` only.
Lesson: know which collection you are querying and what its metadata fields
actually mean; interest-tag operations are scoped to the videos collection.

## 7. Hard rules recap

- LLMs are pickers, not authors, for anything that mutates the graph
  (links, tag merges): choose from closed candidate lists, clamp in code.
- Never threshold bare-string tag embeddings; thresholds are
  embedder-relative (gte-small today).
- Generated files (`me/profile.md`, sources notes, review digests) belong to
  their pipelines — edit the generator, not the output.
- Env config lives in `~/.ytk/.env` (global, cwd-independent); repo `.env`
  is a local convenience only.
