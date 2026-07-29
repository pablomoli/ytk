# LinkedIn draft — post 1: the map (vision-setter)

Attach: `05-chained-vs-traced-filaments.png` (lead image).
Alternate: `02-uniform-vs-adaptive.png` if the feed crops the pair badly.

---

I've been building a map of my own mind, and it looks like the universe.

For the past months I've saved everything I learn from into one system:
every YouTube video I watch, every article, every note I write. Each one
becomes a point in space — placed by what it *says*, not where I filed it.
Four thousand notes so far.

Plot the density of those points and you get fog: bright where I've spent
my attention, dark where I haven't. And the fog isn't shapeless. It has
ridges — thin bright filaments connecting the clusters, exactly like the
cosmic web that links galaxies.

That's not a metaphor I invented. It's the same math. Astronomers trace
filaments through galaxy surveys with a ridge-following algorithm, so I
used it on my notes: step along the ridge, correct back onto the crest,
repeat. The picture attached is the before and after. My first attempt
connected nearby points with line segments and produced the left panel —
broken dashes, 27 fragments. Walking the ridge properly produces the
right panel: continuous strands you can follow from one interest into
the next.

What I've learned building it, the honest version:

Every gradient is hand-derived and checked against finite differences.
My math minor is finally doing production work.

I keep a second renderer in matplotlib whose only job is to disagree
with the first one. It has caught three bugs the pretty renderer hid.
Never trust only the renderer you also wrote.

The measurement that surprised me most: 98% of my notes sit within two
steps of a 225-point skeleton. Thousands of hours of curiosity,
compressible to a wireframe — and the notes far from any strand are the
most interesting ones. That's the frontier: the things I'm curious about
that haven't connected to anything yet.

The map is one piece of a larger system I'm building in public — search,
recall, a feed that knows my taste. Next post: what the fog is actually
made of, and the dial that nearly ruined it.

---

## Alt hooks (pick one, first line is the whole ad)

1. "I've been building a map of my own mind, and it looks like the universe." (current)
2. "Astronomers trace filaments between galaxies. I used their algorithm on 4,000 of my own notes."
3. "This is every video I've watched and every note I've taken — rendered as a nebula."

## Cut candidates if too long for the feed

- The finite-differences line (keep the matplotlib witness — it's the
  stronger craft signal and the more repeatable lesson).
- The closing series tease can shrink to "Next: what the fog is made of."

## Register checks

- No tool names, no "ytk", no stack talk — the system is described by
  what it does. Specifics live in the figures.
- Claims traceable to measured numbers: 27 fragments, 225 vertices,
  98.3% within 2h, 4,067 notes (rounded in prose).
- Learning shown as method (witness renderer, derivative checks), not
  as humility boilerplate.
