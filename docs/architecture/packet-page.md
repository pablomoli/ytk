# The packet page (#213)

Built 2026-09-13/14 from the session-081 design record
(`docs/design/packet-page/README.md`, which holds the decisions, the rejected
directions and the locked values; this file is what runs).

## What it is

One instrument page for the curator engine (`docs/architecture/curator-engine.md`):
where every packet in flight is, and one packet's whole record. Two routes:

- `/packet`: the track. Three instruments in one column: the **rose** (seven
  stations as sectors on a ring, a packet a bar whose length is the hold on a
  log scale), the **field** (seven stations on a plane, one shader surface
  rising over them), and the **waves** (seven phosphor channels, one per
  station). The track answers four things only: which station, how many
  there, how long each has been there, whether a model holds it. Nothing
  filed is drawn.
- `/packet/<id>`: the same track with that bar lit, and the page below:
  header (station, since, the pad of calls, the draft's view hash against
  the grade's), the packet column (strip, units, the transcript folded
  around cited seconds, frames), every round (findings in, draft out,
  verdict out), asks (answerable), connections, the trail.

`t=<iso>` on either route is a replay instant; absent is live, polled every
five seconds. Selection is URL state: a click, `j`/`k`, a digest ask card's
link and the path `ytk item` prints all agree; `esc` returns to `/packet`.

## Data flow

```
ledger (activity, asks, answers, takes)   evidence/{views,attempts,drafts,frames}
                 \                              /
                  ytk/headless.py: history() -> station_at(h, t, working)
                                   track(conn, t)    packet(conn, item_id, t)
                                          |                    |
ytk/ui/server.py:              GET /api/packet[?t]   GET /api/packet/<id>[?t]
                               GET /api/evidence/frame/<id>/<n>   (guarded under the evidence dir)
                                          |                    |
web/src/api/packet.ts:         useTrack(t)            usePacket(id, t)
web/src/routes/packet.tsx      (layout: the track, readouts, j/k/esc)
web/src/routes/packet.$id.tsx  (the page; answers POST /api/outbox/answer, the digest's path)
```

The MCP `item_show` / `view_show` stay text; the JSON shape lives in the hub
API only.

## The reconstruction

`station_at` returns the station, since when, and a note, from the rows at
or before `t`. The cases that were wrong until measured, each a test in
`tests/test_packet.py`:

1. An answered ask sits at the proctor until the loop picks it up: the
   answers row lands at the answer, the owner's activity row at pickup.
2. A connect with nothing argued (or a `connect-none` row) files the item.
3. An open attempt is the student's until the writer's row lands (not until
   `closed_at`, which is stamped at the verdict), then the spell-checker's
   until the grade row, then the teacher's for the grade's `duration_ms`
   when replaying.
4. The pad counts every row with tokens; the librarian's call after an
   acceptance at the cap makes nine of eight, drawn red.
5. Live, the teacher and the librarian are invisible in the ledger (their
   rows land when the verb ends), so a live instant reads the loop's
   `working_on.stage.key` (`enrich`, `checks`, `grade`, `connect`) and maps
   it to the station. A replay instant never consults the loop.

Verified end to end on item 787 (2026-09-13): twelve station changes,
every one explained. The engine bug that run surfaced (a patch attempt
returning a byte-identical draft, graded anyway) is #216.

## Values and where they live

- `web/src/lib/packetTrack.ts`: `ROSE`, `FIELD` (tilt 0.22 since the
  overhead camera), `MOTION`, `GLOW`, `DIM`; the field shader's ramp, nine
  contours, fog 16 to 42.
- `web/src/lib/packetWaves.ts`: frequency, motion, harmonics, breath, idle,
  persist, offset (the owner's, read off a knob lab); `RAMP` 0.57, `HUES` 1,
  `GREEN` 1. Channels never overlap; every peak is normalized; activity is
  frequency, never height.
- No sliders on the real page. A knob lab existed under `?lab=1` for one
  evening and was removed once the values were chosen.

## Verification protocol

Headless Playwright Chromium with `--use-gl=angle --use-angle=swiftshader`,
never the owner's browser: console errors, the fps readout, stage height
over ten seconds, a screenshot per state, and for interactions a probe that
hovers, clicks and reads the DOM back. The rose turns at 0.042 rad/s, so a
probe clicks right after a hover hit, not after a screenshot. To view a
branch without a second curator loop, serve `ytk.ui.server.app` with its
lifespan patched to a no-op on a spare port; `just ui 8877` is refused by
the hub lock and overriding the lock would run two loops on the live ledger.

## Open

- The first-click band: the open ask, the latest verdict and the thesis in
  the header, and the cover next to the id.
- Field labels overlap when the camera turns; leader lines to summits.
- Beacons (a vertical line per packet) instead of sprites on the field.
- Trail rows as links to their instant, so a replay is one click.
- `track()` loads every non-grandfathered item's history per poll; filter by
  last state in SQL first when the ledger grows.
