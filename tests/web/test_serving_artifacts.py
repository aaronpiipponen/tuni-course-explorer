"""Contract proof for the real serving-artifact lifecycle and its one build guidance.

The test prepares the authored fictional fixture through the product loader, then drives the real
artifact builder against the guarded disposable database. Before it loads the fixture it builds
and opens the empty migrated database and asserts the empty hubs, the fixed-dimension empty shared
store, the empty catalogue and the absent packed meta row. It then changes stored input vectors so
the derived tables and both embedding hub files have observably different content, injects one
failure at the real transaction commit boundary and one after the commit at engine disposal, and
asserts the actual tables, ``current`` target, embedding directory and both hub byte sets. It then
makes every stored vector pending and proves the embeddings-off build writes the catalogue and the
study fragments alone and leaves the embedding directory and the tables as they were, that
switching the features on reuses that directory, and that a changed embedding configuration
refuses until a build. It also uses the real filesystem namespace for the owned prune contract.
"""

from __future__ import annotations

import json
import math
import os
import shutil
from contextlib import contextmanager
from pathlib import Path

import pytest
from sqlalchemy import delete, event, func, select

from course_explorer import serving_artifacts, serving_build
from course_explorer.config import (
    embedding_configuration_for_site,
    load_database_settings,
    load_embedding_runtime_settings,
    load_normalization_settings,
    load_web_settings,
)
from course_explorer.constants import COURSE_EMBEDDING_DIMENSION
from course_explorer.db import session as database_session
from course_explorer.db.models import (
    CourseEmbeddingCentroid,
    CourseEmbeddingChunk,
    CourseEmbeddingNeighbor,
    CourseEmbeddingSearchBlock,
    CourseEmbeddingSearchGroup,
    CourseEmbeddingSearchMeta,
)
from course_explorer.embeddings.hub_files import (
    compute_embedding_hubs,
    read_current_chunk_vectors,
)
from course_explorer.embeddings.shared_store import (
    CENTROIDS_FILE,
    CENTROIDS_META_FILE,
    CHUNKS_FILE,
)
from course_explorer.enums import CourseEmbeddingStatus, TeachingTextField
from course_explorer.mock_data import load_mock_curriculum, load_mock_embeddings
from course_explorer.serving_artifacts import (
    HUB_CATALOGUE_FILE,
    HUB_OUTCOMES_FILE,
    ServingArtifacts,
    configured_embedding_directory,
)
from course_explorer.serving_build import (
    build_serving_artifacts,
    embedding_directories,
    prune_serving_artifacts,
)
from course_explorer.study_structure.fragments import FILE_NAME as STUDY_FRAGMENT_FILE

pytestmark = pytest.mark.integration

_FIXTURE_DIR = Path(__file__).resolve().parents[2] / "data" / "mock"


@pytest.fixture(autouse=True)
def _open_lightweight_artifacts() -> None:
    """Override the shared opener patch so this module exercises the real artifact opener."""


@pytest.fixture(autouse=True)
def _preload_supervisor_artifacts() -> None:
    """Override the shared preload. This module opens and builds the real artifact set itself."""


def _open_artifacts(settings):
    """Open the artifact set for the site's embedding switch, resolved at the call."""
    embedding = embedding_configuration_for_site(load_web_settings())
    return ServingArtifacts.open(settings, embedding=embedding)


def _build_artifacts(settings):
    """Build the artifact set for the site's embedding switch, resolved at the call."""
    embedding = embedding_configuration_for_site(load_web_settings())
    return build_serving_artifacts(settings, embedding=embedding)


def _current_build_name(family: Path) -> str:
    """Return the build name the family's ``current`` symlink resolves to."""
    return Path(os.path.realpath(family / "current")).name


def _report_relative(path: Path, root: Path) -> str:
    """Return one artifact path in the report's repository-relative form."""
    return path.resolve().relative_to(root.resolve()).as_posix()


def _owned_builds(family: Path) -> set[str]:
    """Return the build directory names one family holds."""
    return {
        entry.name
        for entry in family.iterdir()
        if entry.is_dir() and not entry.is_symlink() and entry.name.endswith("Z")
    }


def _directory_files(directory: Path) -> dict[str, int]:
    """Return each file name of one directory with its modification time in nanoseconds."""
    return {path.name: path.stat().st_mtime_ns for path in directory.iterdir()}


def _table_state(factory: object) -> tuple[object, ...]:
    """Read the actual derived tables, packed meta row and chunk count of one dataset."""
    with factory() as session:
        centroids = tuple(
            sorted(
                (
                    row.group_id,
                    row.sisu_course_unit_id,
                    row.representative_source_hash,
                    row.chunk_count,
                    bytes(row.centroid),
                    row.embedding_configuration_hash,
                )
                for row in session.scalars(select(CourseEmbeddingCentroid))
            )
        )
        groups = tuple(
            sorted(
                (
                    row.group_no,
                    row.group_id,
                    row.sisu_course_unit_id,
                    row.representative_source_hash,
                )
                for row in session.scalars(select(CourseEmbeddingSearchGroup))
            )
        )
        blocks = tuple(
            sorted(
                (row.block_no, row.n, tuple(row.groups), tuple(row.norms), bytes(row.vectors))
                for row in session.scalars(select(CourseEmbeddingSearchBlock))
            )
        )
        meta = session.get(CourseEmbeddingSearchMeta, True)
        meta_state = None if meta is None else (meta.group_count,)
        neighbors = session.scalar(select(func.count()).select_from(CourseEmbeddingNeighbor))
        chunks = session.scalar(select(func.count()).select_from(CourseEmbeddingChunk))
        return (centroids, groups, blocks, meta_state, neighbors, chunks)


def _disturb_input_vectors(factory: object) -> None:
    """Change one catalogue and one outcome chunk vector so derived content must differ."""
    with factory.begin() as session:
        completed = session.scalars(
            select(CourseEmbeddingChunk)
            .where(CourseEmbeddingChunk.status == CourseEmbeddingStatus.COMPLETED)
            .order_by(CourseEmbeddingChunk.id)
        ).all()
        catalogue_chunk = next(
            row for row in completed if row.field is not TeachingTextField.OUTCOMES
        )
        outcome_chunk = next(row for row in completed if row.field is TeachingTextField.OUTCOMES)
        for row in (catalogue_chunk, outcome_chunk):
            changed = list(row.embedding or ())
            changed[0] += 0.25
            row.embedding = changed


def test_serving_artifact_lifecycle_restores_before_commit_and_keeps_a_committed_build(
    database: tuple[object, object],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A real build, commit rollback and post-commit disposal keep the actual state."""
    _, factory = database
    settings = load_database_settings().model_copy(update={"admin_state_root": "state"})

    # The migrated database starts empty, so the first real build serves an empty dataset.
    empty_report = _build_artifacts(settings)
    assert empty_report.embeddings_enabled is True
    assert (
        empty_report.chunk_count,
        empty_report.outcomes_chunk_count,
        empty_report.centroid_count,
        empty_report.neighbor_count,
        empty_report.search_group_count,
        empty_report.search_block_count,
    ) == (0, 0, 0, 0, 0, 0)
    assert (tmp_path / empty_report.catalogue_path).read_text(encoding="utf-8") == "[]\n"
    assert (tmp_path / empty_report.outcomes_path).read_text(encoding="utf-8") == "[]\n"
    assert _table_state(factory) == ((), (), (), None, 0, 0)
    empty_opened = _open_artifacts(settings)
    empty_build = empty_opened.root.name
    empty_embeddings = empty_opened.embedding_reads()
    assert empty_embeddings.hubs == ((), ())
    assert empty_embeddings.shared_store.centroids.shape == (0, COURSE_EMBEDDING_DIMENSION)
    assert empty_embeddings.search.group_count == 0
    empty_catalogue = json.loads(empty_opened.catalogue_body("empty"))
    assert empty_catalogue["courses"] == []
    assert empty_catalogue["modules"] == []

    fixture_dir = tmp_path / "fixtures"
    shutil.copytree(_FIXTURE_DIR, fixture_dir)
    normalization = load_normalization_settings()
    embedding = load_embedding_runtime_settings()
    load_mock_curriculum(
        factory,
        fixture_dir=fixture_dir,
        raw_root=tmp_path / "raw",
        normalization=normalization,
    )
    load_mock_embeddings(factory, fixture_dir=fixture_dir, embedding=embedding)

    report = _build_artifacts(settings)

    assert report.chunk_count > 0
    assert report.outcomes_chunk_count > 0
    assert report.centroid_count > 0
    assert report.search_group_count > 0
    assert report.search_block_count > 0
    assert report.study_fragment_projectable > 0
    for path in (
        report.catalogue_path,
        report.outcomes_path,
        report.hub_pair_path,
        report.catalogue_artifact_path,
        report.shared_centroid_path,
        report.shared_chunk_path,
        report.study_fragment_path,
    ):
        assert (tmp_path / path).is_file()

    opened = _open_artifacts(settings)
    old_build = opened.root.name
    old_hubs = opened.embedding_reads().hubs
    old_state = _table_state(factory)
    family = opened.root.parent
    embedding_root = configured_embedding_directory(family, embedding)
    _, staging, replaced = embedding_directories(embedding_root)
    assert {path.name for path in opened.root.iterdir()} == {
        serving_artifacts.CATALOGUE_FILE,
        STUDY_FRAGMENT_FILE,
    }
    assert {path.name for path in embedding_root.iterdir()} == {
        HUB_CATALOGUE_FILE,
        HUB_OUTCOMES_FILE,
        serving_artifacts.HUB_PAIR_FILE,
        CENTROIDS_FILE,
        CENTROIDS_META_FILE,
        CHUNKS_FILE,
    }
    assert not staging.exists()
    assert not replaced.exists()
    old_pair = (embedding_root / HUB_CATALOGUE_FILE).read_bytes()
    old_outcomes = (embedding_root / HUB_OUTCOMES_FILE).read_bytes()
    assert report.catalogue_path == _report_relative(embedding_root / HUB_CATALOGUE_FILE, tmp_path)
    assert report.outcomes_path == _report_relative(embedding_root / HUB_OUTCOMES_FILE, tmp_path)
    assert old_state[3] == (report.search_group_count,)
    assert old_state[4] > 0
    assert _current_build_name(family) == old_build

    with pytest.raises(ValueError, match="scripts/admin.py serving-artifacts"):
        _open_artifacts(settings.model_copy(update={"admin_state_root": "absent-state"}))

    database_root = serving_artifacts.serving_database_root(
        tmp_path / "state", settings.postgres_db
    )
    obsolete_build = family / "20261028T000000000000Z"
    obsolete_build.mkdir()
    (family / "current.tmp").write_text("stale", encoding="utf-8")
    (family / "unrelated.txt").write_text("keep", encoding="utf-8")
    (opened.root / "leftover.tmp").write_text("stale", encoding="utf-8")
    obsolete_embedding = family / f"embedding-{'0' * 64}"
    obsolete_embedding.mkdir()
    obsolete_staging = family / f"embedding-{'0' * 64}.tmp"
    obsolete_staging.mkdir()
    obsolete_replaced = family / f"embedding-{'0' * 64}.previous"
    obsolete_replaced.mkdir()
    obsolete_family = database_root / "0123456789abcdef01234567"
    obsolete_family_build = obsolete_family / "20261027T000000000000Z"
    obsolete_family_build.mkdir(parents=True)
    os.symlink(obsolete_family_build.name, obsolete_family / "current")

    prune = prune_serving_artifacts(settings, embedding=embedding)

    assert prune.build_id == old_build
    assert prune.family_path == family.relative_to(tmp_path).as_posix()
    assert not obsolete_build.exists()
    assert not (family / "current.tmp").exists()
    assert not (opened.root / "leftover.tmp").exists()
    assert not obsolete_embedding.exists()
    assert not obsolete_staging.exists()
    assert not obsolete_replaced.exists()
    assert embedding_root.is_dir()
    assert not obsolete_family.exists()
    assert (family / "unrelated.txt").is_file()
    assert _current_build_name(family) == old_build
    assert prune.family_path.startswith("state/serving/")
    assert prune.removed == tuple(
        sorted(
            (
                obsolete_family_build.relative_to(tmp_path).as_posix(),
                (obsolete_family / "current").relative_to(tmp_path).as_posix(),
                obsolete_build.relative_to(tmp_path).as_posix(),
                (family / empty_build).relative_to(tmp_path).as_posix(),
                (family / "current.tmp").relative_to(tmp_path).as_posix(),
                (opened.root / "leftover.tmp").relative_to(tmp_path).as_posix(),
                obsolete_embedding.relative_to(tmp_path).as_posix(),
                obsolete_staging.relative_to(tmp_path).as_posix(),
                obsolete_replaced.relative_to(tmp_path).as_posix(),
            )
        )
    )

    no_current_settings = settings.model_copy(update={"postgres_db": "no_current_test"})
    no_current_root = serving_artifacts.serving_database_root(
        tmp_path / "state", no_current_settings.postgres_db
    )
    no_current_family = no_current_root / serving_artifacts.serving_key(no_current_settings).key
    failed_build = no_current_family / "20261028T020000000000Z"
    failed_build.mkdir(parents=True)
    other_family = no_current_root / "fedcba9876543210fedcba98"
    other_build = other_family / "20261027T000000000000Z"
    other_build.mkdir(parents=True)
    os.symlink(other_build.name, other_family / "current")

    no_current_prune = prune_serving_artifacts(no_current_settings, embedding=embedding)

    assert no_current_prune.build_id is None
    assert not failed_build.exists()
    assert (other_family / "current").exists()
    assert other_build.is_dir()
    assert no_current_prune.family_path == no_current_family.relative_to(tmp_path).as_posix()

    _disturb_input_vectors(factory)
    new_hubs = compute_embedding_hubs(read_current_chunk_vectors(factory, embedding))
    assert new_hubs.catalogue != old_hubs[0]
    assert new_hubs.outcomes != old_hubs[1]

    real_session_scope = database_session.session_scope

    @contextmanager
    def _fail_commit(factory_under_commit: object):
        with real_session_scope(factory_under_commit) as session:

            def _raise_at_commit(*_args: object) -> None:
                raise OSError("synthetic transaction commit failure")

            event.listen(session, "before_commit", _raise_at_commit)
            yield session

    monkeypatch.setattr(serving_build, "session_scope", _fail_commit)
    with pytest.raises(OSError, match="synthetic transaction commit failure"):
        _build_artifacts(settings)
    monkeypatch.setattr(serving_build, "session_scope", real_session_scope)

    assert _table_state(factory) == old_state
    assert _current_build_name(family) == old_build
    assert _owned_builds(family) == {old_build}
    assert (embedding_root / HUB_CATALOGUE_FILE).read_bytes() == old_pair
    assert (embedding_root / HUB_OUTCOMES_FILE).read_bytes() == old_outcomes
    assert not staging.exists()
    assert not replaced.exists()

    real_database_context = database_session.database_context

    @contextmanager
    def _fail_after_disposal(settings_under_build: object):
        with real_database_context(settings_under_build) as factory_under_build:
            yield factory_under_build
        raise OSError("synthetic engine disposal failure")

    monkeypatch.setattr(serving_build, "database_context", _fail_after_disposal)
    with pytest.raises(OSError, match="synthetic engine disposal failure"):
        _build_artifacts(settings)
    monkeypatch.setattr(serving_build, "database_context", real_database_context)

    new_state = _table_state(factory)
    assert new_state != old_state
    new_build = _current_build_name(family)
    assert new_build != old_build
    assert (family / new_build).is_dir()
    new_pair = (embedding_root / HUB_CATALOGUE_FILE).read_bytes()
    new_outcomes = (embedding_root / HUB_OUTCOMES_FILE).read_bytes()
    assert (new_pair, new_outcomes) != (old_pair, old_outcomes)
    assert not replaced.exists()
    committed = _open_artifacts(settings)
    assert committed.root.name == new_build
    assert committed.root == (family / new_build).resolve()
    committed_hubs = committed.embedding_reads().hubs

    # A first build of a configuration that fails before the commit leaves no embedding directory.
    shutil.rmtree(embedding_root)
    rollback_state = _table_state(factory)
    monkeypatch.setattr(serving_build, "session_scope", _fail_commit)
    with pytest.raises(OSError, match="synthetic transaction commit failure"):
        _build_artifacts(settings)
    monkeypatch.setattr(serving_build, "session_scope", real_session_scope)
    assert not embedding_root.exists()
    assert not staging.exists()
    assert not replaced.exists()
    assert _table_state(factory) == rollback_state
    assert _current_build_name(family) == new_build

    # One more build restores the directory the following cases read.
    assert _build_artifacts(settings).chunk_count > 0
    committed = _open_artifacts(settings)
    committed_hubs = committed.embedding_reads().hubs
    new_build = committed.root.name

    # A failed second replacement of the configured embedding directory restores the previous one,
    # so the family never loses the directory the next build would collect as a replaced copy.
    hub_bytes = (embedding_root / HUB_CATALOGUE_FILE).read_bytes()
    outcomes_bytes = (embedding_root / HUB_OUTCOMES_FILE).read_bytes()
    directory_state = _table_state(factory)
    real_replace = os.replace

    def _fail_directory_publish(source: object, destination: object) -> None:
        if Path(destination) == embedding_root and Path(source) == staging:
            raise OSError("synthetic embedding directory publish failure")
        real_replace(source, destination)

    monkeypatch.setattr(serving_build.os, "replace", _fail_directory_publish)
    with pytest.raises(OSError, match="synthetic embedding directory publish failure"):
        _build_artifacts(settings)
    monkeypatch.setattr(serving_build.os, "replace", real_replace)

    assert (embedding_root / HUB_CATALOGUE_FILE).read_bytes() == hub_bytes
    assert (embedding_root / HUB_OUTCOMES_FILE).read_bytes() == outcomes_bytes
    assert _table_state(factory) == directory_state
    assert _current_build_name(family) == new_build
    assert not staging.exists()
    assert not replaced.exists()
    assert _open_artifacts(settings).embedding_reads().hubs == committed_hubs

    fragment_path = committed.root / STUDY_FRAGMENT_FILE
    fragment_bytes = fragment_path.read_bytes()
    fragment_path.unlink()
    with pytest.raises(ValueError, match="scripts/admin.py serving-artifacts"):
        _open_artifacts(settings)
    fragment_path.write_bytes(fragment_bytes)

    centroid_index = embedding_root / "centroids.json"
    centroid_index_bytes = centroid_index.read_bytes()
    centroid_index.unlink()
    with pytest.raises(ValueError, match="scripts/admin.py serving-artifacts"):
        _open_artifacts(settings)
    centroid_index.write_bytes(centroid_index_bytes)

    assert _open_artifacts(settings).root.name == new_build

    # A hub of another dimension or with a non-finite component refuses the one open.
    hub_path = embedding_root / HUB_CATALOGUE_FILE
    hub_original = hub_path.read_bytes()
    hub_path.write_text("[0.0]", encoding="utf-8")
    with pytest.raises(ValueError, match=f"exactly {COURSE_EMBEDDING_DIMENSION} components"):
        _open_artifacts(settings)
    hub_path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="must hold a JSON array"):
        _open_artifacts(settings)
    hub_path.write_text(
        json.dumps([0.0] * (COURSE_EMBEDDING_DIMENSION - 1) + [math.inf]), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="finite components"):
        _open_artifacts(settings)
    hub_path.write_bytes(hub_original)
    assert _open_artifacts(settings).root.name == new_build

    # A site with the embedding features off builds with incomplete vector coverage and
    # writes the catalogue artifact and the study fragments alone.
    monkeypatch.setenv("WEB_EMBEDDINGS_ENABLED", "0")
    with factory.begin() as session:
        for chunk in session.scalars(select(CourseEmbeddingChunk)):
            chunk.status = CourseEmbeddingStatus.PENDING
            chunk.embedding = None
    embedding_before = _directory_files(embedding_root)
    tables_before = _table_state(factory)
    off_report = _build_artifacts(settings)
    assert off_report.embeddings_enabled is False
    assert off_report.hub_pair_path is None
    assert off_report.chunk_count is None
    assert off_report.search_group_count is None
    off_root = (tmp_path / off_report.study_fragment_path).parent
    assert {path.name for path in off_root.iterdir()} == {
        serving_artifacts.CATALOGUE_FILE,
        STUDY_FRAGMENT_FILE,
    }
    off_opened = _open_artifacts(settings)
    assert off_opened.root == off_root.resolve()
    assert off_opened.embeddings is None
    with pytest.raises(ValueError, match="the embedding features are off on this site"):
        off_opened.embedding_reads()
    assert _current_build_name(off_root.parent) == off_root.name
    assert _directory_files(embedding_root) == embedding_before
    assert _table_state(factory) == tables_before

    # Switching the features on without a build reuses the embedding directory of the configuration.
    monkeypatch.setenv("WEB_EMBEDDINGS_ENABLED", "1")
    reused = _open_artifacts(settings)
    assert reused.root == off_root.resolve()
    assert reused.embedding_reads().hubs == committed_hubs

    # A changed embedding configuration has no embedding directory, so the open refuses until a
    # build.
    monkeypatch.setenv("EMBEDDING_MODEL", "another-embedding-model")
    with pytest.raises(ValueError, match="serving embedding artifacts are missing"):
        _open_artifacts(settings)
    monkeypatch.delenv("EMBEDDING_MODEL")

    # The same incomplete coverage makes an embeddings-on build fail before it switches the target.
    with pytest.raises(ValueError, match="embedding stage is required"):
        _build_artifacts(settings)
    monkeypatch.setenv("WEB_EMBEDDINGS_ENABLED", "0")
    assert _open_artifacts(settings).root == off_root.resolve()
    monkeypatch.setenv("WEB_EMBEDDINGS_ENABLED", "1")

    # A packed search row without any stored neighbour refuses the embeddings-on open.
    with factory.begin() as session:
        session.execute(delete(CourseEmbeddingNeighbor))
    with pytest.raises(ValueError, match="course embedding neighbours are absent"):
        _open_artifacts(settings)

    # A missing packed search meta row refuses the embeddings-on open.
    with factory.begin() as session:
        meta = session.get(CourseEmbeddingSearchMeta, True)
        session.delete(meta)
    with pytest.raises(ValueError, match="meta row.*serving-artifacts"):
        _open_artifacts(settings)

    # Prune keeps a current build that holds no embedding file and collects an owned obsolete one.
    # With the features off it keeps every owned embedding directory, including an obsolete
    # configuration and its staging copy, because it resolves no embedding configuration.
    obsolete_off_build = off_root.parent / "20261029T000000000000Z"
    obsolete_off_build.mkdir()
    off_embedding = off_root.parent / f"embedding-{'1' * 64}"
    off_embedding.mkdir()
    off_embedding_staging = off_root.parent / f"embedding-{'1' * 64}.tmp"
    off_embedding_staging.mkdir()
    off_prune = prune_serving_artifacts(settings, embedding=None)
    assert off_prune.build_id == off_root.name
    assert not obsolete_off_build.exists()
    assert embedding_root.is_dir()
    assert off_embedding.is_dir()
    assert off_embedding_staging.is_dir()
    assert _current_build_name(off_root.parent) == off_root.name
