# Testing

The test suite proves the Python services, the database migrations, the browser app, the administration console and the documentation wiki against their public contracts.

## Python services and domain

The Python tests live under `tests/`, one folder per subsystem they exercise, with shared helpers in `tests/support/` and shared source responses in `tests/fixtures/`. Most tests run without a network or a database. A test that reaches an external boundary uses one small fake for that boundary, such as the curriculum-source HTTP transport, the model HTTP client or the worker transport.

An ordinary test receives the values of the committed example subsystem files and of `examples/.env.example` through the autouse `_file_free_settings_environment` fixture in `tests/conftest.py`. `POSTGRES_PASSWORD` holds the template placeholder `replace-with-local-secret` unless the process environment already carries the variable. The fixture also sets an environment-only marker, so each settings read takes its values from the process environment and opens no configuration file.

Integration tests carry the `integration` marker. They run against the disposable `course_explorer_test` database through the `_database_session` fixture, which refuses a database name without the `_test` suffix and applies the Alembic head before the first test. The `_database_session` fixture truncates the mapped tables once before it yields, and the per-test `database` fixture truncates them after each test. Tests that exercise Compose call the same `db` service through `course_explorer_admin.mechanics.compose_prefix`, so a snapshot and its restore reach one PostgreSQL instance with pgvector.

Two further marker groups select tests that run on request:

- `slow` tests drive real worker subprocesses and a disposable PostgreSQL database. The integration selection leaves them out.
- `live` tests call an enabled public network service or a running loopback embedding service. They run only when their own environment variable enables them.

`pyproject.toml` selects `not integration and not live and not slow` for a plain `uv run pytest`. The integration selection `integration and not slow and not live` adds the PostgreSQL tests, and `uv run pytest -m integration` selects the `slow` tests as well.

## Frontend modules and rendered components

The browser app and the administration console each run Vitest over `src/**/*.test.ts` in a jsdom environment. The web test command also runs the documentation wiki compiler test with Node's test runner. The console adds a test-only no-op `ResizeObserver`, because jsdom supplies the DOM without layout measurement.

Most frontend tests cover state, actions, request dispatch, the solver and read modules. Rendered checks mount the real components in jsdom.

The browser app checks cover the error notice, the shell language, the course completion control, the tab carousel and its touch swipes, the cached report read, the served header tabs, the structure editor, its module confirmation and its edits, the Discover list preservation, the module lookup box and its version hand-off, the comparison pane, its slot hydration, its replacement question and its result meters, the saved-data reset, the whole-state import, the search submit and activity re-read, the semantic fallback notice, the minimum route ownership and the feature bootstrap.

The console checks cover the signed-in shell and its tab session, the preparation stage and inference run panels, a panel's visibility read loop, the backups inventory, the log panels and their explicit worker read, the rebuild confirmation, the configuration save, the dataset and backup cleanup, a confirmed target decision and a refused feature-switch write.

A rendered check that reads through the API answers that route through a small fetch fixture with typed reports and throws on an unexpected request. A rendered test that needs layout supplies test-local viewport and row geometry and a no-op `ResizeObserver`, while the module lookup renders the real virtual window. A file import uses a real test `File` with its text reader installed, and the export check records the stored text inside the test. jsdom supplies the DOM without layout or a browser process, so these checks prove component wiring and visible state. The browser journeys prove the browser rendering itself.

Five Node journeys under `web/tools/` drive the built app in headless Chromium against one disposable database loaded with the example dataset. `browser-route.test.mjs` covers the served minimum route and its browser worker, `browser-phone.test.mjs` the phone shell and its swipe navigation, `browser-lookup-guard.test.mjs` the lookup touch guard, `browser-docs.test.mjs` a configured documentation page with its return control, and `browser-docs-search.test.mjs` the documentation search. The shared fixture opens an isolated context, seeds the saved profile and tab, and dispatches native touch input. The runner in `tests/web/browser_runner.py` creates one fresh database, loads the example dataset, serves the built app on a loopback port and stops every process and database it created. The journeys prove the built app's browser rendering, its worker execution and its touch input.

The wiki compiler test covers the configured allowlist, navigation order and depth, Markdown destinations, HTML safety, root-relative links and images, and missing images. It builds pages from a temporary repository tree.

## Checks on every push

The checks on every push are the lint and format checks, the network-free Python suite, the browser app and administration console checks, the PostgreSQL integration selection and the five browser journeys. [Local checks](/docs/testing/local-checks.md) lists the exact local commands. [Solver fixtures](/docs/testing/solver-fixtures.md) lists the seven generated solver JSON files and their regeneration commands.

The slow tests and the live tests are selected on request. [Local checks](/docs/testing/local-checks.md#checks-on-every-push-and-pull-request) lists the exact commands and states where the workflow's commands differ from the local ones. The checks on every push start no model, run no remote stage and read no public curriculum source.
