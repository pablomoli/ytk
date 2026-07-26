# Chroma Server Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move every production ytk process behind one loopback-only Chroma server, preserve all healthy text vectors, rebuild both visual collections, and re-enable visual search.

**Architecture:** A new runtime module selects `HttpClient` when `CHROMA_URL` is configured and retains embedded mode only for isolated tests and the one-time legacy source reader. A launchd-managed `chroma run` process owns `~/.ytk/chroma-server`; a migration module copies six healthy collections through public APIs while excluding both visual names, which are regenerated from source images after cutover.

**Tech Stack:** Python 3.13, ChromaDB 1.5.9, Click, launchd, pytest, Ruff, Pyright

## Global Constraints

- The live Chroma server binds only to `127.0.0.1:8000`.
- The server persists at `~/.ytk/chroma-server`.
- `~/.ytk/chroma` remains untouched as the legacy source and rollback artifact.
- Copy `ytk_memories`, `ytk_memories_v2`, `ytk_segments`, `ytk_segments_v2`, `ytk_videos`, and `ytk_videos_v2`.
- Never open, count, copy, delete, or otherwise access the two legacy visual collections during migration.
- Rebuild `ytk_visual` and `ytk_visual_pending` only from source image files.
- Preserve Qwen3 and SigLIP vector-generation behavior; model serving is out of scope.
- Do not update the retrieval baseline.
- Keep the visual circuit breaker after successful re-enablement.
- Never rebuild `/Applications/ytk.app`; its stable executable owns the Full Disk Access grant.
- Commit and push all repository changes without agent co-authorship.

---

### Task 1: Runtime Configuration and Client Factory

**Files:**
- Create: `ytk/chroma_runtime.py`
- Create: `tests/test_chroma_runtime.py`
- Modify: `ytk/store.py:41-108`
- Modify: `tests/conftest.py:18-180`
- Modify: `.env.example`

**Interfaces:**
- Produces: `ChromaRuntime`, `runtime_config() -> ChromaRuntime`, `create_client(config: ChromaRuntime) -> ClientAPI`, `active_store_info() -> dict`
- Consumes: existing `_CHROMA_PATH` as the embedded-test and legacy-source default

- [ ] **Step 1: Write failing runtime-selection tests**

```python
def test_runtime_defaults_to_embedded(tmp_path):
    cfg = runtime_config({}, default_path=tmp_path / "legacy")
    assert cfg.mode == "embedded"
    assert cfg.legacy_path == tmp_path / "legacy"
    assert cfg.url is None


def test_runtime_selects_loopback_http(tmp_path):
    cfg = runtime_config(
        {
            "CHROMA_URL": "http://127.0.0.1:8000",
            "CHROMA_SERVER_PATH": str(tmp_path / "server"),
        },
        default_path=tmp_path / "legacy",
    )
    assert (cfg.mode, cfg.host, cfg.port, cfg.ssl) == ("http", "127.0.0.1", 8000, False)
    assert cfg.server_path == tmp_path / "server"


@pytest.mark.parametrize(
    "url",
    ["http://0.0.0.0:8000", "http://192.168.1.2:8000", "https://example.com:443"],
)
def test_runtime_rejects_non_loopback_url(url, tmp_path):
    with pytest.raises(ValueError, match="loopback"):
        runtime_config({"CHROMA_URL": url}, default_path=tmp_path / "legacy")
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
uv run pytest tests/test_chroma_runtime.py -q
```

Expected: import failure because `ytk.chroma_runtime` does not exist.

- [ ] **Step 3: Implement immutable runtime parsing and client creation**

Implement:

```python
@dataclass(frozen=True)
class ChromaRuntime:
    mode: Literal["embedded", "http"]
    legacy_path: Path
    server_path: Path
    url: str | None
    host: str
    port: int
    ssl: bool


def runtime_config(
    environ: Mapping[str, str] | None = None,
    *,
    default_path: Path | None = None,
) -> ChromaRuntime:
    source = os.environ if environ is None else environ
    legacy_path = Path(
        source.get("CHROMA_PATH", str(default_path or Path.home() / ".ytk" / "chroma"))
    ).expanduser()
    server_path = Path(
        source.get("CHROMA_SERVER_PATH", str(Path.home() / ".ytk" / "chroma-server"))
    ).expanduser()
    url = source.get("CHROMA_URL", "").strip()
    if not url:
        return ChromaRuntime(
            mode="embedded",
            legacy_path=legacy_path,
            server_path=server_path,
            url=None,
            host="",
            port=0,
            ssl=False,
        )
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("CHROMA_URL must be an HTTP loopback URL")
    if parsed.username or parsed.password or parsed.path not in {"", "/"}:
        raise ValueError("CHROMA_URL must contain only loopback host and port")
    if parsed.query or parsed.fragment or parsed.port is None:
        raise ValueError("CHROMA_URL must contain only loopback host and port")
    return ChromaRuntime(
        mode="http",
        legacy_path=legacy_path,
        server_path=server_path,
        url=url.rstrip("/"),
        host=parsed.hostname,
        port=parsed.port,
        ssl=False,
    )


def create_client(config: ChromaRuntime) -> ClientAPI:
    if config.mode == "http":
        return chromadb.HttpClient(
            host=config.host,
            port=config.port,
            ssl=config.ssl,
        )
    config.legacy_path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(config.legacy_path))
```

Accept only `localhost`, `127.0.0.1`, and `::1` as HTTP hosts. Reject URL
paths, query strings, fragments, credentials, and missing ports.

- [ ] **Step 4: Route the store through the factory**

Keep `_CHROMA_PATH` for compatibility with isolated tests and migration-source
selection. Replace its direct `PersistentClient` construction with:

```python
def _get_client() -> ClientAPI:
    global _client
    if _client is None:
        _client = create_client(runtime_config(default_path=_CHROMA_PATH))
    return _client
```

Add `CHROMA_URL` and `CHROMA_SERVER_PATH` to `.env.example`.

- [ ] **Step 5: Isolate pytest from production server configuration**

Add an autouse fixture before store client setup:

```python
@pytest.fixture(autouse=True)
def _embedded_chroma_only(monkeypatch):
    monkeypatch.delenv("CHROMA_URL", raising=False)
    monkeypatch.delenv("CHROMA_SERVER_PATH", raising=False)
```

This must run before any test creates a store client.

- [ ] **Step 6: Run focused and existing store tests**

Run:

```bash
uv run pytest tests/test_chroma_runtime.py tests/test_store_epochs.py \
  tests/test_store_chunked.py tests/test_store_delete.py -q
```

Expected: all pass without contacting port 8000.

- [ ] **Step 7: Commit**

```bash
git add .env.example ytk/chroma_runtime.py ytk/store.py \
  tests/conftest.py tests/test_chroma_runtime.py
git commit -m "feat: add Chroma runtime client factory"
```

### Task 2: Real HTTP Boundary Test

**Files:**
- Modify: `tests/test_chroma_runtime.py`

**Interfaces:**
- Consumes: `runtime_config`, `create_client`
- Produces: a real-server regression test covering the exact production client boundary

- [ ] **Step 1: Write a real-server integration test**

Start the dependency's `chroma` executable on a free loopback port with a
temporary data directory. Poll `heartbeat()` with a deadline instead of using
a fixed sleep.

```python
def test_http_client_round_trip_with_real_server(tmp_path, free_tcp_port):
    with running_chroma_server(tmp_path / "server", free_tcp_port):
        cfg = runtime_config(
            {
                "CHROMA_URL": f"http://127.0.0.1:{free_tcp_port}",
                "CHROMA_SERVER_PATH": str(tmp_path / "server"),
            },
            default_path=tmp_path / "legacy",
        )
        client = create_client(cfg)
        col = client.create_collection("round_trip", metadata={"hnsw:space": "cosine"})
        col.add(ids=["one"], embeddings=[[1.0, 0.0]], metadatas=[{"kind": "test"}])
        assert col.count() == 1
        assert col.query(query_embeddings=[[1.0, 0.0]], n_results=1)["ids"] == [["one"]]
        client.delete_collection("round_trip")
```

The production mutation caught by this test is constructing an embedded client
or sending an invalid host/port to Chroma.

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
uv run pytest tests/test_chroma_runtime.py::test_http_client_round_trip_with_real_server -q
```

Expected: failure because the server fixture does not exist.

- [ ] **Step 3: Implement the test fixture**

Resolve `Path(sys.executable).with_name("chroma")`, launch:

```text
chroma run --host 127.0.0.1 --port <port> --path <tmp_path>
```

Capture output, enforce a 20-second readiness deadline, and terminate/kill the
exact child in `finally`.

- [ ] **Step 4: Verify GREEN**

Run:

```bash
uv run pytest tests/test_chroma_runtime.py -q
```

Expected: all pass and no Chroma process remains.

- [ ] **Step 5: Commit**

```bash
git add tests/test_chroma_runtime.py
git commit -m "test: exercise the real Chroma HTTP boundary"
```

### Task 3: launchd-Managed Chroma Service

**Files:**
- Modify: `ytk/chroma_runtime.py`
- Create: `tests/test_chroma_service.py`
- Modify: `ytk/cli.py:2685-2820`

**Interfaces:**
- Produces: `chroma_executable() -> Path`, `launchd_plist(config, ytk_bin, log_path) -> str`, `wait_for_chroma(config, timeout_s) -> bool`
- Produces CLI: `ytk chroma serve|install|restart|status|uninstall`

- [ ] **Step 1: Write failing service tests**

```python
def test_launchd_plist_is_loopback_persistent_and_keepalive(tmp_path):
    cfg = runtime_config(
        {
            "CHROMA_URL": "http://127.0.0.1:8000",
            "CHROMA_SERVER_PATH": str(tmp_path / "server"),
        },
        default_path=tmp_path / "legacy",
    )
    plist = plistlib.loads(
        launchd_plist(cfg, Path("/usr/local/bin/ytk"), tmp_path / "chroma.log").encode()
    )
    assert plist["Label"] == "com.ytk.chroma"
    assert plist["KeepAlive"] is True
    assert plist["RunAtLoad"] is True
    assert plist["ProgramArguments"] == ["/usr/local/bin/ytk", "chroma", "serve"]


def test_wait_for_chroma_reports_unreachable_without_fallback(tmp_path):
    cfg = runtime_config(
        {"CHROMA_URL": "http://127.0.0.1:65534"},
        default_path=tmp_path / "legacy",
    )
    assert not wait_for_chroma(cfg, timeout_s=0.05)
    assert not (tmp_path / "legacy").exists()
```

- [ ] **Step 2: Verify RED**

Run:

```bash
uv run pytest tests/test_chroma_service.py -q
```

Expected: missing service functions.

- [ ] **Step 3: Implement service helpers**

Generate the plist with exact resolved paths and log locations. `serve` uses
`os.execv()` to replace itself with:

```text
<venv>/bin/chroma run --host 127.0.0.1 --port 8000 --path ~/.ytk/chroma-server
```

`wait_for_chroma` repeatedly creates an HTTP client and calls `heartbeat()`
until a monotonic deadline. Each failure closes the client before retrying.

- [ ] **Step 4: Add Click lifecycle commands**

Implement:

```text
ytk chroma serve
ytk chroma install
ytk chroma restart
ytk chroma status
ytk chroma uninstall
```

`status` must separately print launchd loaded, TCP/HTTP reachable, and heartbeat
healthy. `install` writes `~/Library/LaunchAgents/com.ytk.chroma.plist` and
uses `bootout`/`bootstrap`.

- [ ] **Step 5: Make hub startup wait for HTTP Chroma**

Before `uvicorn.run()`, if runtime mode is HTTP:

```python
if not wait_for_chroma(cfg, timeout_s=30.0):
    raise click.ClickException(f"Chroma server unavailable at {cfg.url}")
```

Embedded test/dev mode does not wait.

- [ ] **Step 6: Verify GREEN**

Run:

```bash
uv run pytest tests/test_chroma_service.py tests/test_chroma_runtime.py \
  tests/test_hub.py -q
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add ytk/chroma_runtime.py ytk/cli.py \
  tests/test_chroma_service.py tests/test_chroma_runtime.py
git commit -m "feat: manage the local Chroma server"
```

### Task 4: Safe Collection Migration

**Files:**
- Create: `ytk/chroma_migrate.py`
- Create: `tests/test_chroma_migrate.py`
- Modify: `ytk/cli.py`

**Interfaces:**
- Produces: `copy_collections(source, target, *, resume=False, batch_size=256) -> MigrationReport`
- Produces: `write_report(report, recovery_dir) -> Path`
- Produces CLI: `ytk chroma migrate [--resume] [--batch-size N]`

- [ ] **Step 1: Write failing copy tests with real Chroma clients**

Create an embedded source with one healthy collection and both forbidden visual
collections. Use an ephemeral target.

```python
def test_copy_preserves_vectors_and_never_opens_visual_collections(tmp_path):
    source = chromadb.PersistentClient(path=str(tmp_path / "source"))
    source.create_collection("ytk_memories_v2", metadata={"hnsw:space": "cosine"}).add(
        ids=["a", "b"],
        documents=["alpha", "beta"],
        embeddings=[[1.0, 0.0], [0.0, 1.0]],
        metadatas=[{"source": "one"}, {"source": "two"}],
    )
    source.create_collection("ytk_visual")
    source.create_collection("ytk_visual_pending")
    target = chromadb.EphemeralClient()

    report = copy_collections(source, target, batch_size=1)

    assert report.collections == {"ytk_memories_v2": 2}
    assert {c.name for c in target.list_collections()} == {"ytk_memories_v2"}
    got = target.get_collection("ytk_memories_v2").get(
        include=["documents", "metadatas", "embeddings"]
    )
    assert got["ids"] == ["a", "b"]
    assert got["documents"] == ["alpha", "beta"]
    assert got["metadatas"] == [{"source": "one"}, {"source": "two"}]
```

Also test that a non-empty target fails without `resume`, and that two resumed
runs produce the same IDs and counts.

- [ ] **Step 2: Verify RED**

Run:

```bash
uv run pytest tests/test_chroma_migrate.py -q
```

Expected: import failure because the migration module does not exist.

- [ ] **Step 3: Implement typed migration records**

Use:

```python
EXCLUDED_COLLECTIONS = frozenset({"ytk_visual", "ytk_visual_pending"})

@dataclass
class MigrationReport:
    started_at: str
    completed_at: str
    source_path: str
    target_url: str
    collections: dict[str, int]
    excluded: list[str]
    complete: bool
```

Filter `source.list_collections()` by `collection.name` before any count/get
call. Copy with `include=["documents", "metadatas", "embeddings"]`, `limit`,
and `offset`. Upsert original IDs and compare source/target counts.

- [ ] **Step 4: Implement atomic reporting and CLI**

Write JSON to a sibling temporary file under `~/.ytk/recovery/`, then
`os.replace()`. The CLI constructs the source explicitly from `CHROMA_PATH`
and target explicitly from `CHROMA_URL`; it refuses when visual indexing is
enabled or when legacy and server paths resolve equal.

- [ ] **Step 5: Verify GREEN**

Run:

```bash
uv run pytest tests/test_chroma_migrate.py tests/test_chroma_runtime.py -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add ytk/chroma_migrate.py ytk/cli.py tests/test_chroma_migrate.py
git commit -m "feat: migrate healthy collections to Chroma server"
```

### Task 5: Remove Production Embedded-Client Bypasses

**Files:**
- Modify: `scripts/build_map.py:27-42,138,519`
- Modify: `scripts/dedupe_chroma.py:39-52`
- Modify: `ytk/ui/server.py:768-787`
- Modify: `tests/test_chroma_runtime.py`
- Modify: `tests/test_settings.py:92-101`

**Interfaces:**
- Consumes: `ytk.store._get_client()` and `active_store_info()`
- Produces: server-backed map, dedupe, and settings consumers

- [ ] **Step 1: Write failing consumer tests**

Add a settings test expecting:

```python
assert environment["chroma"]["mode"] == "http"
assert environment["chroma"]["url"] == "http://127.0.0.1:8000"
assert environment["chroma"]["server_path"].endswith(".ytk/chroma-server")
```

Add a runtime test that two calls return the same cached HTTP client and that
closing/resetting does not create the legacy directory.

- [ ] **Step 2: Verify RED**

Run the exact new tests and confirm missing `chroma` diagnostics.

- [ ] **Step 3: Route scripts and settings through store**

Replace direct `chromadb.PersistentClient` construction in both scripts with
the store client. Remove obsolete `CHROMA` constants/imports. Change settings
metadata from a single `chroma_path` string to `active_store_info()`.

- [ ] **Step 4: Verify all direct-client call sites**

Run:

```bash
rg -n "PersistentClient" ytk scripts
```

Expected: only the explicit legacy source constructor in
`ytk/chroma_migrate.py` and the embedded branch in `ytk/chroma_runtime.py`.

- [ ] **Step 5: Run focused tests**

Run:

```bash
uv run pytest tests/test_chroma_runtime.py tests/test_settings.py \
  tests/test_graph.py tests/test_retrieval_gate.py -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add scripts/build_map.py scripts/dedupe_chroma.py ytk/ui/server.py \
  tests/test_chroma_runtime.py tests/test_settings.py
git commit -m "refactor: route Chroma consumers through server client"
```

### Task 6: Fresh Visual Rebuild Command

**Files:**
- Modify: `ytk/store.py`
- Modify: `ytk/visual.py`
- Modify: `ytk/cli.py:2845-2870`
- Create: `tests/test_visual_rebuild.py`

**Interfaces:**
- Produces: `reset_visual_collections() -> None`
- Produces: `rebuild_visual_indexes(progress=None) -> tuple[int, int]`
- Produces CLI: `ytk visual rebuild --yes`

- [ ] **Step 1: Write failing rebuild tests**

Using a temporary healthy embedded client, pre-populate both visual
collections with sentinel IDs. Stub source discovery and `embed_images`.

```python
def test_rebuild_replaces_both_visual_collections_from_sources(tmp_path, monkeypatch):
    saved, pending = visual.rebuild_visual_indexes()
    assert (saved, pending) == (1, 1)
    assert store.visual_ids() == {"ig:new"}
    assert store.pending_visual_ids() == {"https://new/"}
```

Assert that legacy sentinel IDs disappear and that source embeddings/metadata
are present.

- [ ] **Step 2: Verify RED**

Run:

```bash
uv run pytest tests/test_visual_rebuild.py -q
```

Expected: missing rebuild API.

- [ ] **Step 3: Implement server-only visual reset**

`reset_visual_collections()` refuses embedded mode, deletes only the two
collections by exact name, clears `_VISUAL_PROBE`, then recreates through the
guarded accessors. It never receives arbitrary names.

- [ ] **Step 4: Implement rebuild orchestration and CLI confirmation**

`rebuild_visual_indexes()` runs saved cover indexing with
`skip_existing=False`, then pending synchronization. `ytk visual rebuild`
requires `--yes`, refuses when `YTK_VISUAL_INDEX=off`, and prints both verified
counts.

- [ ] **Step 5: Verify GREEN**

Run:

```bash
uv run pytest tests/test_visual_rebuild.py tests/test_visual_disabled.py \
  tests/test_visual_pending.py tests/test_visual_text.py -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add ytk/store.py ytk/visual.py ytk/cli.py tests/test_visual_rebuild.py
git commit -m "feat: rebuild visual indexes from source covers"
```

### Task 7: Repository Verification and Merge

**Files:**
- Modify only files needed to fix verification failures caused by this migration

- [ ] **Step 1: Run formatting, linting, and types**

```bash
uv run --extra dev ruff format ytk scripts tests
uv run --extra dev ruff check ytk scripts tests
uv run pyright
```

- [ ] **Step 2: Run the full Python suite**

```bash
uv run pytest -q
```

- [ ] **Step 3: Run the retrieval gate**

```bash
uv run ytk eval
```

The baseline must not be updated. Expected hit@5 and hit@10 are no worse than
the frozen v2 baseline.

- [ ] **Step 4: Review the complete branch diff**

```bash
wt step diff
git diff master...HEAD --check
```

- [ ] **Step 5: Push and integrate**

Push the branch, then use the finishing workflow to integrate it into
`master`. Preserve coherent commits; do not squash away the TDD task history
unless the user explicitly requests it.

### Task 8: Offline Migration and Live Cutover

**Files:**
- Modify runtime files only: `~/.ytk/.env`, launchd plists, recovery backups
- Create: next `docs/session-NNN-brief.md`

**Interfaces:**
- Consumes: installed `ytk chroma` lifecycle and migration commands
- Produces: live server-backed text and visual search

- [ ] **Step 1: Re-verify live idle state**

```bash
curl --max-time 10 -fsS http://127.0.0.1:6969/api/ingest/status
```

Require `running=false` and an empty queue before stopping the hub.

- [ ] **Step 2: Back up runtime configuration and state**

Copy explicit files to timestamped names under `~/.ytk/recovery/`:

- `~/.ytk/.env`
- `~/Library/LaunchAgents/com.ytk.hub.plist`
- `~/.ytk/ingest-job.json`
- `~/.ytk/reels_state.json`

Do not copy, move, delete, or edit `~/.ytk/chroma`.

- [ ] **Step 3: Install the merged code**

```bash
uv tool install --reinstall .
```

- [ ] **Step 4: Configure and start the fresh server**

Set:

```dotenv
CHROMA_SERVER_PATH=~/.ytk/chroma-server
```

Keep `CHROMA_URL` unset until copy verification finishes. Install and start:

```bash
ytk chroma install
ytk chroma status
```

- [ ] **Step 5: Stop legacy writers**

Boot out `com.ytk.hub` and terminate only exact pre-cutover `ytk-mcp`
processes after resolving their PIDs. Verify no process holds
`~/.ytk/chroma/chroma.sqlite3`.

- [ ] **Step 6: Copy all healthy collections**

Run the migration with the target URL supplied only to that process:

```bash
CHROMA_URL=http://127.0.0.1:8000 ytk chroma migrate
```

Require exact target counts:

```text
ytk_memories        6799
ytk_memories_v2     4531
ytk_segments        2996
ytk_segments_v2     5656
ytk_videos           315
ytk_videos_v2        200
```

- [ ] **Step 7: Cut clients over and verify text**

Set `CHROMA_URL=http://127.0.0.1:8000` in `~/.ytk/.env`, keep
`YTK_VISUAL_INDEX=off`, then bootstrap/restart the hub. Verify:

```bash
curl --max-time 10 -fsS http://127.0.0.1:6969/api/ready
ytk search "chroma server migration"
uv run ytk eval
```

- [ ] **Step 8: Rebuild both visual collections**

Set `YTK_VISUAL_INDEX=on`, start a new process, and run:

```bash
ytk visual rebuild --yes
```

If this fails, immediately restore `YTK_VISUAL_INDEX=off`, restart the hub, and
leave text search live.

- [ ] **Step 9: Verify visual and concurrent operation**

Verify:

```bash
ytk similar --text "astronomy and real star clusters" -n 5
curl --max-time 10 -fsS http://127.0.0.1:6969/api/ready
curl --max-time 10 -fsS http://127.0.0.1:6969/api/ingest/status
```

Start multiple short-lived ytk client processes and confirm only the Chroma
server owns files under `~/.ytk/chroma-server`.

- [ ] **Step 10: Record and push close-out**

Write the session brief to the vault and repo, update the hot note and vault
index, call `vault_remember`, comment on issue #130 with verified counts and
live results, then commit and push the repository brief. Leave the legacy
directory intact.
