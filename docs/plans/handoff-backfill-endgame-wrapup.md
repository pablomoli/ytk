# Handoff: finish the #105 description-backfill endgame

Written 2026-07-24 for a FRESH session started after a machine restart. The
expensive work is done and durable; what remains is the cheap, re-runnable
wrap-up (eval → baseline decision → map/figure rebuild → finalize PR #109).

Restart-safe: everything below reads from durable state (the live Chroma
store on disk, the branch on the remote, snapshots in `~/.ytk`). Nothing
here depends on the process that ran the backfill.

## State at handoff time (verified, not assumed)

- **Re-embed COMPLETE and persisted** to the live store `~/.ytk/chroma`
  (NOT in git — the vectors are on disk). `ytk_videos_v2` = 170, readable
  and consistent.
- **Ledger** `~/.ytk/reenrich-descriptions.json`: `ok 164`, `no-description 4`,
  `no-transcript 1`, `failed 1`. Total 170.
  - The one permanent failure is `r3bkGPobpTw` — the YouTube video was
    deleted (SME copyright block). It keeps its ORIGINAL enrichment and
    vectors. Do not retry it; it is unrecoverable. State it in the PR as
    "1 of 170 retains pre-run enrichment (source deleted)."
- **Branch / PR:** `worktree-agent-a9bd15465dc40bb2a`, draft **PR #109**,
  head `5e79e73`, clean and fully pushed. Do the wrap-up on this branch
  (check it out via `wt switch worktree-agent-a9bd15465dc40bb2a`, or a fresh
  worktree from it).
- **Phase 1 verified earlier:** 165 notes carry `## Description`, 165 store
  records carry `description` metadata, **0 embedded documents contain
  description text** (store-but-never-embed invariant holds).

## Rollback assets (do NOT delete until the baseline decision is made)

- `~/.ytk/chroma.pre-desc-backfill-20260724` — full store snapshot (369M).
  The only rollback path. To roll back: stop any store user, move the live
  `~/.ytk/chroma` aside, restore this copy.
- `~/.ytk/youtube-notes.pre-reenrich-20260724` — 172 note snapshot.
- `~/.ytk/map.pre-105-descriptions.json` — pre-change map payload.
- On the branch: `docs/assets/01-fog/pre-105-descriptions/` — the nine
  pre-change fog PNGs. KEEP THESE regardless — the before/after pair is
  capstone report material.

## Preserved endgame tooling (rescued from /tmp before restart)

`~/.ytk/desc-backfill-tooling/` holds what the backfill agent built:
- `compare_and_stamp.py` — gate comparator; **refuses to re-stamp on
  regression** by design. Read it before trusting it, but it encodes the
  right policy.
- `map_stats.py` — recomputes the numbers quoted in
  `docs/assets/01-fog/README.md` (median strand distance, % within 2h,
  strand/junction counts) from a map payload. Validated to reproduce the
  pre-change numbers.
- `validate_reenrich.py`, `verify_phase1.py` — invariant checks.
- `pr-body.md` — the agent's drafted PR #109 body (Phase 1 results,
  before-numbers, test verdict, #110 conflict note). Start the final PR
  body from this, don't rewrite from scratch.
- `phase2.log`, `phase2-retry.log`, `pytest.log` — run logs for reference.

## The wrap-up, in order

### 1. Sanity-check the store is quiet and consistent
```
curl -s http://localhost:6969/api/ingest/status   # want "running": false
cd /Users/melocoton/Developer/ytk && uv run python -c "import chromadb,os;from ytk.store import epoch_collection_name;print(chromadb.PersistentClient(path=os.path.expanduser('~/.ytk/chroma')).get_collection(epoch_collection_name('ytk_videos')).count())"
```
Expect 170. If the hub shows an ingest running, wait — do not write to the
store concurrently (Chroma PersistentClient is not multi-process safe).

### 2. Run the eval and compare BY HAND
```
uv run ytk eval        # 156 frozen known-item queries
```
**The exit code is unreliable** — the gate fails on `corpus_fingerprint`
drift (corpus grew 114 → 170 since the baseline was stamped), which is a
comparability warning, not a score regression. This is issue **#111**; do
not treat a non-zero exit as a real failure.

Compare the reported hit rates by hand against the "before" run captured
pre-backfill:

| metric | before |
|---|---|
| hit@1 | 0.718 |
| hit@5 | 0.917 |
| hit@10 | 0.949 |
| nDCG@10 | 0.683 |

### 3. The baseline decision
- **Parity or improvement on hit@1** → keep the re-embed, re-stamp:
  `uv run ytk eval --update-baseline`. Note the epoch + date in the commit.
- **hit@1 REGRESSION** → do NOT re-stamp. Roll back to
  `~/.ytk/chroma.pre-desc-backfill-20260724`, report the numbers, and say
  the backfill was reverted. A regression is a more valuable finding than
  the feature.

**Set expectations: FLAT is the expected, acceptable outcome — keep it.**
Two structural reasons, both documented:
- Under the v2 epoch **only `thesis + summary` is embedded** (issue #113);
  concept-level enrichment gains have nowhere to land in the vector space.
- The enrichment prompt drifted since these videos were first ingested, so
  this run cannot isolate the description's contribution (it compares
  "today's prompt + description" vs "each video's ingest-day prompt").
Flat does NOT trigger rollback — only an actual hit@1 regression does.

### 4. If the re-embed is kept: rebuild downstream artifacts
The embedding changed, so the map and figures are stale.
```
cd /Users/melocoton/Developer/ytk
uv run python scripts/build_map.py --sweep                 # refit UMAP, rebuild ~/.ytk/map.json
uv run --with matplotlib python scripts/plot_assets.py --refresh   # all 9 figures
```
Then re-read the prose numbers in `docs/assets/01-fog/README.md`
against `map_stats.py` output and update any that changed (median 0.55h,
98.8% within 2h, 10 strands, 5 junctions were the PRE-change values — do
not copy them forward, re-read them). Keep the pre-change PNGs.

Note per the notes file: #106 (semantic domains) has NOT run — it only
recolours and does not reshape, so it is a separate future pass. This
endgame is the #105 reshape only.

### 5. Finalize PR #109
Start from `~/.ytk/desc-backfill-tooling/pr-body.md`. Add: final ledger
tally (164 ok + 4 no-description + 1 no-transcript + 1 permanent = 170),
the eval before/after numbers, the baseline decision and why, the one
permanent loss, and the #110 merge-conflict note (keep this branch's logic,
take #110's formatting, re-run `ruff format` — do NOT rebase onto #110).
Mark ready for review when done.

## Standing gotchas (each has cost a session)

- **Bash cwd drifts** after `cd web && ...`; a wrong-directory `uv run`
  fails SILENTLY. Prefix every command with `cd /Users/melocoton/Developer/ytk && `.
- **Never chain a hub status check and a restart** with `;`/`&&`. Inspect
  `/api/ingest/status` as its own command, decide, then act.
- **Use `wt`, never raw `git worktree`.** Never force-push, never push to
  master. This is background-session work → isolate in a worktree.
- If deploying anything (not required for this endgame), deploy from a clean
  export: `git archive HEAD | tar -x -C <tmpdir>` then reinstall.

## Related issues (context, not tasks for this endgame)
#105 (this), #106 (semantic domains, next), #108 (dist build hook),
#110 (typing sweep PR — will conflict), #111 (eval gate frozen-corpus fix —
why the exit code lies), #113 (v2 embeds only thesis+summary — why flat is
expected), #114 (browser-in-test-suite hang).
