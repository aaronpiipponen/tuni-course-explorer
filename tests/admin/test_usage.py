"""Behavior proofs for the shared usage records and their windowed administrative report."""

from __future__ import annotations

import multiprocessing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from course_explorer import usage
from course_explorer.usage import (
    UsageRecord,
    UsageReport,
    UsageRouteSummary,
    append_usage_record,
    read_usage_report,
)

_USAGE_PATH = Path("data") / "usage" / "requests"
_SEED_HOUR = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)


def _append_child(root: str, hour: datetime, durations: tuple[float, ...]) -> None:
    """Append one child's records to the supplied temporary usage root.

    A child entry point binds the shared owner's root and appends only its own supplied records, and
    it loads no settings.
    """
    from course_explorer import usage as owner

    owner.repository_root = lambda: Path(root)
    for duration in durations:
        owner.append_usage_record(
            hour=hour, route="/api/features", status=200, duration_seconds=duration
        )


def _report_child(root: str, hour: datetime) -> None:
    """Read and prune the same temporary usage file while the appending children run.

    The supplied hour is the one fixed report clock, so no child depends on the machine's own time.
    """
    from course_explorer import usage as owner

    owner.repository_root = lambda: Path(root)
    for _ in range(25):
        owner.read_usage_report(hours=1, retention_days=30, now=hour + timedelta(minutes=30))


def test_usage_report_aggregates_window_and_prunes_retention(tmp_path: Path) -> None:
    """One window reports its totals and route means, and the file keeps exactly the retained hours."""
    append_usage_record(
        hour=_SEED_HOUR - timedelta(hours=1),
        route="/api/catalogue",
        status=200,
        duration_seconds=1.0,
    )
    append_usage_record(
        hour=_SEED_HOUR - timedelta(hours=1),
        route="/api/catalogue",
        status=200,
        duration_seconds=3.0,
    )
    append_usage_record(hour=_SEED_HOUR, route="/", status=404, duration_seconds=2.0)
    append_usage_record(
        hour=_SEED_HOUR - timedelta(hours=3), route="/", status=200, duration_seconds=9.0
    )
    append_usage_record(
        hour=_SEED_HOUR - timedelta(days=30), route="/", status=200, duration_seconds=4.0
    )
    append_usage_record(
        hour=_SEED_HOUR - timedelta(days=30, hours=1),
        route="/",
        status=200,
        duration_seconds=5.0,
    )

    report = read_usage_report(hours=2, retention_days=30, now=_SEED_HOUR + timedelta(minutes=30))

    assert report == UsageReport(
        window_start=_SEED_HOUR - timedelta(hours=1),
        window_end=_SEED_HOUR + timedelta(hours=1),
        requests=3,
        mean_duration_seconds=2.0,
        routes=(
            UsageRouteSummary(route="/", requests=1, mean_duration_seconds=2.0),
            UsageRouteSummary(route="/api/catalogue", requests=2, mean_duration_seconds=2.0),
        ),
    )
    retained = [
        UsageRecord.model_validate_json(line)
        for line in (tmp_path / _USAGE_PATH).read_text(encoding="utf-8").splitlines()
    ]
    assert [record.hour for record in retained] == [
        _SEED_HOUR - timedelta(hours=1),
        _SEED_HOUR - timedelta(hours=1),
        _SEED_HOUR,
        _SEED_HOUR - timedelta(hours=3),
        _SEED_HOUR - timedelta(days=30),
    ]


def test_usage_append_and_prune_preserve_concurrent_records(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Two appending processes and one reading writer keep all forty recorded lines intact."""
    root = tmp_path / "usage-root"
    left = tuple(1.0 + 0.25 * index for index in range(20))
    right = tuple(101.0 + 0.25 * index for index in range(20))
    context = multiprocessing.get_context("fork")
    children = (
        context.Process(target=_append_child, args=(str(root), _SEED_HOUR, left)),
        context.Process(target=_append_child, args=(str(root), _SEED_HOUR, right)),
        context.Process(target=_report_child, args=(str(root), _SEED_HOUR)),
    )
    for child in children:
        child.start()
    for child in children:
        child.join(timeout=60)

    assert [child.exitcode for child in children] == [0, 0, 0]
    monkeypatch.setattr(usage, "repository_root", lambda: root)
    report = read_usage_report(hours=1, retention_days=30, now=_SEED_HOUR + timedelta(minutes=30))
    assert report.requests == 40
    assert report.routes == (
        UsageRouteSummary(route="/api/features", requests=40, mean_duration_seconds=53.375),
    )
    records = [
        UsageRecord.model_validate_json(line)
        for line in (root / _USAGE_PATH).read_text(encoding="utf-8").splitlines()
    ]
    assert sorted(record.duration_seconds for record in records) == sorted((*left, *right))
