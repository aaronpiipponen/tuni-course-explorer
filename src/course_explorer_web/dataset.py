"""Resolve the serving database and the opaque identity every cached web read reports."""

import os
from dataclasses import dataclass

from course_explorer.config import DatabaseSettings, load_database_settings_with_identity
from course_explorer.hashing import json_sha256

# The environment variable that carries the supervisor's serving generation into every child it
# starts.
SERVING_GENERATION_ENV = "COURSE_EXPLORER_WEB_GENERATION"


@dataclass(frozen=True)
class ServingDataset:
    """One resolved serving connection paired with its opaque dataset identity."""

    settings: DatabaseSettings
    identity: str


def resolve_serving_dataset() -> ServingDataset:
    """Resolve the serving connection once and derive its opaque identity.

    The identity combines the serving parent's generation value with the selected dataset ID, and
    raw database mode contributes a JSON null selection. A missing or blank generation value raises
    ``ValueError`` so a serving process without the startup handoff fails at its read boundary.
    The returned record carries the resolved database settings alongside the identity, so each
    dataset read uses the connection those settings name.
    """
    generation = os.environ.get(SERVING_GENERATION_ENV, "")
    if not generation:
        raise ValueError(f"{SERVING_GENERATION_ENV} is not set for the serving process")
    settings, dataset_id = load_database_settings_with_identity()
    identity = json_sha256([generation, dataset_id], ensure_ascii=False)
    return ServingDataset(settings=settings, identity=identity)
