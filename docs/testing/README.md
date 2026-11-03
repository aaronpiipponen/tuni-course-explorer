# Testing

The test suite proves the Python services, the database migrations, the browser app, the administration console and the documentation wiki against their public contracts.

## Python services and domain

The Python tests live under `tests/`, one folder per subsystem they exercise, with shared helpers in `tests/support/` and shared source responses in `tests/fixtures/`. Most tests run without a network or a database. A test that reaches an external boundary uses one small fake for that boundary, such as the curriculum-source HTTP transport, the model HTTP client or the worker transport.

An ordinary test receives the values of the committed example subsystem files and of `examples/.env.example` through the autouse `_file_free_settings_environment` fixture in `tests/conftest.py`. `POSTGRES_PASSWORD` holds the template placeholder `replace-with-local-secret` unless the process environment already carries the variable, and `FEEDBACK_POSTGRES_PASSWORD` holds its own template placeholder. The fixture also sets an environment-only marker, so each settings read takes its values from the process environment and opens no configuration file.

Integration tests carry the `integration` marker. They run against the disposable `course_explorer_test` database through the `_database_session` fixture, which refuses a database name without the `_test` suffix and applies the curriculum Alembic head before the first test. The `_database_session` fixture truncates the mapped tables once before it yields, and the per-test `database` fixture truncates them after each test.

The feedback tests that need stored rows create one generated application database per test through `tests/support/database.py`, apply the feedback head from `alembic_feedback.ini`, and use a temporary attachment root. They prove the validated submission, the configured text-order search without duplicate results, the combined filters derived from every select, the scoped attachment read beside a named deletion that leaves the other submission and the shared directories untouched, and the HTTP forwarding path with the browser and site hourly allowances under admission on and off. The refusal and body-bound router proofs supply no database and use example-only intake settings, so they prove the exact-site refusal and the declared and streamed body bound alone. Tests that exercise Compose call the same `db` service through `course_explorer_admin.mechanics.compose_prefix`, so a snapshot and its restore reach one PostgreSQL instance with pgvector.

Two further marker groups select tests that run on request:

- `slow` tests drive real worker subprocesses and a disposable PostgreSQL database. The integration selection leaves them out.
- `live` tests call an enabled public network service or a running loopback embedding service. They run only when their own environment variable enables them.

`pyproject.toml` selects `not integration and not live and not slow` for a plain `uv run pytest`. The integration selection `integration and not slow and not live` adds the PostgreSQL tests, and `uv run pytest -m integration` selects the `slow` tests as well. The feedback integration tests create and drop their own generated `_test` databases through the same raw test connection, and the HTTP tests compose synthetic intake settings with the committed example feedback definition and a temporary attachment root instead of reading a site's feedback settings.

## Frontend modules and rendered components

The browser app and the administration console each run Vitest over `src/**/*.test.ts` in a jsdom environment. The web test command also runs two documentation tests with Node's test runner: the wiki compiler test and the help-link test. The help-link test reads the `/docs#<page>/<heading>` links in `web/src` and `admin-web/src` and enforces that each one names a page the tracked wiki selection in `examples/config/wiki.json` lists and a heading that page carries. The console adds a test-only no-op `ResizeObserver`, because jsdom supplies the DOM without layout measurement.

Most frontend tests cover state, actions, request dispatch, the solver and read modules. Rendered checks mount the real components in jsdom.

The browser app checks cover the error notice, the shell language, the course completion control, the tab carousel and its touch swipes, the cached report read, the served header tabs, the standalone feedback form and its publication choice, the structure editor, its module confirmation and its edits, the Discover list preservation, the module lookup box and its version hand-off, the comparison pane, its slot hydration, its replacement question and its result meters, the saved-data reset, the whole-state import, the search submit and activity re-read, the semantic fallback notice, the minimum route ownership and the feature bootstrap.

The console checks cover the signed-in shell and its tab session, the preparation stage and inference run panels, a panel's visibility read loop, the backups inventory, the log panels and their explicit worker read, the rebuild confirmation, the configuration save, the dataset and backup cleanup, the sixth feedback tab and its named local deletion, a confirmed target decision and a refused feature-switch write.

A rendered check that reads through the API answers that route through a small fetch fixture with typed reports and throws on an unexpected request. A rendered test that needs layout supplies test-local viewport and row geometry and a no-op `ResizeObserver`, while the module lookup renders the real virtual window. A file import uses a real test `File` with its text reader installed, and the export check records the stored text inside the test. jsdom supplies the DOM without layout or a browser process, so these checks prove component wiring and visible state. The browser journeys prove the browser rendering itself.

Five Node journeys under `web/tools/` drive the built app in headless Chromium against one disposable database loaded with the example dataset. `browser-route.test.mjs` covers the served minimum route and its browser worker, `browser-phone.test.mjs` the phone shell and its swipe navigation, `browser-lookup-guard.test.mjs` the lookup touch guard, `browser-docs.test.mjs` a configured documentation page with its return control, and `browser-docs-search.test.mjs` the documentation search. The shared fixture opens an isolated context, seeds the saved profile and tab, and dispatches native touch input. The runner in `tests/web/browser_runner.py` creates one fresh database, loads the example dataset, serves the built app on a loopback port and stops every process and database it created. The journeys prove the built app's browser rendering, its worker execution and its touch input.

The feedback submission proofs use an isolated loopback composition instead: one migrated feedback application store, a temporary repository root, the real front router over real worker applications, temporary attachment files and the real feedback routes.

The wiki compiler test covers the configured allowlist, navigation order and depth, Markdown destinations, HTML safety, root-relative links and images, and missing images. It builds pages from a temporary repository tree.

## Output and runtime state

`data/` holds the product's runtime state and the load tool's run area under `data/load/`. Tests write only to temporary directories.

## Checks on every push

The checks on every push are the lint and format checks, the network-free Python suite, the browser app and administration console checks, the PostgreSQL integration selection and the five browser journeys. [Local checks](/docs/testing/local-checks.md) lists the exact local commands. [Solver fixtures](/docs/testing/solver-fixtures.md) lists the seven generated solver JSON files and their regeneration commands.

The slow tests and the live tests are selected on request. [Local checks](/docs/testing/local-checks.md#checks-on-every-push-and-pull-request) lists the exact commands and states where the workflow's commands differ from the local ones. The checks on every push start no model, run no remote stage and read no public curriculum source.

## Serving load measurement

The serving load tooling runs a per-operation cost matrix and a steady capacity ladder against a disposable stack from one versioned workload and one machine configuration. [Serving load measurement](/docs/testing/load-measurement.md) states the machine configuration, the workload sections, the stack launcher, the cost matrix result, the admission fit, the k6 bundle, the level summarizer and the saturation view.
