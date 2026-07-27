# pyright: basic
"""Import-weight regression gate for the CLI (#146).

`ytk --help` must not pay for chromadb, the Claude Agent SDK, or yt-dlp.
Presence in sys.modules after `import ytk.cli` is the precise, non-flaky
signal — a timing threshold would rot.
"""

from __future__ import annotations

import subprocess
import sys

HEAVY_MODULES = ("chromadb", "claude_agent_sdk", "mcp", "yt_dlp")


def test_cli_import_does_not_pull_heavy_modules():
    probe = (
        "import sys, ytk.cli; "
        f"heavy = [m for m in {HEAVY_MODULES!r} if m in sys.modules]; "
        "sys.exit('heavy imports leaked into ytk.cli: ' + ', '.join(heavy) if heavy else 0)"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr.strip()
