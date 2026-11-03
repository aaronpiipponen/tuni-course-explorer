"""The serving artifact family paths and the opened artifact set of one dataset.

The artifact root holds one database namespace, ``serving/db-<encoded database name>``, and one
family directory per academic year under it. A ``current`` symlink in the family names the opened
build, which holds the catalogue and the study fragments. An ``embedding-<configuration hash>``
directory beside it holds the hub pair and the shared stores of one embedding configuration, and
its existence is the only record that the configuration has been built. Every similarity consumer
reads its hub pair from the opened set. The module owns the artifact key and paths, opening the set
and the catalogue body. The caller resolves the site's embedding mode once and passes the resolved
configuration in, so opening reads no switch. A site that serves the embedding features opens its
hub pair, shared store and packed search meta row, and both hubs hold either one finite vector of
the fixed embedding dimension or an empty array for a dataset with no chunk. An empty catalogue hub
corresponds to an absent packed meta row and zero retained search groups, and both hubs of an empty
dataset are empty. A site with the embedding features off opens only the catalogue and the study
fragments, holds no embedding read and opens no embedding directory. The administrative command and
the serving processes both open the set through this module.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from course_explorer import administration
from course_explorer.config import (
    DatabaseSettings,
    EmbeddingRuntimeSettings,
    load_normalization_settings,
)
from course_explorer.constants import COURSE_EMBEDDING_DIMENSION
from course_explorer.db.models import CourseEmbeddingNeighbor, CourseEmbeddingSearchMeta
from course_explorer.db.session import database_context
from course_explorer.embeddings.generation import embedding_configuration_sha256
from course_explorer.embeddings.shared_store import SharedServingStore
from course_explorer.study_structure.fragments import FILE_NAME as STUDY_FRAGMENT_FILE
from course_explorer.study_structure.fragments import StudyFragmentStore

BUILD_COMMAND = "scripts/admin.py serving-artifacts"
_BUILD_GUIDANCE = f"run `{BUILD_COMMAND}` to build the serving artifacts"

CATALOGUE_FILE = "catalogue.json"
HUB_PAIR_FILE = "hub-pair.json"
HUB_CATALOGUE_FILE = "embedding-hub.json"
HUB_OUTCOMES_FILE = "embedding-outcomes-hub.json"
EMBEDDING_DIRECTORY_PREFIX = "embedding-"


class ServingArtifactKey(BaseModel):
    """The stable key of one serving artifact family."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    database_name: str
    academic_year_start: int
    key: str


class ServingHubPair(BaseModel):
    """The two authoritative hub files of one embedding directory."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    catalogue_file: str
    outcomes_file: str


def serving_artifact_key(
    database_name: str,
    academic_year_start: int,
) -> ServingArtifactKey:
    """Return the artifact key of one database and academic year.

    One family belongs to one dataset and year, so a site keeps its family across an embedding
    mode switch. The embedding configuration identity names that family's embedding directory.
    """
    digest = hashlib.sha256(f"{database_name}:{academic_year_start}".encode()).hexdigest()[:24]
    return ServingArtifactKey(
        database_name=database_name,
        academic_year_start=academic_year_start,
        key=digest,
    )


def embedding_directory(family: Path, configuration_hash: str) -> Path:
    """Return the embedding artifact directory of one configuration under an artifact family.

    The directory holds the hub pair, the shared centroid and chunk stores, and its existence is
    the only record that this configuration has been built for the family.
    """
    return family / f"{EMBEDDING_DIRECTORY_PREFIX}{configuration_hash}"


def configured_embedding_directory(family: Path, embedding: EmbeddingRuntimeSettings) -> Path:
    """Return the embedding directory the configured embedding settings build under one family.

    The directory name includes the configuration hash, which the build computes as well, so
    opening, building, reading and pruning a family all name the same directory.
    """
    return embedding_directory(family, embedding_configuration_sha256(embedding))


def serving_database_root(admin_state_root: Path, database_name: str) -> Path:
    """Return the artifact namespace of one serving database under the configured state root.

    The standard URL component encoder keeps every accepted database name in one filesystem
    component. The ``db-`` prefix keeps an encoded name from colliding with a bare ``serving``
    child and makes the namespace visibly the database owner.
    """
    component = urllib.parse.quote(database_name, safe="")
    return admin_state_root / "serving" / f"db-{component}"


def serving_artifact_root(admin_state_root: Path, key: ServingArtifactKey) -> Path:
    """Return the artifact family directory of one key under its database namespace."""
    return serving_database_root(admin_state_root, key.database_name) / key.key


def serving_key(database_settings: DatabaseSettings) -> ServingArtifactKey:
    """Return the artifact key the serving database and the configured academic year resolve."""
    return serving_artifact_key(
        database_settings.postgres_db,
        load_normalization_settings().current_academic_year_start,
    )


def catalogue_body(artifact: bytes, identity: str) -> bytes:
    """Append one serving identity to the plain catalogue artifact in the response field order."""
    if not artifact.endswith(b"}"):
        raise ValueError("catalogue artifact does not hold a JSON object")
    return artifact[:-1] + b',"dataset_identity":' + json.dumps(identity).encode() + b"}"


def _read_hub(path: Path) -> tuple[float, ...]:
    """Read one hub file as one empty tuple for an empty JSON array or one finite fixed vector."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"serving hub file {path} must hold a JSON array; {_BUILD_GUIDANCE}")
    if not payload:
        return ()
    values = tuple(payload)
    if len(values) != COURSE_EMBEDDING_DIMENSION:
        raise ValueError(
            f"serving hub file {path} must hold exactly {COURSE_EMBEDDING_DIMENSION} components; "
            f"{_BUILD_GUIDANCE}"
        )
    try:
        components = tuple(float(value) for value in values)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"serving hub file {path} must hold numeric components; {_BUILD_GUIDANCE}"
        ) from exc
    if any(not math.isfinite(component) for component in components):
        raise ValueError(f"serving hub file {path} must hold finite components; {_BUILD_GUIDANCE}")
    return components


@dataclass(frozen=True)
class ServingSearchMeta:
    """The packed search row facts the serving reads consume.

    ``group_count`` is zero for an empty dataset, whose build writes no packed meta row.
    """

    group_count: int


@dataclass(frozen=True)
class ServingEmbeddings:
    """The opened embedding artifacts of one site that serves the embedding features.

    ``hubs`` holds the catalogue hub and the outcomes hub, each either one vector of the fixed
    embedding dimension or an empty tuple for an empty dataset, and ``shared_store`` holds the
    centroid and chunk stores. Every embedding read of the opened set reads them.
    """

    hubs: tuple[tuple[float, ...], tuple[float, ...]]
    shared_store: SharedServingStore
    search: ServingSearchMeta


@dataclass(frozen=True)
class ServingArtifacts:
    """One opened build with its embedding directory reads.

    ``root`` is the current build directory, which holds the catalogue and the study fragments.
    ``embeddings`` is ``None`` on a site with the embedding features off. Such a site holds no hub
    pair, shared store or packed search row, and opening reads none of them. An embeddings-on site
    that holds an empty dataset opens empty hubs and zero retained search groups. The catalogue body
    is read from ``root`` on every call, and the embedding reads are those the opening made from the
    family's embedding directory, so a ``current`` switch never changes an opened set.
    """

    root: Path
    study_fragments: StudyFragmentStore
    embeddings: ServingEmbeddings | None

    def embedding_reads(self) -> ServingEmbeddings:
        """Return the embedding reads of this set, or raise the build guidance.

        A route that reads them has applied its site's embedding switch, so an absent read means
        the opened set and the configured switch disagree.
        """
        if self.embeddings is None:
            raise ValueError(
                "the embedding features are off on this site; enable WEB_EMBEDDINGS_ENABLED "
                f"and {_BUILD_GUIDANCE}"
            )
        return self.embeddings

    @classmethod
    def open(
        cls,
        database_settings: DatabaseSettings,
        *,
        embedding: EmbeddingRuntimeSettings | None,
    ) -> ServingArtifacts:
        """Open the ``current`` build and the configured embedding directory of the served dataset.

        ``embedding`` is the resolved embedding configuration on a site that serves the embedding
        features and ``None`` on a site with them off, so the entry point decides the mode once and
        this opening reads no switch. A missing artifact family, a missing current target, a missing
        catalogue or study fragment file, a missing embedding directory for the configuration, a
        missing hub pair file or hub file, and a missing packed search meta row beside a nonempty
        catalogue hub raise ``ValueError`` naming the build command. A dataset that holds embedded
        chunks and no stored neighbour row raises that error as well. A hub file that is not a JSON
        array, or whose nonempty components are not exactly the fixed embedding dimension, are not
        numeric, or are not finite, also raises that error. An empty catalogue hub with no packed
        search meta row opens the zero retained group count of an empty dataset, which holds no
        neighbour and serves with the embedding features on. The meta row and the neighbour presence
        are read once when the set opens, never per request.
        """
        repository = administration.repository_root()
        key = serving_key(database_settings)
        family = serving_artifact_root(repository / database_settings.admin_state_root, key)
        current = family / "current"
        if not current.exists():
            raise ValueError(f"serving artifacts are missing at {family}; {_BUILD_GUIDANCE}")
        build = Path(os.path.realpath(current))
        embeddings: ServingEmbeddings | None = None
        if embedding is not None:
            embedding_root = configured_embedding_directory(family, embedding)
            pair_path = embedding_root / HUB_PAIR_FILE
            if not pair_path.is_file():
                raise ValueError(
                    f"serving embedding artifacts are missing at {embedding_root}; "
                    f"{_BUILD_GUIDANCE}"
                )
            pair = ServingHubPair.model_validate_json(pair_path.read_text(encoding="utf-8"))
            catalogue = embedding_root / pair.catalogue_file
            outcomes = embedding_root / pair.outcomes_file
            for path in (catalogue, outcomes):
                if not path.is_file():
                    raise ValueError(f"serving hub file {path} is missing; {_BUILD_GUIDANCE}")
            hubs = (_read_hub(catalogue), _read_hub(outcomes))
            with database_context(database_settings) as factory, factory() as session:
                try:
                    meta_row = session.get(CourseEmbeddingSearchMeta, True)
                except SQLAlchemyError as exc:
                    raise ValueError(
                        f"packed search meta table is missing or unreadable; {_BUILD_GUIDANCE}"
                    ) from exc
                if (
                    meta_row is not None
                    and session.scalar(select(CourseEmbeddingNeighbor.query_chunk_id).limit(1))
                    is None
                ):
                    raise ValueError(f"course embedding neighbours are absent; {_BUILD_GUIDANCE}")
            if meta_row is None:
                if hubs[0]:
                    raise ValueError(f"packed search meta row is missing; {_BUILD_GUIDANCE}")
                group_count = 0
            else:
                group_count = meta_row.group_count
            embeddings = ServingEmbeddings(
                hubs=hubs,
                shared_store=SharedServingStore.open(
                    embedding_root,
                    dataset_key=key.key,
                    academic_year_start=key.academic_year_start,
                ),
                search=ServingSearchMeta(group_count=group_count),
            )
        catalogue_artifact = build / CATALOGUE_FILE
        if not catalogue_artifact.is_file():
            raise ValueError(
                f"serving catalogue artifact is missing at {catalogue_artifact}; {_BUILD_GUIDANCE}"
            )
        fragment_path = build / STUDY_FRAGMENT_FILE
        if not fragment_path.is_file():
            raise ValueError(
                f"study fragment file is missing at {fragment_path}; {_BUILD_GUIDANCE}"
            )
        return cls(
            root=build,
            study_fragments=StudyFragmentStore.open(
                fragment_path,
                dataset_key=key.key,
                academic_year_start=key.academic_year_start,
            ),
            embeddings=embeddings,
        )

    def catalogue_body(self, identity: str) -> bytes:
        """Return the plain catalogue body with one serving identity appended.

        The caller retains the returned body. This module keeps no copy, so one serving process
        holds one plain catalogue body.
        """
        return catalogue_body((self.root / CATALOGUE_FILE).read_bytes(), identity)
