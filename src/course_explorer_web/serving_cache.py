"""The per-process retained caches of one serving dataset identity.

The module holds one slot per serving process. A request that resolves the same dataset identity
receives the same three caches, and a different identity replaces them, so no retained row outlives
the dataset it was read from. Construction reads no database, opens no engine and touches no file.
The lookup projection builds on its first command use, the source-fact cache fills on its first
compiler read, and the descriptive chunk cache fills on its first descriptive read.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from course_explorer.config import WebSettings
from course_explorer.embeddings.read import DescriptiveChunkCache
from course_explorer.prerequisite.source_cache import PrerequisiteSourceFactCache
from course_explorer.search.projection import LookupProjectionCache
from course_explorer_web.dataset import ServingDataset


@dataclass(frozen=True)
class ServingCaches:
    """The lookup projection, the prerequisite source facts and the chunk tuples of one dataset."""

    dataset_identity: str
    lookup_projection: LookupProjectionCache
    prerequisite_sources: PrerequisiteSourceFactCache
    descriptive_chunks: DescriptiveChunkCache


_lock = threading.Lock()
_current: ServingCaches | None = None


def serving_caches(serving: ServingDataset, settings: WebSettings) -> ServingCaches:
    """Return the caches of this dataset identity, building them when the identity differs."""
    global _current
    with _lock:
        if _current is not None and _current.dataset_identity == serving.identity:
            return _current
        _current = ServingCaches(
            dataset_identity=serving.identity,
            lookup_projection=LookupProjectionCache(),
            prerequisite_sources=PrerequisiteSourceFactCache(
                max_entries=settings.web_prerequisite_source_cache_entries
            ),
            descriptive_chunks=DescriptiveChunkCache(max_entries=settings.web_chunk_cache_entries),
        )
        return _current
