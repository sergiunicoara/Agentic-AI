from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Optional
import numpy as np

@dataclass
class EngineResult:
    ids: np.ndarray  # shape (n_queries, k), dtype=int

class VectorEngine(Protocol):
    name: str
    def build(self, docs: np.ndarray) -> None: ...
    def search(self, queries: np.ndarray, k: int) -> EngineResult: ...
