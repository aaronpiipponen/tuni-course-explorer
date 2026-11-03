# Local checks

This page lists the exact lint, Python, PostgreSQL and frontend commands for a local checkout.

## Prerequisites

Python 3.14.3 is selected by `.python-version`, and the locked Python environment is installed with `uv sync --locked`. The browser app and the administration console declare the Node engine range `^22.22.2 || >=24.15.0` in their `package.json` files, and each app is installed from its own lock file with `npm --prefix <app> ci --no-audit --no-fund`.

The web dependencies are also required by the Python suite. The session fixture `solver_bundle` in `tests/conftest.py` runs `npm --prefix web run solver:build` before a test that needs the Node machine route, so install the web dependencies before the Python suite. The suite also loads the native serving libraries and the test-only fixture library, so build them once with the fixture target:

```bash
./.venv/bin/python scripts/build_native.py --fixtures
```

The web build compiles the pages selected by `config/wiki.json`. Every page it lists and every local image those pages reference must exist in the checkout. The wiki compiler test builds temporary repository trees of its own.

The PostgreSQL selection needs a configured Compose `db` service that is already running. The fixture refuses a database name without the `_test` suffix. The Compose commands use the wrapper described in [The Compose environment file](/docs/backend/configuration.md#the-compose-environment-file).

The integration fixture starts its throwaway Compose project from the prepared extension database image and builds nothing. Prepare that image once:

```bash
uv run python -m course_explorer_admin.compose --non-interactive -- build db
```

A missing prepared image fails the fixture and prints this preparation command as its guidance.

## Lint and format checks

```bash
uv run ruff check .
uv run ruff format --check .
git diff --check
```

Ruff reads the configuration in `pyproject.toml`. `git diff --check` reports whitespace errors in the working tree.

## Network-free Python suite

```bash
uv run pytest
```

`pyproject.toml` selects `not integration and not live and not slow`. An ordinary test receives the committed example values as its settings environment, and [Testing](/docs/testing/README.md#python-services-and-domain) states the fixture and its two template placeholders. The suite builds the Node solver bundle from the installed web dependencies.

## PostgreSQL selection

A local integration run consumes the checkout's own database settings: `POSTGRES_HOST`, `POSTGRES_PORT` and `POSTGRES_USER` from `config/database.toml`, and `POSTGRES_PASSWORD` from the ignored environment file. A process environment value under the same key takes precedence. Ordinary tests read the example configuration instead. The connection values are consumed by the owning settings loader and the database client.

The role in the commands below is `course_explorer`, the `POSTGRES_USER` value in `examples/config/database.toml`. Create the disposable database when it is absent. The existence check prints `1` for a database that is present and an empty line otherwise:

```bash
uv run python -m course_explorer_admin.compose -- exec -T db psql -U course_explorer -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='course_explorer_test'"
```

Create the database only when the check prints no `1`:

```bash
uv run python -m course_explorer_admin.compose -- exec -T db createdb -U course_explorer course_explorer_test
```

Then run the integration selection without the `slow` and `live` groups:

```bash
POSTGRES_DB=course_explorer_test uv run pytest -m "integration and not slow and not live" tests
```

The `_database_session` fixture refuses a database name without the `_test` suffix, and [Testing](/docs/testing/README.md#python-services-and-domain) states how it truncates the mapped tables, so the run is repeatable on the same database.

The feedback application store has its own migrated disposable database per test for the proofs that need stored rows, with `alembic_feedback.ini` applied and a temporary attachment root. The feedback tests prove the validated submission, the configured search order without duplicate results, the combined filters over every configured select, the scoped attachment read with a named deletion that preserves the other submission, and the feedback-only migration that preserves its rows.

The publication tests drive the real renderer and CLI adapter over a disposable feedback application store and temporary attachment files, replacing only `subprocess.run`. They prove the mapped title, body and both designated images under their filenames, with an unmapped field and attachment excluded, a partial upload that preserves the created link without a second creation, and a timeout, an unconfirmed failure and a precommitted `uncertain` row that never send again. They also drive the real front router over real worker applications: the forwarding test supplies the migrated feedback application store and proves the browser and site hourly allowances with admission on and off, while the exact-site refusal and the declared and streamed body bound run without a database and with example-only intake settings. The targeted command bounds a schema change in the feedback application store or the curriculum database:

```bash
POSTGRES_DB=course_explorer_test uv run pytest -m "integration and not slow and not live" tests/feedback tests/db/test_database_schema.py
```

These tests use the raw test connection only to create and drop their own application databases, and they read no feedback credential.

An isolated disposable instance uses its own Compose project and its own published loopback port. Set both values and start the database:

```bash
export COMPOSE_PROJECT_NAME=course-explorer-local-verify
export POSTGRES_PORT=5434
uv run python -m course_explorer_admin.compose -- up -d --wait --no-build --pull never db
```

The Compose wrapper forwards `COMPOSE_PROJECT_NAME` as its project name, and the Compose file publishes the database on `127.0.0.1` at `POSTGRES_PORT`. The start uses the already prepared extension image and builds nothing. Create and run the database with the commands above. To reset the disposable database, drop it and recreate it with the create command above:

```bash
uv run python -m course_explorer_admin.compose -- exec -T db dropdb -U course_explorer --if-exists course_explorer_test
```

Remove the project with its volumes when the run ends:

```bash
uv run python -m course_explorer_admin.compose --non-interactive -- down --volumes
```

Narrow the selection to named integration tests when one repository or query changed. The publication proof needs no GitHub credential, network call or real repository, and it runs against the same disposable `_test` database and temporary attachment root as the other feedback tests. Run the whole integration selection for a schema or persistence change. `uv run pytest -m integration` adds the slow tests, and the live tests run only when their own environment variable enables them. The commands above run the integration selection alone.

## Browser app and console checks

The browser app:

```bash
npm --prefix web run typecheck
npm --prefix web run test
npm --prefix web run format:check
npm --prefix web run build
```

The administration console:

```bash
npm --prefix admin-web run typecheck
npm --prefix admin-web run test
npm --prefix admin-web run format:check
npm --prefix admin-web run build
```

`npm --prefix web run test` runs Vitest over `web/src/**/*.test.ts` and then the wiki compiler test with Node's test runner. `npm --prefix admin-web run test` runs Vitest over the console sources. The web build compiles the wiki pages that `config/wiki.json` selects, and the console build compiles the console sources. Run the commands of an app when its own source changes. The rendered checks include the feedback form's publication choice in the web app and the feedback inbox's named local deletion in the console.

## Browser journeys

The five browser journeys need the running PostgreSQL instance from the selection above and the built browser app. Install the locked browser and build the app once:

```bash
npm --prefix web run browser:install
npm --prefix web run build
```

```bash
npm --prefix web run browser:test
```

The command runs all five Node journeys in headless Chromium and is separate from `npm --prefix web run test`. A positional listed basename runs one journey, for example:

```bash
npm --prefix web run browser:test -- browser-route.test.mjs
```

The runner reads the database host, port and user from `config/database.toml`, and the password from the ignored environment file, through `load_raw_database_settings()`. The runner builds its database engines from those settings and passes the same values to the serving process. The child serving process and the import read every other product setting from the committed example configuration, with the environment-only marker set so those reads open no runtime TOML or environment file.

The runner creates one database named `course_explorer_browser_<random hex>_test`, applies the Alembic head and imports the example dataset from `data/mock/` through the real example-data loader in a temporary capture root. It serves the built app on an ephemeral loopback port and runs the Node journeys against that origin. On completion or failure it stops the Node process and the app, drops exactly the database it created and removes its temporary files. A name without the `_test` suffix is refused before creation.

A UI proof that spans the feedback page, the administration console and the structure drag is a separate disposable composition. It holds its own migrated feedback and curriculum databases, its own temporary attachment root and certificate, real loopback services and isolated browser contexts, and it stops and removes only those owned resources. It adds no permanent journey or test suite.

## Checks on every push and pull request

Each push to `main` and each pull request that targets it runs these checks in the repository's CI workflow. The workflow builds the native libraries with the test-only fixture library before the Python suite, and it builds the extension database image before it starts the Compose `db` service. It runs `git diff --check HEAD^ HEAD` in place of `git diff --check`. Before the browser app and console checks and the integration selection it copies `examples/config/*.toml`, `examples/config/wiki.json`, `examples/config/feedback-form.json` and `examples/docker-compose.yml` into the checkout, so those steps read the example configuration and Compose file. It then starts the Compose `db` service with `POSTGRES_DB=course_explorer_test`, a synthetic database password and its own Compose project name, and the integration selection and the browser journeys run with that same environment.
