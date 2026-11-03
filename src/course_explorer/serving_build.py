"""Build, switch and prune the serving artifact family of one dataset.

One build writes the catalogue artifact and the study fragments into one build directory created
for this build and switches the family's ``current`` symlink. A site that serves the embedding
features also writes the authoritative hub files and the shared centroid and chunk stores into the
family's ``embedding-<configuration hash>`` directory, replaces the centroid, neighbour and packed
search tables in one transaction, and fails before that transaction when any current chunk vector is
missing or stale. The existence of that directory is the record that the configuration has been
built, so a site with the embedding features off writes the catalogue artifact and the study
fragments alone, replaces no table and leaves every embedding directory untouched. It resolves the
selected dataset or the configured raw database and the database settings the build reads, and the
entry point resolves the embedding mode and passes the configured embedding settings in for the
build and the prune alike. A pre-commit failure restores the previous target and embedding
directory. A post-commit error leaves the committed state in place. Pruning collects owned obsolete
builds, embedding directories of other configurations and temporary outputs after a restart. A
prune on a site with the embedding features off keeps every embedding directory. The opened
artifact set is read-only and belongs to `serving_artifacts`, and this module creates and removes
its files.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, TypeAdapter

from course_explorer import administration
from course_explorer.config import (
    DatabaseSettings,
    EmbeddingRuntimeSettings,
    load_database_settings,
    load_raw_database_settings,
    load_search_settings,
)
from course_explorer.curriculum_repository import CurriculumRepository
from course_explorer.datasets import DatasetDatabaseName, read_dataset_receipt
from course_explorer.db.session import database_context, session_scope
from course_explorer.embeddings import neighbors
from course_explorer.embeddings.centroid_repository import CourseCentroidRepository
from course_explorer.embeddings.centroids import compute_course_centroids
from course_explorer.embeddings.generation import embedding_configuration_sha256
from course_explorer.embeddings.hub_files import (
    compute_embedding_hubs,
    read_current_chunk_vectors,
    write_hub_file,
)
from course_explorer.embeddings.search_blocks import CourseEmbeddingSearchRepository
from course_explorer.embeddings.shared_store import (
    CENTROIDS_FILE,
    CHUNKS_FILE,
    SharedServingStore,
)
from course_explorer.search.lookup_commands import run_catalogue_command
from course_explorer.search.projection import build_lookup_projection
from course_explorer.serving_artifacts import (
    CATALOGUE_FILE,
    HUB_CATALOGUE_FILE,
    HUB_OUTCOMES_FILE,
    HUB_PAIR_FILE,
    ServingHubPair,
    configured_embedding_directory,
    embedding_directory,
    serving_artifact_root,
    serving_database_root,
    serving_key,
)
from course_explorer.study_structure.fragments import FILE_NAME as STUDY_FRAGMENT_FILE
from course_explorer.study_structure.fragments import StudyFragmentStore
from course_explorer.study_structure.service import StudyStructureService

BUILD_COMMAND = "scripts/admin.py serving-artifacts"
_BUILD_GUIDANCE = f"run `{BUILD_COMMAND}` to build the serving artifacts"

# The builder names one family by a 24-hex key, one build by its UTC creation stamp and one
# embedding directory by its 64-hex configuration identity. Only these owned names, their staging
# and replaced copies, the current symlink and owned temporary files are removable. Every other
# entry is left in place.
_FAMILY_PATTERN = re.compile(r"^[0-9a-f]{24}$")
_BUILD_PATTERN = re.compile(r"^\d{8}T\d{6}\d{6}Z$")
_EMBEDDING_PATTERN = re.compile(r"^embedding-[0-9a-f]{64}(?:\.tmp|\.previous)?$")


class ServingArtifactsReport(BaseModel):
    """The serving-artifact files and counts one build produced.

    Paths inside the repository are relative to its root and paths outside it are absolute.
    ``catalogue_artifact_path`` and ``study_fragment_path`` name files in the build directory.
    ``hub_pair_path`` and the other embedding artifact paths name files in the family's embedding
    directory. ``catalogue_path`` and ``outcomes_path`` name the two authoritative hub files the
    pair lists. A build with the embedding features off writes no embedding file or table, so every
    embedding path and count is ``None`` and ``embeddings_enabled`` is false. An embeddings-on build
    of an empty dataset writes both hub files as empty arrays and no derived row, so its embedding
    paths are present and its embedding counts are zero.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    embeddings_enabled: bool
    catalogue_artifact_path: str
    study_fragment_path: str
    study_fragment_roots: int
    study_fragment_projectable: int
    study_fragment_unavailable: int
    study_fragment_selection_required: int
    study_fragment_bytes: int
    study_fragment_build_wall_seconds: float
    study_fragment_build_core_seconds: float
    catalogue_path: str | None = None
    outcomes_path: str | None = None
    hub_pair_path: str | None = None
    shared_centroid_path: str | None = None
    shared_chunk_path: str | None = None
    search_group_count: int | None = None
    search_block_count: int | None = None
    chunk_count: int | None = None
    outcomes_chunk_count: int | None = None
    centroid_count: int | None = None
    neighbor_count: int | None = None


class ServingArtifactsPruneReport(BaseModel):
    """The retained build and the owned outputs one prune removed.

    ``family_path`` and every ``removed`` entry share one base: they are repository-relative inside
    the repository and absolute outside it. ``build_id`` is the active family's current build
    identity, or ``None`` when that family has no valid current build and only unreferenced failed
    outputs were collected.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    family_path: str
    build_id: str | None
    removed: tuple[str, ...]


def build_catalogue_artifact(report: BaseModel) -> bytes:
    """Serialize one catalogue report without the serving identity into the artifact bytes."""
    return json.dumps(
        report.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":")
    ).encode()


def _new_build_id() -> str:
    """Return this build's directory identity, ordered by creation time."""
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def write_hub_pair(
    build_root: Path, catalogue: tuple[float, ...], outcomes: tuple[float, ...]
) -> ServingHubPair:
    """Write the two authoritative hub files and their pair into one directory."""
    write_hub_file(build_root / HUB_CATALOGUE_FILE, catalogue)
    write_hub_file(build_root / HUB_OUTCOMES_FILE, outcomes)
    pair = ServingHubPair(
        catalogue_file=HUB_CATALOGUE_FILE,
        outcomes_file=HUB_OUTCOMES_FILE,
    )
    (build_root / HUB_PAIR_FILE).write_text(pair.model_dump_json() + "\n", encoding="utf-8")
    return pair


def publish_current(family: Path, build_root: Path) -> None:
    """Point the family's ``current`` symlink at one completed build through ``os.replace``."""
    current = family / "current"
    temporary = family / "current.tmp"
    temporary.unlink(missing_ok=True)
    os.symlink(build_root.name, temporary)
    os.replace(temporary, current)


def create_build_directory(family: Path) -> Path:
    """Create and return one empty build directory under an artifact family."""
    build_root = family / _new_build_id()
    build_root.mkdir(parents=True, exist_ok=False)
    return build_root


def embedding_directories(final: Path) -> tuple[Path, Path, Path]:
    """Return the embedding directory, its staging directory and its replaced copy.

    The staging directory receives every embedding file of one build, and the replaced copy keeps
    the directory an in-transaction replacement moved aside until the transaction commits.
    """
    return final, final.with_name(f"{final.name}.tmp"), final.with_name(f"{final.name}.previous")


def publish_embedding_directory(final: Path, staging: Path, replaced: Path) -> None:
    """Move one staged embedding directory into place and keep the replaced copy aside."""
    if final.exists():
        os.replace(final, replaced)
    os.replace(staging, final)


def _restore_embedding_directory(
    final: Path, staging: Path, replaced: Path, *, published: bool
) -> None:
    """Restore the configured embedding directory and remove the failed build's staged one.

    A replaced copy is always the previous configured directory, so it is moved back whenever it
    exists, including when the staged directory failed to replace it and the configured path is
    therefore empty. A published directory with no replaced copy belongs to a failed first build of
    the configuration and is removed, so the directory never records a build whose tables rolled
    back. A remaining staging directory is removed.
    """
    if replaced.exists():
        if final.exists():
            _remove_owned_entry(final)
        os.replace(replaced, final)
    elif published and final.exists():
        _remove_owned_entry(final)
    if staging.exists():
        _remove_owned_entry(staging)


def _report_path(path: Path, repository: Path) -> str:
    """Return one resolved artifact path repository-relative inside it and absolute outside it."""
    resolved = path.resolve()
    root = repository.resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        return resolved.as_posix()


def _current_build(family: Path) -> Path | None:
    """Return the build directory the family's ``current`` symlink names, or ``None``."""
    current = family / "current"
    if not current.exists():
        return None
    build = Path(os.path.realpath(current))
    if not build.is_dir() or build.parent != Path(os.path.realpath(family)):
        return None
    return build


def _remove_owned_entry(path: Path) -> Path:
    """Remove one owned directory or file and return it for the common report base."""
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)
    return path


def _prune_owned_entries(
    family: Path,
    *,
    keep_build: Path | None,
    keep_current: bool,
    keep_embedding: str | None,
    keep_all_embeddings: bool,
) -> list[Path]:
    """Remove owned outputs of one family while preserving the named current outputs.

    ``keep_current`` keeps the ``current`` symlink and ``keep_embedding`` keeps the embedding
    directory name of the configured embedding identity. ``keep_all_embeddings`` keeps every
    embedding directory and its staging and replaced copies, for a site with the embedding features
    off. ``keep_build`` keeps one named build directory and removes the temporary files inside it.
    Every other owned build directory, the ``current.tmp`` link, the ``current`` symlink when it is
    not kept, and every other embedding directory with its staging and replaced copies are removed.
    Each removed path is returned so the caller can render every removal through one report base.
    """
    removed: list[Path] = []
    for entry in sorted(family.iterdir()):
        if entry.name == "current":
            if not keep_current:
                entry.unlink(missing_ok=True)
                removed.append(entry)
            continue
        if keep_build is not None and entry.name == keep_build.name:
            continue
        if entry.name == keep_embedding:
            continue
        if keep_all_embeddings and _EMBEDDING_PATTERN.fullmatch(entry.name):
            continue
        if entry.name == "current.tmp":
            removed.append(_remove_owned_entry(entry))
        elif (
            entry.is_dir()
            and not entry.is_symlink()
            and (_BUILD_PATTERN.fullmatch(entry.name) or _EMBEDDING_PATTERN.fullmatch(entry.name))
        ):
            removed.append(_remove_owned_entry(entry))
    if keep_build is not None:
        for temporary in sorted(keep_build.rglob("*.tmp")):
            if temporary.is_file() or temporary.is_symlink():
                removed.append(_remove_owned_entry(temporary))
    return removed


def _restore_current(family: Path, previous: str | None) -> None:
    """Restore the family's ``current`` symlink to a previous build name, or remove it."""
    current = family / "current"
    temporary = family / "current.tmp"
    temporary.unlink(missing_ok=True)
    if previous is None:
        current.unlink(missing_ok=True)
        return
    os.symlink(previous, temporary)
    os.replace(temporary, current)


def build_serving_artifacts(
    settings: DatabaseSettings, *, embedding: EmbeddingRuntimeSettings | None
) -> ServingArtifactsReport:
    """Build one dataset's serving artifacts for the site's embedding mode and switch ``current``.

    ``embedding`` is the resolved embedding configuration on a site that serves the embedding
    features and ``None`` on a site with them off, so the entry point decides the mode once and this
    build reads no switch. The catalogue artifact and the study fragments are written in one build
    directory created for this build. The study-fragment and shared stores open before the
    transaction. The table replacement, the embedding directory replacement and ``current`` switch
    commit as one unit. A site with the embedding features off writes the catalogue artifact and the
    study fragments alone, reads no stored vector, replaces no embedding table and leaves every
    embedding directory as it is. A site with them on writes every embedding artifact into the
    family's embedding staging directory and fails before any table change when a current chunk
    vector is missing or stale, naming the chunk. Before that commit, a failure restores the
    previous ``current`` target and embedding directory, rolls the tables back and removes the
    incomplete outputs. After the commit, an error from the remaining outer database context,
    including engine disposal, propagates as raised and leaves the committed tables, ``current``
    target, embedding directory and completed build directory in place. A pre-commit cleanup failure
    is added as a note to that exception and leaves the owned incomplete directory for ``--prune``.
    A replaced embedding directory that cannot be removed after the commit raises and is left for
    ``--prune``. The build never calls a running worker. A selected dataset change needs the
    supervisor restart.
    """
    repository = administration.repository_root()
    key = serving_key(settings)
    family = serving_artifact_root(repository / settings.admin_state_root, key)
    family.mkdir(parents=True, exist_ok=True)
    current = family / "current"
    previous_build = Path(os.path.realpath(current)).name if current.exists() else None
    build_root = create_build_directory(family)
    # The three embedding paths and the configuration identity are set together when the site
    # serves the embedding features, and each stays ``None`` when it does not.
    configuration_hash: str | None = None
    embedding_root: Path | None = None
    embedding_staging: Path | None = None
    embedding_replaced: Path | None = None
    embedding_published = False
    if embedding is not None:
        configuration_hash = embedding_configuration_sha256(embedding)
        embedding_root, embedding_staging, embedding_replaced = embedding_directories(
            embedding_directory(family, configuration_hash)
        )
        # An interrupted build can leave its own staging or replaced copy behind.
        for leftover in (embedding_staging, embedding_replaced):
            if leftover.exists():
                _remove_owned_entry(leftover)
    # Every reported path is resolved before any table commit, so constructing the report cannot
    # fail after the transaction succeeds.
    catalogue_artifact_path = _report_path(build_root / CATALOGUE_FILE, repository)
    study_fragment_path = _report_path(build_root / STUDY_FRAGMENT_FILE, repository)
    committed = False
    try:
        with database_context(settings) as factory:
            if embedding is not None:
                current_chunks = read_current_chunk_vectors(factory, embedding)
                hubs = compute_embedding_hubs(current_chunks)
                centroids = compute_course_centroids(
                    current_chunks.chunks,
                    current_chunks.vectors,
                    catalogue_hub=hubs.catalogue,
                    outcomes_hub=hubs.outcomes,
                )
                write_hub_pair(embedding_staging, hubs.catalogue, hubs.outcomes)
                SharedServingStore.build(
                    embedding_staging,
                    dataset_key=key.key,
                    academic_year_start=key.academic_year_start,
                    centroids=centroids,
                    chunks=current_chunks.stored,
                )

            fragment_service = StudyStructureService(
                CurriculumRepository(factory), academic_year_start=key.academic_year_start
            )
            fragment_report = StudyFragmentStore.build(
                fragment_service,
                CurriculumRepository(factory).list_module_group_ids(),
                dataset_key=key.key,
                academic_year_start=key.academic_year_start,
                path=build_root / STUDY_FRAGMENT_FILE,
            )
            catalogue_projection = build_lookup_projection(CurriculumRepository(factory))
            catalogue_report = run_catalogue_command(
                database_settings=settings,
                academic_year_start=key.academic_year_start,
                projection=catalogue_projection,
                session_factory=factory,
            )
            (build_root / CATALOGUE_FILE).write_bytes(build_catalogue_artifact(catalogue_report))
            # Open the fragment store so a malformed build fails before the transaction.
            StudyFragmentStore.open(
                build_root / STUDY_FRAGMENT_FILE,
                dataset_key=key.key,
                academic_year_start=key.academic_year_start,
            )
            # The ten mode-independent report fields are built once, and the branch for a site
            # that serves the embedding features adds the embedding artifact paths and counts.
            report_fields: dict[str, object] = {
                "embeddings_enabled": embedding is not None,
                "catalogue_artifact_path": catalogue_artifact_path,
                "study_fragment_path": study_fragment_path,
                "study_fragment_roots": fragment_report.roots,
                "study_fragment_projectable": fragment_report.projectable,
                "study_fragment_unavailable": fragment_report.unavailable,
                "study_fragment_selection_required": fragment_report.selection_required,
                "study_fragment_bytes": fragment_report.bytes,
                "study_fragment_build_wall_seconds": fragment_report.build_wall_seconds,
                "study_fragment_build_core_seconds": fragment_report.build_core_seconds,
            }
            with session_scope(factory) as session:
                if embedding is None:
                    report = ServingArtifactsReport(**report_fields)
                else:
                    search_settings = load_search_settings()
                    CourseCentroidRepository(factory).replace_all_in(
                        session,
                        centroids,
                        embedding_configuration_hash=configuration_hash,
                    )
                    neighbor_count = neighbors.replace_all(
                        session,
                        embedding_configuration_hash=configuration_hash,
                        rows_per_chunk=search_settings.search_neighbor_table_rows_per_chunk,
                        hnsw_iterative_scan=search_settings.search_hnsw_iterative_scan,
                        hnsw_max_scan_tuples=search_settings.search_hnsw_max_scan_tuples,
                    )
                    search_group_count, search_block_count = CourseEmbeddingSearchRepository(
                        session
                    ).replace_all(
                        embedding_configuration_hash=configuration_hash,
                        hub=hubs.catalogue,
                    )
                    publish_embedding_directory(
                        embedding_root, embedding_staging, embedding_replaced
                    )
                    embedding_published = True
                    report = ServingArtifactsReport(
                        **report_fields,
                        catalogue_path=_report_path(
                            embedding_root / HUB_CATALOGUE_FILE, repository
                        ),
                        outcomes_path=_report_path(embedding_root / HUB_OUTCOMES_FILE, repository),
                        hub_pair_path=_report_path(embedding_root / HUB_PAIR_FILE, repository),
                        shared_centroid_path=_report_path(
                            embedding_root / CENTROIDS_FILE, repository
                        ),
                        shared_chunk_path=_report_path(embedding_root / CHUNKS_FILE, repository),
                        search_group_count=search_group_count,
                        search_block_count=search_block_count,
                        chunk_count=hubs.chunk_count,
                        outcomes_chunk_count=hubs.outcomes_chunk_count,
                        centroid_count=len(centroids),
                        neighbor_count=neighbor_count,
                    )
                publish_current(family, build_root)
            # The inner scope commits exactly when it returns. Mark that before the outer database
            # context disposes its engine, so a disposal error after the commit never rewinds the
            # target or removes the completed outputs.
            committed = True
            if embedding_replaced is not None and embedding_replaced.exists():
                _remove_owned_entry(embedding_replaced)
        return report
    except BaseException as error:
        if not committed:
            try:
                _restore_current(family, previous_build)
            except OSError as cleanup_error:
                error.add_note(f"failed to restore serving current: {cleanup_error}")
            if embedding is not None:
                try:
                    _restore_embedding_directory(
                        embedding_root,
                        embedding_staging,
                        embedding_replaced,
                        published=embedding_published,
                    )
                except OSError as cleanup_error:
                    error.add_note(
                        f"failed to restore serving embedding directory {embedding_root}: "
                        f"{cleanup_error}"
                    )
            if build_root.exists():
                try:
                    shutil.rmtree(build_root)
                except OSError as cleanup_error:
                    error.add_note(
                        f"failed to remove incomplete serving artifact build {build_root}: "
                        f"{cleanup_error}"
                    )
        raise


def prune_serving_artifacts(
    settings: DatabaseSettings, *, embedding: EmbeddingRuntimeSettings | None
) -> ServingArtifactsPruneReport:
    """Prune one dataset's artifact namespace without building or replacing tables.

    ``embedding`` is the resolved embedding configuration on a site that serves the embedding
    features and ``None`` on a site with them off, so the entry point decides the mode once and
    this prune reads no switch or embedding setting. With the features on, the configured
    configuration keeps its embedding directory, so enabling them reuses the built directory. With
    them off every owned embedding directory is kept, because an embeddings-off site resolves no
    embedding configuration and changes no embedding state. When the active key has a valid current
    build, every obsolete build, the other configurations' embedding directories with their staging
    and replaced copies, and other year families under the same database namespace are collected.
    With the features off those embedding directories are kept, so an older year family remains
    with its embedding directories. When it has no valid current build, each family keeps its own
    valid current build and only unreferenced failed outputs are collected. Unknown names and other
    database namespaces are never touched. Every removed entry and the retained family path are
    rendered through the one report base: repository-relative inside the repository and absolute
    outside it.
    """
    repository = administration.repository_root()
    key = serving_key(settings)
    database_root = serving_database_root(repository / settings.admin_state_root, key.database_name)
    active_family = database_root / key.key
    keep_embedding = (
        None if embedding is None else configured_embedding_directory(active_family, embedding).name
    )
    keep_all_embeddings = embedding is None
    families = (
        sorted(
            entry
            for entry in database_root.iterdir()
            if entry.is_dir() and not entry.is_symlink() and _FAMILY_PATTERN.fullmatch(entry.name)
        )
        if database_root.is_dir()
        else []
    )
    active_build = _current_build(active_family)
    removed: list[Path] = []
    if active_build is not None:
        for family in families:
            if family == active_family:
                removed.extend(
                    _prune_owned_entries(
                        family,
                        keep_build=active_build,
                        keep_current=True,
                        keep_embedding=keep_embedding,
                        keep_all_embeddings=keep_all_embeddings,
                    )
                )
            else:
                removed.extend(
                    _prune_owned_entries(
                        family,
                        keep_build=None,
                        keep_current=False,
                        keep_embedding=None,
                        keep_all_embeddings=keep_all_embeddings,
                    )
                )
                if family.is_dir() and not any(family.iterdir()):
                    family.rmdir()
    else:
        for family in families:
            build = _current_build(family)
            removed.extend(
                _prune_owned_entries(
                    family,
                    keep_build=build,
                    keep_current=build is not None,
                    keep_embedding=keep_embedding,
                    keep_all_embeddings=keep_all_embeddings,
                )
            )
    return ServingArtifactsPruneReport(
        family_path=_report_path(active_family, repository),
        build_id=active_build.name if active_build is not None else None,
        removed=tuple(sorted(_report_path(path, repository) for path in removed)),
    )


_DATABASE_NAME_ADAPTER = TypeAdapter(DatasetDatabaseName)


def _require_artifact_namespace(admin_state_root: Path, database_name: str) -> Path:
    """Return the owned artifact namespace of one database after refusing redirected paths."""
    name = _DATABASE_NAME_ADAPTER.validate_python(database_name)
    if admin_state_root.is_symlink() or (
        admin_state_root.exists() and not admin_state_root.is_dir()
    ):
        raise ValueError("serving artifact state root must be a regular directory")
    serving = admin_state_root / "serving"
    if serving.is_symlink() or (serving.exists() and not serving.is_dir()):
        raise ValueError("serving artifact namespace must be a regular directory")
    namespace = serving_database_root(admin_state_root, name)
    if namespace.is_symlink():
        raise ValueError("serving artifact namespace must not be a symlink")
    if namespace.exists() and not namespace.is_dir():
        raise ValueError("serving artifact namespace must be a regular directory")
    return namespace


def require_removable_serving_database_artifacts(
    admin_state_root: Path, database_name: str
) -> Path:
    """Validate and return one database's owned artifact namespace before a deletion.

    The namespace is derived solely through :func:`serving_database_root` from the validated
    database name. A symlinked state root, ``serving`` directory or database namespace and a
    non-directory namespace each raise. A missing namespace is a valid absent resource.
    """
    return _require_artifact_namespace(admin_state_root, database_name)


def remove_serving_database_artifacts(namespace: Path) -> None:
    """Remove one validated database's whole artifact namespace across academic years.

    The namespace comes from :func:`require_removable_serving_database_artifacts`, so no receipt
    path or arbitrary filesystem path reaches removal. The internal ``current`` symlinks are not
    followed. A missing namespace succeeds.
    """
    if not namespace.exists():
        return
    shutil.rmtree(namespace)


def dataset_settings(dataset_id: str | None) -> DatabaseSettings:
    """Resolve one named dataset's database settings, or the Selected database when unnamed.

    A named dataset resolves its receipt under the configured state root. The unnamed default is
    the Selected role, which is the configured raw database in bootstrap.
    """
    if dataset_id is None:
        return load_database_settings(role="selected")
    settings = load_raw_database_settings()
    receipt = read_dataset_receipt(
        administration.repository_root() / settings.admin_state_root, dataset_id
    )
    return settings.model_copy(update={"postgres_db": receipt.database_name})
