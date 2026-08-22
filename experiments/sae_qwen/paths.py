"""Where the E2 SAE run store lives.

Outside the repo on purpose. The store is ~500MB of cached vectors and
checkpoints, all regenerable at fixed seeds, and any copy sitting inside a
worktree is a copy that can be committed by accident — 035b45c committed a
symlink to it and left every other worktree pointing at a loop. Set
YTK_SAE_STORE to run against a scratch store.
"""

from __future__ import annotations

import os
from pathlib import Path

STORE = Path(os.environ.get("YTK_SAE_STORE") or Path.home() / ".ytk" / "sae")
DATA = STORE / "data"
CKPT = STORE / "checkpoints"
