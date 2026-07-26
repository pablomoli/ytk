# CLI Decomposition

`ytk/cli.py` is the Click registration root and currently contains 55 top-level
functions across 3,192 lines. The target is a small registration module that
preserves every public command name, option, exit code, and output contract
while moving command-specific orchestration behind typed functions.

## Command ownership

| Group | Commands | Current service dependencies |
|---|---|---|
| Ingestion | `add`, `feed`, `reels`, `auth`, `sync`, `ingest`, `add-instagram`, `backfill-instagram-reels`, `add-pinterest`, `add-tiktok`, `tiktok-sync`, `reddit-sync`, `reddit-discover`, `add-reddit`, `add-imessage`, `memo`, `autoingest` | `filter`, `metadata`, `transcript`, `enrich`, `vault`, `reels`, `memo`, provider modules |
| Retrieval | `dive`, `search`, `eval`, `similar`, `visual index`, `visual rebuild` | `store`, `relevance`, `visual`, retrieval baseline files |
| Profile | `tags`, `profile`, `recap`, `remember`, `recs-backfill`, `enrich-eval` | `interest`, `synthesis`, `recs`, `enrich_eval`, vault tools |
| Maintenance | `reindex`, `gc`, `index`, `schedule`, `autoingest-schedule` | `store`, `ops`, launchd plist generation, filesystem cleanup |
| Workboard | `work` | Already isolated in `ytk/workboard_cli.py`; root only registers `work_command` |
| Runtime | `chroma`, `ui` | `chroma_runtime`, `chroma_migrate`, launchd, hub server |
| Presentation | `graph`, `dashboard`, `review`, `triage`, `chat`, `snap` | Rich rendering, `graph`, `triage`, browser/app launchers, transcription |

The callbacks for `add`, provider-specific ingestion, `reels`, `memo`, `gc`,
runtime installation, `triage`, and `snap` still contain service orchestration.
Search, profile, and most status commands are already thin adapters.

## Existing witnesses

| Boundary | Existing witness |
|---|---|
| Feed URL collection | `tests/test_feed.py` |
| Instagram dispatch and refresh | `tests/test_add_instagram_cli.py` |
| Reel selection, limits, gallery, rebuild, and errors | `tests/test_reels_cli.py` |
| Instagram backfill | `tests/test_backfill_reels.py` |
| Memo capture and routing exit codes | `tests/test_memo_cli.py` |
| Retrieval evaluation CLI and baseline writes | `tests/test_retrieval_gate.py` |
| Chroma migration and install safety | `tests/test_chroma_migrate.py`, `tests/test_chroma_service.py` |
| Garbage collection and audio pruning | `tests/test_gc_audio_prune.py` |
| Visual rebuild confirmation | `tests/test_visual_rebuild.py` |
| Workboard parity and failure rendering | `tests/test_workboard_interfaces.py` |
| Triage service behavior | `tests/test_triage.py` |
| Snap output encoding | `tests/test_snap_webp.py` |

## Dependency-ordered extraction

1. **Freeze registration.** Add
   `tests/test_cli_registration.py::test_root_help_lists_every_public_command`.
   Invoke `ytk --help` with `CliRunner`, parse command names, and assert the
   complete current set. Add
   `test_nested_help_lists_runtime_and_schedule_subcommands` for `chroma`,
   `ui`, `visual`, `schedule`, and `autoingest-schedule`. No command module
   moves before both tests complete a red-green cycle.
2. **Move pure CLI helpers.** Extract `_fmt_duration`, `_fmt_date`,
   `_collect_feed_urls`, and `_parse_date` to `ytk/cli_format.py`.
   `tests/test_feed.py` protects collection. First add
   `tests/test_cli_helpers.py::test_duration_date_and_natural_date_formatting`
   with representative short, hour-long, ISO, shorthand, and invalid inputs.
3. **Extract ingestion registration.** Create `ytk/cli_ingest.py` with the
   provider command decorators and typed service calls. Preserve the root
   `add` dispatcher. Existing provider and reel tests protect behavior; first
   add
   `tests/test_ingest_dispatch.py::test_add_dispatches_every_supported_url_once`,
   asserting each URL family invokes exactly one provider callback with the
   original note and force flags.
4. **Extract memo and auto-ingest commands.** Move only Click parsing and
   rendering; keep `ytk.memo` and `ytk.autoingest` as services.
   `tests/test_memo_cli.py`, `tests/test_autoingest_select.py`, and
   `tests/test_autoingest_score.py` are the witnesses. Add
   `tests/test_autoingest_cli.py::test_autoingest_dry_run_never_starts_ingest`
   before moving the callback.
5. **Extract retrieval and profile adapters.** Create `ytk/cli_retrieval.py`
   and `ytk/cli_profile.py`. The retrieval gate protects `eval`; add
   `tests/test_search_cli.py::test_search_and_dive_preserve_result_order_and_urls`
   using mocked store hits, and
   `tests/test_profile_cli.py::test_profile_render_only_never_calls_synthesis`.
6. **Extract maintenance and runtime groups.** Create
   `ytk/cli_maintenance.py` and `ytk/cli_runtime.py`. Existing Chroma and GC
   suites protect those leaves. Add
   `tests/test_ui_cli.py::test_ui_start_restart_status_and_uninstall_forward_exact_runtime_settings`
   with subprocess and readiness seams, plus
   `tests/test_schedule_cli.py::test_schedule_install_and_uninstall_write_only_the_expected_plist`.
7. **Extract presentation commands.** Create `ytk/cli_present.py` for graph,
   dashboard, review, triage, chat, and snap. Existing triage and snap tests
   protect service output. Add
   `tests/test_presentation_cli.py::test_graph_dashboard_review_and_chat_preserve_side_effect_boundaries`
   and assert dry or mocked invocations open only the requested surface.
8. **Reduce the root.** `ytk/cli.py` should contain environment loading, the
   root `click.group`, command registration, and no service imports. Run the
   registration witnesses plus the complete Python suite before deleting any
   compatibility re-export.

Each step is one commit. Command relocation does not authorize output rewrites,
renames, new aliases, or changes to exception handling.
