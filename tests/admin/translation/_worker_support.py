"""Shared fixtures for the translation worker-side controller contracts.

This support module owns the deterministic translation settings/environment, the canonical session
and policy seeding, the scripted process/runtime doubles, and the output/control/state helpers the
worker and canonical-worker feature groups drive the real worker entrypoints through.
"""

from __future__ import annotations

import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from course_explorer import administration
from course_explorer.administration import administrative_json, atomic_write_private_text
from course_explorer.config import (
    load_administrative_dataset_settings,
    load_translation_settings,
)
from course_explorer.datasets import DatabaseSnapshot
from course_explorer.enums import (
    TeachingTextField,
    TeachingTextLanguage,
    TranslationMethod,
)
from course_explorer.teaching_text.service import DerivedTranslationInput
from course_explorer.translation.service import TranslationRunReport, TranslationSelectionCount
from course_explorer_admin import datasets as datasets_module
from course_explorer_admin import mechanics, remote, worker_session
from course_explorer_admin.remote import WorkerDatasetSession, worker_dataset_session_directory
from course_explorer_admin.translation.controller import (
    TranslationControllerControl,
    TranslationControllerPolicy,
    TranslationControllerWorkerState,
)
from tests.config._support import (
    ADMIN_DATASET_KEYS,
    POSTGRES_KEYS,
    TRANSLATION_KEYS,
    WORKER_GPU_REBOOT_KEYS,
)
from tests.datasets._support import sample_verification
from tests.inference._http_support import completion_response

SESSION_ID = "0123456789abcdef0123456789abcdef"
REVISION = "a" * 40
SOURCE_ID = "f" * 32
STARTED_AT = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


# The translation policy comes from the shared composed public mapping. Only the fake
# artifact identity and the admin root are overridden for these worker contracts.
TRANSLATION_ENV = {
    **POSTGRES_KEYS,
    **TRANSLATION_KEYS,
    "POSTGRES_PASSWORD": "synthetic-secret",
    "SELECTED_DATASET_ENABLED": "0",
    "ADMIN_STATE_ROOT": "data/admin",
    "TRANSLATION_ARTIFACT_PATH": "models/model.gguf",
    "TRANSLATION_ARTIFACT_SHA256": "d" * 64,
    "TRANSLATION_RUNTIME_REVISION": "e" * 40,
}


def report(*, desired: int, generated: int, output: int) -> TranslationRunReport:
    return TranslationRunReport(
        canonical_course_count=0,
        representative_course_count=0,
        no_representative_course_count=0,
        active_representative_count=0,
        inactive_representative_count=0,
        fields=tuple(
            TranslationSelectionCount(
                field=field,
                language=language,
                official_target_count=0,
                current_derived_count=0,
                pending_count=0,
                missing_source_count=0,
            )
            for field in TeachingTextField
            for language in TeachingTextLanguage
        ),
        desired_count=desired,
        reused_count=0,
        generated_count=generated,
        output_count=output,
    )


def configure(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    """Point every canonical loader at one temporary repository with deterministic settings."""
    for key, value in TRANSLATION_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("TRANSLATION_CONTROLLER_SSH_TARGET", "test-worker")
    monkeypatch.setenv("TRANSLATION_CONTROLLER_SSH_CONNECT_TIMEOUT_SECONDS", "10")
    monkeypatch.setenv("TRANSLATION_CONTROLLER_WSL_DISTRIBUTION", "Ubuntu-24.04")
    monkeypatch.setenv("TRANSLATION_CONTROLLER_WORKER_PROJECT_ROOT", str(root))
    monkeypatch.setenv("TRANSLATION_CONTROLLER_STATE_ROOT", "state")
    monkeypatch.setenv("TRANSLATION_CONTROLLER_HEALTH_ATTEMPTS", "3")
    monkeypatch.setenv("TRANSLATION_CONTROLLER_HEALTH_INTERVAL_SECONDS", "0.01")
    monkeypatch.setenv("TRANSLATION_CONTROLLER_STOP_TIMEOUT_SECONDS", "60")
    for key, value in WORKER_GPU_REBOOT_KEYS.items():
        monkeypatch.setenv(key, value)
    for key, value in ADMIN_DATASET_KEYS.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(administration, "repository_root", lambda: root)
    monkeypatch.setattr(remote, "repository_root", lambda: root)
    monkeypatch.setattr(datasets_module, "repository_root", lambda: root)
    # The canonical worker run is invoked with the raw session database pinned and the selected
    # dataset explicitly disabled. The test sets exactly that environment.
    monkeypatch.setenv(
        "POSTGRES_DB", load_administrative_dataset_settings().database_name(SESSION_ID, worker=True)
    )
    monkeypatch.setenv("SELECTED_DATASET_ENABLED", "0")
    # Script the shared canonical restore at its boundary. The canonical worker test and the
    # disposable SQL proof own the real restore mechanics.
    monkeypatch.setattr(
        remote, "prepare_worker_database", lambda session, *, runner: sample_verification()
    )
    # The real received-database schema barrier opens a database. These network-free contracts
    # stub only its success result, while the disposable SQL proof keeps the real checker.
    monkeypatch.setattr(worker_session, "require_worker_database_schema", lambda session: None)


def session() -> WorkerDatasetSession:
    """Return one genuine canonical translation session record for this fixture."""
    settings = load_administrative_dataset_settings()
    return WorkerDatasetSession(
        schema_version=1,
        session_id=SESSION_ID,
        revision=REVISION,
        branch="course-search",
        database_name=settings.database_name(SESSION_ID, worker=True),
        stage="translation",
        source_dataset_id=SOURCE_ID,
        course_limit=10,
        input_snapshot=DatabaseSnapshot(
            schema_version=1,
            session_id=SESSION_ID,
            revision=REVISION,
            database_name="course_explorer",
            dump_sha256="c" * 64,
            verification=sample_verification(),
        ),
    )


def seed_directory(
    root: Path, session_value: WorkerDatasetSession
) -> tuple[Path, WorkerDatasetSession]:
    """Write one canonical session and policy directly, without capture or admission."""
    directory = worker_dataset_session_directory(SESSION_ID)
    directory.mkdir(mode=0o700, parents=True)
    atomic_write_private_text(directory / "session.json", administrative_json(session_value))
    atomic_write_private_text(
        directory / "policy.json",
        administrative_json(
            TranslationControllerPolicy(
                schema_version=2,
                session_id=SESSION_ID,
                revision=REVISION,
                translation_model=load_translation_settings().provenance_model,
            )
        ),
    )
    return directory, session_value


class FakeRunner:
    """Scripted process runner recording commands and answering live git/ss observations."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def run(self, argv, *, cwd=None, env=None, stdin_path=None, stdout_path=None, timeout=None):
        command = tuple(argv)
        self.calls.append(command)
        output = b""
        if command[:3] == ("git", "branch", "--show-current"):
            output = b"course-search\n"
        elif command[:2] == ("git", "rev-parse"):
            output = (REVISION + "\n").encode()
        elif command[:2] == ("git", "status"):
            output = b""
        elif command[:1] == ("ss",):
            output = b""
        return subprocess.CompletedProcess(list(command), 0, stdout=output, stderr=b"")

    def popen(self, argv, *, cwd=None, env=None, stdin_path=None, stdout_path, stderr_path):
        raise AssertionError("no popen expected")


def write_control(directory: Path, action: str) -> None:
    atomic_write_private_text(
        directory / "control.json",
        administrative_json(
            TranslationControllerControl(
                schema_version=1,
                session_id=SESSION_ID,
                revision=REVISION,
                requested_action=action,  # type: ignore[arg-type]
            )
        ),
    )


def write_state(directory: Path, **overrides) -> TranslationControllerWorkerState:
    values = {
        "schema_version": 2,
        "session_id": SESSION_ID,
        "revision": REVISION,
        "lifecycle": "prepared",
        "desired_count": 2,
        "completed_count": 0,
        "started_at": STARTED_AT,
        "active_seconds": 0.0,
    }
    values.update(overrides)
    state = TranslationControllerWorkerState(**values)  # type: ignore[arg-type]
    atomic_write_private_text(directory / "state.json", administrative_json(state))
    return state


def owned_record(pid: int) -> mechanics.OwnedProcessRecord:
    """Return one genuine-schema boot/argv ownership record for a scripted process observation."""
    return mechanics.OwnedProcessRecord(
        schema_version=1,
        pid=pid,
        argv=("python", "-m", "course_explorer_admin.translation.controller_worker", "run"),
        boot_id=mechanics.current_boot_id(),
    )


def write_runner_record(directory: Path, pid: int) -> None:
    """Publish one runner ownership record for the scripted observation."""
    atomic_write_private_text(directory / "runner.json", administrative_json(owned_record(pid)))


def write_runtime_record(directory: Path, pid: int) -> None:
    """Publish one runtime ownership record for the scripted observation."""
    atomic_write_private_text(directory / "runtime.json", administrative_json(owned_record(pid)))


def script_owned_process_is_alive(monkeypatch: pytest.MonkeyPatch, live_pids: set[int]) -> None:
    """Script the shared boot/argv observation instead of relying on arbitrary kernel liveness."""
    monkeypatch.setattr(mechanics, "owned_process_is_alive", lambda record: record.pid in live_pids)


class FakeOwnedRuntime:
    """Scripted public shared runtime owner replacing ``OwnedWorkerRuntime`` in worker tests."""

    instances: list[FakeOwnedRuntime] = []

    def __init__(self, runner, *, root, directory, sleep=time.sleep):
        self.runner = runner
        self.root = root
        self.directory = directory
        self.sleep = sleep
        self.pid = 4242
        self.started = False
        self.stop_count = 0
        FakeOwnedRuntime.instances.append(self)

    def start(self, spec, *, attempts, interval, timeout):
        self.started = True
        self.spec = spec
        return self.pid

    def stop(self, *, timeout, interval):
        self.stop_count += 1


def entry(text: str) -> DerivedTranslationInput:
    return DerivedTranslationInput(
        sisu_course_unit_id="course-v1",
        field=TeachingTextField.NAME,
        language=TeachingTextLanguage.EN,
        source_language=TeachingTextLanguage.FI,
        source_text="Nimi",
        text=text,
        translation_method=TranslationMethod.MODEL,
        translation_model="model",
        generated_at=STARTED_AT,
    )


def write_output(directory: Path, entries: list[DerivedTranslationInput]) -> str:
    payload = json.dumps([item.model_dump(mode="json") for item in entries], ensure_ascii=False)
    atomic_write_private_text(directory / "output.json", payload + "\n")
    import hashlib

    return hashlib.sha256((directory / "output.json").read_bytes()).hexdigest()


def load_control(directory: Path):
    return worker_session.read_control(directory, session())


def _valid_chat_response() -> dict:
    """Return the configured runtime's one valid chat-completion response shape."""
    settings = load_translation_settings()
    return completion_response(
        content="Name",
        model=settings.translation_model_alias,
        fingerprint=f"b7823-{settings.translation_runtime_revision[:9]}",
    ).json()
