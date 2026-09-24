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

- **The install step is already done.** The project environment's
  `transformers` 5.5.4 exports `Sam3Model` and `Sam3Processor`; no scratch
  environment and no main-branch checkout were needed, and no Triton
  import is involved on that path. Checked by importing both classes.
- **The weights are gated.** `facebook/sam3` on the Hub is marked
  `gated: manual`. The account on this machine (`hf auth whoami`:
  `integr8deriv8`) is logged in. Requesting `config.json`:

  ```
  $ hf download facebook/sam3 config.json --local-dir sam3-probe
  Error: Access denied. This repository requires approval.
  ```

  An unauthenticated request for the same file returns HTTP 401. The
  repository lists `model.safetensors` and `sam3.pt` among 12 files; no
  size was fetched.
- Nothing else ran. No timing, no memory figure, no figure: a figure here
  would have to be faked, and the record's rules allow a section with no
  lead PNG when it failed at install.

## Result

**Stopped at the gate, not at the code.** The model class is present in
the installed transformers; the weights need the owner to accept Meta's
license on huggingface.co/facebook/sam3 and wait for approval, which only
the account holder can do. Until then the section's two questions, seconds
per image on MPS and peak memory beside SigLIP-2, have no answer, and the
verdict the brief asked for stays as the brief's inference: the detector is
conditioned on the text, so it runs at query time per image, and it cannot
replace region vectors cached at save time. That inference is also what
sections 54 and 56 point at from the other side: the recipe that located
objects on this material was crop-on-grey with SAM masks, which is
cacheable, and SAM 3 would only change the cutting step.

**Dead end by the plan's own clause**, "if it fails to load, record the
error verbatim and stop; that is the result". The error is recorded above.

## Next, if the owner approves the license

Two commands, in this order, with no other change to the branch:

```
hf download facebook/sam3 --local-dir ~/.cache/huggingface/sam3-probe
HF_HUB_OFFLINE=1 uv run python -c "from transformers import Sam3Model; Sam3Model.from_pretrained('facebook/sam3', dtype='float16').to('mps')"
```

Then the woman image with "sunglasses" and "the whole woman", timed, with
the two-model winners from section 54 beside SAM 3's masks. About 45 minutes
by the plan's budget; nothing else in the night depends on it.
