# Visual Index Circuit Breaker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `YTK_VISUAL_INDEX=off` prevent every production read and write to the damaged visual Chroma collections while leaving enrichment and text indexing operational.

**Architecture:** A dynamic storage-boundary predicate in `ytk.store` owns the switch and gives every public visual operation a neutral disabled result. Higher-level visual indexing checks the predicate before scanning files or loading SigLIP, and the one hub endpoint that currently reaches the private collection directly moves behind a public metadata reader.

**Tech Stack:** Python 3.13, ChromaDB, FastAPI, pytest, python-dotenv, launchd

## Global Constraints

- The default remains enabled; only the exact value `YTK_VISUAL_INDEX=off`, case-insensitive, disables the subsystem.
- Disabled mode must not create or access `ytk_visual` or `ytk_visual_pending`.
- Enrichment, memo routing, vault writes, and text search remain unchanged.
- Disabled readers return neutral values and disabled writers are no-ops.
- The production setting lives in `~/.ytk/.env` so hub, MCP, CLI, and scheduled processes share it.
- The persisted astronomy job is cleared only after its note is confirmed in the vault and text index.

---

### Task 1: Storage-boundary circuit breaker

**Files:**
- Create: `tests/test_visual_disabled.py`
- Modify: `ytk/store.py:316-525`
- Modify: `ytk/store.py:763-770`

**Interfaces:**
- Produces: `visual_index_enabled() -> bool`
- Produces: `get_visual_metadata(item_id: str) -> dict | None`
- Changes: every existing public visual reader and writer returns its documented neutral value when disabled.

- [ ] **Step 1: Write the failing storage-boundary tests**

Create tests that set `YTK_VISUAL_INDEX=off`, replace both private collection accessors with a function that raises `AssertionError`, and assert:

```python
assert store.visual_index_enabled() is False
assert store.visual_index_ok(timeout_s=0.01) is False
assert store.visual_count() == 0
assert store.visual_ids() == set()
assert store.pending_visual_ids() == set()
assert store.update_visual_metadata("ig:x", {}) is False
assert store.get_visual_embedding("ig:x") is None
assert store.get_visual_metadata("ig:x") is None
assert store.visual_similar(embedding=[0.0], n=1) == []
assert store.pending_visual_similar([0.0], n=1) == []
assert store.get_profile_visual_pool() == []
assert store.get_profile_visual_pool(pending=True) == []
```

Call every visual upsert/delete function and verify none reaches either patched accessor.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
uv run pytest tests/test_visual_disabled.py -q
```

Expected: failures because `visual_index_enabled` and `get_visual_metadata` do not exist and unguarded operations reach the raising accessor.

- [ ] **Step 3: Implement the minimal storage switch**

Add:

```python
def visual_index_enabled() -> bool:
    return os.environ.get("YTK_VISUAL_INDEX", "on").strip().lower() != "off"
```

Guard `visual_index_ok()` before its cached probe. Guard all public main and pending visual readers and writers before calling a collection accessor. Add `get_visual_metadata()` so callers do not need the private collection.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run:

```bash
uv run pytest tests/test_visual_disabled.py -q
```

Expected: all tests pass without either private collection accessor being called.

- [ ] **Step 5: Commit the storage boundary**

```bash
git add ytk/store.py tests/test_visual_disabled.py
git commit -m "fix(store): disconnect disabled visual collections"
```

### Task 2: Stop higher-level visual work before model or filesystem access

**Files:**
- Modify: `tests/test_visual_disabled.py`
- Modify: `ytk/visual.py:328-445`
- Modify: `ytk/ui/server.py:672-694`

**Interfaces:**
- Consumes: `store.visual_index_enabled() -> bool`
- Consumes: `store.get_visual_metadata(item_id: str) -> dict | None`
- Changes: disabled `index_covers()` returns `0`, `sync_pending_visual()` returns `(0, 0)`, and `embed_cover_for_save()` returns `False`.

- [ ] **Step 1: Write failing orchestration tests**

Patch `store.visual_index_enabled` to return `False`; patch `iter_covers`, `embed_images`, and private collection accessors to raise if called. Assert:

```python
assert visual.index_covers(skip_existing=True) == 0
assert visual.sync_pending_visual() == (0, 0)
assert visual.embed_cover_for_save(Path("unused.jpg"), "ig:x", {}) is False
```

Add an endpoint test proving `/api/visual-image?id=ig:x` returns `404` through `get_visual_metadata()` without importing `_visual_collection`.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
uv run pytest tests/test_visual_disabled.py -q
```

Expected: higher-level functions call the patched work functions or the endpoint reaches the private collection.

- [ ] **Step 3: Implement early returns and the public metadata boundary**

Place the enabled check before `iter_covers()`, queue loading, or `embed_images()`. Change `/api/visual-image` to call `get_visual_metadata()` and return `404` when it returns `None`.

- [ ] **Step 4: Run the focused and neighboring tests**

Run:

```bash
uv run pytest tests/test_visual_disabled.py tests/test_visual_pending.py tests/test_visual_text.py tests/test_store_delete.py tests/test_hub.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit orchestration containment**

```bash
git add ytk/visual.py ytk/ui/server.py tests/test_visual_disabled.py
git commit -m "fix(visual): stop disabled indexing before model load"
```

### Task 3: Deploy disabled mode and recover the stuck job

**Files:**
- Modify runtime config: `~/.ytk/.env`
- Modify runtime state: `~/.ytk/ingest-job.json`, `~/.ytk/reels_state.json`
- No repository source changes.

**Interfaces:**
- Consumes: `YTK_VISUAL_INDEX=off`
- Produces: a responsive hub with the astronomy memo retained once and no visual collection access.

- [ ] **Step 1: Verify the astronomy note before state mutation**

Use `vault_search` for the exact astronomy sentence and confirm the result is
`memo_2026-07-25-2110-i-should-make-the-next-ytk-visualization-027cd2`.

- [ ] **Step 2: Back up the two runtime state files**

Copy each file to a timestamped explicit path under `~/.ytk/recovery/`; do not modify the Chroma directory in this containment task.

- [ ] **Step 3: Set the global runtime switch**

Run the installed python-dotenv CLI:

```bash
~/.local/share/uv/tools/ytk/bin/dotenv \
  -f ~/.ytk/.env set YTK_VISUAL_INDEX off
```

Verify only the named key:

```bash
~/.local/share/uv/tools/ytk/bin/dotenv \
  -f ~/.ytk/.env get YTK_VISUAL_INDEX
```

Expected: `off`.

- [ ] **Step 4: Remove only the completed astronomy item**

Use the repository's state model for the pending queue and an atomic JSON
rewrite for the persisted job:

```python
import json
import os
from pathlib import Path

from ytk import reels
from ytk.ui import hub

target = "imessage:session:5082ac1a03a844da"
state = reels.load_state(hub.STATE_PATH)
state.pending = [item for item in state.pending if item.url != target]
reels.save_state(state, hub.STATE_PATH)

path = Path.home() / ".ytk" / "ingest-job.json"
data = json.loads(path.read_text())
data["entries"] = [entry for entry in data.get("entries", []) if entry.get("url") != target]
tmp = path.with_suffix(".json.tmp")
tmp.write_text(json.dumps(data, indent=2) + "\n")
os.replace(tmp, path)
```

After the rewrite, load both files and assert the target is absent while their
unrelated entry counts are unchanged.

- [ ] **Step 5: Install and restart**

```bash
uv tool install --reinstall .
launchctl kickstart -k gui/501/com.ytk.hub
```

- [ ] **Step 6: Verify the live service**

```bash
curl --max-time 10 -fsS http://127.0.0.1:6969/api/ready
curl --max-time 10 -fsS http://127.0.0.1:6969/api/ingest/status
curl --max-time 10 -fsS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:6969/
```

Expected: JSON readiness, a non-running ingest status, and HTTP `200`.

### Task 4: Full verification and close-out

**Files:**
- Create through vault MCP: next sequential `second-brain/projects/ytk/session-NNN-brief.md`
- Update through vault MCP: `second-brain/wiki/index.md` and `second-brain/wiki/hot.md` if project state changed.

**Interfaces:**
- Consumes: completed circuit breaker and deployed runtime switch.
- Produces: verified repository and durable recovery documentation.

- [ ] **Step 1: Run repository verification**

```bash
uv run pytest -q
uv run ruff check .
uv run pyright
git diff --check
```

Expected: all tests pass, Ruff and Pyright exit zero, and no whitespace errors.

- [ ] **Step 2: Reproduce the containment boundary out of process**

Run a fresh installed Python process with `YTK_VISUAL_INDEX=off`, patch the raw
collection accessor to abort if reached, and call the public visual operations.
Expected: neutral results and process exit zero.

- [ ] **Step 3: Write the session brief and memory**

Record the damaged `ytk_visual` finding, the incomplete #130 guard, the global
off switch, runtime recovery, verification evidence, and the remaining
single-Chroma-server migration.

- [ ] **Step 4: Commit and push close-out**

```bash
git add docs
git commit -m "docs: record visual index containment"
git push origin master
git status --short
```

Expected: push succeeds and the final status is empty.
