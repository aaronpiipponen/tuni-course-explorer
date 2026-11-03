"""Fit the admission cost curves from one matrix result's fit inputs.

Usage::

    python tools/load/fit.py RESULT [--workload WORKLOAD] [--output OUTPUT]
        [--threshold SECONDS]

``RESULT`` is the matrix result whose ``fit_inputs`` the fit reads.
``--workload`` is the workload file whose version must match the result's.
``--output`` also writes the report to this path.
``--threshold`` is the curve cost in core-seconds that the acceptance rule checks, 1.0 by default.

The fit reads the matrix's ``fit_inputs`` directly, keeps the inference-enabled rows of each
recommendation and next-courses class, averages the rows of one basis size, and gives every measured
basis equal weight. Each input is itself a mean over distinct cache misses of the same request
shape, with its measured range. Each curve is
``base + head * min(n, knee) + tail * max(0, n - knee)`` with nonnegative coefficients and the
configured origin. The knee is searched over every integer basis from the smallest to the largest
measured basis. For each candidate knee the eight subsets of the three coefficients are solved with
NumPy least squares. The selected curve is the candidate that passes the measured crossing
acceptance rule with the smallest squared residual. A class whose candidates all miss that rule
reports its smallest-residual candidate and its failed acceptance. The origin cost is
``base + head * origin`` and the tail cost is ``base + head * knee``. The tool changes no
configuration file by itself.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy
from common import DEFAULT_WORKLOAD, load_json, write_json

from course_explorer.config import load_admission_settings

CLASSES = (
    "recommendation_active",
    "recommendation_inactive",
    "next_courses_active",
    "next_courses_inactive",
)
SUBSETS = tuple(
    tuple(name for index, name in enumerate(("base", "head", "tail")) if mask & (1 << index))
    for mask in range(8)
)


def _fit_coefficients(
    bases: numpy.ndarray, costs: numpy.ndarray, knee: int
) -> tuple[tuple[str, ...], dict[str, float], float, list[dict]]:
    """Return the feasible coefficient subset with the smallest squared residual and every trial."""
    columns = {
        "base": numpy.ones_like(bases),
        "head": numpy.minimum(bases, knee),
        "tail": numpy.maximum(0, bases - knee),
    }
    best: tuple[tuple[str, ...], dict[str, float], float] | None = None
    candidates = []
    for subset in SUBSETS:
        coefficients = {name: 0.0 for name in ("base", "head", "tail")}
        feasible = True
        if subset:
            design = numpy.column_stack([columns[name] for name in subset])
            solution, _residuals, _rank, _singular = numpy.linalg.lstsq(design, costs, rcond=None)
            feasible = all(value >= 0.0 for value in solution)
            if feasible:
                for name, value in zip(subset, solution, strict=True):
                    coefficients[name] = float(value)
        if feasible:
            prediction = sum(coefficients[name] * columns[name] for name in columns)
            residual = float(numpy.sum((prediction - costs) ** 2))
        else:
            residual = None
        candidates.append(
            {
                "active_coefficients": list(subset),
                "coefficients": dict(coefficients),
                "feasible": feasible,
                "squared_residual": residual,
            }
        )
        if feasible and (best is None or residual < best[2]):
            best = (subset, coefficients, residual)
    if best is None:
        raise RuntimeError("no nonnegative admission coefficient set fits the measurements")
    return (*best, candidates)


def _fit_knee(
    points: list[dict], *, origin: int, threshold: float
) -> tuple[tuple[int, tuple[str, ...], dict[str, float], float, list[dict], dict], list[dict]]:
    """Return the accepted knee with the smallest feasible residual and every candidate knee.

    The applied curve of every candidate knee is checked against the measured ranges around the
    first measured crossing. The selected knee is the accepted candidate with the smallest squared
    residual. When no candidate passes, the smallest residual candidate is selected and reports that
    it misses the acceptance rule.
    """
    basis_values = numpy.asarray([point["basis"] for point in points], dtype=numpy.float64)
    cost_values = numpy.asarray([point["mean"] for point in points], dtype=numpy.float64)
    smallest = max(1, int(basis_values.min()))
    largest = int(basis_values.max())
    if largest < smallest:
        raise RuntimeError("the measured bases do not span a knee candidate")
    best = None
    best_accepted = None
    scan = []
    for knee in range(smallest, largest + 1):
        subset, coefficients, residual, candidates = _fit_coefficients(
            basis_values, cost_values, knee
        )
        applied = _rounded_applied_values(coefficients, origin=origin, knee=knee)
        accepted = _acceptance(
            points,
            origin=origin,
            knee=knee,
            **applied,
            threshold=threshold,
        )
        scan.append(
            {
                "knee_basis": knee,
                "active_coefficients": list(subset),
                "squared_residual": residual,
                "acceptance_passes": accepted["passes"],
                "crossing_basis": accepted["crossing_basis"],
            }
        )
        candidate = (knee, subset, coefficients, residual, candidates, accepted)
        if best is None or residual < best[3]:
            best = candidate
        if accepted["passes"] and (best_accepted is None or residual < best_accepted[3]):
            best_accepted = candidate
    chosen = best_accepted or best
    assert chosen is not None
    return chosen, scan


def _rounded_applied_values(
    coefficients: dict[str, float], *, origin: int, knee: int
) -> dict[str, float]:
    """Return the four rounded configuration values the product curve evaluates."""
    return {
        "origin_cost": _rounded(coefficients["base"] + coefficients["head"] * origin),
        "slope": _rounded(coefficients["head"]),
        "tail_cost": _rounded(coefficients["base"] + coefficients["head"] * knee),
        "tail_slope": _rounded(coefficients["tail"]),
    }


def _curve_value(basis: int, *, knee: int, coefficients: dict[str, float]) -> float:
    """Return the fitted formula's value at one basis size."""
    return (
        coefficients["base"]
        + coefficients["head"] * min(basis, knee)
        + coefficients["tail"] * max(0, basis - knee)
    )


def _applied_curve_value(
    basis: int,
    *,
    origin: int,
    knee: int,
    origin_cost: float,
    slope: float,
    tail_cost: float,
    tail_slope: float,
) -> float:
    """Return the product curve's value from its rounded configuration values."""
    if basis <= knee:
        return origin_cost + slope * (basis - origin)
    return tail_cost + tail_slope * (basis - knee)


def _crossing(
    *, origin: int, knee: int, coefficients: dict[str, float], threshold: float
) -> int | None:
    """Return the smallest integer basis whose fitted cost reaches the threshold, or ``None``."""
    at_knee = _curve_value(knee, knee=knee, coefficients=coefficients)
    if at_knee >= threshold:
        if coefficients["head"] <= 0.0:
            return origin
        basis = (threshold - coefficients["base"]) / coefficients["head"]
        return max(origin, math.ceil(basis))
    if coefficients["tail"] <= 0.0:
        return None
    basis = knee + (threshold - at_knee) / coefficients["tail"]
    return max(knee + 1, math.ceil(basis))


def _applied_crossing(
    *,
    origin: int,
    knee: int,
    origin_cost: float,
    slope: float,
    tail_cost: float,
    tail_slope: float,
    threshold: float,
) -> int | None:
    """Return the first integer basis where the product curve reaches the threshold."""

    def value(basis: int) -> float:
        return _applied_curve_value(
            basis,
            origin=origin,
            knee=knee,
            origin_cost=origin_cost,
            slope=slope,
            tail_cost=tail_cost,
            tail_slope=tail_slope,
        )

    if value(origin) >= threshold:
        return origin
    if slope > 0.0:
        candidate = max(origin, origin + math.ceil((threshold - origin_cost) / slope))
        while candidate <= knee and value(candidate) < threshold:
            candidate += 1
        while candidate > origin and value(candidate - 1) >= threshold:
            candidate -= 1
        if candidate <= knee and value(candidate) >= threshold:
            return candidate
    if tail_slope <= 0.0:
        return None
    candidate = max(knee + 1, knee + math.ceil((threshold - tail_cost) / tail_slope))
    if tail_cost >= threshold:
        candidate = knee + 1
    while value(candidate) < threshold:
        candidate += 1
    while candidate > knee + 1 and value(candidate - 1) >= threshold:
        candidate -= 1
    return candidate


def _acceptance(
    points: list[dict],
    *,
    origin: int,
    knee: int,
    origin_cost: float,
    slope: float,
    tail_cost: float,
    tail_slope: float,
    threshold: float,
) -> dict:
    """Return the crossing and whether the applied curve stays inside the measured ranges.

    The measured crossing is the first basis whose mean reaches the threshold in basis order. The
    near points are that basis, the last basis below the threshold before it, and one measured base
    on each side of that span. The curve passes when each near point's prediction lies inside that
    point's measured minimum-to-maximum range and the applied crossing lies above the last measured
    mean below the threshold and at or below the first mean at or above it.
    """
    crossing = _applied_crossing(
        origin=origin,
        knee=knee,
        origin_cost=origin_cost,
        slope=slope,
        tail_cost=tail_cost,
        tail_slope=tail_slope,
        threshold=threshold,
    )
    ordered = sorted(points, key=lambda point: point["basis"])
    above_index = next(
        (index for index, point in enumerate(ordered) if point["mean"] >= threshold), None
    )
    last_below = ordered[above_index - 1] if above_index not in (None, 0) else None
    first_above = ordered[above_index] if above_index is not None else None
    near: list[dict] = []
    if last_below is not None and first_above is not None:
        low = ordered.index(last_below)
        high = ordered.index(first_above)
        near = ordered[max(0, low - 1) : min(len(ordered), high + 2)]
    checks = []
    for point in near:
        prediction = _applied_curve_value(
            point["basis"],
            origin=origin,
            knee=knee,
            origin_cost=origin_cost,
            slope=slope,
            tail_cost=tail_cost,
            tail_slope=tail_slope,
        )
        checks.append(
            {
                "basis": point["basis"],
                "mean": point["mean"],
                "minimum": point["minimum"],
                "maximum": point["maximum"],
                "prediction": prediction,
                "inside_measured_range": point["minimum"] <= prediction <= point["maximum"],
            }
        )
    crossing_inside = (
        crossing is not None
        and last_below is not None
        and first_above is not None
        and last_below["basis"] < crossing <= first_above["basis"]
    )
    return {
        "threshold_seconds": threshold,
        "last_below": (
            None
            if last_below is None
            else {
                "basis": last_below["basis"],
                "mean": last_below["mean"],
                "minimum": last_below["minimum"],
                "maximum": last_below["maximum"],
                "samples": last_below["samples"],
            }
        ),
        "first_above": (
            None
            if first_above is None
            else {
                "basis": first_above["basis"],
                "mean": first_above["mean"],
                "minimum": first_above["minimum"],
                "maximum": first_above["maximum"],
                "samples": first_above["samples"],
            }
        ),
        "crossing_basis": crossing,
        "crossing_inside_measured_span": crossing_inside,
        "near_points": checks,
        "inside_measured_ranges": all(check["inside_measured_range"] for check in checks),
        "passes": bool(
            crossing_inside and checks and all(check["inside_measured_range"] for check in checks)
        ),
    }


def _group_inputs(rows: list[dict], fit_class: str) -> list[dict]:
    """Return one inference-enabled row set per measured basis for one class, or fail loudly."""
    selected = [row for row in rows if row["class"] == fit_class]
    if not selected:
        raise RuntimeError(f"the matrix holds no fit input for {fit_class}")
    missing = [
        row["label"] for row in selected if not isinstance(row.get("include_inferred"), bool)
    ]
    if missing:
        raise RuntimeError(
            "the matrix fit inputs carry no explicit include_inferred field for "
            + ", ".join(sorted(missing))
        )
    inferred = [row for row in selected if row["include_inferred"]]
    if not inferred:
        raise RuntimeError(f"the matrix holds no inference-enabled fit input for {fit_class}")
    by_basis: dict[int, list[dict]] = {}
    for row in inferred:
        by_basis.setdefault(int(row["basis_size"]), []).append(row)
    return [
        {
            "basis": basis,
            "mean": sum(float(row["core_s_mean"]) for row in group) / len(group),
            "minimum": min(float(row["core_s_min"]) for row in group),
            "maximum": max(float(row["core_s_max"]) for row in group),
            "samples": sum(int(row["sample_count"]) for row in group),
            "labels": sorted(row["label"] for row in group),
        }
        for basis, group in sorted(by_basis.items())
    ]


def _fit_curve(rows: list[dict], fit_class: str, *, origin: int, threshold: float) -> dict:
    """Fit one class's curve, searching its knee, and describe its measured spread and residuals."""
    points = _group_inputs(rows, fit_class)
    cost_values = numpy.asarray([point["mean"] for point in points], dtype=numpy.float64)
    (
        (
            knee,
            subset,
            coefficients,
            residual,
            candidates,
            applied,
        ),
        knee_scan,
    ) = _fit_knee(points, origin=origin, threshold=threshold)
    predictions = numpy.asarray(
        [_curve_value(point["basis"], knee=knee, coefficients=coefficients) for point in points]
    )
    errors = predictions - cost_values
    rounded = {name: _rounded(value) for name, value in coefficients.items()}
    rounded_applied = _rounded_applied_values(coefficients, origin=origin, knee=knee)
    rounded_predictions = numpy.asarray(
        [
            _applied_curve_value(point["basis"], origin=origin, knee=knee, **rounded_applied)
            for point in points
        ]
    )
    rounded_errors = rounded_predictions - cost_values
    return {
        "class": fit_class,
        "active_coefficients": list(subset),
        "candidates": candidates,
        "knee_scan": knee_scan,
        "rounded_coefficients": rounded,
        "rounded_applied_values": rounded_applied,
        "rounded_squared_residual": float(numpy.sum(rounded_errors**2)),
        "rounded_maximum_absolute_residual": float(numpy.max(numpy.abs(rounded_errors))),
        "coefficients": coefficients,
        "origin_basis": origin,
        "knee_basis": knee,
        "origin_cost": coefficients["base"] + coefficients["head"] * origin,
        "tail_cost": coefficients["base"] + coefficients["head"] * knee,
        "squared_residual": residual,
        "root_mean_squared_residual": float(numpy.sqrt(residual / len(points))),
        "maximum_absolute_residual": float(numpy.max(numpy.abs(errors))),
        "points": [
            {
                **point,
                "prediction": float(prediction),
                "residual": float(error),
            }
            for point, prediction, error in zip(points, predictions, errors, strict=True)
        ],
        "threshold_seconds": threshold,
        "heavy_basis": _crossing(
            origin=origin, knee=knee, coefficients=coefficients, threshold=threshold
        ),
        "applied_heavy_basis": applied["crossing_basis"],
        "acceptance": applied,
    }


def _config_values() -> tuple[int, int]:
    """Return the recommendation and next-courses origin basis sizes."""
    settings = load_admission_settings()
    return (
        settings.admission_recommendation_origin_basis,
        settings.admission_next_courses_origin_basis,
    )


def _rounded(value: float) -> float:
    """Return one cost or slope at the configuration file's five decimal places."""
    return round(value, 5)


def main(argv: list[str] | None = None) -> int:
    """Fit every admission curve from one matrix result and print the applied values."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    parser.add_argument("--workload", type=Path, default=DEFAULT_WORKLOAD)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--threshold", type=float, default=1.0)
    arguments = parser.parse_args(argv)
    result = load_json(arguments.result)
    if "fit_inputs" not in result:
        raise ValueError("the matrix result holds no fit_inputs")
    recommendation_origin, next_origin = _config_values()
    workload = load_json(arguments.workload)
    if workload["version"] != result["workload"]["version"]:
        raise ValueError("the workload version differs from the matrix result's version")
    fit = {
        fit_class: _fit_curve(
            result["fit_inputs"],
            fit_class,
            origin=(
                recommendation_origin if fit_class.startswith("recommendation") else next_origin
            ),
            threshold=arguments.threshold,
        )
        for fit_class in CLASSES
    }
    search_rows = [row for row in result["fit_inputs"] if row["class"] == "search_inactive"]
    search = {
        "class": "search_inactive",
        "points": [
            {
                "label": row["label"],
                "mean_core_s": float(row["core_s_mean"]),
                "minimum_core_s": float(row["core_s_min"]),
                "maximum_core_s": float(row["core_s_max"]),
                "sample_count": int(row["sample_count"]),
            }
            for row in search_rows
        ],
        "mean_core_s": (
            sum(float(row["core_s_mean"]) for row in search_rows) / len(search_rows)
            if search_rows
            else None
        ),
    }
    graphs = [
        {
            "label": row["label"],
            "elapsed_s_median": float(row["elapsed_s_median"]),
            "core_s_mean": float(row["core_s_mean"]),
            "drawing_elements": row.get("drawing_elements"),
        }
        for row in result["fit_inputs"]
        if row["class"] == "graph"
    ]
    per_class_values = {}
    for fit_class, curve in fit.items():
        active = fit_class.startswith("recommendation")
        prefix = "ADMISSION_RECOMMENDATION_" if active else "ADMISSION_NEXT_COURSES_"
        scope = "ACTIVE_" if fit_class.endswith("_active") else "INACTIVE_"
        applied_curve = curve["rounded_applied_values"]
        per_class_values[fit_class] = {
            f"{prefix}{scope}KNEE_BASIS": curve["knee_basis"],
            f"{prefix}{scope}ORIGIN_COST": applied_curve["origin_cost"],
            f"{prefix}{scope}SLOPE": applied_curve["slope"],
            f"{prefix}{scope}TAIL_COST": applied_curve["tail_cost"],
            f"{prefix}{scope}TAIL_SLOPE": applied_curve["tail_slope"],
        }
    accepted_classes = [
        fit_class for fit_class, curve in fit.items() if curve["acceptance"]["passes"]
    ]
    rejected_classes = [
        fit_class for fit_class, curve in fit.items() if not curve["acceptance"]["passes"]
    ]
    fitted_values = {
        key: value for values in per_class_values.values() for key, value in values.items()
    }
    applied_values = {
        key: value
        for fit_class in accepted_classes
        for key, value in per_class_values[fit_class].items()
    }
    fitted_knees = {fit_class: curve["knee_basis"] for fit_class, curve in fit.items()}
    applied_knees = {fit_class: fitted_knees[fit_class] for fit_class in accepted_classes}
    fitted_heavy_basis = {
        fit_class: curve["applied_heavy_basis"] for fit_class, curve in fit.items()
    }
    applied_heavy_basis = {
        fit_class: fitted_heavy_basis[fit_class] for fit_class in accepted_classes
    }
    acceptance = {fit_class: curve["acceptance"] for fit_class, curve in fit.items()}
    document = {
        "result": str(arguments.result),
        "workload_version": result["workload"]["version"],
        "threshold_seconds": arguments.threshold,
        "fit": fit,
        "search_inactive": search,
        "graphs": graphs,
        "fitted_values": fitted_values,
        "applied_values": applied_values,
        "fitted_knees": fitted_knees,
        "applied_knees": applied_knees,
        "fitted_heavy_basis": fitted_heavy_basis,
        "applied_heavy_basis": applied_heavy_basis,
        "accepted_classes": accepted_classes,
        "rejected_classes": rejected_classes,
        "acceptance": acceptance,
        "acceptance_all": not rejected_classes,
    }
    if arguments.output is not None:
        write_json(arguments.output, document)
    print(json.dumps(document, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
