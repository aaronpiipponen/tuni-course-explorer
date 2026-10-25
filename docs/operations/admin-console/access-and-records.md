# Console access and records

The administration backend admits each console request through a fixed order, writes the command log and runs the usage report over the web server's request records.

## The separate backend

The administration backend is a separate process with its own settings family and its own loopback bind. One process serves the built console shell and its assets, the three authentication routes, and the feature routes that run fixed `scripts/admin.py` commands. It starts one uvicorn worker with the access log off and proxy headers disabled.

The course-exploration web server holds no route, file or import of the administration backend or the console. The console is a separate React build, and the course-exploration package serves none of its files. The backend creates no file when it builds the application, opens no database and runs no command.

Every feature route runs one fixed command shape. A request supplies values for an admitted shape, never an executable, a script, a shell fragment or an extra argument. The [Administration backend](/docs/backend/interfaces/admin-backend.md) page describes the package, the routes and the command union. The [Administration console code](/docs/frontend/admin-console.md) page describes the browser application and its panels.

## Admission order

Every HTTP request passes one order of checks, and a refusal answers before any handler runs. The diagram shows the order and the outcome each check produces.

![A request passes the administration lock, the exact site, the built shell or asset exception, the session requirement and the CSRF check. A shell or asset read is admitted without a session. The lock, a site mismatch, a sign-in without a live session and a missing or wrong CSRF token answer an empty 403, a protected address without an authenticated session answers an empty 401, and a request for a fresh anonymous session beyond the creation limit answers an empty 429.](/docs/diagrams/admin-admission-order.svg)

### The lock

The administration lock is the first check. It reads the directory entry `data/admin-web/lock`. While any entry exists at that path, whatever its type or content, every request answers `403` with an empty body. The refusal names no reason, file or header. It covers the sign-in page, the shell, the assets, an authenticated request and an unknown address.

The lock is also checked inside the sign-in attempt, so two concurrent attempts cannot both pass the failed-attempt limit.

### The exact site

The request must carry exactly one `Host` header equal to the configured origin's host and optional port. A duplicate `Host` header is refused. The request may carry at most one `Origin` header, and a supplied origin must equal the configured `ADMIN_WEB_ORIGIN` string exactly, including its scheme and port. A state-changing request must carry one. A `null` origin and a foreign origin both fail the check.

The check reads the `Host` and `Origin` headers alone, so a forwarded host or scheme header has no effect. The backend compares `Host` with the origin's host and optional port and `Origin` with the exact origin string, even though the proxy reaches it over plain HTTP on loopback. Every failure at this check answers `403` with an empty body.

### The built console

A `GET` or `HEAD` of exactly `/` or of a path that begins `/assets/` is admitted after the lock and the exact-site checks and before any cookie is read. The built shell and its built assets need no session. The request creates no session, touches no session, runs no command and appends no record.

The address `/assets` without its trailing slash is not the static exception, and a `POST` of the shell or an asset path uses the ordinary session and CSRF flow. A request for an asset the build does not hold answers the mount's own `404` rather than another file. A build that is absent fails when it is requested.

### The session requirement

`GET /auth/session` reuses the live session of the presented cookie or creates an anonymous session within the server-wide [anonymous session creation limit](#the-anonymous-session-creation-limit). An anonymous session holds a CSRF token and grants no administration access. A `GET /auth/session` that needs a fresh anonymous grant while the limit is spent answers `429` with an empty body.

`POST /auth/login` needs a live session of any kind, anonymous or authenticated. A sign-in request without one answers `403` with an empty body. Every other address, an unknown path and a mounted file included, needs an authenticated live session. A request without one answers `401` with an empty body.

An admitted unknown address reaches the router's ordinary `404` or `405`. A session that is revoked between its admission and its refresh answers `401`.

### CSRF and admitted requests

A method other than `GET`, `HEAD` or `OPTIONS` needs the exact origin and a live session whose `X-CSRF-Token` header matches that session's token. A missing token, a wrong token, a repeated header and a non-ASCII value each answer `403` with an empty body. The comparison runs before any command and before the session's idle clock is refreshed.

An admitted request refreshes its own session's idle clock and carries that session in the request state. A websocket scope is closed with code 1008.

### Refusal outcomes

| Situation | Status | Body | Effect |
|---|---|---|---|
| The lock entry exists | `403` | Empty | No handler, command or record |
| The host or origin check fails | `403` | Empty | No handler, command or record |
| A sign-in request has no live session | `403` | Empty | No handler, command or record |
| A protected address has no authenticated session | `401` | Empty | No handler, command or record |
| A request for a fresh anonymous session beyond the creation limit | `429` | Empty | No handler, command, record or durable state, and `Retry-After` gives the wait |
| A state-changing request has no matching CSRF token | `403` | Empty | No handler, command or record, and no idle refresh |
| A credential is wrong | `401` | `{"detail":"Authentication failed"}` | One failed attempt recorded |
| A third consecutive credential failure creates the lock | `403` | Empty | The lock is created and a lock event is recorded |
| The stored credential state is malformed | `500` | `{"error":"ExceptionClass"}` | No failed attempt recorded |
| A request body fails validation after admission | `422` | `{"detail":"Invalid request"}` | No command |

The authentication routes and the request-validation failure carry `Cache-Control: no-store`. A creation-limit refusal carries it as well, together with `Retry-After`. A command that ran and failed answers `200` with the command's own nonzero `exit_code`, a null `report` and its safe `failure_line`.

## Sessions

An administration session is one signed-in grant held in the backend process's memory. A signed-in session opens the console's tabs. The session token is never written to a file or returned in a response. The session report returns the authentication state, the CSRF token, the account name and the presentation settings `poll_seconds`, `app_url` and `repository_url`.

The cookie is `__Host-course-explorer-admin` with `Secure`, `HttpOnly`, `SameSite=Strict` and `Path=/`. It carries no `Domain` attribute and no persistent `Max-Age` or `Expires` value, because the server owns the lifetime. A successful sign-in turns the anonymous session into a signed-in session, rotates the cookie to a fresh server-side token and issues a fresh CSRF token.

A session expires when the time since its last admitted request reaches `ADMIN_WEB_SESSION_IDLE_MINUTES` or the time since its creation reaches `ADMIN_WEB_SESSION_MAX_HOURS`. The example file sets 30 minutes and 12 hours. Expiry is checked at the boundary itself. An expired entry is dropped when its cookie is next resolved, and the next `GET /auth/session` creates an anonymous session when the creation limit admits one. An admitted request refreshes only the idle clock. A built shell or asset request reads no cookie and refreshes nothing, and a refused request refreshes nothing.

Several sessions may exist at once, and each expires on its own. Sign-out ends the one session that asks for it and deletes its cookie. Replacing the administration password invalidates every authenticated session on its next request, because the session is checked against the stored credential identity.

The sessions live in the process's memory. A restart of the administration backend ends every session. The administration rebuild builds the console and then restarts the backend, so it signs every operator out.

### The anonymous session creation limit

The administration backend counts the fresh anonymous sessions it grants in one sliding window, shared by every client of the process. `ADMIN_WEB_ANONYMOUS_SESSION_LIMIT` in `config/admin_web.toml` sets the count and `ADMIN_WEB_ANONYMOUS_SESSION_WINDOW_SECONDS` sets the window in seconds. The example file sets 10 sessions in 60 seconds.

Only a request that receives a fresh anonymous grant spends the count. A request that presents any live anonymous or authenticated cookie reuses its session and spends nothing, and a successful sign-in replaces the session without spending a slot. On `GET /auth/session`, a missing, unknown, expired or revoked cookie needs a fresh grant.

A fresh grant while the count is spent answers `429` with an empty body, `Cache-Control: no-store` and a positive `Retry-After` in whole seconds. The value is the wait until the oldest counted grant leaves the window, rounded up to the next whole second and never below one second. A grant exactly one window old is discarded before the count is read, so the wait never exceeds the window.

The refusal creates no session and no cookie. It records no failed sign-in, writes no command-log entry or durable state and runs no command. The creation limit is separate from the [administration lock](#failed-attempts-and-the-lock). A wrong username or password counts toward the lock and never toward this limit, and a locked site answers `403` before the limit is read. The lock, the exact site check and the shell or asset admission keep their precedence over the limit.

The count and the sessions live in the process's memory. A restart of the administration backend clears the count. The [Administration backend](/docs/backend/interfaces/admin-backend.md#sessions) page states how the security owner tracks the window and raises the refusal.

## The administration account

Each site holds one administration account in `data/admin-web/password`, a JSON document with the username and an argon2id encoded hash. The file is published at mode 0600 under a mode-0700 state directory. The password itself is never written, echoed or acknowledged.

Set the account with the administration command's password entry, which prompts for the password twice at a hidden prompt. The [Operator menu](/docs/operations/operator-menu.md#the-administration-password) page states the entry and its prompts, and [self-hosting](/docs/getting-started/self-hosting.md#the-administration-account) states the setup step. The command writes the credential file alone and changes neither the lock nor the failed-attempt count.

A sign-in verifies the stored argon2id hash before it compares the username. A wrong username or password answers `401` with `{"detail":"Authentication failed"}` and records one failed attempt. A malformed or unreadable stored hash raises an operational failure, which answers `500` with a content-free error and records no failed attempt.

## Failed attempts and the lock

The diagram shows the session states beside the failed-attempt count and the lock.

![An anonymous session becomes a signed-in session on a correct sign-in, and the signed-in session expires after its idle or total lifetime. Failed sign-ins accumulate in the failed-attempt count, and the third consecutive failure creates the administration lock. A correct sign-in resets the count and deleting the lock file ends the refusal.](/docs/diagrams/admin-sign-in-states.svg)

The failed-attempt count is a JSON document at `data/admin-web/failed-logins` with one `count` member. The file is published at mode 0600 under the state directory, and a missing file means zero. The limit of three consecutive failures is fixed in code rather than configured.

A failed sign-in increments the count and appends one `failed-login` entry to the command log. The third consecutive failure creates the file `data/admin-web/lock` and appends one `lock` entry with exit code `403` and duration `0.0`. The first two failures answer `401` with the authentication failure detail. The third answers `403` with an empty body.

The lock is the file itself. The check reads the directory entry alone, so a dangling symlink, a directory and a nonempty file each lock the site exactly as an empty regular file does. While the entry exists, every request answers `403` with an empty body, including an authenticated session and a request for the shell or an asset.

Clearing the lock is a manual step in the checkout that runs the backend: delete the whole entry at `data/admin-web/lock`. The deletion leaves the failed-attempt count in place, so a wrong sign-in creates the lock again. A correct sign-in resets the count to zero. A valid authenticated cookie that is within its lifetime works again once the entry is deleted, and that use of the session leaves the count in place.

## The command log

The command log is the file `data/admin-web/command-log`. It holds the last `ADMIN_WEB_COMMAND_LOG_LIMIT` entries in oldest-first order, and the example file sets 200 entries. An append retains the last entries and rewrites the same file under one exclusive lock. A read returns the last entries and rewrites nothing. A missing file is an empty report. A malformed or unreadable line fails the read instead of being repaired or skipped.

| Field | Content |
|---|---|
| `time` | The entry's UTC time |
| `command` | A fixed command label chosen from source text |
| `exit_code` | The command's integer exit code |
| `duration_seconds` | The monotonic elapsed duration |
| `result` | `success`, `failure`, `login`, `failed-login` or `lock` |
| `failure_line` | At most one line of 200 characters naming an exception class and an optional return code |

A successful sign-in appends one `login` entry with exit code `0`. A failed sign-in appends `failed-login` with exit code `1`. The failure that creates the lock appends `lock` with exit code `403` and duration `0.0`. The three events use the same file and the same entry shape as a command outcome.

Every fixed command that runs appends its entry, including a command that failed. A successful read that the console issues automatically appends no entry, while a failed automatic read appends one. The successful automatic reads are the dashboard, the preparation status and report reads, the inference status, summary and dataset listing, the five log reads, the configuration file listing and read, and the backup listing. The target read, the target decision, every stage and inference action, the hub write, a configuration save, a backup deletion and every maintenance action append an entry even when the request carries the automatic-read marker.

An entry holds no captured command output beyond the one safe failure line. It holds no password, key value, session token or free-form command argument, and no target id, dataset id, file name or branch name.

The [Command log panel](/docs/operations/admin-console/logs.md#command-log) reads the log in the console. The operator menu's Server and log reads choice five runs the same read and prints the entries oldest first. The [Operator menu](/docs/operations/operator-menu.md#the-command-log-read) page states the entry and the machine command. An explicit read of the log appends its own `logs commands` entry, while an automatic console read appends none.

## Request records and the usage report

The course-exploration web server's front router appends one request record to `data/usage/requests` for every HTTP request it answers. The file is mode 0600, and one record is one JSON line. It holds the request-start UTC hour rounded down, a fixed route label, the response status and the elapsed seconds. The route label comes from the request path: `/` and `/docs` report themselves, one of the nine fixed API paths reports that path, `/assets` covers a served or a missing asset, and every other path reports `unmatched`. The record holds no requested path, query, header, user agent, network address or course data.

The status is the response's own status, or `500` when a handler fails before it starts a response. The administration backend appends no request record. The usage file counts course-exploration requests alone.

`USAGE_RETENTION_DAYS` in `config/web.toml` sets the retention, and the example file sets 30 days. The usage report retains the records from the current rounded UTC hour back that many days inclusive and prunes the older records each time it runs.

The report takes a positive whole number of hours. Its window is the current rounded UTC hour and the preceding hours, inclusive. A count longer than the retention in hours is refused before the file is opened, and a nonpositive count is refused. The report returns the window bounds, the request count, the mean duration and one row per route sorted by route. A window with no recorded request reports zero requests, a null mean and no route rows. A missing file returns that report and creates nothing, and a malformed line fails the report without rewriting the file.

The [Usage panel](/docs/operations/admin-console/logs.md#usage) reads the report in the console. The operator menu's Server and log reads choice four runs the same report, and the [Operator menu](/docs/operations/operator-menu.md#the-usage-report) page states the window and the pruning side effect.

## Settings

`config/admin_web.toml` holds the 11 required keys of the administration backend. The example file sets these values.

| Key | Meaning | Unit | Example |
|---|---|---|---|
| `ADMIN_WEB_HOST` | The loopback address the backend binds | Address | `127.0.0.1` |
| `ADMIN_WEB_PORT` | The TCP port the backend binds | Port | `8039` |
| `ADMIN_WEB_ORIGIN` | The exact HTTPS origin compared with `Host` and `Origin` | URL | `https://localhost:8039` |
| `ADMIN_WEB_SESSION_IDLE_MINUTES` | The idle lifetime of one session | Minutes | `30` |
| `ADMIN_WEB_SESSION_MAX_HOURS` | The total lifetime from session creation | Hours | `12` |
| `ADMIN_WEB_ANONYMOUS_SESSION_LIMIT` | The fresh anonymous sessions one process grants in the window | Sessions | `10` |
| `ADMIN_WEB_ANONYMOUS_SESSION_WINDOW_SECONDS` | The length of the sliding window | Seconds | `60` |
| `ADMIN_WEB_COMMAND_LOG_LIMIT` | The entries the command log retains | Entries | `200` |
| `ADMIN_WEB_POLL_SECONDS` | The seconds between completed automatic reads of one enabled panel | Seconds | `60` |
| `ADMIN_WEB_APP_URL` | The absolute address of the console's App link | URL | `http://localhost:8037/` |
| `ADMIN_WEB_REPOSITORY_URL` | The HTTPS GitHub owner and repository address of the console's GitHub link | URL | `https://github.com/aaronpiipponen/tuni-course-explorer` |

The host must be `127.0.0.1`, and the port must be a valid TCP port. The origin must be one exact HTTPS origin without credentials, a path, a query or a fragment. The app address must be an absolute HTTP or HTTPS address at the root. The repository address must name one owner and one repository on `github.com` over HTTPS. The two session lifetimes, the creation limit, its window, the command-log limit and the poll interval are positive integers.

The session report returns the values of `ADMIN_WEB_POLL_SECONDS`, `ADMIN_WEB_APP_URL` and `ADMIN_WEB_REPOSITORY_URL` as the console's presentation metadata. The lock path and the failed-attempt limit are fixed in code. [Configuration](/docs/backend/configuration.md) states how the settings owner reads and validates the file.

## Related pages

The [Administration console how-to](/docs/operations/admin-console/README.md) describes the console's tabs and their actions. The [Administration backend](/docs/backend/interfaces/admin-backend.md) and [Administration console code](/docs/frontend/admin-console.md) pages describe the implementation. [Configuration](/docs/backend/configuration.md) states the settings composition, and [self-hosting](/docs/getting-started/self-hosting.md#the-administration-account) states the first account and the deployment steps.
