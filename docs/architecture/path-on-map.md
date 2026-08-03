# The road on /map — implementation plan

Backend shipped: `GET /api/path` (hub.compute_path, tests in
tests/test_path_api.py). This plan covers the map surface. Measured
constants it inherits: cosine retrieval, content-identity dedup, stops=9 /
k=3 defaults, support judged against the returned corpus background;
extrapolation capped at t=1.25 if a slider ever exists (20.3); CSLS is an
optional diversity knob at a known support price of ~0.012 (19.2), absent
from v1.

## The safe rendering path: ride the label pipeline, not the GL closure

The renderer already projects world -> screen every frame for HTML labels
and SVG leader lines. The route polyline is the same class of object: a
screen-space overlay derived from projected positions. v1 therefore draws
the road as an SVG path in the existing label/leader-line container —
zero new WebGL programs, zero new buffers, nothing added to `destroy()`,
pan/zoom inherited at the label refresh cadence. Promotion to a GL ribbon
(the filament program family) is a later, separate decision and follows
the decomposition doc's extraction order if taken.

## Slices, witness-first (decomposition-doc discipline)

1. **API decode** — `web/src/api/path.ts` + `path.test.ts`: decode the
   /api/path payload, tolerate missing fields.
2. **Pure join** — `web/src/lib/mapRoute.ts` + `mapRoute.test.ts`: join
   itinerary video_ids to map point positions; waypoints missing from the
   map are skipped, never invented; output is an ordered position list
   plus per-stop metadata. Pure function, no DOM, no GL.
3. **Road mode interaction** — in-page control on /map (page controls
   never in the nav, #136): toggle road mode; the next two point clicks
   (existing picking) fill slots A and B; fetch; store as controlled
   React state (single-owner rule — no DOM pokes).
4. **Overlay render** — SVG path + waypoint dots in the label container,
   driven by the same projection tick as labels. Chromium test: road mode
   + two synthetic clicks yields an SVG path with the expected vertex
   count; pixel-variance check per the live-verify rule (a green test
   with a blank canvas is the documented failure mode).
5. **Itinerary panel** — side panel listing stops (title, support vs
   background); click a stop -> existing fly-to. Radix/shadcn primitives,
   Tailwind against observatory tokens, no styles.css additions (#136).
6. **Visual QA with the user on the live hub** — name the surface
   exactly: /map, road mode, after `uv tool install --reinstall .` and
   `launchctl kickstart -k gui/501/com.ytk.hub`.

Later, separately: feature lanes under the itinerary (fingerprints.npz is
a repo artifact, not shipped with the wheel — lanes need either a served
sidecar or a build step; decide then), Haiku narration as optional gloss
per stop (18.5's verdict: lanes name what changes, narration says what it
means).
