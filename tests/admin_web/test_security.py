"""Security proofs for the administration backend: admission, sessions, lockout and credentials."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import httpx
import pytest

from course_explorer_admin_web.security import SESSION_COOKIE_NAME
from tests.admin_web import _support


def _empty_refusal(response: httpx.Response) -> None:
    """Assert one request was refused with the bare empty response the lock produces."""
    assert response.status_code == 403
    assert response.content == b""


@pytest.mark.parametrize("sequence", ["lockout", "reset-by-success"])
def test_admin_lockout_persists_and_blocks_every_request(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, sequence: str
) -> None:
    """Three consecutive failures lock the whole site, and a successful login resets the count."""
    root, settings, clock, application = _support.site(monkeypatch, tmp_path)
    authenticated = _support.authenticated_client(application)
    failing = _support.site_client(application)
    csrf = _support.bootstrap(failing)

    if sequence == "reset-by-success":
        # Two failures, a successful login, then two more failures: the count restarts, so no lock.
        for _ in range(2):
            assert (
                _support.login(failing, csrf_token=csrf, password="wrong-password").status_code
                == 401
            )
        assert (
            _support.login(authenticated, csrf_token=_support.bootstrap(authenticated)).status_code
            == 200
        )
        for _ in range(2):
            assert (
                _support.login(failing, csrf_token=csrf, password="wrong-password").status_code
                == 401
            )
        assert not (root / _support.LOCK_PATH).exists()
        assert (
            json.loads((root / _support.FAILED_LOGINS_PATH).read_text(encoding="utf-8"))["count"]
            == 2
        )
        return

    # One failure on a first application, then two on a recreated one: the count and the lock are
    # durable state rather than in-memory state.
    assert _support.login(failing, csrf_token=csrf, password="wrong-password").status_code == 401
    assert not (root / _support.LOCK_PATH).exists()
    assert (
        json.loads((root / _support.FAILED_LOGINS_PATH).read_text(encoding="utf-8"))["count"] == 1
    )

    recreated = _support.site_client(_support.admin_web_app(root, settings, clock=clock))
    csrf = _support.bootstrap(recreated)
    assert _support.login(recreated, csrf_token=csrf, password="wrong-password").status_code == 401
    third = _support.login(recreated, csrf_token=csrf, password="wrong-password")
    assert third.status_code == 403
    assert third.content == b""
    assert (root / _support.LOCK_PATH).exists()
    # The lock is the file itself, so its contents decide nothing.
    (root / _support.LOCK_PATH).write_text("operator removal note\n", encoding="utf-8")

    # The authenticated session of the first application is refused while the lock exists.
    _empty_refusal(authenticated.get("/unknown"))
    _empty_refusal(authenticated.get("/auth/session"))
    authenticated_cookie = _support.session_cookie(authenticated)

    locked = _support.site_client(_support.admin_web_app(root, settings, clock=clock))
    _empty_refusal(
        locked.post(
            "/auth/login",
            json={"username": _support.OPERATOR_NAME, "password": _support.OPERATOR_PASSWORD},
            headers={"Origin": _support.ORIGIN, "X-CSRF-Token": _support.VALUE_SENTINEL},
        )
    )
    _empty_refusal(locked.get("/auth/session"))
    _empty_refusal(
        locked.get("/unknown", headers={"Cookie": f"{SESSION_COOKIE_NAME}={authenticated_cookie}"})
    )
    _empty_refusal(locked.get(_support.STATIC_PROBE_PATH))
    # The registered console shell and its built assets are refused by the lock like every address.
    _empty_refusal(locked.get("/"))
    _empty_refusal(locked.head("/"))
    _empty_refusal(locked.get(_support.ASSET_PROBE_PATH))


@pytest.mark.parametrize(
    "case",
    [
        "host-mismatch",
        "duplicate-host",
        "foreign-origin",
        "null-origin",
        "missing-origin",
        "missing-csrf",
        "wrong-csrf",
        "forwarded-host",
        "static-shell-anonymous",
        "static-asset-anonymous",
        "static-head-shell",
        "static-wrong-host",
        "static-foreign-origin",
        "protected-anonymous-route",
        "protected-wrong-csrf-route",
        "anonymous-config-read",
        "anonymous-config-set",
        "config-read-wrong-csrf",
        "config-set-wrong-csrf",
        "positive-control",
        "anonymous-probe",
        "authenticated-probe",
        "static-idle",
        "refused-csrf-idle",
        "non-ascii-csrf",
    ],
)
def test_admin_requests_enforce_host_origin_and_csrf(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, case: str
) -> None:
    """Each request is admitted only through the configured exact site and its CSRF boundary."""
    root, _settings, clock, application = _support.site(monkeypatch, tmp_path)
    client = _support.site_client(application)

    if case == "static-shell-anonymous":
        # The shell is served without a session, and the request creates no session, count or entry.
        response = client.get("/")
        assert response.status_code == 200
        assert response.text == _support.SHELL_TEXT
        assert response.headers["cache-control"] == "no-store"
        assert client.cookies.get(SESSION_COOKIE_NAME) is None
        assert not (root / _support.FAILED_LOGINS_PATH).exists()
        assert not (root / _support.COMMAND_LOG_PATH).exists()
        return

    if case == "static-asset-anonymous":
        response = client.get(_support.ASSET_PROBE_PATH)
        assert response.status_code == 200
        assert response.text == _support.ASSET_PROBE_TEXT
        assert client.cookies.get(SESSION_COOKIE_NAME) is None
        assert not (root / _support.COMMAND_LOG_PATH).exists()
        return

    if case == "static-head-shell":
        response = client.head("/")
        assert response.status_code == 200
        assert response.content == b""
        assert client.cookies.get(SESSION_COOKIE_NAME) is None
        return

    if case in {"static-wrong-host", "static-foreign-origin"}:
        headers = (
            {"Host": "evil.example.com"}
            if case == "static-wrong-host"
            else {"Origin": "https://evil.example.com"}
        )
        response = client.get("/", headers=headers)
        assert response.status_code == 403
        assert response.content == b""
        return

    if case == "protected-anonymous-route":
        # A feature route keeps its session requirement, and the anonymous bootstrap sets no grant.
        _support.bootstrap(client)
        response = client.get("/api/dashboard")
        assert response.status_code == 401
        assert response.content == b""
        # The assets prefix without its slash is not the static exception.
        assert client.get("/assets").status_code == 401
        return

    if case == "protected-wrong-csrf-route":
        authenticated = _support.authenticated_client(application)
        log_path = root / _support.COMMAND_LOG_PATH
        entries_before = log_path.read_bytes()
        refused = authenticated.post(
            "/api/inference/datasets/delete",
            json={"dataset_id": "b" * 32},
            headers={"Origin": _support.ORIGIN, "X-CSRF-Token": "wrong-token"},
        )
        assert refused.status_code == 403
        assert refused.content == b""
        # A refused request executes no command and appends no entry.
        assert log_path.read_bytes() == entries_before
        return

    if case in {"anonymous-config-read", "anonymous-config-set"}:
        # A configuration read and a configuration save both keep the authenticated-session
        # requirement, so an anonymous session reaches neither its own CSRF token nor its body.
        csrf = _support.bootstrap(client)
        read = case == "anonymous-config-read"
        refused = client.post(
            "/api/settings/config/read" if read else "/api/settings/config/set",
            json=(
                {"file": "config/web.toml"}
                if read
                else {"file": "config/web.toml", "key": "WEB_PORT", "value": "18026"}
            ),
            headers={"Origin": _support.ORIGIN, "X-CSRF-Token": csrf},
        )
        assert refused.status_code == 401
        assert refused.content == b""
        # No command ran, and a refused request records nothing.
        assert not (root / _support.COMMAND_LOG_PATH).exists()
        return

    if case in {"config-read-wrong-csrf", "config-set-wrong-csrf"}:
        # A configuration read or save without the session's own CSRF token is refused, and the
        # refused request executes no command and appends no entry.
        authenticated = _support.authenticated_client(application)
        log_path = root / _support.COMMAND_LOG_PATH
        entries_before = log_path.read_bytes()
        read = case == "config-read-wrong-csrf"
        refused = authenticated.post(
            "/api/settings/config/read" if read else "/api/settings/config/set",
            json=(
                {"file": "config/web.toml"}
                if read
                else {"file": "config/web.toml", "key": "WEB_PORT", "value": "18026"}
            ),
            headers={"Origin": _support.ORIGIN, "X-CSRF-Token": "wrong-token"},
        )
        assert refused.status_code == 403
        assert refused.content == b""
        assert log_path.read_bytes() == entries_before
        return

    if case == "static-idle":
        # Static admission reads no cookie, so it never refreshes a live session's idle clock.
        authenticated = _support.authenticated_client(application)
        log_path = root / _support.COMMAND_LOG_PATH
        entries_before = log_path.read_bytes()
        clock.advance(timedelta(minutes=29))
        static = authenticated.get("/")
        assert static.status_code == 200
        assert static.text == _support.SHELL_TEXT
        assert log_path.read_bytes() == entries_before
        clock.advance(timedelta(minutes=1))
        assert authenticated.get("/unknown").status_code == 401
        return

    if case == "positive-control":
        # An otherwise valid request is admitted, through the real anonymous bootstrap and login.
        csrf = _support.bootstrap(client)
        assert client.cookies.get(SESSION_COOKIE_NAME) is not None
        response = _support.login(client, csrf_token=csrf)
        assert response.status_code == 200
        assert response.json()["authenticated"] is True
        return

    if case == "anonymous-probe":
        # An admitted anonymous session reaches no protected address.
        _support.bootstrap(client)
        response = client.get("/unknown")
        assert response.status_code == 401
        assert response.content == b""
        return

    if case == "authenticated-probe":
        # An admitted authenticated session reaches the router's ordinary answer for an unknown path.
        authenticated = _support.authenticated_client(application)
        assert authenticated.get("/unknown").status_code == 404
        return

    if case == "refused-csrf-idle":
        # A refused state-changing request refreshes no idle clock and records nothing, so the same
        # session reaches its idle boundary untouched at minute 30.
        authenticated = _support.authenticated_client(application)
        csrf = authenticated.get("/auth/session").json()["csrf_token"]
        failed_logins = (root / _support.FAILED_LOGINS_PATH).read_bytes()
        command_log = (root / _support.COMMAND_LOG_PATH).read_bytes()
        clock.advance(timedelta(minutes=29))
        refused = authenticated.post(
            "/auth/logout",
            json={},
            headers={"Origin": _support.ORIGIN, "X-CSRF-Token": "wrong-token"},
        )
        assert refused.status_code == 403
        assert refused.content == b""
        assert (root / _support.FAILED_LOGINS_PATH).read_bytes() == failed_logins
        assert (root / _support.COMMAND_LOG_PATH).read_bytes() == command_log
        clock.advance(timedelta(minutes=1))
        assert authenticated.get("/unknown").status_code == 401
        return

    if case == "non-ascii-csrf":
        # A raw non-ASCII token header is a mismatch rather than a decoding failure: the request is
        # refused with the bare 403 before any route or idle refresh, and it records nothing.
        authenticated = _support.authenticated_client(application)
        failed_logins = (root / _support.FAILED_LOGINS_PATH).read_bytes()
        command_log = (root / _support.COMMAND_LOG_PATH).read_bytes()
        clock.advance(timedelta(minutes=29))
        refused = authenticated.post(
            "/auth/logout",
            json={},
            headers=[
                (b"Origin", _support.ORIGIN.encode("ascii")),
                (b"X-CSRF-Token", b"\xff\xfe"),
            ],
        )
        assert refused.status_code == 403
        assert refused.content == b""
        assert (root / _support.FAILED_LOGINS_PATH).read_bytes() == failed_logins
        assert (root / _support.COMMAND_LOG_PATH).read_bytes() == command_log
        clock.advance(timedelta(minutes=1))
        assert authenticated.get("/unknown").status_code == 401
        return

    csrf = _support.bootstrap(client)

    def login_attempt(**headers: str) -> object:
        """Send one fully valid login attempt carrying exactly the supplied boundary headers."""
        return client.post(
            "/auth/login",
            json={"username": _support.OPERATOR_NAME, "password": _support.OPERATOR_PASSWORD},
            headers=headers,
        )

    if case == "host-mismatch":
        response = client.get("/auth/session", headers={"Host": "localhost:9999"})
    elif case == "duplicate-host":
        response = client.get(
            "/auth/session",
            headers=[("Host", "localhost:8039"), ("Host", "localhost:8039")],
        )
    elif case == "foreign-origin":
        response = client.get("/auth/session", headers={"Origin": "https://evil.example.com"})
    elif case == "null-origin":
        response = login_attempt(Origin="null", **{"X-CSRF-Token": csrf})
    elif case == "missing-origin":
        response = login_attempt(**{"X-CSRF-Token": csrf})
    elif case == "missing-csrf":
        response = login_attempt(Origin=_support.ORIGIN)
    elif case == "wrong-csrf":
        response = login_attempt(Origin=_support.ORIGIN, **{"X-CSRF-Token": "wrong-token"})
    else:
        response = client.get(
            "/auth/session",
            headers={
                "Host": "evil.example.com",
                "X-Forwarded-Host": "localhost:8039",
                "X-Forwarded-Proto": "https",
            },
        )

    assert response.status_code == 403
    assert response.content == b""
    # A refused request reaches no handler and records no credential attempt.
    assert not (root / _support.FAILED_LOGINS_PATH).exists()
    assert not (root / _support.COMMAND_LOG_PATH).exists()


@pytest.mark.parametrize("limit", ["idle", "total"])
def test_admin_sessions_expire_at_idle_or_total_limit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, limit: str
) -> None:
    """A session works below its configured boundary and is refused at the boundary itself."""
    _root, _settings, clock, application = _support.site(monkeypatch, tmp_path)
    first = _support.authenticated_client(application)
    second = _support.site_client(application)
    assert _support.login(second, csrf_token=_support.bootstrap(second)).status_code == 200

    if limit == "idle":
        clock.advance(timedelta(minutes=29))
        # Below the idle boundary the session works, and that request refreshes its own clock.
        assert second.get("/unknown").status_code == 404
        clock.advance(timedelta(minutes=1))
        # The idle lifetime is reached exactly, so the untouched session is refused.
        assert first.get("/unknown").status_code == 401
        assert second.get("/unknown").status_code == 404
    else:
        # Touches keep the idle clock alive until the total lifetime is reached.
        for _ in range(35):
            clock.advance(timedelta(minutes=20))
            assert first.get("/unknown").status_code == 404
        assert _support.login(second, csrf_token=_support.bootstrap(second)).status_code == 200
        clock.advance(timedelta(minutes=20))
        assert first.get("/unknown").status_code == 401
        assert second.get("/unknown").status_code == 404

    # A fresh bootstrap may create anonymous state, and it reports an unauthenticated session.
    assert first.get("/auth/session").json()["authenticated"] is False


@pytest.mark.parametrize(
    "case",
    ["correct", "incorrect", "forged-and-predecessor", "password-replacement", "malformed-hash"],
)
def test_admin_login_issues_protected_server_session(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, case: str
) -> None:
    """A correct credential issues one server-validated session with the protected cookie."""
    root, _settings, _clock, application = _support.site(monkeypatch, tmp_path)
    client = _support.site_client(application)
    initial_csrf = _support.bootstrap(client)
    initial_cookie = _support.session_cookie(client)

    if case == "incorrect":
        response = _support.login(client, csrf_token=initial_csrf, password="wrong-password")
        assert response.status_code == 401
        assert "set-cookie" not in response.headers
        assert client.get("/auth/session").json()["authenticated"] is False
        assert (
            json.loads((root / _support.FAILED_LOGINS_PATH).read_text(encoding="utf-8"))["count"]
            == 1
        )
        return

    if case == "malformed-hash":
        # A stored hash that is not an argon2id encoding fails operationally before the presented
        # username can turn the attempt into a failed login.
        path = root / _support.PASSWORD_PATH
        credential = json.loads(path.read_text(encoding="utf-8"))
        credential["password_hash"] = "invalid-synthetic-hash"
        path.write_text(json.dumps(credential) + "\n", encoding="utf-8")
        response = _support.login(client, csrf_token=initial_csrf, username="another-operator")
        assert response.status_code == 500
        assert response.headers["cache-control"] == "no-store"
        assert set(response.json()) == {"error"}
        assert not (root / _support.FAILED_LOGINS_PATH).exists()
        assert not (root / _support.COMMAND_LOG_PATH).exists()
        return

    if case == "forged-and-predecessor":
        # Neither a forged value nor the rotated anonymous token is a server session.
        forged = client.get("/unknown", headers={"Cookie": f"{SESSION_COOKIE_NAME}=forged-token"})
        assert forged.status_code == 401
        assert _support.login(client, csrf_token=initial_csrf).status_code == 200
        rotated = client.get(
            "/unknown", headers={"Cookie": f"{SESSION_COOKIE_NAME}={initial_cookie}"}
        )
        assert rotated.status_code == 401
        return

    response = _support.login(client, csrf_token=initial_csrf)
    assert response.status_code == 200
    report = response.json()
    assert report["authenticated"] is True
    assert report["username"] == _support.OPERATOR_NAME
    assert report["csrf_token"] != initial_csrf
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/unknown").status_code == 404

    if case == "password-replacement":
        # The established session is bound to the stored credential identity, so the first session
        # request after a replacement receives anonymous state and a replacement cookie.
        authenticated_cookie = _support.session_cookie(client)
        _support.set_account_password(monkeypatch, root)
        replaced = client.get("/auth/session")
        assert replaced.status_code == 200
        assert replaced.json()["authenticated"] is False
        assert replaced.json()["username"] is None
        assert _support.session_cookie(client) != authenticated_cookie
        refused = client.get(
            "/unknown", headers={"Cookie": f"{SESSION_COOKIE_NAME}={authenticated_cookie}"}
        )
        assert refused.status_code == 401
        replacement = _support.site_client(application)
        replacement_csrf = _support.bootstrap(replacement)
        assert _support.login(replacement, csrf_token=replacement_csrf).status_code == 401
        assert (
            _support.login(
                replacement,
                csrf_token=replacement_csrf,
                password=_support.REPLACEMENT_PASSWORD,
            ).status_code
            == 200
        )
        return

    issued_cookie = _support.session_cookie(client)
    assert issued_cookie != initial_cookie
    issued = response.headers["set-cookie"]
    assert issued.startswith(f"{SESSION_COOKIE_NAME}={issued_cookie}")
    assert "HttpOnly" in issued
    assert "Secure" in issued
    assert "SameSite=strict" in issued
    assert "Path=/" in issued
    assert "Domain" not in issued
    assert "Max-Age" not in issued
    assert "Expires" not in issued


def test_admin_logout_revokes_only_its_session(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Logout ends one session on the server and leaves the other session usable."""
    _root, _settings, _clock, application = _support.site(monkeypatch, tmp_path)
    first = _support.site_client(application)
    second = _support.site_client(application)
    first_report = _support.login(first, csrf_token=_support.bootstrap(first))
    assert first_report.status_code == 200
    revoked_token = _support.session_cookie(first)
    _support.login(second, csrf_token=_support.bootstrap(second))
    assert second.get("/unknown").status_code == 404

    response = first.post(
        "/auth/logout",
        json={},
        headers={
            "Origin": _support.ORIGIN,
            "X-CSRF-Token": first_report.json()["csrf_token"],
        },
    )

    assert response.status_code == 204
    assert response.content == b""
    assert response.headers["cache-control"] == "no-store"
    deletion = response.headers["set-cookie"]
    assert deletion.startswith(f'{SESSION_COOKIE_NAME}=""')
    assert "Max-Age=0" in deletion
    assert "Path=/" in deletion
    assert "HttpOnly" in deletion
    assert "Secure" in deletion
    assert "SameSite=strict" in deletion
    assert first.cookies.get(SESSION_COOKIE_NAME) is None
    refused = first.get("/unknown", headers={"Cookie": f"{SESSION_COOKIE_NAME}={revoked_token}"})
    assert refused.status_code == 401
    assert second.get("/unknown").status_code == 404
    # A fresh bootstrap is anonymous, so it does not bypass the revocation.
    fresh = _support.site_client(application)
    assert fresh.get("/auth/session").json()["authenticated"] is False


def test_anonymous_session_budget_is_server_wide_and_spares_live_sessions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Fresh anonymous sessions spend one process-wide budget while live sessions keep working."""
    root, _settings, _clock, application = _support.site(
        monkeypatch,
        tmp_path,
        ADMIN_WEB_ANONYMOUS_SESSION_LIMIT=2,
        ADMIN_WEB_ANONYMOUS_SESSION_WINDOW_SECONDS=60,
    )
    first = _support.site_client(application)
    _support.bootstrap(first)
    first_cookie = _support.session_cookie(first)

    # A refused admission and a static read create no grant, so the remaining slot stays open.
    refused_admission = _support.site_client(application)
    for _ in range(3):
        assert (
            refused_admission.get("/auth/session", headers={"Host": "evil.example.com"}).status_code
            == 403
        )
    assert refused_admission.get("/").status_code == 200
    assert refused_admission.get(_support.ASSET_PROBE_PATH).status_code == 200
    assert refused_admission.cookies.get(SESSION_COOKIE_NAME) is None

    second = _support.site_client(application)
    second_csrf = _support.bootstrap(second)
    assert not (root / _support.FAILED_LOGINS_PATH).exists()
    assert not (root / _support.COMMAND_LOG_PATH).exists()
    assert not (root / _support.LOCK_PATH).exists()

    # The budget is server-wide, so a third no-cookie client is refused at the spent budget.
    third = _support.site_client(application)
    refused = third.get("/auth/session")
    assert refused.status_code == 429
    assert refused.content == b""
    assert refused.headers["cache-control"] == "no-store"
    assert refused.headers["retry-after"] == "60"
    assert "set-cookie" not in refused.headers
    assert third.cookies.get(SESSION_COOKIE_NAME) is None
    assert not (root / _support.LOCK_PATH).exists()

    # A live anonymous session and a successful sign-in's authenticated replacement both reuse
    # their grant without spending a slot.
    reused = first.get("/auth/session")
    assert reused.status_code == 200
    assert reused.json()["authenticated"] is False
    assert _support.session_cookie(first) == first_cookie
    assert _support.login(second, csrf_token=second_csrf).status_code == 200
    assert second.get("/unknown").status_code == 404
    assert third.get("/auth/session").status_code == 429

    # The shell exception and the exact-site refusal keep their place ahead of the budget.
    assert third.get("/").status_code == 200
    assert third.get("/auth/session", headers={"Host": "evil.example.com"}).status_code == 403

    # A refusal at the spent budget adds no failed attempt and no command-log entry.
    log_before = (root / _support.COMMAND_LOG_PATH).read_bytes()
    failed_before = (root / _support.FAILED_LOGINS_PATH).read_bytes()
    assert third.get("/auth/session").status_code == 429
    assert (root / _support.COMMAND_LOG_PATH).read_bytes() == log_before
    assert (root / _support.FAILED_LOGINS_PATH).read_bytes() == failed_before


def test_anonymous_session_budget_recovers_at_the_rolling_window(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The window discards a creation at its boundary and each refusal rounds its wait up."""
    _root, _settings, clock, application = _support.site(
        monkeypatch,
        tmp_path,
        ADMIN_WEB_ANONYMOUS_SESSION_LIMIT=2,
        ADMIN_WEB_ANONYMOUS_SESSION_WINDOW_SECONDS=60,
    )
    first = _support.site_client(application)
    _support.bootstrap(first)
    clock.advance(timedelta(seconds=20))
    second = _support.site_client(application)
    _support.bootstrap(second)

    third = _support.site_client(application)
    refused = third.get("/auth/session")
    assert refused.status_code == 429
    assert refused.headers["retry-after"] == "40"
    assert third.cookies.get(SESSION_COOKIE_NAME) is None

    # Half a second before the oldest creation leaves, the wait rounds up to one second.
    clock.advance(timedelta(seconds=39, milliseconds=500))
    refused = third.get("/auth/session")
    assert refused.status_code == 429
    assert refused.headers["retry-after"] == "1"

    # At the window boundary itself the oldest creation is discarded and a fresh grant is admitted.
    clock.advance(timedelta(milliseconds=500))
    admitted = third.get("/auth/session")
    assert admitted.status_code == 200
    assert admitted.json()["authenticated"] is False
    assert _support.session_cookie(third) is not None

    # The next-oldest creation sets the following refusal's wait.
    fourth = _support.site_client(application)
    refused = fourth.get("/auth/session")
    assert refused.status_code == 429
    assert refused.content == b""
    assert refused.headers["retry-after"] == "20"
