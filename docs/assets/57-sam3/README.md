# 57 — SAM 3 on this machine (#218)

**Question.** SAM 3 (arXiv 2511.16719) segments from a text concept in one
model, which would replace the two-model recipe (SAM cuts, SigLIP names) for
the two queries it could not handle on the woman image: "sunglasses", where
no region matched, and "the whole woman", where SAM had no whole-person
mask. The brief said the official release fails on Apple Silicon because of
a Triton dependency and that the transformers main branch is the workaround.
Does it load on the M3, how long does an image take on MPS, and does it
belong in ytk at query time or only in the boxing project on the 3070?

Section 4 of the patch-grid night, `docs/design/patch-grid-night/README.md`.

## What was done

- **Install.** The project environment's `transformers` 5.5.4 already
  exports `Sam3Model` and `Sam3Processor`; no scratch environment and no
  main-branch checkout were needed, and no Triton import sits on that path.
  The image processor needs torchvision, so the run uses the same
  `--with torchvision` flag as SAM.
- **The gate.** `facebook/sam3` is gated `manual`. The first attempt on
  2026-09-24 was refused ("Access denied. This repository requires
  approval."); the owner requested access on 2026-09-26 and Meta granted it
  within about twenty minutes. `hf download facebook/sam3` then fetched 6.4
  GB (both the safetensors and the `.pt` checkpoint).
- **The run.** `Sam3Model.from_pretrained(..., dtype=float16)` on MPS, 0.84B
  parameters, and seven concept prompts on the woman image: the two the
  plan named ("sunglasses", "the whole woman"), their plain-noun forms
  ("a woman wearing sunglasses", "woman"), the printed caption two ways
  ("printed caption text", "text"), and "a stone wall" from the spike.
  Instances kept at score 0.5. `run57.py`, once with five prompts and once
  with seven; the second run was slower per prompt with the same masks.

## Result

**It loads, it runs, it is a few seconds a query.**

| | |
|---|---|
| load, fp16 | 4 to 6 s |
| per prompt after warm-up | 2.6 s (five-prompt run), 4.9 s (seven-prompt run) |
| peak MPS driver memory | 3.0 GB |

- **"sunglasses"**: one mask, score 0.93, 0.3 percent of the frame, on the
  sunglasses. Its overlap with the spike's SAM masks: IoU 0.81 with the
  region section 54's masked head chose, 0.02 with the region crop-on-grey
  chose (her face). On the one small-object query where SAM 3 supplies a
  ground truth, the masked head was right and the crops were not.
- **"a woman wearing sunglasses"** and **"woman"**: one mask each, scores
  0.95 and 0.96, 26 percent of the frame, the whole person. No SAM-1 region
  overlaps it above IoU 0.20, so the two-model recipe cannot return this
  answer at all; both section 54 recipes gave her face. **"the whole
  woman"**: nothing above 0.5. The prompt wants a noun phrase, not a
  description of scope.
- **"printed caption text"** and **"text"**: nothing above 0.5. SAM 3 does
  not cut the caption either, so the unaddressed failure the brief noted
  stays unaddressed by this model.
- **"a stone wall"**: four masks, scores 0.55 to 0.86, 2 to 29 percent of
  the frame, the wall and the pavement it stands on. IoU 0.28 with the
  crop's winner.

**Verdict for ytk.** The brief's inference holds and now has numbers: the
detector is conditioned on the text, so it costs a forward pass per image
per query, about three to five seconds on the M3 at 3 GB. That rules it out
as the engine behind a cached "show me where" across the whole collection,
and rules it in for a single-image view where a few seconds is fine, where
it returns the whole person the SAM-1 masks never had and the small object
the crops missed. On the 3070 it is a query-time tool for boxing without
reservation. The night's one dead-end condition for this section, more than
a few seconds per image or memory pressure beside SigLIP-2, sits on the
line: 2.6 to 4.9 s, and 3 GB beside SigLIP-2's 1 GB fits on this machine.

**A caveat this section raises for section 54.** Section 54's 6-to-2
verdict against the masked head rested on the covering tiebreaker, and
section 56 later showed that covering favours large regions. SAM 3's
sunglasses mask agrees with the masked head's pick on the only small object
where an independent answer exists. The 54 verdict is not overturned by one
query, but it is weaker than it read, and it is recorded here so the
owner's decision sees it.

## Figures

- `01-sam3-against-the-recipe.png` — the woman image, SAM 3's masks per
  prompt in cyan painted by score, section 54's crop-on-grey winner in blue
  and masked-head winner in gold where the prompt was asked there.

Cache `~/.ytk/patch_grid/night/57_sam3.npz`; runner
`experiments/patch_grid/run57.py`; figure `scripts/plot_night.py 57`.
