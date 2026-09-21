> Produced 2026-09-20 by a seven-agent sweep for section 53 (#218): four literature searchers, one Reddit searcher, a link checker that confirmed 41 of 42 sources against the arXiv API or by fetching them, and one synthesizer allowed to cite only what verified. Five of the most load-bearing arXiv ids were re-checked by hand afterwards. Reddit refused every way of being read, so section 4 is empty by measurement, not by omission. "I" below is the synthesizer.

# Research brief: locating a text match inside SigLIP-2 (2026-09-20)

I cite only the verified findings. Anything that is my own inference is marked as such.

## 1. Where tonight's work sits

**(a) The pooling probe's attention weights.**
- This is the raw-attention visualization line. Chefer et al. built relevancy propagation to replace it (https://arxiv.org/abs/2012.09838), with a bi-modal extension in https://arxiv.org/abs/2103.15679.
- The literature predicts the failure. Grad-ECLIP moves away from attention maps because they are "extremely sparse in CLIP" (https://arxiv.org/abs/2502.18816). Darcet et al. show that high-norm tokens produce noisy attention maps and hurt dense tasks (https://arxiv.org/abs/2309.16588).
- A probe spending 20-24 percent of its attention on 10 tokens fits that pattern.

**(b) The patch-alone lens.**
- This is MaskCLIP's move. The survey describes it as replacing last-layer attention with the identity, so values are just projected (https://arxiv.org/abs/2505.22209).
- The searcher reports that the survey has no discussion of attention-pooling heads or of SigLIP/SigLIP-2. The whole successor line (SCLIP, ClearCLIP, NACLIP, ProxyCLIP, ResCLIP) assumes a CLS token, so there was no known substitution to make for a MAP head.
- No source directly explains the speckled, near query-independent map. Three give partial explanations:
  - CorrCLIP finds raw CLIP patch correlations incoherent, with unrelated patches scoring spuriously high (https://arxiv.org/abs/2411.10086).
  - Darcet et al. find high-norm tokens carry global rather than local information (https://arxiv.org/abs/2309.16588).
  - TextRegion handles SigLIP-2 by keeping the probe's real cross-attention and only masking which patches it may see. It does not bypass the head (https://arxiv.org/abs/2505.23769).
- My inference, not a paper's claim: in CLIP the step after pooling is close to linear, so scoring each token alone roughly decomposes the pooled sum. In SigLIP-2 the head applies layernorm and a residual MLP after pooling, so that decomposition does not hold. A single token is an input the head never saw in training. Layernorm also erases the norm differences that set real mixing weights. What survives is mostly shared global content, which would read as query-independent.

**(c) Gradient x input through the head only.**
- This is the Chefer, Grad-ECLIP, LeGrad line.
- Those methods use intermediate spatial features (Grad-ECLIP) or gradients at every layer (LeGrad, https://arxiv.org/abs/2404.03214). A head-only gradient sees tokens after global mixing has already happened.
- Weak agreement with occlusion is what this line would predict. The whole-encoder version remains untested here.

**Occlusion.**
- This is the perturbation line, rooted in RISE (https://arxiv.org/abs/1806.07421) and extremal perturbations (https://arxiv.org/abs/1910.08485).
- Both exist because a single fixed-size cover has known weaknesses. RISE uses many random multi-region masks. Extremal perturbations optimizes a smooth mask of variable area.
- FIxLIP argues first-order maps "overlook complex cross-modal interactions" (https://arxiv.org/abs/2508.05430).
- My reading: the frame-filling subject is an interaction case, because no single 64 px region is necessary when the evidence is redundant.

**The long tokens.**
- This is the registers line. Darcet et al. define high-norm as above 150, find 2.37 percent of patches (about 13.6 of 576, against our roughly 10), see them emerge near 37 percent depth, and see them only in large models (https://arxiv.org/abs/2309.16588).
- Mamba-R shows the phenomenon is not attention-specific (https://arxiv.org/abs/2405.14858).
- In OpenCLIP ViT-B/16, about 10 of roughly 37,000 MLP neurons cause it. The outlier tokens appear after layer 6 of 12 (https://arxiv.org/abs/2506.08010).
- CLIP Surgery's "noisy activations" is an earlier diagnosis of the same family (https://arxiv.org/abs/2304.05653).
- That these tokens keep the attention after their pixels are greyed is consistent with Darcet's finding that they hold little local information.
- No verified source measures this on SigLIP-2 or on any MAP head. Our numbers appear to be unreported.

**SAM cuts, SigLIP names.**
- This is the recipe that keeps winning across the verified findings:
  - TextRegion: https://arxiv.org/abs/2505.23769
  - CorrCLIP: https://arxiv.org/abs/2411.10086
  - Trident: https://arxiv.org/abs/2411.19346
  - Region adjacency graphs: https://arxiv.org/abs/2512.07360
- The literature predicts our success.
- The reliance on printed text is independently corroborated on CLIP internals through attribution patching, which finds "visual typography" components (https://arxiv.org/abs/2505.20229). That was measured on CLIP, not SigLIP-2.

## 2. What has changed since the recipe we used

**TextRegion replaces the "46 crops on grey" step.**
- It reports ViT-B/16 mIoU against MaskCLIP, SCLIP and ProxyCLIP: VOC21 70.9 vs 61.1 / 59.1 / 61.3, ADE20K 22.8 vs 11.9 / 16.1 / 20.2, COCO-Stuff 28.7 vs 16.7 / 22.4 / 26.5 (https://arxiv.org/abs/2505.23769). Code is at https://github.com/avaxiao/TextRegion.
- The recipe is one encoder pass, then one masked head pass per region.
- M3: very likely fine, because the encoder already runs and the head is tiny.
- RTX 3070: fine.
- It uses SAM2. Our sam-vit-base masks should substitute. That is my assumption.

**SAM 3** (https://arxiv.org/abs/2511.16719) does concept-prompted detection, segmentation and tracking in one model. It reports about 30 ms per image on an H200.
- M3: the official release fails on Apple Silicon because of a Triton dependency. The transformers main branch is the workaround, and no MPS timings exist (https://huggingface.co/facebook/sam3/discussions/11). An MLX port is listed but its page was not opened (https://huggingface.co/mlx-community/sam3-image).
- No smaller variant exists. The request for one is open with no reply (https://github.com/facebookresearch/sam3/issues/219).
- RTX 3070: CUDA is present. The roughly 848M-parameter, 3.4 GB figure comes from secondary write-ups. It should fit in 8 GB for still images. Video memory use is unknown. Triton on native Windows may need WSL2, which is my guess.
- Verdict for ytk (my inference): SAM 3's detector is conditioned on the text, so it must run at query time per image. Region embeddings are query-independent and cache at save time. For "instant from cache" the two-model recipe is not obsolete. For boxing it may be.

**Alternatives to fixing SigLIP-2's patch tokens.**
- dinov3.seg reports an average mIoU of 50.44 with no SigLIP component (https://arxiv.org/abs/2603.19531).
- TIPSv2 trains patch-text alignment in during pretraining (https://arxiv.org/abs/2604.12012).
- If the goal becomes "best dense map" rather than "understand SigLIP-2", this is the line to use.

**MobileSAM.**
- It is claimed to be about 66x smaller and 38x faster than SAM ViT-H (https://docs.ultralytics.com/models/mobile-sam, from a search snippet).
- See section 5 for why I doubt it helps us much.

**Video.**
- Grounded-SAM-2 is the maintained detect, segment, track pipeline for video (https://github.com/IDEA-Research/Grounded-SAM-2).
- SAM 3.1 "Object Multiplex" for multi-object tracking rests on a search snippet only (https://ai.meta.com/blog/segment-anything-model-3/).

## 3. Ranked next experiments

**1. Region-masked MAP head on cached tokens.**
- What to do:
  - At save time, run one SigLIP-2 pass, keep the 576 tokens, and keep the SAM masks.
  - Run the real head once per mask, with -inf on attention logits outside the mask.
  - Store about 46 vectors per image. Query time is then a dot product.
- Source: TextRegion (https://arxiv.org/abs/2505.23769).
- Cost on the M3: one encode plus 46 tiny head passes, seconds per image. SAM's 17 s stays the bottleneck.
- Figure: crop-on-grey vs masked-pool vs occlusion on the same queries.
- Dead end: masked-pool picks the right mask less often than crop-on-grey, or every region containing a long token scores alike.

**2. Handle the long tokens.**
- What to do:
  - First, reuse the masking code from experiment 1 to hide the roughly 10 long tokens from the probe. Measure how far the embedding moves and whether lens (a) then agrees with occlusion.
  - Then hook the per-layer norms to find the depth where they emerge. Compare it with 37 percent (https://arxiv.org/abs/2309.16588) and layer 6 of 12 (https://arxiv.org/abs/2506.08010).
  - Then try the neuron relocation, with code at https://github.com/nickjiang2378/test-time-registers.
- Cost on the M3: forward passes with hooks over 40 images, minutes to an hour.
- This is the most publishable item, because nothing here has been measured on a MAP head.
- Dead end: no small neuron set explains the outliers, or Spearman against occlusion stays below about 0.2 after relocation.

**3. Firm up the referee.**
- What to do:
  - Occlude whole SAM objects. That is 46 passes, roughly 16 s per image at our measured rate.
  - Add a RISE run (https://arxiv.org/abs/1806.07421) on a handful of images only. 2,000 masks is about 11 minutes per image, so size it before launching.
  - Score the lenses with insertion/deletion curves, as FIxLIP does on SigLIP-2 (https://arxiv.org/abs/2508.05430).
- Dead end: RISE and sliding occlusion rank regions the same way, which would mean the current referee is already adequate.

**4. Time SAM 3 on the M3.**
- What to do: run SAM 3 through transformers main on the queries where we failed ("sunglasses", a whole person).
- Sources: https://huggingface.co/facebook/sam3/discussions/11 and https://arxiv.org/abs/2511.16719.
- Cost on the M3: an install plus a few images.
- Dead end: more than a few seconds per image on MPS, or memory pressure when it runs next to SigLIP-2. In that case move this to the 3070 and keep it for boxing only.

**5. Whole-encoder gradient lens.**
- What to do: run LeGrad (https://arxiv.org/abs/2404.03214) or Grad-ECLIP-style weighting (https://arxiv.org/abs/2502.18816), after the register handling from experiment 2.
- Cost on the M3: one forward and backward per image-query pair. Nothing caches, so it suits a single-image view only.
- Dead end: Spearman against the improved referee stays below about 0.3.

## 4. What practitioners say

- Zero Reddit threads were opened, so there is no consensus or anecdote to report.
- The Reddit searcher was blocked five ways: a JSON login wall, a WebFetch refusal, a WebSearch crawler block, four mirrors, and jina.ai.
- DuckDuckGo showed thread titles about SAM and SAM 3 in r/computervision, r/deeplearning, r/comfyui and r/StableDiffusion, but none could be loaded.
- Three of the four literature searchers also came up empty on Reddit.
- Two numbers from the non-Reddit sweep are unverified:
  - Grounded-SAM-2 runs at about 1.5 s per image on a T4.
  - YOLO-World runs at 161 FPS on a T4.

## 5. Disagreements and unknowns

**Whether SAM 3 makes the recipe obsolete.**
- The SAM searcher says our recipe is "architecturally superseded".
- I say it is not superseded for query-time caching, as argued in section 2.
- No source compares SAM 3 against an occlusion referee.

**Whether MobileSAM brings the mask step under a second.**
- The searcher predicts a sub-second step. I doubt it, for two reasons:
  - The 38x figure is measured against ViT-H, and we run ViT-B.
  - Automatic mask generation decodes a 32x32 grid of 1,024 point prompts and then filters the masks. That share of the 17 s would not shrink with a smaller encoder. This is my knowledge, unverified in this run.
- Profile the encoder against the prompt loop before swapping. Lowering points_per_side may help more.

**Claims I cannot stand behind.** These came from searcher summaries and have no verified finding behind them:
- The attention-sink paper (2507.16018), including its "another token takes over when one is masked" result.
- YOLOE (2503.07465).
- 2512.06032.
- The Reddit sweep's 2608.02284, 2502.06818, 2511.16170 and 2410.11087.
- The 848M parameter count for SAM 3.
- The contents of the MLX port page.
- SAM 3.1.

**Claims that are thin or the searcher's own explanation.**
- The recipe of https://arxiv.org/abs/2510.23894 is known only at abstract level.
- The SigLIP-2 paper's dense-feature numbers were not retrieved (https://arxiv.org/abs/2502.14786).
- The line that lens (b) is "context-free because the probe sees one token" is the searcher's explanation, not TextRegion's text.

**Untested on SigLIP-2 or on any MAP head.**
- Register neurons.
- PH-Reg (https://arxiv.org/abs/2505.21501).
- LeGrad, Grad-ECLIP and CLIP Surgery.
- Weighted relevance accumulation (https://arxiv.org/abs/2308.10240).
- Whether FIxLIP's SigLIP-2 results say anything about the head is unread.

**Unaddressed failures.**
- No verified source addresses printed text that SAM cannot cut. An OCR box used as an extra region is my suggestion only.
- No verified source addresses part-versus-whole selection among nested masks.

## 6. Sources

- TextRegion: Text-Aligned Region Tokens from Frozen Image-Text Models, 2025-05, https://arxiv.org/abs/2505.23769 (code at https://github.com/avaxiao/TextRegion)
- Improving Visual Discriminability of CLIP for Training-Free Open-Vocabulary Semantic Segmentation, 2025-10, https://arxiv.org/abs/2510.23894
- A Survey on Training-free Open-Vocabulary Semantic Segmentation, 2025-05, https://arxiv.org/abs/2505.22209
- CorrCLIP, 2024-11, https://arxiv.org/abs/2411.10086
- Trident, 2024-11, https://arxiv.org/abs/2411.19346
- dinov3.seg, 2026-03, https://arxiv.org/abs/2603.19531
- TIPSv2, 2026-04, https://arxiv.org/abs/2604.12012
- SigLIP 2, 2025-02, https://arxiv.org/abs/2502.14786
- Structure-Aware Feature Rectification with Region Adjacency Graphs, 2025-12, https://arxiv.org/abs/2512.07360
- SAM 3: Segment Anything with Concepts, 2025-11, https://arxiv.org/abs/2511.16719
- facebook/sam3 discussion #11 (Apple Silicon, Triton), https://huggingface.co/facebook/sam3/discussions/11
- mlx-community/sam3-image (listing only), https://huggingface.co/mlx-community/sam3-image
- facebookresearch/sam3 issue #219, 2025-11, https://github.com/facebookresearch/sam3/issues/219
- MobileSAM, Ultralytics docs (snippet), https://docs.ultralytics.com/models/mobile-sam
- IDEA-Research/Grounded-SAM-2, https://github.com/IDEA-Research/Grounded-SAM-2
- SAM 3.1 blog (snippet only), 2026-03, https://ai.meta.com/blog/segment-anything-model-3/
- Vision Transformers Don't Need Trained Registers, 2025-06, https://arxiv.org/abs/2506.08010 (code at https://github.com/nickjiang2378/test-time-registers)
- Vision Transformers with Self-Distilled Registers, 2025-05, https://arxiv.org/abs/2505.21501
- Vision Transformers Need Registers, 2023-09, https://arxiv.org/abs/2309.16588
- Mamba-R: Vision Mamba Also Needs Registers, 2024-05, https://arxiv.org/abs/2405.14858
- Grad-ECLIP, 2025-02, https://arxiv.org/abs/2502.18816
- LeGrad, 2024-04, https://arxiv.org/abs/2404.03214
- FIxLIP (Weighted Banzhaf Interactions), 2025-08, https://arxiv.org/abs/2508.05430
- CLIP Surgery, 2023-04, https://arxiv.org/abs/2304.05653
- Transformer Interpretability Beyond Attention Visualization, 2020-12, https://arxiv.org/abs/2012.09838
- Generic Attention-model Explainability (bi-modal), 2021-03, https://arxiv.org/abs/2103.15679
- Weighted Relevance Accumulation, 2023-08, https://arxiv.org/abs/2308.10240
- RISE, 2018-06, https://arxiv.org/abs/1806.07421
- Extremal Perturbations and Smooth Masks, 2019-10, https://arxiv.org/abs/1910.08485
- From What to How: Attributing CLIP's Latent Components, 2025-05, https://arxiv.org/abs/2505.20229