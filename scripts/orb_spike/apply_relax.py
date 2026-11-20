"""Write the neighbors layout into ~/.ytk/orb-spike/map.json. python apply_relax.py [raw]
Default runs the worktree's ytk.spheremap.evened over the raw bearings kept in map.raw.json."""

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ytk.spheremap import evened

here = Path.home() / ".ytk" / "orb-spike"
d = json.loads((here / "map.raw.json").read_text())
if sys.argv[1:] != ["raw"]:
    p = evened(np.array(d["content"]["sphere"]["radial"], float))
    d["content"]["sphere"]["radial"] = [[round(float(x), 4) for x in r] for r in p]
(here / "map.json").write_text(json.dumps(d))
print("wrote", sys.argv[1:] or "evened")
