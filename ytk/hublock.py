"""Single-instance guard for the hub (#38).

An exclusive flock on ~/.ytk/hub.lock, taken before uvicorn binds; the second
instance sees the lock and exits without ever reaching the port. The returned
file object must stay open for the life of the process — closing it releases
the lock.
"""

from __future__ import annotations

import fcntl
import os
from pathlib import Path
from typing import IO


def lock_path() -> Path:
    """YTK_HUB_LOCK overrides so tests never contend with the live hub."""
    env = os.environ.get("YTK_HUB_LOCK")
    return Path(env) if env else Path.home() / ".ytk" / "hub.lock"


def acquire(path: Path | None = None) -> IO[str] | None:
    """Take the exclusive lock; None when another instance already holds it."""
    path = path or lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "w")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle
