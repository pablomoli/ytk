# Encoder audit — report 3: competitor stacks and interest-over-time prior art

2026-07-16 · issue #73, #74, #83 · deep-research pass C
105 agents · 23 sources fetched · 114 claims extracted · 25 adversarially verified (25 confirmed, 0 refuted, 3-0 votes throughout)

## Headline findings

1. **ytk's incumbent encoder is the open-source mainstream choice.** Khoj —
   the leading self-hostable "AI second brain" (35.8k stars, active, AGPL) —
   defaults to exactly `thenlper/gte-small` via sentence-transformers
   (`src/khoj/processor/embeddings.py`, verified against master July 2026).
   Whatever the MTEB gap turns out to be (pass A), gte-small is not an
   embarrassing outlier; it is the ecosystem default. The bar for migration is
   measured improvement, not fashion.
2. **Local-first embedding on consumer Macs is a solved, shipped problem** —
   Reflect (client-side similar-notes index over E2E-encrypted notes), Reor
   (Transformers.js + LanceDB), Smart Connections (bundled bge-micro-v2,
   384-dim, ~25 MB, in Electron), Khoj (gte-small + pgvector). Apple now backs
   this at OS level: NLContextualEmbedding (macOS 14+, 2023), the ~3B
   Foundation Models framework (2025, semantic-search APIs added WWDC 2026),
   Core AI (WWDC 2026), and mlx-embeddings (BERT/ModernBERT/Qwen3 architectures
   on Apple Silicon). ytk's architecture is on the right side of the split.
3. **The most direct commercial precedent for interest-over-time is Recall's
   Graph View 2.0** (shipped Jan 12, 2026): card-node knowledge graph with a
   date-range slider and a play button that animates the growth of the
   knowledge base over time. Nobody verified in this pass ships a
   stock-market/ticker metaphor — #83 has open lane.

## Product-by-product (verified, 3-0 adversarial votes)

| Product | Embeddings | Vector store | Local? | Note |
|---|---|---|---|---|
| Khoj (OSS, active) | gte-small via sentence-transformers (default; HF/OpenAI opt-in) | Postgres + pgvector | yes (default) | closest architectural cousin to ytk |
| Smart Connections (Obsidian) | bundled TaylorAI/bge-micro-v2, 384-dim, ~25 MB, transformers.js, block-level chunking | local index | yes | zero-setup local semantic search, no API key |
| Reor (OSS, archived Mar 2026) | Transformers.js feature-extraction, mean pooling | LanceDB | yes | prior art only; CPU-bound and reportedly slow |
| Reflect | undisclosed client-side model for similar-notes; cloud LLM (GPT-4 era) for chat | client-side index | embeddings yes | vendor self-report (Nov 2023), no teardown; privacy-split architecture |
| Mem (2022 era) | OpenAI embedding models | Pinecone (+ metadata filtering per user) | no | 2022 snapshot; current stack unknown |
| Rewind (Dec 2022 teardown) | none — SQLite FTS4 + Porter stemming | none | all indexing local (Vision OCR, whisper.cpp base.en) | flagship lifelogger launched with zero semantic search |

Apple platform layer (all verified): NLContextualEmbedding = BERT-style
on-device embedding sequences since macOS 14 (caller mean-pools);
Foundation Models framework (June 2025) = ~3B on-device LLM, no embedding API
at launch, semantic-search APIs added WWDC 2026; Core AI (WWDC 2026, replaces
Core ML) = Swift API for arbitrary on-device models. mlx-embeddings (v0.1.0,
Mar 2026) implements BERT, XLM-RoBERTa, ModernBERT, Qwen3, Llama-bidirectional
— i.e. the architecture families behind the pass-A candidate list run natively
on MLX.

## Interest-over-time prior art

**Verified:** Recall Graph View 2.0 (Jan 2026) — nodes are saved cards,
click opens slide-out drawer, timeline animation + date-range slider
replaying knowledge growth by creation date. Confirmed shipped (docs +
third-party reviews, not announcement-only).

**Extracted but NOT adversarially verified in this pass** (verification budget
went to the product claims; treat as leads with citations, not established
facts):

- ThemeRiver (Havre et al., IEEE InfoVis 2000) — the foundational
  theme-strength-as-river-current visualization; direct academic ancestor of
  what #83 wants.
- Streamgraph (Byron & Wattenberg 2008) — the technique was originally
  invented to visualize one person's last.fm music-listening history per
  artist per week: personal interest-over-time is the streamgraph's literal
  birthplace.
- Spotify Wrapped 2024 "Your Music Evolution" — segments a listener's year
  into distinct musical phases; commercial personal-taste-over-time story.
- arXiv:1912.09210 — geometric interest-drift metric: per-bin activity
  vectors, drift measured as angle between consecutive bins (45-degree
  threshold separates drift from shift). Directly reusable as a #83 "price
  change" definition.
- arXiv:2409.10649 (TTEC) — temporal topic embeddings aligned across time
  slices via a frozen "compass" model trained on the whole corpus, making
  cross-slice embeddings comparable. This is a concrete answer to #83's
  hardest problem (theme identity across snapshots) and to the #73 concern
  that re-embedding reprices history.

## What did not survive / stays open

No claims survived verification for mymind, Tana, Fabric.so, or
Limitless/Rewind's CURRENT (2025-26) stack — the report is silent on those,
not negative. Graph-view reception (the "pretty but useless" critique) was
extracted from Obsidian community sources but not verified. These fold into
#74's remaining scope, along with mining the local inbox reels about
competitors, which no web pass can do.

## Implications for ytk

- **Keep-or-migrate framing shifts:** the incumbent is the ecosystem default,
  so pass A must show a measured, corpus-specific win to justify moving —
  exactly what the eval harness is for. "Everyone uses something better" is
  now a refuted premise.
- **#83 (interest market):** use TTEC-style compass alignment (or simply pin
  theme centroids in the incumbent space) for ticker identity; use the
  arXiv:1912.09210 angle metric as a candidate price-change signal; the
  streamgraph's last.fm origin story argues a streamgraph view belongs next to
  the candlestick view — same data, two lenses. Recall's playable timeline is
  the only shipped competitor; a market metaphor is differentiated.
- **Grove/galaxy (#78):** the community's documented complaint about PKM graph
  views is undifferentiated hairballs; Recall's fix is cards-as-nodes +
  drawer + time scrubbing. Grove's provenance-bucket discipline and the
  planned galaxy layering are aligned with the fix, not the failure mode.
- **Platform watch:** Apple's WWDC 2026 semantic-search APIs and Core AI are
  worth a spike for the mobile horizon (#82) — an on-device Apple-native
  embedding path could eventually serve iPhone capture without hosting.

## Sources (primary unless noted)

kevinchen.co/blog/rewind-ai-app-teardown · get.mem.ai/blog/building-mem-x ·
pinecone.io case study · reflect.app/blog/ai-search + reflect.academy ·
github.com/reorproject/reor · github.com/khoj-ai/khoj + docs.khoj.dev ·
smartconnections.app + github.com/brianpetro/obsidian-smart-connections ·
developer.apple.com (NLContextualEmbedding, core-ai, WWDC26 241/324) ·
machinelearning.apple.com (foundation-models-2025) ·
github.com/Blaizzy/mlx-embeddings · feedback.getrecall.ai changelog +
docs.recall.it · leads: ieeexplore.ieee.org/document/885098 (ThemeRiver),
leebyron.com/streamgraph (Byron & Wattenberg PDF), newsroom.spotify.com
(Wrapped 2024), arXiv:1912.09210, arXiv:2409.10649.
