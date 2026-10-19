"""The fixed short rebuilds of this checkout and the queued restart of its administration unit.

This module owns the operator's rebuilds. ``rebuild_site`` builds the site frontend from the
checkout's installed dependencies, recreates the already-prepared database and embedding containers,
restarts the site's web unit, and proves the configured loopback listener belongs to the restarted
process. ``rebuild_admin`` builds the administration frontend alone, and ``restart_admin`` queues one
non-blocking restart of this checkout's own administration unit. Each is one bounded maintenance
command over prepared resources.

Every selected unit is validated through ``server.read_owned_site_unit`` before any mutation, so no
rebuild and no restart can reach another application's service. The steps
run in one fixed order, each bounded by the configured stop timeout, and the first failure stops the
command without a later step, a rollback, a retry or a success report. The administration restart
returns once the queue admits the request.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from course_explorer.administration import repository_root
from course_explorer.config import (
    load_administrative_site_settings,
    load_local_lifecycle_settings,
)
from course_explorer_admin import mechanics, server

# The exact ordered steps a completed rebuild names, as its transient acknowledgment.
REBUILD_STEPS: tuple[str, ...] = ("frontend", "containers", "web", "bind")

# The one step the administration build names: its own frontend.
ADMIN_REBUILD_STEPS: tuple[str, ...] = ("frontend",)

# The administration entry point this checkout's own administration unit runs, relative to the
# checkout root.
_ADMIN_ENTRY_POINT = "scripts/run_admin_web.sh"

# The two services a rebuild recreates, in order. The volumes and images stay in place.
REBUILD_SERVICES: tuple[str, ...] = ("db", "embedding")

_SOCKET_OWNER_PATTERN = re.compile(r"pid=([0-9]+)")


class RebuildReport(BaseModel):
    """One completed rebuild: its steps, and the configured web bind it verified."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    steps: tuple[str, ...]
    host: str
    port: int


class AdminRebuildReport(BaseModel):
    """One completed administration build: the ordered steps it ran.

    The report holds the steps. The build writes the administration frontend output, and a separate
    ``restart_admin`` invocation queues the restart.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    steps: tuple[str, ...]


class AdminRestartReport(BaseModel):
    """One acknowledged administration restart request.

    ``restart_queued`` is always true, because the report is returned only after the restart request
    is admitted.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    restart_queued: Literal[True] = True


def _loopback(address: str) -> bool:
    """Report whether one socket's local address is a loopback address."""
    host, _, _ = address.rpartition(":")
    return host == "127.0.0.1" or host.startswith("127.") or host == "[::1]"


def _read_web_listeners(
    runner: mechanics.ProcessRunner, *, root: Path, port: int, pid: int, timeout: float
) -> tuple[str, ...]:
    """Return the local addresses of the listeners proven to belong to the web process.

    Only the local address column is inspected, and only a listener whose process ownership names
    the web process is accepted. An ownership this viewer cannot read therefore never passes the
    check, and the bounded bind wait fails instead. A listener the web process owns on an address
    that is not a loopback address fails at once, because the site answers on a loopback address
    alone. Listeners of another process on the same port are not this web process and are left as
    they are.
    """
    output = runner.run(("ss", "-H", "-ltnp", f"sport = :{port}"), cwd=root, timeout=timeout).stdout
    owned: list[str] = []
    for line in output.decode("utf-8").splitlines():
        fields = line.split()
        if len(fields) < 6:
            continue
        owners = {int(match) for match in _SOCKET_OWNER_PATTERN.findall(" ".join(fields[5:]))}
        if pid not in owners:
            continue
        if not _loopback(fields[3]):
            raise ValueError("the web process must not listen on a non-loopback address")
        owned.append(fields[3])
    return tuple(owned)


def rebuild_site(*, runner: mechanics.ProcessRunner) -> RebuildReport:
    """Rebuild the frontend, the two containers, the web unit and its verified bind.

    Every step is checked. The frontend build runs from the checkout with its installed
    dependencies, the containers are recreated from their prepared images without a build or a
    download, and the restarted unit must answer on the configured loopback bind.
    """
    root = repository_root()
    website = server.read_web_service(runner=runner)
    settings = load_local_lifecycle_settings()
    timeout = settings.stop_timeout_seconds

    runner.run(("npm", "--prefix", "web", "run", "build"), cwd=root, timeout=timeout)
    runner.run(
        (
            *mechanics.compose_prefix(non_interactive=True),
            "up",
            "-d",
            "--wait",
            "--force-recreate",
            "--no-build",
            "--pull",
            "never",
            *REBUILD_SERVICES,
        ),
        cwd=root,
        timeout=timeout,
    )
    runner.run(("systemctl", "--user", "restart", website.unit), cwd=root, timeout=timeout)

    restarted = server.read_web_service(runner=runner)
    mechanics.await_state(
        lambda: _read_web_listeners(
            runner, root=root, port=restarted.port, pid=restarted.main_pid, timeout=timeout
        ),
        lambda owned: f"127.0.0.1:{restarted.port}" in owned,
        attempts=settings.startup_attempts,
        interval=settings.poll_interval_seconds,
        sleep=time.sleep,
    )
    return RebuildReport(steps=REBUILD_STEPS, host=restarted.host, port=restarted.port)


def rebuild_admin(*, runner: mechanics.ProcessRunner) -> AdminRebuildReport:
    """Build the administration frontend of this checkout after validating its own unit.

    The command runs the administration frontend build from the checkout's installed dependencies.
    A build failure propagates, and a separate ``restart_admin`` invocation queues the restart.
    """
    root = repository_root()
    unit = load_administrative_site_settings().admin_service_unit
    server.read_owned_site_unit(runner, unit, root=root, entry_point=_ADMIN_ENTRY_POINT)
    timeout = load_local_lifecycle_settings().stop_timeout_seconds

    runner.run(("npm", "--prefix", "admin-web", "run", "build"), cwd=root, timeout=timeout)
    return AdminRebuildReport(steps=ADMIN_REBUILD_STEPS)


def restart_admin(*, runner: mechanics.ProcessRunner) -> AdminRestartReport:
    """Queue one non-blocking restart of this checkout's own administration unit.

    The unit comes from the site settings and is validated as this checkout's administration unit
    before the request is admitted. The restart is queued rather than waited for, so the caller is
    not the process being replaced. The returned report acknowledges queue admission alone.
    """
    root = repository_root()
    unit = load_administrative_site_settings().admin_service_unit
    server.read_owned_site_unit(runner, unit, root=root, entry_point=_ADMIN_ENTRY_POINT)
    timeout = load_local_lifecycle_settings().stop_timeout_seconds

    runner.run(("systemctl", "--user", "--no-block", "restart", unit), cwd=root, timeout=timeout)
    return AdminRestartReport()
