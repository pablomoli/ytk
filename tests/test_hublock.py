"""Single-instance hub lock (#38): exclusive flock on ~/.ytk/hub.lock."""

from __future__ import annotations

from ytk import hublock


def test_acquire_then_contend_then_release(tmp_path):
    path = tmp_path / "hub.lock"
    held = hublock.acquire(path)
    assert held is not None
    # flock is per open file description: a second open contends like a
    # second process would.
    assert hublock.acquire(path) is None
    held.close()
    second = hublock.acquire(path)
    assert second is not None
    second.close()
