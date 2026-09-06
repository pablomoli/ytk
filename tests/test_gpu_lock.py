"""Every encoder holds the process GPU lock while it touches the model."""

from __future__ import annotations

from ytk import gpu, store


def test_text_encoder_holds_the_gpu_lock(monkeypatch):
    class FakeModel:
        def encode(self, texts, **kw):
            assert gpu.GPU_LOCK.locked()
            return [[1.0, 0.0] for _ in texts]

    ef = store.InstructionAwareEF("m", "q: ", device="cpu")
    monkeypatch.setattr(ef, "_load", lambda: FakeModel())
    assert [float(v) for v in ef.embed_user_query("x")] == [1.0, 0.0]
    assert not gpu.GPU_LOCK.locked()
