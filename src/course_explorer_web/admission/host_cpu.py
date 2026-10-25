"""Read the whole host's busy CPU time and core count for the admission load meter."""

from __future__ import annotations

import os


def busy_cpu_seconds() -> float:
    """Return the host's busy CPU time in core-seconds since boot.

    The first eight numeric fields of ``/proc/stat``'s first line hold user, nice, system, idle,
    iowait, irq, softirq and steal time in clock ticks. The two guest fields after them are already
    counted in user and nice, so they stay out of the total. An unreadable stat file raises
    ``OSError``.
    """
    with open("/proc/stat", encoding="ascii") as stat:
        fields = stat.readline().split()
    ticks = sum(int(value) for value in fields[1:9])
    idle = int(fields[4]) + int(fields[5])
    return (ticks - idle) / os.sysconf("SC_CLK_TCK")


def core_count() -> int:
    """Return the host's core count, raising ``RuntimeError`` when the host reports none."""
    count = os.cpu_count()
    if count is None:
        raise RuntimeError("the host core count is unavailable")
    return count
