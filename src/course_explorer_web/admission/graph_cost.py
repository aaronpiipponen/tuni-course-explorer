"""The cache key of one prerequisite graph request."""

from __future__ import annotations

from collections.abc import Mapping


def graph_cost_field(body: Mapping[str, object]) -> str:
    """Return the cache field of one prerequisite graph request.

    The target is the request's own target string. The serving route marks a build for measurement
    only when that string is the root's canonical id or its exact official code, so the stored key
    space is at most two spellings per course times the eight flag combinations.
    """
    target = body.get("target_code")
    target = target if isinstance(target, str) else ""
    recommended = 1 if body.get("include_recommended") is True else 0
    inferred = 1 if body.get("include_inferred") is True else 0
    active = 1 if body.get("active_only") is True else 0
    return f"{target}|{recommended}|{inferred}|{active}"
