"""Cgroup CPU, memory and whole-host counters for one disposable serving stack.

The web supervisor and its children are placed in one cgroup pair and measured through
`cpuacct.usage` and the memory controller files. The disposable database and embedding provider are
containers with their own cgroups. Every counter read raises when the expected file is absent, so a
missing counter never becomes a zero.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

CGROUP_ROOT = Path("/sys/fs/cgroup")


def container_cgroup(container: str, controller: str) -> Path:
    """Return the host cgroup v1 directory of one container's controller."""
    pid = subprocess.run(
        ["sudo", "-n", "docker", "inspect", "--format", "{{.State.Pid}}", container],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    for line in Path(f"/proc/{pid}/cgroup").read_text(encoding="utf-8").splitlines():
        _hierarchy, controllers, relative = line.split(":", 2)
        if controller in controllers.split(","):
            candidate = CGROUP_ROOT / controller / relative.lstrip("/")
            if candidate.is_dir():
                return candidate
    raise RuntimeError(f"the {controller} cgroup of container {container} was not found")


def cpu_seconds(path: Path) -> float:
    """Return one cgroup's cumulative CPU seconds from the v1 or v2 counter."""
    usage = path / "cpuacct.usage"
    if usage.is_file():
        return int(usage.read_text(encoding="utf-8")) / 1e9
    statistics = path / "cpu.stat"
    if statistics.is_file():
        rows = dict(row.split() for row in statistics.read_text(encoding="utf-8").splitlines())
        return int(rows["usage_usec"]) / 1e6
    raise RuntimeError(f"the cgroup CPU counter is missing under {path}")


def memory_state(path: Path) -> dict[str, int | str]:
    """Return current, peak, limit, swap and failure facts of one memory cgroup."""
    oom = dict(
        row.split()
        for row in (path / "memory.oom_control").read_text(encoding="utf-8").splitlines()
    )
    current = int((path / "memory.usage_in_bytes").read_text(encoding="utf-8"))
    result: dict[str, int | str] = {
        "current_bytes": current,
        "peak_bytes": int((path / "memory.max_usage_in_bytes").read_text(encoding="utf-8")),
        "limit_bytes": int((path / "memory.limit_in_bytes").read_text(encoding="utf-8")),
        "failcnt": int((path / "memory.failcnt").read_text(encoding="utf-8")),
        "oom_kill": int(oom["oom_kill"]),
    }
    memsw_usage = path / "memory.memsw.usage_in_bytes"
    if memsw_usage.is_file():
        memsw_current = int(memsw_usage.read_text(encoding="utf-8"))
        result["memsw_current_bytes"] = memsw_current
        result["memsw_limit_bytes"] = int(
            (path / "memory.memsw.limit_in_bytes").read_text(encoding="utf-8")
        )
        result["swap_current_bytes"] = max(0, memsw_current - current)
    else:
        result["memsw_current_bytes"] = "unavailable"
        result["memsw_limit_bytes"] = "unavailable"
        result["swap_current_bytes"] = "unavailable"
    return result


def memory_stat(path: Path) -> dict[str, int]:
    """Return one memory cgroup's byte counters from `memory.stat`."""
    statistics = path / "memory.stat"
    if not statistics.is_file():
        raise RuntimeError(f"the memory.stat counter is missing under {path}")
    return {
        key: int(value)
        for key, value in (
            line.split() for line in statistics.read_text(encoding="utf-8").splitlines()
        )
    }


def process_memory(pid: int) -> dict[str, int | str]:
    """Return one process's name and resident set size.

    A process that exits between the cgroup member read and this read is recorded by pid alone.
    """
    status = Path(f"/proc/{pid}/status")
    if not status.is_file():
        return {"pid": pid}
    name = ""
    rss_kib = 0
    for line in status.read_text(encoding="utf-8").splitlines():
        if line.startswith("Name:"):
            name = line.split(":", 1)[1].strip()
        elif line.startswith("VmRSS:"):
            rss_kib = int(line.split()[1])
    return {"pid": pid, "name": name, "rss_bytes": rss_kib * 1024}


def memory_detail(path: Path) -> dict:
    """Return one cgroup's memory.stat counters and the resident size of each process."""
    return {
        "stat": memory_stat(path),
        "processes": [process_memory(pid) for pid in cgroup_members(path)],
    }


def host_cpu() -> dict[str, float]:
    """Return whole-host busy and idle CPU seconds from `/proc/stat`."""
    fields = Path("/proc/stat").read_text(encoding="utf-8").splitlines()[0].split()[1:]
    values = [int(value) for value in fields]
    idle = values[3] + values[4]
    busy = sum(values) - idle
    ticks = os.sysconf("SC_CLK_TCK")
    return {"busy_seconds": busy / ticks, "idle_seconds": idle / ticks}


def host_load() -> tuple[float, float, float]:
    """Return the one, five and 15 minute host load averages."""
    return os.getloadavg()


def usage_lines(path: Path) -> int:
    """Return the number of lines in one usage record file, or zero when it is absent."""
    if not path.is_file():
        return 0
    with path.open("rb") as stream:
        return sum(1 for _line in stream)


def cgroup_members(path: Path) -> list[int]:
    """Return the process identifiers in one cgroup."""
    return [int(value) for value in (path / "cgroup.procs").read_text(encoding="utf-8").split()]


def process_cgroup(pid: int, controller: str) -> str:
    """Return one process's cgroup path on one controller, relative to its mount."""
    for line in Path(f"/proc/{pid}/cgroup").read_text(encoding="utf-8").splitlines():
        _hierarchy, controllers, relative = line.split(":", 2)
        if controller in controllers.split(","):
            return relative
    return ""


def descendants(pid: int) -> list[int]:
    """Return every descendant of one process from `/proc` children files."""
    found: list[int] = []
    visited: set[int] = {pid}
    pending = [pid]
    while pending:
        current = pending.pop()
        task_directory = Path(f"/proc/{current}/task")
        if not task_directory.is_dir():
            continue
        for task in task_directory.iterdir():
            children = task / "children"
            if not children.is_file():
                continue
            for value in children.read_text(encoding="utf-8").split():
                child = int(value)
                if child in visited:
                    continue
                visited.add(child)
                found.append(child)
                pending.append(child)
    return found


def wait_for_cgroup(pid: int, path: Path, timeout: float = 10.0) -> None:
    """Wait until one process appears in one cgroup, and raise after the timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if str(pid) in (path / "cgroup.procs").read_text(encoding="utf-8").split():
            return
        time.sleep(0.02)
    raise RuntimeError(f"process {pid} did not enter cgroup {path}")
