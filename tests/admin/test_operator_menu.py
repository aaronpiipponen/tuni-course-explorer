"""Behavior contracts for the numbered operator menu."""

from __future__ import annotations

import json

import pytest

from course_explorer_admin import commands


class _Sentinel:
    """One JSON-renderable owner result standing in for a real DTO."""

    disposition: str | None = None

    def __init__(self, label: str) -> None:
        self.label = label

    def model_dump_json(self) -> str:
        return json.dumps({"label": self.label})


class _ScriptedRead:
    """Scripted input that records every prompt it is asked for."""

    def __init__(self, answers: list[str]) -> None:
        self._answers = list(answers)
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if not self._answers:
            raise EOFError
        return self._answers.pop(0)


@pytest.mark.parametrize(
    ("scenario", "answers", "server_branch"),
    [
        ("ingestion-status", ["2", "4", "0", "0"], "main"),
        ("catalogue-summary", ["6", "1", "0", "0"], "main"),
        ("selected-migration", ["1", "4", "0", "0"], "main"),
        ("worker-setup-main", ["1", "2", "0", "0"], "main"),
        ("worker-setup-nonmain-default", ["1", "2", "", "0", "0"], "prerequisite-inference"),
        (
            "worker-setup-explicit-branch",
            ["1", "2", "other-origin-branch", "0", "0"],
            "prerequisite-inference",
        ),
        ("dispose-nothing", ["5", "6", "disp-target", "1", "0", "0"], "main"),
        ("dispose-done", ["5", "6", "disp-target", "2", "0", "0"], "main"),
        ("dispose-failed", ["5", "6", "disp-target", "3", "0", "0"], "main"),
        ("embedding-write-hubs", ["4", "6", "0", "0"], "main"),
        ("supplied-callbacks", ["2", "4", "0", "6", "4", "0", "0"], "main"),
    ],
)
def test_operator_menu_routes_explicit_choices_and_uses_server_setup_branch(
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
    answers: list[str],
    server_branch: str,
) -> None:
    """Each scenario drives only its menu path and asserts only that path's calls/report/prompts."""
    sentinel = _Sentinel("ok")
    disposition_report = _Sentinel("disposition-report")
    tool_calls: list[tuple[str, str]] = []
    report_calls: list[tuple[str, str]] = []
    setup_calls: list[dict] = []
    migration_calls: list[object] = []
    preflight_calls: list[object] = []
    disposition_reads: list[str] = []
    disposition_sets: list[tuple[str, object]] = []
    checkout_calls: list[object] = []
    hub_calls: list[object] = []

    def fake_checkout(runner, root):
        checkout_calls.append((runner, root))
        return server_branch, "a" * 40

    monkeypatch.setattr(commands.mechanics, "require_prepared_checkout", fake_checkout)
    monkeypatch.setattr(
        commands,
        "run_administrative_command",
        lambda stage, action: tool_calls.append((stage, action)) or sentinel,
    )
    monkeypatch.setattr(
        commands,
        "run_administrative_summary",
        lambda kind: report_calls.append(("summary", kind)) or sentinel,
    )
    monkeypatch.setattr(
        commands,
        "run_administrative_coverage",
        lambda kind: report_calls.append(("coverage", kind)) or sentinel,
    )
    monkeypatch.setattr(
        commands,
        "run_administrative_setup",
        lambda kind, branch="main", code_only=False: (
            setup_calls.append({"kind": kind, "branch": branch, "code_only": code_only}) or sentinel
        ),
    )
    monkeypatch.setattr(
        commands,
        "run_administrative_preflight",
        lambda: preflight_calls.append(sentinel) or sentinel,
    )
    monkeypatch.setattr(
        commands,
        "run_administrative_migration",
        lambda: migration_calls.append(sentinel) or sentinel,
    )
    monkeypatch.setattr(
        commands, "run_administrative_hubs", lambda: hub_calls.append(sentinel) or sentinel
    )
    monkeypatch.setattr(
        commands,
        "read_inference_target_disposition",
        lambda target: disposition_reads.append(target) or disposition_report,
    )
    monkeypatch.setattr(
        commands,
        "set_inference_target_disposition",
        lambda target, decision: disposition_sets.append((target, decision)) or disposition_report,
    )

    reader = _ScriptedRead(answers)
    writes: list[str] = []
    supplied_calls: list[tuple[str, str, str]] = []

    def supplied_command(stage, action):
        supplied_calls.append(("command", stage, action))
        return sentinel

    def supplied_summary(kind):
        supplied_calls.append(("summary", kind, ""))
        return sentinel

    menu_arguments: dict[str, object] = {}
    if scenario == "supplied-callbacks":
        menu_arguments = {"run_command": supplied_command, "run_summary": supplied_summary}
    assert commands.run_operator_menu(read=reader, write=writes.append, **menu_arguments) == 0

    if scenario == "supplied-callbacks":
        # The supplied callbacks replace exactly the stage command and the inference summary. The
        # base owners are never reached for them.
        assert supplied_calls == [("command", "ingestion", "status"), ("summary", "inference", "")]
        assert tool_calls == [] and report_calls == []
        assert setup_calls == [] and migration_calls == []
        assert preflight_calls == [] and disposition_reads == [] and disposition_sets == []
        assert checkout_calls == []
        return

    if scenario == "ingestion-status":
        assert tool_calls == [("ingestion", "status")]
        # The ingestion tool menu shows no dispose entry and status touches only the ingestion tool.
        assert "6 Dispose target" not in writes
        assert "6 Write hubs" not in writes
        assert report_calls == [] and setup_calls == [] and migration_calls == []
        assert preflight_calls == [] and disposition_reads == [] and disposition_sets == []
        assert checkout_calls == []
        return
    if scenario == "embedding-write-hubs":
        # Only the embedding tool offers the hub writer, and choosing it calls the writer once.
        assert "6 Write hubs" in writes
        assert len(hub_calls) == 1
        assert tool_calls == [] and report_calls == [] and setup_calls == []
        assert disposition_reads == [] and disposition_sets == [] and checkout_calls == []
        return
    if scenario == "catalogue-summary":
        assert report_calls == [("summary", "catalogue")]
        assert tool_calls == [] and setup_calls == [] and migration_calls == []
        assert disposition_reads == [] and disposition_sets == [] and checkout_calls == []
        return
    if scenario == "selected-migration":
        assert len(migration_calls) == 1
        assert tool_calls == [] and report_calls == [] and setup_calls == []
        assert disposition_reads == [] and disposition_sets == [] and checkout_calls == []
        return
    if scenario.startswith("worker-setup"):
        expected_branch = {
            "worker-setup-main": "main",
            "worker-setup-nonmain-default": "prerequisite-inference",
            "worker-setup-explicit-branch": "other-origin-branch",
        }[scenario]
        assert setup_calls == [{"kind": "worker", "branch": expected_branch, "code_only": False}]
        assert len(checkout_calls) == 1
        branch_prompts = [prompt for prompt in reader.prompts if prompt.startswith("Origin branch")]
        if scenario == "worker-setup-main":
            # The server branch is main, so no branch prompt is offered.
            assert branch_prompts == []
        else:
            # Each non-main selection prompts once and offers the server branch as its Enter default.
            assert len(branch_prompts) == 1
            assert "prerequisite-inference" in branch_prompts[0]
        assert tool_calls == [] and report_calls == [] and migration_calls == []
        assert disposition_reads == [] and disposition_sets == []
        return

    # One nothing/done/failed disposition choice: the entry is present, the canonical identity is
    # reported before the choice prompt, and the shared setter is called exactly once.
    expected = {
        "dispose-nothing": None,
        "dispose-done": "done",
        "dispose-failed": "failed",
    }[scenario]
    assert "6 Dispose target" in writes
    assert disposition_reads == ["disp-target"]
    assert disposition_sets == [("disp-target", expected)]
    assert writes.index('{"label": "disposition-report"}') < writes.index("Dispose target")
    assert tool_calls == [] and report_calls == [] and setup_calls == [] and migration_calls == []
    assert checkout_calls == []


@pytest.mark.parametrize(
    "scenario",
    [
        "stage-failure-retry",
        "main-eof",
        "main-interrupt",
        "worker-branch-eof",
        "disposition-read-error",
        "disposition-cancellation",
        "disposition-choice-eof",
        "disposition-choice-interrupt",
    ],
)
def test_operator_menu_failure_and_eof_preserve_running_work(
    monkeypatch: pytest.MonkeyPatch, scenario: str
) -> None:
    """One refusal/interruption path per invocation: no implicit stop and no setter/setup call."""
    sentinel = _Sentinel("ok")
    calls: list[tuple[str, str]] = []
    setup_calls: list[dict] = []
    disposition_sets: list[tuple[str, object]] = []
    writes: list[str] = []

    monkeypatch.setattr(
        commands,
        "run_administrative_command",
        lambda stage, action: calls.append((stage, action)) or sentinel,
    )
    monkeypatch.setattr(
        commands,
        "run_administrative_setup",
        lambda kind, branch="main", code_only=False: setup_calls.append({"kind": kind}) or sentinel,
    )
    monkeypatch.setattr(commands, "read_inference_target_disposition", lambda target: sentinel)
    monkeypatch.setattr(
        commands,
        "set_inference_target_disposition",
        lambda target, decision: disposition_sets.append((target, decision)) or sentinel,
    )

    if scenario == "stage-failure-retry":
        # A failed operation is not success. A retry after the failure succeeds and stops nothing.

        def flaky(stage, action):
            calls.append((stage, action))
            if len(calls) == 1:
                raise RuntimeError("boom")
            return sentinel

        monkeypatch.setattr(commands, "run_administrative_command", flaky)
        assert (
            commands.run_operator_menu(
                read=_ScriptedRead(["2", "4", "4", "0", "0"]), write=writes.append
            )
            == 0
        )
        assert calls == [("ingestion", "status"), ("ingestion", "status")]
        payloads = [json.loads(line) for line in writes if line.startswith("{")]
        assert {"error": "RuntimeError"} in payloads
        assert {"label": "ok"} in payloads
        assert not any(action == "stop" for _stage, action in calls)
        assert setup_calls == [] and disposition_sets == []
        return

    if scenario == "main-eof":
        # EOF at the main menu returns 0 without any implicit stop or setup.
        assert (
            commands.run_operator_menu(read=lambda prompt: (_ for _ in ()).throw(EOFError())) == 0
        )
    elif scenario == "main-interrupt":
        # An interrupt at the main menu returns 130 without any implicit stop or setup.
        assert (
            commands.run_operator_menu(
                read=lambda prompt: (_ for _ in ()).throw(KeyboardInterrupt())
            )
            == 130
        )
    elif scenario == "worker-branch-eof":
        # EOF at the worker branch prompt returns 0, with no spurious operation error.
        monkeypatch.setattr(
            commands.mechanics,
            "require_prepared_checkout",
            lambda runner, root: ("prerequisite-inference", "a" * 40),
        )
        assert commands.run_operator_menu(read=_ScriptedRead(["1", "2"]), write=writes.append) == 0
        assert not any('"error"' in line for line in writes)
    elif scenario == "disposition-read-error":
        # A disposition read failure presents the safe error class and sets nothing.

        def failing_read(_target):
            raise RuntimeError("disposition-read-payload")

        monkeypatch.setattr(commands, "read_inference_target_disposition", failing_read)
        assert (
            commands.run_operator_menu(
                read=_ScriptedRead(["5", "6", "disp-target", "0", "0"]), write=writes.append
            )
            == 0
        )
        assert not any("disposition-read-payload" in line for line in writes)
        assert {"error": "RuntimeError"} in [
            json.loads(line) for line in writes if line.startswith("{")
        ]
    elif scenario == "disposition-cancellation":
        # Cancel at the choice prompt mutates nothing.
        assert (
            commands.run_operator_menu(
                read=_ScriptedRead(["5", "6", "disp-target", "0", "0"]), write=writes.append
            )
            == 0
        )
    elif scenario == "disposition-choice-eof":
        # EOF at the choice prompt returns 0 and sets nothing.
        assert (
            commands.run_operator_menu(
                read=_ScriptedRead(["5", "6", "disp-target"]), write=lambda _line: None
            )
            == 0
        )
    else:  # disposition-choice-interrupt
        # An interrupt at the choice prompt returns 130 and sets nothing.
        disposition_answers = ["5", "6", "disp-target"]

        def interrupting_read(prompt: str) -> str:
            if not disposition_answers:
                raise KeyboardInterrupt
            return disposition_answers.pop(0)

        assert commands.run_operator_menu(read=interrupting_read) == 130

    assert disposition_sets == []
    assert calls == []
    assert setup_calls == []
