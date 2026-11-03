"""Build the k6 run bundle, sample the stack counters and summarize one capacity level.

Usage::

    python tools/load/k6.py bundle --database DATABASE [--name NAME]
        [--machine-config PATH] [--workload PATH]
    python tools/load/k6.py counters --name NAME [--output PATH] [--interval SECONDS]
        [--seconds SECONDS] [--machine-config PATH]
    python tools/load/k6.py summarize --k6-summary PATH --k6-raw PATH --counters PATH
        --cache-events PATH --profile {light_only,mixed} --users COUNT [--settle-seconds SECONDS]
        [--workload PATH] [--output PATH]
    python tools/load/k6.py saturation --results PATH [PATH ...] [--rise FRACTION]
        [--workload PATH] [--output PATH]

``bundle`` writes one k6 bundle and its run command under ``data/load/bundles``.
``counters`` samples one recorded stack until a signal or ``--seconds``.
``summarize`` pairs one level's k6 output with its counters and the cache event log.
``saturation`` applies the light-throughput stop rule over one profile's level results.
``--database`` names the database the bundle's payload context reads.
``--name`` names the bundle, defaulting to ``bundle-<UTC timestamp>``, or the recorded stack.
``--machine-config`` is the machine configuration file.
``--workload`` is the workload file.
``--k6-summary`` is k6's JSON summary export and ``--k6-raw`` its JSON point export.
``--counters`` is a counters record and ``--cache-events`` the stack's cache event log.
``--profile`` selects the capacity profile, ``light_only`` or ``mixed``.
``--users`` is the level's simulated user count.
``--settle-seconds`` overrides the workload's settle window for this level.
``--results`` lists the level results the saturation view reads.
``--rise`` overrides the workload's saturation rise fraction.
``--interval`` is the counter sample interval in seconds and ``--seconds`` an optional stop time.
``--output`` is the result path of ``counters``, ``summarize`` or ``saturation``, defaulting to a
file under ``data/load/results``.

The bundle holds the two stateful profile scripts, the versioned workload and the payload context
resolved from the measurement dataset. The counters command records the web, database and embedding
cgroups while the operator runs one level on the configured load client. The summarize command pairs
one level's k6 output with those counters and the cache event log and writes the recorded result. The
saturation command applies the light-throughput stop rule over a profile's level results.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import signal
import time
from datetime import datetime
from pathlib import Path

import context
import counters
from common import (
    DEFAULT_MACHINE_CONFIG,
    DEFAULT_WORKLOAD,
    HERE,
    RUN_ROOT,
    load_json,
    load_workload,
    utc_stamp,
    write_json,
)
from machine import MachineConfig, load_machine_config

from course_explorer.config import load_normalization_settings

_K6_SOURCE = HERE / "k6"


def _database_environment(machine: MachineConfig, database: str) -> dict[str, str]:
    """Return the connection values and configured academic year for one measurement database."""
    normalization = load_normalization_settings()
    return {
        "POSTGRES_HOST": machine.stack.database_host,
        "POSTGRES_PORT": str(machine.stack.database_port),
        "POSTGRES_USER": machine.stack.database_user,
        "POSTGRES_PASSWORD": machine.stack.database_password,
        "POSTGRES_DB": database,
        "CURRENT_ACADEMIC_YEAR": normalization.current_academic_year,
    }


def _windows_join(directory: str, name: str) -> str:
    """Join one remote directory and bundle name with forward separators.

    The copy and run commands hand the result to Windows OpenSSH and `cmd.exe`, and both accept the
    forward form of a drive path.
    """
    return directory.replace("\\", "/").rstrip("/") + "/" + name


def build_bundle(
    *,
    machine: MachineConfig,
    workload: dict,
    workload_path: Path,
    name: str,
    database: str,
) -> Path:
    """Write one self-contained k6 bundle and its run command."""
    bundle = RUN_ROOT / "bundles" / name
    if bundle.exists():
        raise RuntimeError(f"the bundle already exists: {bundle}")
    bundle.mkdir(parents=True)
    try:
        payload = context.build_context(_database_environment(machine, database), workload)
    except BaseException:
        shutil.rmtree(bundle, ignore_errors=True)
        raise
    write_json(bundle / "payload-context.json", payload)
    shutil.copyfile(workload_path, bundle / "workload.json")
    for source in ("lib.js", "warmup.js", "light.js", "mixed.js"):
        shutil.copyfile(_K6_SOURCE / source, bundle / source)
    remote = _windows_join(machine.worker.directory, name)
    target = machine.worker.target_base_url
    k6 = f'"{machine.worker.k6}"'
    worker_ssh = f"ssh {machine.worker.user}@{machine.worker.host}"
    capacity = workload["capacity"]
    levels = [int(level) for level in capacity["levels"]]
    commands = [
        f"scp -r '{bundle}' '{machine.worker.user}@{machine.worker.host}:{remote}'",
        (
            "# On the load client, open one SSH local forward to the stack's loopback port"
            " and keep it open for every level of one stack and profile run."
        ),
        (
            f"ssh -N -p {machine.worker.tunnel_port} "
            f"-L {machine.worker.forward_port}:127.0.0.1:{machine.stack.web_port} "
            f"{machine.worker.tunnel_user}@{machine.worker.tunnel_host}"
        ),
    ]
    scripts = {"light_only": "light.js", "mixed": "mixed.js"}
    for profile in capacity["profiles"]:
        script = scripts[profile]
        commands.append(f"# Fresh stack for the {profile} profile, then one fixed warm-up.")
        commands.append(
            f'{worker_ssh} \'cd "{remote}" && {k6} run --quiet --no-color --no-usage-report '
            f"-e BASE_URL={target} warmup.js'"
        )
        for level in levels:
            commands.append(
                f"# {profile} level {level}. Start the server counter sampler for this level first."
            )
            commands.append(
                f'{worker_ssh} \'cd "{remote}" && {k6} run --quiet --no-color --no-usage-report '
                f"--out json=raw-{profile}-{level}.json "
                f"-e BASE_URL={target} -e LEVEL={level} {script}'"
            )
    commands.append(
        "# Copy each level's summary and raw files back to the bundle before summarizing it."
    )
    (bundle / "run-command.txt").write_text("\n".join(commands) + "\n", encoding="utf-8")
    write_json(
        bundle / "bundle.json",
        {
            "name": name,
            "workload_version": workload["version"],
            "seed": workload.get("seed"),
            "dataset": payload["dataset"],
            "capacity": {
                "levels": levels,
                "level_seconds": capacity["level_seconds"],
                "settle_seconds": capacity["settle_seconds"],
                "profiles": capacity["profiles"],
            },
            "worker": {
                "host": machine.worker.host,
                "user": machine.worker.user,
                "directory": machine.worker.directory,
                "k6": machine.worker.k6,
                "tunnel_host": machine.worker.tunnel_host,
                "tunnel_user": machine.worker.tunnel_user,
                "tunnel_port": machine.worker.tunnel_port,
                "forward_port": machine.worker.forward_port,
                "target_base_url": target,
            },
        },
    )
    return bundle


def sample_counters(
    *,
    machine_config: Path,
    name: str,
    output: Path,
    interval: float,
    seconds: float | None,
) -> dict:
    """Sample one recorded stack's counters until stopped, then write the result."""
    state_path = RUN_ROOT / "stacks" / name / "stack.json"
    if not state_path.is_file():
        raise RuntimeError(f"no recorded stack is named {name}")
    state = load_json(state_path)
    web_cpu = Path(state["cpu_cgroup"])
    web_memory = Path(state["memory_cgroup"])
    machine = load_machine_config(machine_config)
    database_container = state.get("database_container", machine.stack.database_container)
    embedding_container = state.get("embedding_container", machine.stack.embedding_container)
    db_cpu = counters.container_cgroup(database_container, "cpuacct")
    db_memory = counters.container_cgroup(database_container, "memory")
    embedding_cpu = counters.container_cgroup(embedding_container, "cpuacct")
    embedding_memory = counters.container_cgroup(embedding_container, "memory")
    stopping = {"value": False}

    def request_stop(_signum, _frame) -> None:
        stopping["value"] = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    started = time.time()
    host_start = counters.host_cpu()
    memory_start = {
        "web": counters.memory_state(web_memory),
        "db": counters.memory_state(db_memory),
        "embedding": counters.memory_state(embedding_memory),
        "web_detail": counters.memory_detail(web_memory),
    }
    usage_path = Path(state["usage_path"])
    usage_start = counters.usage_lines(usage_path)
    samples = []
    detail_interval = 5.0
    last_detail = 0.0
    deadline = None if seconds is None else time.monotonic() + seconds
    while not stopping["value"]:
        if deadline is not None and time.monotonic() >= deadline:
            break
        now = time.time()
        sample = {
            "at": now,
            "web_core_s": counters.cpu_seconds(web_cpu),
            "db_core_s": counters.cpu_seconds(db_cpu),
            "embedding_core_s": counters.cpu_seconds(embedding_cpu),
            "web_current_bytes": int(
                (web_memory / "memory.usage_in_bytes").read_text(encoding="utf-8")
            ),
        }
        if now - last_detail >= detail_interval:
            sample["web_detail"] = counters.memory_detail(web_memory)
            last_detail = now
        samples.append(sample)
        time.sleep(interval)
    finished = time.time()
    host_end = counters.host_cpu()
    memory_end = {
        "web": counters.memory_state(web_memory),
        "db": counters.memory_state(db_memory),
        "embedding": counters.memory_state(embedding_memory),
        "web_detail": counters.memory_detail(web_memory),
    }
    result = {
        "schema": 1,
        "stack": state,
        "started_at": started,
        "finished_at": finished,
        "interval_seconds": interval,
        "samples": samples,
        "memory": {"start": memory_start, "end": memory_end},
        "host": {
            "busy_core_s_start": host_start["busy_seconds"],
            "busy_core_s_end": host_end["busy_seconds"],
        },
        "usage": {
            "path": str(usage_path),
            "lines_before": usage_start,
            "lines_after": counters.usage_lines(usage_path),
        },
    }
    write_json(output, result)
    return result


def _percentile(values: list[float], fraction: float) -> float:
    """Return the nearest-rank percentile of a non-empty list."""
    ordered = sorted(values)
    index = max(0, math.ceil(fraction * len(ordered)) - 1)
    return ordered[index]


def _latency(values: list[float]) -> dict:
    """Return the count, median and tail percentiles of one latency list."""
    if not values:
        return {"count": 0, "p50": None, "p95": None, "p99": None, "max": None}
    return {
        "count": len(values),
        "p50": _percentile(values, 0.50),
        "p95": _percentile(values, 0.95),
        "p99": _percentile(values, 0.99),
        "max": max(values),
    }


def _read_raw(path: Path) -> tuple[list[dict], float | None]:
    """Return status-tagged latency points and the clock offset from one k6 raw export."""
    points: list[dict] = []
    offset = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("type") != "Point":
            continue
        metric = row.get("metric")
        data = row.get("data", {})
        if metric == "request_duration":
            tags = data.get("tags", {})
            stamp = data.get("time")
            if not isinstance(stamp, str):
                raise RuntimeError("a k6 raw request point holds no RFC3339 time")
            points.append(
                {
                    "time": datetime.fromisoformat(stamp).timestamp() * 1000.0,
                    "value": float(data["value"]),
                    "user_class": str(tags.get("user_class", "unknown")),
                    "operation": str(tags.get("operation", "unknown")),
                    "status": str(tags.get("status", "unknown")),
                }
            )
        elif metric == "clock_offset_seconds":
            offset = float(data.get("value", 0.0))
    return points, offset


def _cache_rates(path: Path, start: float, end: float) -> dict:
    """Return one hit rate per cache over the sampler window."""
    result: dict[str, dict] = {}
    if not path.is_file():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        cache = event.get("cache")
        kind = event.get("event")
        if cache is None or kind not in ("hit", "miss"):
            continue
        at = float(event.get("at", 0.0))
        if at < start or at > end:
            continue
        entry = result.setdefault(cache, {"hits": 0, "misses": 0})
        if kind == "hit":
            entry["hits"] += 1
        else:
            entry["misses"] += 1
    for entry in result.values():
        total = entry["hits"] + entry["misses"]
        entry["hit_rate"] = entry["hits"] / total if total else None
    return result


def _apportion(
    samples: list[dict],
    latencies: list[dict],
    offset: float,
) -> dict:
    """Share each counter interval's CPU equally among the requests that overlap it."""
    components = ("web_core_s", "db_core_s", "embedding_core_s")
    by_class: dict[str, dict[str, float]] = {}
    by_operation: dict[str, dict[str, float]] = {}
    unattributed = {name: 0.0 for name in components}
    for index in range(len(samples) - 1):
        first = samples[index]
        second = samples[index + 1]
        start = float(first["at"])
        end = float(second["at"])
        if end <= start:
            continue
        overlap = []
        for point in latencies:
            point_end = float(point["time"]) / 1000.0 - offset
            point_start = point_end - float(point["value"]) / 1000.0
            if point_start < end and point_end > start:
                overlap.append(point)
        if not overlap:
            for name in components:
                unattributed[name] += float(second[name]) - float(first[name])
            continue
        share = 1.0 / len(overlap)
        for point in overlap:
            class_name = str(point.get("user_class", "unknown"))
            operation = str(point.get("operation", "unknown"))
            class_values = by_class.setdefault(class_name, {name: 0.0 for name in components})
            operation_values = by_operation.setdefault(
                operation, {name: 0.0 for name in components}
            )
            for name in components:
                value = (float(second[name]) - float(first[name])) * share
                class_values[name] += value
                operation_values[name] += value
    for values in (*by_class.values(), *by_operation.values()):
        values["total_core_s"] = sum(values[name] for name in components)
    return {
        "per_class": by_class,
        "per_operation": by_operation,
        "unattributed": unattributed,
    }


def _traffic_block(points: list[dict], seconds: float) -> dict:
    """Return successful, refused and client transport failure counts, throughput and latency."""

    def side(selected: list[dict]) -> dict:
        return {
            "count": len(selected),
            "per_second": len(selected) / seconds if seconds > 0 else 0.0,
            "latency_ms": _latency([point["value"] for point in selected]),
        }

    success = [point for point in points if point["status"] == "200"]
    refused = [point for point in points if point["status"] == "429"]
    transport = [point for point in points if point["status"] == "0"]
    attempts = len(points)
    return {
        "attempts": attempts,
        "success": side(success),
        "refused": side(refused),
        "refusal_rate": len(refused) / attempts if attempts else None,
        "transport_failures": side(transport),
        "transport_failure_rate": len(transport) / attempts if attempts else None,
    }


def _traffic(points: list[dict], seconds: float) -> dict:
    """Return traffic overall, per simulated user class and per operation."""
    classes = sorted({point["user_class"] for point in points})
    operations = sorted({point["operation"] for point in points})
    return {
        "overall": _traffic_block(points, seconds),
        "by_class": {
            name: _traffic_block(
                [point for point in points if point["user_class"] == name], seconds
            )
            for name in classes
        },
        "by_operation": {
            name: _traffic_block([point for point in points if point["operation"] == name], seconds)
            for name in operations
        },
    }


def _windows(points: list[dict], level_ms: float, settle_ms: float) -> dict:
    """Return the full, settle and measured traffic windows of one level."""
    if level_ms <= 0:
        raise RuntimeError("the workload holds no positive level length")
    if not 0 <= settle_ms < level_ms:
        raise RuntimeError("the settle window must fit inside the level")
    start = min(point["time"] for point in points)
    end = start + level_ms
    settle_end = start + settle_ms
    full = [point for point in points if point["time"] <= end]
    settle = [point for point in points if point["time"] <= settle_end]
    measured = [point for point in points if settle_end < point["time"] <= end]
    return {
        "full": {
            "started_at_ms": start,
            "finished_at_ms": end,
            "seconds": level_ms / 1000.0,
            "traffic": _traffic(full, level_ms / 1000.0),
        },
        "settle": {
            "started_at_ms": start,
            "finished_at_ms": settle_end,
            "seconds": settle_ms / 1000.0,
            "traffic": _traffic(settle, settle_ms / 1000.0),
        },
        "measured": {
            "started_at_ms": settle_end,
            "finished_at_ms": end,
            "seconds": (level_ms - settle_ms) / 1000.0,
            "traffic": _traffic(measured, (level_ms - settle_ms) / 1000.0),
        },
    }


def summarize(
    *,
    summary_path: Path,
    raw_path: Path,
    counters_path: Path,
    cache_events: Path,
    workload_path: Path,
    profile: str,
    users: int,
    settle_seconds: float | None = None,
) -> dict:
    """Build one recorded level result.

    An unexpected status or a failed request that no client transport failure explains raises. A
    request with status 0 is a client transport failure and is recorded separately.
    """
    if users < 1:
        raise ValueError("the level user count must be positive")
    summary = load_json(summary_path)
    workload = load_workload(workload_path)
    if profile not in workload["capacity"]["profiles"]:
        raise ValueError(f"the workload has no capacity profile {profile}")
    settle = (
        float(workload["capacity"]["settle_seconds"])
        if settle_seconds is None
        else float(settle_seconds)
    )
    metrics = summary.get("metrics", {})
    points, offset = _read_raw(raw_path)
    if not points:
        raise RuntimeError("the k6 raw export holds no status-tagged request points")
    clock = 0.0 if offset is None else offset
    status_counts: dict[str, int] = {}
    for point in points:
        status_counts[point["status"]] = status_counts.get(point["status"], 0) + 1
    unexpected = {
        status: count
        for status, count in status_counts.items()
        if status not in ("200", "429", "0")
    }
    transport_failures = int(status_counts.get("0", 0))
    metric_values = {
        name: metrics.get(name, {}).get("values", {})
        for name in (
            "unexpected_status",
            "http_reqs",
            "iterations",
            "http_req_duration",
            "http_req_failed",
        )
    }
    unexpected_metric = int(metric_values["unexpected_status"].get("count", 0) or 0)
    failed_metric = metric_values["http_req_failed"]
    failed_rate = float(failed_metric.get("rate", 0.0) or 0.0)
    if (
        unexpected
        or (unexpected_metric and unexpected_metric > transport_failures)
        or (failed_rate > 0.0 and transport_failures == 0)
    ):
        raise RuntimeError(
            "the run returned an unexpected status or a failed request: "
            f"unexpected_status={unexpected or metric_values['unexpected_status']}, "
            f"http_req_failed={failed_metric}, transport_failures={transport_failures}"
        )
    recorded = load_json(counters_path)
    samples = recorded.get("samples", [])
    if len(samples) < 2:
        raise RuntimeError("the counter record holds fewer than two samples")
    component_totals = {
        name: float(samples[-1][name]) - float(samples[0][name])
        for name in ("web_core_s", "db_core_s", "embedding_core_s")
    }
    apportioned = _apportion(samples, points, clock)
    duration_ms = float(summary.get("state", {}).get("testRunDurationMs") or 0)
    level_ms = float(workload["capacity"]["level_seconds"]) * 1000.0
    if duration_ms + 1000.0 < level_ms:
        raise RuntimeError("the k6 run ended before the configured level length")
    windows = _windows(points, level_ms, settle * 1000.0)
    summary_metrics = {
        name: metric_values[name]
        for name in ("http_reqs", "iterations", "http_req_duration", "http_req_failed")
    }
    memory = recorded.get("memory", {})
    memory_series = [
        {
            "at": float(sample["at"]),
            "web_current_bytes": int(sample["web_current_bytes"]),
            "stat": sample["web_detail"]["stat"],
            "processes": sample["web_detail"]["processes"],
        }
        for sample in samples
        if "web_detail" in sample
    ]
    host_busy = float(recorded["host"]["busy_core_s_end"]) - float(
        recorded["host"]["busy_core_s_start"]
    )
    total_core = sum(component_totals.values())
    seconds = float(recorded["finished_at"]) - float(recorded["started_at"])
    return {
        "schema": 1,
        "profile": profile,
        "users": users,
        "workload_version": int(workload["version"]),
        "seed": workload.get("seed"),
        "window": {
            "started_at": recorded.get("started_at"),
            "finished_at": recorded.get("finished_at"),
            "seconds": seconds,
        },
        "k6": {
            "test_run_duration_ms": duration_ms,
            "level_seconds": float(workload["capacity"]["level_seconds"]),
            "settle_seconds": settle,
            "thresholds": summary.get("options", {}).get("thresholds"),
            "metrics": summary_metrics,
        },
        "requests": {
            "statuses": status_counts,
            "refused_429": int(metrics.get("refused_429", {}).get("count", 0) or 0),
            "transport_failures": transport_failures,
            "unexpected": unexpected,
        },
        "windows": windows,
        "cache": _cache_rates(
            cache_events, float(recorded["started_at"]), float(recorded["finished_at"])
        ),
        "core_seconds": {
            "total": component_totals,
            "per_class": apportioned["per_class"],
            "per_operation": apportioned["per_operation"],
            "unattributed": apportioned["unattributed"],
            "method": "apportioned: equal share per overlapping request from the server counter series",
            "clock_offset_seconds": clock,
            "clock_source": "response date header" if offset is not None else "unavailable",
        },
        "memory": memory,
        "memory_series": memory_series,
        "background": {
            "host_busy_core_s": host_busy,
            "measured_core_s": total_core,
            "background_core_s": host_busy - total_core,
            "host_busy_core_s_per_second": host_busy / seconds if seconds else None,
        },
        "usage": recorded.get("usage"),
    }


def saturation(results: list[dict], rise_fraction: float) -> dict:
    """Return the light-throughput saturation view over one profile's level results."""
    if not results:
        raise ValueError("the saturation view needs at least one level result")
    if not 0.0 < rise_fraction < 1.0:
        raise ValueError("the saturation rise must be a fraction between zero and one")
    ordered = sorted(results, key=lambda result: int(result["users"]))
    profile = str(ordered[0]["profile"])
    if any(str(result["profile"]) != profile for result in ordered):
        raise ValueError("the saturation view needs the results of one profile")
    levels = []
    previous = None
    stop_level = None
    for result in ordered:
        light = result["windows"]["measured"]["traffic"]["by_class"].get("light")
        if light is None:
            raise RuntimeError(f"the level {result['users']} holds no light request")
        per_second = float(light["success"]["per_second"])
        rise = None
        if previous is not None:
            rise = (per_second - previous) / previous if previous > 0.0 else None
        settles = previous is not None and (rise is None or rise < rise_fraction)
        if settles and stop_level is None:
            stop_level = int(result["users"])
        levels.append(
            {
                "users": int(result["users"]),
                "light_success_per_second": per_second,
                "rise_fraction": rise,
                "light_success_latency_ms": light["success"]["latency_ms"],
                "light_refusal_rate": light["refusal_rate"],
                "light_refused_latency_ms": light["refused"]["latency_ms"],
                "meets_stop_rule": settles,
            }
        )
        previous = per_second
    return {
        "profile": profile,
        "rule": {
            "metric": "light successful requests per second in the measured window",
            "rise_fraction": rise_fraction,
        },
        "levels": levels,
        "stop_level": stop_level,
    }


def main(argv: list[str] | None = None) -> int:
    """Run the bundle, counters, summarize or saturation command."""
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    bundle = subcommands.add_parser("bundle", help="write one k6 run bundle")
    bundle.add_argument("--machine-config", type=Path, default=DEFAULT_MACHINE_CONFIG)
    bundle.add_argument("--workload", type=Path, default=DEFAULT_WORKLOAD)
    bundle.add_argument("--name")
    bundle.add_argument("--database", required=True)
    sample = subcommands.add_parser("counters", help="sample one running stack")
    sample.add_argument("--machine-config", type=Path, default=DEFAULT_MACHINE_CONFIG)
    sample.add_argument("--name", required=True)
    sample.add_argument("--output", type=Path)
    sample.add_argument("--interval", type=float, default=0.25)
    sample.add_argument("--seconds", type=float)
    summary = subcommands.add_parser("summarize", help="pair one k6 run with its counters")
    summary.add_argument("--k6-summary", type=Path, required=True)
    summary.add_argument("--k6-raw", type=Path, required=True)
    summary.add_argument("--counters", type=Path, required=True)
    summary.add_argument("--cache-events", type=Path, required=True)
    summary.add_argument("--profile", choices=("light_only", "mixed"), required=True)
    summary.add_argument("--users", type=int, required=True)
    summary.add_argument("--settle-seconds", type=float)
    summary.add_argument("--workload", type=Path, default=DEFAULT_WORKLOAD)
    summary.add_argument("--output", type=Path)
    view = subcommands.add_parser("saturation", help="apply the light saturation rule")
    view.add_argument("--results", type=Path, nargs="+", required=True)
    view.add_argument("--rise", type=float)
    view.add_argument("--workload", type=Path, default=DEFAULT_WORKLOAD)
    view.add_argument("--output", type=Path)
    arguments = parser.parse_args(argv)
    if arguments.command == "bundle":
        machine = load_machine_config(arguments.machine_config)
        workload = load_workload(arguments.workload)
        name = arguments.name or f"bundle-{utc_stamp()}"
        path = build_bundle(
            machine=machine,
            workload=workload,
            workload_path=arguments.workload,
            name=name,
            database=arguments.database,
        )
        print(path)
        return 0
    if arguments.command == "counters":
        output = arguments.output or (RUN_ROOT / "results" / f"counters-{arguments.name}.json")
        sample_counters(
            machine_config=arguments.machine_config,
            name=arguments.name,
            output=output,
            interval=arguments.interval,
            seconds=arguments.seconds,
        )
        print(output)
        return 0
    if arguments.command == "saturation":
        workload = load_workload(arguments.workload)
        rise = (
            float(workload["capacity"]["saturation_rise"])
            if arguments.rise is None
            else float(arguments.rise)
        )
        results = [load_json(path) for path in arguments.results]
        output = arguments.output or (RUN_ROOT / "results" / f"saturation-{utc_stamp()}.json")
        result = saturation(results, rise)
        write_json(output, result)
        print(output)
        return 0
    output = arguments.output or (RUN_ROOT / "results" / f"k6-{utc_stamp()}.json")
    result = summarize(
        summary_path=arguments.k6_summary,
        raw_path=arguments.k6_raw,
        counters_path=arguments.counters,
        cache_events=arguments.cache_events,
        workload_path=arguments.workload,
        profile=arguments.profile,
        users=arguments.users,
        settle_seconds=arguments.settle_seconds,
    )
    write_json(output, result)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
