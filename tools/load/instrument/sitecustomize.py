"""Record serving cache hit and miss events for one load run without changing product code.

The launcher adds this directory to `PYTHONPATH` and names the event file. Each wrapper calls the
wrapped method and appends one small JSON line after it returns. A stack without a cache
module leaves that cache unpatched and records only the caches that exist.
"""

from __future__ import annotations

import json
import os
import time

_LOG = os.environ.get("TCE_LOAD_CACHE_EVENTS")


def _write(row: dict) -> None:
    """Append one complete event line under the process's append-only write."""
    row.update(pid=os.getpid(), at=time.time())
    payload = (json.dumps(row, sort_keys=True) + "\n").encode("utf-8")
    descriptor = os.open(_LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        if os.write(descriptor, payload) != len(payload):
            raise OSError("cache event append was short")
    finally:
        os.close(descriptor)


def _patch_report_cache() -> bool:
    """Wrap the next-course report cache methods when the stack carries that cache."""
    from course_explorer.next_courses.report_cache import NextCourseReportCache

    original_get_raw = NextCourseReportCache.get_raw
    original_put_raw = NextCourseReportCache.put_raw
    original_get = NextCourseReportCache.get

    def get_raw(self, raw):
        report = original_get_raw(self, raw)
        _write(
            {
                "cache": "next_report",
                "event": "hit" if report is not None else "miss",
                "kind": "raw",
                "completed": len(raw.completed_inputs),
            }
        )
        return report

    def put_raw(self, raw, canonical, report):
        original_put_raw(self, raw, canonical, report)
        _write(
            {
                "cache": "next_report",
                "event": "put",
                "kind": "raw",
                "completed": len(raw.completed_inputs),
            }
        )

    def get(self, key):
        report = original_get(self, key)
        _write(
            {
                "cache": "next_report",
                "event": "hit" if report is not None else "miss",
                "kind": "canonical",
                "completed": len(key.completed_group_ids),
            }
        )
        return report

    NextCourseReportCache.get_raw = get_raw
    NextCourseReportCache.put_raw = put_raw
    NextCourseReportCache.get = get
    return True


def _patch_query_cache() -> bool:
    """Wrap the shared query-embedding cache when the stack carries that cache."""
    from course_explorer.embeddings.query_cache import SharedQueryEmbeddingCache

    original_get = SharedQueryEmbeddingCache.get
    original_put = SharedQueryEmbeddingCache.put

    def get(self, text, *, configuration):
        vector = original_get(self, text, configuration=configuration)
        _write(
            {
                "cache": "query_embedding",
                "event": "hit" if vector is not None else "miss",
                "text_length": len(text),
            }
        )
        return vector

    def put(self, text, vector, *, configuration):
        original_put(self, text, vector, configuration=configuration)
        _write({"cache": "query_embedding", "event": "put", "text_length": len(text)})

    SharedQueryEmbeddingCache.get = get
    SharedQueryEmbeddingCache.put = put
    return True


if _LOG:
    patched: list[str] = []
    try:
        if _patch_report_cache():
            patched.append("next_report")
    except ModuleNotFoundError:
        pass
    try:
        if _patch_query_cache():
            patched.append("query_embedding")
    except ModuleNotFoundError:
        pass
    _write({"event": "startup", "patched": patched})
