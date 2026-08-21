# 51 — CLIP identity (49R): the portrait claim, re-judged

**Question.** Section 49 killed composited portraits: deduplicated, same-latent
half-portraits were no more alike than strangers (AUC 0.43) under a pixel
Pearson judge. But pixel correlation punishes translation and layout — two
thumbnails from one channel, same topic, same style, score near zero if the
composition shifts. Issue #192: was the claim wrong, or the judge? Re-run the
identical split-half design with the perceptually aligned judge the
literature prescribes — cosine in CLIP image-embedding space.

## Pre-registration (written before any measurement)

**Construction.** Every unique exemplar thumbnail embedded once with the
open_clip ViT-L/14 **image** tower (the section-47 text tower's sibling;
weights already cached). A latent's visual identity = the activation-weighted
mean CLIP-image vector of its top-24 one-per-note exemplars (>= 12 distinct
images to qualify — section 49's dedup rule, unchanged).

**Registered gate.** Disjoint exemplar halves (even/odd activation ranks,
as in 49) give two identity vectors per latent; similarity = cosine.
Same-latent pairs vs 2,000 cross-latent pairs must separate at ROC
**AUC >= 0.80**. A fresh bar — nothing inherited from 49, in either
direction.

**Interpretation, fixed in advance.** PASS means latents do have visual
identities and section 49 indicted its judge along with its claim; the
display face remains a real exemplar (now the CLIP-medoid: the thumbnail
nearest the identity vector), and a redeemed wall may return. FAIL means
portraits are dead twice — pixel and perceptual — and the metaphor closes
for good.

Numbers land in `clip_identity.json`; runner
`experiments/sae_qwen/clip_identity.py`. Results follow below this line
only after the gate has run.

---

## Result: FAIL at 0.60 — dead in both judges, and now we know why

- **AUC 0.60** against the registered 0.80 (`01-the-second-judge.png`).
  Better than the pixel judge's 0.43, and still far short.
- **The mechanism is in the medians:** same-latent halves 0.894,
  cross-latent pairs 0.887. In CLIP space every YouTube thumbnail
  resembles every other — faces, bold type, saturated design. The
  thumbnail *genre* is its own cone, and it drowns the content.
- **Post-hoc diagnostics, disclosed and unregistered:** centering out the
  mean image embedding lifts AUC only to 0.64, so the cone is not the
  whole story. The rest is structural: **505 unique images serve 2,045
  qualifying latents** — random latent pairs already share 11% of their
  exemplar images. A ~500-item visual vocabulary cannot individuate a
  2,048-concept dictionary, under any judge.
- Per the pre-registered interpretation: **the portrait metaphor closes
  for good.** The passport's face stays what section 49 left it — a real
  exemplar, evidence displayed, nothing derived. Any future visual
  identity for latents needs a richer image source (frames, not
  thumbnails) and would be a new metaphor with its own registration.
