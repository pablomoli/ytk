"""Paths for regenerable E2 SAE artifacts.

The run store stays outside repositories and worktrees so cached vectors and
checkpoints cannot enter version control. Set YTK_SAE_STORE to select a
scratch store; the default is ``~/.ytk/sae``.
"""

from __future__ import annotations

import os
from pathlib import Path

STORE = Path(os.environ.get("YTK_SAE_STORE") or Path.home() / ".ytk" / "sae")
DATA = STORE / "data"
CKPT = STORE / "checkpoints"
