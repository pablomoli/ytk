"""SigLIP-2 over the taste test frames on a CUDA machine, keeping what the pooled vector throws away.

Per frame: the pooled vector, and at three depths of the vision tower the per-channel mean
and spread of the patch features and a Gram matrix of the patches after a fixed random
projection to 64 channels (channel correlations, with where things are discarded).
Standalone: no ytk import. Same checkpoint and revision as ytk/visual.py. Run by taste_pass_cuda.py.
"""

from __future__ import annotations

import numpy as np
import torch
from PIL import Image
from transformers import AutoModel, AutoProcessor

MODEL_ID = "google/siglip2-so400m-patch16-384"
MODEL_REVISION = "dd658faac399427308559e2c3ac1e99cbe43845d"
DEPTHS, PROJ, BATCH = (9, 18, 27), 64, 32


def processor():
    return AutoProcessor.from_pretrained(MODEL_ID, revision=MODEL_REVISION)


def prepare(proc, im: Image.Image) -> torch.Tensor:
    """The frame as the model takes it, on the CPU, so the decoded image need not be kept."""
    return proc(images=[im], return_tensors="pt")["pixel_values"][0].half()


class Tower:
    def __init__(self) -> None:
        self.model = (
            AutoModel.from_pretrained(MODEL_ID, revision=MODEL_REVISION, dtype=torch.float16)
            .to("cuda")
            .eval()
        )
        width = self.model.config.vision_config.hidden_size
        # One fixed projection for every frame and depth, so Gram matrices are comparable.
        gen = torch.Generator(device="cpu").manual_seed(0)
        self.proj = (torch.randn(width, PROJ, generator=gen) / PROJ**0.5).to("cuda")
        self.iu = torch.triu_indices(PROJ, PROJ)
        # Hooks, not output_hidden_states: the layer's own output is the one thing every version returns.
        layers, self.grabbed = self.model.vision_model.encoder.layers, {}
        for d in DEPTHS:
            layers[min(d, len(layers)) - 1].register_forward_hook(
                lambda _m, _i, o, d=d: self.grabbed.__setitem__(
                    d, o[0] if isinstance(o, tuple) else o
                )
            )

    def read(self, px: torch.Tensor) -> list[dict[str, np.ndarray]]:
        """px (B, 3, 384, 384) from prepare(); one dict of readings per frame."""
        with torch.inference_mode():
            feat = self.model.get_image_features(pixel_values=px.to("cuda").half())
            feat = getattr(feat, "pooler_output", feat)
            out = {"pooled": torch.nn.functional.normalize(feat.float(), dim=-1)}
            for d in DEPTHS:
                h = self.grabbed[d].float()
                out[f"stats_{d}"] = torch.cat([h.mean(1), h.std(1)], dim=1)
                z = h @ self.proj
                z = z - z.mean(1, keepdim=True)
                g = z.transpose(1, 2) @ z / z.shape[1]
                out[f"gram_{d}"] = g[:, self.iu[0], self.iu[1]]
        arrays = {k: v.cpu().numpy().astype(np.float32) for k, v in out.items()}
        return [{k: v[i] for k, v in arrays.items()} for i in range(len(px))]
