"""Server-side session, credential-check, failed-attempt and durable-lock owner of the admin backend.

One process holds one ``AdminSecurity``. It owns the in-memory session dictionary, the bounded
creation times of its fresh anonymous sessions, the persisted failed-login count, the durable lock
file and the sole command log. Sessions and the anonymous-session budget live in memory alone, and the
count, the lock and the command log live on disk.

The lock is the file ``data/admin-web/lock`` itself. While any entry exists at that path, the whole
site is refused. Removing that file clears the lock. Three consecutive failed logins create it, and
a successful login resets the count.

A fresh anonymous session consumes one slot of the server-wide budget shared by every client of the
process. A live anonymous or authenticated session is reused without consuming a slot.
"""

from __future__ import annotations

import math
import os
import secrets
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from pydantic import BaseModel, ConfigDict, SecretStr

from course_explorer.administration import (
    administrative_json,
    atomic_write_private_text,
    load_private_model,
    utc_now,
)
from course_explorer.config import AdminWebSettings
from course_explorer_admin.credentials import (
    ADMIN_WEB_STATE_ROOT,
    read_admin_credential,
    verify_admin_password,
)
from course_explorer_admin_web.command_log import CommandLog, CommandLogEntry

# The failed-attempt limit and the lock path are code constants.
FAILED_LOGIN_LIMIT = 3
LOCK_FILENAME = "lock"
FAILED_LOGINS_FILENAME = "failed-logins"

# The one site-scoped session cookie. Its name carries the `__Host-` prefix, so a browser sends it
# only to this exact host over a secure connection and without a Domain attribute.
SESSION_COOKIE_NAME = "__Host-course-explorer-admin"

_COOKIE_TOKEN_BYTES = 32


class FailedLogins(BaseModel):
    """The persisted count of consecutive failed logins on this site."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    count: int


@dataclass(frozen=True)
class SessionGrant:
    """One server-side session: its tokens, its authentication state and its lifetime bounds.

    The grant belongs to this process alone. The session report carries the authenticated state, the
    CSRF token and the username. The process holds the session token in memory.
    """

    token: str
    csrf_token: str
    authenticated: bool
    username: str | None
    created_at: datetime
    last_seen: datetime
    credential_identity: str | None


class AnonymousSessionRateLimited(Exception):
    """The refusal of one fresh anonymous session grant.

    ``retry_after_seconds`` is the positive whole-second wait until the oldest counted creation leaves
    the configured window and the budget admits a fresh grant.
    """

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("fresh anonymous session rate limit reached")
        self.retry_after_seconds = retry_after_seconds


class AdminSecurity:
    """Own the sessions, the failed-attempt count, the lock and the command log of one admin site.

    One re-entrant lock serializes every session, anonymous-grant budget, count and lock transition,
    so two concurrent login attempts cannot both pass the failed-attempt limit and two concurrent
    bootstrap requests cannot both exceed the fresh-session budget. Blocking state reads and writes
    run under the caller's own thread.
    """

    def __init__(
        self, root: Path, settings: AdminWebSettings, *, clock: Callable[[], datetime] = utc_now
    ) -> None:
        self._root = root
        self._settings = settings
        self._clock = clock
        self._lock = threading.RLock()
        self._sessions: dict[str, SessionGrant] = {}
        self._anonymous_grant_times: deque[datetime] = deque(
            maxlen=settings.admin_web_anonymous_session_limit
        )
        self.log = CommandLog(root, limit=settings.admin_web_command_log_limit)

    @property
    def state_directory(self) -> Path:
        """Return the administration state directory, creating nothing."""
        return self._root / ADMIN_WEB_STATE_ROOT

    def is_locked(self) -> bool:
        """Report whether the site's lock entry exists, whatever its type or content.

        The check reads the directory entry alone and never parses, truncates or creates it. A
        dangling symlink and a nonempty file lock the site exactly as an empty regular file does.
        """
        try:
            os.lstat(self.state_directory / LOCK_FILENAME)
        except FileNotFoundError:
            return False
        return True

    def bootstrap(self, cookie: str | None) -> SessionGrant:
        """Reuse the request's validated live session or create an anonymous one.

        An anonymous session exists to protect a login with a CSRF token and grants no administration
        access. A recreated application starts with no session, because the sessions live in memory.
        The presented cookie is resolved through the one credential-validating read, so a session
        whose credential identity changed is replaced by fresh anonymous state.

        A live session is returned without consuming the budget. A fresh grant consumes one slot of
        the server-wide budget, and a spent budget raises ``AnonymousSessionRateLimited`` before any
        grant is created or touched.
        """
        with self._lock:
            existing = self.resolve(cookie)
            if existing is not None:
                return existing
            self._require_anonymous_budget(self._clock())
            grant = self._create_session(
                authenticated=False, username=None, credential_identity=None
            )
            self._anonymous_grant_times.append(grant.created_at)
            return grant

    def resolve(self, cookie: str | None) -> SessionGrant | None:
        """Return the live session of one cookie, or ``None`` for an absent or expired one.

        Expired entries are pruned first, and an authenticated session is checked against the current
        stored credential identity, so replacing the password invalidates that session on its next
        request. A returned grant keeps its own last-seen time, because the idle clock of an admitted
        request is refreshed by ``touch`` alone.
        """
        with self._lock:
            self._prune_expired()
            grant = self._sessions.get(cookie or "")
            if grant is None:
                return None
            if grant.authenticated and grant.credential_identity != self._credential_identity():
                self._sessions.pop(grant.token, None)
                return None
            return grant

    def touch(self, cookie: str) -> SessionGrant | None:
        """Refresh the idle clock of one admitted session, or report an absent one as ``None``.

        This is the post-admission mutation rather than another credential check, so it looks up the
        token alone. The refreshed entry replaces the stored one, so a token revoked before this call
        returns ``None`` instead of being inserted again.
        """
        with self._lock:
            grant = self._sessions.get(cookie)
            if grant is None:
                return None
            return self._replace_last_seen(grant)

    def login(self, cookie: str, *, username: str, password: SecretStr) -> SessionGrant | None:
        """Verify one credential attempt and return a fresh authenticated session on success.

        A username mismatch, a password mismatch and a locked site each return ``None`` after
        recording the outcome they own: a failed attempt logs ``failed-login``, and the third
        consecutive failure creates the durable lock and logs the ``lock`` event. A successful
        verification resets the persisted count, logs ``login``, drops the presented anonymous or
        old entry and issues fresh tokens. Malformed credential state raises instead, because it is
        an operational failure rather than an attempt, and a failed log write propagates rather than
        reporting a success.
        """
        with self._lock:
            if self.is_locked():
                return None
            started = time.monotonic()
            credential = read_admin_credential(root=self._root)
            matched = verify_admin_password(credential, username=username, password=password)
            now = self._clock()
            if not matched:
                self._record_failed_attempt(now, started)
                return None
            self._write_failed_logins(0)
            self.log.append(
                CommandLogEntry(
                    time=now,
                    command="login",
                    exit_code=0,
                    duration_seconds=time.monotonic() - started,
                    result="login",
                )
            )
            self._sessions.pop(cookie, None)
            return self._create_session(
                authenticated=True,
                username=credential.username,
                credential_identity=credential.password_hash,
            )

    def logout(self, cookie: str) -> None:
        """Drop only the session of one cookie and record nothing."""
        with self._lock:
            self._sessions.pop(cookie, None)

    def _require_anonymous_budget(self, now: datetime) -> None:
        """Discard out-of-window creations and raise the rate refusal at the budget.

        Creations at or before the start of the configured window are discarded first. When the
        remaining count reaches the configured limit, the refusal carries the ceiling-rounded wait
        until the oldest counted creation leaves the window.
        """
        window = timedelta(seconds=self._settings.admin_web_anonymous_session_window_seconds)
        cutoff = now - window
        while self._anonymous_grant_times and self._anonymous_grant_times[0] <= cutoff:
            self._anonymous_grant_times.popleft()
        if len(self._anonymous_grant_times) >= self._settings.admin_web_anonymous_session_limit:
            oldest = self._anonymous_grant_times[0]
            remaining = (oldest + window - now).total_seconds()
            raise AnonymousSessionRateLimited(max(1, math.ceil(remaining)))

    def _create_session(
        self, *, authenticated: bool, username: str | None, credential_identity: str | None
    ) -> SessionGrant:
        """Create one session entry with its own opaque cookie and CSRF tokens."""
        now = self._clock()
        grant = SessionGrant(
            token=secrets.token_urlsafe(_COOKIE_TOKEN_BYTES),
            csrf_token=secrets.token_urlsafe(_COOKIE_TOKEN_BYTES),
            authenticated=authenticated,
            username=username,
            created_at=now,
            last_seen=now,
            credential_identity=credential_identity,
        )
        self._sessions[grant.token] = grant
        return grant

    def _replace_last_seen(self, grant: SessionGrant) -> SessionGrant:
        """Return one session with its idle clock refreshed and store that refreshed entry."""
        refreshed = SessionGrant(
            token=grant.token,
            csrf_token=grant.csrf_token,
            authenticated=grant.authenticated,
            username=grant.username,
            created_at=grant.created_at,
            last_seen=self._clock(),
            credential_identity=grant.credential_identity,
        )
        self._sessions[grant.token] = refreshed
        return refreshed

    def _prune_expired(self) -> None:
        """Drop every session whose idle or total lifetime has been reached."""
        now = self._clock()
        for token, grant in tuple(self._sessions.items()):
            if self._expired(grant, now):
                del self._sessions[token]

    def _expired(self, grant: SessionGrant, now: datetime) -> bool:
        """Report whether one session reached either configured lifetime."""
        return now - grant.last_seen >= timedelta(
            minutes=self._settings.admin_web_session_idle_minutes
        ) or now - grant.created_at >= timedelta(hours=self._settings.admin_web_session_max_hours)

    def _credential_identity(self) -> str:
        """Return the current stored credential identity an authenticated session must match."""
        return read_admin_credential(root=self._root).password_hash

    def _record_failed_attempt(self, now: datetime, started: float) -> None:
        """Record one failed credential attempt, creating the lock at the configured limit.

        The measured duration covers credential verification and the count transition that follows
        it. The third consecutive failure creates the lock file and records one ``lock`` event instead
        of a login failure, and that event carries duration ``0.0`` because it is instantaneous.
        """
        count = self._read_failed_logins() + 1
        self._write_failed_logins(count)
        duration = time.monotonic() - started
        if count >= FAILED_LOGIN_LIMIT:
            self._create_lock()
            self.log.append(
                CommandLogEntry(
                    time=now,
                    command="lock",
                    exit_code=403,
                    duration_seconds=0.0,
                    result="lock",
                )
            )
            return
        self.log.append(
            CommandLogEntry(
                time=now,
                command="login",
                exit_code=1,
                duration_seconds=duration,
                result="failed-login",
            )
        )

    def _read_failed_logins(self) -> int:
        """Return the persisted consecutive-failure count, where genuine absence means zero."""
        path = self.state_directory / FAILED_LOGINS_FILENAME
        if not path.is_symlink() and not path.exists():
            return 0
        return load_private_model(path, FailedLogins).count

    def _write_failed_logins(self, count: int) -> None:
        """Publish the consecutive-failure count atomically, creating the state directory."""
        self.state_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        atomic_write_private_text(
            self.state_directory / FAILED_LOGINS_FILENAME,
            administrative_json(FailedLogins(count=count)),
            mode=0o600,
        )

    def _create_lock(self) -> None:
        """Create the lock file when its path is absent, without truncating what it holds."""
        self.state_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(self.state_directory / LOCK_FILENAME, os.O_WRONLY | os.O_CREAT, 0o600)
        os.close(descriptor)
