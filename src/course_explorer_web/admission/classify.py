"""Classify one API request as free, light or heavy and estimate a heavy request's core-seconds."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from course_explorer.config import AdmissionSettings
from course_explorer_web.serving import ACTIVE_ONLY_DEFAULT, INCLUDE_INACTIVE_DEFAULT, Route


class AdmissionClass(StrEnum):
    """The admission class of one request."""

    FREE = "free"
    LIGHT = "light"
    HEAVY = "heavy"


@dataclass(frozen=True)
class Classification:
    """One request's class and, for a heavy request, its estimated total core-seconds."""

    admission_class: AdmissionClass
    cost: float


_LIGHT = Classification(AdmissionClass.LIGHT, 0.0)
_FREE = Classification(AdmissionClass.FREE, 0.0)


def _identifiers(value: object) -> set[str]:
    """Return the nonblank identifier strings of a list value, or an empty set for any other value."""
    if not isinstance(value, list):
        return set()
    return {item.strip() for item in value if isinstance(item, str) and item.strip()}


def basis_size(body: Mapping[str, object]) -> int:
    """Return the number of distinct nonblank identifiers in the request's chosen basis list.

    A ``selected`` basis uses the selected list, or the completed list when the selected list is
    empty. Every other basis uses the completed list.
    """
    selected = _identifiers(body.get("selected_courses"))
    if body.get("basis") == "selected" and selected:
        return len(selected)
    return len(_identifiers(body.get("completed_courses")))


def active_only_from_body(body: Mapping[str, object]) -> bool:
    """Return whether the request reads active courses only.

    An absent flag takes the request model's active-only default, so only an explicit ``false``
    selects the inactive scope.
    """
    return body.get("active_only", ACTIVE_ONLY_DEFAULT) is not False


@dataclass(frozen=True)
class _Curve:
    """One scope's piecewise linear cost curve: its origin, its slope, its knee and its tail."""

    origin_basis: int
    origin_cost: float
    slope: float
    knee_basis: int
    tail_cost: float
    tail_slope: float


def _curve_cost(basis: int, *, active_only: bool, active: _Curve, inactive: _Curve) -> float:
    """Return the request scope's curve value in core-seconds at the given basis size."""
    curve = active if active_only else inactive
    if basis <= curve.knee_basis:
        return curve.origin_cost + curve.slope * (basis - curve.origin_basis)
    return curve.tail_cost + curve.tail_slope * (basis - curve.knee_basis)


def _heavy_basis(*, active_only: bool, active: int, inactive: int) -> int:
    """Return the basis size from which the request scope is heavy."""
    return active if active_only else inactive


def recommendation_cost(basis: int, settings: AdmissionSettings, *, active_only: bool) -> float:
    """Return the estimated total core-seconds of one recommendation read.

    The two scopes carry separate curves, because a read that includes inactive courses prices
    every active course as well.
    """
    return _curve_cost(
        basis,
        active_only=active_only,
        active=_Curve(
            settings.admission_recommendation_origin_basis,
            settings.admission_recommendation_active_origin_cost,
            settings.admission_recommendation_active_slope,
            settings.admission_recommendation_knee_basis,
            settings.admission_recommendation_active_tail_cost,
            settings.admission_recommendation_active_tail_slope,
        ),
        inactive=_Curve(
            settings.admission_recommendation_origin_basis,
            settings.admission_recommendation_inactive_origin_cost,
            settings.admission_recommendation_inactive_slope,
            settings.admission_recommendation_knee_basis,
            settings.admission_recommendation_inactive_tail_cost,
            settings.admission_recommendation_inactive_tail_slope,
        ),
    )


def next_courses_cost(basis: int, settings: AdmissionSettings, *, active_only: bool) -> float:
    """Return the estimated total core-seconds of one next-courses read.

    The two scopes carry separate curves, with the same shape as the recommendation curves.
    """
    return _curve_cost(
        basis,
        active_only=active_only,
        active=_Curve(
            settings.admission_next_courses_origin_basis,
            settings.admission_next_courses_active_origin_cost,
            settings.admission_next_courses_active_slope,
            settings.admission_next_courses_knee_basis,
            settings.admission_next_courses_active_tail_cost,
            settings.admission_next_courses_active_tail_slope,
        ),
        inactive=_Curve(
            settings.admission_next_courses_origin_basis,
            settings.admission_next_courses_inactive_origin_cost,
            settings.admission_next_courses_inactive_slope,
            settings.admission_next_courses_knee_basis,
            settings.admission_next_courses_inactive_tail_cost,
            settings.admission_next_courses_inactive_tail_slope,
        ),
    )


def classify(
    route: Route,
    body: Mapping[str, object],
    settings: AdmissionSettings,
    *,
    graph_cost: float | None = None,
) -> Classification:
    """Return the class and cost of one request from its route, body and cached graph cost.

    Every cost is total server core-seconds. A prerequisite graph is heavy only when its cached
    elapsed cost reaches the configured heavy threshold. Every other route is classified from the
    request shape alone.
    """
    if route in (Route.FEATURES, Route.COURSE_SUMMARIES):
        return _FREE
    if route is Route.SEARCH:
        if body.get("include_inactive", INCLUDE_INACTIVE_DEFAULT) is not False:
            return Classification(
                AdmissionClass.HEAVY, settings.admission_search_inactive_cost_core_seconds
            )
        return _LIGHT
    if route is Route.RECOMMENDATIONS:
        basis = basis_size(body)
        active_only = active_only_from_body(body)
        heavy_basis = _heavy_basis(
            active_only=active_only,
            active=settings.admission_recommendation_active_heavy_basis,
            inactive=settings.admission_recommendation_inactive_heavy_basis,
        )
        if basis >= heavy_basis:
            return Classification(
                AdmissionClass.HEAVY,
                recommendation_cost(basis, settings, active_only=active_only),
            )
        return _LIGHT
    if route is Route.NEXT_COURSES:
        basis = basis_size(body)
        active_only = active_only_from_body(body)
        heavy_basis = _heavy_basis(
            active_only=active_only,
            active=settings.admission_next_courses_active_heavy_basis,
            inactive=settings.admission_next_courses_inactive_heavy_basis,
        )
        if basis >= heavy_basis:
            return Classification(
                AdmissionClass.HEAVY, next_courses_cost(basis, settings, active_only=active_only)
            )
        return _LIGHT
    if route is Route.PREREQUISITES:
        if graph_cost is not None and graph_cost >= settings.admission_graph_heavy_seconds:
            return Classification(AdmissionClass.HEAVY, graph_cost)
        return _LIGHT
    return _LIGHT
