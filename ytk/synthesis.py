"""Synthesis engine for ytk's interest model.

Reads every note's embedding + enrichment from the ChromaDB video collection,
clusters notes into themes, and makes one Claude structured call to label the
clusters and write a prose profile. Pure helpers are unit-tested; `run_profile`
wires the store and the Claude SDK together.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from pydantic import BaseModel
from sklearn.cluster import KMeans

from .config import InterestConfig, load_config
from .interest import InterestSnapshot, Theme, save_snapshot
from .sdk import run_structured
from .store import get_all_videos
from .vault import _get_brain_path


class SynthesisTooSparse(Exception):
    """Raised when the vault has too few notes to synthesize a profile."""

    def __init__(self, have: int, need: int):
        super().__init__(f"need at least {need} notes to synthesize, have {have}")
        self.have = have
        self.need = need


def choose_k(n: int, cfg: InterestConfig) -> int:
    """Pick a cluster count: sqrt-scaled, clamped to [cluster_min, cluster_max] and n."""
    if n <= 0:
        return 1
    if n <= cfg.cluster_min:
        return n
    k = round(math.sqrt(n / 2))
    return max(cfg.cluster_min, min(cfg.cluster_max, k, n))


def cluster_embeddings(embeddings: np.ndarray, k: int) -> list[int]:
    """Assign each embedding row to one of k clusters. Deterministic (seeded)."""
    km = KMeans(n_clusters=k, random_state=0, n_init=10)
    return [int(label) for label in km.fit_predict(embeddings)]
