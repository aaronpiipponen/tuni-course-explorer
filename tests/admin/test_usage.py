"""Behavior proofs for the shared usage records and their windowed administrative report."""

from __future__ import annotations

import multiprocessing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from course_explorer import administration, usage
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
    from course_explorer import administration as owner

    owner.repository_root = lambda: Path(root)

    for duration in durations:
        usage.append_usage_record(
            hour=hour, route="/api/features", status=200, duration_seconds=duration
        )


def _report_child(root: str, hour: datetime) -> None:
    """Read and prune the same temporary usage file while the appending children run.

    The supplied hour is the one fixed report clock, so no child depends on the machine's own time.
    """
    from course_explorer import administration as owner

    owner.repository_root = lambda: Path(root)
    for _ in range(25):
        usage.read_usage_report(hours=1, retention_days=30, now=hour + timedelta(minutes=30))


def test_usage_report_aggregates_window_and_prunes_retention(tmp_path: Path) -> None:
    """The report covers the two-hour window, and the stored file keeps the five records inside the
    30-day retention."""
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
        p95_duration_seconds=3.0,
        p99_duration_seconds=3.0,
        routes=(
            UsageRouteSummary(
                route="/",
                requests=1,
                mean_duration_seconds=2.0,
                p95_duration_seconds=2.0,
                p99_duration_seconds=2.0,
            ),
            UsageRouteSummary(
                route="/api/catalogue",
                requests=2,
                mean_duration_seconds=2.0,
                p95_duration_seconds=3.0,
                p99_duration_seconds=3.0,
            ),
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
    monkeypatch.setattr(administration, "repository_root", lambda: root)
    report = read_usage_report(hours=1, retention_days=30, now=_SEED_HOUR + timedelta(minutes=30))
    assert report.requests == 40
    assert report.routes == (
        UsageRouteSummary(
            route="/api/features",
            requests=40,
            mean_duration_seconds=53.375,
            p95_duration_seconds=105.25,
            p99_duration_seconds=105.75,
        ),
    )
    records = [
        UsageRecord.model_validate_json(line)
        for line in (root / _USAGE_PATH).read_text(encoding="utf-8").splitlines()
    ]
    assert sorted(record.duration_seconds for record in records) == sorted((*left, *right))


def test_usage_report_reports_nearest_rank_percentiles() -> None:
    """The report takes one route distribution's percentiles overall and keeps each route separate."""
    for duration in range(100, 0, -1):
        append_usage_record(
            hour=_SEED_HOUR,
            route="/api/catalogue",
            status=200,
            duration_seconds=float(duration),
        )
    append_usage_record(hour=_SEED_HOUR, route="/api/features", status=200, duration_seconds=200.0)

    report = read_usage_report(hours=1, retention_days=30, now=_SEED_HOUR + timedelta(minutes=30))

    assert report.requests == 101
    assert report.mean_duration_seconds == pytest.approx(5250 / 101)
    assert report.p95_duration_seconds == 96.0
    assert report.p99_duration_seconds == 100.0
    assert report.routes == (
        UsageRouteSummary(
            route="/api/catalogue",
            requests=100,
            mean_duration_seconds=50.5,
            p95_duration_seconds=95.0,
            p99_duration_seconds=99.0,
        ),
        UsageRouteSummary(
            route="/api/features",
            requests=1,
            mean_duration_seconds=200.0,
            p95_duration_seconds=200.0,
            p99_duration_seconds=200.0,
        ),
    )


@pytest.mark.parametrize(
    "record_present", (False, True), ids=("absent-file", "out-of-window-record")
)
def test_usage_report_leaves_empty_window_percentiles_unavailable(
    tmp_path: Path, record_present: bool
) -> None:
    """One window with no recorded request reports no duration facts and creates no file."""
    if record_present:
        append_usage_record(
            hour=_SEED_HOUR - timedelta(hours=5),
            route="/",
            status=200,
            duration_seconds=4.0,
        )

    report = read_usage_report(hours=1, retention_days=30, now=_SEED_HOUR + timedelta(minutes=30))

    assert report.requests == 0
    assert report.mean_duration_seconds is None
    assert report.p95_duration_seconds is None
    assert report.p99_duration_seconds is None
    assert report.routes == ()
    if not record_present:
        assert not (tmp_path / _USAGE_PATH).exists()
