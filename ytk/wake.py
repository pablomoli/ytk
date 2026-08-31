"""Out-of-process loop nudge (#197 P5).

Surfaces insert their event rows, then POST /api/loop/wake at the hub. Best
effort by design: a lost or failed nudge is caught by the loop's 60-second
poll, and a down hub drains the backlog on start.
"""

from __future__ import annotations

import urllib.error
import urllib.request

NUDGE_TIMEOUT_S = 1.0


def nudge_loop() -> bool:
    """POST the wake endpoint; True when the hub answered."""
    from .config import load_config

    hub = load_config().hub
    url = f"http://{hub.host}:{hub.port}/api/loop/wake"
    req = urllib.request.Request(url, data=b"", method="POST")
    try:
        with urllib.request.urlopen(req, timeout=NUDGE_TIMEOUT_S) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError, TimeoutError):
        return False
