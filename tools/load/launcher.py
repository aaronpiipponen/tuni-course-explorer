"""Start, inspect and stop one disposable serving stack for the load measurements.

Usage::

    python tools/load/launcher.py start --database DATABASE --admin-state-root PATH
        (--checkout PATH | --commit COMMIT) [options]
    python tools/load/launcher.py status --name NAME
    python tools/load/launcher.py stop --name NAME [--machine-config PATH] [--keep-checkout]

``start`` creates the copy, cgroups and supervisor and waits for readiness.
``stop`` stops the process tree and removes the cgroups and checkout it created.
``status`` prints one recorded stack's state.
``--database`` names the stack's database, which must end with ``_test``.
``--admin-state-root`` is the state root inside the disposable checkout.
``--checkout`` is a checkout to run, and ``--commit`` a commit to extract into a disposable
checkout.
``--machine-config`` is the machine configuration file.
``--name`` names the stack, defaulting to ``stack-<UTC timestamp>`` for a start.
``--port``, ``--workers`` and ``--memory-mib`` override the machine values.
``--no-instrument`` disables the cache event log.
``--keep-checkout`` keeps the disposable checkout after a stop.

The launcher creates a cgroup pair, composes the copy's own settings, starts the product's
supervisor from the copy with `PYTHONPATH` set to that copy, verifies that every supervisor
descendant is inside the enforcing cgroup, and tears down only the process tree it started. A copy
whose resolved repository data root is this checkout's live `data/`, or that is a Git work tree, is
refused.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import counters
from common import (
    DEFAULT_MACHINE_CONFIG,
    INSTRUMENT_DIRECTORY,
    ROOT,
    RUN_ROOT,
    load_json,
    utc_stamp,
    write_json,
)
from machine import MachineConfig, load_machine_config

PAGE_COUNTER_MAX = 9223372036854771712
READY_TIMEOUT_SECONDS = 240.0
STOP_TIMEOUT_SECONDS = 30.0

_CONFIGURATION_PROBE = """
import json
import sys
from pathlib import Path

from course_explorer import configuration
from course_explorer.configuration import environment_value

values = configuration.read_public_configuration(Path(sys.argv[1]))
Path(sys.argv[2]).write_text(
    json.dumps({alias: environment_value(value) for alias, value in values.items()}),
    encoding="utf-8",
)
"""

_ROOT_PROBE = """
from course_explorer.administration import repository_root

print(repository_root())
"""

_SELECTION_PROBE = """
from course_explorer import administration
from course_explorer.config import load_raw_database_settings
from course_explorer.datasets import read_dataset_role

settings = load_raw_database_settings()
root = administration.repository_root() / settings.admin_state_root
receipt = read_dataset_role(root, "selected")
print("enrolled" if receipt is not None else "bootstrap")
"""


def _tail(path: Path, lines: int = 30) -> str:
    """Return the last lines of one text log."""
    if not path.is_file():
        return ""
    content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(content[-lines:])


def _free_port(host: str, port: int) -> bool:
    """Return whether one TCP port can be bound on the given host."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, port))
        except OSError:
            return False
    return True


def _request(path: str, body: dict) -> tuple[int, bytes]:
    """Send one JSON request without following an error status."""
    request = urllib.request.Request(
        path,
        data=json.dumps(body).encode("utf-8"),
        headers={"content-type": "application/json", "accept-encoding": "identity"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


class Stack:
    """One disposable serving supervisor, its cgroup pair and its recorded facts."""

    def __init__(
        self,
        *,
        machine: MachineConfig,
        name: str | None = None,
        checkout: Path | None = None,
        commit: str | None = None,
        database: str,
        admin_state_root: str,
        port: int | None = None,
        workers: int | None = None,
        memory_mib: int | None = None,
        instrument: bool = True,
        keep_checkout: bool = False,
    ) -> None:
        if (checkout is None) == (commit is None):
            raise ValueError("give exactly one of a checkout path or a commit")
        self.name = name or f"stack-{utc_stamp()}"
        if not self.name.replace("-", "").replace("_", "").isalnum():
            raise ValueError("the stack name must hold letters, digits, '-' or '_'")
        self.machine = machine
        self.checkout = Path(checkout).resolve() if checkout is not None else None
        self.commit = commit
        self.database = database
        if not self.database.endswith("_test"):
            raise ValueError("the stack database name must end with _test")
        self.admin_state_root = admin_state_root
        admin_path = Path(self.admin_state_root)
        if admin_path.is_absolute() or ".." in admin_path.parts:
            raise ValueError("the admin state root must stay inside the disposable checkout")
        self.port = port or machine.stack.web_port
        self.workers = workers or machine.stack.web_workers
        self.memory_mib = memory_mib or machine.stack.web_memory_mib
        self.instrument = instrument
        self.keep_checkout = keep_checkout
        self.run_dir = RUN_ROOT / "stacks" / self.name
        self.state_path = self.run_dir / "stack.json"
        self.log_path = self.run_dir / "supervisor.log"
        self.cache_events = self.run_dir / "cache-events.jsonl"
        self.cpu_cgroup: Path | None = None
        self.memory_cgroup: Path | None = None
        self.created_cgroups: list[Path] = []
        self.process: subprocess.Popen | None = None
        self.state: dict = {}
        self._closed = False

    def start(self) -> dict:
        """Create the copy, cgroups and supervisor, and wait for readiness."""
        if self.state_path.exists():
            raise RuntimeError(f"a recorded stack already uses the name {self.name}")
        if self.run_dir.exists():
            raise RuntimeError(f"the stack run directory has no recorded state: {self.run_dir}")
        self.run_dir.mkdir(parents=True)
        if self.checkout is None:
            self.checkout = self._checkout_from_commit()
        self.state = {
            "name": self.name,
            "commit": self.commit,
            "checkout": str(self.checkout),
            "checkout_created": self.commit is not None,
            "database": self.database,
            "database_container": self.machine.stack.database_container,
            "embedding_container": self.machine.stack.embedding_container,
            "admin_state_root": self.admin_state_root,
            "port": self.port,
            "workers": self.workers,
            "memory_mib": self.memory_mib,
            "instrument": self.instrument,
            "started_at": time.time(),
        }
        try:
            self._create_cgroups()
            environment = self.environment()
            self._start_process(environment)
            self._wait_ready()
            self._verify_membership()
        except BaseException:
            self.stop()
            raise
        memory = counters.memory_state(self.memory_cgroup)
        self.state.update(
            {
                "pid": self.process.pid,
                "url": f"http://{self.machine.stack.web_host}:{self.port}",
                "cpu_cgroup": str(self.cpu_cgroup),
                "memory_cgroup": str(self.memory_cgroup),
                "cgroup_membership": counters.process_cgroup(self.process.pid, "memory"),
                "member_pids": counters.descendants(self.process.pid),
                "cgroup_members": counters.cgroup_members(self.memory_cgroup),
                "created_cgroups": [str(path) for path in self.created_cgroups],
                "memory_limit_bytes": memory["limit_bytes"],
                "memory_memsw_limit_bytes": memory["memsw_limit_bytes"],
                "parent_memory_limit_bytes": int(
                    (self.machine.stack.memory_cgroup_root / "memory.limit_in_bytes").read_text(
                        encoding="utf-8"
                    )
                ),
                "usage_path": str(self.checkout / "data" / "usage" / "requests"),
                "usage_lines_before": counters.usage_lines(
                    self.checkout / "data" / "usage" / "requests"
                ),
                "host_cpu_start": counters.host_cpu(),
                "host_load_start": counters.host_load(),
                "supervisor_log": str(self.log_path),
                "cache_events": str(self.cache_events) if self.instrument else None,
            }
        )
        write_json(self.state_path, self.state)
        return self.state

    def environment(self) -> dict[str, str]:
        """Compose the copy's settings plus the explicit disposable overrides."""
        assert self.checkout is not None
        checkout = self.checkout
        live_data = (ROOT / "data").resolve()
        target_data = (checkout / "data").resolve()
        state_data = (checkout / self.admin_state_root).resolve()
        if checkout == ROOT.resolve():
            raise RuntimeError("the live checkout is not a disposable measurement copy")
        if (checkout / ".git").exists():
            raise RuntimeError(
                "the checkout is a Git work tree, so a disposable copy comes from git archive or "
                "rsync without .git"
            )
        if target_data == live_data:
            raise RuntimeError("the stack data root resolves to this checkout's live data/")
        if checkout not in state_data.parents:
            raise RuntimeError("the admin state root resolves outside the disposable checkout")
        probe_environment = {
            "HOME": os.environ.get("HOME", ""),
            "PATH": os.environ.get("PATH", ""),
            "LANG": os.environ.get("LANG", ""),
            "PYTHONPATH": str(checkout / "src"),
        }
        selection_process = subprocess.run(
            [sys.executable, "-c", _SELECTION_PROBE],
            cwd=checkout,
            env=probe_environment,
            check=False,
            capture_output=True,
            text=True,
        )
        if selection_process.returncode != 0:
            raise RuntimeError(
                "the copy's dataset state could not be read:\n" + selection_process.stderr.strip()
            )
        if selection_process.stdout.strip() != "bootstrap":
            raise RuntimeError(
                "the supplied measurement state root is enrolled; the load measurement launches an "
                "explicit raw database and requires a bootstrap state root"
            )
        configuration_path = self.run_dir / "configuration.json"
        process = subprocess.run(
            [
                sys.executable,
                "-c",
                _CONFIGURATION_PROBE,
                str(checkout),
                str(configuration_path),
            ],
            cwd=checkout,
            env=probe_environment,
            check=False,
            capture_output=True,
            text=True,
        )
        if process.returncode != 0:
            raise RuntimeError(
                "the copy's configuration could not be composed:\n" + process.stderr.strip()
            )
        values = load_json(configuration_path)
        if not isinstance(values, dict):
            raise RuntimeError("the copy's configuration probe returned no mapping")
        root_process = subprocess.run(
            [sys.executable, "-c", _ROOT_PROBE],
            cwd=checkout,
            env=probe_environment,
            check=False,
            capture_output=True,
            text=True,
        )
        if root_process.returncode != 0:
            raise RuntimeError("the copy's package did not import:\n" + root_process.stderr.strip())
        resolved_root = Path(root_process.stdout.strip()).resolve()
        if resolved_root != checkout:
            raise RuntimeError(
                f"the copy's repository root is {resolved_root}, not its own checkout {checkout}"
            )
        environment = {
            "HOME": os.environ.get("HOME", ""),
            "PATH": os.environ.get("PATH", ""),
            "LANG": os.environ.get("LANG", ""),
            "PYTHONPATH": f"{INSTRUMENT_DIRECTORY}:{checkout / 'src'}",
            "PYTHONDONTWRITEBYTECODE": "1",
            "TCE_LOAD_CHECKOUT": str(checkout),
            "TCE_LOAD_CPU_CGROUP": str(self.cpu_cgroup),
            "TCE_LOAD_MEMORY_CGROUP": str(self.memory_cgroup),
        }
        for key, value in values.items():
            if isinstance(key, str) and isinstance(value, str):
                environment.setdefault(key, value)
        # glibc reads the arena cap at process start, and the router and forked workers inherit it.
        # A revision whose configuration defines no arena cap starts without it, as its own launcher
        # does.
        if "WEB_MALLOC_ARENA_MAX" in values:
            environment["MALLOC_ARENA_MAX"] = str(values["WEB_MALLOC_ARENA_MAX"])
        environment.update(
            {
                "COURSE_EXPLORER_SETTINGS_SOURCE": "environment",
                "POSTGRES_HOST": self.machine.stack.database_host,
                "POSTGRES_PORT": str(self.machine.stack.database_port),
                "POSTGRES_USER": self.machine.stack.database_user,
                "POSTGRES_PASSWORD": self.machine.stack.database_password,
                "POSTGRES_DB": self.database,
                "ADMIN_STATE_ROOT": self.admin_state_root,
                "EMBEDDING_HOST": self.machine.stack.embedding_host,
                "EMBEDDING_PORT": str(self.machine.stack.embedding_port),
                "WEB_HOST": self.machine.stack.web_host,
                "WEB_PORT": str(self.port),
                "WEB_WORKERS": str(self.workers),
            }
        )
        if self.instrument:
            environment["TCE_LOAD_CACHE_EVENTS"] = str(self.cache_events)
        return environment

    def _checkout_from_commit(self) -> Path:
        """Extract one commit into a fresh disposable checkout."""
        assert self.commit is not None
        destination = RUN_ROOT / "checkouts" / f"{self.commit[:12]}-{self.name}"
        if destination.exists():
            raise RuntimeError(f"the disposable checkout already exists: {destination}")
        destination.mkdir(parents=True)
        archive = self.run_dir / "checkout.tar"
        try:
            process = subprocess.run(
                ["git", "archive", "--format=tar", self.commit],
                cwd=ROOT,
                check=False,
                capture_output=True,
            )
            if process.returncode != 0:
                raise RuntimeError(
                    f"git archive {self.commit} failed:\n" + process.stderr.decode(errors="replace")
                )
            archive.write_bytes(process.stdout)
            with tarfile.open(archive) as bundle:
                bundle.extractall(destination, filter="data")
        except BaseException:
            shutil.rmtree(destination, ignore_errors=True)
            raise
        finally:
            archive.unlink(missing_ok=True)
        return destination.resolve()

    def _create_cgroups(self) -> None:
        """Create and limit the run cgroup pair before the supervisor starts."""
        for root in (self.machine.stack.cpu_cgroup_root, self.machine.stack.memory_cgroup_root):
            if not root.is_dir():
                raise RuntimeError(f"the cgroup parent is missing: {root}")
            if not os.access(root, os.W_OK):
                raise RuntimeError(f"the cgroup parent is not writable: {root}")
        self.cpu_cgroup = self.machine.stack.cpu_cgroup_root / self.name
        self.memory_cgroup = self.machine.stack.memory_cgroup_root / self.name
        cap = self.memory_mib * 1024 * 1024
        parent = self.machine.stack.memory_cgroup_root
        parent_limit = parent / "memory.limit_in_bytes"
        parent_memsw = parent / "memory.memsw.limit_in_bytes"
        if int(parent_limit.read_text(encoding="utf-8")) < cap:
            # A child's limit cannot enforce a bound above its parent's, so raise the shared
            # measurement parent to the requested cap. A higher parent limit is never lowered.
            if parent_memsw.exists():
                parent_memsw.write_text(str(PAGE_COUNTER_MAX), encoding="utf-8")
            parent_limit.write_text(str(cap), encoding="utf-8")
            if parent_memsw.exists():
                parent_memsw.write_text(str(cap), encoding="utf-8")
        for path in (self.cpu_cgroup, self.memory_cgroup):
            if path.exists():
                raise RuntimeError(f"the cgroup already exists: {path}")
            path.mkdir()
            self.created_cgroups.append(path)
        memsw = self.memory_cgroup / "memory.memsw.limit_in_bytes"
        if memsw.exists():
            memsw.write_text(str(PAGE_COUNTER_MAX), encoding="utf-8")
        (self.memory_cgroup / "memory.limit_in_bytes").write_text(str(cap), encoding="utf-8")
        if memsw.exists():
            memsw.write_text(str(cap), encoding="utf-8")

    def _start_process(self, environment: dict[str, str]) -> None:
        """Start the bootstrap that enters both cgroups before the supervisor runs."""
        if not _free_port(self.machine.stack.web_host, self.port):
            raise RuntimeError(f"port {self.port} is already bound")
        self.cache_events.write_text("", encoding="utf-8")
        log = self.log_path.open("wb")
        self.process = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve().parent / "_bootstrap.py")],
            cwd=self.checkout,
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=log,
            start_new_session=True,
        )
        log.close()
        try:
            counters.wait_for_cgroup(self.process.pid, self.cpu_cgroup)
            counters.wait_for_cgroup(self.process.pid, self.memory_cgroup)
        except BaseException:
            self.stop()
            raise

    def _wait_ready(self) -> None:
        """Wait for the features route, and fail with the supervisor log when it exits."""
        assert self.process is not None
        url = f"http://{self.machine.stack.web_host}:{self.port}/api/features"
        deadline = time.monotonic() + READY_TIMEOUT_SECONDS
        last = "no response"
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(
                    f"the supervisor exited with {self.process.returncode}:\n"
                    + _tail(self.log_path)
                )
            try:
                status, body = _request(url, {})
            except (OSError, urllib.error.URLError) as error:
                last = str(error)
                time.sleep(0.5)
                continue
            if status == 200:
                return
            last = f"status {status}: {body[:300]!r}"
            time.sleep(0.5)
        raise RuntimeError(f"the supervisor did not become ready: {last}\n" + _tail(self.log_path))

    def _verify_membership(self) -> None:
        """Fail when a supervisor descendant is outside either enforcing cgroup."""
        assert self.process is not None
        expected = {
            controller: counters.process_cgroup(self.process.pid, controller)
            for controller in ("cpuacct", "memory")
        }
        escaped = [
            pid
            for pid in counters.descendants(self.process.pid)
            if any(
                counters.process_cgroup(pid, controller) != path
                for controller, path in expected.items()
            )
        ]
        if escaped:
            raise RuntimeError(f"supervisor descendants escaped the enforcing cgroup: {escaped}")

    def stop(self) -> dict:
        """Stop the supervisor tree and remove only the cgroups and copy it created."""
        if self._closed:
            return self.state
        process = self.process
        if process is not None and process.poll() is None:
            expected = counters.process_cgroup(process.pid, "memory")
            recorded = self.state.get("cgroup_membership")
            if recorded is not None and expected != recorded:
                raise RuntimeError(
                    f"supervisor {process.pid} left its recorded cgroup {recorded}: {expected}"
                )
            process.terminate()
            try:
                process.wait(timeout=STOP_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=STOP_TIMEOUT_SECONDS)
        elif process is None and self.state.get("pid"):
            self._stop_recorded_process(int(self.state["pid"]))
        for path in self.created_cgroups:
            if not path.is_dir():
                continue
            deadline = time.monotonic() + STOP_TIMEOUT_SECONDS
            while counters.cgroup_members(path) and time.monotonic() < deadline:
                time.sleep(0.1)
            members = counters.cgroup_members(path)
            if members:
                raise RuntimeError(f"the supervisor cgroup still holds {members}")
            path.rmdir()
        self.state.update(
            {
                "stopped_at": time.time(),
                "exit_code": None if process is None else process.returncode,
                "host_cpu_end": counters.host_cpu(),
                "host_load_end": counters.host_load(),
            }
        )
        if self.checkout is not None:
            usage_path = self.checkout / "data" / "usage" / "requests"
            self.state["usage_lines_after"] = counters.usage_lines(usage_path)
        if self.state_path.exists():
            write_json(self.state_path, self.state)
        if self.state.get("checkout_created") and not self.keep_checkout:
            checkout = Path(self.state["checkout"])
            checkouts_root = (RUN_ROOT / "checkouts").resolve()
            if checkouts_root in checkout.resolve().parents:
                shutil.rmtree(checkout, ignore_errors=True)
        self._closed = True
        return self.state

    def _stop_recorded_process(self, pid: int) -> None:
        """Stop one started supervisor after verifying its command line and cgroup."""
        command = Path(f"/proc/{pid}/cmdline")
        if not command.is_file():
            return
        arguments = command.read_bytes().split(b"\0")
        if not any(argument.endswith(b"_bootstrap.py") for argument in arguments):
            raise RuntimeError(f"process {pid} is not a started stack bootstrap")
        recorded = self.state.get("cgroup_membership")
        if recorded is not None and counters.process_cgroup(pid, "memory") != recorded:
            raise RuntimeError(f"process {pid} left its recorded cgroup")
        os.kill(pid, 15)
        deadline = time.monotonic() + STOP_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if not Path(f"/proc/{pid}").exists():
                return
            time.sleep(0.1)
        raise RuntimeError(f"the supervisor {pid} did not stop")


def main(argv: list[str] | None = None) -> int:
    """Run the stack start, stop or status command."""
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    start = subcommands.add_parser("start", help="start one disposable stack")
    start.add_argument("--machine-config", type=Path, default=DEFAULT_MACHINE_CONFIG)
    start.add_argument("--checkout", type=Path)
    start.add_argument("--commit")
    start.add_argument("--name")
    start.add_argument("--database", required=True)
    start.add_argument("--admin-state-root", required=True)
    start.add_argument("--port", type=int)
    start.add_argument("--workers", type=int)
    start.add_argument("--memory-mib", type=int)
    start.add_argument("--no-instrument", action="store_true")
    start.add_argument("--keep-checkout", action="store_true")
    stop = subcommands.add_parser("stop", help="stop one recorded stack")
    stop.add_argument("--name", required=True)
    stop.add_argument("--machine-config", type=Path, default=DEFAULT_MACHINE_CONFIG)
    stop.add_argument("--keep-checkout", action="store_true")
    status = subcommands.add_parser("status", help="print one recorded stack state")
    status.add_argument("--name", required=True)
    arguments = parser.parse_args(argv)
    if arguments.command == "start":
        machine = load_machine_config(arguments.machine_config)
        stack = Stack(
            machine=machine,
            name=arguments.name,
            checkout=arguments.checkout,
            commit=arguments.commit,
            database=arguments.database,
            admin_state_root=arguments.admin_state_root,
            port=arguments.port,
            workers=arguments.workers,
            memory_mib=arguments.memory_mib,
            instrument=not arguments.no_instrument,
            keep_checkout=arguments.keep_checkout,
        )
        print(json.dumps(stack.start(), indent=2, sort_keys=True))
        return 0
    state_path = RUN_ROOT / "stacks" / arguments.name / "stack.json"
    if arguments.command == "status":
        if not state_path.is_file():
            raise RuntimeError(f"no recorded stack is named {arguments.name}")
        print(json.dumps(load_json(state_path), indent=2, sort_keys=True))
        return 0
    if not state_path.is_file():
        raise RuntimeError(f"no recorded stack is named {arguments.name}")
    recorded = load_json(state_path)
    stack = Stack(
        machine=load_machine_config(arguments.machine_config),
        name=arguments.name,
        checkout=Path(recorded["checkout"]),
        database=recorded["database"],
        admin_state_root=recorded["admin_state_root"],
        port=recorded["port"],
        workers=recorded["workers"],
        memory_mib=recorded["memory_mib"],
        instrument=bool(recorded.get("instrument")),
        keep_checkout=bool(arguments.keep_checkout),
    )
    stack.state = recorded
    stack.cpu_cgroup = Path(recorded["cpu_cgroup"])
    stack.memory_cgroup = Path(recorded["memory_cgroup"])
    stack.created_cgroups = [Path(path) for path in recorded.get("created_cgroups", [])]
    print(json.dumps(stack.stop(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
