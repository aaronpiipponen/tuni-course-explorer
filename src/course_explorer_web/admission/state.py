"""The front router's in-memory admission state: the load score meter, the user counters and the heavy queue.

The score combines the whole host's CPU utilisation with the light and heavy activity counted in
the same window:

    score = cpu_weight * cpu_utilisation
          + light_weight * light_requests_admitted_in_window
          + heavy_weight * heavy_requests_admitted_or_running_in_window

The score maps onto a normalized load position between the headroom and saturation lines, and a
saturation latch holds the position at 1 until the score falls below the release line. Every
policy read consumes that position.

One event loop mutates the state, so no lock guards the counters and the client. The heavy queue
mutations and its waiters share one ``asyncio.Condition``, so every waiter re-checks its predicate
when a ticket joins, starts or is released.
"""

from __future__ import annotations

import asyncio
import secrets
import time
from collections import deque
from dataclasses import dataclass, field

from course_explorer.config import AdmissionSettings
from course_explorer_web.admission import policy
from course_explorer_web.admission.classify import Classification


class AdmissionRefused(Exception):
    """Raised when admission refuses one request with ``429``."""


@dataclass
class _Identity:
    """One anonymous cookie's light bucket, light tickets and heavy bucket."""

    tokens: float
    at_milliseconds: float
    heavy_tokens: float
    heavy_at_milliseconds: float
    running: set[str] = field(default_factory=set)
    last_used: float = 0.0


class AdmissionState:
    """Hold one process's admission counters, its heavy queue and its graph costs.

    ``cores`` is the host's core count that the CPU utilisation divides by. A graph cost belongs to
    the one dataset identity it was measured under. Nothing here is persisted or shared between
    processes.

    The light and heavy buckets advance on ``time.monotonic()`` milliseconds, while the identity
    lifetime and the load window's sample index use wall-clock seconds. The activity timestamps of
    the score use monotonic seconds.
    """

    def __init__(self, settings: AdmissionSettings, cores: int) -> None:
        self._settings = settings
        self._cores = cores
        self.load_position = 0.0
        self.cpu_utilisation = 0.0
        self.score = 0.0
        self.light_window = 0
        self.heavy_window = 0
        self.saturated = False
        self._previous_busy: float | None = None
        self._busy: dict[int, float] = {}
        self._light_admitted: deque[float] = deque()
        self._heavy_started: deque[float] = deque()
        self._heavy_running: dict[str, float] = {}
        self._identities: dict[str, _Identity] = {}
        self._waiting: list[str] = []
        self._running: set[str] = set()
        self._tickets: dict[str, str] = {}
        self._condition = asyncio.Condition()
        self._graph_identity: str | None = None
        self._graph_costs: dict[str, float] = {}

    @property
    def running_heavy(self) -> int:
        """Return the heavy requests that hold a global slot."""
        return len(self._running)

    @property
    def waiting_heavy(self) -> int:
        """Return the heavy tickets that wait for a global slot."""
        return len(self._waiting)

    def sample(self, busy_seconds: float, second: int) -> float:
        """Add one host busy interval and return the updated normalized load position.

        The interval is the growth of the host's cumulative busy time since the previous sample, so
        a repeated or decreasing reading stores zero. The first sample stores zero. Intervals older
        than ``ADMISSION_LOAD_WINDOW_SECONDS`` leave the window, and the CPU utilisation divides the
        window's core-seconds by the window length times the core count.

        The activity counts cover the same window. A light admission or a heavy start stays counted
        until its monotonic timestamp is older than the window, and a running heavy request whose
        start has left the window stays counted once until it is released. The score and the
        position it maps to refresh here, on the once-a-second sample, rather than on admission.
        """
        interval = (
            0.0 if self._previous_busy is None else max(0.0, busy_seconds - self._previous_busy)
        )
        self._previous_busy = busy_seconds
        self._busy[second] = interval
        window = self._settings.admission_load_window_seconds
        oldest = second - window
        for key in [key for key in self._busy if key <= oldest]:
            del self._busy[key]
        self.cpu_utilisation = sum(self._busy.values()) / (window * self._cores)
        self._refresh_activity(window)
        self.score = (
            self._settings.admission_score_cpu_weight * self.cpu_utilisation
            + self._settings.admission_score_light_weight * self.light_window
            + self._settings.admission_score_heavy_weight * self.heavy_window
        )
        self._apply_score()
        return self.load_position

    def reset_meter(self) -> None:
        """Clear the meter baseline and treat the site as unloaded after an unreadable counter.

        The CPU baseline, the CPU buckets and every derived value return to their unloaded state.
        The activity timestamps and the running tickets stay, so the next good sample counts the
        activity already admitted and stores a fresh CPU baseline instead of the outage.
        """
        self._previous_busy = None
        self._busy = {}
        self.cpu_utilisation = 0.0
        self.score = 0.0
        self.light_window = 0
        self.heavy_window = 0
        self.saturated = False
        self.load_position = 0.0

    def admit_light(self, cookie: str) -> str:
        """Take one light token and one concurrency ticket, or raise ``AdmissionRefused``.

        The bucket refills at the current light rate up to the configured burst, and the identity
        admits no more light tickets than the current light concurrency. The returned ticket is
        opaque and is released with ``release_light``. An admitted request counts as light activity
        for the score window.
        """
        identity = self._identity(cookie)
        now = time.monotonic() * 1000.0
        balance = policy.light_balance(
            identity.tokens, now - identity.at_milliseconds, self.load_position, self._settings
        )
        limit = policy.light_concurrency(self.load_position, self._settings)
        if len(identity.running) >= limit or balance < 1.0:
            raise AdmissionRefused
        identity.tokens = balance - 1.0
        identity.at_milliseconds = now
        ticket = secrets.token_hex(8)
        identity.running.add(ticket)
        identity.last_used = time.time()
        self._light_admitted.append(time.monotonic())
        return ticket

    def release_light(self, cookie: str, ticket: str) -> None:
        """Drop one light concurrency ticket and the identity once it is stale and idle."""
        identity = self._identities.get(cookie)
        if identity is None:
            return
        identity.running.discard(ticket)
        self._drop_if_stale(cookie, identity)

    async def admit_heavy(self, cookie: str, classification: Classification) -> str:
        """Charge one heavy request and take its global slot, or raise ``AdmissionRefused``.

        The charge is the classification's cost, or the whole current budget when the cost is
        larger. A short balance refuses at once. A ticket waits for a slot without a time limit,
        keeps its place when the queue cap drops, and refunds its charge when the queue is at its
        cap at the moment it joins. The returned ticket is released with ``release_heavy``, and a
        request that takes its slot counts as heavy activity for the score window.
        """
        identity = self._identity(cookie)
        budget = policy.heavy_budget(self.load_position, self._settings)
        charge = min(classification.cost, budget)
        if not self._charge_heavy(identity, budget, charge):
            raise AdmissionRefused
        identity.last_used = time.time()
        ticket = secrets.token_hex(8)
        try:
            await self._acquire_slot(ticket, cookie)
        except AdmissionRefused:
            self._charge_heavy(
                identity,
                policy.heavy_budget(self.load_position, self._settings),
                -charge,
            )
            raise
        started = time.monotonic()
        self._heavy_started.append(started)
        self._heavy_running[ticket] = started
        return ticket

    async def release_heavy(self, ticket: str) -> None:
        """Drop one heavy ticket from the running set and wake the waiting tickets."""
        async with self._condition:
            self._running.discard(ticket)
            self._heavy_running.pop(ticket, None)
            self._remove_ticket(ticket)
            self._condition.notify_all()

    def graph_cost(self, dataset_identity: str, field: str) -> float | None:
        """Return one cached graph cost for the current dataset identity, or ``None``."""
        if dataset_identity != self._graph_identity:
            return None
        return self._graph_costs.get(field)

    def record_graph_cost(self, dataset_identity: str, field: str, seconds: float) -> None:
        """Store one built graph's cost, replacing the costs of a different dataset identity."""
        if dataset_identity != self._graph_identity:
            self._graph_identity = dataset_identity
            self._graph_costs = {}
        self._graph_costs[field] = seconds

    def expire(self, second: int) -> None:
        """Drop every identity that has been idle for its lifetime and holds no ticket."""
        for cookie in list(self._identities):
            self._drop_if_stale(cookie, self._identities[cookie], second=second)

    def _refresh_activity(self, window: int) -> None:
        """Expire the activity older than the window and count what stays inside it.

        A timestamp exactly on the cutoff stays in the window. A heavy request that is still
        running counts once, either through its recent start or, once that start has aged out,
        through its own older start time.
        """
        cutoff = time.monotonic() - window
        while self._light_admitted and self._light_admitted[0] < cutoff:
            self._light_admitted.popleft()
        while self._heavy_started and self._heavy_started[0] < cutoff:
            self._heavy_started.popleft()
        self.light_window = len(self._light_admitted)
        older_running = sum(1 for start in self._heavy_running.values() if start < cutoff)
        self.heavy_window = len(self._heavy_started) + older_running

    def _apply_score(self) -> None:
        """Enter or leave saturation and map the score onto the normalized load position."""
        headroom = self._settings.admission_score_headroom
        saturation = self._settings.admission_score_saturation
        if self.saturated:
            if self.score < self._settings.admission_score_release:
                self.saturated = False
        elif self.score >= saturation:
            self.saturated = True
        if self.saturated:
            self.load_position = 1.0
            return
        self.load_position = min(1.0, max(0.0, (self.score - headroom) / (saturation - headroom)))

    def _identity(self, cookie: str) -> _Identity:
        identity = self._identities.get(cookie)
        if identity is None:
            now = time.monotonic() * 1000.0
            identity = _Identity(
                tokens=float(self._settings.admission_light_burst),
                at_milliseconds=now,
                heavy_tokens=max(
                    self._settings.admission_heavy_budget_core_seconds,
                    self._settings.admission_heavy_budget_saturated_core_seconds,
                ),
                heavy_at_milliseconds=now,
                last_used=time.time(),
            )
            self._identities[cookie] = identity
        return identity

    def _charge_heavy(self, identity: _Identity, budget: float, charge: float) -> bool:
        """Take one heavy charge from one identity's bucket, or return ``False``.

        The bucket holds at most the current budget and refills at that budget over one configured
        window. A negative charge refunds and never exceeds the capacity.
        """
        now = time.monotonic() * 1000.0
        balance = policy.heavy_balance(
            identity.heavy_tokens,
            now - identity.heavy_at_milliseconds,
            budget,
            self._settings,
        )
        if balance < charge:
            return False
        identity.heavy_tokens = min(budget, balance - charge)
        identity.heavy_at_milliseconds = now
        return True

    async def _acquire_slot(self, ticket: str, cookie: str) -> None:
        """Wait in the first-in-first-out queue until this ticket takes a free slot.

        A ticket that is already queued keeps its place, so the one refusal is a queue at its cap
        when the ticket joins.
        """
        async with self._condition:
            if len(self._waiting) >= policy.heavy_queue_limit(self.load_position, self._settings):
                raise AdmissionRefused
            self._waiting.append(ticket)
            self._add_ticket(ticket, cookie)
            self._condition.notify_all()
            try:
                while True:
                    slots = policy.heavy_slots(self.load_position, self._settings)
                    if self._waiting[0] == ticket and len(self._running) < slots:
                        self._waiting.pop(0)
                        self._running.add(ticket)
                        self._condition.notify_all()
                        return
                    await self._condition.wait()
            except BaseException:
                if ticket in self._waiting:
                    self._waiting.remove(ticket)
                self._running.discard(ticket)
                self._remove_ticket(ticket)
                self._condition.notify_all()
                raise

    def _add_ticket(self, ticket: str, cookie: str) -> None:
        self._tickets[ticket] = cookie

    def _remove_ticket(self, ticket: str) -> None:
        self._tickets.pop(ticket, None)

    def _drop_if_stale(
        self, cookie: str, identity: _Identity, *, second: int | None = None
    ) -> None:
        now = time.time() if second is None else second
        if identity.running or cookie in self._tickets.values():
            return
        if now - identity.last_used >= self._settings.admission_identity_ttl_seconds:
            self._identities.pop(cookie, None)
