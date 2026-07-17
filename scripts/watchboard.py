"""Live terminal dashboard for long-running ytk work — run it in a tmux pane.

Renders, refreshing every 2 s:
  - the current ops run from ~/.ytk/ops-status.json (steps, progress, ETA)
  - the tail of /tmp/ytk-encoder-eval.log (raw worker output)
  - the last few ops-journal milestones
  - hub liveness (:6969) and git HEAD

Stdlib only, ANSI only, no alternate screen — scrollback survives ctrl-c.

  uv run python scripts/watchboard.py [--interval 2]
"""

import argparse
import json
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

STATUS = Path.home() / ".ytk" / "ops-status.json"
JOURNAL = Path.home() / ".ytk" / "logs" / "ops-journal.md"
WORKLOG = Path("/tmp/ytk-encoder-eval.log")

DIM = "\033[2m"
BOLD = "\033[1m"
BRASS = "\033[33m"
RED = "\033[31m"
GREEN = "\033[32m"
RESET = "\033[0m"
MARK = {"done": f"{GREEN}[ok]{RESET}", "running": f"{BRASS}[..]{RESET}",
        "fail": f"{RED}[XX]{RESET}", "skip": f"{DIM}[--]{RESET}"}


def tail(path: Path, n: int) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="ignore").splitlines()[-n:]
    except Exception:
        return []


def age_s(iso: str) -> float:
    try:
        then = datetime.fromisoformat(iso)
        return (datetime.now(timezone.utc) - then).total_seconds()
    except Exception:
        return -1


def hub_state() -> str:
    try:
        with urllib.request.urlopen("http://127.0.0.1:6969/api/ready",
                                    timeout=1) as r:
            warm = json.loads(r.read()).get("search")
        return f"{GREEN}up{RESET}" + ("" if warm else f" {DIM}(warming){RESET}")
    except Exception:
        return f"{RED}down{RESET}"


def git_head() -> str:
    try:
        return subprocess.run(
            ["git", "log", "-1", "--format=%h %s"], capture_output=True,
            text=True, cwd=Path(__file__).resolve().parents[1], timeout=2,
        ).stdout.strip()[:70]
    except Exception:
        return "?"


def bar(cur: int, total: int, width: int = 34) -> str:
    fill = int(width * cur / total) if total else 0
    return "#" * fill + "-" * (width - fill)


def render() -> str:
    lines: list[str] = []
    now = time.strftime("%H:%M:%S")
    lines.append(f"{BOLD}{BRASS}ytk watchboard{RESET}  {DIM}{now}{RESET}  "
                 f"hub {hub_state()}  {DIM}{git_head()}{RESET}")
    lines.append("")

    try:
        st = json.loads(STATUS.read_text(encoding="utf-8"))
    except Exception:
        st = {}
    if st:
        upd = age_s(st.get("updated", ""))
        stale = (f"  {RED}stale {int(upd // 60)}m{RESET}"
                 if upd > 300 and any(s["state"] == "running"
                                      for s in st.get("steps", [])) else "")
        lines.append(f"{BOLD}run{RESET} {st.get('run', '?')}"
                     f"  {DIM}{st.get('intent', '')}{RESET}{stale}")
        for s in st.get("steps", []):
            detail = f"  {DIM}{s.get('detail', '')[:60]}{RESET}" if s.get("detail") else ""
            lines.append(f"  {MARK.get(s['state'], '[??]')} {s['name']}{detail}")
        p = st.get("progress")
        if p and p.get("total"):
            eta = f"  eta {p['eta_min']:.0f}m" if p.get("eta_min") is not None else ""
            rate = f"  {p['rate']} vec/s" if p.get("rate") else ""
            lines.append(f"  {BRASS}{bar(p['current'], p['total'])}{RESET} "
                         f"{p['current']}/{p['total']}{rate}{eta}"
                         f"  {DIM}{p.get('label', '')}{RESET}")
    else:
        lines.append(f"{DIM}no ops run recorded yet{RESET}")

    lines.append("")
    lines.append(f"{BOLD}worker log{RESET} {DIM}{WORKLOG}{RESET}")
    for ln in tail(WORKLOG, 10):
        lines.append(f"  {DIM}{ln[:110]}{RESET}")

    lines.append("")
    lines.append(f"{BOLD}journal{RESET} {DIM}{JOURNAL}{RESET}")
    for ln in tail(JOURNAL, 5):
        lines.append(f"  {ln[:110]}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=2.0)
    args = ap.parse_args()
    while True:
        frame = render()
        print("\033[H\033[2J" + frame, flush=True)
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
