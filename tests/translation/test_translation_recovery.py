"""Worker and recovery contracts for the translation-only worker.

Selectors live in `test_translation_service.py`. This file owns the resumable worker's
retained-output validation, atomic publication, failure sidecar, and lifecycle callbacks.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from course_explorer.enums import (
    TeachingTextLanguage,
    TranslationMethod,
)
from course_explorer.http_retry import RequestNotStarted
from course_explorer.teaching_text.service import teaching_text_sha256
from course_explorer.translation.provider import TranslationContractError
from course_explorer.translation.service import TranslationWorkerService
from tests.translation._service_support import (
    GENERATED_AT,
    PROVENANCE,
    FakeCurriculum,
    FakeTranslations,
    ForbiddenProvider,
    RecordingProvider,
    course,
    load_output,
    retained_entry,
    settings,
    version,
    worker,
    write_output,
)

# Exact reference output bytes for the two fixed-clock fixture entries below. This is a
# literal fixed-format array: it must not be serialized from the model or helper under test.
ORIGINAL_OUTPUT = """[
  {
    "sisu_course_unit_id": "course-a-v1",
    "field": "name",
    "language": "en",
    "source_language": "fi",
    "source_text": "Nimi",
    "text": "Name",
    "translation_method": "model",
    "generated_at": "2026-01-01T12:00:00Z",
    "translation_model": "google/translategemma-12b-it@d1b225e1caa17f1ddc7e62065d8637d0923f34e2;Q5_K_M;sha256:6a4cd9eae938fd869ceeb310ed9c8de2f44bacb0c2d79541a4f4dbf2b201c6da"
  },
  {
    "sisu_course_unit_id": "course-a-v1",
    "field": "content",
    "language": "en",
    "source_language": "fi",
    "source_text": "Sisältö",
    "text": "Content",
    "translation_method": "model",
    "generated_at": "2026-01-01T12:00:00Z",
    "translation_model": "google/translategemma-12b-it@d1b225e1caa17f1ddc7e62065d8637d0923f34e2;Q5_K_M;sha256:6a4cd9eae938fd869ceeb310ed9c8de2f44bacb0c2d79541a4f4dbf2b201c6da"
  }
]
""".encode()


def test_worker_reuses_complete_output_without_provider_io_or_timestamp_change(
    tmp_path: Path,
) -> None:
    """A fully retained output performs no provider request and preserves its stored timestamps."""
    representative = version("course-a-v1", name_fi="Nimi", content_fi="Sisältö")
    output = tmp_path / "bounded.json"
    first = RecordingProvider(["Name", "Content"])
    service = TranslationWorkerService(
        FakeCurriculum((course("course-a", representative),)),
        FakeTranslations(),
        first,
        settings(),
        clock=lambda: GENERATED_AT,
    )
    report = service.run(output_path=output)
    assert (
        report.desired_count,
        report.generated_count,
        report.reused_count,
        report.output_count,
    ) == (
        2,
        2,
        0,
        2,
    )
    original = output.read_bytes()
    assert original == ORIGINAL_OUTPUT
    timestamps = [entry.generated_at for entry in load_output(output)]

    rerun = TranslationWorkerService(
        FakeCurriculum((course("course-a", representative),)),
        FakeTranslations(),
        ForbiddenProvider(),
        settings(),
        clock=lambda: datetime(2030, 1, 1, tzinfo=UTC),
    )
    report = rerun.run(output_path=output)

    assert (
        report.desired_count,
        report.generated_count,
        report.reused_count,
        report.output_count,
    ) == (
        2,
        0,
        2,
        2,
    )
    assert output.read_bytes() == original
    assert [entry.generated_at for entry in load_output(output)] == timestamps


def test_worker_rejects_duplicate_stale_foreign_manual_or_wrong_model_output(
    tmp_path: Path,
) -> None:
    """Invalid retained output fails loudly instead of being silently deleted or imported."""
    cases = {
        "duplicate": [retained_entry(), retained_entry(text="Name two")],
        "stale": [retained_entry(source_text="Vanha")],
        "foreign": [retained_entry(source_id="other-v1")],
        "manual": [retained_entry(method=TranslationMethod.MANUAL, translation_model=None)],
        "wrong-model": [retained_entry(translation_model="other@rev;Q5_K_M;sha256:" + "0" * 64)],
    }
    for name, entries in cases.items():
        output = tmp_path / f"{name}.json"
        write_output(output, entries)
        before = output.read_bytes()
        service = worker(tmp_path, ForbiddenProvider())
        with pytest.raises(ValueError):
            service.run(output_path=output)
        assert output.read_bytes() == before


def test_worker_records_sanitized_terminal_failure_and_resumes_without_losing_successes(
    tmp_path: Path,
) -> None:
    """Terminal failures write one text-free deterministic sidecar and resume without data loss."""
    representative = version("course-a-v1", name_fi="Nimi", content_fi="Sisältö")
    output = tmp_path / "bounded.json"
    provider = RecordingProvider(["Name", TranslationContractError("bad<>")])
    service = TranslationWorkerService(
        FakeCurriculum((course("course-a", representative),)),
        FakeTranslations(),
        provider,
        settings(),
        clock=lambda: GENERATED_AT,
    )

    with pytest.raises(TranslationContractError):
        service.run(output_path=output)

    sidecar = output.with_name(output.name + ".failure.json")
    assert sidecar.exists()
    assert oct(sidecar.stat().st_mode & 0o777) == "0o600"
    record = json.loads(sidecar.read_text(encoding="utf-8"))
    assert record["error_type"] == "TranslationContractError"
    assert record["error_message"] == "TranslationContractError"
    assert record["sisu_course_unit_id"] == "course-a-v1"
    assert record["field"] == "content"
    assert record["language"] == "en"
    assert record["source_language"] == "fi"
    assert record["translation_model"] == PROVENANCE
    assert record["source_text_hash"] == teaching_text_sha256("Sisältö")
    assert "bad" not in sidecar.read_text(encoding="utf-8")

    # The one published success is import-compatible and retains exact official provenance.
    entries = load_output(output)
    assert [
        (entry.sisu_course_unit_id, entry.field.value, entry.language.value) for entry in entries
    ] == [("course-a-v1", "name", "en")]
    entry = entries[0]
    assert entry.source_language is TeachingTextLanguage.FI
    assert entry.source_text == "Nimi"
    assert entry.text == "Name"
    assert entry.translation_method is TranslationMethod.MODEL
    assert entry.translation_model == PROVENANCE
    assert entry.generated_at == GENERATED_AT
    assert provider.calls == [
        ("Nimi", TeachingTextLanguage.FI, TeachingTextLanguage.EN),
        ("Sisältö", TeachingTextLanguage.FI, TeachingTextLanguage.EN),
    ]
    # The public sidecar work identity is the frozen canonical hash of that exact work item.
    assert record["work_key_sha256"] == (
        "ac463f8f57183126da3d78c0b6873cfaa82be08a6dcdcaadc0655cc6dde85c80"
    )

    resume = TranslationWorkerService(
        FakeCurriculum((course("course-a", representative),)),
        FakeTranslations(),
        RecordingProvider(["Content"]),
        settings(),
        clock=lambda: GENERATED_AT,
    )
    report = resume.run(output_path=output)

    assert (
        report.desired_count,
        report.generated_count,
        report.reused_count,
        report.output_count,
    ) == (
        2,
        1,
        1,
        2,
    )
    assert not sidecar.exists()
    assert [entry.text for entry in load_output(output)] == ["Name", "Content"]


def test_worker_control_callback_stops_before_next_provider_call(tmp_path: Path) -> None:
    """A false control callback ends the run before the provider is called again."""
    representative = version("course-a-v1", name_fi="Nimi", content_fi="Sisältö")
    output = tmp_path / "bounded.json"
    provider = RecordingProvider(["Name", "Content"])
    gate_calls: list[int] = []

    def gate() -> bool:
        gate_calls.append(len(gate_calls))
        return len(gate_calls) == 1

    service = TranslationWorkerService(
        FakeCurriculum((course("course-a", representative),)),
        FakeTranslations(),
        provider,
        settings(),
        clock=lambda: GENERATED_AT,
    )
    report = service.run(output_path=output, before_pending_item=gate)

    assert provider.calls == [("Nimi", TeachingTextLanguage.FI, TeachingTextLanguage.EN)]
    assert gate_calls == [0, 1]
    assert [entry.text for entry in load_output(output)] == ["Name"]
    assert (
        report.desired_count,
        report.generated_count,
        report.reused_count,
        report.output_count,
    ) == (1, 1, 0, 1)


def test_worker_declined_request_ends_with_real_partial_report(tmp_path: Path) -> None:
    """A RequestNotStarted from the provider ends the run with the partial report."""
    representative = version("course-a-v1", name_fi="Nimi", content_fi="Sisältö")
    output = tmp_path / "bounded.json"
    provider = RecordingProvider(["Name", RequestNotStarted("declined"), "Content"])
    service = TranslationWorkerService(
        FakeCurriculum((course("course-a", representative),)),
        FakeTranslations(),
        provider,
        settings(),
        clock=lambda: GENERATED_AT,
    )
    report = service.run(output_path=output)

    assert [entry.text for entry in load_output(output)] == ["Name"]
    assert provider.calls[0][0] == "Nimi"
    assert (report.generated_count, report.output_count) == (1, 1)
    assert not output.with_name(output.name + ".failure.json").exists()


def test_worker_checkpoint_callback_runs_only_after_atomic_success(tmp_path: Path) -> None:
    """The checkpoint callback fires once per published success with the retained output count."""
    representative = version("course-a-v1", name_fi="Nimi", content_fi="Sisältö")
    output = tmp_path / "bounded.json"
    provider = RecordingProvider(["Name", "Content"])
    checkpoints: list[tuple[int, int]] = []

    def checkpoint(count: int) -> None:
        checkpoints.append((count, len(load_output(output))))

    service = TranslationWorkerService(
        FakeCurriculum((course("course-a", representative),)),
        FakeTranslations(),
        provider,
        settings(),
        clock=lambda: GENERATED_AT,
    )
    report = service.run(output_path=output, on_checkpoint=checkpoint)

    assert checkpoints == [(1, 1), (2, 2)]
    assert report.generated_count == 2
