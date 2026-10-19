# Command line

Feature read scripts delegate to package commands and print their JSON reports, while the administration command and the two launchers provide separate entry points.

## The scripts

The feature read scripts answer one read each and print one JSON report line.

| Script | Purpose |
|---|---|
| `scripts/search.py` | One unified search over one query, with the four search methods merged into one entry per course. |
| `scripts/course_lookup.py` | Course narrowing by case-insensitive substring over the displayed official name or official code. |
| `scripts/module_lookup.py` | Module narrowing by case-insensitive substring over the displayed name or code of the current academic year. |
| `scripts/compare_courses.py` | The five meters and the verdict for two course identities. |
| `scripts/prerequisites.py` | The prerequisite graph of one course, or its minimum-new-credit route with `--route`. |
| `scripts/next_courses.py` | The courses the chosen basis covers, under the chosen mode. |
| `scripts/recommendations.py` | The courses similar to the chosen basis, ranked. |
| `scripts/study_structure.py` | The official structure of one degree programme or module. |

Four further entry points under `scripts/` provide administration, example data preparation, web serving, and administration serving.

| Entry point | Purpose |
|---|---|
| `scripts/admin.py` | The operator menu and the machine commands for setup, the stages, datasets, backups, configuration, server status, logs, usage, dispositions, rebuilds, the password, coverage, summary and hubs. |
| `scripts/mock_data.py` | The example dataset loader and artifact writer. The two import actions print one report each, and the artifact action prints nothing. |
| `scripts/run_web.sh` | The launcher. It starts the web server process and prints no report. |
| `scripts/run_admin_web.sh` | The administration backend launcher. It execs `./.venv/bin/python -m course_explorer_admin_web` and prints no report. |

A feature script parses its arguments and calls one command function, and the administration command delegates to the administrative dispatcher, so a rule lives in a package command and never in the script. Every machine command prints one report from its owner, and the operator menu prints one report for each action it runs.

## How a command behaves

A feature read script runs in the process that calls it, prints exactly one JSON report line on standard output, and returns exit status 0. A rejected input raises from the command and the script does not catch it, so a failed call prints no report and the caller sees the failure.

Each read command opens its own database context and reads the [selected dataset](/docs/reference/glossary.md#administration). The report of a command is self-contained and holds the result of its read.

- The search report repeats the effective semantic and fuzzy thresholds, the activity scope, and the tier order it used.
- The course lookup report repeats the query and the language and carries the activity scope.
- The module lookup report repeats the query and the language and carries the academic year.
- The next-course report carries the two canonical input sets, the chosen basis, the mode, the language and activity flags, and the ordered results.
- The recommendation report carries the similar courses alone.
- The comparison report carries both summaries, the meters, and the verdict.
- The graph report carries the compiled expression, the drawing with its node states, and the drawing counts.
- The route report carries the outcome, the new credits, the new courses, and the located problems.
- The structure report carries the root, its rules, and its nodes.

[Search](/docs/backend/search-and-discovery/search.md), [Comparison](/docs/backend/search-and-discovery/comparison.md), [Next courses](/docs/backend/search-and-discovery/next-courses.md), [Recommendations](/docs/backend/search-and-discovery/recommendations.md), and [Structure of studies in the catalogue](/docs/backend/catalogue/study-structure.md) describe the reads and their reports.

## Identities and language

The commands that take a course identity accept either a canonical identity or an exact official code, and a canonical identity takes precedence. A blank input, an unknown input, and an official code held by more than one course each fail instead of resolving to a guess. The structure command takes one canonical module identity, and the search, course lookup, and module lookup commands take a text query.

`--display-language` is required by the commands that render official names, and its value is `fi` or `en`. Five scripts take it: search, course lookup, module lookup, next courses, and recommendations. The other commands select no app language, so they take no language option.

## Scope, basis, and toggles

The discovery commands start with inactive courses left out and accept `--all-courses` to include them, while the search, course lookup, and prerequisites commands start with inactive courses included and accept `--active-only` to limit the read. The comparison and structure commands take no activity option.

`--basis` chooses which set counts as covered, either `completed` or `selected`, and it defaults to `completed`. On the prerequisites, next-course, and recommendation commands, `--completed` and `--selected` are repeatable and accept canonical identities or exact official codes. The next-course and recommendation commands use the completed set as the selected set when no selected code is supplied, and a supplied selected set must contain every completed course.

Prerequisites adds `--excluded` and the two category toggles. Each repeatable `--excluded` course appears in the drawing while the calculation routes around it, and excluding the opened root blocks the whole request. `--include-recommended` and `--include-inferred` each add their category to the drawing and to the calculation, and the two are independent.

The next-course and recommendation commands add `--mode`, either `all` or `at_least_one`, and it defaults to `all`. The category toggles are off by default.

## The graph and the route

`scripts/prerequisites.py` prints the prerequisite graph report unless `--route` is given, and `--route` prints the minimum-new-credit result instead. One invocation prints exactly one of the two results. The graph report carries no route result, and the route result carries no drawing graph.

Both operations compile one expression for the root, so the drawing and the calculation cannot describe different requirement sets. A script caller passes no drawing limit, so the graph report always carries a drawing. The web graph route applies the configured limit instead. [Prerequisite graph](/docs/backend/prerequisites/prerequisite-graph.md) and [Minimum route](/docs/backend/prerequisites/minimum-route.md) describe the two operations.

## The administration command

`scripts/admin.py` delegates to the administrative dispatcher, which owns one parser and one JSON emitter. Without a subcommand, and with `menu`, it starts the numbered operator menu, which continues until Exit, an end of input, or an interrupt. [Operator menu](/docs/operations/operator-menu.md) describes the menu and the operations it drives.

The machine commands are `setup datasets`, `setup worker`, `preflight`, `migrate datasets`, `datasets list`, `datasets delete DATASET_ID`, `backups list`, `backups delete NAME`, `config list`, `config read FILE`, `config set FILE KEY VALUE`, `password --username USERNAME`, `server status`, `logs sessions`, `logs commands`, `logs read STAGE SESSION_ID SOURCE --lines N`, `logs embedding --lines N`, `usage --hours HOURS`, `rebuild`, `rebuild-admin`, `restart-admin`, `dispose inference TARGET_ID DISPOSITION`, `target inference TARGET_ID`, the four stages with the actions `start`, `pause`, `resume`, `status`, and `stop`, `coverage KIND` with `teaching-text`, `embedding` or `inference`, `summary KIND` with `catalogue` or `inference`, and `hubs`.

The administration command differs from the read scripts in three ways.

- It reports the state of the selected dataset and of the stages, and some of its commands write to the dataset or to the worker.
- A failure prints one content-free JSON line holding the exception's class name, plus fixed guidance, to standard error, and returns exit status 1. A checked subprocess failure adds its return code. An interrupt returns 130, and a not-ready `preflight` prints its report and returns 1.
- `coverage` and `summary` also print a fixed note to standard error, stating that the reports read the selected dataset and not unreturned worker progress.

`hubs` computes both embedding hub means from the current chunk vectors of the selected dataset and writes the two files that the hub keys reference. Both means are computed before either file is written. A web server whose site serves embedding features reads both hub files when its process starts, so restart the serving process after writing them. The embedding tool in the operator menu offers the same write. [Embeddings](/docs/backend/text-and-vectors/embeddings.md#the-hubs) describes the hub files.

## Dataset and backup cleanup

`datasets` and `backups` each take one nested verb, and each verb runs one delegate.

`datasets list` reports the retained dataset chain in chain order from its receipts, with the dataset id, the kind, the database name, the repository-relative retained dump path and the selected mark of each entry. The selected dataset is always listed, and any other dataset is listed when its server database exists or its retained dump is present. The database name is the name the receipt records, an absent retained dump reports no path, and the read creates no state.

`datasets delete DATASET_ID` drops one non-selected dataset's server database and removes its retained dump. It refuses an id outside the chain, the selected dataset, a receipt naming the selected database, a database name on the fixed protected list, with the selection switch off the database the site serves, and an unsafe retained dump before it changes a resource, and it leaves the receipt, the pointer and every database outside the chain in place. [Datasets](/docs/operations/datasets.md#manual-cleanup) states the whole outcome.

`backups list` reports every regular file under `data/backups` in lexical relative-path order with its size and its last modification time. `backups delete NAME` removes the one regular file that relative name identifies and refuses a name that leaves the root.

All four commands print their owner's report and return exit status 0. A failure prints the content-free JSON line and the guidance of the cleanup kind to standard error, and returns exit status 1. [Operator menu](/docs/operations/operator-menu.md#cleanup-of-datasets-and-backups) holds the same operations behind a confirmation.

## Configuration reads and writes

`config` takes one nested verb, and each verb runs one delegate.

`config list` reports the registered subsystem files in composition order with the device-local environment file last, and it reads no file.

`config read FILE` reports every key of one listed file as that file holds it. A subsystem file is parsed as TOML, so a hub key is reported as its reference table rather than the vector the table points at. The environment file is parsed into its assignments, a bare key reports no value, and every value is reported in plain text. The report is transient and is the one command output that carries file values.

`config set FILE KEY VALUE` replaces the one key of the one listed file with `VALUE`, which is one JSON literal over the broad type the key holds. The write renders only that key's text and leaves every other key with its comments, its order and its line endings. It validates the whole candidate through the settings families that own the key, comparing the key and the aliases without case, reading the environment file freshly and parsing it strictly, and publishes the file atomically. A malformed assignment and a key assigned more than once in the environment file, ignoring case, each refuse the save. An environment-file save locates the stored binding without case and preserves its spelling. An environment-file write is mode 0600 and a subsystem file is published with its own permission bits. The acknowledgment holds the file and the key and no value.

```bash
uv run python scripts/admin.py config list
uv run python scripts/admin.py config read config/web.toml
uv run python scripts/admin.py config set config/web.toml WEB_PORT 18026
uv run python scripts/admin.py config set config/curriculum.toml CURRENT_ACADEMIC_YEAR '"2027-2028"'
```

Every example uses a synthetic value, and an environment-file read is the only command output that renders a device credential.

An unlisted file, a key the file does not carry, a JSON `null`, a non-finite number, a value of the wrong broad type, a value the owning settings family refuses, a value that is not one JSON literal, and a malformed or case-insensitively duplicated environment-file assignment each print the content-free JSON line and the configuration guidance to standard error and return exit status 1. [Operator menu](/docs/operations/operator-menu.md#configuration) holds the same reads and the same save behind a confirmation.

## The administration password

`password --username USERNAME` stores the site's one administration account through one fixed command run over SSH. `--username` is required, and the password is read twice at the hidden terminal prompts `Password: ` and `Repeat password: `, so it never appears in the command line, in an argument, in an environment value or in a pipe. The credential owner hashes the entry with argon2id and publishes the credential file. An entry the terminal cannot hide is an error rather than an echoed fallback, two different entries are refused, and the acknowledgment names no credential.

```bash
uv run python scripts/admin.py password --username OPERATOR
```

The command prints one acknowledgment line and returns exit status 0. It neither deletes the site's lock nor resets the failed-attempt count, and no configuration command can read or write the credential file, because administration state is not configuration. [Operator menu](/docs/operations/operator-menu.md#the-administration-password) holds the same command behind Setup choice 9. A failed command prints the content-free JSON line and the password guidance to standard error and returns exit status 1.

## The target identity read and the summary policies

`target inference TARGET_ID` reads one canonical target's identity and its current durable decision without changing anything. It prints the owner's `InferenceTargetDisposition` report, which holds `dataset_id`, `target_group_id`, `course_code`, `course_name` and `disposition`, where `disposition` is `null` for an automatic target and one of `done` and `failed` for an explicit decision. The read holds the same guards as the decision, because it resolves the target through the selected dataset.

`dispose inference TARGET_ID {nothing|done|failed}` sets that decision, and `nothing` maps to `null` before the call, so the stored decision records an automatic target rather than a terminal one. The menu's **Dispose target** entry reads the identity before it asks for the decision, so the operator sees what the decision applies to. Both commands print the content-free JSON line and the disposition guidance to standard error and return exit status 1 when a guard refuses them.

```bash
uv run python scripts/admin.py target inference TARGET_ID
uv run python scripts/admin.py dispose inference TARGET_ID done
```

The detailed `summary inference` report holds, beside its coverage, publication and failure members, the three configured inference policy values `routing_policy`, `recommendation_policy` and `finding_filter_policy`, projected from the loaded generation settings rather than from a stored duplicate.

## Server status, log reads and rebuild
`server` takes one nested verb, and the verb runs one delegate. `server status` prints one read-only report of the server the command runs on. The report holds the `website`, `host`, `database`, `embedding`, `serving` and `hubs` members, it contacts no worker, and it retains nothing. [Operator menu](/docs/operations/operator-menu.md#the-server-status-report) states each member's facts.

The report states which kind of fact each member carries: measured values from the unit, the kernel and the database, configured values from the settings, the selected dataset's receipt facts, and the checkout identity of the command itself. The receipt facts include the database head the receipt's verification records, which is neither the live database's own revision nor this checkout's expected head.

An optional fact the report finds none of is `null`: a service the Compose listing does not contain is `absent`, a hub reference that names no file has no modification time, and every receipt fact is absent while the selected-dataset switch resolves no dataset. A read, parse or stat failure, a hub reference that does not name a regular file, and an unloaded unit, a unit from another directory or a unit whose command line does not carry this checkout's `scripts/run_web.sh` each fail the command instead of reporting a fact.

`logs` takes one nested verb. `logs sessions` lists the sessions of the four stage roots, newest first, with each session's stage, identity and receipt time. `logs commands` prints the retained entries of the sole administration command log oldest first, each with its time, fixed command label, exit code, elapsed duration, outcome token and its one safe failure line when it has one. The read resolves this checkout and the configured `ADMIN_WEB_COMMAND_LOG_LIMIT`, reads the log owner's own file and creates no file, so an absent log prints an empty entry list and no invocation rewrites the file.

`logs read STAGE SESSION_ID SOURCE --lines N` prints the last `N` lines of one fixed source of one listed session, and `SOURCE` is one of `server-stdout`, `server-stderr`, `keepalive`, `worker-runner` and `worker-runtime`. `--lines` is required and takes an integer, and the owner refuses a count that is not positive before it reads anything. `logs embedding --lines N` prints the last `N` lines of the embedding service's own container log.

The stage and the source are closed sets that the parser checks, and the session identity selects one recorded receipt of that stage. No argument carries a path, a filename or a shell command, so every read reaches one fixed basename beneath a derived directory.

Every directory from the filesystem root through the session directory must be a real directory, so a symlink or another redirect anywhere in that chain is refused before a log path is read, and `logs sessions` skips only a genuinely absent stage root. A worker source reads over the same SSH/WSL transport the stages use, on demand.

An absent log is reported as unavailable with `text` set to `null`, a log file that holds no lines is reported as available with empty text, and a log that is a symlink or not a regular file is refused. A read failure, an unreachable worker and a timeout print the content-free JSON line and the log guidance to standard error and return exit status 1, and no captured log text reaches that line.

```bash
uv run python scripts/admin.py server status
uv run python scripts/admin.py logs sessions
uv run python scripts/admin.py logs commands
uv run python scripts/admin.py logs read inference SESSION_ID worker-runner --lines 50
uv run python scripts/admin.py logs embedding --lines 100
```

`rebuild` builds the site frontend, recreates the database and embedding containers, restarts the site's web unit and checks its loopback bind. It works on the checkout as it stands, uses the prepared container images, reaches no worker, and restarts only the site's own web unit. The report names the four steps and the verified bind, and the first failing step prints the content-free JSON line and the rebuild guidance and returns exit status 1.

`rebuild-admin` builds the administration frontend alone, and `restart-admin` queues one non-blocking restart of this checkout's own administration unit. Both read the required site identities `ADMIN_SITE_WEB_SERVICE_UNIT` and `ADMIN_SITE_ADMIN_SERVICE_UNIT` from the device-local environment file, and each verifies before it acts that the named administration unit is loaded, runs from this checkout and carries the exact `<checkout>/scripts/run_admin_web.sh` token. A unit of another directory, another launcher or another site is refused before anything changes. Neither command recreates a container, opens a database or contacts the worker.

`rebuild-admin` performs the one frontend build and reports its single step. A failed frontend build can change the administration frontend output directory, and it queues no restart. A terminal or menu sequence runs the two commands in order and reaches `restart-admin` only after a successful build: `rebuild-admin` followed by `restart-admin`.

`restart-admin` returns after the restart request is admitted, and its report acknowledges the queueing alone. It claims no observed restart, no restarted process and no verified bind. A failed build and a refused restart each print the content-free JSON line and the rebuild guidance and return exit status 1.

```bash
uv run python scripts/admin.py rebuild
uv run python scripts/admin.py rebuild-admin
uv run python scripts/admin.py restart-admin
```

## The request usage report

`usage --hours HOURS` takes one required option and prints one report of the recorded web requests, and it prunes the records past the configured retention. `--hours` takes a positive integer.

The window is whole hours back from the current rounded UTC hour inclusive. `--hours 1` covers the current hour, the window ends at the end of that hour, and the report holds `window_start`, `window_end`, `requests`, `mean_duration_seconds` and `routes`. Each route row holds its `route`, its `requests` and its `mean_duration_seconds`, the rows sort by route, and the mean duration is the arithmetic mean of the recorded elapsed serving seconds. A window with no recorded request reports zero requests, no mean duration and no route rows.

`USAGE_RETENTION_DAYS` of `config/web.toml` sets the retention that bounds the file. A count that is not positive, or that is longer than the retention in hours, is refused before the command opens the usage file, so a window longer than the retention is refused rather than shortened. The same read drops the records older than the retention in days and retains every newer record, including one outside the reported window. One invocation therefore reports a window and prunes the file.

[Web server](/docs/backend/interfaces/web-server.md#the-request-usage-record) describes the records the serving middleware appends and the file they live in. The report and the serving append take one exclusive lock on the same file, so an append never interleaves with the report's rewrite and neither one loses a record. An absent usage file reports zero requests and creates no file, and a malformed line fails the command without rewriting the file.

```bash
uv run python scripts/admin.py usage --hours 24
```

[Operator menu](/docs/operations/operator-menu.md#the-usage-report) holds the same report behind its hours prompt.

## The example data loader

`scripts/mock_data.py` is data preparation rather than a feature read. Its three actions import the invented example dataset, add the bundled vectors of that dataset, and write the bundled vectors and both hub files. The loader refuses a configuration with the selected-dataset switch enabled, so it fills the configured database, and it requires that database at the running code's migration head. The two import actions print one report each, and the artifact action prints none. [Data preparation](/docs/getting-started/data-preparation.md) describes when the loader runs.

## Usage

```bash
uv run python scripts/search.py "data structures" --display-language en --active-only
uv run python scripts/admin.py coverage embedding
uv run python scripts/mock_data.py load
```

The comparison command takes two course identities as positional arguments, and the structure command takes one canonical module identity as a positional argument, which the module lookup report supplies.

The stage actions, the dataset operations, and the worker operations are described in [Stage lifecycle](/docs/operations/stage-lifecycle.md), [Datasets](/docs/operations/datasets.md), and [Worker sessions](/docs/operations/worker-sessions.md).
