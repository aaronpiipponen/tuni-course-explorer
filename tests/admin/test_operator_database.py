"""Opt-in PostgreSQL proofs for the operator reports and the worker schema barrier.

These integration contracts use the guarded disposable ``*_test`` database only. The report proof
seeds the real 3-active/1000-inactive catalogue and asserts the fresh owning reads against synthetic
metadata whose sample verification differs. The schema proof corrupts only the recorded
Alembic version of that disposable database and proves the real shared worker barrier refuses before
any processing, model, or state work.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import pytest
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import sessionmaker

from course_explorer import administration
from course_explorer.administration import administrative_json, atomic_write_private_text
from course_explorer.config import load_inference_settings, load_normalization_settings
from course_explorer.datasets import (
    DatabaseSchemaMismatchError,
    DatasetReceipt,
    SelectedDatasetPointer,
)
from course_explorer.db.models import (
    Course,
    CourseText,
    CourseVersion,
    InferenceCourseProcessing,
    InferenceModelAttempt,
    InferenceProposal,
)
from course_explorer.db.session import session_scope
from course_explorer.enums import (
    TeachingTextField,
    TeachingTextLanguage,
)
from course_explorer_admin import commands, worker_session
from course_explorer_admin import datasets as datasets_module
from course_explorer_admin import lifecycle as lifecycle_module
from course_explorer_admin.inference import controller_worker as inference_worker
from course_explorer_admin.inference import disposition as disposition_module
from course_explorer_admin.lifecycle import (
    IngestionProgress,
    LifecycleState,
    stage_state_root,
    write_lifecycle_state,
)
from course_explorer_admin.translation import controller_worker as translation_worker
from tests.admin.inference import _worker_support as inference_support
from tests.admin.translation import _worker_support as translation_support
from tests.datasets._support import sample_receipt, sample_verification
from tests.inference._scheduling_support import reconcile, seed_courses

SESSION_ID = "0123456789abcdef0123456789abcdef"
_REAL_WORKER_SCHEMA = worker_session.require_worker_database_schema

_ACTIVE_TARGETS = (
    (
        "admin-live-target-0",
        "ADMIN.T0",
        "Study orientation",
        "Opintoihin perehtyminen",
        "Kurssi esittelee opiskelun käytännöt, opintojen suunnittelun ja yliopiston palvelut.",
        "Opiskelija osaa suunnitella opintonsa ja käyttää palveluja.",
    ),
    (
        "admin-live-target-1",
        "ADMIN.T1",
        "Linear algebra",
        "Lineaarialgebra",
        "Kurssi käsittelee vektoreita, matriiseja, lineaarisia yhtälöryhmiä ja ominaisarvoja.",
        "Opiskelija osaa ratkaista yhtälöryhmiä ja laskea ominaisarvoja.",
    ),
    (
        "admin-live-target-2",
        "ADMIN.T2",
        "Numerical linear algebra",
        "Numeerinen lineaarialgebra",
        "Kurssi käsittelee matriisien numeerisia hajotelmia, iteratiivisia menetelmiä ja "
        "virheanalyysiä.",
        "Opiskelija osaa toteuttaa matriisimenetelmiä ja arvioida niiden numeerista virhettä.",
    ),
)
_INACTIVE_CONTENT_FI = "Kurssi käsittelee vektoreita, matriiseja ja lineaarisia yhtälöryhmiä."
_INACTIVE_CONTENT_EN = "The course teaches vectors, matrices and linear systems."
_INACTIVE_COUNT = 1000


def _require_acceptance_calendar() -> None:
    settings = load_normalization_settings()
    if settings.current_academic_year != "2026-2027" or settings.active_academic_year_window != 3:
        raise RuntimeError(
            "report catalogue requires CURRENT_ACADEMIC_YEAR=2026-2027 and "
            "ACTIVE_ACADEMIC_YEAR_WINDOW=3"
        )


def _seed_report_catalogue(factory: sessionmaker) -> tuple[str, ...]:
    """Seed the real 3-active/1000-inactive catalogue and its bilingual teaching text.

    Active targets get their distinct titles/content/outcomes with English content and outcomes
    absent (six real translation units). Inactive sources get both content languages
    and no outcomes in either language. The seed writes canonical course records and their
    bilingual teaching text.
    """
    _require_acceptance_calendar()
    active_specs = [(group_id, code, True) for group_id, code, *_rest in _ACTIVE_TARGETS]
    inactive_specs = [
        (f"admin-live-source-{index:04d}", f"ADMIN.S{index:04d}", False)
        for index in range(_INACTIVE_COUNT)
    ]
    seed_courses(factory, active_specs + inactive_specs)
    with session_scope(factory) as session:
        for group_id, _code, name_en, name_fi, content_fi, outcomes_fi in _ACTIVE_TARGETS:
            course = session.scalar(select(Course).where(Course.group_id == group_id))
            if course is None:
                raise RuntimeError("seeded active target course is missing")
            version = session.scalar(
                select(CourseVersion).where(CourseVersion.course_id == course.id)
            )
            if version is None:
                raise RuntimeError("seeded active target version is missing")
            version.name_en = name_en
            version.name_fi = name_fi
            text = session.scalar(
                select(CourseText).where(CourseText.course_version_id == version.id)
            )
            if text is None:
                raise RuntimeError("seeded active target text is missing")
            text.content_fi = content_fi
            text.outcomes_fi = outcomes_fi
        for index in range(_INACTIVE_COUNT):
            group_id = f"admin-live-source-{index:04d}"
            course = session.scalar(select(Course).where(Course.group_id == group_id))
            if course is None:
                raise RuntimeError("seeded inactive source course is missing")
            version = session.scalar(
                select(CourseVersion).where(CourseVersion.course_id == course.id)
            )
            if version is None:
                raise RuntimeError("seeded inactive source version is missing")
            text = session.scalar(
                select(CourseText).where(CourseText.course_version_id == version.id)
            )
            if text is None:
                raise RuntimeError("seeded inactive source text is missing")
            text.content_fi = _INACTIVE_CONTENT_FI
            text.content_en = _INACTIVE_CONTENT_EN
    return tuple(
        [group_id for group_id, _code, *_rest in _ACTIVE_TARGETS]
        + [f"admin-live-source-{index:04d}" for index in range(_INACTIVE_COUNT)]
    )


pytestmark = [
    pytest.mark.integration,
]


def _set_alembic_version(engine: Engine, version: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE alembic_version SET version_num = :version"), {"version": version}
        )


def _derive_head_and_predecessor() -> tuple[str, str]:
    script = ScriptDirectory.from_config(AlembicConfig("alembic.ini"))
    head = script.get_heads()[0]
    revision = script.get_revision(head)
    previous = revision.down_revision
    if isinstance(previous, tuple):
        previous = previous[0]
    if previous is None:
        raise RuntimeError("head revision has no predecessor for the schema mismatch test")
    return head, previous


def _count(engine: Engine, model: object) -> int:
    with engine.connect() as connection:
        return int(connection.execute(select(func.count()).select_from(model)).scalar_one())


def _field(report, field: TeachingTextField, language: TeachingTextLanguage):
    for count in report.fields:
        if count.field == field and count.language == language:
            return count
    raise AssertionError(f"missing coverage field {field}/{language}")


def test_operator_reports_read_selected_disposable_fixture_without_writes(
    database: tuple[Engine, object],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The real administrative reports read the selected disposable fixture and write nothing."""
    engine, factory = database
    repo_root = tmp_path / "repo"
    try:
        _seed_report_catalogue(factory)
        receipt = sample_receipt(database_name=engine.url.database)
        admin_root = repo_root / "data" / "admin"
        dataset_dir = admin_root / "datasets" / receipt.dataset_id
        dataset_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        atomic_write_private_text(dataset_dir / "receipt.json", administrative_json(receipt))
        atomic_write_private_text(
            admin_root / "selected-dataset.json",
            administrative_json(
                SelectedDatasetPointer(schema_version=1, dataset_id=receipt.dataset_id)
            ),
        )
        monkeypatch.setattr(administration, "repository_root", lambda: repo_root)
        monkeypatch.setenv("SELECTED_DATASET_ENABLED", "1")
        monkeypatch.setenv("ADMIN_STATE_ROOT", "data/admin")

        markers_before = _count(engine, InferenceCourseProcessing)
        attempts_before = _count(engine, InferenceModelAttempt)
        proposals_before = _count(engine, InferenceProposal)

        catalogue = commands.run_administrative_summary("catalogue")
        assert catalogue.canonical_course_count == 1003
        assert catalogue.active_course_count == 3

        teaching = commands.run_administrative_coverage("teaching-text")
        assert (
            _field(teaching, TeachingTextField.CONTENT, TeachingTextLanguage.EN).missing_count == 3
        )
        assert (
            _field(teaching, TeachingTextField.OUTCOMES, TeachingTextLanguage.EN).missing_count
            == 1003
        )
        assert all(count.derived_count == 0 for count in teaching.fields)

        embedding = commands.run_administrative_coverage("embedding")
        assert embedding.total_chunk_count == 0
        assert embedding.completed_count == 0

        inference = commands.run_administrative_coverage("inference")
        assert inference.eligible_targets == 3
        assert inference.retained_complete_targets == 0
        assert inference.published_targets == 0
        assert inference.uncovered_targets == 3

        summary = commands.run_administrative_summary("inference")
        assert summary.dataset_scope == "retained_server"
        assert summary.coverage.eligible_targets == 3
        assert summary.coverage.retained_complete_targets == 0
        assert summary.publication.eligible_targets == 3
        assert summary.publication.selected_targets == 0
        assert summary.publication.accepted_targets == 0
        # The three policy members are the owning settings' configured values.
        generation = load_inference_settings()
        assert summary.routing_policy == generation.inference_routing_policy
        assert summary.recommendation_policy == generation.inference_recommendation_policy
        assert summary.finding_filter_policy == generation.inference_finding_filter_policy

        assert _count(engine, InferenceCourseProcessing) == markers_before
        assert _count(engine, InferenceModelAttempt) == attempts_before
        assert _count(engine, InferenceProposal) == proposals_before
    finally:
        monkeypatch.setenv("SELECTED_DATASET_ENABLED", "0")


def _forbidden(*args, **kwargs):
    pytest.fail("no runtime or product work may start on a schema mismatch")


def test_worker_schema_mismatch_refuses_before_work(
    database: tuple[Engine, object],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The real shared worker barrier refuses a stale received database before any work."""
    engine, _factory = database
    head, previous = _derive_head_and_predecessor()
    monkeypatch.setattr(worker_session, "create_database_engine", lambda settings: engine)

    with monkeypatch.context() as m:
        stage_root = tmp_path / "translation"
        stage_root.mkdir()
        translation_support.configure(m, stage_root)
        m.setattr(worker_session, "require_worker_database_schema", _REAL_WORKER_SCHEMA)
        m.setenv("SELECTED_DATASET_ENABLED", "0")
        session_value = translation_support.session()
        m.setenv("POSTGRES_DB", session_value.database_name)
        directory, session_value = translation_support.seed_directory(stage_root, session_value)
        translation_support.write_control(directory, "run")
        translation_support.write_state(directory, schema_version=2, lifecycle="prepared")
        m.setattr(translation_worker, "OwnedWorkerRuntime", _forbidden)
        m.setattr(translation_worker, "run_translation_command", _forbidden)
        _REAL_WORKER_SCHEMA(session_value)
        control_before = (directory / "control.json").read_bytes()
        state_before = (directory / "state.json").read_bytes()
        _set_alembic_version(engine, previous)
        try:
            with pytest.raises(DatabaseSchemaMismatchError):
                worker_session.run_worker_session(
                    translation_worker.TranslationWorkerStage(),
                    SESSION_ID,
                    runner=translation_support.FakeRunner(),
                )
            with pytest.raises(DatabaseSchemaMismatchError):
                worker_session.request_worker_action(
                    translation_worker.TranslationWorkerStage(),
                    SESSION_ID,
                    "resume",
                    runner=translation_support.FakeRunner(),
                )
        finally:
            _set_alembic_version(engine, head)
        assert (directory / "control.json").read_bytes() == control_before
        assert (directory / "state.json").read_bytes() == state_before
        assert not (directory / "runner.json").exists()
        assert not (directory / "import-receipt.json").exists()

    with monkeypatch.context() as m:
        stage_root = tmp_path / "inference"
        stage_root.mkdir()
        directory = inference_support.seed_session(m, stage_root, lifecycle="prepared")
        m.setattr(worker_session, "require_worker_database_schema", _REAL_WORKER_SCHEMA)
        m.setenv("SELECTED_DATASET_ENABLED", "0")
        session_value = inference_support.session()
        m.setenv("POSTGRES_DB", session_value.database_name)
        m.setattr(worker_session, "OwnedWorkerRuntime", _forbidden)
        m.setattr(inference_worker, "WorkerInferenceRuntime", _forbidden)
        m.setattr(inference_worker, "run_inference_job", _forbidden)
        _REAL_WORKER_SCHEMA(session_value)
        control_before = (directory / "control.json").read_bytes()
        state_before = (directory / "state.json").read_bytes()
        _set_alembic_version(engine, previous)
        try:
            with pytest.raises(DatabaseSchemaMismatchError):
                worker_session.run_worker_session(
                    inference_worker.InferenceWorkerStage(),
                    SESSION_ID,
                    runner=inference_support.FakeRunner(),
                )
            with pytest.raises(DatabaseSchemaMismatchError):
                worker_session.request_worker_action(
                    inference_worker.InferenceWorkerStage(),
                    SESSION_ID,
                    "resume",
                    runner=inference_support.FakeRunner(),
                )
        finally:
            _set_alembic_version(engine, head)
        assert (directory / "control.json").read_bytes() == control_before
        assert (directory / "state.json").read_bytes() == state_before
        assert not (directory / "runner.json").exists()
        assert not (directory / "import-receipt.json").exists()


_DISPOSITION_TARGET = "disp-target"
_DISPOSITION_SOURCES = ("disp-src-0", "disp-src-1")


def _marker_disposition(engine: Engine) -> str | None:
    with engine.connect() as connection:
        return connection.execute(
            select(InferenceCourseProcessing.disposition)
            .join(Course, Course.id == InferenceCourseProcessing.course_id)
            .where(Course.group_id == _DISPOSITION_TARGET)
        ).scalar_one()


def _seed_disposition_catalogue(factory: sessionmaker) -> None:
    """Seed one active target and two active sources with reconciled markers."""
    seed_courses(
        factory,
        [(_DISPOSITION_TARGET, "DISP.T", True)]
        + [
            (group_id, f"DISP.{index}", True) for index, group_id in enumerate(_DISPOSITION_SOURCES)
        ],
    )
    reconcile(factory)


def _fixture_database_context(factory: sessionmaker):
    """Return a context manager yielding the disposable fixture session factory."""

    @contextmanager
    def context(_settings):
        yield factory

    return context


@pytest.mark.parametrize(
    ("admission", "choice"),
    [
        ("idle_returned_current", "nothing"),
        ("idle_returned_current", "done"),
        ("idle_returned_current", "failed"),
        ("non_idle_stage", None),
        ("initial_selection", None),
        ("wrong_actual_schema", None),
    ],
)
def test_disposition_reads_selected_schema_and_guards_writes(
    database: tuple[Engine, object],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    admission: str,
    choice: str | None,
) -> None:
    """The disposition service writes one disposition on an idle returned current-schema dataset.

    Every other admission refuses the write and leaves the durable decision unset and the final
    store empty.
    """
    engine, factory = database
    repo_root = tmp_path / "repo"
    # The shared owners bind ``repository_root`` into their own module namespace, so redirect every
    # one the guarded context actually uses instead of only the shared source name.
    monkeypatch.setattr(administration, "repository_root", lambda: repo_root)
    monkeypatch.setattr(datasets_module, "repository_root", lambda: repo_root)
    monkeypatch.setattr(lifecycle_module, "repository_root", lambda: repo_root)
    monkeypatch.setattr(disposition_module, "database_context", _fixture_database_context(factory))
    monkeypatch.setattr(disposition_module.mechanics, "SubprocessRunner", _forbidden)
    monkeypatch.setenv("SELECTED_DATASET_ENABLED", "1")
    monkeypatch.setenv("ADMIN_STATE_ROOT", "data/admin")

    _seed_disposition_catalogue(factory)
    dataset_id = "b" * 32
    if admission == "initial_selection":
        receipt = sample_receipt(database_name=engine.url.database)
    else:
        receipt = DatasetReceipt(
            schema_version=1,
            dataset_id=dataset_id,
            database_name=engine.url.database,
            predecessor_id="a" * 32,
            kind="returned",
            dump_sha256="d" * 64,
            verification=sample_verification(),
        )
    admin_root = repo_root / "data" / "admin"
    dataset_dir = admin_root / "datasets" / receipt.dataset_id
    dataset_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    atomic_write_private_text(dataset_dir / "receipt.json", administrative_json(receipt))
    atomic_write_private_text(
        admin_root / "selected-dataset.json",
        administrative_json(
            SelectedDatasetPointer(schema_version=1, dataset_id=receipt.dataset_id)
        ),
    )
    if admission == "non_idle_stage":
        root = stage_state_root("ingestion")
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        write_lifecycle_state(
            root,
            LifecycleState(
                schema_version=1,
                session_id="a" * 32,
                lifecycle="running",
                requested_action="run",
                progress=IngestionProgress(
                    kind="ingestion",
                    stage="capture",
                    response_count=1,
                    verified_response_count=0,
                    normalized=False,
                ),
                work_complete=False,
                active_seconds=0.0,
            ),
        )

    published: list[object] = []
    real_publish = disposition_module.publish_current_cohort

    def recording_publish(*args, **kwargs):
        published.append(args)
        return real_publish(*args, **kwargs)

    monkeypatch.setattr(disposition_module, "publish_current_cohort", recording_publish)
    head, previous = _derive_head_and_predecessor()
    if admission == "wrong_actual_schema":
        _set_alembic_version(engine, previous)
    try:
        if admission == "idle_returned_current":
            disposition = None if choice == "nothing" else choice
            report = disposition_module.set_inference_target_disposition(
                _DISPOSITION_TARGET, disposition
            )
            # The real report carries the canonical identity and the real durable decision, and the
            # publisher ran once through its sole owner.
            assert report.dataset_id == dataset_id
            assert report.target_group_id == _DISPOSITION_TARGET
            assert report.course_code == "DISP.T"
            assert report.course_name == "Name DISP.T"
            assert report.disposition == disposition
            assert len(published) == 1
            assert _marker_disposition(engine) == disposition
            assert (
                disposition_module.read_inference_target_disposition(
                    _DISPOSITION_TARGET
                ).disposition
                == disposition
            )
        else:
            if admission == "wrong_actual_schema":
                with pytest.raises(DatabaseSchemaMismatchError):
                    disposition_module.read_inference_target_disposition(_DISPOSITION_TARGET)
            else:
                # A read succeeds on an initial or non-idle selected dataset and takes no action lock.
                with monkeypatch.context() as read_scope:
                    read_scope.setattr(
                        disposition_module.mechanics, "exclusive_action_lock", _forbidden
                    )
                    read = disposition_module.read_inference_target_disposition(_DISPOSITION_TARGET)
                assert read.dataset_id == receipt.dataset_id
                assert read.target_group_id == _DISPOSITION_TARGET
                assert read.disposition is None
            with pytest.raises((ValueError, DatabaseSchemaMismatchError)):
                disposition_module.set_inference_target_disposition(_DISPOSITION_TARGET, "done")
            # Refused admissions leave the durable decision and the final store untouched.
            assert _marker_disposition(engine) is None
            assert published == []
            assert _count(engine, InferenceProposal) == 0
    finally:
        _set_alembic_version(engine, head)
