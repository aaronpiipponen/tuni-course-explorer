"""Sole owner of the bounded administration command log.

One file, ``data/admin-web/command-log``, holds the administration work's own history: the time, the
fixed command label, the exit code, the duration and the outcome of each recorded execution, plus
the login, failed-login and lock events. A console read the runner ran automatically and that
succeeded records no entry, so the file holds explicit commands, failed automatic reads and the
authentication events. Every entry producer chooses its command label from fixed source-code text,
so a request field, an argument or a shell fragment can never become one.

Each entry holds the time, the fixed command label, the exit code, the duration and the outcome
token, and an entry for a failed command also holds one safe failure line. It is the only durable history the administration
backend writes, and ``read_command_log`` is the read the administration Logs view consumes.
"""

from __future__ import annotations

import fcntl
import os
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from course_explorer.administration import administrative_json, repository_root
from course_explorer.config import load_admin_web_settings
from course_explorer.validation import require_aware, require_finite_nonnegative
from course_explorer_admin.credentials import ADMIN_WEB_STATE_ROOT

COMMAND_LOG_FILENAME = "command-log"

# One safe failure line is a single short JSON line. The bound keeps the file's own line length
# predictable without storing any part of a command's output.
_MAX_FAILURE_LINE = 200


class CommandLogEntry(BaseModel):
    """One retained command-log entry: its time, fixed command label, outcome and duration.

    ``result`` is a safe outcome token rather than the command's report. ``failure_line`` is at most
    one safe failure line naming an exception class, never a message, a value or a child stream.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    time: datetime
    command: str
    exit_code: int
    duration_seconds: float
    result: Literal["success", "failure", "login", "failed-login", "lock"]
    failure_line: str | None = None

    @field_validator("time")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        """Require one timezone-aware timestamp so retained order is meaningful."""
        return require_aware(value, "command-log entry time")

    @field_validator("duration_seconds")
    @classmethod
    def validate_duration(cls, value: float) -> float:
        """Require one finite nonnegative elapsed duration."""
        return require_finite_nonnegative(value, "command-log entry duration")

    @field_validator("failure_line")
    @classmethod
    def validate_failure_line(cls, value: str | None) -> str | None:
        """Require at most one short failure line without line breaks."""
        if value is None:
            return None
        if not value or len(value) > _MAX_FAILURE_LINE or "\n" in value or "\r" in value:
            raise ValueError("command-log failure line must be one short line")
        return value


class CommandLogReport(BaseModel):
    """The retained entries of the sole command log, oldest first."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    entries: tuple[CommandLogEntry, ...]


def _parse_entries(payload: bytes) -> list[CommandLogEntry]:
    """Parse every retained line into its entry, refusing malformed or unreadable state."""
    if not payload:
        return []
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("command log is not readable UTF-8 text") from exc
    lines = text.splitlines()
    if text and not text.endswith("\n"):
        raise ValueError("command log does not end on a line boundary")
    entries: list[CommandLogEntry] = []
    for line in lines:
        try:
            entries.append(CommandLogEntry.model_validate_json(line))
        except ValueError as exc:
            raise ValueError("command log holds a line that does not match its schema") from exc
    return entries


class CommandLog:
    """The sole bounded administration command log over one locked file.

    Every append and every read takes one exclusive lock on the same open file, so a concurrent
    writer cannot lose an entry and a reader never sees a rewritable half-line. Appends keep the last
    ``limit`` entries oldest first, and the locked inode is never replaced.
    """

    def __init__(self, root: Path, *, limit: int) -> None:
        if limit <= 0:
            raise ValueError("command-log limit must be positive")
        self._root = root
        self._limit = limit

    @property
    def path(self) -> Path:
        """Return the sole command-log file beneath the administration state directory."""
        return self._root / ADMIN_WEB_STATE_ROOT / COMMAND_LOG_FILENAME

    def append(self, entry: CommandLogEntry) -> None:
        """Append one entry under the file lock, keeping only the last ``limit`` entries.

        The state directory and the file are created when they are absent, and the file mode is 0600.
        Every retained line is parsed before the rewrite, so malformed state fails instead of being
        repaired or overwritten. The rewritten file keeps the locked inode and flushes before the
        lock is released.
        """
        path = self.path
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        with os.fdopen(descriptor, "r+b") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                retained = _parse_entries(stream.read())
                retained.append(entry)
                payload = "".join(
                    administrative_json(item) for item in retained[-self._limit :]
                ).encode("utf-8")
                stream.seek(0)
                if stream.write(payload) != len(payload):
                    raise OSError("command-log rewrite was short")
                stream.truncate()
                stream.flush()
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def read(self) -> tuple[CommandLogEntry, ...]:
        """Return the last ``limit`` retained entries oldest first, or no entries for absence.

        The read takes the same exclusive lock as an append. An absent file is absent state, while a
        file that holds a malformed or unreadable line fails instead of being skipped. A file that
        holds more entries than the configured limit reports its newest entries and is not rewritten.
        """
        path = self.path
        try:
            stream = path.open("r+b")
        except FileNotFoundError:
            return ()
        with stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                return tuple(_parse_entries(stream.read())[-self._limit :])
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def read_command_log() -> CommandLogReport:
    """Read the retained entries of the sole command log, oldest first.

    The root is this checkout and the bound is the configured command-log limit, so the report
    describes the entries the log owner retains. An absent file is an empty report.
    """
    settings = load_admin_web_settings()
    log = CommandLog(repository_root(), limit=settings.admin_web_command_log_limit)
    return CommandLogReport(entries=log.read())
