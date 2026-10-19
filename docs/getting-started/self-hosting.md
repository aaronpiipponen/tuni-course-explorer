# Self-hosting

Self-hosting runs an installed copy as a service on a Linux host and serves it over HTTPS through a reverse proxy.

Two systemd user units run the copy: the site and the administration backend. One reverse proxy publishes both sites on separate interfaces.

## What the host needs

- A copy installed by the [Installation](/docs/getting-started/installation.md) steps, including the built browser app, the built console and the loaded example dataset.
- Two domain names. The site domain resolves to the interface that serves the site, and the administration domain resolves to the interface that serves the console. Every command on this page uses `example.org` and `admin.example.org` in their place.
- Caddy, run from the built container image, which terminates TLS for both domains and forwards requests to the two loopback backends. It binds port 443 on the two interface addresses and needs no port 80 listener.
- A DuckDNS API token for the administration certificate, supplied at run time in the Caddy container's environment.
- systemd as the service manager, because the two servers run from systemd user units.
- An account that may run `loginctl enable-linger`, the `systemctl --user` commands and `sudo -n docker`.

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
| `StandardOutput=null`, `StandardError=journal` | Sends the error stream to the journal and discards the standard stream |
| `WantedBy=default.target` | The user manager's default target pulls in the unit |

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
journalctl --user -u tuni-course-explorer-web.service
```

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
journalctl --user -u tuni-course-explorer-admin-web.service
```

## The site unit identities

The administration Dashboard reports the site's web unit, while the administration build and restart validate the administration unit. The ignored environment file at the checkout root names both, and the administration command reads both values:

```text
ADMIN_SITE_WEB_SERVICE_UNIT=tuni-course-explorer-web.service
ADMIN_SITE_ADMIN_SERVICE_UNIT=tuni-course-explorer-admin-web.service
```

The values are the unit names installed on this host. A missing value fails the read and names the key.

## The web settings

`config/web.toml` holds the keys a serving host reads:

| Key | Example value | Meaning |
|---|---|---|
| `WEB_HOST` | `127.0.0.1` | The bind address. The settings allow this value alone, so the server answers the host itself. |
| `WEB_PORT` | `8037` | The port the server binds, and the port the reverse proxy targets. |
| `WEB_WORKERS` | `2` | The number of server processes that share the one bound socket. |
| `WEB_EMBEDDINGS_ENABLED` | `true` | Whether the site serves semantic matching, comparison and the recommended courses, and mounts their controls. |
| `WEB_INFERENCE_ENABLED` | `true` | Whether the site serves inferred prerequisites and mounts the controls and marks that describe them. |

The serving process reads these values when it starts, so a changed value reaches the site when the unit starts it again. [Web server](/docs/backend/interfaces/web-server.md) describes the socket, the launcher, and the process count.

`USAGE_RETENTION_DAYS` in the same file is not a serving value. It sets how many days of request records the usage report keeps, and the report refuses a requested hour window longer than that retention in hours. The example keeps 30 days, so a window longer than 720 hours is refused. The serving process appends one request record per request, and an operator reads the aggregates or prunes the old records with:

```bash
uv run python scripts/admin.py usage --hours 24
```

[Command line](/docs/backend/interfaces/command-line.md#the-request-usage-report) states the window, the report fields and the pruning side effect, and [Web server](/docs/backend/interfaces/web-server.md#the-request-usage-record) states the record the serving process appends.

## The administration settings

`config/admin_web.toml` holds the keys the administration backend reads:

| Key | Example value | Meaning |
|---|---|---|
| `ADMIN_WEB_HOST` | `127.0.0.1` | The bind address. The settings allow `127.0.0.1` alone. |
| `ADMIN_WEB_PORT` | `8039` | The port the backend binds, and the port the reverse proxy targets. |
| `ADMIN_WEB_ORIGIN` | `https://localhost:8039` | The one exact HTTPS origin. The `Host` header must carry its host and port, and a supplied `Origin` must equal it. |
| `ADMIN_WEB_SESSION_IDLE_MINUTES` | `30` | Minutes of inactivity after which a session expires. |
| `ADMIN_WEB_SESSION_MAX_HOURS` | `12` | Hours from creation after which a session expires. |
| `ADMIN_WEB_ANONYMOUS_SESSION_LIMIT` | `10` | Fresh anonymous sessions the backend grants in the server-wide window. |
| `ADMIN_WEB_ANONYMOUS_SESSION_WINDOW_SECONDS` | `60` | Length of that sliding window in seconds. |
| `ADMIN_WEB_COMMAND_LOG_LIMIT` | `200` | Entries the command log retains, reported oldest first. |
| `ADMIN_WEB_POLL_SECONDS` | `60` | Seconds between completed automatic reads of one visible console panel. |
| `ADMIN_WEB_APP_URL` | `http://localhost:8037/` | Absolute address the console's App link points at. Its Wiki link opens `/docs#home` on the same site. |
| `ADMIN_WEB_REPOSITORY_URL` | `https://github.com/aaronpiipponen/tuni-course-explorer` | HTTPS GitHub owner and repository address the console's GitHub link opens. |

`ADMIN_WEB_ANONYMOUS_SESSION_LIMIT` and `ADMIN_WEB_ANONYMOUS_SESSION_WINDOW_SECONDS` set one server-wide anonymous session creation limit for the backend process, and a live anonymous or signed-in session consumes none of it. The counted creation times live in the process's memory, so a restarted backend counts from zero. A saved value reaches the backend when the unit starts it again.

The example file under `examples/config/` describes a development instance with the bind `127.0.0.1:8039` and the origin `https://localhost:8039`. A deployed host sets its own origin and application address in `config/admin_web.toml`, which Git ignores.

Every key in the table is required, and a missing key fails the settings read and names the key. The backend compares the `Host` header with the host and port of `ADMIN_WEB_ORIGIN`. It compares an `Origin` header with the configured origin only when the request supplies one, and it refuses a state-changing request that supplies no `Origin`. [Administration backend](/docs/backend/interfaces/admin-backend.md) states the admission and session behavior.

## The administration account

Set the account over SSH with the credential command, which prompts for the password twice without echoing it:

```bash
uv run python scripts/admin.py password --username USERNAME
```

The command writes the username and an argon2id hash to `data/admin-web/password` with owner-only access. Three consecutive failed sign-ins create `data/admin-web/lock`, and while that file exists the backend answers every request with an empty `403`. Delete the whole file over SSH to end the lock. [Console access and records](/docs/operations/admin-console/access-and-records.md) describes the sign-in, the lock and the command log, and [Administration backend](/docs/backend/interfaces/admin-backend.md#the-failed-attempt-count-and-the-lock) states the count and the lock.

## The console build

The administration console is a separate browser app with its own build, served at the administration domain. [Administration console](/docs/operations/admin-console/README.md) describes how to open it, sign in and use its tabs.

```bash
npm --prefix admin-web ci --no-audit --no-fund
npm --prefix admin-web run build
```

The build writes `admin-web/dist`, which the backend serves from the checkout on each request. A change to the backend's own code or settings reaches the administration site when its unit starts again. The console's **Rebuild admin panel** action runs the build and then queues a restart of its own unit, which ends every signed-in session.

## HTTPS with a reverse proxy

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

The DuckDNS token lives in one environment file at `deploy/caddy.env`, with one assignment. `.gitignore` lists `/deploy/`, so Git does not track the file. Create it with owner-only access, then write the assignment:

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
  --env COURSE_EXPLORER_PUBLIC_DOMAIN=example.org \
  --env COURSE_EXPLORER_PUBLIC_BIND=PUBLIC_INTERFACE_ADDRESS \
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
public_address=PUBLIC_INTERFACE_ADDRESS
admin_address=ADMIN_INTERFACE_ADDRESS
curl -fsS --resolve "example.org:443:$public_address" https://example.org/ -o /dev/null
curl -fsS --resolve "admin.example.org:443:$admin_address" https://admin.example.org/ -o /dev/null
```

The two uppercase values are placeholders for the interface addresses the site binds. A zero exit proves that Caddy answers, that the certificate chain verifies against the system trust store and that the served certificate names the requested domain. Inspect the served certificate directly when the domain or the chain is in question:

```bash
openssl s_client -connect "$admin_address:443" -servername admin.example.org \
  -verify_hostname admin.example.org -verify_return_error </dev/null
```

The administration backend binds loopback alone, so a direct request to its port from another host refuses the connection. A probe of the public interface with the administration domain answers no administration content.

## The services and the served site

The database and the embedding service run from `docker-compose.yml` at the checkout root, and both declare `restart: unless-stopped`. Docker starts them again after a host reboot unless an operator stopped them. Start and inspect them through the Compose wrapper:

```bash
uv run python -m course_explorer_admin.compose -- up -d --wait db embedding
uv run python -m course_explorer_admin.compose -- ps
```

The Compose file publishes the database port on `127.0.0.1` alone, at the value of `POSTGRES_PORT` in `config/database.toml`, so the database answers the host and not the network. The embedding service listens on the loopback port from `config/search.toml`, and the web server reaches it for the query embedding of a semantic search.

The served site is read-only. The server registers ten dataset read routes plus one feature read under `/api/`, each a `POST` that reads, the shell document at `/` and `/docs`, and one mounted asset directory from the built browser app. No route writes authoritative data, starts or controls a stage, or reaches the worker, and the launcher passes the serving process no worker connection value. One middleware appends one content-free request record per request to the ignored `data/usage/requests` of the checkout, and that append is the only write on the serving path. [Web API](/docs/backend/interfaces/web-api.md) lists the routes, [Web server](/docs/backend/interfaces/web-server.md#the-request-usage-record) states the record, and [System boundaries](/docs/architecture/boundaries.md#a-read-only-web-server) states the separation the web package enforces.

## Updating a running copy

Run every command from the checkout root.

1. Take the updated source.

   ```bash
   git pull
   ```

2. Sync the Python and browser dependencies.

   ```bash
   uv sync --locked
   npm --prefix web ci --no-audit --no-fund
   npm --prefix admin-web ci --no-audit --no-fund
   ```

3. Apply the schema migrations.

   ```bash
   uv run python -m alembic upgrade head
   ```

   The migration resolves the target database through the settings and applies every revision up to the checkout's single head.

4. Rebuild the browser apps.

   ```bash
   npm --prefix web run build
   npm --prefix admin-web run build
   ```

   Each build writes its own `dist` directory. The site build reads `config/wiki.json`, so an updated wiki page reaches the app after this step.

5. Restart the units.

   ```bash
   systemctl --user restart tuni-course-explorer-web.service
   systemctl --user restart tuni-course-explorer-admin-web.service
   ```

   The site service starts again and reads the updated code, the rebuilt browser app, the subsystem files, and the two hub files. The administration service starts again and reads its own code and settings. [Derived files and the web restart](/docs/operations/README.md#derived-files-and-the-web-restart) describes why a serving copy reads the hubs at start.

Copy the templates into their working paths again after a change to a tracked file under `examples/`. `docker-compose.yml` at the checkout root and the files under `config/` are working copies, and Git ignores them. [Data preparation](/docs/getting-started/data-preparation.md) describes how the data behind a served copy is loaded and refreshed.
