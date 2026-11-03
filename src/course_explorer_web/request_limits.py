"""The serving request-input bounds and the request-model check that enforces them.

The bounds come from the supervisor's preloaded web settings, so one validated configuration owns
every count and length. A request that crosses a bound fails validation at the route's trust
boundary before any command runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Self

from pydantic import BaseModel, ConfigDict, model_validator

from course_explorer_web.serving_cache import preloaded_serving_settings


@dataclass(frozen=True)
class RequestLimits:
    """The configured maximum list length, identifier length and query length."""

    max_course_items: int
    max_identifier_length: int
    max_query_length: int


def request_limits() -> RequestLimits:
    """Return the validated request-input bounds of the serving site."""
    web = preloaded_serving_settings().web
    return RequestLimits(
        max_course_items=web.web_request_max_course_items,
        max_identifier_length=web.web_request_max_identifier_length,
        max_query_length=web.web_request_max_query_length,
    )


class BoundedRequest(BaseModel):
    """A closed feature request whose inputs obey the configured bounds."""

    model_config = ConfigDict(extra="forbid")

    _course_list_fields: ClassVar[tuple[str, ...]] = ()
    _identifier_fields: ClassVar[tuple[str, ...]] = ()
    _identifier_map_fields: ClassVar[tuple[str, ...]] = ()
    _query_fields: ClassVar[tuple[str, ...]] = ()

    @model_validator(mode="after")
    def require_inputs_within_bounds(self) -> Self:
        """Reject a request that carries more or longer inputs than the bounds allow."""
        limits = request_limits()
        for name in self._course_list_fields:
            _require_list(getattr(self, name), limits)
        for name in self._identifier_fields:
            _require_identifier(getattr(self, name), limits)
        for name in self._identifier_map_fields:
            _require_map(getattr(self, name), limits)
        for name in self._query_fields:
            _require_query(getattr(self, name), limits)
        return self


def _require_list(values: tuple[str, ...], limits: RequestLimits) -> None:
    if len(values) > limits.max_course_items:
        raise ValueError(f"a course list holds at most {limits.max_course_items} identities")
    for value in values:
        _require_identifier(value, limits)


def _require_identifier(value: str, limits: RequestLimits) -> None:
    if len(value) > limits.max_identifier_length:
        raise ValueError(f"an identity holds at most {limits.max_identifier_length} characters")


def _require_map(values: dict[str, str], limits: RequestLimits) -> None:
    if len(values) > limits.max_course_items:
        raise ValueError(f"a selection map holds at most {limits.max_course_items} entries")
    for key, value in values.items():
        _require_identifier(key, limits)
        _require_identifier(value, limits)


def _require_query(value: str, limits: RequestLimits) -> None:
    if len(value) > limits.max_query_length:
        raise ValueError(f"a query holds at most {limits.max_query_length} characters")
