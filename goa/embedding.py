"""Shared text embedding helpers, used for the catalogue and for queries."""

import zlib

import numpy as np


def hashed_bow(texts: list[str], dim: int = 512) -> np.ndarray:
    """Fallback when no embedding model can be downloaded: hashed bag of words."""
    out = np.zeros((len(texts), dim), dtype=np.float32)
    for i, t in enumerate(texts):
        for w in t.lower().replace(",", " ").replace(".", " ").replace(":", " ").split():
            out[i, zlib.crc32(w.encode()) % dim] += 1.0  # stable across runs
    return out
