# ytk phone access — design

Date: 2026-07-20
Status: pivoted — Obsidian-first hub shipped; Tailscale/mobile-lite deferred

## Pivot (2026-07-20)

Priority narrowed to "usable from the phone today, no infrastructure." The
Obsidian read layer (Layer 0) is promoted from passive reading to an active
**hub dashboard** built with Bases. Tailscale + mobile-lite pages (Layers 1-2)
are deferred until the user is home; capture (Layer 3) unchanged and still
works via existing channels. Everything below Layer 0 stays as designed, just
scheduled later.

### Shipped: Bases hub (rides iCloud, zero services)

Location: `second-brain/hub/` in the vault (not this git repo — syncs via
iCloud). Files:

- `Hub.md` — dashboard note. `cssclasses: [no-toolbar]`; collapsible callout
  sections; a jump bar (hot cache, profile, ideas, vault index, latest digest)
  over embedded Bases views.
- `ytk-sources.base` — views: Fresh (all sources, cards, `file.ctime` desc),
  YouTube, Instagram, Articles (web/reddit, table), Clips (tiktok/pinterest).
- `ytk-projects.base` — Projects (cards) + All notes (table).
- `.obsidian/snippets/ytk-hub.css` — hides Bases toolbar on `no-toolbar` notes.

Card covers come from a formula, `firstimage: file.embeds[0]`, reading each
note's first embedded image — so 135 YouTube + 145 Instagram notes show
thumbnails with **no backfill and no code change**. This is why the planned
`cover` frontmatter field in `vault.py` was dropped as unnecessary; revisit
only if a note's first embed is ever the wrong cover, or to give web/reddit
notes an image.

On-phone steps (one time): pull the vault so files sync; enable the `ytk-hub`
CSS snippet in Settings -> Appearance; optionally set `Hub.md` as the mobile
Homepage via the Homepage plugin; mark the vault "Keep Downloaded" (iOS 18+).

---

## Goal

Use ytk from the phone: capture links into the queue, browse the fresh feed and
inbox, run semantic search and chat, and read ingested notes/digests — with
outbound YouTube/Instagram links opening the respective native apps.

## Architecture: three layers, no new services

The design layers phone access over what already exists. The vault (markdown in
iCloud) is the read contract; the hub (FastAPI at `hub.host:hub.port`, launchd
`com.ytk.hub`) is the live contract. Nothing moves off the Mac.

| Layer | Provides | Availability |
|---|---|---|
| Obsidian mobile + iCloud | Notes, daily digests, interest profile, memory atoms | Works with Mac asleep (iCloud is the courier) |
| Hub mobile-lite over Tailscale | Fresh feed, inbox triage, semantic search, chat | Mac awake |
| iOS Shortcut + fallbacks | Capture from any app's share sheet | Mac awake; fallbacks absorb downtime |

## Layer 0 — read layer: Obsidian mobile (zero code)

The vault already syncs through Obsidian's iCloud container. Setup is on-device
only: install Obsidian iOS, open the existing iCloud vault. On iOS 18+, mark
the vault folder "Keep Downloaded" in the Files app so iOS never evicts notes
to placeholders under storage pressure (the main reliability gap of the free
iCloud route, per r/ObsidianMD — ingested as
`sources/web/ios-18-finally-introduces-keep-downloaded-option-in-icloud.md`).
Daily digests
(`inbox/review-*.md`), the interest profile (`me/profile.md`), and all source
notes are readable on the phone with no repo changes.

Consequence for scope: no `/m/digest` page — the digest is a vault note and
Obsidian renders it. Mobile-lite is three pages, not four.

## Layer 1 — connectivity: Tailscale

- Install Tailscale on Mac and phone (free Personal plan, MagicDNS on).
- Set `hub.host: 0.0.0.0` in `~/.ytk/config.yaml` so the hub answers on the
  tailnet interface (and home LAN) instead of loopback only.
- Phone reaches `http://<magicdns-name>:<hub.port>` from anywhere.
- No auth layer: tailnet membership is the auth boundary. Nothing is exposed
  publicly (no ngrok/tunnel/port forwarding).
- Known limitation, accepted: hub unreachable while the Mac sleeps. Capture
  fallbacks (Layer 3) absorb this; a VPS or always-on Mac mini is the future
  fix if it ever hurts in practice, not now.

## Layer 2 — mobile-lite pages

Small phone-first pages served by the existing FastAPI app under `/m`,
completely separate from the desktop SPA in `web/` (which stays untouched).
Server-rendered HTML, minimal JS, one-column layout, fast on cellular. They
call the same JSON endpoints the SPA uses — no duplicated backend logic.

- `/m` — fresh feed: thumbnail, title, tags, one-line thesis per card.
- `/m/inbox` — queue triage: assign bucket, add a thought, dismiss. Includes
  the paste-to-queue Add box (capture fallback).
- `/m/ask` — search + chat in one page: semantic search results, or hand the
  query to the existing SSE chat endpoint.

### App-scheme links

Outbound links on `/m` pages render through a helper that maps URLs to native
app schemes — YouTube -> `vnd.youtube://watch?v=<id>`, Instagram ->
`instagram://` equivalents — because universal links do not reliably fire from
a home-screen PWA's in-app browser. A few lines of JS attempt the scheme and
fall back to the `https` URL after a short timeout when the app is absent.
Everything else stays plain `https`.

### Home-screen install

Web manifest + apple-touch-icon so `/m` installs as a standalone app.

## Layer 3 — capture: iOS Shortcut with fallbacks

Primary: a "Save to ytk" Shortcut registered for URLs in the share sheet.
Grabs the shared URL, optionally prompts for a one-line thought, POSTs
`{url, thought}` to the hub's queue-add endpoint over Tailscale.

Repo-side work is only verifying the queue endpoint accepts that bare payload;
the Shortcut itself is built on the phone (documented, not coded).

Fallbacks when the Mac is asleep (Shortcut alerts and copies the link):
1. DM the link to yourself on Instagram — existing `ytk reels` sync catches it.
2. Paste into the `/m/inbox` Add box later.

## Future direction (recorded, not scheduled): Swift companion app

A lightweight SwiftUI app could replace the Obsidian read layer with owned
styling and add a proper share extension (offline-queueing capture). Findings
from this brainstorm, so they are not re-derived later:

- Vault access: system folder picker once -> security-scoped bookmark to the
  Obsidian iCloud folder; readable directly thereafter.
- iCloud placeholders require `startDownloadingUbiquitousItem` handling.
- SwiftUI's native markdown is insufficient; use MarkdownUI + frontmatter split.
- Native app -> universal links open YouTube/Instagram apps without scheme hacks.
- Free dev account = 7-day app expiry; practical use needs the $99/yr account.
- Risk: scope gravity toward a full native client (search/chat need the hub
  anyway). Decision: revisit after real usage of the layers above.
- Prior art: "Funnel" (r/ObsidianMD), a quick-capture iOS app writing into an
  Obsidian vault — evidence the share-extension-into-vault pattern works.

## Test finding: Reddit ingestion (2026-07-20)

`ytk ingest` works on Reddit threads via `old.reddit.com` URLs (verified live);
`www.reddit.com` 403-blocks generic clients. Limitation: the scrape captures
the post but few comments — for discussion threads a dedicated `.json` fetch
path would be the improvement. Out of scope here; noted for a future
reddit-ingest feature.

## Non-goals

Public tunnel/exposure, authentication layer, push notifications, native app
(now), mobile 3D map, offline mode for live features, VPS migration.

## Error handling

- Hub unreachable (Mac asleep/off tailnet): Shortcut alerts + copies link;
  `/m` pages are simply unreachable — acceptable, vault reading still works.
- App not installed for a scheme link: JS timeout falls back to `https`.
- iCloud lag on phone: inherent to Layer 0; live data belongs to Layer 2.

## Testing

- Queue endpoint: request test for bare `{url, thought}` POST.
- `/m` pages: FastAPI route tests (render, data presence); manual pass on
  the phone over Tailscale for link-opening behavior (scheme -> app).
- Retrieval untouched: no search-behavior changes, so the eval gate (#85) is
  not implicated; `/m/ask` calls existing search paths as-is.
