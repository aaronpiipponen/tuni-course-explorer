"""Contracts for the fixed bounded log reads.

Every read is proven against real temporary receipts and real log files. One small transport double
executes the fixed worker command against a temporary worker tree instead of reaching an SSH
target, so the shell guard and the tail command are the real ones. Each parameter performs exactly
one public read and asserts only that read's outcome. Two parameters place a redirect inside the
unresolved session directory chain, so that refusal is proven at the public boundary.
"""

from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import pytest

from course_explorer.administration import administrative_json, atomic_write_private_text
from course_explorer.config import load_administrative_dataset_settings
from course_explorer.datasets import DatabaseSnapshot
from course_explorer_admin import datasets as datasets_admin
from course_explorer_admin import lifecycle, logs, mechanics
from course_explorer_admin.lifecycle import (
    EmbeddingOptions,
    InferenceOptions,
    IngestionOptions,
    LifecycleSession,
    TranslationOptions,
)
from course_explorer_admin.remote import WorkerDatasetSession
from course_explorer_admin.transport import WorkerAvailabilityError, WorkerCommandError
from tests.datasets._support import INITIAL_ID, REVISION, sample_verification

_STAGE_ROOTS = {
    "ingestion": "data/log-read-tests/ingestion",
    "embedding": "data/log-read-tests/embedding",
    "translation": "data/log-read-tests/translation",
    "inference": "data/log-read-tests/inference",
}
_ADMIN_STATE_ROOT = "data/log-read-tests/admin"
_WORKER_ROOT = "worker"
_STOP_TIMEOUT_SECONDS = "77"
_CREATED_AT = datetime(2026, 10, 18, 9, 30, tzinfo=UTC)
_SENTINEL = "synthetic-captured-output"

# Four session identities of the embedding and inference stages, one worker session identity, and
# one identity no stage ever recorded.
_EMBEDDING_SESSION = "a" * 32
_EMPTY_SESSION = "b" * 32
_SYMLINK_SESSION = "c" * 32
_INFERENCE_SESSION = "d" * 32
_TRANSLATION_SESSION = "e" * 32
_FOREIGN_SESSION = "f" * 32
_NON_REGULAR_SESSION = "1" * 32
_TRANSPORT_FAILURE_SESSION = "2" * 32
_REDIRECTED_SESSION = "3" * 32
_KEEPALIVE_ONLY_SESSION = "4" * 32
_WORKER_RECEIPT_ABSENT_SESSION = "5" * 32
_MALFORMED_RECEIPT_SESSION = "6" * 32
_SYMLINKED_RECEIPT_SESSION = "7" * 32

_OPTIONS = {
    "ingestion": IngestionOptions(kind="ingestion"),
    "embedding": EmbeddingOptions(kind="embedding"),
    "inference": InferenceOptions(kind="inference"),
    "translation": TranslationOptions(kind="translation"),
}


def _bind_log_roots(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Bind every owner root a log read derives, before any read runs."""
    for stage, relative in _STAGE_ROOTS.items():
        monkeypatch.setenv(f"{stage.upper()}_CONTROLLER_STATE_ROOT", relative)
    monkeypatch.setenv("ADMIN_STATE_ROOT", _ADMIN_STATE_ROOT)
    monkeypatch.setenv("TRANSLATION_CONTROLLER_WORKER_PROJECT_ROOT", str(tmp_path / _WORKER_ROOT))
    monkeypatch.setenv("TRANSLATION_CONTROLLER_STOP_TIMEOUT_SECONDS", _STOP_TIMEOUT_SECONDS)
    monkeypatch.setattr(lifecycle, "repository_root", lambda: tmp_path)
    monkeypatch.setattr(datasets_admin, "repository_root", lambda: tmp_path)
    monkeypatch.setattr(logs, "repository_root", lambda: tmp_path)
    return tmp_path


def _write_stage_session(root: Path, stage: str, session_id: str) -> Path:
    """Write one real immutable lifecycle receipt into its stage root's session directory."""
    directory = root / _STAGE_ROOTS[stage] / "current" / session_id
    directory.mkdir(mode=0o700, parents=True)
    atomic_write_private_text(
        directory / "session.json",
        administrative_json(
            LifecycleSession(
                schema_version=1,
                session_id=session_id,
                stage=stage,
                revision=REVISION,
                identity_sha256="a" * 64,
                options=_OPTIONS[stage],
                created_at=_CREATED_AT,
            )
        ),
    )
    return directory


def _write_worker_session(root: Path, stage: str, session_id: str) -> Path:
    """Write one real canonical worker dataset session and return its shared directory."""
    settings = load_administrative_dataset_settings()
    directory = datasets_admin.admin_state_root(settings) / "sessions" / session_id
    directory.mkdir(mode=0o700, parents=True)
    atomic_write_private_text(
        directory / "session.json",
        administrative_json(
            WorkerDatasetSession(
                schema_version=1,
                session_id=session_id,
                revision=REVISION,
                branch="synthetic-branch",
                database_name=settings.database_name(session_id, worker=True),
                stage=stage,
                source_dataset_id=INITIAL_ID,
                course_limit=None,
                input_snapshot=DatabaseSnapshot(
                    schema_version=1,
                    session_id=session_id,
                    revision=REVISION,
                    database_name="course_explorer_test",
                    dump_sha256="a" * 64,
                    verification=sample_verification(),
                ),
            )
        ),
    )
    return directory


def _worker_log_path(root: Path, session_id: str, name: str) -> Path:
    """Return the local path the fixed worker log command derives for one session."""
    return root / _WORKER_ROOT / _ADMIN_STATE_ROOT / "sessions" / session_id / name


def _proof_tree(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Build one temporary proof tree of real receipts, real logs and one worker tree."""
    root = _bind_log_roots(monkeypatch, tmp_path)
    embedded = _write_stage_session(root, "embedding", _EMBEDDING_SESSION)
    (embedded / "runner.out").write_text("first\nsecond\nthird\nfourth\nfifth\n", encoding="utf-8")
    (embedded / "runner.err").write_text("only-error-line\n", encoding="utf-8")
    empty = _write_stage_session(root, "embedding", _EMPTY_SESSION)
    (empty / "runner.out").write_text("", encoding="utf-8")
    symlinked = _write_stage_session(root, "embedding", _SYMLINK_SESSION)
    (symlinked / "runner.out").symlink_to(root / "outside.log")
    (root / "outside.log").write_text(f"{_SENTINEL}\n", encoding="utf-8")

    _write_stage_session(root, "inference", _INFERENCE_SESSION)
    _write_worker_session(root, "inference", _INFERENCE_SESSION)
    worker_runner = _worker_log_path(root, _INFERENCE_SESSION, "runner.log")
    worker_runner.parent.mkdir(mode=0o700, parents=True)
    worker_runner.write_text(
        "worker-one\nworker-two\nworker-three\nworker-four\n", encoding="utf-8"
    )

    _write_worker_session(root, "inference", _NON_REGULAR_SESSION)
    _write_stage_session(root, "inference", _NON_REGULAR_SESSION)
    non_regular = _worker_log_path(root, _NON_REGULAR_SESSION, "runner.log")
    non_regular.parent.mkdir(mode=0o700, parents=True)
    non_regular.symlink_to(root / "outside.log")
    _write_stage_session(root, "inference", _TRANSPORT_FAILURE_SESSION)
    _write_worker_session(root, "inference", _TRANSPORT_FAILURE_SESSION)

    translation = _write_stage_session(root, "translation", _TRANSLATION_SESSION)
    shared = _write_worker_session(root, "translation", _TRANSLATION_SESSION)
    (shared / "keepalive.log").write_text("keepalive-one\nkeepalive-two\n", encoding="utf-8")
    assert translation.is_dir()

    # A listed lifecycle session can fail before its worker receipt or shared directory exists.
    _write_stage_session(root, "translation", _KEEPALIVE_ONLY_SESSION)
    _write_stage_session(root, "inference", _WORKER_RECEIPT_ABSENT_SESSION)
    settings = load_administrative_dataset_settings()
    absent_receipt = (
        datasets_admin.admin_state_root(settings) / "sessions" / _WORKER_RECEIPT_ABSENT_SESSION
    )
    absent_receipt.mkdir(mode=0o700, parents=True)

    _write_stage_session(root, "translation", _MALFORMED_RECEIPT_SESSION)
    malformed = _write_worker_session(root, "translation", _MALFORMED_RECEIPT_SESSION)
    (malformed / "session.json").write_text("{not-json", encoding="utf-8")
    _write_stage_session(root, "inference", _SYMLINKED_RECEIPT_SESSION)
    symlinked_receipt = _write_worker_session(root, "inference", _SYMLINKED_RECEIPT_SESSION)
    receipt_path = symlinked_receipt / "session.json"
    receipt_target = root / "outside-receipt.json"
    receipt_target.write_text(receipt_path.read_text(encoding="utf-8"), encoding="utf-8")
    receipt_path.unlink()
    receipt_path.symlink_to(receipt_target)
    return root


class _LocalWorkerLogTransport:
    """Execute the fixed worker log command against the temporary worker tree instead of SSH."""

    def __init__(self, *, unavailable: bool = False) -> None:
        self.unavailable = unavailable
        self.calls: list[tuple[tuple[str, ...], PurePosixPath, object, object]] = []

    def run(self, argv, *, cwd, env=None, stdin_path=None, timeout=None) -> bytes:
        self.calls.append((tuple(argv), cwd, env, timeout))
        if self.unavailable:
            raise WorkerAvailabilityError(None)
        completed = subprocess.run(
            ["bash", "-c", argv[2]],
            cwd=str(cwd),
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            # The raised error carries the process status.
            raise WorkerCommandError(completed.returncode, phase="command")
        return completed.stdout


class _EmbeddingLogBoundary:
    """Answer the one fixed Compose log read without running a real command."""

    def __init__(self, *, text: bytes, fail: bool) -> None:
        self.text = text
        self.fail = fail
        self.calls: list[tuple[str, ...]] = []

    def run(self, argv, *, cwd=None, env=None, stdin_path=None, stdout_path=None, timeout=None):
        command = tuple(argv)
        self.calls.append(command)
        if self.fail:
            raise subprocess.CalledProcessError(
                1, list(command), output=_SENTINEL.encode(), stderr=_SENTINEL.encode()
            )
        return subprocess.CompletedProcess(list(command), 0, stdout=self.text, stderr=b"")


def _tree_state(root: Path) -> dict[str, object]:
    """Return the bytes of every file, and the target of every symlink, under the proof tree."""
    state: dict[str, object] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            state[path.relative_to(root).as_posix()] = f"symlink:{os.readlink(path)}"
        elif path.is_file():
            state[path.relative_to(root).as_posix()] = path.read_bytes()
    return state


@pytest.mark.parametrize(
    ("case", "stage", "session_id", "source", "lines"),
    [
        ("server-stdout", "embedding", _EMBEDDING_SESSION, "server-stdout", 2),
        ("server-stdout-empty", "embedding", _EMPTY_SESSION, "server-stdout", 4),
        ("server-stderr-absent", "inference", _INFERENCE_SESSION, "server-stderr", 3),
        ("server-stdout-symlink", "embedding", _SYMLINK_SESSION, "server-stdout", 4),
        (
            "server-stdout-parent-symlink",
            "ingestion",
            _REDIRECTED_SESSION,
            "server-stdout",
            2,
        ),
        ("server-stdout-root-symlink", "ingestion", _REDIRECTED_SESSION, "server-stdout", 2),
        ("keepalive", "translation", _TRANSLATION_SESSION, "keepalive", 1),
        (
            "keepalive-absent-shared-directory",
            "translation",
            _KEEPALIVE_ONLY_SESSION,
            "keepalive",
            2,
        ),
        (
            "keepalive-malformed-receipt",
            "translation",
            _MALFORMED_RECEIPT_SESSION,
            "keepalive",
            2,
        ),
        ("keepalive-of-local-stage", "embedding", _EMBEDDING_SESSION, "keepalive", 1),
        ("foreign-session", "embedding", _FOREIGN_SESSION, "server-stdout", 1),
        ("invalid-line-count", "embedding", _EMBEDDING_SESSION, "server-stdout", 0),
        ("worker-runner", "inference", _INFERENCE_SESSION, "worker-runner", 3),
        ("worker-runtime-absent", "inference", _INFERENCE_SESSION, "worker-runtime", 3),
        (
            "worker-runner-absent-receipt",
            "inference",
            _WORKER_RECEIPT_ABSENT_SESSION,
            "worker-runner",
            2,
        ),
        (
            "worker-runner-symlinked-receipt",
            "inference",
            _SYMLINKED_RECEIPT_SESSION,
            "worker-runner",
            2,
        ),
        ("worker-runner-non-regular", "inference", _NON_REGULAR_SESSION, "worker-runner", 3),
        (
            "worker-runner-unavailable",
            "inference",
            _TRANSPORT_FAILURE_SESSION,
            "worker-runner",
            3,
        ),
        ("embedding", "embedding", None, "embedding-runtime", 2),
        ("embedding-failure", "embedding", None, "embedding-runtime", 2),
    ],
)
def test_fixed_log_read_uses_only_its_selected_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    case: str,
    stage: str,
    session_id: str | None,
    source: str,
    lines: int,
) -> None:
    """One read returns one fixed source's last lines, an unavailable result, or a raised error."""
    root = _proof_tree(monkeypatch, tmp_path)
    worker_root = root / _WORKER_ROOT
    runner = mechanics.SubprocessRunner()

    if source == "embedding-runtime":
        boundary = _EmbeddingLogBoundary(
            text=b"embedding-one\nembedding-two\n", fail=case.endswith("-failure")
        )
        before_embedding = _tree_state(root)
        report: logs.LogReadReport | None = None
        if case.endswith("-failure"):
            with pytest.raises(subprocess.CalledProcessError) as failure:
                logs.read_embedding_log(lines=lines, runner=boundary)
            assert _SENTINEL not in str(failure.value)
        else:
            report = logs.read_embedding_log(lines=lines, runner=boundary)
        prefix = mechanics.compose_prefix(non_interactive=True)
        assert boundary.calls == [
            (*prefix, "logs", "--no-color", "--no-log-prefix", "--tail", str(lines), "embedding")
        ]
        if report is not None:
            assert report.stage == "embedding" and report.session_id is None
            assert report.source == "embedding-runtime" and report.available is True
            assert report.text == "embedding-one\nembedding-two\n"
        assert _tree_state(root) == before_embedding
        return

    assert stage in _OPTIONS and session_id is not None
    if case in {"server-stdout-parent-symlink", "server-stdout-root-symlink"}:
        # One redirecting component in the unresolved stage directory chain, with a real receipt and
        # a synthetic log behind the redirect.
        redirected = _write_stage_session(tmp_path / "redirected", stage, session_id)
        (redirected / "runner.out").write_text(f"{_SENTINEL}\n", encoding="utf-8")
        stage_root = tmp_path / _STAGE_ROOTS[stage]
        if case == "server-stdout-parent-symlink":
            stage_root.symlink_to(redirected.parent.parent)
        else:
            stage_root.mkdir(mode=0o700, parents=True)
            (stage_root / "current").symlink_to(redirected.parent)
    transport = _LocalWorkerLogTransport(unavailable=case == "worker-runner-unavailable")
    monkeypatch.setattr(logs, "_transport", lambda _runner, _connection: transport)
    before = _tree_state(root)

    def read() -> logs.LogReadReport:
        return logs.read_session_log(
            stage,
            session_id,
            source,
            lines=lines,
            runner=runner,  # type: ignore[arg-type]
        )

    if case == "server-stdout":
        report = read()
        assert report.available is True and report.text == "fourth\nfifth\n"
    elif case == "server-stdout-empty":
        report = read()
        assert report.available is True and report.text == ""
    elif case == "server-stderr-absent":
        report = read()
        assert report.available is False and report.text is None
    elif case == "keepalive":
        report = read()
        assert report.available is True and report.text == "keepalive-two\n"
    elif case in {"keepalive-absent-shared-directory", "worker-runner-absent-receipt"}:
        report = read()
        assert report.available is False and report.text is None
    elif case in {"keepalive-malformed-receipt", "worker-runner-symlinked-receipt"}:
        with pytest.raises(ValueError):
            read()
    elif case == "worker-runner":
        report = read()
        assert report.available is True and report.text == "worker-two\nworker-three\nworker-four\n"
    elif case == "worker-runtime-absent":
        report = read()
        assert report.available is False and report.text is None
    elif case == "server-stdout-symlink":
        with pytest.raises(ValueError) as refused:
            read()
        assert _SENTINEL not in str(refused.value)
    elif case in {"server-stdout-parent-symlink", "server-stdout-root-symlink"}:
        with pytest.raises(ValueError) as refused:
            read()
        assert _SENTINEL not in str(refused.value)
    elif case == "keepalive-of-local-stage":
        with pytest.raises(ValueError):
            read()
    elif case == "foreign-session":
        with pytest.raises(ValueError):
            read()
    elif case == "invalid-line-count":
        with pytest.raises(ValueError):
            read()
    elif case == "worker-runner-non-regular":
        with pytest.raises(WorkerCommandError) as failed:
            read()
        assert failed.value.returncode == 1 and failed.value.phase == "command"
        assert _SENTINEL not in str(failed.value)
    else:  # worker-runner-unavailable
        with pytest.raises(WorkerAvailabilityError):
            read()

    assert stage is not None
    assert _tree_state(root) == before
    no_transport = {
        "keepalive-absent-shared-directory",
        "keepalive-malformed-receipt",
        "worker-runner-absent-receipt",
        "worker-runner-symlinked-receipt",
    }
    if case in no_transport:
        assert transport.calls == []
    elif source in {"worker-runner", "worker-runtime"}:
        # Exactly one worker invocation, with no setup, preflight, keepalive or retry.
        assert len(transport.calls) == 1
        argv, cwd, env, timeout = transport.calls[0]
        assert len(argv) == 3 and argv[0] == "bash" and argv[1] == "-c"
        assert cwd == PurePosixPath(str(worker_root))
        assert env is None
        assert timeout == float(_STOP_TIMEOUT_SECONDS)
        script = argv[2]
        assert "\n" not in script
        assert f"tail -n {lines} -- " in script
        assert "uv" not in script and "pkill" not in script and "sleep" not in script
    else:
        assert transport.calls == []
