"""The fixed API routes, the graph measurement marker and the request-model defaults of serving.

The front router, the request record and the classifier read the route set from here, the three
request models and the classifier read the two flag defaults, and the prerequisite graph route and
the front router read the graph marker.
"""

from __future__ import annotations

from enum import StrEnum

# The request-model defaults of the two flags the classifier prices. A search that omits
# `include_inactive` reads inactive courses, and a recommendation or next-courses request that omits
# `active_only` reads active courses only.
INCLUDE_INACTIVE_DEFAULT = True
ACTIVE_ONLY_DEFAULT = True

# The response header that the prerequisite graph route sets to `1` when the request's target names
# its root, so the front router records the elapsed graph cost of that request.
MEASURE_GRAPH_HEADER = "x-course-explorer-graph-measured"


class Route(StrEnum):
    """The fixed POST paths of the read-only API."""

    SEARCH = "/api/search"
    CATALOGUE = "/api/catalogue"
    COMPARISON = "/api/comparison"
    PREREQUISITES = "/api/prerequisites"
    NEXT_COURSES = "/api/next-courses"
    RECOMMENDATIONS = "/api/recommendations"
    STUDY_STRUCTURE = "/api/study-structure"
    COURSE_SUMMARIES = "/api/course-summaries"
    FEATURES = "/api/features"


def route_of(path: str) -> Route | None:
    """Return the fixed route whose path matches exactly, or ``None``."""
    try:
        return Route(path)
    except ValueError:
        return None
