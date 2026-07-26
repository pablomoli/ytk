"""Hatchling build hook: build the React SPA into the wheel (#108).

web/dist is not committed. Standard wheel builds run `vp build` in web/ and
force-include the result at ytk/ui/webdist, where server.py's _WEB_DIST looks
for it. Editable installs skip the build entirely and serve the repo's own
web/dist, so `uv sync` never pays for a frontend build.

Every failure here must be loud. A wheel that installs with a missing or
near-empty webdist produces a hub that serves a blank page, which is strictly
worse than a failed build.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

# A real bundle is ~1.6MB of JS/CSS/fonts. Anything under this is a broken
# build that somehow exited 0 (e.g. rolldown externalizing missing deps and
# still emitting), not a smaller-than-usual one.
_MIN_BUNDLE_BYTES = 200_000


class CustomBuildHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        if version == "editable":
            return

        web = Path(self.root) / "web"
        dist = web / "dist"

        vp = shutil.which("vp")
        if vp is None:
            raise RuntimeError(
                "building the ytk wheel requires `vp` (vite-plus) on PATH to "
                "compile the SPA — web/dist is not committed, so there is no "
                "prebuilt bundle to fall back to"
            )

        # A clean export (git archive) has no node_modules; the tracked
        # web/pnpm-workspace.yaml and lockfile make a fresh install possible.
        if not (web / "node_modules").is_dir():
            self.app.display_info("hatch_build: installing web dependencies (vp install)")
            subprocess.run([vp, "install"], cwd=web, check=True)

        self.app.display_info("hatch_build: building SPA (vp build)")
        subprocess.run([vp, "build"], cwd=web, check=True)

        index = dist / "index.html"
        assets = list((dist / "assets").glob("*.js")) if (dist / "assets").is_dir() else []
        total = sum(f.stat().st_size for f in dist.rglob("*") if f.is_file())
        if not index.is_file() or not assets or total < _MIN_BUNDLE_BYTES:
            raise RuntimeError(
                f"vp build exited 0 but web/dist looks broken: "
                f"index.html={'present' if index.is_file() else 'MISSING'}, "
                f"js assets={len(assets)}, total bytes={total} "
                f"(need >= {_MIN_BUNDLE_BYTES}) — refusing to package a hub "
                f"that would serve a blank page"
            )

        build_data["force_include"][str(dist)] = "ytk/ui/webdist"
