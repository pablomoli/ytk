# The packet page (#213): design record

Session 081, 2026-09-06 to 2026-09-07. A design session, not a build: the
owner brainstormed, picked among mockups, and iterated a live prototype
fifteen times. Nothing here is hub code. This folder holds what a fresh
session needs to build the real route without re-deriving any decision.

> **Later (session 082, 2026-09-13):** built. The route is `/packet` (the
> track) and `/packet/<id>` (the page below it), `web/src/routes/packet*.tsx`,
> the track in `web/src/lib/packetTrack.ts` with the locked values baked in
> and the slider, nest and ghost machinery removed. The reconstruction runs
> server-side in `ytk/headless.py` (`station_at`, `track`, `packet`), served
> at `/api/packet` and `/api/packet/<id>`; frames at
> `/api/evidence/frame/<id>/<n>`. Answering goes through the hub's outbox
> answer route, the same path the digest cards use. `t` is the replay
> instant on both routes; absent is live. One departure from the generator,
> measured on 534: the writer's row, not `closed_at`, hands the packet from
> the student to the checkers. The generator and template below remain the
> design record; they are not the route's source.

> **Later (session 082, evening):** a third element, the waves: seven
> phosphor channels under rose and field (`web/src/lib/packetWaves.ts`).
> Every peak normalized; activity is frequency and harmonics; a model at
> work is green. Tuned on a knob lab and baked. One rule bends here by the
> owner's choice with the alternatives in view: the channels wear station
> hues (tint 1.0) over the phosphor ramp (0.57). Temperature by load was
> tried and dropped as imperceptible under the tint; alarm red was tried
> and left off.

> **Later (2026-09-14):** merged to master, 13 commits unsquashed, then two
> more branches. The field camera is the owner's now (drag orbits, wheel
> zooms, the slow turn resumes after release) and starts above the surface
> looking down (`FIELD.tilt` 0.22, was 0.75 in the locked values above, by
> the owner's request). The field is one shader surface: height ramp, a
> one-pixel grid at any zoom, nine contour lines, fog, a crowded station
> widening as it rises, and a green sonar ring while a model works. The
> wire-and-fill pair above is gone. Live at the hub's `/packet`; the running
> record is `docs/architecture/packet-page.md`.

## What exists

| artifact | where | state |
|---|---|---|
| Live prototype, v15 | https://claude.ai/code/artifact/36d796b2-7e20-45a4-9f0a-7733ae3bac8d | the reference for the route |
| Design canvas (static mockups: the row with the panel, plus two rejected sketches on page 2) | https://claude.ai/code/artifact/60d6c29a-b47a-4185-be88-97bd185314c9 | the panel design the owner liked, superseded in detail by v15 |
| `gen_packet_page.py` | this folder | regenerates the prototype from the ledger and the evidence files |
| `packet-page.template.html` | this folder | the page; `__DATA__`, `__VIEWS__`, `__IMGS__` are filled by the generator |

Regenerate: `uv run python docs/design/packet-page/gen_packet_page.py [out.html]`.
The output embeds real ledger rows, item titles, takes and two frames, so it
is vault-grade content: never commit the generated page.

## What the page is

One instrument page in the footage-first sense (rails as URL state, readouts
that are measured state, no digest pixels; #204 binds). Two parts.

**The track**, one WebGL stage split in two, one instant:

- **rose** (left). Seven stations are seven sectors on a ring, runner at the
  top and clockwise to owner. A packet is a bar in its station's sector, its
  length the time held on a log scale (a minute to ten days fills the ring,
  blended 0.4 toward linear). Green with a pulse while a model holds it.
  Bars are hit-tested as whole wedges by a ray onto the floor.
- **field** (right). The seven stations sit on a plane (four across the
  back, three across the front) and one continuous surface rises over them:
  each station a Gaussian hill whose height is the sum of log holds there,
  green where a model is working. Value noise warps the ground and adds a
  swell that drifts with time; the camera turns slowly.
- Hover a packet for title, station, hold, rounds, tokens, calls. Click to
  open its page. J and K walk the packets, Esc closes.

**The packet page**, below the track, for the selected packet:

- Header: id, title, source, transcript origin, packet hash, bundle hash,
  the sticky note with its kind, station and since, the pad of eight calls
  (red past eight), and the packet agreement: the draft's view hash against
  the grade's, green "same packet" or red "packet mismatch", grey when the
  item predates #212. Buttons copy the headless verbs for this item and
  attempt: `ytk view`, `ytk grade`, `ytk item`.
- Packet column: the strip (transcript span with spot checks above it, the
  frame rail below with shown, not shown and bounced frames), the unit list
  with weights and budget, the transcript folded to the first fourteen lines
  plus a window around every cited second with cited lines lit, the frames.
- Rounds: every attempt on disk. Findings in with where they point, the
  draft's thesis with its counts and tags, the writer and marker rows (model,
  tokens, seconds), the verdict with layer, bounces and spot checks, and the
  hash the grade read. Latest round open, earlier ones folded to one line.
  An open round shows only what the clock has reached.
- Asks: every ask raised for the item, the reason, the options as buttons
  when open (keys 1 to 4), the chosen one lit, the owner's text. "say what
  is wrong" opens a text box. Answers are local in the prototype and print
  the command they map to: `ytk ask answer <id> <choice> [--text]`.
- Connections: the links the librarian argued, marked approved on answer.
- Trail: the register, last eight with a toggle for all.
- Every `t:<s>` and `frame:NNN` in a finding, bounce or spot check is a
  link: a second scrolls the transcript to that line and flashes it, a
  frame opens a lightbox captioned with the packet hash.

## Decisions on record (do not relitigate)

- Skin is the hub's: `web/src/theme.css` tokens, Newsreader only, brass
  accent, green for "here", one alarm red for bounces and mismatches, DIM
  grey only for what was not shown. What the @rndyrbrts study contributed is
  the skeleton: corner brackets, readouts, keymap, URL state, one accent on
  near-black. No palette law.
- Locked values, chosen by the owner from live URLs: rose tilt 0.50, scale
  1, no ghosts, weight by ink, gap 0, hub 0, wedge taper, side by side,
  curve 0.4, ticks 0.5, rings 0.5, spokes 1, rounds-heat 1, focus 1. Field
  tilt 0.75, spacing 0.30, reach 0.40, lift 1, grain 1, memory 0, focus 1,
  rounds 1. These are constants in the template's `LOCKED` and
  `LOCKED_LAY`; the slider machinery is dormant, not removed.
- Rejected, with the reason: kanban columns (reads as a board); scatter
  strips and median labels (numbers where a shape would do); concentric
  rings and station dials (unreadable at a glance, a speedometer look);
  dots by log depth, a "usual hold" line, and bars by height (each still an
  axis the owner did not care about); a ring of eight-segment "pad" glyphs
  (segments unreadable, id useless); the orrery in Archivo and lime (off the
  hub theme); the register direction; the nest (nested circles by station,
  flower-scalloped) dropped as not needed on this screen; per-stage flowers
  in rose (a regression); an island edge on the field (a regression).
  Nothing filed is drawn: the page is a HUD of what is in flight.
- The track answers four things only: which station, how many there, how
  long each has been there, and whether a model holds it. Labels bare, on
  hover. Sliders exist for exploration, not for the page.

## The reconstruction the route needs

`station_at(item, t)` in the generator is the logic the hub route has to run
server-side, in `ytk/headless.py`, not in the page. From the ledger rows,
the attempt files and the answers table it returns where a packet is at
any instant and since when. The cases that were wrong until measured:

- an answered ask puts the packet back at the proctor until the loop
  consumes the answer (the owner row in the ledger lands at pickup, not at
  the answer);
- a connect run with no links argued files the item;
- an attempt is at the student between `opened_at` and `closed_at`; between
  the enricher's completion row and the grade row it is at the
  spell-checker, then at the teacher for the grade's `duration_ms`;
- the live pad is model calls to date, and the librarian's call after an
  acceptance at the cap makes nine of eight, which the page shows in red.

The instant is a URL parameter (`t`, seconds from 22:12:00Z on 09-06 in the
prototype). The route should default to now and read live files.

## Verification protocol used on every version

Headless Chromium through Playwright, never the owner's browser: console
errors, frame rate readout, stage height over ten seconds (the camera-slide
lesson), a screenshot per state, and for interactions a probe that hovers,
clicks and reads the DOM back. Frame rates in the record are the software
renderer's; the GPU runs faster.

## Open, for the build

1. Whether answering lives on this page or stays on the inbox ask cards.
2. Whether the packet page is its own route (`/packet/<id>`), reachable from
   an ask card and from `ytk item` output as #213 phrases it, with the track
   at `/packet` above it, or one page.
3. A JSON shape for `item_show` and `view_show` that carries what the page
   needs: transitions, attempts with findings and verdicts, asks with
   answers, trail, view summary with a transcript excerpt. The generator's
   `DATA`, `VIEWS` and `IMGS` are the draft of that shape.
4. Frames: the prototype embeds 534's two; the route serves them from
   `evidence/frames/` on demand.
5. The CSS ratchet (#136): the template's stylesheet is prototype CSS; the
   route styles with Tailwind utilities on the tokens and Radix primitives,
   and adds nothing to `styles.css`.
