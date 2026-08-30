# Step 0: what lands, when, and how much passes me

Curator engine (#197), step 0. No model calls. Script:
`scripts/measure_intake.py`; figure `figures/step0-intake.png`; sidecar
`figures/step0-intake.json`. Sources: every note under `sources/{youtube,
instagram,web,tiktok}` (the `captured:` stamp, birth time where the stamp
predates the field), `~/.ytk/capture_log.jsonl`, `~/.ytk/reels_state.json`.

## Instrument audit first

- `capture_log.jsonl`: 668 rows, 144 are test fixtures (`/abc`, `/bad`,
  `example.com`) written by the suite into the live log, the E5 pattern
  again. 524 rows are real and are the only ones counted.
- Ingested Instagram items leave `pending` and no timestamp survives the
  move (3 of 267 ingested shortcodes are still in the queue). Answer latency
  therefore has no instrument. The `asks` table is that instrument; until it
  exists the park timeout cannot be sized from data.
- `shared_at` on pending reels is a date, not a time, and the thread is
  shared with a peer, so "landed" counts both directions of the DM thread.
  The 2,920 July landings are not verified as the owner's own shares.

## Numbers

| quantity | value |
|---|---|
| source notes | 751 (youtube 434, instagram 267, web 28, tiktok 17 at sweep) |
| notes carrying a `My take` | 32 (4.3%) |
| landing rate, mean of last 12 weeks | youtube 31.6/wk, instagram 20.5/wk, web 2.2/wk, tiktok 1.2/wk; 56/wk total |
| landing rate, last three full weeks | 59, 56, 51 |
| bulk weeks | 07-13 (175), 07-20 (162), 07-27 (133): the July backfill and DM sweeps, not steady state |
| captures by hour, owner surfaces | two bands: 00-02 local (263 of 466) and 18 local (77); machine sync spreads 05-06 and 21 |
| instagram queue | 3,739 pending vs 267 ingested: 6.7% of what lands is ever ingested |

## What the numbers decide

- **Volume the ask loop must absorb: ~55 items a week, ~8 a day**, two
  thirds of it YouTube. At one proposal per item, a per-appearance digest
  holds a day or two of items comfortably; a per-item interrupt would fire
  eight times a day. The batched digest (research Q3) is confirmed by the
  owner's own rate, not only by the field's fatigue numbers.
- **The owner appears in bursts, not continuously.** Two bands carry most
  captures. An event-advanced loop (shape B) that delivers asks at the next
  appearance fits this; a 30-minute heartbeat would tick through ~20 empty
  slots a day.
- **Instagram is the hold-and-ask case in extreme form.** 93% of what lands
  never enters. Under the new engine that 93% is not a failure, it is the
  reflex bucket: items that never got a sentence and never will. The design
  must make "never" a cheap, explicit state (`dropped`, archived) rather
  than a queue of 3,739 that grows forever.
- **The July bulk weeks are the shape the engine must refuse.** 175 notes in
  a week with 32 takes across the whole corpus is exactly the intake the
  first law forbids. Backfilling those weeks through the ask loop is a
  separate decision (grandfather as `kept-unlabeled`, per the design note).

## Still unmeasured

Answer latency (needs the `asks` table); hub open hours as sessions rather
than capture bursts (the hub log carries no access lines); how much of the
3,739 is the owner's versus the peer's. None of these block step 1.
