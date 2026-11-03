"""Hub-centred unit-vector arithmetic shared by centroid preparation and recommendation scoring."""

from __future__ import annotations

from collections.abc import Sequence

import numpy

from course_explorer.embeddings.hub import subtract_hub_rows
from course_explorer.enums import TeachingTextField


def unit_row(vector: numpy.ndarray) -> numpy.ndarray:
    """Return one vector's unit form, raising on a zero-length centred vector."""
    norm = float(numpy.sqrt((vector * vector).sum()))
    if norm == 0.0:
        raise ValueError("cannot compare a zero-length centred embedding")
    return vector / norm


def unit_rows(
    embeddings: Sequence[Sequence[float]],
    fields: Sequence[TeachingTextField],
    hub: Sequence[float],
    outcomes_hub: Sequence[float],
) -> numpy.ndarray:
    """Return one float64 unit row per field-specific hub-centred embedding.

    `embeddings` and `fields` must have the same length, and a zero-length centred row raises
    `ValueError`. The row order follows the supplied embeddings.
    """
    if len(embeddings) != len(fields):
        raise ValueError("embeddings and fields must have the same length")
    if not embeddings:
        return numpy.empty((0, len(hub)), dtype=numpy.float64)
    rows = subtract_hub_rows(embeddings, fields, hub, outcomes_hub)
    norms = numpy.sqrt((rows * rows).sum(axis=1))
    if bool(numpy.any(norms == 0.0)):
        raise ValueError("cannot compare a zero-length centred embedding")
    return rows / norms[:, None]
