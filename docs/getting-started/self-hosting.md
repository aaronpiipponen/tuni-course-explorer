# Self-hosting

Self-hosting runs an installed copy as a service on a Linux host and serves it over HTTPS through a reverse proxy.

## What the host needs

- A copy installed by the [Installation](/docs/getting-started/installation.md) steps, including the built browser app and the loaded example dataset.
- A domain name whose DNS record points at the host. Every command on this page uses `example.org` in its place.
- Caddy, which terminates TLS for the domain and forwards requests to the web server. Caddy must be able to bind port 443, and the port must be reachable from the internet for the certificate challenge.
- systemd as the service manager, because the web server runs from a systemd user unit.
- An account that may run `loginctl enable-linger` and the `systemctl --user` commands.

## The systemd user unit

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

## The web settings

`config/web.toml` holds the three keys a serving host reads:

| Key | Example value | Meaning |
|---|---|---|
| `WEB_HOST` | `127.0.0.1` | The bind address. The settings allow this value alone, so the server answers the host itself. |
| `WEB_PORT` | `8037` | The port the server binds, and the port the reverse proxy targets. |
| `WEB_WORKERS` | `2` | The number of server processes that share the one bound socket. |

The serving process reads these values when it starts, so a changed value reaches the site when the unit starts it again. [Web server](/docs/backend/interfaces/web-server.md) describes the socket, the launcher, and the process count.

## HTTPS with a reverse proxy

The template `examples/deploy/Caddyfile` terminates TLS for the domain and forwards every request to the loopback web port.

```bash
cp examples/deploy/Caddyfile deploy/Caddyfile
COURSE_EXPLORER_PUBLIC_DOMAIN=example.org caddy run --config /path/to/checkout/deploy/Caddyfile
```

The site configuration takes the domain from the `COURSE_EXPLORER_PUBLIC_DOMAIN` environment variable, which Caddy reads from its own process environment. A service manager that runs Caddy supplies the same variable in its environment.

The template's global block turns the admin endpoint off and disables the automatic HTTP-to-HTTPS redirects, so Caddy serves the domain over HTTPS alone. Its site block asks for a certificate through an ACME issuer with the HTTP challenge disabled, so the certificate is issued through TLS-ALPN-01 on port 443. The proxy target is `127.0.0.1:8037`, the value of `WEB_PORT` in the example.

The result is one site at `https://example.org` that serves the browser app from the reverse proxy. [Configuration](/docs/backend/configuration.md) and [System boundaries](/docs/architecture/boundaries.md) describe how the web settings reach the process and what the serving side can do.

## The services and the served site

The database and the embedding service run from `docker-compose.yml` at the checkout root, and both declare `restart: unless-stopped`. Docker starts them again after a host reboot unless an operator stopped them. Start and inspect them through the Compose wrapper:

```bash
uv run python -m course_explorer_admin.compose -- up -d --wait db embedding
uv run python -m course_explorer_admin.compose -- ps
```

The Compose file publishes the database port on `127.0.0.1` alone, at the value of `POSTGRES_PORT` in `config/database.toml`, so the database answers the host and not the network. The embedding service listens on the loopback port from `config/search.toml`, and the web server reaches it for the query embedding of a semantic search.

The served site is read-only. The server registers ten read routes under `/api/`, each a `POST` that reads, the shell document at `/` and `/docs`, and one mounted asset directory from the built browser app. No route writes data, starts or controls a stage, or reaches the worker, and the launcher passes the serving process no worker connection value. [Web API](/docs/backend/interfaces/web-api.md) lists the routes, and [System boundaries](/docs/architecture/boundaries.md#a-read-only-web-server) states the separation the web package enforces.

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
   ```

3. Apply the schema migrations.

   ```bash
   uv run python -m alembic upgrade head
   ```

   The migration resolves the target database through the settings and applies every revision up to the checkout's single head.

4. Rebuild the browser app.

   ```bash
   npm --prefix web run build
   ```

   The build writes `web/dist` again, and it reads `config/wiki.json`, so an updated wiki page reaches the app after this step.

5. Restart the unit.

   ```bash
   systemctl --user restart tuni-course-explorer-web.service
   ```

   The service starts again and reads the updated code, the rebuilt browser app, the subsystem files, and the two hub files. [Derived files and the web restart](/docs/operations/README.md#derived-files-and-the-web-restart) describes why a serving copy reads the hubs at start.

Copy the templates into their working paths again after a change to a tracked file under `examples/`. `docker-compose.yml` at the checkout root and the files under `config/` are working copies, and Git ignores them. [Data preparation](/docs/getting-started/data-preparation.md) describes how the data behind a served copy is loaded and refreshed.
