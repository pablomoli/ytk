"""One lock for every model that touches the GPU in this process.

2026-09-06: the hub restarted with three items waiting at answered, the
loop thread's first duplicate-check embedding (Qwen3 on MPS) ran while the
warm-up thread was loading SigLIP on the same device, and Metal aborted the
process three times in forty seconds ("failed assertion _status <
MTLCommandBufferStatusCommitted"). Encodes are short; serializing them
costs milliseconds and removes the race.
"""

from __future__ import annotations

import threading

GPU_LOCK = threading.Lock()
