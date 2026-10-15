"""Sole explicit worker code-setup/update and prepared-checkout owner.

This module owns the one explicit operation that brings the already-provisioned worker checkout
onto a selected GitHub-origin branch with ``git pull --ff-only``, the worker-side package/dependency
bootstrap and pointed resource preparation, and the read-only preflight that verifies prepared code
and worker resources. The remote update is a fast-forward pull, and the bootstrap and pointed
resource preparation run
through the captured, completion-reported transport, so the provisioned worker's sudo must be
passwordless. Code
sync is separate from the recurring translation/inference lifecycle, which validates prepared code
through ``worker_session.require_worker_checkout``.
"""

from __future__ import annotations

import shlex
import subprocess
import tomllib
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict

from course_explorer.administration import repository_root
from course_explorer.config import (
    WorkerConnectionSettings,
    WorkerSetupSettings,
    load_worker_connection_settings,
    load_worker_setup_settings,
)
from course_explorer_admin import mechanics
from course_explorer_admin.provisioning_worker import (
    SYSTEM_PACKAGES,
    WorkerResourcesReport,
)
from course_explorer_admin.transport import SshWslTransport

_SSH_BATCH_COMMAND = "core.sshCommand=ssh -o BatchMode=yes"
_UV_INSTALL_URL = "https://astral.sh/uv/install.sh"


def _repository_project_name() -> str:
    """Read this repository's own distribution name from its tracked pyproject metadata.

    The locked code-only sync reinstalls this editable project so a pyproject-only change refreshes
    the installed distribution, which uv's editable-install freshness otherwise ignores.
    """
    metadata = tomllib.loads((repository_root() / "pyproject.toml").read_text(encoding="utf-8"))
    return metadata["project"]["name"]


_PROJECT_NAME = _repository_project_name()


class WorkerCodeReport(BaseModel):
    """Ordinary frozen report of one explicit worker code update or prepared-code read."""

    model_config = ConfigDict(frozen=True)

    branch: str
    revision: str
    server_origin_differs: bool


class ProvisioningReport(BaseModel):
    """Ordinary frozen report of one setup/update/preflight operation."""

    model_config = ConfigDict(frozen=True)

    code: WorkerCodeReport
    resources: WorkerResourcesReport | None


def update_worker_code(
    *, branch: str = "main", runner: mechanics.ProcessRunner
) -> WorkerCodeReport:
    """Fast-forward the worker checkout to one origin branch, then sync its locked environment.

    The dependency sync installs only the locked project environment. The resource and preparation
    actions own apt packages, artifacts, and runtimes. The remote update is the fast-forward pull
    alone.
    """
    report = _update_worker_code(branch=branch, runner=runner)
    connection = load_worker_connection_settings()
    setup = load_worker_setup_settings()
    transport = SshWslTransport(runner, connection)
    _sync_worker_dependencies(transport, connection, setup)
    return report


def _update_worker_code(
    *, branch: str = "main", runner: mechanics.ProcessRunner
) -> WorkerCodeReport:
    """Update the worker checkout body."""
    root = repository_root()
    _validate_branch(runner, root, branch)
    setup = load_worker_setup_settings()
    server_branch, server_revision = mechanics.require_prepared_checkout(runner, root)
    _require_matching_origin(runner, root, setup.worker_setup_project_url)
    server_origin_differs = _server_origin_differs(
        runner, root, branch=server_branch, revision=server_revision, fetch=True
    )
    connection = load_worker_connection_settings()
    transport = SshWslTransport(runner, connection)
    worker_branch, revision = _update_worker_checkout(
        transport,
        connection,
        branch=branch,
        project_url=setup.worker_setup_project_url,
    )
    return WorkerCodeReport(
        branch=worker_branch, revision=revision, server_origin_differs=server_origin_differs
    )


def preflight_worker(*, runner: mechanics.ProcessRunner) -> ProvisioningReport:
    """Read-only prepared-code and worker-resource check. Installs, builds, and downloads nothing."""
    root = repository_root()
    setup = load_worker_setup_settings()
    branch, revision = mechanics.require_prepared_checkout(runner, root)
    _require_matching_origin(runner, root, setup.worker_setup_project_url)
    server_origin_differs = _server_origin_differs(
        runner, root, branch=branch, revision=revision, fetch=False
    )
    connection = load_worker_connection_settings()
    transport = SshWslTransport(runner, connection)
    worker_branch, worker_revision = _read_worker_checkout(transport, connection)
    code = WorkerCodeReport(
        branch=worker_branch, revision=worker_revision, server_origin_differs=server_origin_differs
    )
    if not _worker_dependencies_ready(transport, connection):
        return ProvisioningReport(
            code=code, resources=WorkerResourcesReport(ready=False, missing=["dependencies"])
        )
    return ProvisioningReport(code=code, resources=_read_worker_resources(transport, connection))


def prepare_worker(*, branch: str = "main", runner: mechanics.ProcessRunner) -> ProvisioningReport:
    """Update code, stream the worker bootstrap, prepare pointed resources, and report readiness."""
    code = _update_worker_code(branch=branch, runner=runner)
    connection = load_worker_connection_settings()
    setup = load_worker_setup_settings()
    transport = SshWslTransport(runner, connection)
    _bootstrap_worker(transport, connection, setup)
    _prepare_worker_resources(transport, connection, setup)
    return ProvisioningReport(code=code, resources=_read_worker_resources(transport, connection))


def _sync_worker_dependencies(
    transport: SshWslTransport, connection: WorkerConnectionSettings, setup: WorkerSetupSettings
) -> None:
    """Install the locked project environment on the already-pulled worker checkout.

    This sync needs no terminal, so it uses the same captured, completion-reported transport path
    as the read-only locked preflight check. It also reinstalls this repository's own editable
    project so a pyproject-only code update refreshes its installed distribution for the preflight
    check.
    """
    transport.run(
        ("uv", "sync", "--locked", "--reinstall-package", _PROJECT_NAME),
        cwd=PurePosixPath(str(connection.worker_project_root)),
        env={"SELECTED_DATASET_ENABLED": "0"},
        timeout=setup.worker_setup_timeout_seconds,
    )


def _validate_branch(runner: mechanics.ProcessRunner, root: Path, branch: str) -> None:
    try:
        runner.run(("git", "check-ref-format", "--branch", branch), cwd=root)
    except subprocess.CalledProcessError as exc:
        raise ValueError("worker setup branch is not a valid Git branch name") from exc


def _require_matching_origin(runner: mechanics.ProcessRunner, root: Path, project_url: str) -> None:
    actual = runner.run(("git", "remote", "get-url", "origin"), cwd=root).stdout.decode().strip()
    if actual != project_url:
        raise ValueError("configured origin does not match WORKER_SETUP_PROJECT_URL")


def _server_origin_differs(
    runner: mechanics.ProcessRunner,
    root: Path,
    *,
    branch: str,
    revision: str,
    fetch: bool,
) -> bool:
    """Report whether the local checkout HEAD differs from its stored origin tracking ref."""
    if fetch:
        runner.run(("git", "-c", _SSH_BATCH_COMMAND, "fetch", "origin"), cwd=root)
    tracked = (
        runner.run(
            ("git", "for-each-ref", "--format=%(objectname)", f"refs/remotes/origin/{branch}"),
            cwd=root,
        )
        .stdout.decode()
        .strip()
    )
    return tracked != revision


def _update_worker_checkout(
    transport: SshWslTransport,
    connection: WorkerConnectionSettings,
    *,
    branch: str,
    project_url: str,
) -> tuple[str, str]:
    worker_root = connection.worker_project_root
    # Refuse a dirty or detached checkout through the one shared full-tree read before the worker
    # fetch/branch-switch/pull script can change it. The requested branch is selected
    # from the worker's tracking branches independently. The server and worker branch names may
    # differ.
    current_branch, _revision = _read_worker_checkout(transport, connection)
    script = _worker_update_script(
        worker_root,
        project_url,
        branch,
        current_branch=current_branch,
    )
    transport.run(
        ("bash", "-c", script),
        cwd=PurePosixPath(str(worker_root)),
    )
    return _read_worker_checkout(transport, connection)


def _read_worker_checkout(
    transport: SshWslTransport, connection: WorkerConnectionSettings
) -> tuple[str, str]:
    worker_root = connection.worker_project_root

    def run(argv: Sequence[str]) -> bytes:
        return transport.run(tuple(argv), cwd=PurePosixPath(str(worker_root)))

    return mechanics.read_prepared_checkout(run, full_tree=True)


def _worker_update_script(
    worker_root: Path,
    project_url: str,
    branch: str,
    *,
    current_branch: str,
) -> str:
    root = shlex.quote(str(worker_root))
    url = shlex.quote(project_url)
    name = shlex.quote(branch)
    local_ref = shlex.quote(f"refs/heads/{branch}")
    remote_ref = shlex.quote(f"refs/remotes/origin/{branch}")
    tracking = shlex.quote(f"origin/{branch}")
    ssh_config = shlex.quote(_SSH_BATCH_COMMAND)
    if current_branch == branch:
        selection = ""
    else:
        selection = (
            f"if git show-ref --verify --quiet {local_ref}; then "
            f"  git checkout {name}; "
            "else "
            f"  git checkout -b {name} --track {tracking}; "
            "fi; "
        )
    return (
        "set -euo pipefail; "
        f"cd {root}; "
        f'test "$(pwd -P)" = {root}; '
        f'test "$(git rev-parse --show-toplevel)" = {root}; '
        f'test "$(git remote get-url origin)" = {url}; '
        f"git -c {ssh_config} fetch origin {name}; "
        f"if git show-ref --verify --quiet {local_ref}; then "
        f"  if ! git merge-base --is-ancestor {local_ref} {remote_ref}; then "
        '    echo "worker local branch is ahead of or diverged from origin" >&2; '
        "    exit 1; "
        "  fi; "
        "fi; "
        f"{selection}"
        f"git -c {ssh_config} pull --ff-only origin {name}; "
        f'test "$(git branch --show-current)" = {name}; '
        f'test "$(git rev-parse HEAD)" = "$(git rev-parse {remote_ref})"; '
        'test -z "$(git status --porcelain --untracked-files=normal)"'
    )


def _bootstrap_worker(
    transport: SshWslTransport, connection: WorkerConnectionSettings, setup: WorkerSetupSettings
) -> None:
    worker_root = connection.worker_project_root
    packages = " ".join(SYSTEM_PACKAGES)
    script = (
        "set -euo pipefail; "
        f"cd {shlex.quote(str(worker_root))}; "
        "test -f src/course_explorer_admin/provisioning_worker.py; "
        "sudo apt-get update; "
        f"sudo apt-get install -y --no-install-recommends {packages}; "
        "if ! command -v uv >/dev/null 2>&1; then "
        f"  curl --disable --fail --location --proto '=https' --tlsv1.2 {_UV_INSTALL_URL} "
        "| UV_NO_MODIFY_PATH=1 sh; "
        "fi; "
        'export PATH="$HOME/.local/bin:$PATH"; '
        "uv sync --locked"
    )
    transport.run(
        ("bash", "-c", script),
        cwd=PurePosixPath(str(worker_root)),
        env={"SELECTED_DATASET_ENABLED": "0"},
        timeout=setup.worker_setup_timeout_seconds,
    )


def _prepare_worker_resources(
    transport: SshWslTransport, connection: WorkerConnectionSettings, setup: WorkerSetupSettings
) -> None:
    transport.run(
        (
            "uv",
            "run",
            "--no-sync",
            "--offline",
            "--no-python-downloads",
            "python",
            "-m",
            "course_explorer_admin.provisioning_worker",
            "prepare",
        ),
        cwd=PurePosixPath(str(connection.worker_project_root)),
        env={"SELECTED_DATASET_ENABLED": "0"},
        timeout=setup.worker_setup_timeout_seconds,
    )


def _read_worker_resources(
    transport: SshWslTransport, connection: WorkerConnectionSettings
) -> WorkerResourcesReport:
    payload = transport.run(
        (
            "uv",
            "run",
            "--no-sync",
            "--offline",
            "--no-python-downloads",
            "python",
            "-m",
            "course_explorer_admin.provisioning_worker",
            "check",
        ),
        cwd=PurePosixPath(str(connection.worker_project_root)),
        env={"SELECTED_DATASET_ENABLED": "0"},
    )
    return WorkerResourcesReport.model_validate_json(payload.decode("utf-8"))


def _worker_dependencies_ready(
    transport: SshWslTransport, connection: WorkerConnectionSettings
) -> bool:
    try:
        transport.run(
            ("uv", "sync", "--locked", "--check", "--offline", "--no-python-downloads"),
            cwd=PurePosixPath(str(connection.worker_project_root)),
        )
    except subprocess.CalledProcessError:
        return False
    return True
