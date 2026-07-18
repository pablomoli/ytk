"""Text-side SigLIP batching contracts used by profile evaluation."""

import numpy as np

from ytk import visual


def test_embed_texts_pads_and_truncates_variable_length_claims(monkeypatch):
    received = {}

    class Inputs(dict):
        def to(self, _device):
            return self

    class Processor:
        def __call__(self, **kwargs):
            received.update(kwargs)
            return Inputs()

    class Features:
        def float(self):
            return self

        def cpu(self):
            return self

        def numpy(self):
            return np.asarray([[1.0, 0.0], [0.0, 1.0]])

    class Model:
        def get_text_features(self, **_inputs):
            return Features()

    monkeypatch.setattr(visual, "_load", lambda: (Model(), Processor(), "cpu"))

    embeddings = visual.embed_texts(["short", "long " * 100])

    assert embeddings == [[1.0, 0.0], [0.0, 1.0]]
    assert received["padding"] == "max_length"
    assert received["truncation"] is True
    assert received["max_length"] == 64
