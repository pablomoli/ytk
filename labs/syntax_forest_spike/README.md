# Syntax forest spike (#217, rung 4) — parked 2026-09-14

Throwaway code kept so the spike can be regenerated, not a module. Last
published state: v8 at
https://claude.ai/code/artifact/945807c6-5ff2-495f-8492-7a3a1611714c

    uv run --extra dev python labs/syntax_forest_spike/spike_stand.py /tmp/forest_stand.json
    uv run python labs/syntax_forest_spike/build.py /tmp/forest_stand.json /tmp/forest_spike.html

`spike_stand.py` selects files (200-5000 named nodes, 36k-node budget for
Python and 34k for web/src), lays each out under the three section 53 rules,
and attaches git facts (first/last commit, commit count) and import fan-in.
`template.html` is the page with a `__DATA__` slot; `build.py` fills it.

What the eight versions settled, in order:

1. Two trees under the rules read as trees at once; the owner's read was
   "corals", accepted as the vision.
2. A stand of 66 files in directory stands on sunflower spirals.
3. Prerendered fully grown (growth kept behind `?grow`); water-current sway
   in the vertex shader; tint per tree by first-commit rank on a
   violet-to-gold ramp; leaves brighter with recent edits; ground ring by
   import fan-in.
4. Smooth 3D value noise over resting position offsets phase, amplitude and
   direction; eight dials on the page.
5. Four presets as visions: deep swell (default), reef surge, still water,
   shimmer. Deep swell: amp 0.018, speed 0.55, height power 1.6, noise
   scale 0.12, phase spread 0.45, direction spread 1.1, jitter 0.4, stand
   wave 0.9.
6. Fourteen-sided tapered tubes (per-instance base/top radii) and joint
   spheres at every segment base.
7. No sphere at the root; trunk flares 1.35x at the ground; fine spheres
   for joints above radius 0.45.
8. Rigid links: the height-dependent translation field was a shear and read
   as stretching. Each segment now moves as a body (base follows the field,
   axis re-aims at the carried tip, length kept, normals rotated).

Open when resumed: joint visibility on thick limbs under rigid links
(threshold 0.45 is the lever); shared normals along chains for the bake;
the trunk stub from the area law at the module node.
