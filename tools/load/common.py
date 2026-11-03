"""Shared paths, workload loading and JSON helpers for the serving load tooling."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RUN_ROOT = ROOT / "data" / "load"
INSTRUMENT_DIRECTORY = HERE / "instrument"
DEFAULT_WORKLOAD = HERE / "workload.json"
DEFAULT_MACHINE_CONFIG = HERE / "machine.toml"

OPERATIONS = frozenset(
    {
        "search",
        "recommendations",
        "next_courses",
        "prerequisites",
        "comparison",
        "study_structure",
        "catalogue",
        "features",
    }
)
CACHE_KINDS = frozenset({"none", "query_embedding", "next_report"})
CYCLE_OPERATIONS = frozenset(
    {
        "search_title",
        "search_code",
        "study_structure",
        "prerequisites",
        "comparison",
        "recommendations",
        "next_courses",
    }
)


def utc_stamp() -> str:
    """Return one compact UTC timestamp for a run directory name."""
    return time.strftime("%Y%m%dT%H%M%S", time.gmtime())


def load_json(path: Path) -> object:
    """Read one UTF-8 JSON file and raise on invalid JSON."""
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: object) -> None:
    """Write one JSON document atomically with a trailing newline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def load_workload(path: Path = DEFAULT_WORKLOAD) -> dict:
    """Load and validate one versioned workload file.

    The validation rejects a missing section, an unknown operation, a duplicate matrix label and
    an unordered capacity ladder. A workload that does not fit the serving API fails at the first
    request and is never adapted.
    """
    document = load_json(path)
    if not isinstance(document, dict):
        raise ValueError("the workload must be a JSON object")
    required = {"version", "pool", "users", "cycles", "capacity", "matrix"}
    missing = sorted(required - set(document))
    if missing:
        raise ValueError(f"the workload is missing {missing}")
    if not isinstance(document["version"], int) or document["version"] < 1:
        raise ValueError("the workload version must be a positive integer")
    if not isinstance(document.get("seed"), int):
        raise ValueError("the workload seed must be an integer")
    pool = document["pool"]
    if (
        not isinstance(pool, list)
        or not pool
        or not all(isinstance(value, str) and value for value in pool)
    ):
        raise ValueError("the workload pool must hold non-empty course identities")
    if len(set(pool)) != len(pool):
        raise ValueError("the workload pool holds a duplicate identity")
    users = document["users"]
    for name in ("light", "heavy"):
        user = users.get(name)
        if not isinstance(user, dict):
            raise ValueError(f"the workload users section is missing {name}")
        if not 1 <= int(user.get("basis_min", 0)) <= int(user.get("basis_max", 0)):
            raise ValueError(f"the {name} basis range is not ordered and positive")
        if not isinstance(user.get("include_inferred"), bool):
            raise ValueError(f"the {name} include_inferred value must be a boolean")
        inactive = user.get("inactive_probability")
        if not isinstance(inactive, (int, float)) or not 0.0 <= float(inactive) <= 1.0:
            raise ValueError(f"the {name} inactive probability must be a probability")
        if int(user.get("study_roots", 0)) < 1:
            raise ValueError(f"the {name} study root count must be positive")
    for name in ("add_probability", "remove_probability"):
        value = users.get(name)
        if not isinstance(value, (int, float)) or not 0.0 <= float(value) <= 1.0:
            raise ValueError(f"the workload {name} must be a probability")
    think_min = users.get("think_time_seconds_min")
    think_max = users.get("think_time_seconds_max")
    if (
        not isinstance(think_min, (int, float))
        or not isinstance(think_max, (int, float))
        or float(think_min) < 0.0
        or float(think_max) < float(think_min)
    ):
        raise ValueError(
            "the workload think_time_seconds_min and think_time_seconds_max values must be "
            "ordered and non-negative"
        )
    target_probability = users.get("target_from_basis_probability")
    if (
        not isinstance(target_probability, (int, float))
        or not 0.0 <= float(target_probability) <= 1.0
    ):
        raise ValueError("the workload target probability must be a probability")
    cycles = document["cycles"]
    for name in ("light", "heavy"):
        cycle = cycles.get(name)
        if not isinstance(cycle, list) or not cycle:
            raise ValueError(f"the workload cycles section is missing {name}")
        unknown = sorted(set(cycle) - CYCLE_OPERATIONS)
        if unknown:
            raise ValueError(f"the {name} cycle holds unknown operations {unknown}")
    capacity = document["capacity"]
    levels = capacity.get("levels")
    if (
        not isinstance(levels, list)
        or not levels
        or not all(isinstance(level, int) and level > 0 for level in levels)
    ):
        raise ValueError("the capacity ladder must hold positive user counts")
    if any(right <= left for left, right in zip(levels, levels[1:])):
        raise ValueError("the capacity ladder must be strictly increasing")
    if int(capacity.get("level_seconds", 0)) <= 0:
        raise ValueError("the capacity level length must be positive")
    settle = capacity.get("settle_seconds")
    if not isinstance(settle, (int, float)) or not 0.0 <= float(settle) < int(
        capacity.get("level_seconds", 0)
    ):
        raise ValueError("the capacity settle window must fit inside one level")
    rise = capacity.get("saturation_rise")
    if not isinstance(rise, (int, float)) or not 0.0 < float(rise) < 1.0:
        raise ValueError("the saturation rise must be a fraction between zero and one")
    if int(capacity.get("heavy_every", 0)) < 1:
        raise ValueError("the mixed profile heavy interval must be positive")
    profiles = capacity.get("profiles")
    if not isinstance(profiles, list) or not profiles:
        raise ValueError("the capacity profiles must hold at least one profile")
    unknown_profiles = sorted(set(profiles) - {"light_only", "mixed"})
    if unknown_profiles:
        raise ValueError(f"the capacity profiles hold unknown names {unknown_profiles}")
    matrix = document["matrix"]
    if not isinstance(matrix.get("cases"), list) or not matrix["cases"]:
        raise ValueError("the workload matrix must hold cases")
    if int(matrix.get("samples", 0)) < 1:
        raise ValueError("the workload matrix sample count must be positive")
    if int(matrix.get("miss_samples", 1)) < 1:
        raise ValueError("the workload matrix miss sample count must be positive")
    labels = set()
    for case in matrix["cases"]:
        label = case.get("label")
        if not label or label in labels:
            raise ValueError(f"the workload matrix case label is missing or duplicate: {label!r}")
        labels.add(label)
        if case.get("operation") not in OPERATIONS:
            raise ValueError(f"the workload matrix case {label} holds an unknown operation")
        if case.get("cache", "none") not in CACHE_KINDS:
            raise ValueError(f"the workload matrix case {label} holds an unknown cache kind")
        if case.get("operation") == "prerequisites" and not document.get("graph_selected"):
            raise ValueError("the workload holds a graph case without graph_selected")
        if case.get("operation") == "search" and case.get("query") not in ("title", "code"):
            raise ValueError(f"the workload matrix case {label} holds an unknown search query")
    for case in matrix.get("warmup", ()):
        if case.get("operation") not in OPERATIONS:
            raise ValueError("the workload warm-up holds an unknown operation")
        if case.get("operation") == "search" and case.get("query") not in ("title", "code"):
            raise ValueError("a workload warm-up search holds an unknown query")
    return document
