"""Shared reuse of validated query embeddings under one embedding configuration.

The supervisor creates the region before it forks the workers, so one query's vector is computed
once and every worker reuses it. The key is the exact text sent to the embedding service under the
configuration identity that produced the vector, and the value is the float64 vector, so a cached
answer is the same vector a fresh request would return.
"""

from __future__ import annotations

import struct

from course_explorer.constants import COURSE_EMBEDDING_DIMENSION
from course_explorer.shared_cache import SharedByteCache

_VECTOR = struct.Struct(f"<{COURSE_EMBEDDING_DIMENSION}d")


class SharedQueryEmbeddingCache:
    """Byte-bounded shared store of query vectors keyed by configuration identity and exact text."""

    def __init__(self, cache: SharedByteCache) -> None:
        self._cache = cache

    @classmethod
    def create(cls, size: int) -> SharedQueryEmbeddingCache:
        """Create the supervisor's shared region of the requested byte size."""
        return cls(SharedByteCache.create(size))

    def get(self, text: str, *, configuration: str) -> tuple[float, ...] | None:
        """Return the stored vector for one exact text and configuration, or ``None``."""
        payload = self._cache.get(_key(text, configuration))
        if payload is None:
            return None
        if len(payload) != _VECTOR.size:
            raise ValueError("the shared query embedding cache holds an unexpected vector size")
        return _VECTOR.unpack(payload)

    def put(self, text: str, vector: tuple[float, ...], *, configuration: str) -> None:
        """Store one validated vector under its exact text and configuration identity."""
        if len(vector) != COURSE_EMBEDDING_DIMENSION:
            raise ValueError("a query embedding vector has an unexpected dimension")
        self._cache.put(_key(text, configuration), _VECTOR.pack(*vector))

    def close(self) -> None:
        """Release the supervisor's region."""
        self._cache.close()


def _key(text: str, configuration: str) -> bytes:
    return b"q" + configuration.encode() + b"\x00" + text.encode()
