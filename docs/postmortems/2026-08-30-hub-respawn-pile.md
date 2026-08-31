# 2026-08-30 — Hub respawn pile: a wedged process plus launchd's KeepAlive, never a single spawner

## Summary

The hub (`com.ytk.hub`, port 6969) accumulated **23,355** `[Errno 48] address
already in use` lines in `~/.ytk/logs/hub.log`. The pile looked like one
specific piece of code respawning a second `ytk ui`, but tracing it (issue #38,
filed 2026-07-05) showed it is the interaction of two otherwise-small failures:
a damaged chroma `ytk_visual` collection that GIL-freezes the whole hub, and
launchd's `KeepAlive: true` respawning a doomed second instance forever. There
was no single spawner to hunt, and none was ever identified — because none
exists.

Severity: the hub is the always-on surface the owner works from, and the
respawn loop sustained itself until a human SIGKILLed every holder. Both halves
have now shipped: the GIL half as `a0881ab` (2026-07-25, closing #130), the
idempotent-startup half as `ebacc57` (2026-08-30, the curator engine's P1,
closing #38 — 57 days after it was filed). Numbers and the faulthandler dump
live in issue #130; the lock's design rationale in
`docs/architecture/curator-engine.md`. This investigation was never written up
by the session that diagnosed it; this doc is that record, written the night
the second half landed.

## Symptom

The triggering pattern, greppable in `~/.ytk/logs/hub.log`:

```
ERROR:    [Errno 48] error while attempting to bind on address ('127.0.0.1', 6969): address already in use
```

Filed as #38, "Something repeatedly respawns ytk ui": *some process keeps
trying to start a second `ytk ui`. Find the respawner (launchd agent? memo/snap
hotkey path? shell alias?).*

Recognizable if it recurs: a hub that "hangs on every restart," accepts TCP on
6969 but never answers `curl` (the connection sits `ESTABLISHED` forever), and
a log file dominated by bind errors. The repeating four-line unit in the log is
the loop's fingerprint:

```
ytk hub  http://127.0.0.1:6969
Ctrl-C to stop
ERROR:    [Errno 48] ... address already in use
[warm] visual index unresponsive — skipped (see #130)
```

Two greps size the loop without reading a line of code. The log holds **23,562**
startup banners against **23,355** bind failures: roughly 207 instances ever
won the port, and everything else was born dead. That ratio — not the raw
23,355 — is what distinguishes a respawn loop from one process retrying.

## Findings

**1. A blocked chroma `count()` on `ytk_visual` GIL-freezes the whole hub.**
`warm_search()` runs its warm-up in a daemon thread (`ytk/ui/hub.py:466`,
thread started at `:513`, called from the FastAPI lifespan at
`ytk/ui/server.py:45`), which is correct — it does not block the lifespan. But
the thread blocks inside chromadb's **Rust** `_count`, holding the GIL while it
waits (the `col.count() == 0` guards in `visual_similar`, `ytk/store.py:554`,
and `pending_visual_similar`, `:475`). While a Rust call holds the GIL, **no
other Python thread can execute a bytecode**, so uvicorn's event loop — alive
and sitting in `asyncio/runners.py:118`, per the faulthandler dump — can never
call `accept()`. The hub binds 6969 and then stalls forever. Python runs signal
handlers only in the main thread between bytecodes, and that is the starved
one, so **SIGTERM and SIGINT do nothing; only SIGKILL clears it**. Finding 1 of
#130.

**2. Every wedged process keeps `ytk_visual`'s HNSW segment open, poisoning it
for later readers.** Collection `44031b5b-2057-4669-a211-04d19326b8c7` holds
its vector segment at `cf2c0f3a-b270-4dc0-8d13-cd51b6b8690e`, whose
`header.bin` / `data_level0.bin` / `length.bin` / `link_lists.bin` stay open in
each wedged process — `lsof` caught two at once, pid 43990 on :6969 and pid
55742 on :6970. A raw chromadb `count()` on that collection never returns from
a brand-new client either, so **every process that touches it after the first
wedge blocks the same way**, including each launchd respawn. It reproduces with
a bare `chromadb.PersistentClient`, so it is not a `ytk.store` configuration
issue, and it is specific to that one collection: `ytk_segments_v2.count()`
returns 5656 in 0.28s. Finding 2 of #130, and the deepest of the three.

**3. launchd `KeepAlive: true` is the respawner — there is no application-level
spawner.** The agent at `~/Library/LaunchAgents/com.ytk.hub.plist` sets
`KeepAlive: true` and `RunAtLoad: true`. Its `ProgramArguments` is **not**
`ytk ui` but `/Applications/ytk.app/Contents/MacOS/ytk-hub`, a 52 KB arm64
Mach-O shim (built 2026-07-17) that reads `$HOME` and execs
`~/.local/bin/ytk ui` — visible only via `strings`, which is why reading the
plist alone does not answer "what is being respawned." When the wedged first
instance is killed, or the new one's bind failure is read as a crash, launchd
starts a fresh one. Before P1 the fresh instance went straight to
`uvicorn.run(...)` with **no idempotency guard** — nothing asked "is a hub
already on this port?" before binding. It failed to bind, exited, and launchd
respawned it. That loop is the pile. The original #38 ask was answered by
findings 1 and 3 together: the spawner is launchd honoring its own contract in
response to a wedge, not a faulty code path.

**4. Contributing conditions: a crowded store on a swapping machine.** Nothing
in the incident explains how `ytk_visual` became damaged in the first place,
and this remains genuinely unknown. Two conditions from #130 are the standing
suspects: several ytk processes hold the chroma store concurrently in normal
use (hub, `ytk-mcp`, CLI runs, parallel agent sessions), and the machine was
under real memory pressure at the time — swap at 2.47 GB of 3.07 GB, 10.8M
pageins. Recorded as conditions, not as a cause.

**Non-finding: the launchd plist, `uv tool install --reinstall`, and the
frontend were not the cause.** #130 reproduced the freeze from a clean `.venv`
on a fresh port with none of those involved. Full Disk Access / TCC loss was
ruled out too (a probe read `chat.db` in 0.00s). Recorded so the dead end is
not re-walked.

**Non-finding: the pile is not self-limiting through log growth.** Both
`StandardOutPath` and `StandardErrorPath` point at one unrotated `hub.log`, and
no `newsyslog.d` entry exists for ytk. 23,355 errors cost only 6.5 MB, so
nothing ever ran out of room and nothing ever complained. (`chroma.log`, on the
same non-rotation, is at 141 MB.) The absence of a size limit is why the pile
could grow for eight weeks unnoticed rather than announcing itself.

## Why so many things were wrong simultaneously

None of the three findings fails the hub on its own. A forever-stuck Rust
`count()` needs a damaged collection to recur — without the wedge, `count()` is
instant. A second instance failing to bind is harmless if binding is
idempotent; the fresh process would just exit, which is precisely what it does
today. And launchd KeepAlive is *supposed* to respawn a crashed process. That
is not a bug, that is the entire reason the agent exists. Each failure sat
below the noise floor of the others.

What compounded them is finding 2, and it is the one that turns an incident
into a loop. The wedge poisons the segment for *every later reader*, so respawn
number two is not merely "the port is taken" — it is a second process that
blocks forever and adds its own open file handles to the poison. The system
manufactures its own victims. A one-off corruption that should have cost one
restart instead became a permanent state that only a human killing every holder
could break, and the machine dutifully supplied fresh holders around the clock.

The GIL is what makes finding 1 invisible rather than merely bad. A Python-level
hang would show up as a slow endpoint; a hang inside a native call that holds
the GIL takes the process's ability to *report* anything with it, including its
ability to die on request. The failure mode is indistinguishable from a dead
socket, which is exactly the wrong signal: it invites you to restart, and every
restart feeds the loop.

The lesson generalizes past chroma. A hub meant to host a single-writer loop
(P2 and beyond in #197) cannot tolerate even one silent second copy racing it.
Single-instance has to be enforced at startup, structurally, because the two
things you would naturally lean on — the port and the process's own signal
handling — are both downstream of a component that can take them away.

## Repair

| commit | date | change |
|---|---|---|
| `a0881ab` | 2026-07-25 | `fix(hub): a blocked chroma count() must not freeze the server (#130)`. Adds `_probe_visual` (`ytk/store.py:341`): the count runs in a **throwaway subprocess** under `subprocess.run(..., timeout=25.0)`, cached in `_VISUAL_PROBE`; every visual path gates on `visual_index_ok()` (`:354`) and degrades to an empty result. |
| `ebacc57` | 2026-08-30 | `feat(engine): P1 — ledger, migrations, hub singleton lock, grandfather import (#197, closes #38)`. `ytk/hublock.py`: exclusive `flock(LOCK_EX \| LOCK_NB)` on `~/.ytk/hub.lock`, acquired at `ytk/cli.py:2958` before the Chroma wait and before uvicorn binds. Second instance prints one dim line and exits 0. |

The subprocess is the whole point of the first fix, and the docstring says why:
*that call cannot be interrupted or timed out in-process.* A thread cannot
escape it, a signal cannot reach it, and `timeout=` on anything in-process is a
promise the GIL will not let Python keep. The only thing that can be killed is
a separate process, so the probe pays a fork to buy back the ability to give
up. Anything defending against a GIL-holding native call needs the same shape.

`flock` over a pid file because the OS releases it on any death, including
SIGKILL — the one signal that was known to be in play here. `flock` over
port-binding because the lock is checkable without making a request, and
"binds but never answers" was the exact symptom.

**Verified live, 2026-08-30:** with the hub running, a second `ytk ui` printed
`hub already running; exiting.` and exited 0 while the first kept serving.

**The damaged collection was never repaired, and that is fine.** The last bind
error in `hub.log` is at line 91,969; the instance that starts after it never
fails, and still logs `[warm] visual index unresponsive — skipped (see #130)`.
`ytk_visual` is unresponsive to this day. The hub simply no longer dies on it —
which is the stronger outcome, and is production proof of `a0881ab` sitting in
the log. Rebuilding the collection is available via `reset_visual_collections()`
(`ytk/store.py:376`) whenever visual search is wanted back; it is not incident
recovery.

## What we got right

- **Did not stop at the first fix.** `a0881ab` fixed the wedge but would not
  have stopped the respawn pile from recurring on the next corrupted
  collection. The lock was kept as a separate layer and shipped separately,
  rather than declaring victory when the symptom disappeared.
- **Fixed the failure mode, not the corrupted data.** Cleaning the segment
  would have made the symptom vanish and taught nothing. Making the hub survive
  an unresponsive collection is why the log now shows a healthy hub reporting a
  broken index instead of a broken hub reporting nothing.
- **Diagnosed with a minimal reproduction before changing code.** The
  two-line `_visual_collection().count()` repro, plus the raw `chromadb` one,
  proved the location (chroma, not `ytk.store`) and killed the reinstall, plist
  and frontend theories before any of them cost a day.
- **Read the faulthandler dump instead of guessing.** The thread stacks named
  the exact frame holding the GIL and the exact starved main thread, which is
  also what explained the signal behavior — a detail no amount of reasoning
  about the symptom would have produced.
- **Closed the wrong framing of the issue.** #38's "find the respawner" was
  re-answered as "KeepAlive reacting to a wedge" rather than run as an
  open-ended hunt through hotkey paths and shell aliases.

## What we'd do differently

- **Wrote the number down, not the investigation.** 23,355 was measured in
  July; which process, which port, and the respawn chain sat only in issue
  comments until this doc, seven weeks later. The gap was the written record,
  not the code. A postmortem belonged with `a0881ab`, when the mechanism was
  fresh and the second half was still unbuilt — the state a postmortem is
  actually good at capturing.
- **Left #38 open for 57 days holding a known answer.** The mechanism was
  understood on 2026-07-26 and the fix was one flock. It shipped only because
  P1 happened to need it. A one-file fix whose cause is fully understood should
  not wait for an epic to adopt it.
- **Never asked the log the cheap questions.** `grep -c` on the startup banner
  against `grep -c` on the error, and reading the ten lines after the last
  error, take under a minute and produced two of this document's strongest
  claims — the 23,562/23,355 ratio and the proof that the fix works in
  production. Both were available the whole time.
- **Recorded the contributing conditions in an issue body and nowhere else.**
  The concurrent store holders and the swapping machine are the only leads on
  *how the collection got damaged*, which is still unknown. That thread was
  dropped once the symptom was handled.
- **Trusted a plist's `ProgramArguments` to be readable.** It names a compiled
  binary. The shim hop went unnoticed, and the doc's first draft asserted the
  plist points at `ytk ui`.

## Prevention

**Architectural rule.** A background agent that will host a single-writer loop
claims single-instance at startup with an exclusive lock, and the second copy
exits quietly — never rely on port binding alone. This is now the shipped
`hub.lock` doctrine (`ytk/hublock.py`), and the `UNIQUE` constraints on the
ledger's `items` and `answers` tables back it at the data layer: the process
lock and the schema make the same promise from two directions.

Second rule, from the repair: **any call into native code that can block
indefinitely gets a subprocess, not a thread and not a timeout.** In-process
defenses are unenforceable once the GIL is held. `_probe_visual` is the
reference shape — probe out-of-process, cache the verdict, degrade the feature.

**Lint / tooling.**
- A startup readiness check that fails loudly rather than hanging silently. The
  current shape of failure — binds, then never answers — is indistinguishable
  from a dead socket, and that ambiguity is what invited the restarts.
- Rotate `~/.ytk/logs/*.log`. A `newsyslog.d` entry or size cap on `hub.log`
  and `chroma.log` (141 MB, unrotated) turns a silent pile into something with
  a visible edge.
- Reconcile the installed plist with the one `ytk ui install` writes
  (`ytk/cli.py:2994`). The live agent runs the app-bundle shim; the code writes
  `{ytk_bin} ui` directly. Running `ytk ui install` today silently replaces the
  shim, and nothing warns about the divergence.

**Documentation.** This postmortem anchors the mechanism behind #38 and #130 so
the respawner hunt is not re-run. The wiring is `ytk/cli.py:2945` (the `ui`
command, lock then Chroma wait then bind), `ytk/hublock.py`, and
`~/Library/LaunchAgents/com.ytk.hub.plist` (whose real target needs `strings`).

**Cultural.**
- When an always-on agent accumulates a repetitive error pile, read the
  launchd plist's `KeepAlive` / `RunAtLoad` contract before assuming an
  application-level respawner exists. Supervisors do what supervisors do.
- Count the log before reading it. Ratios between two greps characterize a loop
  faster than any stack trace, and the lines *after* the last error say whether
  the fix held.
- A postmortem is written when the mechanism is understood, not when the last
  commit lands. Waiting for the second half cost this one seven weeks of detail.
