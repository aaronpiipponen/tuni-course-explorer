# Self-hosting

Self-hosting runs an installed copy as a service on a Linux host and serves it over HTTPS through a reverse proxy.

The administration backend runs from a systemd user unit, and the site runs from a user unit or a system unit. One reverse proxy publishes both sites on separate interfaces.

## What the host needs

- A copy set up by the [Installation](/docs/getting-started/installation.md) steps, including the built browser app, the built console and the loaded example dataset.
- Two domain names. The site domain resolves to the interface that serves the site, and the administration domain resolves to the interface that serves the console. Every command on this page uses `example.org` and `admin.example.org` in their place.
- Caddy, run from the built container image, which terminates TLS for both domains and forwards requests to the two loopback backends. It binds port 443 on the two interface addresses and needs no port 80 listener.
- A DuckDNS API token for the administration certificate, supplied at run time in the Caddy container's environment.
- systemd as the service manager, because both servers run from systemd units, and the site unit runs under the user manager or the system manager.
- An account that may run `loginctl enable-linger`, the `systemctl --user` commands, `sudo -n docker`, and ordinary `sudo` for the one-time installation of a system unit and its restart grant.
- The GitHub CLI `gh` on the sender service's `PATH`, from a release whose `gh issue create` documents `--attach` and `--body-file -`.

## The two startup modes

The example workflow and the real-database workflow ask whether the two backends run as user units or as foreground children of the setup command.

**User units** derives one prefix from the checkout directory's basename, `course-explorer-<basename>`, and appends `-web`, `-admin-web` and `-feedback-sender`. It renders the four `examples/deploy/systemd/*.in` templates into `~/.config/systemd/user/`, replacing `@CHECKOUT@`, `@UV_BIN@` and the feedback timer's paired service name. An identical rendered unit is reused, and a different file refuses. The workflow writes the two derived service names and the `user` scope into `config/admin_web.toml`, verifies the four units with `systemd-analyze --user verify`, reloads the user manager, and enables and starts the two backend services. It enables the sender timer only when publication setup was requested and the configured destination is a real repository.

The user manager starts these units at boot only with lingering enabled. The workflow prints `loginctl enable-linger USER` when the account has no lingering, and it changes no lingering policy itself.

**Foreground** starts `scripts/run_web.sh` and `scripts/run_admin_web.sh` as children of the setup command with the terminal's own streams. It proves both backends, prints the Ctrl-C notice, and waits while polling those two children. Ctrl-C terminates and reaps them and returns the workflow report. A child that exits before the operator stops the pair fails the setup. The database and the embedding service continue running, and the terminal states that fact.

Both modes preserve the working files and credentials. A present `config/`, `.env`, `docker-compose.yml` or `deploy/` file is preserved byte for byte, both generated database passwords live in `.env`, and a present administration account is not reset. A second example run refuses at the example database's user-table check before it imports anything.

The sections below install the units by hand for a host whose names or values differ from the derived ones. The proxy, DNS and certificate are operator steps in every mode, and the workflows install no proxy.

## The site web unit

The template `examples/deploy/systemd/tuni-course-explorer-web.service.in` starts the web server through `scripts/run_web.sh`, which binds the loopback address from `config/web.toml`. Copy it into `deploy/` under the template's name without the `.in` suffix, then replace `@CHECKOUT@` with the absolute path of the checkout.

```bash
cp examples/deploy/systemd/tuni-course-explorer-web.service.in deploy/tuni-course-explorer-web.service
sed -i "s|@CHECKOUT@|/path/to/checkout|g" deploy/tuni-course-explorer-web.service
```

The unit's directives and what each one does:

| Directive | Effect |
|---|---|
| `WorkingDirectory=@CHECKOUT@` | Starts the process in the checkout, which is where `scripts/run_web.sh` finds `.venv/bin/python` |
| `ExecStart=/usr/bin/bash @CHECKOUT@/scripts/run_web.sh` | Runs the launcher with the bash path the unit names |
| `Restart=on-failure`, `RestartSec=5` | Starts the service again five seconds after it exits with a failure |
| `NoNewPrivileges=true` | Applies the no-new-privileges flag to the process and its children |
| `UMask=0077` | Gives files the service creates owner-only access |
| `Nice=5` | Starts the web processes five levels below the default priority, so web CPU yields to the database, the embedding service and the other services of the host |
| `StandardOutput=null`, `StandardError=journal` | Sends the error stream to the journal and discards the standard stream |
| `WantedBy=default.target` | The user manager's default target pulls in the user unit. A system unit sets `WantedBy=multi-user.target` instead. |

Install the unit as a user unit, enable lingering so it runs without a login session, then enable and start it:

```bash
mkdir -p ~/.config/systemd/user
cp deploy/tuni-course-explorer-web.service ~/.config/systemd/user/
loginctl enable-linger "$(id -un)"
systemctl --user daemon-reload
systemctl --user enable --now tuni-course-explorer-web.service
systemctl --user status tuni-course-explorer-web.service
```

The status output shows `active (running)`. The service answers on the loopback host and port from `config/web.toml` on its own, before the reverse proxy is in place. The error stream goes to the journal:

```bash
journalctl --user-unit tuni-course-explorer-web.service
```

The site unit runs under the user manager or the system manager, and both start the same server from the same checkout. Both bind the loopback host and port from `config/web.toml`, so exactly one web unit runs at a time. `ADMIN_SITE_WEB_SERVICE_SCOPE` states which manager owns the installed unit.

1. Stop and disable the user web unit, if the host installed one.

   ```bash
   systemctl --user disable --now tuni-course-explorer-web.service
   ```

   The command stops the unit and removes it from the user manager's default target, so the two placements never hold the same port.

2. Render the template with the checkout path.

   ```bash
   cp examples/deploy/systemd/tuni-course-explorer-web.service.in deploy/tuni-course-explorer-web.service
   sed -i "s|@CHECKOUT@|/path/to/checkout|g" deploy/tuni-course-explorer-web.service
   ```

   Add the three directives to the `[Service]` section, naming the ordinary account that owns the checkout, that account's own group and the account's home directory:

   ```text
   User=OPERATOR_ACCOUNT
   Group=OPERATOR_ACCOUNT
   Environment=HOME=/path/to/home
   ```

   Replace `WantedBy=default.target` in the `[Install]` section with `WantedBy=multi-user.target`.

3. Verify the rendered unit.

   ```bash
   systemd-analyze verify deploy/tuni-course-explorer-web.service
   ```

   A unit that parses and names a launcher present at its path prints no output, and a missing `ExecStart` path or an unknown directive is reported.

4. Install the unit for the system manager and start it.

   ```bash
   sudo install -m 0644 -o root -g root deploy/tuni-course-explorer-web.service /etc/systemd/system/tuni-course-explorer-web.service
   sudo systemctl daemon-reload
   sudo systemctl enable --now tuni-course-explorer-web.service
   systemctl status tuni-course-explorer-web.service
   ```

   The installed unit file is root-owned and readable, the system manager reloads it, and the server starts and is enabled for the next boot. The status output shows `active (running)`, and the server answers on the loopback host and port from `config/web.toml` before the reverse proxy is in place.

5. Grant the one restart the app rebuild runs.

   The app rebuild restarts the web unit with exactly `sudo -n /usr/bin/systemctl restart <unit>`. Create the sudoers file with owner-only access, then write one passwordless grant line into it for the account that owns the checkout:

   ```bash
   install -m 600 /dev/null deploy/tuni-course-explorer-web.sudoers
   ```

   ```text
   OPERATOR_ACCOUNT ALL=(root) NOPASSWD: /usr/bin/systemctl restart tuni-course-explorer-web.service
   ```

   Validate the line and install the file with the sudoers mode:

   ```bash
   sudo visudo -cf deploy/tuni-course-explorer-web.sudoers
   sudo install -m 0440 -o root -g root deploy/tuni-course-explorer-web.sudoers /etc/sudoers.d/tuni-course-explorer-web
   ```

   The check reports `<file>: parsed OK` for a line that parses, and the installed file is root-owned with mode 0440. The file name carries no dot, because the sudoers directory skips a file whose name contains one. The line grants that one restart command, which is the only elevation the app rebuild runs for the web unit.

6. Set the three site keys in `config/admin_web.toml` with the system scope.

   ```toml
   ADMIN_SITE_WEB_SERVICE_UNIT = "tuni-course-explorer-web.service"
   ADMIN_SITE_WEB_SERVICE_SCOPE = "system"
   ADMIN_SITE_ADMIN_SERVICE_UNIT = "tuni-course-explorer-admin-web.service"
   ```

   The status report and the app rebuild read the web unit from the system manager. The administration unit is always a user unit under the user manager.

7. Check the unit and the administration read.

   ```bash
   systemctl is-active tuni-course-explorer-web.service
   systemctl is-enabled tuni-course-explorer-web.service
   systemctl show tuni-course-explorer-web.service -p LoadState -p WorkingDirectory -p ExecStart
   uv run python scripts/admin.py server status
   ```

   The first two checks print `active` and `enabled`, and the property read prints the loaded state, the checkout as the working directory and the command line that runs the checkout's `scripts/run_web.sh`. `server status` prints its report, whose website member names the unit and reports its state.

   An account that may read the system journal reads the unit's error stream with:

   ```bash
   journalctl -u tuni-course-explorer-web.service
   ```

A host that confines the checkout with its own security policy needs that policy to admit the checkout path before the server starts.

## The administration unit

The template `examples/deploy/systemd/tuni-course-explorer-admin-web.service.in` starts the administration backend through `scripts/run_admin_web.sh`. Render it into the user unit directory, replacing `@CHECKOUT@` with the checkout path and `@UV_BIN@` with the directory that holds the `uv` executable:

```bash
sed -e "s|@CHECKOUT@|/path/to/checkout|g" \
  -e "s|@UV_BIN@|/path/to/uv/bin|g" \
  examples/deploy/systemd/tuni-course-explorer-admin-web.service.in \
  > ~/.config/systemd/user/tuni-course-explorer-admin-web.service
systemd-analyze --user verify ~/.config/systemd/user/tuni-course-explorer-admin-web.service
```

The unit's directives and what each one does:

| Directive | Effect |
|---|---|
| `WorkingDirectory=@CHECKOUT@` | Starts the process in the checkout, which is where `scripts/run_admin_web.sh` finds `.venv/bin/python` |
| `ExecStart=/usr/bin/bash @CHECKOUT@/scripts/run_admin_web.sh` | Runs the administration launcher with the bash path the unit names |
| `Environment=PATH=@UV_BIN@:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin` | Supplies the executable search path, including the directory that holds `uv` for the fixed commands |
| `Restart=on-failure`, `RestartSec=5` | Starts the service again five seconds after it exits with a failure |
| `NoNewPrivileges=false` | Permits the fixed commands to run `sudo -n docker` for the Compose operations |
| `UMask=0077` | Gives the administration state files owner-only access |
| `StandardOutput=null`, `StandardError=journal` | Sends the error stream to the journal and discards the standard stream |
| `WantedBy=default.target` | The user manager's default target pulls in the unit |

The unit supplies its own executable search path, and the directory that holds `uv` comes first, so the fixed commands find `uv` and then the system executables. Docker access runs through `sudo`, and the account needs no Docker group membership.

Enable and start the unit after reloading the user manager:

```bash
systemctl --user daemon-reload
systemctl --user enable --now tuni-course-explorer-admin-web.service
systemctl --user status tuni-course-explorer-admin-web.service
```

The status output shows `active (running)`. The backend answers the built console shell on the loopback host and port from `config/admin_web.toml` for a request whose `Host` header carries the host and port of `ADMIN_WEB_ORIGIN`. The error stream goes to the journal:

```bash
journalctl --user-unit tuni-course-explorer-admin-web.service
```

## The feedback sender unit

The templates `examples/deploy/systemd/tuni-course-explorer-feedback-sender.service.in` and `tuni-course-explorer-feedback-sender.timer.in` run one bounded publication attempt. The user-mode workflow renders both with the checkout's derived unit names and enables the timer only for explicit publication setup whose configured destination is a real repository. The commands below render the templates under their tracked basenames for a manual installation. Render both into the user unit directory, replacing `@CHECKOUT@` in the service with the checkout path:

```bash
sed "s|@CHECKOUT@|/path/to/checkout|g" \
  examples/deploy/systemd/tuni-course-explorer-feedback-sender.service.in \
  > ~/.config/systemd/user/tuni-course-explorer-feedback-sender.service
cp examples/deploy/systemd/tuni-course-explorer-feedback-sender.timer.in \
  ~/.config/systemd/user/tuni-course-explorer-feedback-sender.timer
systemd-analyze --user verify \
  ~/.config/systemd/user/tuni-course-explorer-feedback-sender.service \
  ~/.config/systemd/user/tuni-course-explorer-feedback-sender.timer
```

The service is a one-shot activation that runs `scripts/run_feedback_sender.sh`, and the timer starts it after boot and after each completed activation. Enable only the timer:

```bash
systemctl --user daemon-reload
systemctl --user enable --now tuni-course-explorer-feedback-sender.timer
systemctl --user status tuni-course-explorer-feedback-sender.timer
```

The status output shows `active (waiting)`. The service sends its content-safe failure lines to the journal, and the feedback record and its administration view own the publication outcome, identity and link:

```bash
systemctl --user start tuni-course-explorer-feedback-sender.service
journalctl --user-unit tuni-course-explorer-feedback-sender.service
systemctl --user disable --now tuni-course-explorer-feedback-sender.timer
```

The sender reads `FEEDBACK_GITHUB_TOKEN` from the environment file and the destination, visibility and timeout from `config/feedback.toml`. The feedback application store must exist at the configured connection and carry the feedback chain at its head:

```bash
uv run python -m alembic -c alembic_feedback.ini upgrade head
```

The example workflow creates the feedback role, its database and the attachment root at `FEEDBACK_ATTACHMENTS_ROOT`, then applies the chain. When that workflow has not created them, create the role and database named by `FEEDBACK_POSTGRES_USER` and `FEEDBACK_POSTGRES_DB` on the curriculum cluster with the `FEEDBACK_POSTGRES_PASSWORD` value before this command runs. A pending opted-in submission is published only by one sender activation, and an operator inspects the destination repository after an unconfirmed outcome.

## The deployment runner

A push to the main branch of `aaronpiipponen/tuni-course-explorer` deploys this checkout from a self-hosted GitHub Actions runner. The workflow's deploy job runs only in that repository and only after the verification job succeeds, and it selects a runner that carries the labels `self-hosted`, `linux`, `ARM64` and `tuni-deploy`. It deploys only when its own checkout is on main, holds no uncommitted or untracked change, and is at the commit the verification job tested. A checkout that fails one of those conditions prints a `not deployed` line naming the reason and exits with status 0. The template `deploy/systemd/course-explorer-actions-runner.service.in` starts the runner from its own directory, sets its home directory and executable search path, gives the files it writes owner-only access, starts it again after a failure, and permits the passwordless restart of the feature web unit that the deployment runs.

Render the template with the runner directory and the account's home directory, verify it, then install and start it under the user manager:

```bash
sed -e "s|@RUNNER@|/path/to/actions-runner|g" \
  -e "s|@HOME@|/path/to/home|g" \
  deploy/systemd/course-explorer-actions-runner.service.in \
  > ~/.config/systemd/user/course-explorer-actions-runner.service
systemd-analyze --user verify ~/.config/systemd/user/course-explorer-actions-runner.service
systemctl --user daemon-reload
systemctl --user enable --now course-explorer-actions-runner.service
```

The unit runs `/path/to/actions-runner/run.sh`, so register that runner with the repository, the name `tuni-deploy` and those four labels before the first start. `deploy/deploy.sh` restarts the feature web unit with `sudo -n /usr/bin/systemctl restart` and the administration unit with `systemctl --user restart`, so the deployment host installs the feature web unit under the system manager and the administration unit under the user manager of the account that runs the runner. That account needs the passwordless restart grant that [the system installation](#the-site-web-unit) writes. The user manager starts the runner at boot only with lingering enabled, as [the two startup modes](#the-two-startup-modes) states.

`deploy/deploy.sh` sources the values in `deploy/serving.conf` beside it. Copy the tracked example and set the unit names and loopback ports this host uses:

```bash
cp examples/deploy/serving.conf deploy/serving.conf
```

| Value | Holds |
|---|---|
| `DEPLOY_WEB_UNIT` | The systemd unit of the feature web server |
| `DEPLOY_WEB_PORT` | The loopback port the feature web server binds |
| `DEPLOY_ADMIN_UNIT` | The systemd user unit of the administration backend |
| `DEPLOY_ADMIN_PORT` | The loopback port the administration backend binds |

The example file names `tuni-course-explorer-web.service` on port 8037 and `tuni-course-explorer-admin-web.service` on port 8039, the example values of `WEB_PORT` and `ADMIN_WEB_PORT`.

## The site unit identities

The administration Dashboard reports the site's web unit, while the administration build and restart validate the administration unit. The runtime `config/admin_web.toml`, copied from its tracked `examples/config/` counterpart, names both and states the manager of the web unit, and the administration command reads all three values:

```toml
ADMIN_SITE_WEB_SERVICE_UNIT = "course-explorer-checkout-web.service"
ADMIN_SITE_WEB_SERVICE_SCOPE = "user"
ADMIN_SITE_ADMIN_SERVICE_UNIT = "course-explorer-checkout-admin-web.service"
```

The user-mode workflow writes the two derived service names and the `user` scope into this file. The manual unit installation above writes the names it installs. The values are the unit names installed on this host. `ADMIN_SITE_WEB_SERVICE_SCOPE` names the manager that owns the web unit, either `user` or `system`, and the example sets `user`. The scope applies to the web unit alone, and the administration unit always belongs to the user manager.

The status report and the app rebuild read the web unit from the manager the scope names, and each requires a loaded unit whose `WorkingDirectory` is the checkout and whose `ExecStart` carries the checkout's `scripts/run_web.sh`. The administration build and restart require the same of the administration unit with `scripts/run_admin_web.sh`. Under the system scope the app rebuild restarts the web unit with `sudo -n /usr/bin/systemctl restart <unit>` and needs the one grant that [the system installation](#the-site-web-unit) writes. A missing unit name fails the read and names the key, and a missing scope uses `user`.

## The web settings

`config/web.toml` holds the keys a serving host sets:

| Key | Example value | Meaning |
|---|---|---|
| `WEB_APP_URL` | `http://localhost:8037/` | The external root address of this site. The administration console's App link opens it, and the feedback exact Host and Origin boundary is this address without its optional trailing slash. It names the external app, not the loopback proxy target. |
| `WEB_PORT` | `8037` | The port the server binds, and the port the reverse proxy targets. |
| `WEB_EMBEDDINGS_ENABLED` | `true` | Whether the site serves semantic matching, comparison and the recommended courses, and mounts their controls. It also decides which artifacts the build writes and the supervisor opens, as [Serving artifact build](/docs/backend/text-and-vectors/serving-artifact-build.md#the-embedding-switch) states. |
| `WEB_INFERENCE_ENABLED` | `true` | Whether the site serves inferred prerequisites and mounts the controls and marks that describe them. Inference has no serving artifact and no coverage gate. |

The same file holds the bind address, the worker process count, the malloc arenas and the two respawn bounds, and [Configuration](/docs/backend/configuration.md#subsystem-keys) states every key of the administration file, and [Prerequisite graph](/docs/backend/prerequisites/prerequisite-graph.md) states the drawing limit that the same file sets.

The serving processes read these values when they start, so a changed value reaches the site when the unit starts it again. Turning `WEB_EMBEDDINGS_ENABLED` off needs a restart alone. Turning it on needs the running embedding configuration's embedding directory in the artifact family, so run `uv run python scripts/admin.py serving-artifacts` before the web unit starts when the family holds none for that configuration. [Serving artifact build](/docs/backend/text-and-vectors/serving-artifact-build.md#the-embedding-switch) states each mode. `WEB_APP_URL` is one root HTTP or HTTPS address, with HTTPS required unless the hostname is `localhost`, `127.0.0.1` or `::1`. A deployed site states its external address here rather than the loopback proxy target. The front router and the workers are described in [Front router](/docs/backend/interfaces/front-router.md), and the launcher and the supervisor in [Web supervisor](/docs/backend/interfaces/web-supervisor.md).

`USAGE_RETENTION_DAYS` in the same file is not a serving value. It sets how many days of request records the usage report keeps, and the report refuses a requested hour window longer than that retention in hours. The example keeps 30 days, so a window longer than 720 hours is refused. The front router appends one request record per request, and an operator reads the aggregates or prunes the old records with:

```bash
uv run python scripts/admin.py usage --hours 24
```

[Administration commands](/docs/backend/interfaces/administration-commands.md#the-request-usage-report) states the window, the report fields and the pruning side effect, and [Front router](/docs/backend/interfaces/front-router.md#the-request-usage-record) states the record the front router appends.

## The administration settings

`config/admin_web.toml` holds the keys a deployed host sets:

| Key | Example value | Meaning |
|---|---|---|
| `ADMIN_WEB_PORT` | `8039` | The port the backend binds, and the port the reverse proxy targets. |
| `ADMIN_WEB_ORIGIN` | `https://localhost:8039` | The one exact HTTPS origin. The `Host` header must carry its host and port, and a supplied `Origin` must equal it. |

The same file holds the bind address, the two session lifetimes, the anonymous session limit and window, the command-log limit, the console poll interval and the console's repository address. [Configuration](/docs/backend/configuration.md#subsystem-keys) states every administration key.

`ADMIN_WEB_ANONYMOUS_SESSION_LIMIT` and `ADMIN_WEB_ANONYMOUS_SESSION_WINDOW_SECONDS` set one server-wide anonymous session creation limit for the backend process, and a live anonymous or signed-in session consumes none of it. The counted creation times live in the process's memory, so a restarted backend counts from zero. A saved value reaches the backend when the unit starts it again.

The example file under `examples/config/` describes a development instance with the bind `127.0.0.1:8039` and the origin `https://localhost:8039`. A deployed host sets its own origin in `config/admin_web.toml` and its external app address in `config/web.toml`. The same administration file holds the three site keys, which state this host's two service basenames and the manager of the web unit.

Every key of the file is required, and a missing key fails the settings read and names the key. The exception is `ADMIN_SITE_WEB_SERVICE_SCOPE`, whose missing value uses `user`. The backend compares the `Host` header with the host and port of `ADMIN_WEB_ORIGIN`. It compares an `Origin` header with the configured origin only when the request supplies one, and it refuses a state-changing request that supplies no `Origin`. [Administration backend](/docs/backend/interfaces/admin-backend.md) states the admission and session behavior.

## The administration account

Set the account over SSH with the credential command, which prompts for the password twice without echoing it:

```bash
uv run python scripts/admin.py password --username USERNAME
```

The command writes the username and an argon2id hash to `data/admin-web/password` with owner-only access. The example workflow creates the account only when that file is absent and never resets or reads back a present account. Three consecutive failed sign-ins create `data/admin-web/lock`, and while that file exists the backend answers every request with an empty `403`. Delete the whole file over SSH to end the lock. [Console access and records](/docs/operations/admin-console/access-and-records.md) describes the sign-in, the lock and the command log, and [Administration backend](/docs/backend/interfaces/admin-backend.md#the-failed-attempt-count-and-the-lock) states the count and the lock.

## The console build

The administration console is a separate browser app with its own build, served at the administration domain. [Administration console](/docs/operations/admin-console/README.md) describes how to open it, sign in and use its tabs.

```bash
npm --prefix admin-web ci --engine-strict --no-audit --no-fund
npm --prefix admin-web run build
```

The build writes `admin-web/dist`, which the backend serves from the checkout on each request. A change to the backend's own code or settings reaches the administration site when its unit starts again. The console's **Rebuild admin panel** action runs the build and then queues a restart of its own unit, which ends every signed-in session.

## HTTPS with a reverse proxy

The setup workflows install no proxy. The proxy, the two domains, the DNS records and the certificate are explicit operator steps, and the commands below render and run the template.

The template `examples/deploy/Caddyfile` terminates TLS for both domains and forwards each site to its loopback backend:

```bash
cp examples/deploy/Caddyfile deploy/Caddyfile
```

The site configuration takes the two domains and the two bind addresses from Caddy's own process environment, and the container command under [The Caddy container and its storage](#the-caddy-container-and-its-storage) supplies them as explicit values. The two uppercase values are placeholders for the host's interface addresses. The environment file supplies `DUCKDNS_API_TOKEN` as that section describes.

The template's global block turns the admin endpoint off and disables the automatic HTTP-to-HTTPS redirects, so Caddy serves both domains over HTTPS alone. Each site block binds one interface address explicitly, so the site answers on the internet-facing interface and the administration site on a separate interface alone.

The site asks for a certificate through an ACME issuer with the HTTP challenge disabled, so the certificate is issued through TLS-ALPN-01 on port 443. The administration site disables the HTTP and TLS-ALPN challenges and uses the DuckDNS DNS challenge, because its domain resolves to an interface address that the certificate authority cannot reach. Its token placeholder `{env.DUCKDNS_API_TOKEN}` is read by the DNS provider when it provisions, not substituted into the configuration text. The DuckDNS provider comes from the image that [The Caddy image](#the-caddy-image) builds, and Caddy runs from that image.

The site proxy target is `127.0.0.1:8037`, the value of `WEB_PORT` in the example, and the administration target is `127.0.0.1:8039`. Set `ADMIN_WEB_PORT` to that value in `config/admin_web.toml`. [Configuration](/docs/backend/configuration.md) and [System boundaries](/docs/architecture/boundaries.md) describe how the settings reach the processes and what each serving side can do.

## The Caddy image

The administration certificate needs the DuckDNS DNS challenge provider, which the upstream Caddy image does not contain. `examples/deploy/caddy.Dockerfile` builds one image from the pinned builder and runtime manifests and the pinned provider module. Build it once with the Dockerfile on standard input, so the checkout is not a build context:

```bash
sudo -n docker build -t caddy-duckdns:2.11.7 - < examples/deploy/caddy.Dockerfile
```

The build creates the local image `caddy-duckdns:2.11.7`, the tag the container command names. The build takes no environment file, token, runtime configuration or secret build argument.

## The Caddy container and its storage

The DuckDNS token lives in one environment file at `deploy/caddy.env`, with one assignment. The file is not tracked by Git. Create it with owner-only access, then write the assignment:

```bash
install -m 600 /dev/null deploy/caddy.env
```

```text
DUCKDNS_API_TOKEN=token-value
```

Caddy receives that file as its only environment file and reads the token from its own environment. Its site domains and interface addresses reach it as explicit environment values. Run the container on the host network with the two interface addresses bound by the Caddyfile, and mount the Caddyfile read-only with two owner-only directories for the certificate and configuration state:

```bash
mkdir -p ~/.local/share/caddy-duckdns
install -d -m 0700 ~/.local/share/caddy-duckdns/data ~/.local/share/caddy-duckdns/config
sudo -n docker run -d --name caddy-duckdns --network host --restart unless-stopped \
  --env-file /path/to/checkout/deploy/caddy.env \
  --env COURSE_EXPLORER_WEB_DOMAIN=example.org \
  --env COURSE_EXPLORER_WEB_BIND=WEB_INTERFACE_ADDRESS \
  --env COURSE_EXPLORER_ADMIN_DOMAIN=admin.example.org \
  --env COURSE_EXPLORER_ADMIN_BIND=ADMIN_INTERFACE_ADDRESS \
  -v /path/to/checkout/deploy/Caddyfile:/etc/caddy/Caddyfile:ro \
  -v ~/.local/share/caddy-duckdns/data:/data \
  -v ~/.local/share/caddy-duckdns/config:/config \
  caddy-duckdns:2.11.7
```

The `/data` directory holds the issued certificates and the ACME account state. The `/config` directory holds Caddy's autosaved configuration. Mount both, so a container start reads the issued certificate.

> [!CAUTION]
> Caddy's logs and diagnostics are credential-bearing. The DuckDNS provider includes its token in a failed API request, so a certificate failure can write the token to the container log. Do not read, print, grep or share the container log, its configuration dump or its process environment. Investigate a failed certificate with the probes below, and rotate the token if a log leaves the host.

## Certificate and HTTP probes

Probe each site through the interface it binds, with certificate verification enabled:

```bash
web_address=WEB_INTERFACE_ADDRESS
admin_address=ADMIN_INTERFACE_ADDRESS
curl -fsS --resolve "example.org:443:$web_address" https://example.org/ -o /dev/null
curl -fsS --resolve "admin.example.org:443:$admin_address" https://admin.example.org/ -o /dev/null
```

The two uppercase values are placeholders for the interface addresses the site binds. A zero exit proves that Caddy answers, that the certificate chain verifies against the system trust store and that the served certificate names the requested domain. Inspect the served certificate directly when the domain or the chain is in question:

```bash
openssl s_client -connect "$admin_address:443" -servername admin.example.org \
  -verify_hostname admin.example.org -verify_return_error </dev/null
```

The administration backend binds loopback alone, so a direct request to its port from another host refuses the connection. A probe of the public interface with the administration domain answers no administration content.

## The services and the served site

The database and the embedding service run from `docker-compose.yml` at the checkout root, and each declares `restart: unless-stopped`. Docker starts them again after a host reboot unless an operator stopped them. Start and inspect them through the Compose wrapper:

```bash
uv run python -m course_explorer_admin.compose -- up -d --wait db embedding
uv run python -m course_explorer_admin.compose -- ps
```

The Compose file publishes the database port on `127.0.0.1` alone, at the value of `POSTGRES_PORT` in `config/database.toml`, so the database answers the host and not the network. The embedding service listens on the loopback port from `config/search.toml`, and the web server reaches it for the query embedding of a semantic search. The front router holds the admission counters, tickets and graph costs in its own process memory, so admission needs no service or socket.

The served catalogue is read-only. The server registers eight dataset read routes plus one feature read under `/api/`, the feedback definition read and submission write, the shell document at `/`, `/docs` and `/feedback`, and one mounted asset directory from the built browser app. The site reads its Selected dataset, or its configured database in a bootstrap state root.

The unit creates its serving generation at start, and that value bounds the browser's memory cache and its derived structure store. A restart changes the generation but notifies no idle tab, so an in-place refresh of the served data, an import into the configured database included, reaches the browser on its next uncached read or reload after the restart.

No catalogue route writes authoritative data, starts or controls a stage, or reaches the worker, and the launcher passes the serving processes no worker connection value. An admitted feedback submission stores the content its sender supplied in the separate feedback application store alone. One middleware in the front router appends one content-free request record per request to the ignored `data/usage/requests` of the checkout, and the router holds its transient admission counters and feedback allowance in process memory. Those writes are the serving path's own writes, and none of them writes catalogue data.

The minimum route is calculated in the browser. The machine route command runs the same TypeScript solver through Node, and its bundle is prepared explicitly with `npm --prefix web run solver:build`. The web server neither builds nor runs that bundle. [Web API](/docs/backend/interfaces/web-api.md) lists the routes, [Front router](/docs/backend/interfaces/front-router.md#the-request-usage-record) states the record, and [System boundaries](/docs/architecture/boundaries.md#a-read-only-catalogue-web-server) states the separation the web package enforces.

## Updating a running copy

Run every command from the checkout root.

1. Take the updated source.

   ```bash
   git pull
   ```

2. Sync the Python and browser dependencies.

   ```bash
   uv sync --locked --no-managed-python
   npm --prefix web ci --engine-strict --no-audit --no-fund
   npm --prefix admin-web ci --engine-strict --no-audit --no-fund
   ```

   The `--no-managed-python` flag stops uv from downloading an interpreter in place of the host interpreter that the installation's environment step selects. That interpreter must expose `os.memfd_create`, and the example workflow's host check refuses one that does not.

3. Apply the schema migrations.

   ```bash
   uv run python scripts/admin.py migrate selected
   uv run python -m alembic -c alembic_feedback.ini upgrade head
   ```

   The first command applies the checkout's migration head to the Selected dataset. On a bootstrap site that serves its configured database, `uv run python scripts/admin.py migrate database` does the same to that database. The second applies only the feedback chain to the feedback application store, preserving its records. [The schema head and migration](/docs/operations/datasets.md#the-schema-head-and-migration) states the commands and their guards.

4. Rebuild the native libraries and the browser apps.

   ```bash
   ./.venv/bin/python scripts/build_native.py
   npm --prefix web run build
   npm --prefix web run solver:build
   npm --prefix admin-web run build
   ```

   The commands write `native/`, `web/dist`, `web/.solver-cli/cli.js` and `admin-web/dist`. The site build reads `config/wiki.json`, so an updated wiki page reaches the app after this step. The browser build and the web server neither produce nor run the solver bundle, and the machine route command runs it.

5. Restart the units.

   ```bash
   systemctl --user restart tuni-course-explorer-web.service
   systemctl --user restart tuni-course-explorer-admin-web.service
   ```

   A web unit that the system manager owns restarts with `sudo systemctl restart tuni-course-explorer-web.service` in place of the first command, and the administration unit always restarts through the user manager. A completed serving-artifact build and a Selected pointer change both reach the site through the supervisor restart that [Operations](/docs/operations/README.md#derived-files-served-data-and-the-web-restart) states. The site service starts again and reads the updated code, the rebuilt browser app, the subsystem files and the current artifact build, and [Serving state](/docs/backend/interfaces/serving-state.md) and [Web supervisor](/docs/backend/interfaces/web-supervisor.md#startup-and-validation) state what the supervisor resolves and opens before it forks its workers. A restart is also what makes an in-place change to the served data visible to the browser. The administration service starts again and reads its own code and settings.

Copy the templates into their working paths again after a change to a tracked file under `examples/`. `docker-compose.yml` at the checkout root and the files under `config/` are working copies, and Git ignores them. [Getting started](/docs/getting-started/README.md) describes the two ways to load and refresh the data behind a served copy.
