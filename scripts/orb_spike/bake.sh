#!/bin/zsh
# Rebuild everything the orb spike server reads, into ~/.ytk/orb-spike (personal data, kept out of the repo).
# Read-only on the live map, store, vault and hub (:6969 must be up for the library and queue reads).
set -euo pipefail
cd "${0:A:h}/../.."
O=~/.ytk/orb-spike
mkdir -p $O
PY=.venv/bin/python
D=scripts/orb_spike
$PY $D/knn_attach.py 12                     # live map + neighbors + cover aspects
cp $O/map.json $O/map.raw.json
$PY $D/apply_relax.py                       # even out the neighbors layout
$PY $D/orb_vecs.py                          # one store vector per tile
cp $O/map.json $O/map.656.json              # the snapshot grow_map seats new notes onto
cp $O/orb_vecs.npy $O/orb_vecs.656.npy
$PY $D/grow_map.py                          # seat library notes that have no tile yet
curl -sf -m 20 http://localhost:6969/api/queue -o $O/queue.json
$PY $D/ring_bake.py                         # the pending ring and its cover atlas
