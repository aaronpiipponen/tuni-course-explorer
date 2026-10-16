# Installation

Installation sets up a local copy that serves the example dataset, from the dependencies to the first page in the browser.

## What the copy needs

- A checkout of this repository.
- Python 3.14.3. `.python-version` pins that interpreter version and `pyproject.toml` requires Python 3.14 or higher.
- [uv](https://docs.astral.sh/uv/), which installs the interpreter, the Python dependencies, and the commands the steps run.
- Node.js 20.19 or higher within major version 20, or 22.12 or higher, with npm. `web/package.json` declares those engine ranges.
- Docker with Docker Compose. The Compose wrapper runs `sudo docker compose` with the checkout as the project directory and `docker-compose.yml` at the checkout root as the file, so the account that runs the steps must be allowed to run Docker through sudo.
- Access to the Python and npm package registries, and to the embedding model file that `EMBEDDING_ARTIFACT_URL` names.

## The files to copy

The repository tracks the templates a copy is set up from under `examples/`. Git ignores the working copies, so each checkout carries its own settings without changing the templates.

| Template | Working path | Holds |
|---|---|---|
| `examples/config/database.toml`, `curriculum.toml`, `search.toml`, `translation.toml`, `inference.toml`, `worker.toml`, `web.toml` | `config/` | The seven subsystem files, one per subsystem, each holding that subsystem's portable keys |
| `examples/config/wiki.json` | `config/wiki.json` | The pages the documentation wiki renders, and the repository the compiler links to for a page it does not render |
| `examples/config/derived/embedding-hub.json`, `embedding-outcomes-hub.json` | `config/derived/` | The two hub vectors that search, comparison, and recommendations subtract before measuring similarity |
| `examples/.env.example` | `.env` | The machine-local values: the database password and the three worker connection keys |
| `examples/docker-compose.yml` | `docker-compose.yml` | The PostgreSQL database with pgvector and the embedding service |
| `examples/deploy/Caddyfile` | `deploy/Caddyfile` | The HTTPS site template for a host that serves the copy over a domain |
| `examples/deploy/systemd/tuni-course-explorer-web.service.in` | `deploy/` | The systemd user unit template for the web server |

`config/search.toml` names the two hub files by path, so the settings owner resolves each vector from the file under `config/derived/`. [Configuration](/docs/backend/configuration.md) describes how the settings owner reads the subsystem files and the environment file.

## Steps

1. Install the Python and browser dependencies from the checkout root.

   ```bash
   uv sync --locked
   npm --prefix web ci --no-audit --no-fund
   ```

   `uv sync` writes the virtual environment `.venv` at the checkout root and installs the Python packages recorded in `uv.lock`. `npm ci` installs the browser packages recorded in `web/package-lock.json` into `web/node_modules`. The unit template and `scripts/run_web.sh` run the server through `.venv/bin/python`, so the environment lives at the checkout root.

2. Copy the example files to the working paths listed above.

   ```bash
   mkdir -p config config/derived deploy
   cp examples/config/*.toml config/
   cp examples/config/wiki.json config/wiki.json
   cp examples/config/derived/*.json config/derived/
   cp examples/.env.example .env
   cp examples/docker-compose.yml docker-compose.yml
   cp examples/deploy/Caddyfile deploy/Caddyfile
   cp examples/deploy/systemd/tuni-course-explorer-web.service.in deploy/
   ```

   The result is a checkout that holds its own `config/`, `.env`, `docker-compose.yml`, and `deploy/` beside the tracked `examples/`.

3. Build the browser app.

   > [!IMPORTANT]
   > The build compiles the documentation wiki from `config/wiki.json`, so it runs after the copy step. A build without that file fails with `Wiki build: cannot read config/wiki.json (read failed)`.

   ```bash
   npm --prefix web run build
   ```

   The build writes `web/dist`, the directory the web server serves as the shell document and its assets.

4. Set the local values in `.env`, then restrict the file to its owner.

   Set `POSTGRES_PASSWORD` to a password for the local database. The three worker connection keys name the worker that the remote stages reach, and the steps on this page do not read them.

   ```bash
   chmod 600 .env
   ```

   > [!WARNING]
   > Credentials belong in the ignored `.env`, and file mode 0600 gives the file owner-only access. The subsystem files hold portable settings, and their tracked templates are credential-free.

5. Place the embedding model file at the configured path.

   The service reads the file named by `EMBEDDING_ARTIFACT_PATH` and checks it against the digest in `EMBEDDING_ARTIFACT_SHA256`. Both values, and the download location in `EMBEDDING_ARTIFACT_URL`, come from `config/search.toml`, and the download runs once per checkout.

   ```bash
   mkdir -p models
   curl -fL -o models/bge-m3-q8_0.gguf https://huggingface.co/ggml-org/bge-m3-Q8_0-GGUF/resolve/9eba04c5d75ba5a1595e45de734d36bef4e5cb98/bge-m3-q8_0.gguf
   printf '%s  %s\n' aa473d51f451a22f0fcf39ba3330c14bed38a385712b1113440f69df4047a173 models/bge-m3-q8_0.gguf | sha256sum -c -
   ```

   The digest `aa473d51f451a22f0fcf39ba3330c14bed38a385712b1113440f69df4047a173`, the path `models/bge-m3-q8_0.gguf`, and the URL are the values of those three keys. A successful check prints `models/bge-m3-q8_0.gguf: OK`. The path matches the configured value because Docker Compose binds that exact path into the container.

   The embedding container checks the same digest at start and exits before it listens when the file does not match, reporting `embedding artifact checksum mismatch`. The example dataset bundles the vectors of its teaching text, so loading it generates no embedding. The service runs while the site serves, because a search request embeds the query text through it. [Embeddings](/docs/backend/text-and-vectors/embeddings.md) describes the service, the chunking, and the hubs.

6. Build and start the database and the embedding service.

   ```bash
   uv run python -m course_explorer_admin.compose -- build
   uv run python -m course_explorer_admin.compose -- up -d --wait db embedding
   ```

   The wrapper generates a temporary environment file for the run and then runs `sudo docker compose` with the checkout as the project directory, `docker-compose.yml` at the checkout root as the file, and the generated environment file. `build` builds the embedding image from `docker/embedding/Dockerfile`. `up -d --wait` starts both services and returns after each healthcheck reports healthy.

   The database publishes its port on the loopback address alone, and the embedding service listens on the loopback port from `config/search.toml`.

7. Create the schema and load the example dataset.

   ```bash
   uv run python -m alembic upgrade head
   uv run python scripts/mock_data.py load
   ```

   The migration resolves the target database through the settings and creates the schema at the checkout's single head revision. The loader imports the invented example dataset from `data/mock/` through the same normalization path a capture uses, adds the bundled vectors of its chunks, and prints one JSON line: the chunk coverage of the loaded dataset, with the total, pending, completed, and failed counts and one count row per field, language, and text origin.

   The loader keeps the capture it registers under `data/mock-import/`. The `load-curriculum` action stops after the curriculum and leaves the vectors out. Both actions read the bundled fixture and send no request to the embedding service.

8. Start the site.

   ```bash
   bash scripts/run_web.sh
   ```

   The script runs the launcher through `.venv/bin/python`, and the launcher passes the five settings families the serving process needs before the server takes over. The server binds the loopback host and port from `config/web.toml` and serves the built browser app. The command runs in the foreground, and the site answers while the process lives.

## Check the running copy

Open `http://127.0.0.1:8037`, the address from `WEB_HOST` and `WEB_PORT` in `config/web.toml`. The top bar shows the five tabs **Search**, **Compare**, **Prerequisites**, **Discover**, and **Structure of studies**, with **Docs** beside them. **Docs** opens the documentation wiki inside the app, and a page the configuration does not select opens on GitHub. [Web server](/docs/backend/interfaces/web-server.md) describes the addresses the process serves.

The browser checks that `web/package.json` defines:

```bash
npm --prefix web run typecheck
npm --prefix web run test
npm --prefix web run format:check
```

`typecheck` runs the TypeScript compiler without writing output, `test` runs the browser tests and the wiki build tests, and `format:check` runs Prettier in check mode.

The Python tests:

```bash
uv run pytest
```

`pyproject.toml` points pytest at `tests` and excludes the `integration`, `live`, and `slow` markers from the default run.

## Troubleshooting

| Message | Cause | Fix |
|---|---|---|
| `public configuration file is not readable: web.toml` | A subsystem file is missing from `config/`. | Copy the seven templates from `examples/config/` into `config/`. |
| `Wiki build: cannot read config/wiki.json (read failed)` | The browser build ran before the copy step. | Copy `examples/config/wiki.json` to `config/wiki.json`, then rebuild the browser app. |
| `postgres password must not be blank` | `.env` carries no `POSTGRES_PASSWORD` value. | Set a password in `.env`, then run the Compose and migration steps again. |
| `compose bridge requires -- before the forwarded Compose arguments` | The wrapper was called without the `--` before the Compose arguments. | Put `--` between the module and the Compose arguments, as in the commands above. |
| `EMBEDDING_ARTIFACT_SHA256 is required` | Docker Compose ran without the generated environment file that the wrapper supplies. | Run the Compose commands through `course_explorer_admin.compose`. |
| `embedding artifact checksum mismatch` | The file at `EMBEDDING_ARTIFACT_PATH` does not match `EMBEDDING_ARTIFACT_SHA256`. | Repeat the download and the checksum check. |
| `EMBEDDING_HUB_VECTOR derived artifact is not readable` | `config/derived/embedding-hub.json` is missing. | Copy both files from `examples/config/derived/` into `config/derived/`. |
| `mock data import refuses a selected-dataset enabled configuration` | `SELECTED_DATASET_ENABLED` is true in `config/database.toml`. | Set it to `false`, then run the load command again. |
| `the received database does not match the executing checkout's single Alembic head` | The database schema is not at the checkout's head revision. | Run `uv run python -m alembic upgrade head`. |

The example dataset is invented, and its courses, modules, prerequisites, and structure rules are not university data. [Data preparation](/docs/getting-started/data-preparation.md) describes the loader and the artifact actions in full.
