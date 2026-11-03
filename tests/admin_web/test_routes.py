"""Proof that each console feature route maps one request to its admitted fixed commands.

Every case sends one authenticated HTTP request through the real application, the real admission
middleware and the real fixed-command runner over a recording process boundary. It proves the exact
admitted argument list, the one transient outcome the caller receives, and the one command-log entry
the runner appends. The administration self-rebuild is the one two-command route: its request answers
the build outcome and attaches the restart command to the response's background task. A marked request
carries the console's automatic-read header: the marker changes no argv, and a successful read route
omits its entry while a failed one and every action or manual-only route append theirs. No case
executes a lifecycle, decision, hub, rebuild, save or deletion operation: the process boundary records
the call instead of running it.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import RootModel

from course_explorer_admin import commands as admin_commands
from course_explorer_admin.commands import format_operator_error
from course_explorer_admin_web import runner as admin_runner
from tests.admin_web import _support

TARGET_ID = "tuni-canonical-0f3a91"
DATASET_ID = "c" * 32
LOG_SESSION_ID = "e" * 32
LOG_SOURCE = "worker-runner"
CONFIG_FILE = "config/web.toml"
CONFIG_KEY = "WEB_PORT"
CONFIG_VALUE = json.dumps(_support.VALUE_SENTINEL)
BACKUP_NAME = "before-inference.dump"
WORKER_BRANCH = "origin-branch"
FEEDBACK_ID = "3f1c2a64-5b7d-4e29-8c10-6a9d2b4e7f01"
FEEDBACK_ATTACHMENT_ID = "8e2d4b17-9c63-4a52-b0f8-1d7c3e5a9b24"
FEEDBACK_QUERY = "synthetic feedback query"
FEEDBACK_FILTERS = {"role": "student"}
FEEDBACK_ATTACHMENT_CARRIER = "c3ludGhldGljLWZlZWRiYWNrLWNhcnJpZXI="
_FEEDBACK_ATTACHMENT_REPORT: dict[str, object] = {
    "attachment": {
        "id": FEEDBACK_ATTACHMENT_ID,
        "feedback_id": FEEDBACK_ID,
        "field_id": "screenshots",
        "mime_type": "image/png",
    },
    "content_base64": FEEDBACK_ATTACHMENT_CARRIER,
}
_SUCCESS_REPORTS: dict[str, dict[str, object]] = {
    "feedback-attachment": _FEEDBACK_ATTACHMENT_REPORT
}

# The routes the runner answers in process, and the command function it calls for each.
_IN_PROCESS_READS: dict[str, str] = {
    "dashboard": "run_administrative_server_status",
    "preparation-status": "run_administrative_command",
    "preparation-catalogue": "run_administrative_summary",
    "preparation-teaching-text": "run_administrative_coverage",
    "preparation-embedding": "run_administrative_coverage",
    "inference-status": "run_administrative_command",
    "inference-summary": "run_administrative_summary",
    "datasets": "run_administrative_dataset_list",
}

# One row per console feature route: its method, its path, its body, the exact argv tail the runner
# admits for it, and the request-supplied values that must not reach the retained log entry.
_ROUTES: dict[str, tuple[str, str, dict[str, object] | None, tuple[str, ...], tuple[str, ...]]] = {
    "dashboard": ("GET", "/api/dashboard", None, ("server", "status"), ()),
    "preparation-status": (
        "GET",
        "/api/preparation/status/ingestion",
        None,
        ("ingestion", "status"),
        (),
    ),
    "preparation-action": (
        "POST",
        "/api/preparation/action",
        {"stage": "translation", "action": "stop"},
        ("translation", "stop"),
        (),
    ),
    "preparation-catalogue": (
        "GET",
        "/api/preparation/report/catalogue",
        None,
        ("summary", "catalogue"),
        (),
    ),
    "preparation-teaching-text": (
        "GET",
        "/api/preparation/report/teaching-text",
        None,
        ("coverage", "teaching-text"),
        (),
    ),
    "preparation-embedding": (
        "GET",
        "/api/preparation/report/embedding",
        None,
        ("coverage", "embedding"),
        (),
    ),
    "preparation-serving-artifacts": (
        "POST",
        "/api/preparation/serving-artifacts",
        {},
        ("serving-artifacts",),
        (),
    ),
    "inference-status": ("GET", "/api/inference/status", None, ("inference", "status"), ()),
    "inference-action": (
        "POST",
        "/api/inference/action",
        {"action": "pause"},
        ("inference", "pause"),
        (),
    ),
    "inference-summary": ("GET", "/api/inference/summary", None, ("summary", "inference"), ()),
    "inference-target-read": (
        "POST",
        "/api/inference/target/read",
        {"target_id": TARGET_ID},
        ("target", "inference", TARGET_ID),
        (TARGET_ID,),
    ),
    "inference-decision": (
        "POST",
        "/api/inference/target/decision",
        {"target_id": TARGET_ID, "disposition": "failed"},
        ("dispose", "inference", TARGET_ID, "failed"),
        (TARGET_ID, "failed"),
    ),
    "datasets": ("GET", "/api/datasets", None, ("datasets", "list"), ()),
    "datasets-setup": ("POST", "/api/datasets/setup", {}, ("setup", "datasets"), ()),
    "datasets-migrate-selected": (
        "POST",
        "/api/datasets/migrate",
        {"role": "selected"},
        ("migrate", "selected"),
        (),
    ),
    "datasets-migrate-working": (
        "POST",
        "/api/datasets/migrate",
        {"role": "working"},
        ("migrate", "working"),
        (),
    ),
    "datasets-migrate-database": (
        "POST",
        "/api/datasets/migrate",
        {"role": "database"},
        ("migrate", "database"),
        (),
    ),
    "datasets-delete": (
        "POST",
        "/api/datasets/delete",
        {"dataset_id": DATASET_ID},
        ("datasets", "delete", DATASET_ID),
        (DATASET_ID,),
    ),
    "datasets-delete-working": (
        "POST",
        "/api/datasets/delete",
        {"dataset_id": DATASET_ID, "confirm_working": True},
        ("datasets", "delete", DATASET_ID, "--confirm-working"),
        (DATASET_ID,),
    ),
    "datasets-copy-to-working": (
        "POST",
        "/api/datasets/copy-to-working",
        {"source_dataset_id": DATASET_ID},
        ("datasets", "copy-to-working", DATASET_ID),
        (DATASET_ID,),
    ),
    "logs-commands": ("GET", "/api/logs/commands", None, ("logs", "commands"), ()),
    "logs-sessions": ("GET", "/api/logs/sessions", None, ("logs", "sessions"), ()),
    "logs-read": (
        "POST",
        "/api/logs/read",
        {
            "stage": "inference",
            "session_id": LOG_SESSION_ID,
            "source": LOG_SOURCE,
            "lines": 25,
        },
        ("logs", "read", "inference", LOG_SESSION_ID, LOG_SOURCE, "--lines", "25"),
        (LOG_SESSION_ID,),
    ),
    "logs-embedding": (
        "POST",
        "/api/logs/embedding",
        {"lines": 7},
        ("logs", "embedding", "--lines", "7"),
        (),
    ),
    "logs-usage": ("POST", "/api/logs/usage", {"hours": 24}, ("usage", "--hours", "24"), ()),
    "feedback-list": (
        "POST",
        "/api/feedback/list",
        {"query": FEEDBACK_QUERY, "filters": FEEDBACK_FILTERS},
        (
            "feedback",
            "list",
            f"--query={FEEDBACK_QUERY}",
            f"--filters={json.dumps(FEEDBACK_FILTERS)}",
        ),
        (FEEDBACK_QUERY, *FEEDBACK_FILTERS.values()),
    ),
    "feedback-attachment": (
        "POST",
        "/api/feedback/attachment",
        {"feedback_id": FEEDBACK_ID, "attachment_id": FEEDBACK_ATTACHMENT_ID},
        ("feedback", "attachment", FEEDBACK_ID, FEEDBACK_ATTACHMENT_ID),
        (FEEDBACK_ID, FEEDBACK_ATTACHMENT_ID, FEEDBACK_ATTACHMENT_CARRIER),
    ),
    "feedback-delete": (
        "POST",
        "/api/feedback/delete",
        {"feedback_id": FEEDBACK_ID},
        ("feedback", "delete", FEEDBACK_ID),
        (FEEDBACK_ID,),
    ),
    "settings-config-files": (
        "GET",
        "/api/settings/config/files",
        None,
        ("config", "list"),
        (),
    ),
    "settings-config-read": (
        "POST",
        "/api/settings/config/read",
        {"file": CONFIG_FILE},
        ("config", "read", "--", CONFIG_FILE),
        (CONFIG_FILE,),
    ),
    "settings-config-set": (
        "POST",
        "/api/settings/config/set",
        {"file": CONFIG_FILE, "key": CONFIG_KEY, "value": CONFIG_VALUE},
        ("config", "set", "--", CONFIG_FILE, CONFIG_KEY, CONFIG_VALUE),
        (CONFIG_FILE, CONFIG_KEY, _support.VALUE_SENTINEL),
    ),
    "settings-backups": ("GET", "/api/settings/backups", None, ("backups", "list"), ()),
    "settings-backups-delete": (
        "POST",
        "/api/settings/backups/delete",
        {"name": BACKUP_NAME},
        ("backups", "delete", "--", BACKUP_NAME),
        (BACKUP_NAME,),
    ),
    "settings-rebuild": ("POST", "/api/settings/rebuild", {}, ("rebuild",), ()),
    "settings-rebuild-admin": (
        "POST",
        "/api/settings/rebuild-admin",
        {},
        ("rebuild-admin",),
        (),
    ),
    "settings-worker-setup": (
        "POST",
        "/api/settings/worker/setup",
        {"branch": WORKER_BRANCH, "code_only": True},
        ("setup", "worker", f"--branch={WORKER_BRANCH}", "--code-only"),
        (WORKER_BRANCH,),
    ),
    "settings-worker-preflight": (
        "POST",
        "/api/settings/worker/preflight",
        {},
        ("preflight",),
        (),
    ),
}


# The one route whose one request runs a second fixed command: the administration self-rebuild
# attaches the restart command to the successful response's background task.
_ADMIN_REBUILD_ROUTE = "settings-rebuild-admin"
_FOLLOW_UP_TAILS: dict[str, tuple[str, ...]] = {_ADMIN_REBUILD_ROUTE: ("restart-admin",)}

# One (route, outcome) case per invocation. The two common outcomes serve every route. The
# administration self-rebuild adds its own restart queue failure, because it is the route that runs
# the second command the failure belongs to.
_ROUTE_CASES = tuple(
    (route, outcome)
    for route in sorted(_ROUTES)
    for outcome in (
        ("success", "checked-failure", "restart-queue-failure")
        if route == _ADMIN_REBUILD_ROUTE
        else ("success", "checked-failure")
    )
)

# The operator operation whose fixed guidance line a failed request carries.
_ROUTE_GUIDANCE: dict[str, str] = {
    "dashboard": "server",
    "preparation-status": "stage",
    "preparation-action": "stage",
    "preparation-catalogue": "report",
    "preparation-teaching-text": "report",
    "preparation-embedding": "report",
    "preparation-serving-artifacts": "serving-artifacts",
    "inference-status": "stage",
    "inference-action": "stage",
    "inference-summary": "report",
    "inference-target-read": "target-read",
    "inference-decision": "disposition",
    "datasets": "dataset-list",
    "datasets-setup": "setup",
    "datasets-migrate-selected": "migration",
    "datasets-migrate-working": "migration",
    "datasets-migrate-database": "migration",
    "datasets-delete": "dataset-cleanup",
    "datasets-delete-working": "dataset-cleanup",
    "datasets-copy-to-working": "dataset-copy",
    "logs-commands": "logs",
    "logs-sessions": "logs",
    "logs-read": "logs",
    "logs-embedding": "logs",
    "logs-usage": "usage",
    "feedback-list": "feedback",
    "feedback-attachment": "feedback",
    "feedback-delete": "feedback",
    "settings-config-files": "configuration",
    "settings-config-read": "configuration",
    "settings-config-set": "configuration",
    "settings-backups": "backup-list",
    "settings-backups-delete": "backup-cleanup",
    "settings-rebuild": "rebuild",
    "settings-rebuild-admin": "rebuild",
    "settings-worker-setup": "setup",
    "settings-worker-preflight": "preflight",
}

# The routes whose in-process summary read resolves the dataset role before it runs its report.
_ROLE_SCOPED_ROUTES = frozenset(
    {
        "preparation-catalogue",
        "preparation-teaching-text",
        "preparation-embedding",
        "inference-summary",
    }
)

# The routes whose handler forwards the console's automatic-read marker, so a successful automatic
# invocation of them records no command-log entry. Every other route keeps the default false.
_AUTOMATIC_READ_ROUTES = frozenset(
    {
        "dashboard",
        "preparation-status",
        "preparation-catalogue",
        "preparation-teaching-text",
        "preparation-embedding",
        "inference-status",
        "inference-summary",
        "datasets",
        "logs-commands",
        "logs-sessions",
        "logs-read",
        "logs-embedding",
        "logs-usage",
        "settings-config-files",
        "settings-config-read",
        "settings-backups",
        "feedback-list",
        "feedback-attachment",
    }
)

# The one request header the console sets on an automatic read.
AUTOMATIC_HEADER = {"X-Admin-Automatic-Read": "1"}


def _report_bytes() -> bytes:
    """Return the one success body every scripted command call answers with."""
    return json.dumps({}).encode("utf-8")


@pytest.mark.parametrize("marked", [False, True])
@pytest.mark.parametrize(("route", "outcome"), _ROUTE_CASES)
def test_admin_feature_route_runs_its_fixed_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, route: str, outcome: str, marked: bool
) -> None:
    """One authenticated request runs the admitted commands and returns one transient outcome."""
    method, path, body, tail, sensitive = _ROUTES[route]
    root = _support.site_root(monkeypatch, tmp_path)
    settings = _support.admin_web_settings()
    failure = subprocess.CalledProcessError(
        returncode=1,
        cmd=[sys.executable, str(root / "scripts" / "admin.py"), *tail],
        stderr=_support.OUTPUT_SENTINEL.encode("utf-8"),
    )
    follow_up = _FOLLOW_UP_TAILS.get(route)
    success = json.dumps(_SUCCESS_REPORTS.get(route, {})).encode("utf-8")
    in_process = route in _IN_PROCESS_READS
    expected_guidance = admin_commands.operator_guidance(_ROUTE_GUIDANCE[route])
    if route in _ROLE_SCOPED_ROUTES:
        monkeypatch.setattr(admin_runner, "_report_role", lambda: "working")
    if in_process:
        reader = _IN_PROCESS_READS[route]
        if outcome == "checked-failure":

            def failing(*_args: object, **_kwargs: object) -> object:
                raise RuntimeError(_support.OUTPUT_SENTINEL)

            monkeypatch.setattr(admin_commands, reader, failing)
            expected_failure = format_operator_error(RuntimeError("failure"))
        else:
            payload = _SUCCESS_REPORTS.get(route, {})
            monkeypatch.setattr(
                admin_commands, reader, lambda *_args, **_kwargs: RootModel[dict](payload)
            )
            expected_failure = format_operator_error(RuntimeError("failure"))
    # One prepared outcome per admitted command call. The build-failure case stops at the first call,
    # so no restart is queued.
    outcomes: tuple[bytes | BaseException, ...] = (
        (failure,)
        if outcome == "checked-failure"
        else (success, failure)
        if outcome == "restart-queue-failure"
        else (success, success)
        if follow_up is not None
        else (success,)
    )
    boundary = _support.ScriptedProcessBoundary(outcomes)
    application = _support.admin_web_app(
        root, settings, clock=_support.ControlledClock(), process_runner=boundary
    )
    client = _support.authenticated_client(application)
    csrf = client.get("/auth/session").json()["csrf_token"]
    log_path = root / _support.COMMAND_LOG_PATH
    entries_before = len(log_path.read_text(encoding="utf-8").splitlines())
    marker = AUTOMATIC_HEADER if marked else {}

    if method == "GET":
        response = client.get(path, headers=marker)
    else:
        response = client.post(
            path,
            json=body,
            headers={"Origin": _support.ORIGIN, "X-CSRF-Token": csrf, **marker},
        )

    # A command failure is a transient envelope with its checked code, never a transport error.
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    payload = response.json()
    assert set(payload) == {"exit_code", "report", "failure_line", "guidance_line"}

    if follow_up is not None:
        # The answered build is the one response. A queued restart does not appear in it, however
        # that restart's own call ends.
        if outcome == "checked-failure":
            assert payload["exit_code"] == 1
            assert payload["report"] is None
            assert payload["failure_line"] == format_operator_error(failure)
            assert payload["guidance_line"] == expected_guidance
            assert _support.OUTPUT_SENTINEL not in response.text
        else:
            assert payload == {
                "exit_code": 0,
                "report": {},
                "failure_line": None,
                "guidance_line": None,
            }

        expected_tails = [tail] if outcome == "checked-failure" else [tail, follow_up]
        assert boundary.calls == [
            {
                "argv": (sys.executable, str(root / "scripts" / "admin.py"), *expected_tail),
                "cwd": root,
            }
            for expected_tail in expected_tails
        ]
        lines = log_path.read_text(encoding="utf-8").splitlines()
        expected_entries = (
            [("rebuild-admin", "failure")]
            if outcome == "checked-failure"
            else [("rebuild-admin", "success"), ("restart-admin", "success")]
            if outcome == "success"
            else [("rebuild-admin", "success"), ("restart-admin", "failure")]
        )
        # Both commands are explicit actions, so neither marker suppresses its own entry.
        assert len(lines) == entries_before + len(expected_entries)
        entries = [json.loads(line) for line in lines[entries_before:]]
        assert [(entry["command"], entry["result"]) for entry in entries] == expected_entries
        for entry in entries:
            assert entry["exit_code"] == (0 if entry["result"] == "success" else 1)
        for value in sensitive:
            assert value not in lines[-1]
        return

    if outcome == "success":
        scoped = _SUCCESS_REPORTS.get(route, {})
        assert payload == {
            "exit_code": 0,
            "report": (
                {"role": "working", "report": scoped} if route in _ROLE_SCOPED_ROUTES else scoped
            ),
            "failure_line": None,
            "guidance_line": None,
        }
    else:
        assert payload["exit_code"] == 1
        assert payload["report"] is None
        assert payload["failure_line"] == (
            expected_failure if in_process else format_operator_error(failure)
        )
        assert payload["guidance_line"] == expected_guidance
        assert _support.OUTPUT_SENTINEL not in response.text

    # The marker changes no argument list, and every subprocess outcome runs the one admitted command.
    if not in_process:
        assert boundary.calls == [
            {"argv": (sys.executable, str(root / "scripts" / "admin.py"), *tail), "cwd": root}
        ]
    lines = log_path.read_text(encoding="utf-8").splitlines()
    if marked and outcome == "success" and route in _AUTOMATIC_READ_ROUTES:
        # A successful automatic read leaves the sole command log as it was.
        assert len(lines) == entries_before
        return
    assert len(lines) == entries_before + 1
    entry = json.loads(lines[-1])
    assert entry["result"] == ("success" if outcome == "success" else "failure")
    assert entry["exit_code"] == (0 if outcome == "success" else 1)
    # The retained entry carries no identity the request supplied.
    assert TARGET_ID not in lines[-1]
    assert DATASET_ID not in lines[-1]
    for value in sensitive:
        assert value not in lines[-1]


@pytest.mark.parametrize("send_completes", [True, False])
def test_admin_restart_waits_for_response_completion(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, send_completes: bool
) -> None:
    """The self-rebuild queues its restart only after the final response body send completes."""
    root = _support.site_root(monkeypatch, tmp_path)
    settings = _support.admin_web_settings()
    success = _report_bytes()
    boundary = _support.ScriptedProcessBoundary((success, success))
    application = _support.admin_web_app(
        root, settings, clock=_support.ControlledClock(), process_runner=boundary
    )
    client = _support.site_client(application)
    assert _support.login(client, csrf_token=_support.bootstrap(client)).status_code == 200
    csrf = client.get("/auth/session").json()["csrf_token"]
    cookie = _support.session_cookie(client)
    build_tail = ("rebuild-admin",)
    restart_tail = ("restart-admin",)
    log_path = root / _support.COMMAND_LOG_PATH
    entries_before = len(log_path.read_text(encoding="utf-8").splitlines())

    # The admitted call count observed while the final body send is being awaited.
    awaited: list[int] = []
    messages: list[str] = []

    async def send(message: dict[str, object]) -> None:
        if message["type"] == "http.response.body" and not message.get("more_body", False):
            awaited.append(len(boundary.calls))
            if not send_completes:
                raise OSError("synthetic send failure")
        messages.append(str(message["type"]))

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"{}", "more_body": False}

    scope: dict[str, object] = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": "/api/settings/rebuild-admin",
        "raw_path": b"/api/settings/rebuild-admin",
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"host", settings.admin_web_origin.removeprefix("https://").encode()),
            (b"origin", _support.ORIGIN.encode()),
            (b"content-type", b"application/json"),
            (b"x-csrf-token", csrf.encode()),
            (b"cookie", f"{_support.SESSION_COOKIE_NAME}={cookie}".encode()),
        ],
        "client": ("127.0.0.1", _support.admin_web_settings().admin_web_port),
        "server": ("localhost", _support.admin_web_settings().admin_web_port),
    }

    if send_completes:
        asyncio.run(application(scope, receive, send))
    else:
        # A send that fails after the response started reaches the middleware's content-free failure.
        with pytest.raises(RuntimeError) as failed:
            asyncio.run(application(scope, receive, send))
        assert "synthetic send failure" not in str(failed.value)

    # The response start always reaches the client. The body reaches it when that send succeeds.
    assert messages == (
        ["http.response.start", "http.response.body"] if send_completes else ["http.response.start"]
    )
    assert awaited == [1], "the restart was queued before the final body send completed"

    expected_tails = [build_tail] if not send_completes else [build_tail, restart_tail]
    assert boundary.calls == [
        {"argv": (sys.executable, str(root / "scripts" / "admin.py"), *tail), "cwd": root}
        for tail in expected_tails
    ]
    entries = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()[entries_before:]
    ]
    assert [(entry["command"], entry["result"], entry["exit_code"]) for entry in entries] == (
        [("rebuild-admin", "success", 0)]
        if not send_completes
        else [("rebuild-admin", "success", 0), ("restart-admin", "success", 0)]
    )
