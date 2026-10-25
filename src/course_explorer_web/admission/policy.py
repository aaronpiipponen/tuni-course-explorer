"""The admission policy's pure load-regime, rate, budget, queue and slot arithmetic.

The regime, the light limits, the heavy budget, the queue cap and the slots read the normalized
load position the meter produces: the light limits scale by one factor that falls from 1 at the
headroom position to the configured floor at saturation, and the heavy budget interpolates its own
two core-second values between the same bounds. The two balance helpers own the per-user bucket
refill.
"""

from __future__ import annotations

import math
from enum import StrEnum

from course_explorer.config import AdmissionSettings


class Regime(StrEnum):
    """The load regime one load position falls in."""

    HEADROOM = "headroom"
    MIDDLE = "middle"
    SATURATED = "saturated"


def regime(load_position: float, settings: AdmissionSettings) -> Regime:
    """Return the regime for one normalized load position."""
    if load_position <= 0.0:
        return Regime.HEADROOM
    if load_position >= 1.0:
        return Regime.SATURATED
    return Regime.MIDDLE


def light_load_factor(load_position: float, settings: AdmissionSettings) -> float:
    """Return the fraction of the headroom light limits one load position permits.

    The factor is 1 at the headroom position and the configured floor at saturation. Between them
    it falls linearly.
    """
    return 1.0 - (1.0 - settings.admission_light_load_floor) * load_position


def light_rate_per_millisecond(load_position: float, settings: AdmissionSettings) -> float:
    """Return the per-user light token refill rate in tokens per millisecond."""
    return (
        settings.admission_light_operations_per_minute
        * light_load_factor(load_position, settings)
        / 60000
    )


def light_concurrency(load_position: float, settings: AdmissionSettings) -> int:
    """Return the per-user light operations allowed at once, at least one."""
    return max(
        1, int(settings.admission_light_concurrency * light_load_factor(load_position, settings))
    )


def heavy_budget(load_position: float, settings: AdmissionSettings) -> float:
    """Return one user's heavy core-second budget for one window.

    The budget is the headroom value at the headroom position and the saturated value at
    saturation. Between them it interpolates linearly.
    """
    difference = (
        settings.admission_heavy_budget_saturated_core_seconds
        - settings.admission_heavy_budget_core_seconds
    )
    return settings.admission_heavy_budget_core_seconds + difference * load_position


def heavy_queue_limit(load_position: float, settings: AdmissionSettings) -> int:
    """Return the waiting heavy tickets the current regime admits."""
    current = regime(load_position, settings)
    if current is Regime.SATURATED:
        return settings.admission_heavy_queue_saturated_limit
    if current is Regime.MIDDLE:
        return settings.admission_heavy_queue_middle_limit
    return settings.admission_heavy_queue_headroom_limit


def heavy_slots(load_position: float, settings: AdmissionSettings) -> int:
    """Return the global heavy slots, at least one and at most one fewer than the web workers."""
    slots = math.ceil(
        settings.admission_heavy_slots - (settings.admission_heavy_slots - 1) * load_position
    )
    return max(1, min(slots, settings.web_workers - 1))


def light_balance(
    tokens: float,
    elapsed_milliseconds: float,
    load_position: float,
    settings: AdmissionSettings,
) -> float:
    """Return one light bucket's balance after its refill, at most the configured burst."""
    rate = light_rate_per_millisecond(load_position, settings)
    return min(float(settings.admission_light_burst), tokens + elapsed_milliseconds * rate)


def heavy_balance(
    tokens: float, elapsed_milliseconds: float, budget: float, settings: AdmissionSettings
) -> float:
    """Return one heavy bucket's balance after its refill, at most the passed budget."""
    rate = budget / (settings.admission_window_seconds * 1000)
    return min(budget, tokens + elapsed_milliseconds * rate)
