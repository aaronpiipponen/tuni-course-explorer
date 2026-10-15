"""Hub-centred similarity arithmetic shared by search, comparison and recommendations.

Every stored teaching chunk is a unit vector, and the catalogue hub is their mean. Raw similarity is
dominated by that shared mean, so the product features compare `vector - hub` instead of the raw
vector. The learning-outcome field additionally shares a template, so a separate outcomes hub is
subtracted there. This module owns only the pure vector arithmetic. Carriers, settings and
repositories live in their own seams.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from course_explorer.enums import TeachingTextField


def mean_unit_vectors(vectors: Sequence[Sequence[float]]) -> tuple[float, ...]:
    """Return the component-wise mean of the supplied vectors normalized to unit length first.

    The stored chunks are unit vectors, so each supplied vector is normalized before averaging and
    this mean is the hub those same chunks subtract. Empty input, a zero-norm vector, a
    non-finite component, or mismatched dimensions fails loudly instead of returning a fabricated
    centre.
    """
    if not vectors:
        raise ValueError("mean_unit_vectors requires at least one vector")
    dimension = len(vectors[0])
    if dimension == 0:
        raise ValueError("mean_unit_vectors requires non-empty vectors")
    totals = [0.0] * dimension
    for vector in vectors:
        if len(vector) != dimension:
            raise ValueError("mean_unit_vectors requires equal vector dimensions")
        if any(not math.isfinite(component) for component in vector):
            raise ValueError("mean_unit_vectors requires finite components")
        norm = math.sqrt(sum(component * component for component in vector))
        if norm == 0.0:
            raise ValueError("mean_unit_vectors requires non-zero-norm vectors")
        for index, component in enumerate(vector):
            totals[index] += component / norm
    count = len(vectors)
    return tuple(total / count for total in totals)


def subtract_hub(vector: Sequence[float], hub: Sequence[float]) -> tuple[float, ...]:
    """Return `vector - hub`, requiring equal dimensions."""
    if len(vector) != len(hub):
        raise ValueError("vector and hub must have the same dimension")
    return tuple(component - centre for component, centre in zip(vector, hub, strict=True))


def subtract_hub_for_field(
    vector: Sequence[float],
    field: TeachingTextField,
    hub: Sequence[float],
    outcomes_hub: Sequence[float],
) -> tuple[float, ...]:
    """Return `vector` minus the field's hub: the outcomes hub for outcomes, the global hub otherwise."""
    selected = outcomes_hub if field is TeachingTextField.OUTCOMES else hub
    return subtract_hub(vector, selected)
