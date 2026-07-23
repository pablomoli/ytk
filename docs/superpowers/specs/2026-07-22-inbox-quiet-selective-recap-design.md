# Inbox quiet matches, selective pulls, recap — design

Date: 2026-07-22

Three small, independent features on the ingest hub. No new subsystems.

## 1. Quiet profile matches (off by default)

Today, once a profile ranking exists, matched cards are promoted to the top of
the inbox grid and badged on every visit. Add a persisted toggle so the matches
stay hidden unless asked for.

- State: `showProfileMatches` boolean in `inbox.tsx`, persisted to
  `localStorage` key `ytk:inbox:show-profile-matches`, default `false`.
- Off (default): `matchByUrl` resolves to an empty map, so promotion and the
  `profileMatch` badge prop both fall away. Inbox is plain newest-first.
- On: today's behavior (matches lead, badged, reroll/reset/batch controls show).
- Toggle lives in the rail's "profile match" section. Batch controls render
  only when on.
- Auto-on: clicking "rank by profile" sets the flag true (you asked to see
  them); it then persists wherever left.

## 2. Selective source pull

`refresh_sources(force, only)` already supports `only`; the HTTP route drops it.

- Backend `server.py` `/api/queue/refresh`: accept optional `only` query param
  (comma-separated), parse to a set, intersect with the 6 real pull sources
  (`instagram, youtube, pinterest, imessage, tiktok, reddit`), pass through.
  Absent/empty -> `None` -> all (unchanged).
- Frontend: a `SourcePullMenu` popover (`▾` next to "refresh") with the 6 pull
  sources as checkboxes and a "pull" action. Plain "refresh" unchanged (all,
  non-forced). Selective pulls send `force=true` (explicit intent bypasses the
  cadence throttle). Checkbox selection is component state, not persisted.

## 3. Recap — "what's new + how it connects"

Shared core reused by a CLI, a hub button, and a skill. Window = newest N
ingested items (default 12).

- `ytk/digest.py`:
  - `gather_recent(n=12) -> RecapContext`: newest N notes under
    `second-brain/sources/` by mtime (title, tags, url, date, summary), plus
    recent-work signals (`inbox/ideas.md`, last few journal entries, interest
    profile themes). For each ingest, `store.search_all(thesis, n=3)` minus
    itself gives 1-2 grounded nearest notes. Best-effort; a search failure
    never aborts the recap.
  - `render_context(ctx) -> str`: markdown dump, no API call.
  - `synthesize(ctx) -> str`: one Claude call via `sdk.py` returning a
    narrative (throughline + grounded ties with `[[wikilinks]]`).
- CLI `ytk recap [-n 12]` prints the synthesis; `ytk recap --context` dumps
  `render_context` only (no API call) — the skill consumes this.
- Hub `POST /api/recap` -> `{markdown}` (sync, threadpool). Fresh feed gains a
  "what's new" button that renders the narrative inline via the existing
  `parseNote`/`renderInline` machinery (no new markdown dependency).
- Skill `/whats-new`: runs `ytk recap --context`, Claude narrates in
  conversation so the user can follow up.

## Testing

- Backend: `?only=reddit` reaches `refresh_sources(only={"reddit"})`, garbage
  sources dropped; `gather_recent` returns newest-N in order with nearest notes
  (temp vault + stubbed store); `--context` makes zero API calls.
- Frontend: toggle defaults off (no badges), on restores promotion; pull menu
  builds the right query string.
- Synthesis Claude call is smoke-tested, not asserted on content.

## Deploy

`cd web && vp test --run && vp build`, then `uv tool install --reinstall .`,
then `launchctl kickstart -k gui/501/com.ytk.hub` after checking
`/api/ingest/status`.
