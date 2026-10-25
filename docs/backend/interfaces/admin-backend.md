# Administration backend

The administration backend is the separate signed-in process that admits each console request and runs fixed administration commands.

Its admission order, its sessions and lock, and its command log are stated in [Console access and records](/docs/operations/admin-console/access-and-records.md). This page describes the package, its route modules, its security owner, its command log file and its fixed runner.

## The package and its entry point

`src/course_explorer_admin_web/` is the administration backend package. Its `__main__.main()` loads `AdminWebSettings` once through the shared settings owner, builds the application and serves it with `uvicorn.run(..., workers=1, access_log=False, proxy_headers=False)`. One process is fixed, because the sessions live in that process's memory. `scripts/run_admin_web.sh` execs `./.venv/bin/python -m course_explorer_admin_web`, which is the backend's own launcher rather than a copy of the feature web's settings handoff.

`create_app(*, settings=None, root=None, clock=utc_now, dist_directory=None, process_runner=None)` in `src/course_explorer_admin_web/app.py` builds the application. It disables the interactive documentation and the schema route, attaches the resolved `AdminWebSettings` to `application.state.settings`, one `AdminSecurity` to `application.state.security` and one `FixedCommandRunner` to `application.state.commands`, registers the authentication router, the five feature routers and the console frontend, registers the fixed 422 handler, and adds `AdminAdmissionMiddleware` outside every route.

The dist directory defaults to `<root>/admin-web/dist`, and `process_runner` is the process boundary the fixed-command runner executes over. Construction reads the configured settings and the repository root, creates no file, executes no command and opens no database, and the module binds no module-level application. The backend records no request usage, because the usage file counts course-exploration site requests alone.

## The admission order

`AdminAdmissionMiddleware` in `src/course_explorer_admin_web/middleware.py` applies one order to every HTTP request. A refusal answers before any handler runs.

- The administration lock comes first. While the entry `data/admin-web/lock` exists, whatever its type or content, the request gets `403` with an empty body and no reason.
- The request must carry exactly one `Host` header equal to the configured origin's netloc, including its configured port. A duplicate `Host` or `Origin` header is refused, and a supplied `Origin` must equal the configured origin string exactly, so a `null` origin and a foreign origin both fail. The forwarded host and scheme headers are ignored, because a proxy reaches this backend over plain HTTP on loopback.
- A read-only request of the built console shell or of a built asset is admitted here, before its cookie is read. The exception covers `GET` and `HEAD` of exactly `/` and of a path that begins `/assets/`. A `POST` of either path, the address `/assets` without its slash and every other address keep the session flow below. These static requests create no session, touch no session, execute no command and record nothing, and a request for an asset the build does not hold answers the mount's own `404` rather than another file.
- `GET /auth/session` calls `bootstrap`, which reuses the live session of the presented cookie or creates an anonymous one within the process-wide anonymous session creation limit. `bootstrap` raises `AnonymousSessionRateLimited` when the limit is spent, and the middleware catches it and answers `429` with an empty body, `Cache-Control: no-store` and `Retry-After` set to the exception's positive whole-second wait. A lock or exact-site refusal, and the static shell or asset admission, keep their place ahead of this check. Every other request resolves its presented cookie without refreshing it: `POST /auth/login` needs a live session, anonymous or authenticated, and answers `403` without one, and every other address, an unknown path and a mounted file included, needs an authenticated live session and answers `401` without one.
- A method other than `GET`, `HEAD` or `OPTIONS` needs the exact `Origin` and a live session whose `X-CSRF-Token` matches that session's token. The supplied header bytes compare directly with the session's ASCII token under `secrets.compare_digest`, so a non-ASCII value is a mismatch. A missing or wrong token is refused with the empty `403`, and the comparison runs before any session refresh, so a refused request leaves the idle clock of its session where it was.
- Once every check passes, the middleware refreshes that request's own session through `touch` and puts the refreshed session in `scope["state"]["admin_session"]`. A session revoked between its admission and its refresh answers `401` and is not inserted again.

A validly admitted unknown path reaches the router's ordinary `404` or `405`, so the admission boundary adds no route of its own. A websocket scope is closed with code 1008 and a lifespan scope passes through. No CORS middleware is registered, so no browser origin other than the configured one can read a response.

## Routes and responses

| Route | Request | Response |
|---|---|---|
| `GET /auth/session` | No body | `SessionReport(authenticated, csrf_token, username, poll_seconds, app_url, repository_url)`, or an empty `429` at the creation limit |
| `POST /auth/login` | `LoginRequest(username, password)` | The same report, a safe `401`, or an empty `403` |
| `POST /auth/logout` | The empty `LogoutRequest` | `204` with an empty body |
| `GET /` and `GET /assets/...` | No body | The built shell and the built assets |
| `GET /api/dashboard` | No body | One `CommandResult` of the server status command |
| `GET /api/preparation/status/{stage}` | Stage in the path | One `CommandResult` of the stage status action |
| `POST /api/preparation/action` | `StageActionRequest(stage, action)` | One `CommandResult` of the stage action |
| `GET /api/preparation/report/{report}` | Report in the path | One `CommandResult` of the catalogue summary or of the coverage report |
| `POST /api/preparation/hubs` | The empty `HubsRequest` | One `CommandResult` of the hub writer |
| `GET /api/inference/status` | No body | One `CommandResult` of the inference status action |
| `POST /api/inference/action` | `InferenceActionRequest(action)` | One `CommandResult` of the inference action |
| `GET /api/inference/summary` | No body | One `CommandResult` of the inference summary |
| `POST /api/inference/target/read` | `TargetReadRequest(target_id)` | One `CommandResult` of the target read |
| `POST /api/inference/target/decision` | `TargetDecisionRequest(target_id, disposition)` | One `CommandResult` of the decision |
| `GET /api/inference/datasets` | No body | One `CommandResult` of the retained dataset listing |
| `POST /api/inference/datasets/delete` | `DatasetDeleteRequest(dataset_id)` | One `CommandResult` of the dataset deletion |
| `GET /api/logs/commands` | No body | One `CommandResult` of the retained command-log read |
| `GET /api/logs/sessions` | No body | One `CommandResult` of the log-session listing |
| `POST /api/logs/read` | `SessionLogRequest(stage, session_id, source, lines)` | One `CommandResult` of the bounded session-log read |
| `POST /api/logs/embedding` | `EmbeddingLogRequest(lines)` | One `CommandResult` of the embedding-log read |
| `POST /api/logs/usage` | `UsageRequest(hours)` | One `CommandResult` of the windowed usage report |
| `GET /api/settings/config/files` | No body | One `CommandResult` of the configuration file listing |
| `POST /api/settings/config/read` | `ConfigReadRequest(file)` | One `CommandResult` of the configuration file read |
| `POST /api/settings/config/set` | `ConfigSetRequest(file, key, value)` | One `CommandResult` of the one-key save |
| `GET /api/settings/backups` | No body | One `CommandResult` of the backup-file listing |
| `POST /api/settings/backups/delete` | `BackupDeleteRequest(name)` | One `CommandResult` of the backup-file deletion |
| `POST /api/settings/rebuild` | The empty `EmptyRequest` | One `CommandResult` of the site rebuild |
| `POST /api/settings/rebuild-admin` | The empty `EmptyRequest` | One `JSONResponse` holding the build's `CommandResult`, whose successful body queues the restart |
| `POST /api/settings/datasets/setup` | The empty `EmptyRequest` | One `CommandResult` of the selected-dataset enrollment |
| `POST /api/settings/datasets/migrate` | The empty `EmptyRequest` | One `CommandResult` of the selected-dataset migration |
| `POST /api/settings/worker/setup` | `WorkerSetupRequest(branch, code_only)` | One `CommandResult` of the worker setup or update |
| `POST /api/settings/worker/preflight` | The empty `EmptyRequest` | One `CommandResult` of the read-only worker preflight |

`POST /api/settings/config/set` replaces the value of one key that the named file already carries, and it leaves every other byte of the file as it is. In the environment file it also appends one quoted assignment for an absent key that an owning settings family declares, in the file's first line-ending style. It refuses a key that a subsystem file does not carry and an absent environment key that no settings family owns, and a refused candidate writes no file.

The handlers in `routes/auth.py` are the synchronous `session(request, response)`, `login(request, response, body)` and `logout(request, response, body)`. `session` reports the session the admission middleware put in `request.state.admin_session`, and `login` and `logout` delegate to `application.state.security`. `routes/dashboard.py`, `routes/preparation.py`, `routes/inference.py`, `routes/logs.py` and `routes/settings.py` hold the feature handlers.

A single-command handler returns one `request.app.state.commands.run(...)` result as its `CommandResult` response with `Cache-Control: no-store`, and a read handler of those five modules also passes `automatic=automatic_read(request)` as the runner's flag. `rebuild_admin(request, body)` in `routes/settings.py` is the one handler that returns a `JSONResponse`, because it attaches a second command as a background task.

## The administration rebuild

`POST /api/settings/rebuild-admin` is the one feature route that maps one request to two fixed commands. Its handler runs `AdminRebuildCommand` synchronously and returns that command's ordinary envelope, holding the exit code, the decoded report and the safe failure line, in a `JSONResponse` with `Cache-Control: no-store`.

Only a build that reported exit code zero and no failure line attaches `BackgroundTask(application.state.commands.run, RestartAdminCommand(kind="restart-admin"))`. Starlette awaits completion of the final ASGI response body send before it runs a background task, so the restart request follows a completed send rather than an observed client receipt. A build that failed attaches no task, and a send that fails or is cancelled runs no restart.

A failure after the response started reaches the middleware's own handling, which raises the content-free `RuntimeError` and exposes no payload. The restart is the same ordinary runner call the other routes make, so it decodes its report and records one entry of its own under the fixed label `restart-admin` through the one safe outcome path. Its outcome reaches that log alone.

A queue failure records the ordinary safe failure entry and cannot change the response, which was built and sent before the task ran. A successful administration rebuild therefore leaves one `rebuild-admin` entry followed by one `restart-admin` entry, and a failed build leaves the one `rebuild-admin` failure entry. Both commands are explicit actions, so neither suppresses its entry under the automatic-read marker.

## The console frontend

`src/course_explorer_admin_web/frontend.py` registers the built console. `/` answers the build's `index.html` for `GET` and `HEAD` with no-store caching, and `/assets` is a `StaticFiles` mount over the build's assets directory with the default refusal of symlinked entries. No other document, catch-all route, filesystem browser, source map or course-exploration asset is registered, so a build that is absent fails when it is requested instead of answering another file. The console's own React application is built separately from `admin-web/` into `admin-web/dist`, and the course-exploration server holds no file of it.

## Sessions

`AdminSecurity` in `src/course_explorer_admin_web/security.py` owns the sessions, the anonymous session creation limit, the failed-attempt count, the lock and the command log. It holds one re-entrant lock, and its constructor creates no directory and no file.

An administration session is one `SessionGrant`: an opaque token, a CSRF token, its authentication state, the account name, its creation and last-seen times, and the encoded hash of the credential it was issued against. The token and the CSRF value are generated separately with `secrets.token_urlsafe(32)`. The grant is state of this process alone, and it is never serialized into a response or a durable file.

A session expires when either `now - last_seen` reaches the configured idle lifetime or `now - created_at` reaches the configured total lifetime, and expiry is checked before any session is refreshed.

`bootstrap(cookie)` reuses the live session of the presented cookie and otherwise creates an anonymous one within the process-wide anonymous session creation limit, it prunes expired entries so the dictionary needs no background task, and it validates an authenticated session against the stored credential identity, because it resolves the cookie through the one validating read. `resolve(cookie)` returns the live session of one cookie or `None`, prunes the expired entries and drops an authenticated session whose stored credential identity changed, and it leaves the idle clock of a returned session as it is.

`_anonymous_grant_times` is a `collections.deque` capped at `ADMIN_WEB_ANONYMOUS_SESSION_LIMIT` creation times. `bootstrap` resolves the cookie first, so a live grant consumes nothing. Otherwise `_require_anonymous_budget` discards every stored time at or before `now - ADMIN_WEB_ANONYMOUS_SESSION_WINDOW_SECONDS`, raises `AnonymousSessionRateLimited` with `max(1, math.ceil(remaining))` seconds when the retained count reaches the limit, and only then calls `_create_session` and appends its creation time. The sessions and the deque sit under the same `threading.RLock`, so two concurrent bootstrap requests cannot both pass the limit. The session dictionary and the deque live in process memory, so construction creates no file and a restart clears both.

`touch(cookie)` refreshes the idle clock of the one admitted session and returns `None` for an absent or revoked one, and it is the one post-admission mutation. `login(cookie, ...)` verifies one credential attempt and returns a fresh authenticated grant, or `None` when the attempt fails or the site is locked. `logout(cookie)` drops the one entry of that cookie.

The session cookie is `__Host-course-explorer-admin` with `Secure`, `HttpOnly`, `SameSite=Strict`, `Path=/`, no `Domain` and no persistent `Max-Age` or `Expires`, because the server owns the lifetime. Bootstrap writes a cookie only for the entry it creates, login rotates it, and logout deletes it with the same attributes after the server revocation. Several sessions may exist at once, each expires on its own, and logout ends only the one that asked for it.

An authenticated session resolves against the current stored credential identity, so replacing the password invalidates that session on its next request. That check compares one encoded hash and hashes nothing per request. The first `GET /auth/session` of an invalidated cookie therefore receives fresh anonymous state and a replacement cookie rather than an authenticated report when the creation limit admits a fresh grant, and only that replacement cookie resolves. A spent limit answers the empty `429` and issues no replacement cookie. A restart discards every session and empties the anonymous-grant window, while the failed-attempt count, the lock and the command log live on disk.

## The failed-attempt count and the lock

Three consecutive failed logins create the lock, and the limit and the lock path are code constants rather than settings. The count is the sole JSON document `data/admin-web/failed-logins`, published atomically at mode 0600 under a mode-0700 directory. Genuine absence means zero, and a successful login resets the count.

A failed credential records one `failed-login` event, and the failure that reaches the limit creates the lock file, without truncating what that path holds, and records one `lock` event instead. Login checks the lock inside its own serialized transition as well as at admission, so two concurrent attempts cannot both pass the limit.

The lock is the file itself. Existence is tested with `lstat`, so a dangling symlink, a directory and a nonempty file each lock the site exactly as an empty regular file does, and no code path removes it. An operator ends the lock by deleting the whole file over SSH, and the web surface never lists or names it. An entry at that path is checked before login, before any route and before any static file, for an authenticated request as well as an anonymous one.

## The credential file

`src/course_explorer_admin/credentials.py` is the sole owner of the password file `data/admin-web/password`, and it holds no web framework dependency, because the provisioning command and the backend both use it. The file is one closed JSON document holding the username and an argon2id encoded hash, with the hash excluded from the model's rendered form.

`set_admin_password` requires a nonblank NUL-free username and a nonblank password, hashes with the library's own argon2id cost parameters, creates the state directory with parents at mode 0700, and publishes the file atomically at mode 0600. `read_admin_credential` loads it strictly as a regular non-symlink file.

`verify_admin_password` extracts and checks the stored hash parameters and runs its one verification call before it compares the username, so a stored hash that is not argon2id and an unreadable hash raise rather than counting an attempt, whatever username the attempt presents.

The username and the hash belong to this credential file and to the security state it validates. A session report carries the authenticated username but no hash. No acknowledgment, command-log entry or command result carries either value.

## The command log

`src/course_explorer_admin_web/command_log.py` owns the sole durable administration history, the file `data/admin-web/command-log`. One `CommandLogEntry` holds the time, a fixed command label, the exit code, the elapsed monotonic duration, one outcome token and at most one short safe failure line. The outcome token is `success`, `failure`, `login`, `failed-login` or `lock`, and every producer chooses its label from fixed source-code text rather than from an argument or a request field. No entry holds captured output, a password, a key value, a session token or a free-form argument.

`CommandLog.append` opens the file with `os.open(..., os.O_RDWR | os.O_CREAT, 0o600)`, takes `fcntl.flock(LOCK_EX)` on that descriptor, parses every retained line, appends the entry, retains the last configured entries oldest first and rewrites the locked inode in place before it flushes. `CommandLog.read` takes the same lock, parses the whole file and returns the last configured number of entries oldest first, or no entries for genuine absence. A file holding more entries than the configured limit reports its newest entries and the read rewrites nothing. A malformed or unreadable line fails the read instead of being repaired or skipped.

The authentication events use the same file and the same shape as a command outcome, and the lock event carries duration `0.0` because it is an instantaneous transition.

`read_command_log()` is the Logs view's one read of that file. It resolves this checkout as the root and `ADMIN_WEB_COMMAND_LOG_LIMIT` as the bound, calls `CommandLog.read` once, and returns a `CommandLogReport` holding the newest configured entries oldest first. It creates no file, prunes nothing and records nothing: an invocation of the `logs commands` command is itself recorded by the runner alone, and a successful automatic invocation of it records no entry.

## The fixed command runner

`src/course_explorer_admin_web/runner.py` admits a closed command shape and builds its exact argument list. The discriminated `FixedCommand` union holds these command models:

- Status and usage: `ServerStatusCommand` and `UsageCommand`
- Stages and reports: `StageCommand`, `CoverageCommand`, `SummaryCommand` and `HubsCommand`
- Inference: `TargetReadCommand` and `TargetDecisionCommand`
- Datasets: `DatasetListCommand`, `DatasetDeleteCommand`, `DatasetSetupCommand` and `DatasetMigrateCommand`
- Logs: `CommandLogCommand`, `LogSessionsCommand`, `SessionLogCommand` and `EmbeddingLogCommand`
- Configuration and backups: `ConfigFilesCommand`, `ConfigReadCommand`, `ConfigSetCommand`, `BackupListCommand` and `BackupDeleteCommand`
- Maintenance and worker: `RebuildCommand`, `AdminRebuildCommand`, `RestartAdminCommand`, `WorkerSetupCommand` and `WorkerPreflightCommand`

`UsageCommand.hours`, `SessionLogCommand.lines` and `EmbeddingLogCommand.lines` are strict positive integers. `StageCommand` carries one of the four stage names and one of the five lifecycle actions, `SessionLogCommand` carries the shared fixed log source and dataset identity types, and `CoverageCommand` and `SummaryCommand` carry one closed report literal each. `TargetInput` requires a nonblank NUL-free target id that does not begin with a hyphen, so a positional target cannot reach the command parser as an option. `DatasetDeleteCommand.dataset_id` is the shared fixed lowercase-hex dataset id type. `ConfigReadCommand.file`, `ConfigSetCommand.file`, `ConfigSetCommand.key`, `BackupDeleteCommand.name` and `WorkerSetupCommand.branch` pass the shared text validator, so a blank or NUL-bearing value is refused here.

A configuration value is one JSON literal string without NUL characters that this layer neither strips nor interprets, and the models that carry one set `hide_input_in_errors` and exclude that field from their rendered form. `WorkerSetupCommand.code_only` is a strict boolean.

`FixedCommandRunner.run` revalidates the supplied value against that union before it executes anything, so a mapping or an arbitrary object is not a command. No check of course existence, stage idleness, dataset chain, selected status, file confinement, key existence, backup name safety or branch validity happens here, because those guards belong to the command's owning service.

The runner builds `(sys.executable, str(root / "scripts" / "admin.py"), ...)` with the admitted verbs, runs it once through `course_explorer_admin.mechanics.ProcessRunner` with `cwd=root`, and never uses a shell, a caller-selected executable or a free-form argument. A configuration file or key and a backup name follow their verb after a `--` separator, so a value that reads as an option cannot become one. A target id is refused when it starts with a hyphen, so it cannot reach the parser as an option without a separator. The worker branch uses the `--branch=BRANCH` form with `--code-only` appended only for its true value.

Its union admission and its argument construction happen before any execution, so a refused command runs nothing and records nothing. It captures the command's UTC start time and its monotonic start before it executes, and the recorded entry carries that start time. A checked non-zero exit is reported with its own integer status.

Its safe failure line comes from `_checked_failure_line`, which reads only the first physical stderr line, requires one JSON object holding an `error` identifier and an optional integer `returncode`, validates the identifier with `require_error_type(..., max_length=64)`, and rebuilds the line from those two fields alone. An absent, undecodable, malformed, extra-field or invalid first line returns `format_operator_error(exc)` instead, so the wrapper's class and checked code stand in for the child's unusable line. The exit status is `exc.returncode` in every case, and neither the returned outcome nor the sole log entry carries a message, a traceback, the child's raw line or its guidance text. Any other failure of execution, decoding or report assembly becomes status 1 and the same content-free wrapper class line, so it returns no captured stream and no exception message, and the decoded report is returned transiently only.

One fixed-label log entry is appended before either outcome, unless the invocation was an automatic read whose outcome succeeded, and a log write failure propagates rather than reporting a successful command.

The one command label comes from `_command_label`, which returns a fixed literal or a closed vocabulary combination alone. A stage label joins its admitted stage and action, a coverage, summary, setup, migration or log label joins its admitted verb, and the target, decision, dataset, configuration, backup, rebuild, administration build, administration restart, preflight and status labels name the command without the target id, the dataset id, the decision argument, a file name, a key, a value, a backup name or a branch.

## Automatic read attribution

`src/course_explorer_admin_web/routes/read_mode.py` holds the one marker reader, `automatic_read(request) -> bool`, which returns true for exactly one `X-Admin-Automatic-Read` header carrying the value `1` and false for an absent header, another value or a repeated header. The console sets that header on the reads its own loop repeats, while its explicit reload, its actions and a manual client such as `scripts/admin.py` set none.

Only a read route forwards the marker. The forwarding routes are `dashboard`, the preparation `status` and both `report` branches, the inference `status`, `summary` and `datasets`, the five logs routes, and the settings `config_files`, `config_read` and `backups`. The target read, the target decision, every lifecycle action, the hub write, the configuration save, the backup deletion, the rebuild, the administration build and its restart, the dataset enrollment and migration, the worker setup and the preflight keep the default false, so a tagged request of one of them records its own fixed entry.

`FixedCommandRunner.run(command, *, automatic=False)` omits the entry for one automatic invocation whose exit code is zero and which reported no failure line, which is a read the command completed successfully. Every failed automatic read, every explicit read, every action and every authentication event records as it does for a default invocation. The flag selects no argument, so an automatic read runs the same fixed argv as an explicit one, and it carries no admission meaning: the lock, host, origin, session and CSRF boundary and every refusal are identical for a tagged request and an untagged one.

## Tests

| Test file | Covers |
|---|---|
| `tests/admin_web/test_security.py` | The lock and the consecutive-attempt reset, the exact-site and CSRF boundary, the static shell and asset exception, idle and total expiry, credential rotation, the malformed stored credential, logout of one session, and the server-wide anonymous session budget. Two HTTP regressions prove the budget: one covers a shared budget that spares live sessions, and one covers recovery at the sliding-window boundary and the rounded `Retry-After`. |
| `tests/admin_web/test_commands.py` | The fixed argv, admitted and refused command shapes, every fixed label, the safe failures, the automatic-read entry rule, and the bounded log entries. |
| `tests/admin_web/test_routes.py` | One request per feature route mapping to one argv and one outcome, with and without the automatic marker, and the build-then-queue sequence of the administration rebuild. |
| `tests/admin_web/test_command_log_read.py` | The log read over a temporary checkout: the newest configured entries, no file created for an absent log, and no rewrite of a present one. |
| `tests/config/test_configuration_sources.py`, `tests/config/test_settings.py` | The administration family's automatic composition, its process overrides and its loopback refusal. |
| `tests/admin/test_configuration.py` | One `config/admin_web.toml` key save, one `config/admission.toml` key save, an environment-file save that preserves every other byte, the append of an absent environment key that an owning settings family declares with its refused invalid value, the refused absent subsystem-file key and the refused absent environment key that no family owns, and the refused non-loopback candidate beside a process override. |
| `tests/admin/test_operator_commands.py`, `tests/admin/test_operator_menu.py` | The password command's hidden two-entry prompt and acknowledgment, the Setup menu entry, and every cancel, end-of-input and interrupt that stores nothing. |
| `tests/web/test_boundary.py` | The course-exploration web package importing no administration module, `course_explorer_admin_web` included. |
| `admin-web/src/app/App.test.ts` | The console shell's session boundary, sign-in and refusal handling, the five mounted tab trees, and the sign-out a completed administration rebuild leaves. |
| `admin-web/src/features/inference/DatasetCleanup.test.ts` | The dataset deletion confirmation, which posts only the confirmed listed dataset and posts nothing when it is cancelled. |

`tests/admin_web/_support.py` holds the shared test support for the administration backend: a temporary site root, one real argon2id account, a controlled clock, an HTTPS-base test client and one shared process-boundary double.

The administration rebuild route test also proves the build-then-queue details: the restart tail is admitted only after the build succeeded, a build failure records one build-failure entry and no restart call, a queue failure leaves the sent build envelope intact and records the safe restart failure as its second entry, and the restart is queued only after the final response body send completes, with a failed send running no restart.

The tests never read a real site's state. They bind the credential owner to a temporary root, build the administration settings from explicit values, and serve the console from a temporary build, so no configuration file and no checkout's `data/admin-web/` directory is opened.
