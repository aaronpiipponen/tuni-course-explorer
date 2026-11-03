"""Measure one request at a time against a fresh disposable stack.

Usage::

    python tools/load/matrix.py --database DATABASE --admin-state-root PATH
        (--checkout PATH | --commit COMMIT) [options]

``--database`` names the stack's database, which must end with ``_test``.
``--admin-state-root`` is the state root inside the disposable checkout.
``--checkout`` is a checkout to run, and ``--commit`` a commit to extract into a disposable
checkout.
``--machine-config`` is the machine configuration file.
``--workload`` is the workload file.
``--name`` names the stack, defaulting to ``matrix-<UTC timestamp>``.
``--port``, ``--workers`` and ``--memory-mib`` override the machine values.
``--samples`` is the measured sample count per case.
``--miss-samples`` is the distinct cache-miss count per cached case.
``--per-case-warmups`` is the warm-up count before each uncached case.
``--no-instrument`` disables the cache event log.
``--keep-checkout`` keeps the disposable checkout after the run.
``--output`` is the result path, defaulting to ``data/load/results/<name>.json``.

The matrix sends the workload's bodies sequentially over HTTP, reads the web, database and
embedding cgroup counters around each call, and records per-operation core-seconds for cache misses
and hits, memory, background CPU and the admission fit inputs. A cached case measures its configured
number of misses on distinct request bodies of the same shape, so one fit point is a mean with a
measured range. A stack that rejects a body stops the run with the label, status and response
prefix.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import platform
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import context
import counters
from common import (
    DEFAULT_MACHINE_CONFIG,
    DEFAULT_WORKLOAD,
    RUN_ROOT,
    load_workload,
    utc_stamp,
    write_json,
)
from launcher import Stack
from machine import load_machine_config

_PATHS = {
    "search": "/api/search",
    "recommendations": "/api/recommendations",
    "next_courses": "/api/next-courses",
    "prerequisites": "/api/prerequisites",
    "comparison": "/api/comparison",
    "study_structure": "/api/study-structure",
    "catalogue": "/api/catalogue",
    "features": "/api/features",
}


def _post(
    url: str, path: str, body: dict, *, accept_gzip: bool = False
) -> tuple[int, bytes, dict[str, str]]:
    """Send one JSON body without following an error status."""
    request = urllib.request.Request(
        url + path,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "accept-encoding": "gzip" if accept_gzip else "identity",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            headers = {key.lower(): value for key, value in response.headers.items()}
            return response.status, response.read(), headers
    except urllib.error.HTTPError as error:
        headers = {key.lower(): value for key, value in error.headers.items()}
        return error.code, error.read(), headers


def _basis(workload: dict, offset: int, size: int) -> list[str]:
    """Return one deterministic basis from the workload pool."""
    pool = workload["pool"]
    return [pool[(offset + index) % len(pool)] for index in range(size)]


def _entry(pool: dict, group_id: str) -> dict:
    """Return one pool course's context entry or fail loudly."""
    try:
        return pool[group_id]
    except KeyError as error:
        raise RuntimeError(f"the payload context has no entry for {group_id}") from error


def build_body(case: dict, workload: dict, context_values: dict) -> dict:
    """Build one request body from the workload rules and the dataset context."""
    operation = case["operation"]
    language = workload["display_language"]
    if operation == "search":
        pool = workload["pool"]
        group_id = pool[int(case["query_pool_index"]) % len(pool)]
        entry = _entry(context_values["pool"], group_id)
        if case["query"] == "code":
            text = entry["code"]
        elif case["query"] == "title":
            text = entry["title_en"] or entry["title_fi"]
        else:
            raise ValueError(f"the search case {case['label']} holds an unknown query rule")
        if not text:
            raise RuntimeError(f"the pool course {group_id} has no query text")
        return {
            "query": text,
            "display_language": language,
            "include_inactive": bool(case.get("include_inactive", False)),
        }
    if operation in ("recommendations", "next_courses"):
        body = {
            "selected_courses": [],
            "completed_courses": _basis(
                workload, int(case.get("basis_offset", 0)), int(case["basis_size"])
            ),
            "basis": "completed",
            "display_language": language,
            "include_inferred": bool(case.get("include_inferred", False)),
            "active_only": bool(case.get("active_only", True)),
        }
        if operation == "next_courses":
            body["mode"] = "all"
        return body
    if operation == "prerequisites":
        return {
            "target_code": case["target"],
            "selected_codes": list(workload["graph_selected"]),
            "completed_codes": [],
            "include_recommended": False,
            "include_inferred": bool(case.get("include_inferred", False)),
            # The graph request model defaults active_only to false.
            "active_only": bool(case.get("active_only", False)),
        }
    if operation == "comparison":
        pool = workload["pool"]
        first = pool[int(case["course_a_index"]) % len(pool)]
        second = pool[int(case["course_b_index"]) % len(pool)]
        return {"course_a": first, "course_b": second}
    if operation == "study_structure":
        if case.get("explicit_version"):
            entry = context_values["study_explicit_version"]
            return {
                "root_group_ids": [entry["group_id"]],
                "module_versions": {entry["group_id"]: entry["version"]},
                "allow_unavailable": True,
            }
        roots = context_values[
            "study_roots_with_unavailable"
            if case.get("include_unavailable_roots")
            else "study_roots"
        ]
        return {
            "root_group_ids": roots[: int(case.get("root_count", 20))],
            "allow_unavailable": True,
        }
    if operation in ("catalogue", "features"):
        return {}
    raise RuntimeError(f"the matrix has no body rule for {operation}")


def _cache_identity(operation: str, body: dict) -> tuple | None:
    """Return the cache key one measured request occupies, or ``None`` when it occupies none.

    Recommendations and next courses share the next-course report cache, so both produce the same
    key shape. The query-embedding cache is keyed by the query text alone.
    """
    if operation in ("recommendations", "next_courses"):
        return (
            "next_report",
            tuple(sorted(body["completed_courses"])),
            bool(body["active_only"]),
            bool(body["include_inferred"]),
            body["display_language"],
            body.get("mode", "all"),
        )
    if operation == "search":
        return ("query_embedding", body["query"])
    return None


def _variant_bodies(
    case: dict, workload: dict, context_values: dict, count: int, used: set
) -> list[tuple[dict, dict]]:
    """Return one distinct request body per sample of a cached or cacheless search case.

    A recommendation or next-courses case takes distinct pool offsets of the same basis size. A
    search case takes distinct pool courses. A candidate whose cache key the run already requested
    is skipped, so every returned body of a cached case is a genuine miss, and each returned
    identity is added to ``used``. A full-pool basis is one canonical request, so it cannot supply
    distinct bodies and fails loudly.
    """
    pool_size = len(workload["pool"])
    operation = case["operation"]
    variants: list[tuple[dict, dict]] = []
    if operation in ("recommendations", "next_courses"):
        size = int(case["basis_size"])
        if size >= pool_size:
            raise RuntimeError(
                f"the case {case['label']} uses a full-pool basis, so every sample resolves to "
                "the same canonical request and cannot be a distinct miss"
            )
        step = pool_size // count
        if step < 1:
            raise RuntimeError(
                f"the case {case['label']} asks for more miss samples than the pool provides"
            )
        start = int(case.get("basis_offset", 0))
        for index in range(count):
            offset = (start + index * step) % pool_size
            for attempt in range(pool_size):
                current = (offset + attempt) % pool_size
                body = build_body({**case, "basis_offset": current}, workload, context_values)
                identity = _cache_identity(operation, body)
                if identity in used:
                    continue
                used.add(identity)
                variants.append(({"basis_offset": current}, body))
                break
            else:
                raise RuntimeError(f"the case {case['label']} found no unused basis of size {size}")
        return variants
    if operation == "search":
        start = int(case["query_pool_index"])
        for step in range(pool_size):
            current = (start + step) % pool_size
            body = build_body({**case, "query_pool_index": current}, workload, context_values)
            identity = _cache_identity(operation, body)
            if identity in used:
                continue
            used.add(identity)
            variants.append(({"query_pool_index": current}, body))
            if len(variants) == count:
                return variants
        raise RuntimeError(
            f"the case {case['label']} found only {len(variants)} unused query texts"
        )
    raise RuntimeError(f"the case {case['label']} has no rule for distinct cache-miss bodies")


def _read_events(path: Path | None, offset: int) -> tuple[list[dict], int]:
    """Return the cache events appended since one byte offset."""
    if path is None or not path.is_file():
        return [], offset
    content = path.read_bytes()
    if len(content) < offset:
        offset = 0
    rows = []
    for line in content[offset:].splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows, len(content)


def _cache_state(events: list[dict], cache: str) -> str | None:
    """Return a hit when any request of the cache hit, else a miss, else ``None``."""
    states = [
        event["event"]
        for event in events
        if event.get("cache") == cache and event.get("event") in ("hit", "miss")
    ]
    if "hit" in states:
        return "hit"
    if "miss" in states:
        return "miss"
    return None


def _result_facts(path: str, payload: bytes) -> tuple[int | None, int | None]:
    """Return the report's result count and prerequisite drawing element count."""
    try:
        report = json.loads(payload)
    except json.JSONDecodeError:
        return None, None
    if path == "/api/search":
        return len(report.get("results", ())), None
    if path == "/api/recommendations":
        return len(report.get("similarity_results", ())), None
    if path == "/api/next-courses":
        return len(report.get("results", ())), None
    if path == "/api/study-structure":
        return (
            len(report.get("roots", ())) + len(report.get("unavailable_root_group_ids", ())),
            None,
        )
    if path == "/api/catalogue":
        return len(report.get("courses", ())) + len(report.get("modules", ())), None
    if path == "/api/prerequisites":
        pieces = len((report.get("solver") or {}).get("pieces") or ())
        drawing = report.get("drawing") or {}
        return pieces, drawing.get("element_count")
    return None, None


def _measure(
    url: str,
    path: str,
    body: dict,
    counters_by_name: dict[str, Path],
    *,
    accept_gzip: bool = False,
) -> dict:
    """Send one request and return its status, sizes and component core-seconds."""
    before = {name: counters.cpu_seconds(component) for name, component in counters_by_name.items()}
    wall_start = time.perf_counter()
    status, payload, headers = _post(url, path, body, accept_gzip=accept_gzip)
    wall = time.perf_counter() - wall_start
    after = {name: counters.cpu_seconds(component) for name, component in counters_by_name.items()}
    split = {name: after[name] - before[name] for name in counters_by_name}
    decoded = gzip.decompress(payload) if headers.get("content-encoding") == "gzip" else payload
    result_count, drawing_elements = _result_facts(path, decoded)
    return {
        "status": status,
        "bytes": len(payload),
        "gzip": headers.get("content-encoding") == "gzip",
        "wall_s": wall,
        "web_core_s": split["web"],
        "db_core_s": split["db"],
        "embedding_core_s": split["embedding"],
        "total_core_s": sum(split.values()),
        "result_count": result_count,
        "drawing_elements": drawing_elements,
        "preview": payload[:300],
    }


def _fail(label: str, result: dict) -> None:
    """Raise one content-safe refusal for a request the stack did not accept."""
    preview = result["preview"].decode("utf-8", errors="replace")
    raise RuntimeError(f"{label} answered {result['status']}: {preview!r}")


def _summary(rows: list[dict]) -> dict:
    """Return the median, range, mean and spread of one state's rows."""
    result = {}
    for name in ("web_core_s", "db_core_s", "embedding_core_s", "total_core_s", "wall_s"):
        values = [float(row[name]) for row in rows]
        result[name] = {
            "count": len(values),
            "median": statistics.median(values),
            "mean": statistics.fmean(values),
            "min": min(values),
            "max": max(values),
            "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
            "values": values,
        }
    return result


def _fit_class(case: dict) -> str | None:
    """Return the admission class of one matrix case, or ``None`` when it has none.

    Inference is not an admission dimension: an inference-enabled recommendation, next-course or
    graph request keeps the product class of the same route and scope, so its fit entry is named by
    that class and distinguished by its case label.
    """
    operation = case["operation"]
    active = bool(case.get("request", {}).get("active_only", True))
    if operation == "recommendations":
        return "recommendation_active" if active else "recommendation_inactive"
    if operation == "next_courses":
        return "next_courses_active" if active else "next_courses_inactive"
    if operation == "prerequisites":
        return "graph"
    if operation == "search" and case.get("request", {}).get("include_inactive"):
        return "search_inactive"
    return None


def run(
    *,
    stack: Stack,
    workload: dict,
    workload_path: Path,
    context_values: dict,
    samples: int | None,
    matrix_warmups: int | None,
    miss_samples: int | None = None,
) -> dict:
    """Run the matrix and return the result document."""
    url = f"http://{stack.machine.stack.web_host}:{stack.port}"
    db_cpu = counters.container_cgroup(stack.machine.stack.database_container, "cpuacct")
    db_memory = counters.container_cgroup(stack.machine.stack.database_container, "memory")
    embedding_cpu = counters.container_cgroup(stack.machine.stack.embedding_container, "cpuacct")
    embedding_memory = counters.container_cgroup(stack.machine.stack.embedding_container, "memory")
    components = {"web": stack.cpu_cgroup, "db": db_cpu, "embedding": embedding_cpu}
    memory_paths = {"web": stack.memory_cgroup, "db": db_memory, "embedding": embedding_memory}
    matrix = workload["matrix"]
    warmup_samples = int(matrix.get("warmup_samples", 1))
    per_case_warmups = int(
        matrix.get("per_case_warmup_samples", 1) if matrix_warmups is None else matrix_warmups
    )
    sample_count = int(matrix.get("samples", 3) if samples is None else samples)
    if sample_count < 1:
        raise ValueError("the matrix sample count must be positive")
    miss_count = int(matrix.get("miss_samples", 3) if miss_samples is None else miss_samples)
    if miss_count < 1:
        raise ValueError("the matrix miss sample count must be positive")
    if warmup_samples < 0 or per_case_warmups < 0:
        raise ValueError("the matrix warm-up count must not be negative")
    event_path = Path(stack.state["cache_events"]) if stack.state.get("cache_events") else None
    if event_path is None and any(case.get("cache", "none") != "none" for case in matrix["cases"]):
        raise RuntimeError("cache instrumentation is required for a matrix with cached cases")
    events_offset = 0
    patched_caches: set[str] = set()
    if event_path is not None:
        # Drop the startup events before the first measured call.
        startup_events, events_offset = _read_events(event_path, 0)
        for event in startup_events:
            if event.get("event") == "startup":
                patched_caches = set(event.get("patched") or ())
    host_before = counters.host_cpu()
    component_before = {name: counters.cpu_seconds(path) for name, path in components.items()}
    memory_before = {name: counters.memory_state(path) for name, path in memory_paths.items()}
    used: set = set()
    for case in matrix.get("warmup", ()):
        body = build_body(case, workload, context_values)
        identity = _cache_identity(case["operation"], body)
        if identity is not None and identity[0] in patched_caches:
            used.add(identity)
        for _index in range(warmup_samples):
            result = _measure(
                url,
                _PATHS[case["operation"]],
                body,
                components,
                accept_gzip=bool(case.get("accept_gzip", False)),
            )
            if result["status"] != 200:
                _fail(str(case["label"]), result)
    _events, events_offset = _read_events(event_path, events_offset)
    measured: list[dict] = []
    for case in matrix["cases"]:
        label = str(case["label"])
        body = build_body(case, workload, context_values)
        cache = str(case.get("cache", "none"))
        if cache == "none":
            for _index in range(per_case_warmups):
                result = _measure(
                    url,
                    _PATHS[case["operation"]],
                    body,
                    components,
                    accept_gzip=bool(case.get("accept_gzip", False)),
                )
                if result["status"] != 200:
                    _fail(label, result)
            _events, events_offset = _read_events(event_path, events_offset)
            if case["operation"] == "search":
                # A search without a query cache still runs one distinct query per sample.
                variants = _variant_bodies(case, workload, context_values, sample_count, used)
                schedule = [("warm", variant, variant_body) for variant, variant_body in variants]
            else:
                schedule = [("warm", None, body) for _index in range(sample_count)]
        else:
            variants = _variant_bodies(case, workload, context_values, miss_count, used)
            schedule = [("miss", variant, variant_body) for variant, variant_body in variants]
            schedule += [("hit", variants[0][0], variants[0][1]) for _index in range(sample_count)]
        case_rows = []
        for state, variant, measured_body in schedule:
            result = _measure(
                url,
                _PATHS[case["operation"]],
                measured_body,
                components,
                accept_gzip=bool(case.get("accept_gzip", False)),
            )
            if result["status"] != 200:
                _fail(label, result)
            events, events_offset = _read_events(event_path, events_offset)
            actual = _cache_state(events, cache) if cache != "none" else None
            row = {
                "cache_state": actual or ("none" if cache == "none" else state),
                "expected_cache_state": None if cache == "none" else state,
                "cache": cache,
                "cache_events": events,
                "variant": variant,
                "status": result["status"],
                "bytes": result["bytes"],
                "result_count": result["result_count"],
                "drawing_elements": result["drawing_elements"],
                "gzip": result["gzip"],
                "wall_s": result["wall_s"],
                "web_core_s": result["web_core_s"],
                "db_core_s": result["db_core_s"],
                "embedding_core_s": result["embedding_core_s"],
                "total_core_s": result["total_core_s"],
            }
            if cache != "none" and actual is None:
                raise RuntimeError(f"{label} produced no {cache} cache event")
            if state == "miss" and actual == "hit":
                raise RuntimeError(f"{label} expected a cache miss but measured a hit")
            if state == "hit" and actual == "miss":
                raise RuntimeError(f"{label} expected a cache hit but measured a miss")
            case_rows.append(row)
        measured.append(
            {
                "label": label,
                "operation": case["operation"],
                "cache": cache,
                "request": body,
                "rows": case_rows,
                "by_state": {
                    state: _summary([row for row in case_rows if row["cache_state"] == state])
                    for state in {row["cache_state"] for row in case_rows}
                },
            }
        )
    host_after = counters.host_cpu()
    memory_after = {name: counters.memory_state(path) for name, path in memory_paths.items()}
    component_after = {name: counters.cpu_seconds(path) for name, path in components.items()}
    component_core_s = {name: component_after[name] - component_before[name] for name in components}
    measured_total = sum(component_core_s.values())
    host_busy = host_after["busy_seconds"] - host_before["busy_seconds"]
    fit_inputs = []
    for case in measured:
        fit_class = _fit_class(case)
        if fit_class is None:
            continue
        state_rows = case["by_state"]
        state = "miss" if "miss" in state_rows else next(iter(state_rows))
        summary = state_rows[state]
        fit = {
            "class": fit_class,
            "label": case["label"],
            "include_inferred": bool(case["request"].get("include_inferred", False)),
            "cache_state": state,
            "basis_size": (
                len(case["request"]["completed_courses"])
                if case["operation"] in ("recommendations", "next_courses")
                else 0
            ),
            "core_s_mean": summary["total_core_s"]["mean"],
            "core_s_median": summary["total_core_s"]["median"],
            "core_s_min": summary["total_core_s"]["min"],
            "core_s_max": summary["total_core_s"]["max"],
            "elapsed_s_median": summary["wall_s"]["median"],
            "sample_count": summary["total_core_s"]["count"],
            "result_count": case["rows"][0].get("result_count"),
            "drawing_elements": case["rows"][0].get("drawing_elements"),
        }
        fit_inputs.append(fit)
    return {
        "schema": 1,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "workload": {
            "version": workload["version"],
            "seed": workload.get("seed"),
            "path": str(workload_path),
        },
        "dataset": context_values["dataset"],
        "stack": stack.state,
        "measurement": {
            "warmup_samples": warmup_samples,
            "per_case_warmup_samples": per_case_warmups,
            "sample_count": sample_count,
            "miss_samples": miss_count,
            "request_timeout_seconds": 300,
            "components": {name: str(path) for name, path in components.items()},
        },
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "cpu_count": os.cpu_count(),
            "host_load_start": stack.state.get("host_load_start"),
            "host_load_end": counters.host_load(),
        },
        "background": {
            "host_busy_core_s": host_busy,
            "measured_component_core_s": component_core_s,
            "measured_total_core_s": measured_total,
            "background_core_s": host_busy - measured_total,
            "load_start": stack.state.get("host_load_start"),
            "load_end": counters.host_load(),
        },
        "memory": {
            **memory_after,
            "before": memory_before,
            "sum_current_bytes": sum(
                int(values["current_bytes"]) for values in memory_after.values()
            ),
            "sum_peak_bytes": sum(int(values["peak_bytes"]) for values in memory_after.values()),
            "peak_scopes": {
                "web": "run",
                "db": "container_lifetime",
                "embedding": "container_lifetime",
            },
        },
        "usage": {
            "path": stack.state.get("usage_path"),
            "lines_before": stack.state.get("usage_lines_before"),
            "lines_after": counters.usage_lines(Path(stack.state["usage_path"])),
        },
        "cases": measured,
        "fit_inputs": fit_inputs,
    }


def main(argv: list[str] | None = None) -> int:
    """Run the cost matrix against one fresh disposable stack."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--machine-config", type=Path, default=DEFAULT_MACHINE_CONFIG)
    parser.add_argument("--workload", type=Path, default=DEFAULT_WORKLOAD)
    parser.add_argument("--checkout", type=Path)
    parser.add_argument("--commit")
    parser.add_argument("--name")
    parser.add_argument("--database", required=True)
    parser.add_argument("--admin-state-root", required=True)
    parser.add_argument("--memory-mib", type=int)
    parser.add_argument("--workers", type=int)
    parser.add_argument("--port", type=int)
    parser.add_argument("--samples", type=int)
    parser.add_argument("--miss-samples", type=int)
    parser.add_argument("--per-case-warmups", type=int)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--no-instrument", action="store_true")
    parser.add_argument("--keep-checkout", action="store_true")
    arguments = parser.parse_args(argv)
    machine = load_machine_config(arguments.machine_config)
    workload = load_workload(arguments.workload)
    name = arguments.name or f"matrix-{utc_stamp()}"
    stack = Stack(
        machine=machine,
        name=name,
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
    stack.start()
    try:
        context_values = context.build_context(stack.environment(), workload)
        result = run(
            stack=stack,
            workload=workload,
            workload_path=arguments.workload,
            context_values=context_values,
            samples=arguments.samples,
            matrix_warmups=arguments.per_case_warmups,
            miss_samples=arguments.miss_samples,
        )
    finally:
        stack.stop()
    result["stack"] = stack.state
    output = arguments.output or (RUN_ROOT / "results" / f"{name}.json")
    write_json(output, result)
    print(
        json.dumps(
            {
                "output": str(output),
                "stack": stack.state["name"],
                "cases": len(result["cases"]),
                "fit_inputs": len(result["fit_inputs"]),
                "usage_lines": result["usage"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
