"""Contracts for the shared local detached lifecycle core.

These proofs drive the real core, the real detached worker subprocess and the real
state/lock layout over temporary durable units: one continuous operator work window, one
interruption/incompatibility boundary, the distinct owned-temporary-service security boundary,
and ingestion idle raw-retention ownership and confinement.
The synthetic stage and process double live in ``tests/admin/_lifecycle_support.py``.
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from course_explorer.config import (
    CaptureSettings,
    KoriSettings,
    NormalizationSettings,
)
from course_explorer.ingestion.capture import capture_curriculum
from course_explorer.ingestion.manifest import RawCaptureStore
from course_explorer_admin import local_stages
from course_explorer_admin.lifecycle import (
    IngestionOptions,
    IngestionProgress,
    read_lifecycle_state,
    require_retained_ingestion_manifest,
    run_lifecycle_command,
)
from tests.admin._lifecycle_support import (
    DELAY_ALIAS,
    FAIL_DATABASE_ALIAS,
    IDENTITY_ALIAS,
    INITIAL_ACTION_ALIAS,
    UNITS_ALIAS,
    LocalLifecycleRunner,
    SupportStage,
    configure_environment,
    session_id_from_state,
    unit_count,
    wait_for_lifecycle,
    wait_for_stable_state,
    wait_for_units,
)
from tests.ingestion._capture_support import (
    FixtureSource,
    RecordingCapturePersistence,
    new_store,
)
from tests.support import settings_factory


class _CheckpointContext:
    """A lifecycle context double that records each checkpoint as the ingestion progress."""

    def __init__(self, progress: IngestionProgress, options: IngestionOptions) -> None:
        self.progress = progress
        self.session = SimpleNamespace(options=options)
        self.checkpoints: list[IngestionProgress] = []

    def read_state(self) -> SimpleNamespace:
        return SimpleNamespace(progress=self.progress)

    def checkpoint(self, progress: IngestionProgress) -> None:
        self.progress = progress
        self.checkpoints.append(progress)

    def admit(self) -> bool:
        return True


def _unit_files(root: Path, session_id: str) -> dict[str, bytes]:
    directory = root / session_id / "units"
    return {path.name: path.read_bytes() for path in sorted(directory.glob("unit-*.txt"))}


@pytest.mark.parametrize("stage_name", ["ingestion", "embedding"])
def test_local_lifecycle_actions_checkpoint_pause_stop_and_resume_pending(
    stage_name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Five actions return. Pause/stop checkpoint. Resume/start continue only pending units."""
    configure_environment(monkeypatch)
    monkeypatch.setenv(UNITS_ALIAS, "8")
    monkeypatch.setenv(DELAY_ALIAS, "0.4")
    monkeypatch.setenv(IDENTITY_ALIAS, "identity-a")
    root = tmp_path / "state"
    runner = LocalLifecycleRunner(root=root, running={"db"})
    stage = SupportStage(stage_name)  # type: ignore[arg-type]
    stage.temporary_services = ()  # ownership is a separate proof below
    sleep = time.sleep
    try:
        # Status on a fresh root creates nothing.
        fresh = run_lifecycle_command("status", stage=stage, root=root, runner=runner, sleep=sleep)
        assert fresh.lifecycle == "idle"
        assert not root.exists()

        # Detached start returns one running status and launches exactly one child.
        started = run_lifecycle_command("start", stage=stage, root=root, runner=runner, sleep=sleep)
        assert started.lifecycle == "running"
        session_id = session_id_from_state(root)
        wait_for_units(root, session_id, 1)
        assert len(runner.launches) == 1

        # A second live start returns the same status without another launch.
        live = run_lifecycle_command("start", stage=stage, root=root, runner=runner, sleep=sleep)
        assert live.session_id == session_id
        assert len(runner.launches) == 1

        # Status during work changes neither state bytes nor launches resources.
        stable = wait_for_stable_state(root)
        during = run_lifecycle_command("status", stage=stage, root=root, runner=runner, sleep=sleep)
        assert during.lifecycle == "running"
        assert (root / "state.json").read_bytes() == stable
        assert len(runner.launches) == 1

        # Pause at the next committed unit boundary. The owned worker exits.
        paused = run_lifecycle_command("pause", stage=stage, root=root, runner=runner, sleep=sleep)
        assert paused.lifecycle == "paused"
        assert paused.session_id == session_id
        assert runner.children[-1].wait(timeout=5) == 0
        files_at_pause = _unit_files(root, session_id)
        assert 1 <= len(files_at_pause) < 8

        # Public resume re-arms the same session. Stop while coverage is partial.
        resumed = run_lifecycle_command(
            "resume", stage=stage, root=root, runner=runner, sleep=sleep
        )
        assert resumed.session_id == session_id
        assert len(runner.launches) == 2
        stopped_partial = run_lifecycle_command(
            "stop", stage=stage, root=root, runner=runner, sleep=sleep
        )
        assert stopped_partial.lifecycle == "idle"
        partial_state = read_lifecycle_state(root)
        assert partial_state is not None and partial_state.work_complete is False
        partial_files = _unit_files(root, session_id)
        assert 1 <= len(partial_files) < 8
        for name, payload in files_at_pause.items():
            assert partial_files[name] == payload

        # A bare start continues only the pending units to completion.
        run_lifecycle_command("start", stage=stage, root=root, runner=runner, sleep=sleep)
        assert len(runner.launches) == 3
        wait_for_lifecycle(root, {"completed"})
        assert unit_count(root, session_id) == 8
        after = _unit_files(root, session_id)
        for name, payload in files_at_pause.items():
            assert after[name] == payload

        # Stop finalizes to idle. A repeated idle stop is byte- and launch-identical.
        stopped = run_lifecycle_command("stop", stage=stage, root=root, runner=runner, sleep=sleep)
        assert stopped.lifecycle == "idle"
        state_bytes = (root / "state.json").read_bytes()
        launches = len(runner.launches)
        again = run_lifecycle_command("stop", stage=stage, root=root, runner=runner, sleep=sleep)
        assert again.lifecycle == "idle"
        assert (root / "state.json").read_bytes() == state_bytes
        assert len(runner.launches) == launches
    finally:
        runner.close()


def test_local_lifecycle_interruption_preserves_checkpoint_and_refuses_incompatible_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Killing the owned child keeps checkpoints. An incompatible start refuses and stop works."""
    configure_environment(monkeypatch)
    monkeypatch.setenv(UNITS_ALIAS, "8")
    monkeypatch.setenv(DELAY_ALIAS, "0.15")
    monkeypatch.setenv(IDENTITY_ALIAS, "identity-a")
    root = tmp_path / "state"
    runner = LocalLifecycleRunner(root=root, running={"db"})
    stage = SupportStage("ingestion")
    sleep = time.sleep
    try:
        run_lifecycle_command("start", stage=stage, root=root, runner=runner, sleep=sleep)
        session_id = session_id_from_state(root)
        wait_for_units(root, session_id, 2)

        # Kill only the exact owned synthetic child and reap it.
        owned = read_lifecycle_state(root)
        assert owned is not None and owned.process is not None
        os.kill(owned.process.pid, signal.SIGKILL)
        runner.children[-1].wait()
        files_before = _unit_files(root, session_id)
        state_bytes = (root / "state.json").read_bytes()

        # Observe interrupted without a status write.
        interrupted = run_lifecycle_command(
            "status", stage=stage, root=root, runner=runner, sleep=sleep
        )
        assert interrupted.lifecycle == "interrupted"
        assert (root / "state.json").read_bytes() == state_bytes

        # A changed configuration identity refuses start and preserves files/units.
        monkeypatch.setenv(IDENTITY_ALIAS, "identity-b")
        with pytest.raises(ValueError):
            run_lifecycle_command("start", stage=stage, root=root, runner=runner, sleep=sleep)
        assert (root / "state.json").read_bytes() == state_bytes
        assert _unit_files(root, session_id) == files_before

        # Stop preserves the receipt and checkpoints.
        stopped = run_lifecycle_command("stop", stage=stage, root=root, runner=runner, sleep=sleep)
        assert stopped.lifecycle == "idle"
        assert (root / session_id / "session.json").is_file()
        assert _unit_files(root, session_id) == files_before

        # Compatible work resumes pending units without repeating a completed one.
        monkeypatch.setenv(IDENTITY_ALIAS, "identity-a")
        run_lifecycle_command("start", stage=stage, root=root, runner=runner, sleep=sleep)
        wait_for_lifecycle(root, {"completed"})
        assert unit_count(root, session_id) == 8
        resumed = _unit_files(root, session_id)
        for name, payload in files_before.items():
            assert resumed[name] == payload
    finally:
        runner.close()


@pytest.mark.parametrize("pre_existing", [False, True])
def test_local_lifecycle_releases_only_owned_temporary_services(
    pre_existing: bool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Refused initial pause, terminal pause and completion release only owned services."""
    configure_environment(monkeypatch)
    monkeypatch.setenv(UNITS_ALIAS, "6")
    monkeypatch.setenv(DELAY_ALIAS, "0.1")
    monkeypatch.setenv(IDENTITY_ALIAS, "identity-a")
    root = tmp_path / "state"
    running = {"db", "embedding"} if pre_existing else {"db"}
    runner = LocalLifecycleRunner(root=root, running=running)
    stage = SupportStage("embedding")
    sleep = time.sleep
    failing_runner: LocalLifecycleRunner | None = None
    release_runner: LocalLifecycleRunner | None = None
    try:
        # A pending initial pause refuses the first start without any unit work.
        monkeypatch.setenv(INITIAL_ACTION_ALIAS, "pause")
        started = run_lifecycle_command("start", stage=stage, root=root, runner=runner, sleep=sleep)
        assert started.lifecycle == "paused"
        session_id = session_id_from_state(root)
        assert unit_count(root, session_id) == 0

        # Public pause unloads the dead owner and leaves the embedding and database state in place.
        paused = run_lifecycle_command("pause", stage=stage, root=root, runner=runner, sleep=sleep)
        assert paused.lifecycle == "paused"
        state = read_lifecycle_state(root)
        assert state is not None and state.process is None and state.owned_services == ()
        assert "db" in runner.running
        if pre_existing:
            assert "embedding" in runner.running
        else:
            assert "embedding" not in runner.running

        # A run re-arms the same session, pauses at a durable unit, then completes.
        monkeypatch.setenv(INITIAL_ACTION_ALIAS, "run")
        run_lifecycle_command("resume", stage=stage, root=root, runner=runner, sleep=sleep)
        wait_for_units(root, session_id, 1)
        paused = run_lifecycle_command("pause", stage=stage, root=root, runner=runner, sleep=sleep)
        assert paused.lifecycle == "paused"
        assert "db" in runner.running
        if not pre_existing:
            assert "embedding" not in runner.running
        run_lifecycle_command("resume", stage=stage, root=root, runner=runner, sleep=sleep)
        wait_for_lifecycle(root, {"completed"})

        # Pause after completion unloads retained owned services without relabeling the outcome.
        completed = run_lifecycle_command(
            "pause", stage=stage, root=root, runner=runner, sleep=sleep
        )
        assert completed.lifecycle == "completed"
        state = read_lifecycle_state(root)
        assert state is not None and state.process is None and state.owned_services == ()
        assert state.work_complete is True
        assert "db" in runner.running
        if pre_existing:
            assert "embedding" in runner.running
        else:
            assert "embedding" not in runner.running

        stopped = run_lifecycle_command("stop", stage=stage, root=root, runner=runner, sleep=sleep)
        assert stopped.lifecycle == "idle"
        assert "db" in runner.running
        if pre_existing:
            assert "embedding" in runner.running
        else:
            assert "embedding" not in runner.running

        # A preparation failure after the session-owned service started preserves its ownership.
        if not pre_existing:
            monkeypatch.setenv(FAIL_DATABASE_ALIAS, "1")
            failing_root = tmp_path / "failing"
            failing_runner = LocalLifecycleRunner(root=failing_root, running={"db"})
            failing_stage = SupportStage("embedding")
            with pytest.raises(RuntimeError):
                run_lifecycle_command(
                    "start",
                    stage=failing_stage,
                    root=failing_root,
                    runner=failing_runner,
                    sleep=sleep,
                )
            failed = read_lifecycle_state(failing_root)
            assert failed is not None and failed.lifecycle == "failed"
            assert failed.owned_services == ("embedding",)
            assert "db" in failing_runner.running

            # Pause does not finalize: the failed outcome/receipt persist and the service releases.
            failed_pause = run_lifecycle_command(
                "pause",
                stage=failing_stage,
                root=failing_root,
                runner=failing_runner,
                sleep=sleep,
            )
            assert failed_pause.lifecycle == "failed"
            after_pause = read_lifecycle_state(failing_root)
            assert after_pause is not None and after_pause.owned_services == ()
            assert after_pause.process is None
            assert (failing_root / after_pause.session_id / "session.json").is_file()
            assert "embedding" not in failing_runner.running
            assert "db" in failing_runner.running

            # Stop finalizes the failed session to idle with incomplete coverage.
            failed_stop = run_lifecycle_command(
                "stop",
                stage=failing_stage,
                root=failing_root,
                runner=failing_runner,
                sleep=sleep,
            )
            assert failed_stop.lifecycle == "idle"
            final_failed = read_lifecycle_state(failing_root)
            assert final_failed is not None and final_failed.work_complete is False
            assert (failing_root / final_failed.session_id / "session.json").is_file()

        # A session-owned service release failure on stop is recorded safely without losing
        # evidence. A subsequent pause preserves the record and only a completed stop clears it.
        monkeypatch.setenv(FAIL_DATABASE_ALIAS, "1")
        release_root = tmp_path / "release-failure"
        release_runner = LocalLifecycleRunner(root=release_root, running={"db"}, fail_release=True)
        release_stage = SupportStage("embedding")
        # A successful stage finalize leaves a finer breadcrumb behind. The stop owner must regain
        # authority so the subsequent release error names the executing `services` step.
        successful_finalize = release_stage.finalize

        def finalize_then_local_cleanup(context) -> None:
            successful_finalize(context)
            context.failure_step = "local_cleanup"

        release_stage.finalize = finalize_then_local_cleanup  # type: ignore[method-assign]
        with pytest.raises(RuntimeError):
            run_lifecycle_command(
                "start",
                stage=release_stage,
                root=release_root,
                runner=release_runner,
                sleep=sleep,
            )
        failed_release = read_lifecycle_state(release_root)
        assert failed_release is not None and failed_release.owned_services == ("embedding",)
        session_file = release_root / failed_release.session_id / "session.json"
        assert session_file.is_file()

        with pytest.raises(subprocess.CalledProcessError):
            run_lifecycle_command(
                "stop",
                stage=release_stage,
                root=release_root,
                runner=release_runner,
                sleep=sleep,
            )
        recorded = read_lifecycle_state(release_root)
        assert recorded is not None and recorded.stop_failure is not None
        assert recorded.stop_failure.step == "services"
        assert recorded.stop_failure.error_type == "CalledProcessError"
        assert recorded.stop_failure.returncode == 255
        assert recorded.owned_services == ("embedding",)
        assert session_file.is_file()
        assert "synthetic-secret-sentinel" not in recorded.model_dump_json()

        # Pause preserves the recorded stop failure: it never clears it.
        release_runner.fail_release = False
        paused_release = run_lifecycle_command(
            "pause", stage=release_stage, root=release_root, runner=release_runner, sleep=sleep
        )
        assert paused_release.lifecycle == "failed"
        after_pause_release = read_lifecycle_state(release_root)
        assert after_pause_release is not None and after_pause_release.stop_failure is not None

        # A completed stop clears the record and releases the owned service.
        stopped_release = run_lifecycle_command(
            "stop", stage=release_stage, root=release_root, runner=release_runner, sleep=sleep
        )
        assert stopped_release.lifecycle == "idle"
        cleared = read_lifecycle_state(release_root)
        assert cleared is not None and cleared.stop_failure is None
        assert "embedding" not in release_runner.running
    finally:
        runner.close()
        if failing_runner is not None:
            failing_runner.close()
        if release_runner is not None:
            release_runner.close()


def _configure_ingestion_raw_root(
    monkeypatch: pytest.MonkeyPatch, root: Path, raw_data_root: Path
) -> LocalLifecycleRunner:
    """Bind one temporary ingestion state root, raw root and local process boundary."""
    configure_environment(monkeypatch)
    monkeypatch.setattr(local_stages, "stage_state_root", lambda stage: root)
    capture_settings = settings_factory(CaptureSettings).model_copy(
        update={"raw_data_root": raw_data_root}
    )
    monkeypatch.setattr(local_stages, "load_capture_settings", lambda: capture_settings)
    return LocalLifecycleRunner(root=root, running={"db"})


@pytest.mark.parametrize(
    ("kori_override", "normalization_override", "capture_override", "same_identity"),
    [
        ({"KORI_REQUEST_TIMEOUT_SECONDS": 90.0}, {}, {}, True),
        ({"KORI_MAX_ATTEMPTS": 5}, {}, {}, True),
        ({"KORI_RETRY_BACKOFF_SECONDS": 5.0}, {}, {}, True),
        ({"KORI_CONCURRENCY": 2}, {}, {}, True),
        ({}, {}, {"CAPTURE_CHECKPOINT_RESPONSE_COUNT": 20}, True),
        ({}, {}, {"RAW_DATA_ROOT": Path("raw-other")}, True),
        ({"KORI_SEARCH_PAGE_SIZE": 50}, {}, {}, False),
        ({"KORI_BATCH_SIZE": 20}, {}, {}, False),
        ({"KORI_MAX_PARTITION_DEPTH": 4}, {}, {}, False),
        ({}, {"ACTIVE_ACADEMIC_YEAR_WINDOW": 4}, {}, False),
    ],
)
def test_ingestion_identity_ignores_operational_tuning(
    kori_override: dict[str, object],
    normalization_override: dict[str, object],
    capture_override: dict[str, object],
    same_identity: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The identity covers the stage, the configuration, the selected database and the options.

    The configuration is the kori settings without their operational tuning values, plus the
    normalization settings.
    """
    base_kori = settings_factory(KoriSettings)
    base_normalization = settings_factory(NormalizationSettings)
    base_capture = settings_factory(CaptureSettings)
    changed_kori = settings_factory(KoriSettings, **kori_override)
    changed_normalization = settings_factory(NormalizationSettings, **normalization_override)
    changed_capture = settings_factory(CaptureSettings, **capture_override)
    database = SimpleNamespace(postgres_db="course_explorer_test")
    stage = local_stages.IngestionStage()
    options = IngestionOptions(kind="ingestion")

    def identity(
        kori: KoriSettings,
        normalization: NormalizationSettings,
        capture: CaptureSettings,
    ) -> str:
        monkeypatch.setattr(local_stages, "load_kori_settings", lambda: kori)
        monkeypatch.setattr(local_stages, "load_normalization_settings", lambda: normalization)
        monkeypatch.setattr(local_stages, "load_capture_settings", lambda: capture)
        monkeypatch.setattr(local_stages, "load_database_settings", lambda: database)
        return stage.identity_sha256(options)

    baseline = identity(base_kori, base_normalization, base_capture)
    changed = identity(changed_kori, changed_normalization, changed_capture)
    assert (changed == baseline) is same_identity


def test_ingestion_continuation_refuses_changed_retained_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A recorded continuation identity admits its retained bytes and refuses any change."""
    monkeypatch.chdir(tmp_path)
    store = new_store(tmp_path)
    capture_settings = settings_factory(CaptureSettings, RAW_DATA_ROOT=Path("raw"))
    monkeypatch.setattr(local_stages, "load_capture_settings", lambda: capture_settings)
    context = _CheckpointContext(
        IngestionProgress(
            kind="ingestion",
            stage="capture",
            response_count=0,
            verified_response_count=0,
            normalized=False,
        ),
        IngestionOptions(kind="ingestion", manifest_path=store.manifest_relative_path),
    )

    local_stages.IngestionStage().finalize(context)

    retained = context.progress
    assert retained.manifest_path == store.manifest_relative_path
    assert retained.run_id == store.manifest.run_id
    assert retained.manifest_sha256 == store.manifest_sha256
    require_retained_ingestion_manifest(retained.manifest_path, retained.manifest_sha256)

    store.manifest_path.write_bytes(store.manifest_path.read_bytes() + b" ")
    with pytest.raises(ValueError):
        require_retained_ingestion_manifest(retained.manifest_path, retained.manifest_sha256)


def test_ingestion_checkpoints_reuse_published_manifest_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A capture checkpoint records the store's published digest without rereading the file."""
    monkeypatch.chdir(tmp_path)
    store = new_store(tmp_path)

    def reject_first_positive(stage: str, completed: int, total: int | None) -> bool:
        return not (stage == "capture" and completed > 0)

    assert (
        capture_curriculum(
            FixtureSource(),
            store,
            RecordingCapturePersistence(),
            checkpoint_response_count=100,
            on_boundary=reject_first_positive,
        )
        is None
    )
    assert len(store.manifest.responses) > 0
    prefix = len(store.manifest.responses)
    progress = IngestionProgress(
        kind="ingestion",
        stage="capture",
        manifest_path=store.manifest_relative_path,
        run_id=store.manifest.run_id,
        manifest_sha256=store.manifest_sha256,
        response_count=prefix,
        verified_response_count=prefix,
        verification_total=prefix,
        normalized=False,
    )
    context = _CheckpointContext(progress, IngestionOptions(kind="ingestion"))
    original_sha256_file = local_stages.sha256_file
    reread: list[Path] = []

    def guard_manifest_reread(path: Path) -> str:
        if path == store.manifest_path:
            reread.append(path)
            raise AssertionError("a manifest checkpoint reread its own bytes")
        return original_sha256_file(path)

    def fake_run_capture_command(**kwargs: object) -> None:
        on_store_selected = kwargs["on_store_selected"]
        on_boundary = kwargs["on_boundary"]
        assert callable(on_store_selected) and callable(on_boundary)
        on_store_selected(store)
        assert on_boundary("verification", prefix, prefix)
        store.mark_failed(ValueError("synthetic"))
        assert on_boundary("capture", prefix, None)
        return None

    monkeypatch.setattr(local_stages, "sha256_file", guard_manifest_reread)
    monkeypatch.setattr(local_stages, "run_capture_command", fake_run_capture_command)
    assert local_stages.IngestionStage().run(context) is False

    verification = next(
        checkpoint for checkpoint in context.checkpoints if checkpoint.stage == "verification"
    )
    assert verification.verified_response_count == prefix
    assert verification.verification_total == prefix
    checkpoint = context.checkpoints[-1]
    assert checkpoint.stage == "capture"
    assert checkpoint.manifest_sha256 == store.manifest_sha256
    assert checkpoint.verified_response_count == 0
    assert checkpoint.verification_total is None
    assert reread == []


def test_ingestion_idle_stop_prunes_unretained_capture_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Absent-state stop removes every unretained capture, leaving raw-root outsiders untouched."""
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "state"
    runner = _configure_ingestion_raw_root(monkeypatch, root, Path("raw"))

    first = RawCaptureStore.create(Path("raw"))
    second = RawCaptureStore.create(Path("raw"))
    (first.run_root / "tiny.txt").write_text("first\n", encoding="utf-8")
    (second.run_root / "tiny.txt").write_text("second\n", encoding="utf-8")

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "sentinel.txt").write_text("outside\n", encoding="utf-8")
    (second.run_root / "escape").symlink_to(outside, target_is_directory=True)

    backups = tmp_path / "data" / "backups"
    backups.mkdir(parents=True)
    (backups / "sentinel.txt").write_text("backups\n", encoding="utf-8")

    # Status on an absent state preserves every capture directory.
    status = local_stages.run_ingestion_command("status", runner=runner)
    assert status.lifecycle == "idle"
    assert first.run_root.is_dir() and second.run_root.is_dir()

    stopped = local_stages.run_ingestion_command("stop", runner=runner)
    assert stopped.lifecycle == "idle"
    assert not first.run_root.exists() and not second.run_root.exists()
    assert (tmp_path / "raw").is_dir()
    assert (outside / "sentinel.txt").is_file()
    assert (backups / "sentinel.txt").is_file()

    # A repeated idle stop is harmless.
    again = local_stages.run_ingestion_command("stop", runner=runner)
    assert again.lifecycle == "idle"


@pytest.mark.parametrize("unsafe_kind", ["backups_overlap", "symlink_run"])
def test_ingestion_stop_refuses_unsafe_raw_ownership(
    unsafe_kind: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An overlapping backups root or a symlinked run entry refuses before any deletion."""
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "state"

    if unsafe_kind == "backups_overlap":
        backups = tmp_path / "data" / "backups"
        backups.mkdir(parents=True)
        (backups / "sentinel.txt").write_text("backups\n", encoding="utf-8")
        runner = _configure_ingestion_raw_root(monkeypatch, root, Path("data"))
    else:
        runner = _configure_ingestion_raw_root(monkeypatch, root, Path("raw"))
        ordinary = RawCaptureStore.create(Path("raw"))
        (ordinary.run_root / "tiny.txt").write_text("ordinary\n", encoding="utf-8")
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "sentinel.txt").write_text("outside\n", encoding="utf-8")
        (tmp_path / "raw" / "linked-run").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError):
        local_stages.run_ingestion_command("stop", runner=runner)

    if unsafe_kind == "backups_overlap":
        assert (backups / "sentinel.txt").is_file()
    else:
        assert (outside / "sentinel.txt").is_file()
        assert (tmp_path / "raw" / "linked-run").is_symlink()
        assert ordinary.run_root.is_dir()
        assert (ordinary.run_root / "tiny.txt").read_text(encoding="utf-8") == "ordinary\n"
