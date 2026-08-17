# The experiment record — directory rules

The house-style contract is `README.md` in this directory and it is
binding; read it before drawing anything. `../experiments.md` is the
index: every section gets a row there (number, name, what it asked,
what it found) when it lands.

## The record is also published

The public face of this record lives in the spacecraft repo
(`~/Developer/spacecraft`, deploys to pablomolina.space). The
`/experiments` page there renders one card per section, generated from
each section's lead figure and its question row in
`../experiments.md`; five sections carry full on-site writeups.

When a section lands here:

- add its row to `../experiments.md` — the site's card hook quotes the
  "what it asked" column verbatim, so write it as the public one-liner
  it will become
- make sure the section has at least one committed still: the site's
  card uses the first PNG in the folder, and a video-only section
  cannot be indexed (issue #190 is the record of that mistake)
- if the section deserves a full public writeup, add it in the
  spacecraft repo: entry in `src/content/experiments.js` (opening +
  deep section + footnotes), figure WebPs under
  `public/images/experiments/`, `featured: true` only if it should
  ride the journey's gallery rail
