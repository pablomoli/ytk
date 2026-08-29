---
date: 2026-08-29
type: research
project: ytk
status: input to the ingestion-redesign spec; critic says not yet decisive
generator: workflow wf_5861784b-2a5 (13 agents: 3 vault readers, 4 web scouts, 4 link verifiers, synthesis, critic)
stats: 50 vault findings; 92 web findings, 73 kept after link verification, 19 dropped; 43 web searches
---

# The LOOP: what shape should it have?

Research note for the ytk curator agent. Six questions: wake, carry, ask, stop, grade, watch.

## 1. What the corpus already knew

The vault holds four sources that speak to loops directly and five project memories that already answer parts of the six questions with measurements.

**Wake.** [[Self-grading loops beat one-off prompts, per Karpathy]] models wake as schedule-only: "the automation is the heartbeat that fired the loop on a schedule." Nothing in the reel wakes on an event or a human. [[Ex-NASA dev reveals his Agentic Engineering Workflow]] disagrees: vertical slices exist so the human can "re-steer it now when it's cheap," so the tick lands on a structural checkpoint, not clock time. [[Filed ytk issue #150: benchmark-then-trial ladder companion to #149]] records that the owner already committed one loop-class job (D2 oneiric dreaming) to a weekly timer. [[State of Agentic Coding #5 with Armin and Ben]] adds that agent context and human attention degrade together over a day (mornings work, afternoons collapse), so cadence should be sized to the human's review capacity, which Horthy names as the true bottleneck via Theory of Constraints.

**Carry.** The reel carries three files: an editable work file, an untouchable grader, a goals/rules markdown. Horthy moves context out of prompts into files on disk plus session-start hooks, "so inference is spent on reasoning." [[The #149 experiment arc closed its runnable rungs]] measured that wholesale context injection costs more than nothing (2,279 vs 1,012 tokens) and that a ~300-400 token distilled brief is the supported shape. [[Session follow-up ran the 139->149->148 sequence]] is the nearest built sibling: the #148 state machine (captured -> submitted -> enriched -> filed, terminal skipped) in a sidecar ledger at `~/.ytk/batch_ledger.json`, with chroma/memory/idle guards and a morning report, built and deliberately held undeployed. [[Rung 0 of the memory-field experiments (#150) shipped]] shows provenance changes what "normal" looks like (organic notes 10.2 near-dup pairs per 100, imported claude-mem summaries 362), so the ledger needs a provenance field. [[Issue #13 research -- bounded growth for the second brain]] audited claude-mem's unbounded growth (7.8 GB, a decay column designed and never implemented) and found a field consensus that nobody deletes; they summarize, invalidate, or down-rank.

**Ask.** The reel never asks a human. [[Thariq (Claude Code) @ Anthropic]] shows the ask's shape evolving: one question, then a 30-40 question interview, then an HTML report the human answers from; he also says the surface format itself gates capability. Horthy front-loads asks into a context-light design session and mechanizes "which choices did you make that you're not confident of?" before the run. Armin and Ben warn the model will not escalate on its own ("no back pressure"; it flatters at the end of the window) and cannot say "this state shouldn't exist." #148 chose "bounded retries then park," which is a third option between proceed and ask. Issue #13 hard-codes a bright line (any retrieval hit or classify() >= 2 is untouchable; rollups never touch "## My take"), reserving asks for judgment calls.

**Stop.** The reel stops when the grader passes; neither it nor Thariq mention a budget, stuck detector, or kill switch. Horthy's "dumb zone" (~100k tokens, compact to a handoff doc, restart) is a measurable reset rule, and his light-software-factory failure shows debt accumulates silently with no stuck signal. Armin installed a midnight hard-stop skill because nothing else caught him.

**Grade.** The reel's whole thesis is self-grading with the grader walled off. Horthy and Armin/Ben both say the same model class cannot grade its own quality where there is no fast oracle; Horthy prefers "back pressure" (a deterministic outcome number) and cites Cognition's run-the-tests-against-pre-patch trick. Ben's cheap proxy: grep PR titles for "refactor." The owner's own standard, from #150 D2, is residue survival (did the output land in ideas.md or an issue within 30 days), and #13 sequences measurement before any threshold ("every later threshold gets picked from this output, not guessed"). The E5 baseline autopsy (139 "silent partials" were pytest pollution; real baseline 17 captures, 0 losses) is a warning that the instrument itself must be audited first.

**Watch.** Thin inside. Horthy's Riptide syncs file edits to notifications and pulls comments back in. E3 audited 429 MCP calls from session JSONLs as the observability method. Ben's rule: nobody may say "Claude did this."

Where inside disagrees with itself: the reel's autonomous five-piece machine versus Thariq's "it's not just loops, the bottleneck is human unknown-unknowns" and Horthy's "stop playing with your coding agents."

## 2. What the field does in 2026

**Q1 wake.** Claude Code's /loop wakes three ways: fixed interval, a self-chosen delay of one minute to one hour, or a Monitor stream with no polling ([Run prompts on a schedule](https://code.claude.com/docs/en/scheduled-tasks)). Its three hosting tiers trade off hard: session /loop needs an open session, Desktop tasks need the machine on, cloud Routines have no local file access ([same](https://code.claude.com/docs/en/scheduled-tasks)). OpenClaw layers a 30-minute heartbeat under a live-message daemon ([OpenClaw guide](https://petronellatech.com/blog/openclaw-ai-agent-guide/)). Letta sleeptime agents run during idle at configurable frequency with token budget as the de facto stop ([Letta](https://www.letta.com/blog/sleep-time-compute)). Anthropic recommends pausing "at checkpoints or when encountering blockers," not on a cadence ([Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents)). A weekly `/obsidian-learn` sweep classifies findings Active/Stale/Superseded/Promotable ([theaioperator](https://theaioperator.io/p/your-notes-are-a-graveyard-heres)); an HN commenter runs a random-note review with a `#noreview` opt-out ([HN 44402470](https://news.ycombinator.com/item?id=44402470)).

**Q2 carry.** Anthropic's harness persists a JSON feature list with pass/fail, a progress file, and descriptive commits, and does a full context reset from a handoff file when compaction is not enough ([Effective harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)); NOTES.md-style structured notes are the lighter tier, with tool-result clearing the safest compaction ([Context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)). 12-factor-agents unifies execution state and history into one serializable thread ([factor 5](https://github.com/humanlayer/12-factor-agents/blob/main/content/factor-05-unify-execution-state.md)) and caps an agent at 3-10, at most 20, steps ([HumanLayer](https://www.humanlayer.dev/blog/12-factor-agents)). Approved lessons load into future sessions as standing rules ([theaioperator](https://theaioperator.io/p/your-notes-are-a-graveyard-heres)). This agrees with the inside E6 result: small distilled state, not raw dumps.

**Q3 ask.** Per-action approval fails: users approve 93% and attend less each time; auto mode cut prompts 84% while missing 17% of risky actions; the gate must be structural, "not negotiated by the model" ([How we contain Claude](https://www.anthropic.com/engineering/how-we-contain-claude)). Experienced users auto-approve twice as often but interrupt more ([same](https://www.anthropic.com/engineering/how-we-contain-claude)). A separate Intent Agent that monitors for missing information lifted resolution from 44% to 66% on queried tasks ([Ask or Assume](https://arxiv.org/html/2603.26233v1)). OpenAI models the ask as a typed interruption with serialized resume state ([OpenAI Agents SDK](https://openai.github.io/openai-agents-python/human_in_the_loop/)); durable-execution frameworks suspend at zero compute with a bounded timeout ([Inngest](https://www.inngest.com/blog/durable-execution-key-to-harnessing-ai-agents)); 12-factor flags that most orchestrators cannot pause between tool selection and execution, exactly where approval sits ([factor 6](https://github.com/humanlayer/12-factor-agents/blob/main/content/factor-06-launch-pause-resume.md)). Karpathy's slider: move toward closed-loop only as the verifier strengthens ([Loop Engineering](https://www.aibuilderclub.com/blog/loop-engineering-karpathy)). The ask's shape in second-brain practice is a structured proposal (destination plus tags) the human accepts ([MindStudio](https://www.mindstudio.ai/blog/build-ai-second-brain-claude-code-obsidian)). This disagrees with Horthy's front-loaded ask only in placement; both reject asking on every step.

**Q4 stop.** /loop stops on `ScheduleWakeup stop:true`, with a 20-minute fallback wakeup and a hard seven-day expiry ([scheduled tasks](https://code.claude.com/docs/en/scheduled-tasks)). Ralph Wiggum's own reference run needed a "janky" 100-iteration cap and manual termination ([dwmkerr](https://dwmkerr.com/ralph-wiggum-loop/)). Frameworks ship iteration limits off by default; failure modes are repeated identical calls, circular reasoning, ambiguous termination, goal drift ([When Agents Do Not Stop](https://arxiv.org/pdf/2607.01641)). A circuit breaker trips on no-progress steps, spend cap, error-rate spike, or anomalous tool pattern, must live outside the agent's process, and must fail to an inert state; a kill switch is the human's deliberate halt ([opsagent](https://opsagent.pl/blog/agent-kill-switch)). Models facing shutdown have acted to prevent it ([Agentic misalignment](https://www.anthropic.com/research/agentic-misalignment)). Outside directly contradicts the reel's "stops when the grader passes."

**Q5 grade.** Unit-test-only self-verification produced premature "done"; the harness demands end-to-end checks and forbids editing tests ([Effective harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)). Production evals layer deterministic checks, an LLM judge, and human calibration, routing low-confidence scores to a human queue ([Arize](https://arize.com/blog/how-to-build-llm-as-a-judge-evaluators-that-hold-up-in-production/)). The evaluator-optimizer pattern only pays off with clear criteria ([Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents)). Remove the human only after the automated check has caught real failures "a dozen times without a miss" ([Loop Engineering](https://www.aibuilderclub.com/blog/loop-engineering-karpathy)). A 60% single-run success became 25% over eight runs ([Fiddler](https://www.fiddler.ai/blog/ai-agent-failure-rate)). Graphiti sidesteps grading by invalidating rather than deleting ([Graphiti](https://github.com/getzep/graphiti)).

**Q6 watch.** Thinnest area, inside and out. A poisoned tool return leaves a log indistinguishable from a legitimate call, so action-only logs are insufficient ([How we contain Claude](https://www.anthropic.com/engineering/how-we-contain-claude)). The MindStudio workflow uses one session log for both continuity and human review ([MindStudio](https://www.mindstudio.ai/blog/build-ai-second-brain-claude-code-obsidian)). mem0's dashboard is watch-after, not gate-before ([mem0](https://github.com/mem0ai/mem0)).

## 3. What the competitors do

| Product | Entry gated? | Human annotates at capture? | Store | Human reads notes? | Loop over corpus? |
|---|---|---|---|---|---|
| [claude-mem](https://github.com/thedotmack/claude-mem) | No (5 hooks) | No | SQLite + Chroma | No | No (recency-only injection) |
| [mem0](https://github.com/mem0ai/mem0) | Explicit add call | No | vector + dashboard | Rarely | No (add-only, never revisits) |
| [Letta](https://docs.letta.com/guides/agents/memory) | Agent self-edits | No | memory blocks | No | Yes, sleeptime at idle, budget-bounded |
| [Graphiti/Zep](https://github.com/getzep/graphiti) | No | No | temporal graph | No | Continuous ingest; invalidates, never deletes |
| [Khoj](https://github.com/khoj-ai/khoj) | Manual upload | No | local index | Yes | Scheduled automations (newsletters) |
| [Karakeep](https://github.com/karakeep-app/karakeep) | Yes, multi-channel | Optional | Drizzle ORM + Meilisearch | Yes | No; auto-enrich at save, review unspecified |
| [Readwise Reader](https://readwise.io/read) | Yes | During reading | hosted | Yes | Daily Review resurfacing only |
| [mymind](https://www.mymind.com) | Yes | No | hosted (undocumented) | Yes, visually | No; save-time only |
| [Smart Connections](https://github.com/brianpetro/obsidian-smart-connections) | Human only | Yes | local .smart-env | Yes | None; on-demand |
| [Reor](https://github.com/reorproject/reor) | Human writes | Yes | markdown + LanceDB | Yes | Background auto-link only |
| [Fabric](https://github.com/danielmiessler/fabric) | Per invocation | Yes | none | Yes | None |
| [Open Notebook](https://github.com/lfnovo/open-notebook) | Yes | Optional | SurrealDB | Yes | None; user-triggered transforms |
| [Recall](https://www.recall.it/) | Yes | No | hosted | Via chat | Spaced-repetition quizzes (human is oracle) |
| [second-brain-agent](https://github.com/flepied/second-brain-agent) | No (inotify) | Human writes md | ChromaDB | Yes | Re-index only, no generation |
| [Claude-Obsidian](https://aitoolly.com/ai-news/article/2026-08-27-claude-obsidian-a-new-self-organizing-ai-second-brain-for-personal-knowledge-management) | No | No | markdown graph | Unclear | Files and links autonomously, no ask step |
| [NicholasSpisak/second-brain](https://github.com/NicholasSpisak/second-brain) | Human command | Discusses takeaways first | markdown wiki | Yes | Human-woken only |

No competitor combines a self-running loop over the corpus with a structural ask-the-human gate. ytk's LOOP would be the first surveyed design in that cell.

## 4. What people regret and what they changed

Westenberg deleted a 10,000-note vault: "I didn't revisit ideas. I didn't interrogate them. I filed them away and trusted the structure" ([HN 44402470](https://news.ycombinator.com/item?id=44402470)). Commenters split real second brains (write-only engineering logs) from aspirational collections, and only the latter rots ([same](https://news.ycombinator.com/item?id=44402470)); one archives old notes by date instead of deleting or grooming; another names the organizing-cost trap where people relaunch fresh systems rather than pay down a backlog. A separate thread's metric for a working PKM is downstream output, never tidiness ([HN 34036498](https://news.ycombinator.com/item?id=34036498)). The ssp.sh author forbids AI auto-tagging and auto-linking because "relations and connections won't count for anything, since they aren't made by you," allows only marked, quote-blocked 1-2 sentence intros, and reports that generated bulk degrades search until you stop maintaining the vault ([ssp.sh](https://www.ssp.sh/brain/using-obsidian-with-ai/)). This is the sharpest disagreement with the owner's premise that he does not read the notes: the community regret is about vaults the human reads. Where the notes are for search, the ssp.sh search-noise finding still applies, and the retrieval eval gate (#85) is the instrument that catches it.

## 5. Three LOOP shapes for ytk

**Shape A: Heartbeat curator.** A launchd daemon under the hub ticks every 30 minutes, pulls the next N ledger items, advances what it can, queues asks to the voice outbox. Model: OpenClaw, Letta sleeptime, the reel, and the already-built #148.

**Shape B: Event-advanced with an idle sweep.** Each item is advanced by the event that changed it: capture wakes `read`, a human answer wakes `answered -> enriched`, a hub idle period wakes one bounded sweep for parked and stale items. No standing timer except the sweep guard.

**Shape C: Session-bound curator.** No daemon. The loop runs only inside a human-opened session (`ytk curate` or the hub chat), interviews the human on the backlog, and stops when the session ends. Model: NicholasSpisak, Smart Connections, Thariq's interview pattern.

| Question | A: Heartbeat | B: Event + sweep | C: Session-bound |
|---|---|---|---|
| Wake | Timer; must also honor idle/memory guards from #148 | Capture, answer, idle sweep; matches Anthropic's checkpoint/blocker rule | Human only |
| Carry | Sidecar ledger; tick has no memory of prior tick except ledger | Ledger + per-item resume state (typed interrupt) + 300-token standing brief | Session context; ledger for handoff |
| Ask | Batched per tick into outbox; risk of approval fatigue at 30-minute cadence | Asks accrue in outbox, delivered as one digest when the human next appears; timeout -> park | Live, interview-shaped; strongest but only when the human is present |
| Stop | Per-tick item cap plus TTL; needs external breaker | Per-item tick cap, per-sweep budget, external breaker; suspended items cost nothing | Session end; nothing runs unattended |
| Grade | Deterministic checks only; no oracle between ticks | Deterministic + residue survival + retrieval hits; human answers calibrate | Human is the oracle every time |
| Watch | Morning report + ledger | Outbox digest + ledger + reasoning trail per transition | The session itself |
| Laptop cost | Burns subscription windows while idle; wakes disk and Chroma; 16 GB contention with parallel sessions | Near-zero when idle; sweep sized by idle guard; subscription spent only on real transitions | Zero unattended; the loop never advances anything the human did not sit for |

The subscription is the hidden constraint: there is no per-token spend cap to trip (the Agent SDK bills the plan, per the vault's enrichment-rides-subscription note), so the only "budget" signal available to a breaker is tick count and rate-limit errors. Shape A spends that plan window on timer ticks that mostly find nothing to do.

## 6. Recommendation: Shape B

Choose the event-advanced loop with a guarded idle sweep. It is the only shape that satisfies the first law without approval fatigue: asks are structural (the state machine cannot pass `asking` without an `answered` record), batched (one digest per human appearance), and bounded (timeout parks the item). It is also the cheapest on this laptop and the closest to what the corpus already built and measured.

**Ledger.** Keep the eight states, add two: `parked` (bounded retries exhausted, or ask timed out) distinct from `asking`, and treat `dropped` as down-ranked plus archived, never deleted, per #13 and Graphiti. Add `provenance`, `tick_count`, `ask_count`, `resume_state` (the serialized interrupt), and `captured:` as frontmatter per #148. Transitions to `connected` and `kept|dropped` require a human answer until the grader graduates; enrichment does not. The bright lines from #13 (retrieval hit, classify() >= 2, "## My take") are code, never asks.

**Verbs.** `capture`, `annotate`, `journal`, `brain dump` are events that wake the loop. `connect` proposes and asks; it writes provenance-marked links only after `answered`, per ssp.sh. `tell-me-about`, `teach`, `speak` are human-woken reads and do not touch the loop. `ask` is the loop's own verb: a structured proposal (target state, evidence, one-line rationale, accept/reject/edit) rather than an open question, per MindStudio and Thariq's report stage.

**Voice.** The outbox is a queue of typed interrupts with resume state, rendered as a digest by whatever surface is open (hub, memo, morning report). Deliver one digest per human appearance, not one per item. The inbox answer is the event that resumes the item. An unanswered ask parks after a window measured from the owner's actual answer latency, not guessed.

**Stop and watch.** Per-item tick cap and per-sweep budget inside the loop; a separate launchd watchdog that reads a kill file and rate-limit error counts, outside the loop's process, dropping it to an inert state. Every transition writes a one-line reason to the ledger so the trail is readable after the fact. Grade by residue survival and retrieval hits over pre-registered windows, and run the E5-style instrument audit before trusting a number.

## 7. Open questions

- The actual ask latency of the owner (needed to size the park timeout) is unmeasured.
- Whether a separate "should I ask" pass (the Intent Agent result) beats folding the check into the advance pass for curation, not code, is untested.
- Karpathy's primary LOOPS.md was not fetched; only a secondary blog.
- No source described a voice-rendered, surface-agnostic ask channel; HumanLayer treats channels as Slack/email/SMS. Whether a spoken ask survives the structured-proposal shape is unknown.
- Question 6 remains thin: no source gave a concrete mechanism for watching an in-flight loop beyond logs and a morning report.
- Whether the notes-nobody-reads premise survives the ssp.sh search-noise finding depends on the #85 gate catching enrichment bloat, which has not been tested against LOOP-authored content.
- Reddit and X were unreachable; the community section leans on HN and blogs.


## 8. Critic's verdict (independent pass, unedited)

Not ready to pick a shape. The note surveys breadth well on Q1 (wake) and Q4 (stop) but the Shape B recommendation is under-determined on the four things a builder needs first: the event mechanism (what process observes a capture/answer and fires read/enriched), the ledger's location and concurrency story (parallel Claude sessions, iCloud vault, crash mid-transition), an ask taxonomy for curation (what kinds of unsure exist, which single question is worth asking), and an in-loop grader for the one transition it lets pass unattended (enriched). Q6 is admitted thin and stays thin despite ytk already owning a hub at :6969 with SSE, an inbox with buckets+thoughts, `ytk memo` notify, `capture_log.jsonl`, and loaded launchd jobs (com.ytk.hub, com.ytk.chroma, com.ytk.nightly) that the note never inventories as candidate wake hosts or watch surfaces. The load-bearing "closest to what the corpus already built" claim is inverted: `ytk/batch.py` (#148) is timer-driven launchd scripts with a morning report (Shape A), and it submits via the Batch API with a batch_id, the exact transport the vault's enrichment-rides-subscription note calls a new expense; the note cites both facts and never reconciles them. Requested coverage gaps: Obsidian Copilot, NotebookLM (Open Notebook substituted), Temporal/Restate/Hatchet, HumanLayer factor 7, Ralph's primary sources, Karpathy LOOPS.md. Several numbers are secondary-sourced or misattributed (Fiddler pass^k, Horthy dumb zone, containment-post percentages).

### Gaps

- **Q1: no event mechanism. Shape B says 'capture wakes read, an answer wakes enriched' but never names what observes the event: hub POST handler, file watcher on the vault (second-brain-agent uses inotify), ledger poll, or SDK hook. Also unaddressed: launchd does not fire while the lid is closed, and missed intervals coalesce, so 'idle sweep' on a laptop needs a wake-on-resume rule.**
  Why it matters: Without the mechanism, B's 'near-zero when idle' cost claim cannot be checked; if events route through the always-on hub (com.ytk.hub is loaded) the idle cost is the hub's, not zero. Sleep behavior decides whether the sweep ever runs.
  Where to look: launchd StartInterval vs StartCalendarInterval missed-run coalescing on sleep; watchdog/fsevents on iCloud-synced directories; hub SSE job model in ytk/ui/hub.py (background ingest job already exists)
- **Q1: no ytk numbers. Capture rate (items/day from capture_log.jsonl or batch_ledger.json), answer latency, and hub-open hours are all unmeasured, yet 'Shape A ticks mostly find nothing to do' and 'park timeout sized from actual latency' both depend on them.**
  Why it matters: Cadence and park timeout are the two tunables of B; both are guessed. The note's own #13 rule says measure before threshold.
  Where to look: count states and timestamps in ~/.ytk/batch_ledger.json and capture_log.jsonl; hub access log for session boundaries
- **Q2: where the ledger lives and who else writes it. Single JSON at ~/.ytk (like #148), SQLite, or vault frontmatter? Parallel Claude sessions (a standing hazard in this repo's memory) plus the hub plus the loop all touching one file is not discussed; neither is crash mid-transition (the Temporal replay finding was dropped and nothing verified replaced it) nor idempotent re-delivery of verb events (double capture, second answer to a parked ask). #148 has idempotency; the note does not carry it into the verb design.**
  Why it matters: A ledger is the only thing B carries between ticks; a torn write or a lost transition is a silent state corruption that no grader catches.
  Where to look: SQLite WAL single-writer patterns for daemons; Inngest/Restate step memoization docs; 12-factor factor 5 + 12 (stateless reducer); ytk/batch.py load/save
- **Q2: the 300-400 token brief (E6) measured session context injection, not per-tick loop state. Applying it to 'standing brief' is a transfer, not a result. Also missing: how human answers become standing rules (theaioperator mention) for ytk specifically, i.e. what the loop learns from a hundred accept/reject answers and where that lives.**
  Why it matters: The loop's value compounds only if answers reduce future asks; without a learned-preference store every item asks from scratch.
  Where to look: Letta memory blocks edit policy; mem0 preference extraction; 12-factor factor 3 own your context window
- **Q3: no ask taxonomy for curation. The note never enumerates what the curator can be unsure about (duplicate? which bucket? drop vs keep? connect to which note? enrichment wrong? provenance?). The dropped Anthropic autonomy data gave a reasons-to-ask distribution for coding and the dropped EVPI paper gave a 'which single question' rule; nothing replaced either. The first law ('when unsure, it asks') has no operational definition of unsure.**
  Why it matters: Digest fatigue is a function of ask count per type; you cannot size the digest or decide the Intent-Agent question without the taxonomy.
  Where to look: Anthropic 'measuring agent autonomy' post; openreview EVPI clarifying-question paper; HumanLayer 12-factor factor 7 (contact humans with tool calls) which is the on-point factor and is uncited
- **Q3: the 93%/84%/17% approval-fatigue figures are about per-tool-call permission prompts in coding sessions. Transfer to batched curation proposals is asserted, not shown. Also unaddressed: the 'edit' branch of accept/reject/edit (free-text edit reopens the open-question shape the note rejects), late answers after park, and contradictory answers.**
  Why it matters: The whole digest design rests on fatigue numbers from a different interaction class.
  Where to look: spot-check figures in anthropic.com/engineering/how-we-contain-claude; Readwise Daily Review completion rates; Recall quiz retention as human-oracle cadence data
- **Q4: 'no per-token spend cap to trip' is sourced to a vault memory, not to Agent SDK docs. The SDK exposes max_turns and per-result usage/cost fields even when billing rides the plan, and the plan has 5-hour rate windows; those are usable breaker inputs. Per-item tick cap and per-sweep budget have no numbers. No stuck signal is defined for curation (the dropped '5+ identical commands' finding was the only concrete one), and no goal-drift signal (over-connecting, over-tagging) exists.**
  Why it matters: The breaker is only as good as its inputs; the note designs it with one input (rate-limit errors) while dismissing others that exist.
  Where to look: claude-agent-sdk query options max_turns, ResultMessage.usage/total_cost_usd; claude-api skill; arXiv 2607.01641 termination taxonomy applied to non-code loops
- **Q5: no in-loop oracle. Residue survival is a 30-day lagging metric and #85 is a frozen known-item ranking gate on old docs; neither can gate a transition at tick time. The recommendation lets 'enriched' pass without a human and names no deterministic check for it (schema validity? near-dup rate against the 10.2/100 organic baseline? length ceiling?). 'Until the grader graduates' has no graduation criterion; Karpathy's 'dozen without a miss' is cited but not turned into a rule with a counter.**
  Why it matters: An ungated enriched transition is exactly where ssp.sh's search-noise regret enters, and the note says so without closing it.
  Where to look: near-dup rate from #150 rung 0 as a per-tick guard; Arize deterministic-first eval layering; dropped llm-council self-preference and grader-in-workspace hacking findings need verified replacements
- **Q6: no surface, no revert, no alert. The note proposes 'one-line reason per transition' immediately after citing that action-only logs are insufficient. It ignores that the hub already exists (SSE, /inbox buckets+thoughts, background job status at /api/ingest/status), that `ytk memo` has focus-aware notify, that E3 already audits MCP calls from JSONLs, and that claude-mem has a Telegram alert mode. No undo path: the vault is iCloud, not git, so a bad LOOP transition on a note has no revert unless the ledger stores before/after.**
  Why it matters: Q6 is the question the owner can least afford to leave thin: he does not read the notes, so the watch surface is the only place drift is visible.
  Where to look: ytk/ui/hub.py job status endpoints; Riptide (Horthy) sync model; claude-mem mode-creator Telegram; snapshot-before-write pattern in ytk vault_write
- **Existing ytk surfaces not inventoried against the verbs: hub inbox 'thoughts' already is `annotate`; memo already is `brain dump`/`speak` input; morning report already is a digest; com.ytk.nightly is a loaded timer host. The note designs the voice outbox as if none of these exist.**
  Why it matters: Choosing a shape means choosing which existing daemon hosts it; the note compares three abstract shapes rather than three concrete deployments on this machine.
  Where to look: launchctl list | grep ytk; ytk/cli.py launchd install commands (~line 2592-2790); ytk/ui/hub.py memo POST
- **Requested but not covered: Obsidian Copilot (absent), NotebookLM (Open Notebook substituted without saying so), Temporal/Restate/Hatchet (only Inngest, one sentence), HumanLayer factor 7, Ralph loop primary sources (Huntley, Claude Code ralph plugin) beyond dwmkerr, heartbeat agents beyond OpenClaw, Karpathy LOOPS.md (admitted), Khoj's research agent loop, Readwise Ghostreader. claude-mem row 'No loop' is wrong-ish: it runs an agent worker on hooks that extracts observations (event-driven summarization) and it is installed on this machine.**
  Why it matters: The 'first design in that cell' claim rests on a table with 'unclear'/'unspecified' entries and missing rows.
  Where to look: github.com/logancyang/obsidian-copilot; docs.temporal.io/develop agent samples; humanlayer 12-factor factor-07; ghuntley.com/ralph; claude-mem worker/observer architecture

### Claims the critic marks unsupported or over-reached

- 'Closest to what the corpus already built and measured' for Shape B: ytk/batch.py (#148) is launchd-timer-driven with a morning report, i.e. Shape A, and submits via the Batch API (batch_id), which the vault's enrichment-rides-subscription note calls a new expense; the note cites both and never reconciles.
- 'No competitor combines a self-running loop over the corpus with a structural ask gate; ytk would be the first surveyed design in that cell' — table has Karakeep 'review unspecified', Claude-Obsidian 'unclear', mymind 'undocumented', and omits Obsidian Copilot and NotebookLM; first-in-survey is stated as first-in-field.
- 'No per-token spend cap to trip' — sourced to a vault memory; Agent SDK exposes max_turns and usage/cost on results regardless of billing path; unverified against SDK docs.
- 'Shape A ... timer ticks that mostly find nothing to do' — no capture-rate measurement; asserted.
- Laptop-cost row 'wakes disk and Chroma' — com.ytk.chroma is a loaded launchd server, already running; Shape A does not wake it.
- '60% single-run success became 25% over eight runs' attributed to Fiddler — this is tau-bench pass^k; Fiddler is a secondary retelling.
- Horthy 'dumb zone ~100k tokens' and 'stop playing with your coding agents' — podcast recollection from vault notes, not a primary doc.
- 'The model will not escalate on its own (no back pressure)' (Armin/Ben) is presented as settled, while the dropped Anthropic autonomy measurement shows Claude Code asks 2x more on complex tasks; the disagreement is not surfaced.
- 'Models facing shutdown have acted to prevent it' as support for a kill switch — contrived-scenario research applied to a curation loop; decorative.
- 93% approve / 84% fewer prompts / 17% risky misses — pulled from one post and applied to batched curation proposals; transfer unestablished and figures unverified here.
- 'connect writes provenance-marked links only after answered, per ssp.sh' — ssp.sh forbids AI links entirely; it does not support gated AI links.
- 'Approved lessons load into future sessions as standing rules' — single practitioner blog (theaioperator), generalised.
- 'Park after a window measured from the owner's actual answer latency' — no instrument records answers; capture_log.jsonl logs captures only.
- E6 '300-400 token distilled brief is the supported shape' applied to per-tick loop state — measured for session context injection, not loop carry.
- Karpathy slider and 'dozen without a miss' — secondary blog; primary LOOPS.md unfetched (admitted but still used as a rule).
- claude-mem 'No loop (recency-only injection)' — it runs an event-driven agent worker on hooks; row understates it.

### Dropped by link verification (examples, unverified, do not cite)

- Event-driven agent triggers cut both cost and latency dramatically versus polling: an agent polling 100 endpoints every 30s can blow a 5,000-req/hour budget 2.4x over before any real work happens, whi (https://agentblueprint.substack.com/p/event-driven-vs-polling-architectures)
- Temporal's workflow-activity boundary is explicitly recommended as the mapping for agent loops: workflows hold the deterministic orchestration plan and replay history to recover, while activities are  (https://www.spheron.network/blog/ai-agent-workflow-orchestration-temporal-inngest-restate-gpu-cloud/)
- A documented failure mode of LLM-authored ground truth: when an LLM writes the test assertions for its own eval suite, the assertions tend to encode the current — possibly buggy — implementation as 'e (https://dev.to/virginiamwega2svg/evaluating-agents-with-an-llm-as-judge-harness-without-kidding-yourself-about-it-186k)
- OpenClaw's architecture separates a persistent gateway daemon (routing 50+ messaging platforms into a ReAct loop) from the heartbeat scheduler that fires background checklists, meaning human-triggered (https://arxiv.org/pdf/2603.27517)
- Karpathy's llm-council project found that a model grading its own output systematically rates itself higher than peer models rate the same output, based on 73,580 paired judgments. (https://llmcouncil.ai/karpathy-llm-council)
- In rubric-based and ML-engineering agent evaluation settings, agents learn to hack the scoring pipeline itself -- e.g. via hardcoding expected outputs or exploiting boundary conditions -- rather than  (https://arxiv.org/html/2603.11337)
- Smaller/weaker LLM judges are easily manipulated by agents using deceptive formatting and misleading calculations to trigger false-positive passing grades, while stronger judges like GPT-4o resisted s (https://arxiv.org/html/2603.11337)
- In multi-agent evolutionary or pipeline settings, a single output that hacks the scoring function to get an inflated score can dominate selection and cause degenerate strategies to propagate through t (https://arxiv.org/html/2603.11337)
- Anthropic's own measurement of Claude Code shows the agent scales its rate of stopping to ask for clarification with task complexity, asking more than twice as often on the most complex tasks as on mi (https://www.anthropic.com/news/measuring-agent-autonomy)
- In Anthropic's data, Claude Code's top reasons for stopping to ask were: presenting a choice between approaches (35%), gathering diagnostic info (21%), clarifying a vague/incomplete request (13%), req (https://www.anthropic.com/news/measuring-agent-autonomy)
