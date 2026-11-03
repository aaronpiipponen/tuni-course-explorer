"""Contracts for the fixed rebuild of the frontend, containers, web unit and its bind, and for the
administration frontend build and its own-unit restart.

One small process-boundary double answers the fixed systemd, npm, Compose and socket reads, so no
real restart or recreation ever runs. Every parameter performs exactly one public rebuild and
asserts the executed prefix, the first-failure cutoff and that nothing beyond the fixed prepared
steps was reached. The administration commands are proven separately: one invocation performs only
its own build or restart of this checkout's own administration unit.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from course_explorer import administration
from course_explorer.config import ENVIRONMENT_ONLY_SETTINGS_SOURCE, SETTINGS_SOURCE_MARKER
from course_explorer_admin import mechanics, rebuild, server
from course_explorer_admin.lifecycle import InferenceProgress, LifecycleState, write_lifecycle_state
from tests.admin._rebuild_support import (
    _ADMIN_UNIT,
    _OWNED_PROCESS,
    _SENTINEL,
    _UNIT,
    _WEB_HOST,
    _WEB_PORT,
    _WEB_WORKERS,
    _RebuildProcessBoundary,
)
from tests.support import REPO_ROOT, public_environment

_OTHER_UNIT = "synthetic-other-site.service"
_STOP_TIMEOUT_SECONDS = "77"
_STARTUP_ATTEMPTS = "3"
_POLL_INTERVAL_SECONDS = "0.01"
_OTHER_ADDRESS = "192.0.2.10"
_REBUILD_STEPS = (
    "up",
    "-d",
    "--wait",
    "--force-recreate",
    "--no-build",
    "--pull",
    "never",
    "db",
    "embedding",
)


def _bind_rebuild_roots(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, scope: str = "user"
) -> Path:
    """Bind both site identities, the web manager scope, the timing policy and the checkout."""
    monkeypatch.setenv("ADMIN_SITE_WEB_SERVICE_UNIT", _UNIT)
    monkeypatch.setenv("ADMIN_SITE_ADMIN_SERVICE_UNIT", _ADMIN_UNIT)
    monkeypatch.setenv("ADMIN_SITE_WEB_SERVICE_SCOPE", scope)
    monkeypatch.setenv("WEB_HOST", _WEB_HOST)
    monkeypatch.setenv("WEB_PORT", str(_WEB_PORT))
    monkeypatch.setenv("WEB_WORKERS", str(_WEB_WORKERS))
    monkeypatch.setenv("ADMIN_STOP_TIMEOUT_SECONDS", _STOP_TIMEOUT_SECONDS)
    monkeypatch.setenv("ADMIN_STARTUP_ATTEMPTS", _STARTUP_ATTEMPTS)
    monkeypatch.setenv("ADMIN_POLL_INTERVAL_SECONDS", _POLL_INTERVAL_SECONDS)
    root = tmp_path / "checkout"
    root.mkdir()
    monkeypatch.setattr(administration, "repository_root", lambda: root)
    return root


@pytest.mark.parametrize("scope", ["user", "system"])
@pytest.mark.parametrize(
    ("case", "fail_step", "wrong_site", "listeners"),
    [
        (
            "success",
            None,
            False,
            (
                (f"127.0.0.1:{_WEB_PORT}", _OWNED_PROCESS),
                # A listener of another process on the same port is not this bind.
                (f"{_OTHER_ADDRESS}:{_WEB_PORT}", ""),
            ),
        ),
        ("wrong-site-unit", None, True, ()),
        ("build-failure", "frontend", False, ()),
        ("container-failure", "containers", False, ()),
        ("restart-failure", "restart", False, ()),
        (
            "non-loopback-listener",
            None,
            False,
            ((f"{_OTHER_ADDRESS}:{_WEB_PORT}", _OWNED_PROCESS),),
        ),
    ],
)
def test_rebuild_runs_only_the_remaining_fixed_steps(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    scope: str,
    case: str,
    fail_step: str | None,
    wrong_site: bool,
    listeners: tuple[tuple[str, str], ...],
) -> None:
    """One rebuild stops at its first failure and otherwise verifies its own loopback bind."""
    root = _bind_rebuild_roots(monkeypatch, tmp_path, scope=scope)
    boundary = _RebuildProcessBoundary(
        root=root,
        unit=_UNIT,
        working_directory=tmp_path / "another-checkout" if wrong_site else None,
        fail_step=fail_step,
        listeners=listeners,
    )
    expected_labels = {
        "success": [
            "unit",
            "git",
            "git",
            "frontend",
            "containers",
            "unit",
            "git",
            "git",
            "restart",
            "unit",
            "git",
            "git",
            "bind",
        ],
        "wrong-site-unit": ["unit"],
        "build-failure": ["unit", "git", "git", "frontend"],
        "container-failure": ["unit", "git", "git", "frontend", "containers"],
        "restart-failure": [
            "unit",
            "git",
            "git",
            "frontend",
            "containers",
            "unit",
            "git",
            "git",
            "restart",
        ],
        "non-loopback-listener": [
            "unit",
            "git",
            "git",
            "frontend",
            "containers",
            "unit",
            "git",
            "git",
            "restart",
            "unit",
            "git",
            "git",
            "bind",
        ],
    }[case]

    if case == "success":
        report = rebuild.rebuild_site(runner=boundary)
        assert report.steps == ("frontend", "containers", "web", "bind")
        assert (report.host, report.port) == (_WEB_HOST, _WEB_PORT)
    elif case in {"wrong-site-unit", "non-loopback-listener"}:
        with pytest.raises(ValueError) as refused:
            rebuild.rebuild_site(runner=boundary)
        assert _SENTINEL not in str(refused.value)
    else:
        with pytest.raises(subprocess.CalledProcessError) as failed:
            rebuild.rebuild_site(runner=boundary)
        assert failed.value.returncode == 1
        assert _SENTINEL not in str(failed.value)

    assert [label for label in boundary.labels() if label not in {"unit", "git"}] == [
        label for label in expected_labels if label not in {"unit", "git"}
    ]

    bridge = mechanics.compose_prefix(non_interactive=True, interpreter=True)
    # Every rebuild step is bounded by the configured foreground subprocess ceiling.
    step_timeouts = {
        timeout
        for command, timeout in boundary.calls
        if command[: len(bridge)] == bridge or command[0] in {"npm", "ss"}
    }
    expected_steps = [label for label in expected_labels if label != "unit" and label != "git"]
    assert step_timeouts == ({float(_STOP_TIMEOUT_SECONDS)} if expected_steps else set())

    commands = [command for command, _ in boundary.calls]
    assert all(
        command[0] not in {"ssh", "wsl.exe", "docker", "du", "pkill"} for command in commands
    )
    # No step removes a volume, tears the stack down, or builds or downloads an image.
    assert all(not (set(command) & {"volume", "down", "rm", "prune"}) for command in commands)
    expected_show = (
        ("systemctl", "show", _UNIT)
        if scope == "system"
        else ("systemctl", "--user", "show", _UNIT)
    )
    for command in commands:
        if command[:3] == ("systemctl", "--user", "show") or command[:2] == (
            "systemctl",
            "show",
        ):
            assert command[: len(expected_show)] == expected_show
    restarts = [command for command in commands if "restart" in command]
    if "restart" in expected_labels:
        expected_restart = (
            ("sudo", "-n", "/usr/bin/systemctl", "restart", _UNIT)
            if scope == "system"
            else ("systemctl", "--user", "restart", _UNIT)
        )
        assert restarts == [expected_restart]
        assert restarts[0][-1] != _OTHER_UNIT
    else:
        assert restarts == []
    prefixes = bridge
    compose = next((command for command in commands if command[: len(prefixes)] == prefixes), None)
    if "containers" in expected_labels:
        assert compose == (*prefixes, *_REBUILD_STEPS)
    else:
        assert compose is None
    npm = next((command for command in commands if command[0] == "npm"), None)
    if npm is not None:
        assert npm == ("npm", "--prefix", "web", "run", "build")
    else:
        assert case == "wrong-site-unit"

    # The rebuild retains no receipt, state file or any other file in the checkout.
    assert list(root.rglob("*")) == []


@pytest.mark.parametrize("site_scope", ["user", "system"])
@pytest.mark.parametrize(
    "action",
    ["build", "restart"],
)
@pytest.mark.parametrize(
    "case",
    ["success", "unit-not-loaded", "wrong-checkout", "wrong-launcher", "step-failure"],
)
def test_admin_maintenance_commands_act_only_on_their_own_unit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, site_scope: str, action: str, case: str
) -> None:
    """One administration build or restart mutates this checkout's own administration unit alone.

    The feature web unit's configured scope varies, and the administration commands address the
    user manager and their own unit.
    """
    root = _bind_rebuild_roots(monkeypatch, tmp_path, scope=site_scope)
    boundary = _RebuildProcessBoundary(
        root=root,
        unit=_UNIT,
        admin_loaded=case != "unit-not-loaded",
        admin_working_directory=tmp_path / "another-checkout" if case == "wrong-checkout" else None,
        admin_launcher=(
            tmp_path / "another-checkout" / "scripts" / "run_admin_web.sh"
            if case == "wrong-launcher"
            else None
        ),
        fail_admin_build=case == "step-failure" and action == "build",
        fail_admin_restart=case == "step-failure" and action == "restart",
    )
    command = rebuild.rebuild_admin if action == "build" else rebuild.restart_admin

    if case == "success":
        report = command(runner=boundary)
        if action == "build":
            assert report.steps == ("frontend",)
            assert report.schema_version == 1
        else:
            assert report.restart_queued is True
            assert report.schema_version == 1
    elif case in {"unit-not-loaded", "wrong-checkout", "wrong-launcher"}:
        # The own-unit check refuses before the build or the restart mutates anything.
        with pytest.raises(ValueError) as refused:
            command(runner=boundary)
        assert _SENTINEL not in str(refused.value)
    else:
        with pytest.raises(subprocess.CalledProcessError) as failed:
            command(runner=boundary)
        assert failed.value.returncode == 1
        assert _SENTINEL not in str(failed.value)

    attempted = case in {"success", "step-failure"}
    expected_labels = {
        "build": ["unit", "admin-frontend"] if attempted else ["unit"],
        "restart": ["unit", "admin-restart"] if attempted else ["unit"],
    }[action]
    assert [label for label in boundary.labels() if label not in {"unit", "git"}] == [
        label for label in expected_labels if label not in {"unit", "git"}
    ]

    commands = [recorded for recorded, _ in boundary.calls]
    # Only the configured administration unit is addressed, and only its own frontend is built.
    unit_reads = [command for command in commands if command[:3] == ("systemctl", "--user", "show")]
    assert all(command[:2] != ("systemctl", "show") for command in commands)
    assert unit_reads == [
        (
            "systemctl",
            "--user",
            "show",
            _ADMIN_UNIT,
            "--no-pager",
            *(
                argument
                for property_name in server._SITE_PROPERTIES
                for argument in ("-p", property_name)
            ),
        )
    ]
    assert all(_UNIT not in command and _OTHER_UNIT not in command for command in commands)
    if action == "build" and attempted:
        assert ("npm", "--prefix", "admin-web", "run", "build") in commands
    if action == "restart" and attempted:
        assert ("systemctl", "--user", "--no-block", "restart", _ADMIN_UNIT) in commands

    # Neither command touches Compose, Git metadata, a listener, the feature web or the worker.
    assert all(
        command[0] not in {"git", "ss", "du", "ssh", "wsl.exe", "docker", "pkill", "sudo", "uv"}
        for command in commands
    )
    # Every attempted mutating step is bounded by the configured foreground subprocess ceiling.
    step_timeouts = {
        timeout
        for command, timeout in boundary.calls
        if command[0] == "npm" or "restart" in command
    }
    assert step_timeouts == ({float(_STOP_TIMEOUT_SECONDS)} if attempted else set())

    # The administration commands retain no receipt, state file or any other file in the checkout.
    assert list(root.rglob("*")) == []


_DEPLOY_SCRIPT = Path(__file__).resolve().parents[2] / "deploy" / "deploy.sh"
_STAGE_GUARD = (
    "from course_explorer_admin.datasets import require_stages_idle; require_stages_idle()"
)


def test_deploy_refuses_busy_stages_before_mutation(tmp_path: Path) -> None:
    """The deploy script stops at a non-idle stage before any build or restart.

    The real script runs against a scratch checkout holding only a Python wrapper, which recognizes
    the exact guard string and runs it with this suite's interpreter after binding the checkout.
    Rejecting npm, sudo, systemctl and ss stubs come first on the child path, and every other
    interpreter invocation is rejected and logged.
    """
    root = tmp_path / "checkout"
    (root / ".venv" / "bin").mkdir(parents=True)
    stubs = tmp_path / "bin"
    stubs.mkdir()
    invocation_log = tmp_path / "invocations.log"
    mutation_log = tmp_path / "mutations.log"
    guard_log = tmp_path / "guard.log"
    child = tmp_path / "guard.py"
    admin_state = "data/admin-tests/deploy-guard"
    stage_root = root / admin_state / "inference" / "current"
    stage_root.mkdir(parents=True)
    write_lifecycle_state(
        stage_root,
        LifecycleState(
            session_id="e" * 32,
            lifecycle="running",
            requested_action="run",
            progress=InferenceProgress(kind="inference"),
            work_complete=False,
            active_seconds=0.0,
        ),
    )
    child.write_text(
        "\n".join(
            (
                "from pathlib import Path",
                "from course_explorer import administration",
                f"administration.repository_root = lambda: Path({str(root)!r})",
                "from course_explorer_admin.datasets import require_stages_idle",
                "require_stages_idle()",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    wrapper = root / ".venv" / "bin" / "python"
    wrapper.write_text(
        "\n".join(
            (
                "#!/usr/bin/bash",
                "set -euo pipefail",
                f'printf "%s\\n" "$*" >> "{invocation_log}"',
                f'if [[ $# -eq 2 && "$1" == "-c" && "$2" == "{_STAGE_GUARD}" ]]; then',
                f'  printf "guard\\n" >> "{guard_log}"',
                f'  exec "{sys.executable}" "{child}"',
                "fi",
                f'printf "rejected\\n" >> "{mutation_log}"',
                "exit 64",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o700)
    for name in ("npm", "sudo", "systemctl", "ss"):
        stub = stubs / name
        stub.write_text(
            "\n".join(
                (
                    "#!/usr/bin/bash",
                    f'printf "%s %s\\n" "{name}" "$*" >> "{mutation_log}"',
                    "exit 1",
                )
            )
            + "\n",
            encoding="utf-8",
        )
        stub.chmod(0o700)

    environment = public_environment()
    environment.update(
        {
            SETTINGS_SOURCE_MARKER: ENVIRONMENT_ONLY_SETTINGS_SOURCE,
            "INFERENCE_CONTROLLER_STATE_ROOT": f"{admin_state}/inference",
            "HOME": str(tmp_path),
            "PATH": f"{stubs}:/usr/bin:/bin",
            "PYTHONPATH": str(REPO_ROOT / "src"),
        }
    )
    result = subprocess.run(
        ("bash", str(_DEPLOY_SCRIPT), "a" * 40),
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode != 0
    assert guard_log.read_text(encoding="utf-8") == "guard\n"
    assert not mutation_log.exists()
    assert invocation_log.read_text(encoding="utf-8").strip() == f"-c {_STAGE_GUARD}"
