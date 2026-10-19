"""Sole owner of the per-request usage records and their windowed report.

Serving appends one content-free record per HTTP request and the fixed administrative usage command
reads that window's request aggregates and prunes records past the configured retention. Both
operations take one exclusive lock on the same open file, so an append never interleaves with a
report's rewrite of the retained lines.
"""

from __future__ import annotations

import fcntl
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from course_explorer.administration import repository_root, utc_now

_USAGE_RELATIVE_PATH = Path("data") / "usage" / "requests"


class UsageRecord(BaseModel):
    """One content-free request record: its start hour, fixed route label, status and duration.

    ``hour`` is the request-start UTC hour rounded down and ``duration_seconds`` is the monotonic
    elapsed serving time. The serving middleware owns the route normalization and the hour
    rounding. The model is both the serialization and the parsing shape of one file line.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    hour: datetime
    route: str
    status: int
    duration_seconds: float


class UsageRouteSummary(BaseModel):
    """One route's request count and arithmetic mean duration inside a report window."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    route: str
    requests: int
    mean_duration_seconds: float


class UsageReport(BaseModel):
    """One window's request total, overall mean duration and per-route summaries.

    ``mean_duration_seconds`` is ``None`` and ``routes`` is empty when the window holds no
    recorded request.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    window_start: datetime
    window_end: datetime
    requests: int
    mean_duration_seconds: float | None
    routes: tuple[UsageRouteSummary, ...]


def append_usage_record(
    *, hour: datetime, route: str, status: int, duration_seconds: float
) -> None:
    """Append one complete record line to the usage file under one exclusive lock.

    The usage directory and file are created when they are absent, and the file mode is 0600.
    The whole encoded line is written under the lock, and a short write raises an I/O error.
    """
    record = UsageRecord(hour=hour, route=route, status=status, duration_seconds=duration_seconds)
    line = record.model_dump_json().encode("utf-8") + b"\n"
    path = _usage_file(repository_root())
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        try:
            if os.write(descriptor, line) != len(line):
                raise OSError("usage record append was short")
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def read_usage_report(
    *, hours: int, retention_days: int, now: datetime | None = None
) -> UsageReport:
    """Return one hour window's report and prune the records past the retention.

    ``hours`` counts whole hours back from the current rounded UTC hour inclusive, so the window
    is ``current_hour - (hours - 1) hours`` up to the current hour's end. It is validated before
    the file is opened: it must be positive and at most ``retention_days * 24`` hours. Retention
    keeps records from ``current_hour - timedelta(days=retention_days)`` inclusive. ``now`` defaults
    to the shared UTC clock and is captured once.

    A truly absent file returns the empty report and creates nothing. A malformed line or record
    fails without rewriting the file. Retained lines are read and rewritten under one exclusive
    lock on the same file. The report aggregates the windowed records after releasing the lock.
    """
    if hours <= 0 or hours > retention_days * 24:
        raise ValueError(
            "usage hours must be positive and no longer than the configured retention in hours"
        )
    current_hour = rounded_usage_hour(utc_now() if now is None else now)
    window_start = current_hour - timedelta(hours=hours - 1)
    window_end = current_hour + timedelta(hours=1)
    retention_start = current_hour - timedelta(days=retention_days)
    path = _usage_file(repository_root())
    if not path.exists():
        return _empty_report(window_start, window_end)

    retained: list[bytes] = []
    windowed: list[UsageRecord] = []
    with path.open("r+b") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            for line in stream.read().splitlines():
                record = UsageRecord.model_validate_json(line)
                if record.hour < retention_start:
                    continue
                retained.append(line)
                if window_start <= record.hour < window_end:
                    windowed.append(record)
            stream.seek(0)
            stream.write(b"".join(line + b"\n" for line in retained))
            stream.truncate()
            stream.flush()
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    return _summarize(window_start, window_end, windowed)


def _usage_file(root: Path) -> Path:
    """Return the sole usage file beneath one checkout root."""
    return root / _USAGE_RELATIVE_PATH


def rounded_usage_hour(value: datetime) -> datetime:
    """Return one instant's UTC hour rounded down.

    The serving middleware and this report share the one rounding, so a request record's hour
    and a report window boundary are the same value.
    """
    return value.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


def _empty_report(window_start: datetime, window_end: datetime) -> UsageReport:
    """Return the report of a window that holds no recorded request."""
    return UsageReport(
        window_start=window_start,
        window_end=window_end,
        requests=0,
        mean_duration_seconds=None,
        routes=(),
    )


def _summarize(
    window_start: datetime, window_end: datetime, records: list[UsageRecord]
) -> UsageReport:
    """Return the window's totals and its per-route summaries in route order."""
    if not records:
        return _empty_report(window_start, window_end)
    durations_by_route: dict[str, list[float]] = {}
    for record in records:
        durations_by_route.setdefault(record.route, []).append(record.duration_seconds)
    durations = [record.duration_seconds for record in records]
    return UsageReport(
        window_start=window_start,
        window_end=window_end,
        requests=len(records),
        mean_duration_seconds=sum(durations) / len(durations),
        routes=tuple(
            UsageRouteSummary(
                route=route,
                requests=len(route_durations),
                mean_duration_seconds=sum(route_durations) / len(route_durations),
            )
            for route, route_durations in sorted(durations_by_route.items())
        ),
    )
