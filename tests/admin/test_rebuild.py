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
from pathlib import Path

import pytest

from course_explorer_admin import mechanics, rebuild, server

_UNIT = "synthetic-site-web.service"
_ADMIN_UNIT = "synthetic-site-admin.service"
_OTHER_UNIT = "synthetic-other-site.service"
_WEB_HOST = "127.0.0.1"
_WEB_PORT = 18026
_WEB_WORKERS = 2
_STOP_TIMEOUT_SECONDS = "77"
_STARTUP_ATTEMPTS = "3"
_POLL_INTERVAL_SECONDS = "0.01"
_MAIN_PID = 4242
_RESTARTED_PID = 5252
_SENTINEL = "synthetic-failure-output"
_OTHER_ADDRESS = "192.0.2.10"
_OWNED_PROCESS = 'users:(("python",pid={owner},fd=4))'
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


class _RebuildProcessBoundary:
    """Answer the fixed rebuild process reads and record every command in order.

    The web unit is answered with this checkout's web launcher and the administration unit with this
    checkout's administration launcher, so an owner that selects the wrong unit or the wrong launcher
    is refused before it mutates anything. The administration build and restart outcomes are decided
    by their own flags, so one double serves the site rebuild, the administration build and the
    administration restart. The double answers both the user-manager and the system-manager command
    forms, and the public-contract assertions verify that the configured manager selects the form.
    """

    def __init__(
        self,
        *,
        root: Path,
        unit: str,
        working_directory: Path | None = None,
        fail_step: str | None = None,
        listeners: tuple[tuple[str, str], ...] = (),
        admin_unit: str = _ADMIN_UNIT,
        admin_loaded: bool = True,
        admin_working_directory: Path | None = None,
        admin_launcher: Path | None = None,
        fail_admin_build: bool = False,
        fail_admin_restart: bool = False,
    ) -> None:
        self.root = root
        self.unit = unit
        self.working_directory = root if working_directory is None else working_directory
        self.fail_step = fail_step
        self.listeners = listeners
        self.admin_unit = admin_unit
        self.admin_loaded = admin_loaded
        self.admin_working_directory = admin_working_directory
        self.admin_launcher = admin_launcher
        self.fail_admin_build = fail_admin_build
        self.fail_admin_restart = fail_admin_restart
        self.calls: list[tuple[tuple[str, ...], float | None]] = []
        self.restarted = False
        self.admin_restart_queued = False

    def run(
        self,
        argv,
        *,
        cwd: Path | None = None,
        env: object = None,
        stdin_path: Path | None = None,
        stdout_path: Path | None = None,
        timeout: float | None = None,
    ) -> subprocess.CompletedProcess[bytes]:
        command = tuple(argv)
        self.calls.append((command, timeout))
        if command[:3] == ("systemctl", "--user", "show"):
            return self._completed(command, self._unit_properties(command[3]))
        if command[:2] == ("systemctl", "show"):
            return self._completed(command, self._unit_properties(command[2]))
        if command[:3] == ("systemctl", "--user", "restart"):
            if self.fail_step == "restart":
                self._fail(command)
            self.restarted = True
            return self._completed(command, b"")
        if command[:4] == ("sudo", "-n", "/usr/bin/systemctl", "restart"):
            if self.fail_step == "restart":
                self._fail(command)
            self.restarted = True
            return self._completed(command, b"")
        if command[:4] == ("systemctl", "--user", "--no-block", "restart"):
            if self.fail_admin_restart:
                self._fail(command)
            self.admin_restart_queued = True
            return self._completed(command, b"")
        if command[:2] == ("git", "branch"):
            return self._completed(command, b"synthetic-branch\n")
        if command[:2] == ("git", "rev-parse"):
            return self._completed(command, ("c" * 40 + "\n").encode())
        if command[0] == "npm":
            if "admin-web" in command and self.fail_admin_build:
                self._fail(command)
            if "admin-web" not in command and self.fail_step == "frontend":
                self._fail(command)
            return self._completed(command, b"")
        if command[: len(mechanics.compose_prefix(non_interactive=True))] == (
            mechanics.compose_prefix(non_interactive=True)
        ):
            if self.fail_step == "containers":
                self._fail(command)
            return self._completed(command, b"")
        if command[0] == "ss":
            return self._completed(command, self._listener_listing())
        raise AssertionError(f"the rebuild ran an unexpected process command: {command[0]}")

    def _fail(self, command: tuple[str, ...]) -> None:
        raise subprocess.CalledProcessError(
            1, list(command), output=_SENTINEL.encode(), stderr=_SENTINEL.encode()
        )

    def _completed(
        self, command: tuple[str, ...], stdout: bytes
    ) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(list(command), 0, stdout=stdout, stderr=b"")

    def _unit_properties(self, unit: str) -> bytes:
        if unit == self.admin_unit:
            load_state = "loaded" if self.admin_loaded else "not-found"
            working_directory = (
                self.root if self.admin_working_directory is None else self.admin_working_directory
            )
            launcher = (
                self.root / "scripts" / "run_admin_web.sh"
                if self.admin_launcher is None
                else self.admin_launcher
            )
        else:
            load_state = "loaded"
            working_directory = self.working_directory
            launcher = self.root / "scripts" / "run_web.sh"
        return "".join(
            f"{name}={value}\n"
            for name, value in (
                ("LoadState", load_state),
                ("ActiveState", "active"),
                ("SubState", "running"),
                ("MainPID", str(_RESTARTED_PID if self.restarted else _MAIN_PID)),
                ("ActiveEnterTimestampMonotonic", "1000000"),
                ("WorkingDirectory", str(working_directory)),
                (
                    "ExecStart",
                    "{ path=/usr/bin/bash ; argv[]=/usr/bin/bash "
                    f"{launcher} ; ignore_errors=no ; "
                    "start_time=[n/a] ; stop_time=[n/a] }",
                ),
            )
        ).encode()

    def _listener_listing(self) -> bytes:
        return "".join(
            f"LISTEN 0 2048 {address} 0.0.0.0:* {owners.format(owner=_RESTARTED_PID)}\n"
            for address, owners in self.listeners
        ).encode()

    def labels(self) -> list[str]:
        """Return the recorded commands as their step labels, in execution order."""
        labels: list[str] = []
        for command, _ in self.calls:
            if command[:3] == ("systemctl", "--user", "show") or command[:2] == (
                "systemctl",
                "show",
            ):
                labels.append("unit")
            elif command[:3] == ("systemctl", "--user", "restart") or command[:4] == (
                "sudo",
                "-n",
                "/usr/bin/systemctl",
                "restart",
            ):
                labels.append("restart")
            elif command[:4] == ("systemctl", "--user", "--no-block", "restart"):
                labels.append("admin-restart")
            elif command[0] == "git":
                labels.append("git")
            elif command[0] == "npm" and "admin-web" in command:
                labels.append("admin-frontend")
            elif command[0] == "npm":
                labels.append("frontend")
            elif command[0] == "ss":
                labels.append("bind")
            else:
                labels.append("containers")
        return labels


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
    monkeypatch.setattr(rebuild, "repository_root", lambda: root)
    monkeypatch.setattr(server, "repository_root", lambda: root)
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
            "restart",
            "unit",
            "git",
            "git",
            "bind",
        ],
        "wrong-site-unit": ["unit"],
        "build-failure": ["unit", "git", "git", "frontend"],
        "container-failure": ["unit", "git", "git", "frontend", "containers"],
        "restart-failure": ["unit", "git", "git", "frontend", "containers", "restart"],
        "non-loopback-listener": [
            "unit",
            "git",
            "git",
            "frontend",
            "containers",
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

    assert boundary.labels() == expected_labels

    # Every rebuild step is bounded by the configured foreground subprocess ceiling.
    step_timeouts = {
        timeout
        for command, timeout in boundary.calls
        if command[0] in {"npm", "ss", "uv"} or "restart" in command
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
    prefixes = mechanics.compose_prefix(non_interactive=True)
    compose = next((command for command in commands if command[0] == "uv"), None)
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
    assert boundary.labels() == expected_labels

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
