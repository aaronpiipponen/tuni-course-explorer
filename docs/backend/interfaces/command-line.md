# Command line

Feature read scripts delegate to package commands and print their JSON reports, while the administrative command and the launcher provide separate entry points.

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

Three further entry points under `scripts/` provide administration, example data preparation, and web serving.

| Entry point | Purpose |
|---|---|
| `scripts/admin.py` | The operator menu and the administrative machine commands. Its reports are the stage, dataset, worker, coverage, summary, and hub reports of the administrative dispatcher. |
| `scripts/mock_data.py` | The example dataset loader and artifact writer. The two import actions print one report each, and the artifact action prints nothing. |
| `scripts/run_web.sh` | The launcher. It starts the web server process and prints no report. |

A feature script parses its arguments and calls one command function, and the administrative script delegates to the administrative dispatcher, so a rule lives in a package command and never in the script.

## How a command behaves

A feature read script runs in the process that calls it, prints exactly one JSON report line on standard output, and returns exit status 0. A rejected input raises from the command and the script does not catch it, so a failed call prints no report and the caller sees the failure.

Each read command opens its own database context and reads the [selected dataset](/docs/reference/glossary.md#administration). The report of a command is self-contained. The search report repeats the effective semantic and fuzzy thresholds, the activity scope, and the tier order it used. The lookup reports repeat the query and the language. The course lookup report carries the activity scope, and the module lookup report carries the academic year. The next-course report carries the two canonical input sets, the chosen basis, the mode, the language and activity flags, and the ordered results. The recommendation report carries the similar courses alone. The comparison report carries both summaries, the meters, and the verdict. The graph report carries the compiled expression, the drawing with its node states, and the drawing counts. The route report carries the outcome, the new credits, the new courses, and the located problems. The structure report carries the root, its rules, and its nodes.

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

## The administrative command

`scripts/admin.py` delegates to the administrative dispatcher, which owns one parser and one JSON emitter. Without a subcommand, and with `menu`, it starts the numbered operator menu, which continues until Exit, an end of input, or an interrupt. [Operator menu](/docs/operations/operator-menu.md) describes the menu and the operations it drives.

The machine commands are `setup datasets`, `setup worker`, `preflight`, `migrate datasets`, `dispose inference`, the four stages with the actions `start`, `pause`, `resume`, `status`, and `stop`, `coverage`, `summary`, and `hubs`.

The administrative command differs from the read scripts in three ways.

- It reports the state of the selected dataset and of the stages, and some of its commands write to the dataset or to the worker.
- A failure prints one content-free JSON line holding the exception's class name, plus fixed guidance, to standard error, and returns exit status 1. A checked subprocess failure adds its return code. An interrupt returns 130, and a not-ready `preflight` prints its report and returns 1.
- `coverage` and `summary` also print a fixed note to standard error, stating that the reports read the selected dataset and not unreturned worker progress.

`hubs` computes both embedding hub means from the current chunk vectors of the selected dataset and writes the two files that the hub keys reference. Both means are computed before either file is written. A running web server reads both hub files when its process starts, so restart the serving process after writing them. The embedding tool in the operator menu offers the same write. [Embeddings](/docs/backend/text-and-vectors/embeddings.md#the-hubs) describes the hub files.

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
