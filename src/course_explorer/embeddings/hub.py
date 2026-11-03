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

import numpy

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


def subtract_hub_rows(
    rows: Sequence[Sequence[float]],
    fields: Sequence[TeachingTextField],
    hub: Sequence[float],
    outcomes_hub: Sequence[float],
) -> numpy.ndarray:
    """Return the field-specific hub-subtracted rows as one float64 array.

    Outcomes rows subtract `outcomes_hub` and every other row subtracts `hub`. The two sequences
    must have the same length, the hub pair must share the row dimension, and a mismatch raises
    `ValueError`.
    """
    if len(rows) != len(fields):
        raise ValueError("rows and fields must have the same length")
    if len(hub) != len(outcomes_hub):
        raise ValueError("hub and outcomes hub must have the same dimension")
    matrix = numpy.asarray(rows, dtype=numpy.float64)
    if matrix.size == 0:
        return numpy.empty((0, len(hub)), dtype=numpy.float64)
    if matrix.ndim != 2 or matrix.shape[1] != len(hub):
        raise ValueError("rows and hub must have the same dimension")
    centres = numpy.asarray(
        [outcomes_hub if field is TeachingTextField.OUTCOMES else hub for field in fields],
        dtype=numpy.float64,
    )
    return matrix - centres


def subtract_hub(vector: Sequence[float], hub: Sequence[float]) -> tuple[float, ...]:
    """Return `vector - hub` component by component."""
    return tuple(value - centre for value, centre in zip(vector, hub, strict=True))


def subtract_hub_for_field(
    vector: Sequence[float],
    field: TeachingTextField,
    hub: Sequence[float],
    outcomes_hub: Sequence[float],
) -> tuple[float, ...]:
    """Return `vector` minus the field's hub: the outcomes hub for outcomes, the global hub otherwise."""
    return subtract_hub(vector, outcomes_hub if field is TeachingTextField.OUTCOMES else hub)
