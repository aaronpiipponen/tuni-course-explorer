# Command adapters

The scripts directory holds one adapter per command surface: the feature reads, the example data loader, the administrative dispatcher, the three shell launchers, and the native library build.

## The adapters

| Script | Callable | Report |
|---|---|---|
| `scripts/search.py` | `course_explorer.search.commands.run_search_command` | `UnifiedSearchReport` |
| `scripts/catalogue.py` | `course_explorer.search.lookup_commands.run_catalogue_command` | `CatalogueReport` |
| `scripts/compare_courses.py` | `course_explorer.comparison.commands.run_course_comparison_command` | `CourseComparisonReport` |
| `scripts/prerequisites.py` | `course_explorer.prerequisite.commands.run_prerequisite_command` or `run_minimum_route_command` | `PrerequisiteGraphReport` or a minimum-route result |
| `scripts/next_courses.py` | `course_explorer.next_courses.commands.run_next_courses_command` | `NextCoursesReport` |
| `scripts/recommendations.py` | `course_explorer.recommendations.commands.run_recommendations_command` | `RecommendationsReport` |
| `scripts/study_structure.py` | `course_explorer.study_structure.commands.run_study_structure_command` | `StudyStructureReport` |
| `scripts/admin.py` | `course_explorer_admin.cli.main` | The owner's DTO per administration command |
| `scripts/mock_data.py` | `course_explorer.mock_data.run_mock_data_command` | `NormalizationReport`, `CourseEmbeddingCoverageReport`, `ServingArtifactsReport`, or nothing |
| `scripts/run_web.sh` | No callable, it execs the checkout's interpreter with `-m course_explorer_web.launch` | No report |
| `scripts/run_admin_web.sh` | No callable, it execs the checkout's interpreter with `-m course_explorer_admin_web` | No report |
| `scripts/run_feedback_sender.sh` | No callable, it execs the checkout's interpreter with `-m course_explorer.feedback.sender` | No report |
| `scripts/build_native.py` | `main` in the same file | No report. It writes the native libraries into `native/`. |

The command and read adapters hold no rule of their own, matching [Adapters hold no business logic](/docs/architecture/invariants.md#adapters-hold-no-business-logic). `scripts/build_native.py` is the build adapter, and it holds its own build steps.

## Argument contracts

| Script | Arguments |
|---|---|
| `search.py` | `query` positional, `--display-language` required with choices from `get_args(DisplayLanguage)`, `--semantic-min-score` float, `--fuzzy-min-score` float, `--active-only` store true |
| `catalogue.py` | No argument and no option |
| `compare_courses.py` | `course_a` and `course_b` positionals, no option |
| `prerequisites.py` | `course_code` positional, `--completed`, `--selected`, `--excluded`, `--completed-node`, and `--excluded-node` append, `--include-recommended`, `--include-inferred`, `--active-only`, `--basis` with the choices `completed` and `selected`, `--route` store true |
| `next_courses.py` | `--selected` and `--completed` append, `--basis`, `--mode` with the choices `all` and `at_least_one`, `--display-language` required, `--include-inferred`, and the mutually exclusive `--active-only` and `--all-courses` |
| `recommendations.py` | The same set as `next_courses.py` |
| `study_structure.py` | `root_group_id` positional, `--module-version GROUP_ID=VERSION_ID` append |
| `admin.py` | No parser, the dispatcher owns it |
| `build_native.py` | `--non-interactive` and `--fixtures` store true, and no positional argument |
| `mock_data.py` | `action` positional with the choices `load-curriculum`, `load`, `write-artifacts` and `write-bundle`, `--fixture-dir` defaulting to `data/mock`, `--raw-root` defaulting to `data/mock-import` |

`search.py` maps `--active-only` to `include_inactive=not args.active_only`. `next_courses.py` and `recommendations.py` call `parser.set_defaults(active_only=True)`, so an invocation without either activity flag reads active courses only. `prerequisites.py` builds one `options` dict and passes it to whichever prerequisite command the invocation selects. `--route` prints the minimum-new-credit result from the shared TypeScript solver run through Node.

The comparison adapter takes its identities as positionals and declares no option. The structure adapter takes its root as a positional and repeatable exact group-to-version selections, so it owns argument parsing alone and no selection rule.

## The checkout source

Every script under `scripts/` that imports the product calls `install()` from `scripts/_checkout_source.py` before its first product import. `install()` puts the `src` directory of the checkout that holds the script first on `sys.path` and prepends it to `PYTHONPATH`, so the process and the children it starts read that checkout's package. The adapters keep their product imports inside `main()` after the call, so no product module loads before the checkout is on the path.

The three shell scripts name the same `src` directory on the `PYTHONPATH` of the process they exec.

## Delegation and output

Every feature adapter and the example-data adapter define `main(argv: Sequence[str] | None = None) -> int`, parse with `argparse`, and call their command once. A returned report is printed with `report.model_dump_json()`, and the route command prints the object its command returns with `json.dumps`. A successful call returns 0. Each closes with the `if __name__ == "__main__":` guard and `raise SystemExit(main())`, so the process exit status is the function's return value.

`scripts/admin.py` is the administrative adapter. It calls `install()`, imports the dispatcher inside `main()`, and returns the dispatcher's exit status, so the parser, the JSON emission, and the exit status belong to the dispatcher rather than to the script. The script states the command grammar in its usage header and holds no rule of its own.

A feature adapter lets every exception propagate, so a command failure reaches the caller as an uncaught exception and no partial report is printed. `argparse` exits with a usage message before any command call when an argument is missing or unknown.

`mock_data.py` prints the returned report, so the `write-artifacts` action prints one `ServingArtifactsReport` line and returns 0, and the two load actions print their own report line. The `write-bundle` action returns no report and prints nothing.

## The administrative dispatcher

`course_explorer_admin/cli.py` owns the one administrative parser, the JSON emission, and the safe failure presentation.

- `_parser()` builds `ArgumentParser(prog="admin.py")` with one subcommand per command group:
  - `menu`, `preflight`, `rebuild`, `rebuild-admin` and `restart-admin` take no further argument, and `serving-artifacts` takes optional `--dataset ID` and `--prune`.
  - `coverage` takes one required kind out of `teaching-text`, `embedding` and `inference` plus a required `--role` of `selected` or `working`, and `summary` takes one required kind out of `catalogue` and `inference` plus the same required role.
  - `setup` takes `datasets` or `worker`, with `--branch` defaulting to `main` and a `--code-only` flag. The worker choice alone uses them, and the dataset choice refuses a branch other than `main` and refuses `--code-only`.
  - `migrate` takes `selected`, `working` or `database`.
  - `datasets` takes `list`, `delete DATASET_ID`, `copy-to-working SOURCE_DATASET_ID`, `copy-to-selected SOURCE_DATASET_ID` with `--confirm-restart`, and `ensure-selected`, and `backups` takes `list` and `delete NAME`.
  - `config` takes `list`, `read FILE` and `set FILE KEY VALUE`, and `server` takes `status`.
  - `logs` takes `sessions`, `commands`, `read STAGE SESSION_ID SOURCE --lines N` and `embedding --lines N`.
  - `feedback` takes `list [--query TEXT] [--filters JSON]`, `attachment FEEDBACK_ID ATTACHMENT_ID` and `delete FEEDBACK_ID`.
  - `password` requires `--username`, and `usage` takes `--hours`.
  - `dispose` takes `inference`, one target and one disposition out of `nothing`, `done` and `failed`, and `target` takes `inference` and one target.
  - Each stage name takes one action out of `_ACTIONS`.
- The `logs read` source choices come from the source literal itself, and `--lines` is required on both log verbs. The administration backend passes a configuration file or key and a backup name after a `--` separator, which the parser accepts as a positional argument. A target id is refused when it begins with a hyphen, so it cannot reach the parser as an option. The worker branch uses the `--branch=BRANCH` form.
- `main(argv=None, *, run_command=None, run_summary=None, configuration_families=())` parses one command and delegates once. An absent command, or `menu`, runs `run_operator_menu`. `target inference TARGET_ID` delegates once to `commands.read_inference_target_disposition`, which is the same owner the menu's identity-first flow reads before it asks for a decision. A supplied `run_command` or `run_summary` replaces that one call and nothing else, so a wrapper can inject an extra route without a second parser. The family tuple reaches the configuration save and the menu's configuration entry alone, so a wrapper supplies the validation families of a package the base product does not import.
- `_emit(report)` prints `report.model_dump_json()` to standard output and the fixed `worker_origin_notice(report)` text to standard error.
- `main` returns 0 on success, 1 on failure, and 130 on `KeyboardInterrupt`. `preflight` returns 1 when the report carries no resources or reports them as not ready.
- `_fail(exc, operation)` prints `format_operator_error(exc)`, which holds only the exception class name and the `returncode` of a checked subprocess failure. It then prints `operator_guidance(operation, configuration_error=isinstance(exc, ValidationError))`.
- The operation of an invocation is one of 23 fixed names: `setup`, `preflight`, `stage`, `report`, `migration`, `disposition`, `target-read`, `serving-artifacts`, `dataset-cleanup`, `dataset-copy`, `dataset-list`, `dataset-promotion`, `backup-list`, `backup-cleanup`, `configuration`, `server`, `logs`, `rebuild`, `usage`, `password`, `feedback`, `self-host-example` and `self-host-real-database`. Each name selects one fixed line of guidance: `setup` and `stage` for the setup and stage commands, `preflight` for the worker preflight, `report` for coverage and summary, `migration` for the dataset migration, `disposition` for the decision command, `target-read` for the target read, `serving-artifacts` for the artifact build, `dataset-list` and `backup-list` for the two listings, `dataset-copy` for `copy-to-working`, `dataset-promotion` for `copy-to-selected`, the two cleanup names for the deletions and `ensure-selected`, the two self-host names for `self-host example` and `self-host real-database`, `configuration` for the configuration commands, `server` for the server status, `logs` for the log reads, `rebuild` for the three rebuild and restart verbs, `usage` for the usage report, `password` for the password command, and `feedback` for the feedback reads and deletion.
- `coverage` and `summary` print `REPORT_SCOPE` to standard error as well.

The two self-host commands follow the same delegate shape. `run_administrative_example_setup` takes one `ExampleSetupInput`, and `run_administrative_real_database_setup` takes one `RealDatabaseSetupInput`, each with an optional process runner and writer. Each delegate resolves the production subprocess runner and calls `setup_example` or `setup_real_database` in `course_explorer_admin.self_host` once, and each returns the transient `SelfHostReport`: the address to open and the Selected dataset id, which is `null` for the example path.

The four cleanup commands each call one command function and emit its report. `run_administrative_dataset_list` returns a `DatasetListReport`, `run_administrative_dataset_delete` takes the one dataset id and returns a `DatasetDeletionReport`, `run_administrative_backup_list` returns a `BackupListReport`, and `run_administrative_backup_delete` takes the one relative name and returns a `BackupDeletionReport`. The two dataset delegates resolve the production subprocess runner exactly as setup does, because the listing owner probes the database through Compose and the deletion owner drops it through Compose, and each owner lives in its own module: `course_explorer_admin.datasets` owns the receipt chain and the drop, and `course_explorer_admin.backups` owns the directory under `data/backups`. A cleanup failure prints the class token and the `dataset-list` or `backup-list` guidance for a listing and the `dataset-cleanup` or `backup-cleanup` guidance for a deletion, so a refusal names the listing and the running database service rather than a payload.

The three configuration commands each call one command function and emit its report. `run_administrative_config_list` returns a `ConfigurationFilesReport`, `run_administrative_config_read` takes the one file name and returns a `ConfigurationFileReport`, and `run_administrative_config_set` takes the one file, the one key and the one JSON literal value plus an optional tuple of settings families, and returns a `ConfigurationWriteReport`. The families belong to the caller, and the editor for the files lives in `course_explorer_admin.configuration` beside the file-source owner it reads and writes through. A save failure prints the class token and the `configuration` guidance, so a refusal names the listing, the key and the file permissions rather than a value. A caller supplies the families of a package the base product does not import as the tuple, and the dispatcher accepts an empty tuple.

The three feedback commands each call one command function and emit its report. `run_administrative_feedback_list` takes the optional query and filter mapping and returns a `FeedbackListReport`, `run_administrative_feedback_attachment` takes the two UUIDs and returns a `FeedbackAttachmentReport`, and `run_administrative_feedback_delete` takes one UUID and returns a `FeedbackDeletionReport`. Each delegate opens `feedback_context()` once and delegates once to the one feedback owner, which owns the configured matching, the scoped read and the named deletion. The dispatcher decodes `--filters` with `parse_feedback_filters` and converts the UUID arguments inside its safe-error block. A refusal prints the class token and the feedback guidance, so it names the configured definition, the database connection and the stored identity rather than a query, a filter value or file bytes.

The server status, log, usage and rebuild commands each call one command function and emit its report.

- `run_administrative_server_status` takes an optional runner and returns a `ServerStatusReport` from `course_explorer_admin.server`.
- `run_administrative_log_sessions` takes no argument and returns a `LogSessionsReport`. `run_administrative_session_log` takes the stage, the session identity, the source and the required line count and returns a `LogReadReport`, and `run_administrative_embedding_log` takes the one line count and returns a `LogReadReport`.
- `run_administrative_command_log` takes no argument and returns the `CommandLogReport` its owner `course_explorer_admin_web.command_log.read_command_log` assembled.
- `run_administrative_usage` takes the one hour count, loads `UsageSettings` once for the retention and returns a `UsageReport` from `course_explorer.usage`. Its owner reads the retained lines and rewrites the file under one exclusive lock, releases the lock, and then computes the window count, mean and exact nearest-rank p95 and p99 from the records it selected, overall and per route.
- `run_administrative_rebuild` takes an optional runner and returns a `RebuildReport` from `course_explorer_admin.rebuild`.

The command-log delegate imports its owner inside the call, because the administration backend package imports this dispatcher.

The two administration maintenance commands follow the same delegate shape. `run_administrative_admin_rebuild` takes an optional runner and returns an `AdminRebuildReport`, and `run_administrative_restart_admin` takes an optional runner and returns an `AdminRestartReport`. Both reports come from `course_explorer_admin.rebuild`, both delegates resolve the production subprocess runner as setup does, and `commands` re-exports the two report models beside its delegates. The behavior of the two operations, the required own-unit identity they share and the ordering a sequence of them holds belong to their owner, so this layer neither validates a unit nor orders the two calls.

The server status and the log reads resolve the production subprocess runner exactly as setup does, and the session-log delegate passes that runner to its owner because a worker source reaches the configured worker over the transport. A failure prints the class token and the `server`, `logs`, `rebuild` or `usage` guidance, so a refusal names the site unit and this checkout, the listed session and source, the prepared resources, or the requested window and the usage-file permissions rather than a payload.

`run_administrative_password(*, username, read_password=None)` reads the password twice through the caller's reader, which defaults to the hidden terminal prompt, refuses two different entries, and delegates once to `course_explorer_admin.credentials.set_admin_password` with a wrapped password. It returns the credential owner's `PasswordSetReport`, whose only field is its own `configured` token, so the acknowledgment carries no credential. The command takes no password argument, no environment source and no piped-password mode. `commands` re-exports `PasswordSetReport` beside the delegate.

`dispose ... nothing` maps the token to `None` before the call, so the stored decision records an automatic target rather than a terminal one. A refusal of `dispose` prints the class token and the disposition guidance. A refusal of `target` prints the class token and the target-read guidance. Both commands read the same Working dataset.

## The launcher scripts

`scripts/run_web.sh` is the shell adapter for the web server. It enables `set -euo pipefail`, sets `PYTHONPATH` to the checkout's `src` directory, and execs the checkout's `.venv/bin/python -m course_explorer_web.launch`, so the launcher takes the place of the shell process. The launcher module composes the seven settings families every site needs and adds the embedding family only when the site serves embedding features, then hands the serving process a settings-file-free environment, as described in [Web supervisor](/docs/backend/interfaces/web-supervisor.md#the-launcher-and-the-environment-handoff).

`scripts/run_admin_web.sh` is the shell adapter for the administration backend. It enables `set -euo pipefail`, sets `PYTHONPATH` to the checkout's `src` directory, and execs the checkout's `.venv/bin/python -m course_explorer_admin_web`, so the backend takes the place of the shell process. The backend's own entry point loads `AdminWebSettings` and builds the application, as [Administration backend](/docs/backend/interfaces/admin-backend.md) describes.

`scripts/run_feedback_sender.sh` is the shell adapter for one feedback publication attempt. It enables `set -euo pipefail`, sets `PYTHONPATH` to the checkout's `src` directory, and execs the checkout's `.venv/bin/python -m course_explorer.feedback.sender`, so the sender module takes the place of the shell process. [Feedback publication](/docs/backend/feedback-publication.md#the-sender-operation) states the attempt that module makes.

`scripts/build_native.py` is the build adapter for the native serving libraries. It runs `docker build` against `docker/native/Dockerfile` with `sudo` and a local output target, then stages each produced shared object into the checkout's `native/` directory. `--non-interactive` passes `-n` to `sudo`, and `--fixtures` adds the test-only fixture library. A build that produces no library changes nothing.

## The example-data adapter

`course_explorer.mock_data.run_mock_data_command(action, *, fixture_dir, raw_root)` in `src/course_explorer/mock_data.py` is a data-writing adapter rather than a feature read.

- `load-curriculum` registers the invented fixture as one completed capture and applies the normalization batch, returning a `NormalizationReport`.
- `load` does the same and then reconciles the bundled vectors through the embedding repository, returning a `CourseEmbeddingCoverageReport`.
- `write-artifacts` prepares the fixture and calls the one serving-artifact builder for the set the site's embedding switch selects. It returns the builder's `ServingArtifactsReport` and writes no tracked file.
- `write-bundle` prepares the fixture and rewrites the tracked bundled vector file from the stored vectors of the prepared fixture. It returns nothing.

The command refuses a state root whose Selected pointer names an enrolled dataset, before it opens an engine, and it requires the database at the single migration head. It writes the configured database rather than reading it, and `write-bundle` additionally rewrites the tracked bundled vector file under `--fixture-dir`. The read-only web surface does not reach it.

## Adding an adapter

To add an adapter:

1. Put the behavior in one command function in the owning package, with caller-input validation before any settings load or I/O.
2. Add `scripts/<name>.py` with `main(argv=None) -> int`, an `ArgumentParser`, one call to that function, `print(report.model_dump_json())`, `return 0`, and the `__main__` guard.
3. Keep the adapter to that shape: it carries no logic of its own, and the tests of the owning command cover its public behavior at its own boundary. The table below lists the test files.

| Test file | Covers |
|---|---|
| `tests/search/test_search_command.py` | The search command's service composition and engine disposal, the single bounded query-embedding attempt, and the real lexical methods served without any embedding composition. |
| `tests/search/test_lookup_commands.py` | The catalogue command's minimal official projection and its empty summary shortcut. |
| `tests/comparison/test_comparison_command.py` | The comparison command's refusal of blank inputs before any settings load or I/O. |
| `tests/prerequisite/test_prerequisite_command.py` | Graph and route preparation over one shared structure with their results kept separate, the drawing refusal that leaves calculation and counts truthful, and the machine command returning the shared Node result. |
| `tests/next_courses/test_next_courses_command.py` | The next-course command's input validation before I/O and its empty-basis shortcut with no candidate or compiler read. |
| `tests/recommendations/test_recommendations_command.py` | The recommendation command's input validation and its empty-basis shortcut with no I/O. |
| `tests/study_structure/test_study_structure_command.py` | The structure command's blank-root refusal before settings and the explicit module-version selection forwarded to the shared batch service. |
| `tests/admin/test_operator_commands.py` | The dispatcher's input refusal, preflight status, hidden password entry with mismatch refusal, feedback list/attachment/delete delegation with parsed filters and UUIDs, class-only safe failures with no payload, and the `nothing` disposition mapping. |
| `tests/feedback/test_feedback_service.py` | The feedback owner's validated submission, configured search and filters, scoped attachment read, named deletion and no-write refusals over a disposable `_test` database and temporary files. |
| `tests/admin/test_operator_menu.py` | The numbered entries, their confirmations, and every refusal, cancel, end-of-input and interrupt that mutates nothing. |
| `tests/admin/test_configuration.py` | One subsystem-file key save and one environment-file key save, each preserving the other bytes, and each refused candidate changing neither the file nor its directories. |
| `tests/admin/test_backups.py` | The backup listing and the deletion of one confined listed file, with a refused name deleting nothing. |
| `tests/admin/test_usage.py` | One window's totals, route means and exact nearest-rank percentiles, the percentiles of one route distribution kept separate from its route rows, an empty window's unavailable values, retention pruning, and the record preservation of two appending processes beside one reporting writer. |
| `tests/admin_web/test_security.py` | The lock, the site and CSRF boundary, the static shell and asset exception, session expiry, rotation and logout. |
| `tests/admin_web/test_commands.py` | The fixed command argv and refused command shapes, and the bounded safe entries of the sole command log. |
| `tests/admin_web/test_command_log_read.py` | The command-log read command over a temporary checkout: the newest configured entries in their own order from a file that holds more, no file created for an absent log and no rewrite of a present one. |
| `tests/admin/test_server_status.py` | The server status report against the disposable database with one process-boundary double for the systemd, Compose, Git and directory-total reads. |
| `tests/admin/test_log_reads.py` | Each fixed log source, the absent log it reports as unavailable, an absent worker receipt reported as unavailable without a transport call, its refusals of a redirected session directory chain, a malformed or symlinked receipt and a non-regular log, and its one worker command over a local transport double. |
| `tests/admin/test_rebuild.py` | The four rebuild steps, its first-failure cutoff and its loopback bind check with one process-boundary double, and the administration build and restart acting only on this checkout's own administration unit through the shared loaded-unit, checkout and launcher check. |

The security tests also prove the boundary order around a refusal. A refused state-changing request leaves the idle clock of its session alone, and a raw non-ASCII CSRF header is refused before any route or idle refresh.

The static shell and asset exception mutates no session. Two sessions expire independently, a credential replacement rotates an authenticated session on its next request, the first session request after a password replacement receives an anonymous grant, a malformed stored credential fails operationally, and logout ends one session alone.
