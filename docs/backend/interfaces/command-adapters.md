# Command adapters

The scripts directory holds one adapter per command surface: the feature reads, the example data loader, the administrative dispatcher, and the web launcher.

## The adapters

| Script | Callable | Report |
|---|---|---|
| `scripts/search.py` | `course_explorer.search.commands.run_search_command` | `UnifiedSearchReport` |
| `scripts/course_lookup.py` | `course_explorer.search.lookup_commands.run_course_lookup_command` | `CourseLookupReport` |
| `scripts/module_lookup.py` | `course_explorer.search.lookup_commands.run_module_lookup_command` | `ModuleLookupReport` |
| `scripts/compare_courses.py` | `course_explorer.comparison.commands.run_course_comparison_command` | `CourseComparisonReport` |
| `scripts/prerequisites.py` | `course_explorer.prerequisite.commands.run_prerequisite_command` or `run_minimum_route_command` | `PrerequisiteGraphReport` or `MinimumCreditPathEvaluation` |
| `scripts/next_courses.py` | `course_explorer.next_courses.commands.run_next_courses_command` | `NextCoursesReport` |
| `scripts/recommendations.py` | `course_explorer.recommendations.commands.run_recommendations_command` | `RecommendationsReport` |
| `scripts/study_structure.py` | `course_explorer.study_structure.commands.run_study_structure_command` | `StudyStructureReport` |
| `scripts/admin.py` | `course_explorer_admin.cli.main` | The owner's DTO per administrative command |
| `scripts/mock_data.py` | `course_explorer.mock_data.run_mock_data_command` | `NormalizationReport`, `CourseEmbeddingCoverageReport`, or `None` |
| `scripts/run_web.sh` | No callable, it execs `python -m course_explorer_web.launch` | No report |

No adapter holds a rule of its own, matching [Adapters hold no business logic](/docs/architecture/invariants.md#adapters-hold-no-business-logic).

## Argument contracts

| Script | Arguments |
|---|---|
| `search.py` | `query` positional, `--display-language` required with choices from `get_args(DisplayLanguage)`, `--semantic-min-score` float, `--fuzzy-min-score` float, `--active-only` store true |
| `course_lookup.py` | `query` positional, `--display-language` required with choices from `get_args(DisplayLanguage)`, `--active-only` store true |
| `module_lookup.py` | `query` positional, `--display-language` required, no other option |
| `compare_courses.py` | `course_a` and `course_b` positionals, no option |
| `prerequisites.py` | `course_code` positional, `--completed`, `--selected`, `--excluded`, `--completed-node`, and `--excluded-node` append, `--include-recommended`, `--include-inferred`, `--active-only`, `--basis` with the choices `completed` and `selected`, `--route` store true |
| `next_courses.py` | `--selected` and `--completed` append, `--basis`, `--mode` with the choices `all` and `at_least_one`, `--display-language` required, `--include-inferred`, and the mutually exclusive `--active-only` and `--all-courses` |
| `recommendations.py` | The same set as `next_courses.py` |
| `study_structure.py` | `root_group_id` positional, no option |
| `admin.py` | No parser, the dispatcher owns it |
| `mock_data.py` | `action` positional with the choices `load-curriculum`, `load`, and `write-artifacts`, `--fixture-dir` defaulting to `data/mock`, `--raw-root` defaulting to `data/mock-import`, `--hubs-dir` defaulting to `config/derived` |

`search.py` and `course_lookup.py` map `--active-only` to `include_inactive=not args.active_only`. `next_courses.py` and `recommendations.py` call `parser.set_defaults(active_only=True)`, so an invocation without either activity flag reads active courses only. `prerequisites.py` builds one `options` dict and passes it to whichever of the two prerequisite commands the invocation selects.

The comparison and structure adapters take their identities as positionals and declare no option, so the two report shapes are the only difference between them at this layer.

## Delegation and output

Every feature adapter and the example-data adapter define `main(argv: Sequence[str] | None = None) -> int`, parse with `argparse`, and call their command once. A returned report is printed with `report.model_dump_json()`, and a successful call returns 0. Each closes with the `if __name__ == "__main__":` guard and `raise SystemExit(main())`, so the process exit status is the function's return value.

`scripts/admin.py` is the administrative adapter. It imports `main` from `course_explorer_admin.cli` and raises `SystemExit(main())` from that imported function, so the parser, the JSON emission, and the exit status belong to the dispatcher rather than to the script.

A feature adapter lets every exception propagate, so a command failure reaches the caller as an uncaught exception and no partial report is printed. `argparse` exits with a usage message before any command call when an argument is missing or unknown.

`mock_data.py` prints only when the callable returns a report, so the `write-artifacts` action prints nothing and returns 0.

## The administrative dispatcher

`course_explorer_admin/cli.py` owns the one administrative parser, the JSON emission, and the safe failure presentation.

- `_parser()` builds `ArgumentParser(prog="admin.py")` with the subcommands `menu`, `setup` (`datasets` or `worker`, plus `--branch` defaulting to `main` and a `--code-only` flag), `preflight`, `migrate` (`datasets`), `dispose` (`inference`, one target, one disposition out of `nothing`, `done`, and `failed`), one subcommand per stage name with an action out of `_ACTIONS`, `coverage`, `hubs`, and `summary`.
- `main(argv=None, *, run_command=None, run_summary=None)` parses one command and delegates once. An absent command, or `menu`, runs `run_operator_menu`. A supplied `run_command` or `run_summary` replaces that one call and nothing else, so a wrapper can inject an extra route without a second parser.
- `_emit(report)` prints `report.model_dump_json()` to standard output and the fixed `worker_origin_notice(report)` text to standard error.
- `main` returns 0 on success, 1 on failure, and 130 on `KeyboardInterrupt`. `preflight` returns 1 when the report carries no resources or reports them as not ready.
- `_fail(exc, operation)` prints `format_operator_error(exc)`, which holds only the exception class name and the `returncode` of a checked subprocess failure, followed by `operator_guidance(operation, configuration_error=isinstance(exc, ValidationError))`.
- `coverage` and `summary` print `REPORT_SCOPE` to standard error as well.

`dispose ... nothing` maps the token to `None` before the call, so the stored decision records an automatic target rather than a terminal one.

## The launcher script

`scripts/run_web.sh` is the shell adapter for the web server. It enables `set -euo pipefail` and execs `./.venv/bin/python -m course_explorer_web.launch`, so the launcher takes the place of the shell process. The launcher module composes the five settings families and hands the serving process a file-free environment, as described in [Web server](/docs/backend/interfaces/web-server.md#the-launcher-and-the-environment-handoff).

## The example-data adapter

`course_explorer.mock_data.run_mock_data_command(action, *, fixture_dir, raw_root, hubs_dir)` in `src/course_explorer/mock_data.py` is a data-writing adapter rather than a feature read.

- `load-curriculum` registers the invented fixture as one completed capture and applies the normalization batch, returning a `NormalizationReport`.
- `load` does the same and then reconciles the bundled vectors through the embedding repository, returning a `CourseEmbeddingCoverageReport`.
- `write-artifacts` computes both hub means and writes the fixture bundle and both hub files, returning `None`.

The command refuses a selected-dataset-enabled configuration before it opens an engine, and it requires the database at the single migration head. It writes the configured database rather than reading it, and the read-only web surface does not reach it.

## Adding an adapter and its tests

To add an adapter:

1. Put the behavior in one command function in the owning package, with caller-input validation before any settings load or I/O.
2. Add `scripts/<name>.py` with `main(argv=None) -> int`, an `ArgumentParser`, one call to that function, `print(report.model_dump_json())`, `return 0`, and the `__main__` guard.
3. Add a test that loads the script as a standalone module and asserts the delegation and the printed report.

The adapter tests load a script by path with `importlib.util.spec_from_file_location(name, Path(__file__).parents[2] / "scripts" / f"{name}.py")`, monkeypatch the command symbol on the loaded module to record its arguments and return a prepared report, and then assert that `main(...)` returns 0, that exactly one call carried the expected keyword arguments, and that standard output is `report.model_dump_json()` plus a newline.

| Test file | Covers |
|---|---|
| `tests/search/test_search_command.py` | The search adapter forwarding every option and printing one unified report, and the missing-language usage failure. |
| `tests/search/test_lookup_commands.py` | The course and module lookup adapters, the forwarded `include_inactive` mapping, and the module adapter rejecting an option it does not declare. |
| `tests/comparison/test_comparison_command.py` | The comparison adapter delegating both identities once and the missing-argument usage failure. |
| `tests/prerequisite/test_prerequisite_command.py` | The prerequisite adapter forwarding every option to the graph command, `--route` dispatching the same options to the route command alone, and each operation running only its own read. |
| `tests/next_courses/test_next_courses_command.py` | The discovery adapter with the mode and activity defaults, both activity flags, and the missing-language usage failure. |
| `tests/recommendations/test_recommendations_command.py` | The recommendation adapter forwarding all toggles once and emitting the recommendation report. |
| `tests/study_structure/test_study_structure_command.py` | The structure adapter delegating one identity and rejecting an undeclared option. |
| `tests/admin/test_operator_commands.py` | The dispatcher's delegate-once contract, the `hubs` machine command, the disposition tokens, the safe failure token with no payload, and the help and syntax failures that delegate nothing. |
