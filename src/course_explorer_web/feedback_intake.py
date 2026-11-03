"""The exact-site check and the submission allowance of the front router's feedback paths.

The module owns the two fixed feedback paths, the exact-site write boundary and one router's
transient rolling-hour submission allowance. The allowance counts admitted attempts, so a refused
body or a failed write spends its charge. It holds no identity history beyond the current window and
no persisted counter, and it collects no address, fingerprint or profile.
"""

from __future__ import annotations

import math
import time
from collections import deque
from collections.abc import Callable
from urllib.parse import urlsplit

from starlette.types import Scope

from course_explorer.config import FeedbackIntakeSettings
from course_explorer.http_headers import header_values
from course_explorer_web.request_body import RequestRefused

# The two fixed feedback HTTP paths, shared by the front router, the worker route and usage labels.
FEEDBACK_DEFINITION_PATH = "/api/feedback/definition"
FEEDBACK_SUBMISSION_PATH = "/api/feedback"

# The length of the rolling window the hourly allowances count over.
_WINDOW_SECONDS = 3600


def require_feedback_site(scope: Scope, settings: FeedbackIntakeSettings) -> None:
    """Refuse a submission unless its Host and Origin name the configured feedback site exactly.

    The request must carry exactly one Host whose value is the configured origin's netloc and
    exactly one Origin whose value is the configured origin string. The origin is derived from the
    site's one app address. A missing, repeated, ``null`` or foreign value is refused with 403.
    Forwarded host and protocol headers are ignored, and the transport scheme is not compared
    because the proxy reaches the router over plain HTTP.
    """
    origin = settings.web_app_origin
    netloc = urlsplit(origin).netloc
    hosts = header_values(scope.get("headers", ()), b"host")
    if len(hosts) != 1 or hosts[0].decode("latin-1") != netloc:
        raise RequestRefused(403)
    origins = header_values(scope.get("headers", ()), b"origin")
    if len(origins) != 1 or origins[0].decode("latin-1") != origin:
        raise RequestRefused(403)


class FeedbackIntake:
    """One front router's transient rolling-hour allowance for feedback submissions.

    The deque holds one ``(monotonic timestamp, identity)`` entry per admitted attempt. Both the
    per-identity and the whole-site counts come from it, so no second counter exists. A refusal
    leaves the deque unchanged, and a replaced router starts with an empty allowance.
    """

    def __init__(
        self,
        settings: FeedbackIntakeSettings,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._browser_limit = settings.feedback_browser_submissions_per_hour
        self._site_limit = settings.feedback_site_submissions_per_hour
        self._clock = clock
        self._events: deque[tuple[float, str]] = deque()

    def admit(self, identity: str) -> None:
        """Charge one submission attempt to its browser and to the site, or raise 429.

        The check and the append run in one turn with no suspension between them. A refusal carries
        the greater ceiling of the two waits until enough relevant oldest attempts leave the window.
        """
        now = self._clock()
        cutoff = now - _WINDOW_SECONDS
        while self._events and self._events[0][0] <= cutoff:
            self._events.popleft()
        browser_timestamps = [
            timestamp for timestamp, event_identity in self._events if event_identity == identity
        ]
        waits: list[float] = []
        if len(browser_timestamps) >= self._browser_limit:
            waits.append(
                browser_timestamps[len(browser_timestamps) - self._browser_limit]
                + _WINDOW_SECONDS
                - now
            )
        if len(self._events) >= self._site_limit:
            waits.append(
                self._events[len(self._events) - self._site_limit][0] + _WINDOW_SECONDS - now
            )
        if waits:
            raise RequestRefused(429, retry_after_seconds=max(1, math.ceil(max(waits))))
        self._events.append((now, identity))
