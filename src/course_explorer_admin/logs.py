"""The one session listing and the fixed bounded reads of the operator's logs.

This module owns two read-only operations. It discovers the four stage roots' own session receipts
and lists them newest first, and it reads the last lines of exactly one fixed log source of one
discovered session: the two server-side runner streams beside a lifecycle receipt, the shared
session directory's ``keepalive.log``, and the two worker logs a remote session writes, which are
read on demand over the SSH/WSL transport.

Every read is confined to a fixed basename beneath a derived directory, so no caller supplies a
path or a filename. A log the product never wrote is reported as unavailable rather than created,
and a read failure is raised rather than reported as an empty log. Log text is the operator's
transient result: it is never logged, stored, or included in an error.
"""

from __future__ import annotations

import re
import shlex
import stat
from collections import deque
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict

from course_explorer.administration import load_private_model, repository_root, session_directory
from course_explorer.config import WorkerConnectionSettings, load_worker_connection_settings
from course_explorer.datasets import DatasetId
from course_explorer_admin import mechanics
from course_explorer_admin.lifecycle import LifecycleSession, StageName, stage_state_root
from course_explorer_admin.remote import (
    WorkerDatasetSession,
    load_worker_dataset_session,
    remote_worker_session_directory,
    worker_dataset_session_directory,
)
from course_explorer_admin.transport import SshWslTransport, WorkerCommandError

type LogSource = Literal[
    "server-stdout", "server-stderr", "keepalive", "worker-runner", "worker-runtime"
]

# The fixed source set in report order, derived from the one source literal.
LOG_SOURCES: tuple[str, ...] = get_args(LogSource.__value__)

_SESSION_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
_STAGE_NAMES: tuple[StageName, ...] = ("ingestion", "embedding", "translation", "inference")
_REMOTE_STAGES: tuple[StageName, ...] = ("translation", "inference")

# The two server-side streams a lifecycle receipt holds, and the fixed basename of each.
_SERVER_SOURCES = {"server-stdout": "runner.out", "server-stderr": "runner.err"}

# The three sources that need a recorded worker session. The two worker logs live on the worker and
# the keepalive log lives in the shared server session directory.
_KEEPALIVE_SOURCE = "keepalive"
_WORKER_SOURCES = {"worker-runner": "runner.log", "worker-runtime": "runtime.log"}
_KEEPALIVE_LOG = "keepalive.log"

# The one exit status the fixed worker read reserves for an absent log.
_WORKER_ABSENT_STATUS = 3

# The one embedding service whose container log this module reads, and the source name it reports.
_EMBEDDING_SERVICE = "embedding"
_EMBEDDING_SOURCE = "embedding-runtime"


class _LogModel(BaseModel):
    """Frozen, closed DTO base for the log-read contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class LogSessionEntry(_LogModel):
    """One discovered session: its stage, its identity and the time its receipt records."""

    stage: StageName
    session_id: DatasetId
    created_at: datetime


class LogSessionsReport(_LogModel):
    """Every discovered session of the four stage roots, newest first."""

    schema_version: Literal[1] = 1
    sessions: tuple[LogSessionEntry, ...]


class LogReadReport(_LogModel):
    """One transient bounded log read.

    ``available`` is ``False`` only for a log the owning stage or worker recorded as absent, and
    ``text`` then carries ``None``. A log file that holds no lines is available with empty text,
    and ``session_id`` is ``None`` for the embedding container log.
    """

    schema_version: Literal[1] = 1
    stage: StageName
    session_id: str | None
    source: str
    available: bool
    text: str | None


def _require_directory(path: Path, *, message: str, allow_absent: bool = False) -> bool:
    """Guard one unresolved directory chain and report whether the whole chain exists.

    Every component from the filesystem root through ``path`` is inspected with ``lstat`` metadata
    in that order, so a symlink or another non-directory is refused before a descendant is traversed.
    A component that does not exist returns ``False`` while ``allow_absent`` is true, and otherwise
    raises. Every other metadata error propagates. The supplied path is inspected as given and never
    resolved, and no directory is created.
    """
    for candidate in reversed((path, *path.parents)):
        try:
            metadata = candidate.lstat()
        except FileNotFoundError:
            if allow_absent:
                return False
            raise ValueError(f"{message} must be a directory that is not a symlink") from None
        if not stat.S_ISDIR(metadata.st_mode):
            raise ValueError(f"{message} must be a directory that is not a symlink")
    return True


def _require_line_count(lines: int) -> None:
    """Refuse anything that is not a positive whole line count."""
    if isinstance(lines, bool) or not isinstance(lines, int) or lines <= 0:
        raise ValueError("the log line count must be a positive whole number")


def _require_stage(stage: str) -> None:
    """Refuse a stage name outside the four stage owners."""
    if stage not in _STAGE_NAMES:
        raise ValueError("stage must be ingestion, embedding, translation, or inference")


def _require_source(stage: str, source: str) -> None:
    """Refuse a source outside the fixed set, and a worker source of a local stage."""
    if source not in LOG_SOURCES:
        raise ValueError("log source must be one of the fixed log sources")
    if source not in _SERVER_SOURCES and stage not in _REMOTE_STAGES:
        raise ValueError("this log source belongs to the remote worker stages alone")


def _require_session_id(session_id: str) -> None:
    """Refuse anything that is not a 32-lowercase-hexadecimal session identity."""
    if _SESSION_ID_PATTERN.fullmatch(session_id) is None:
        raise ValueError("session id must be 32 lowercase hexadecimal characters")


def _read_session_directory(stage: StageName, session_id: str) -> tuple[Path, LifecycleSession]:
    """Return one session's confined directory and receipt behind the confinement guards.

    Every directory from the filesystem root through the session directory must be a real
    directory, so a redirect anywhere in that unresolved chain refuses before a descendant path is
    read. The receipt must name the requested session and this stage. A session id that the stage
    never recorded therefore refuses before any log path is built.
    """
    root = stage_state_root(stage)
    _require_directory(root, message="the stage root")
    directory = session_directory(root, session_id)
    _require_directory(directory, message="the session directory")
    session = load_private_model(directory / "session.json", LifecycleSession)
    if session.session_id != session_id or session.stage != stage:
        raise ValueError("the session receipt must name the requested session and stage")
    return directory, session


def list_log_sessions() -> LogSessionsReport:
    """List the discovered sessions of the four stage roots, newest first.

    Discovery reads each stage root's own session receipts and creates nothing. Only a genuinely
    absent stage root contributes no entry, and a stage root behind a redirect refuses rather than
    reporting an empty inventory. A directory name that is not a session identity is ignored. A
    session-named directory whose receipt is missing, malformed or of another stage fails loudly
    rather than being listed with guessed values.
    """
    entries: list[LogSessionEntry] = []
    for stage in _STAGE_NAMES:
        root = stage_state_root(stage)
        if not _require_directory(root, message="the stage root", allow_absent=True):
            continue
        for child in sorted(root.iterdir()):
            if _SESSION_ID_PATTERN.fullmatch(child.name) is None:
                continue
            _, session = _read_session_directory(stage, child.name)
            entries.append(
                LogSessionEntry(
                    stage=stage,
                    session_id=session.session_id,
                    created_at=session.created_at,
                )
            )
    # Two stable sorts keep the newest receipt first and break a shared time by stage and identity.
    entries.sort(key=lambda entry: (entry.stage, entry.session_id))
    entries.sort(key=lambda entry: entry.created_at, reverse=True)
    return LogSessionsReport(sessions=tuple(entries))


def _tail(path: Path, lines: int) -> str:
    """Return the last ``lines`` of one text file, keeping the file's own line endings."""
    with path.open("r", encoding="utf-8", newline="") as stream:
        return "".join(deque(stream, maxlen=lines))


def _tail_fixed_file(
    path: Path, *, stage: StageName, session_id: str | None, source: str, lines: int
) -> LogReadReport:
    """Read one fixed local log file, or report the absence its owner recorded."""
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError("a log must be a regular file that is not a symlink")
    if not path.exists():
        return LogReadReport(
            stage=stage, session_id=session_id, source=source, available=False, text=None
        )
    return LogReadReport(
        stage=stage,
        session_id=session_id,
        source=source,
        available=True,
        text=_tail(path, lines),
    )


def _worker_session_for_log(stage: StageName, session_id: str) -> WorkerDatasetSession | None:
    """Return one recorded worker session, or ``None`` when its receipt is genuinely absent.

    The shared session directory is guarded without resolution, and a missing directory or
    ``session.json`` is the absence a lifecycle session can leave before it prepares its worker
    resources. A symlinked or non-regular receipt, a malformed receipt and a receipt of another
    stage fail instead of being reported as absence.
    """
    directory = worker_dataset_session_directory(session_id)
    if not _require_directory(directory, message="the worker session directory", allow_absent=True):
        return None
    receipt = directory / "session.json"
    if receipt.is_symlink() or (receipt.exists() and not receipt.is_file()):
        raise ValueError("worker session receipt must be a regular non-symlink file")
    if not receipt.exists():
        return None
    session = load_worker_dataset_session(session_id)
    if session.stage != stage:
        raise ValueError("the recorded worker session must name the requested stage")
    return session


def _read_keepalive_log(stage: StageName, session_id: str, lines: int) -> LogReadReport:
    """Tail the shared session directory's keepalive log while that file exists."""
    if _worker_session_for_log(stage, session_id) is None:
        return LogReadReport(
            stage=stage,
            session_id=session_id,
            source=_KEEPALIVE_SOURCE,
            available=False,
            text=None,
        )
    directory = worker_dataset_session_directory(session_id)
    return _tail_fixed_file(
        directory / _KEEPALIVE_LOG,
        stage=stage,
        session_id=session_id,
        source=_KEEPALIVE_SOURCE,
        lines=lines,
    )


def _transport(
    runner: mechanics.ProcessRunner, connection: WorkerConnectionSettings
) -> SshWslTransport:
    """Construct the one SSH/WSL transport a worker log read uses."""
    return SshWslTransport(runner, connection)


def _worker_log_script(path: PurePosixPath, lines: int) -> str:
    """Build the one fixed single-line guard-and-tail script for a derived worker log path.

    The walk checks every ancestor from the root to the log's parent in that order. A symlink is
    refused before existence is tested, and an ancestor must be a searchable directory, so an
    inaccessible descendant is never reported as an absent log. Exit 3 is the one absence status the
    caller classifies. Every derived path is quoted.
    """
    parts = path.parts
    ancestors = [PurePosixPath(parts[0])]
    for part in parts[1:-1]:
        ancestors.append(ancestors[-1] / part)
    directories = " ".join(shlex.quote(str(candidate)) for candidate in ancestors)
    target = shlex.quote(str(path))
    return (
        f"for __ce_directory in {directories}; do "
        'if test -L "$__ce_directory"; then exit 1; fi; '
        'if test ! -e "$__ce_directory"; then exit 3; fi; '
        'if test ! -d "$__ce_directory" || test ! -x "$__ce_directory"; then exit 1; fi; '
        "done; "
        f"if test -L {target}; then exit 1; fi; "
        f"if test ! -e {target}; then exit 3; fi; "
        f"if test ! -f {target}; then exit 1; fi; "
        f"tail -n {lines} -- {target} || exit 1"
    )


def _read_worker_log(
    stage: StageName,
    session_id: str,
    source: str,
    lines: int,
    *,
    runner: mechanics.ProcessRunner,
) -> LogReadReport:
    """Read one fixed worker log on demand over the SSH/WSL transport.

    The recorded canonical session supplies the worker directory, so the path is derived server
    side. A genuinely absent worker receipt reports the log unavailable without loading worker
    settings or opening the transport. Exactly one transport invocation runs, and a command-phase
    absence status is an unavailable log.
    """
    if _worker_session_for_log(stage, session_id) is None:
        return LogReadReport(
            stage=stage, session_id=session_id, source=source, available=False, text=None
        )
    connection = load_worker_connection_settings()
    remote_path = remote_worker_session_directory(connection, session_id) / _WORKER_SOURCES[source]
    try:
        payload = _transport(runner, connection).run(
            ("bash", "-c", _worker_log_script(remote_path, lines)),
            cwd=PurePosixPath(str(connection.worker_project_root)),
            timeout=connection.stop_timeout_seconds,
        )
    except WorkerCommandError as exc:
        if exc.phase == "command" and exc.returncode == _WORKER_ABSENT_STATUS:
            return LogReadReport(
                stage=stage, session_id=session_id, source=source, available=False, text=None
            )
        raise
    return LogReadReport(
        stage=stage,
        session_id=session_id,
        source=source,
        available=True,
        text=payload.decode("utf-8"),
    )


def read_session_log(
    stage: StageName,
    session_id: str,
    source: LogSource,
    *,
    lines: int,
    runner: mechanics.ProcessRunner,
) -> LogReadReport:
    """Read the last ``lines`` of one fixed log source of one discovered session.

    The line count, the stage, the source and the session identity are validated before any settings
    load or file read, and the requested session must be the stage's own recorded receipt. A worker
    source reads over the transport, because that log lives on the worker.
    """
    _require_line_count(lines)
    _require_stage(stage)
    _require_source(stage, source)
    _require_session_id(session_id)
    directory, _ = _read_session_directory(stage, session_id)
    if source in _SERVER_SOURCES:
        return _tail_fixed_file(
            directory / _SERVER_SOURCES[source],
            stage=stage,
            session_id=session_id,
            source=source,
            lines=lines,
        )
    if source == _KEEPALIVE_SOURCE:
        return _read_keepalive_log(stage, session_id, lines)
    return _read_worker_log(stage, session_id, source, lines, runner=runner)


def read_embedding_log(*, lines: int, runner: mechanics.ProcessRunner) -> LogReadReport:
    """Read the last ``lines`` of the embedding service's own container log.

    The read runs the configured Compose project's log command, which does not start the service. A
    successful command reports what the service logged, and an empty log is an available empty
    result. A failed Compose command raises.
    """
    _require_line_count(lines)
    argv = (
        *mechanics.compose_prefix(non_interactive=True),
        "logs",
        "--no-color",
        "--no-log-prefix",
        "--tail",
        str(lines),
        _EMBEDDING_SERVICE,
    )
    output = runner.run(argv, cwd=repository_root()).stdout
    return LogReadReport(
        stage="embedding",
        session_id=None,
        source=_EMBEDDING_SOURCE,
        available=True,
        text=output.decode("utf-8"),
    )
