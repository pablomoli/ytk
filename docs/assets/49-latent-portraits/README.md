# 49 — Latent portraits (rung 7', part 2): the pass that was a bug

**Question.** GEN mode wanted to *imagine* what a latent looks like and
failed its gate (section 47). The extractive twin *composites*: a latent's
portrait as the activation-weighted average of its exemplars' real
thumbnails. The registered question was whether such portraits are
identities — whether a latent's face survives being built from a different
half of its own evidence.

## Pre-registration (written before any measurement)

**Construction.** For each latent with >= 12 image-bearing exemplars:
center-crop square, 128x128, average weighted by activation.

**Registered gate — identifiability (P1).** Two portraits per latent from
disjoint exemplar halves; similarity = pixel Pearson r; same-latent vs
all-cross-pairs must separate at **ROC AUC >= 0.80**.

---

## Result: FAIL — and the pass that preceded it was the finding

The first run scored **AUC 0.97** and was declared a win. The owner then
looked at the hub and asked one question: *why does the same image pop up
again and again?* That question was the real gate.

**The contamination.** Segments inherit their parent video's thumbnail. In
a typical latent's top-24 exemplars, **40% are the same image repeated**
(a third of latents are majority-duplicate). So "disjoint halves" routinely
held copies of one physical image, and the gate scored agreement between a
thumbnail and itself.

**The collapse (figure 01).** Same measurement, one exemplar per note:
AUC **0.97 -> 0.43**. Same-latent halves (median r 0.16) are no more alike
than different latents (0.20). Deduplicated, a transparency-average of 24
distinct thumbnails has no identity at all — the fifth registered loss,
and the first one caught by eye rather than by null.

**The mechanism (figure 02).** Latent #272's top-8 evidence before and
after one-per-note: five copies of one lecture frame and two copies of the
tokenization card, versus eight distinct notes. The "ghost typography" the
first run celebrated was substantially this — one video agreeing with
itself.

**What survives.** The passport (figure 03) keeps a face, but an honest
one: the latent's most central *real* exemplar thumbnail — evidence
displayed, nothing derived, no gate needed because nothing is claimed.
The same one-per-note rule is now applied to section 43's wall mosaics
(re-rendered; distinct-image coverage is 45.9%, not the 55.9% the
duplicates inflated) and to the hub's feature cards.

**Verdict on the metaphor.** Composited portraits are dead as an
instrument: without duplicate inflation they carry no identity, and with
it they carry a lie. The paraphrase slot stays open; the compass (48)
remains the surviving candidate.
