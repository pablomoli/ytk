HARD CONSTRAINT NOTE: The environment blocked writing REPORT.md (subagents must return findings as text). The full report follows as my return value.

# Enrichment Audit: Is ytk's AI enrichment "lowkey selling us"?

Overnight audit, 2026-07-05/06. Five literature sweeps, four experiments on the real vault (seeded random sample: 30/82 YouTube + 30/91 Instagram notes), every finding adversarially re-verified. All artifacts under `scratchpad/enrichment-audit/` (specificity.json, retrieval_ab.json, faithfulness.json, rewrites.md, refute_hedge.json).

---

## 1. Verdict: No. The enrichment is not selling you. But two real defects were found, and neither is the one you suspected.

### The suspicion, tested three ways

**Selling/hedge language: absent.** (CONFIRMED under adversarial re-check.) Across all 60 sampled summaries, a ~40-term hedge/praise lexicon (amazing, powerful, leverage, delve, robust, very, ...) fired 12 times total. 48/60 summaries have zero hits; the worst note has one word (0.98 per 100 words). Doubling the lexicon with 40 more sell/hedge terms still gives only 0.33/100w, and the extras are functional in context ("notably more accurate than Whisper locally" is a comparison, not praise). Epistemic hedging is 0.08/100w. The apparent worst offenders are false positives: the note with 6x "incredible" is about a tool that builds supercuts of the word "incredible"; "striking" x3 in the Jon Jones note is MMA striking. One real tic survived scrutiny: "The standout X is..." appears in 7/60 sampled summaries (19 vault-wide), plus stock framing verbs ("walks through", "covers"). Mild formula, not selling.

**Specificity: high.** (CONFIRMED for the headline; the YouTube-vs-Instagram gap WEAKENED.) Median 11.1 named specifics per 100 words (tools, commands, numbers, proper nouns); p25 = 7.1, max = 27.3. A deliberately generic fluff baseline written in the same register scores 0.0 on the same counter, so the vault median sits far above genuinely vague prose. The claimed YT > IG gap (12.1 vs 9.0 median) did not survive: Mann-Whitney p = 0.079, permutation p = 0.12 at n=30/30, confounded by topic mix (yoga and art posts carry fewer countable tech tokens) and by a counter case-bias against lowercase Instagram entity names ("oio.studio", "mur mur", Sanskrit pose names). Report it as a weak tendency, not a finding. The "worst notes are degenerate inputs" story also WEAKENED: 4 of the bottom 6 are measurement artifacts of that same case-bias, and a pre-enrichment emptiness filter would catch only 1 of 5 (hot_meh, a five-hashtag zero-slide post) while false-positiving a note you personally annotated as exactly what you wanted.

**Faithfulness: 97.7%.** 176 atomic claims across 12 transcript-bearing notes, judged claim-by-claim against the transcript: 172 SUPPORTED, 4 INFLATED, 0 fabricated. Zero invented intensifiers; "chill down the spine" was literally in the transcript. The 4 defects are precision slips, not hype:

1. Fish self-recognition "on par with a human toddler" (transcript: 20 min matches mirror-naive adults, toddlers are ~10 min).
2. WASM image-optimization war story credited to Scott; Wes tells it (speaker misattribution across a `>>` marker).
3. "Claude directly without OpenCode headers" when the host said he moved to a harness called "PI".
4. "TFIIH phosphorylating Pol II's CTD": textbook-correct biology (CDK7), but the transcript has P-TEFb doing it; the model reached into its own domain knowledge.

Two error signatures: speaker misattribution in multi-host podcasts, and reaching slightly beyond the transcript. Both likely worsened by Whisper transcripts that drop speaker labels.

### The finding that flipped under verification

The first-pass headline was "raw transcript out-retrieves enrichment (recall@1 0.98 vs 0.82); enrichment does not earn its keep as a retriever." **REFUTED.** The gap is a measurement artifact that also exists in production: the enrichment arm crammed each note into ONE document of 800-1200 tokens, and the embedder (gte-small) hard-truncates at 512 tokens, silently cutting the entity-dense tail. The transcript arm got 752 intact chunk vectors. Re-run with enrichment chunked to fit the window: **recall@1 = 1.00, beating transcript's 0.98.** The audit's own combined arm was already at 1.00. Equalize granularity and enrichment wins.

The companion finding ("enrichment's one win was abstractive thesis language") was also REFUTED: the transcript contains "it's new bootstrap" verbatim, and the winning query had been authored while looking at the enrichment text. Circular.

**So the real bug is in `ytk/store.py`, not `ytk/enrich.py`:** every production `video_doc` (771-978 tokens measured) already exceeds gte-small's 512-token window today. The Key Concepts tail, the most retrievable part of the note, is never embedded. This is the single highest-leverage fix in the whole audit, and it costs zero API calls.

A methodological gotcha for future audits, CONFIRMED: YouTube notes have no `## Summary` heading; the summary lives under `## Commentary` (vault.py `_build_note`, lines 153-157). 0/82 YouTube notes have `## Summary`. A naive parser scores every YT summary as empty, and CLAUDE.md's documented note format is stale on this point.

### Bottom line

| Claim | Verdict | Effect size |
|---|---|---|
| Summaries use selling/hedge language | Unfounded | 12 hits / 60 summaries; 48/60 at zero |
| Summaries are generic | Unfounded | median 11.1 specifics/100w vs 0.0 fluff baseline |
| Enrichment hallucinates | Mostly unfounded | 4/176 claims inflated, 0 fabricated (2.3%) |
| Enrichment loses to raw transcript at retrieval | Refuted (truncation artifact) | chunked enrichment: recall@1 1.00 vs 0.98 |
| Long summaries are padded | Qualitatively holds, r=0.28 stat unsound | within-source partial r = 0.20 |
| ~75% of key_concepts name concrete tools | Confirmed, conservative lower bound | 329/435 pooled |

The prompt is doing its job. The pipeline around it leaks: a 512-token embedding cliff, a flat cap of 8 that drops named tools, drifting timestamps, and ASR garbles adopted as real terms.

---

## 2. What the literature says enrichment should be, for episodic recall

The relevant frame is not "summarization quality" but "index construction for a future self who half-remembers." Five transferable results:

1. **Faithfulness is claim-level, and precision alone is gameable.** RAGAS (arXiv:2309.15217) and FActScore (arXiv:2305.14251) score the fraction of atomic claims supported by the source; SAFE (arXiv:2403.18802) adds the F1@K correction: a summary that says less scores higher on pure precision, so faithfulness must be paired with a coverage denominator. QuestEval (arXiv:2103.12693) supplies that recall signal: generate questions from the source, check the summary answers them. ytk's failure mode is exactly the recall side; the cap of 8 dropped `fresh`, `delta`, `difftastic`, Lima, Hermes, and SEVA's lead author from long videos while precision stayed near-perfect.

2. **Importance-weight the claims.** arXiv:2510.07083: unweighted atomic precision over-rewards trivial claims. Verify thesis and key_concepts strictly; tolerate softness in connective prose.

3. **Context-stripped chunks fail vague queries.** Anthropic's Contextual Retrieval: prepending a 50-100 token situating context to each chunk before embedding cut top-20 retrieval failures 35% alone, 67% with BM25 + reranking. ytk's `ytk_segments` are exactly the naked chunks this fixes.

4. **Query-shaped text in the index is powerful (doc2query/HyDE), but must be quality-filtered** (Doc2Query--, arXiv:2301.03266). key_moments are already implicit doc2query expansions; the missing piece is verbatim quotes and normalized entity names as lexical anchors, since episodic queries often carry one rare exact token ("television CLI") that BM25 nails and embeddings blur. ChromaDB is dense-only; a lexical side channel matters.

5. **Granularity beats cleverness.** Dense X Retrieval (arXiv:2312.06648): proposition-level units retrieve better per word budget than passages. This is precisely why the chunked-enrichment arm hit 1.00. Skip ColBERT at vault scale; retrieve top-20 and rerank instead.

If a judge model ever rates enrichments: single-answer rubric grading with the transcript in context, never pairwise (position bias), and beware verbosity bias and self-preference since enricher and judge would both be Claude (arXiv:2306.05685, arXiv:2410.21819).

---

## 3. Before/after: the rewrite trial (5 notes, hand-verified against transcripts)

Headline: **density per 100 words did NOT improve** (old 9.6-12.4, new 10.1-15.2, mostly flat). The production prompt already writes at the honest prose-density ceiling. The rewrites' gains are pure coverage, +73% to +190% absolute named specifics, from a longer budget on long videos:

| video | old summary | new summary |
|---|---|---|
| you-ve-been-using-git-wrong (11 min) | 157w / 15 specifics | 234w / 26 |
| supercuts-in-seconds | 170w / 21 | 299w / 37 |
| phil-daru-mma-boxing | 155w / 16 | 297w / 30 |
| ben-vinegar-tmux (66 min) | 180w / 22 | 423w / 53 |
| judy-fan-cognitive-tools (71 min) | 181w / 22 | 421w / 64 |

**What the cap of 8 dropped (66-min Ben Vinegar episode):** `fresh` (get-fresh.dev, the VS-Code-like terminal editor), `delta`, `difftastic`, Lima, Hermes, and the Kimi-K2.5-suffices point. One of the ten test queries ("that VS Code like text editor Ben mentioned") was unanswerable from the old note for exactly this reason; it was the only real answer-presence gap in 10 queries. 42/60 sampled notes have exactly 8 key concepts: the cap is saturated, i.e. it is truncating, not selecting.

**Timestamp drift, late in long videos:** the supercuts note put ffmpeg internals at 12:30 (actual 11:07), Internet Archive at 13:30 (actual 12:09); Ben Vinegar's public-issue story stamped 30:27, actually 26:31. Early timestamps are accurate; drift grows with position, consistent with estimation rather than anchoring.

**ASR propagation:** "reax" (garbled "regex") adopted as a real term in concepts and insights; "Yael Winkler" for Yael Vinker. Yet "Omari" was correctly normalized to Omarchy, so the model can fix these when nudged.

**A representative pair** (git video, thesis):

> OLD: "Argues that GitHub's recurring workflow oddities exist because Git was designed for distributed Linux-kernel maintenance rather than centralized team collaboration, then demonstrates Git's native patch-and-email workflow before conceding GitHub's centralized model is genuinely better for most teams."

> NEW: "Tom Delalande demonstrates Git's native collaboration stack, a bare repo on a Raspberry Pi, Apache + GitWeb + smart HTTP, git format-patch / git apply patches over a mailing list, to argue GitHub's recurring oddities exist because Git was designed to maintain the Linux kernel, then concedes GitHub's centralized model is 'undeniably better for most people.'"

Same claim; the new one carries six greppable entities and a verbatim quote. That is the whole delta: not less selling, more anchors.

**And the retrieval punchline:** old enrichments already rank 1/30 on all 10 episodic queries. The richer rewrite REGRESSED one query to rank 5 under the production doc composition, because more content pushed more entities past the 512-token cliff. Concepts-first ordering or 3 vectors per video restores 10/10. Richer enrichment actively hurts until store.py is fixed.

---

## 4. Enrichment spec v2 (PROPOSAL, for discussion, not implemented)

A full prompt rewrite is not justified by the evidence. This is a targeted revision plus the indexing fixes the data demands.

### Schema changes

- `key_concepts`: **duration-scaled budget, no flat cap.** "As many as the content warrants; a 60-minute talk may need 15+, a 3-minute reel maybe 3." The 8-cap is the single biggest coverage killer (42/60 notes saturated).
- `key_moments`: same scaling (a 66-min podcast earned 22 in the rewrite), with timestamps **copied from the nearest transcript anchor, never estimated.** This makes them mechanically lintable post-hoc.
- New field `quotes`: 1-2 short verbatim transcript quotes per note. Free lexical anchors for BM25/where-document; currently zero exist.
- Optional field `retrieval_hooks`: 3-5 doc2query-style questions a future you might ask ("how did that guy split anonymous reads from authed pushes"). Filter generic ones per Doc2Query--. Indexed, not rendered prominently.
- Keep `thesis`, `summary`, `insights`, `interest_tags` as-is. They tested clean.

### Prompt principles (deltas only)

1. Normalize obvious ASR mishearings of tool and person names ("reax" -> regex); the model already does this when nudged (Omari -> Omarchy).
2. In multi-speaker transcripts, attribute claims to a speaker only when the transcript makes it unambiguous; otherwise say "one of the hosts." (2 of 4 faithfulness defects were misattributions.)
3. Do not import domain knowledge beyond the transcript, even when textbook-correct. (The TFIIH/P-TEFb conflation.)
4. Do not touch the anti-fluff instructions. They are working: 48/60 summaries have zero hedge words. Optionally ban the one surviving formula, "The standout X is."

### Indexing changes (store.py side; prerequisite for any richer enrichment)

- **Fix the 512-token cliff first.** Every production video_doc overflows gte-small's window today. Either reorder concepts-first, or split into 3 vectors per video (thesis+summary | concepts | insights+moments) with max-sim collapse. Both restored 10/10 rank 1 in the trial.
- Prepend a one-line situating context (title + thesis) to each transcript segment before embedding, per Anthropic contextual retrieval. Near-free with Haiku + prompt caching at vault volume.
- Add a lexical channel (BM25 side index or Chroma where-document) fused with dense, for the rare-exact-token episodic queries.
- Skip: ColBERT/multi-vector late interaction, HyDE by default (retrieval is already saturated at this scale; revisit if recall drops at 500+ notes).

---

## 5. Open questions and the continuous eval harness

### Open questions

1. Do the saturated retrieval numbers hold at full-vault scale (338+ docs) and at segment level (`ytk dive`)? Every arm hit recall@5 = 1.0 on a 30-doc pool; ceiling effects hide real differences.
2. Instagram measurement: the specifics counter is case-biased against lowercase entity names. Before concluding anything about IG enrichment quality, the counter needs an entity extractor that credits "oio.studio" and Sanskrit pose names.
3. Timestamp drift root cause: is it Whisper segment timing, or the model estimating? A lint comparing key_moment stamps against nearest transcript anchors would answer this cheaply across the whole vault.
4. Is a duration-scaled budget enough for coverage, or does long-form content need a two-pass enrichment (outline, then per-section extraction)?
5. Should degenerate Instagram posts be skipped? The only defensible guard found is narrow: hashtag-only caption AND zero slides (catches hot_meh, nothing else). Emptiness is only detectable after reading visuals.

### What a follow-up harness should measure continuously (per-ingest lint + monthly batch)

Per-ingest, zero-API-cost lints:
- **Token overflow:** video_doc length vs the embedder window. Alert > 512. (This bug shipped silently; the lint makes it impossible to reintroduce.)
- **Cap saturation:** flag when key_concepts hits its budget exactly; saturation means truncation.
- **Timestamp anchoring:** every key_moment within N seconds of a transcript anchor.
- **Hedge lexicon:** the expanded ~80-term regex; alert above 0.5/100w. Currently a formality, cheap insurance against prompt regressions.
- **Quote presence:** at least one verbatim quote per transcript-bearing note (once spec v2 lands).

Monthly batch, model-assisted (single-answer rubric grading, transcript in context, never pairwise):
- **Faithfulness spot-check:** claim decomposition on a random 5 notes, importance-weighted (thesis and concepts strict). Track the inflated rate; baseline is 2.3%.
- **Coverage (QuestEval-style):** sample salient transcript segments, ask whether the note would let you retrieve them. This is the metric the cap of 8 was silently failing.
- **Retrieval regression suite:** a frozen set of episodic queries written from memory BEFORE reading the enrichment (the audit's one circularity lesson), scored recall@1/MRR against the live index after every store.py or prompt change.

### One-line summary for the coffee

The enrichment is honest, dense, and 97.7% faithful; your suspicion was wrong in the best way. The actual problems are mechanical: the vector store truncates every video doc at 512 tokens today, and the flat cap of 8 concepts throws away the exact named tools you will one day search for. Fix store.py first, scale the caps second, touch the prompt barely.