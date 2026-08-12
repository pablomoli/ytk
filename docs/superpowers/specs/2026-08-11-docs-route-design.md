# /docs — the experiment record in the hub

Serve `docs/assets/` (the 31-section visual-experiment record) as a hub route:
a chronological gallery on `#000` with per-section pages rendering each
README whole. Approved 2026-08-11.

## Constraint that shapes everything

`docs/assets/` is 136MB; the installed wheel cannot carry it. The hub must
serve it from the repo checkout at runtime, the same way `vault_media` serves
the vault from `OBSIDIAN_VAULT_PATH` rather than bundling it.

## Backend

New module `ytk/ui/docs_record.py`; routes registered in `ytk/ui/server.py`.

- **Repo path resolution.** Optional `YTK_REPO_PATH` (env / `.env`, plumbed
  like the vault path). Fallback: the source checkout via
  `Path(__file__).resolve().parents[2]` when `docs/assets` exists there, so
  dev needs zero config. Neither present: `/api/docs` returns
  `{"available": false}` and the page names the fix.
- **`GET /api/docs`** — manifest. Scan `docs/assets/NN-slug/` dirs; per
  section: id (`30-coastlines`), number, title (README's `# ` H1), deck
  (first non-heading paragraph, markdown stripped), cover (first image by
  name sort), figure count, video presence. Sorted by number. 31 dirs,
  parsed per request; no cache.
- **`GET /api/docs/{section}`** — raw README markdown plus a file listing
  (images, mp4s, sidecar json/csv) for the section.
- **`GET /docs-media/{path:path}`** — `FileResponse` rooted at
  `docs/assets`, guarded with `resolve()` + `is_relative_to` (the
  `vault_media` pattern), `Cache-Control: public, max-age=86400`.
- `_SPA_ROUTES` admits `docs` and `docs/<section>` paths. The existing
  `/docs/settings` endpoint registers before the SPA catch-all and keeps
  winning.

## Frontend

Two TanStack routes. Tailwind utilities on observatory tokens only; nothing
enters `styles.css` (CSS ratchet, #136).

- **`/docs`** (`routes/docs.tsx`) — full-bleed `#000`. Grid of section
  cards: cover figure edge-to-edge, E-number + title + deck below. Newest
  first: the top edge shows the frontier, though the record itself is
  written oldest-first. Nav bar gains a `docs` link — a link only.
- **`/docs/$section`** (`routes/docs.$section.tsx`) — README rendered
  whole. `> **Later:**` blockquotes styled as a distinct annotation layer
  (they are the corrections mechanism and must read as such). Image srcs
  rewritten to `/docs-media/...`; mp4s as `<video controls>`. Prose at
  reading measure, figures full-width. Prev/next section links.
- **Markdown: `marked`** (~35KB, zero deps) with a renderer hook for the
  image-path rewrite. The owned `inlineMarkdown.tsx` precedent was justified
  by "these notes never use nested markdown"; the section READMEs do — 25/31
  carry tables, 27/31 fenced code — so an owned block renderer is surface
  without payoff. Content is our own; no sanitizer.
- **WebGL accent** — one fixed canvas behind the index grid: sparse
  slow-drifting particle field in dim ember tones (three `Points`, ~2k
  points; three is already a dep). DPR-capped, paused on
  `visibilitychange`, absent under `prefers-reduced-motion`. The grid never
  depends on it.

## Scope cuts (v1)

Numbered sections only. Skipped: `memory-field/`, the loose program READMEs
(`README.md`, `README-two-lenses-program.md`), hub screenshots, `icon.png`.
The two-lenses arbiter can become a pinned entry later.
No search, no tag filtering, no lightbox beyond the section page.

## Testing

- pytest: manifest parsing (title/deck/cover extraction, malformed dirs
  skipped) and the `/docs-media` traversal guard — the one security-shaped
  surface.
- vitest: both routes against stubbed `/api/docs` responses (autouse network
  stubs; suite runs in real Chromium via `vp exec vitest run`).
