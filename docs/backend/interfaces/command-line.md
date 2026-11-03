# Command line

The feature read scripts delegate to package commands and print one JSON report each, and the administration command, the example data loader and the launchers sit beside them.

## The scripts

The feature read scripts answer one read each and print one JSON report line.

| Script | Purpose |
|---|---|
| `scripts/search.py` | One unified search over one query, with every search method the opened artifact build serves merged into one entry per course. |
| `scripts/catalogue.py` | The minimal official catalogue the browser narrowing boxes filter locally. |
| `scripts/compare_courses.py` | The five meters and the verdict for two course identities. |
| `scripts/prerequisites.py` | The prerequisite graph of one course, or its minimum-new-credit route with `--route`. |
| `scripts/next_courses.py` | The courses the chosen basis covers, under the chosen mode. |
| `scripts/recommendations.py` | The courses similar to the chosen basis, ranked. |
| `scripts/study_structure.py` | The official structure of one degree programme or module. |

Six further entry points run the administration command, the example data loader, the web server launcher, the administration backend launcher, the feedback sender and the native library build. The administration command and the example data loader are described in [Administration commands](/docs/backend/interfaces/administration-commands.md), the launchers and the native build in [Command adapters](/docs/backend/interfaces/command-adapters.md), and the sender in [Feedback publication](/docs/backend/feedback-publication.md).

A feature script parses its arguments and calls one command function, so a rule lives in a package command and never in the script.

The search, comparison and recommendation scripts open the artifact set, which follows the site's embedding switch. `scripts/search.py` runs the semantic method when the opened set holds embedding reads and the three lexical methods alone when it holds none. `scripts/compare_courses.py` and `scripts/recommendations.py` read the opened set's embedding data and fail when it holds none, because both features need the embedding artifacts. [Search](/docs/backend/search-and-discovery/search.md#a-site-without-semantic-matching) and [Recommendation ranking](/docs/backend/search-and-discovery/recommendation-ranking.md#recommendation-composition) state each behavior.

## How a command behaves

A feature read script runs in the process that calls it, prints exactly one JSON report line on standard output, and returns exit status 0. A rejected input raises from the command and the script does not catch it, so a failed call prints no report and the caller sees the failure.

Each read command opens its own database context and reads the [selected dataset](/docs/reference/glossary.md#administration). The report of a command is self-contained and holds the result of its read.

- The search report repeats the effective semantic and fuzzy thresholds, the activity scope, and the tier order it used.
- The catalogue report carries every represented course's canonical identity, code, FI and EN names, credits and activity flag, and every canonical module's eligible version candidates with their exact version identity, kind, code, FI and EN names, validity bounds and period memberships.
- The next-course report carries the two canonical input sets, the chosen basis, the mode, the language and activity flags, and the ordered results.
- The recommendation report carries the similar courses alone.
- The comparison report carries both summaries, the meters, and the verdict.
- The graph report carries the solver structure, the drawing when the configured allowance permits it, and the drawing counts. It carries no computed box states, because the browser evaluates those from the structure it holds.
- The route report carries the outcome, the new credits, the new courses, and the located problems.
- The structure report carries the root, its rules, and its nodes. The web batch report carries every requested root, the roots it could not project, and the roots whose canonical group needs an explicit version selection.

[Search](/docs/backend/search-and-discovery/search.md), [Comparison](/docs/backend/search-and-discovery/comparison.md), [Next courses](/docs/backend/search-and-discovery/next-courses.md), [Recommendations](/docs/backend/search-and-discovery/recommendations.md), and [Structure of studies in the catalogue](/docs/backend/catalogue/study-structure.md) describe the reads and their reports.

## Identities and language

The commands that take a course identity accept either a canonical identity or an exact official code, and a canonical identity takes precedence. A blank input, an unknown input, and an official code held by more than one course each fail instead of resolving to a guess. The structure command takes one canonical module identity from the catalogue report and an exact version identity for each ambiguous canonical group, the search command accepts a text query, and the catalogue command takes no input.

Three commands render official names and therefore take the app language: search, next courses, and recommendations. The other commands select no app language. [Command adapters](/docs/backend/interfaces/command-adapters.md#argument-contracts) states each option name, its value and its default.

## Scope, basis, and toggles

The discovery commands start with inactive courses left out, while the search and prerequisites commands start with inactive courses included. The catalogue command carries every course's activity flag, so the browser applies the activity scope to its local filter. The comparison and structure commands take no activity option.

The basis option chooses which set counts as covered and defaults to the completed set. On the prerequisites, next-course, and recommendation commands, the completed and selected inputs are repeatable and accept canonical identities or exact official codes. The next-course and recommendation commands use the completed set as the selected set when no selected code is supplied, and a supplied selected set must contain every completed course.

Prerequisites accepts excluded courses and the two category toggles. Each excluded course appears in the drawing while the calculation routes around it, and excluding the opened root blocks the whole request. The recommended and inferred toggles each add their category to the drawing and to the calculation, and the two are independent.

Prerequisites also marks drawn boxes through completed-node and excluded-node keys. Each value is one current graph-box key in the form `s:<owner>:d:<24 hex>`, whose last part is 24 lowercase hexadecimal digits, and the graph report's drawing carries the key of each module and numeric requirement box as that box's node identity. A value of another shape fails the command before it opens the database, with `completed node key '<key>' is not a current graph-box key (s:<owner>:d:<24 hex>)`, or the same message naming `excluded`.

A key marks one drawn module or numeric requirement box as met or excluded in the calculation, and the mark applies to every requirement that box stands for. It changes neither the completed set nor the selected set. Exclusion wins when both options name the same box, and a key that names any other box marks nothing. The graph report and the route result take the two options alike.

The mode option chooses whether a next course needs every prerequisite or any one of them, and it defaults to requiring every one. The category toggles are off by default.

## The graph and the route

`scripts/prerequisites.py` prints the prerequisite graph report unless `--route` is given, and `--route` prints the minimum-new-credit result instead. The graph report describes the drawing and the calculation structure without any node state, and the route result is separate. The route command runs the shared TypeScript solver through Node, so its bundle is prepared once with `npm --prefix web run solver:build`. A missing bundle fails the command with the build instruction, and one invocation prints exactly one of the two results. The graph report carries no route result, and the route result carries no drawing graph.

Both operations compile one solver structure for the root, so the drawing and the calculation cannot describe different requirement sets. A script caller passes no drawing limit, so the graph report always carries a drawing. The web graph route applies the configured limit instead. [Prerequisite graph](/docs/backend/prerequisites/prerequisite-graph.md) and [Minimum route](/docs/backend/prerequisites/minimum-route.md) describe the two operations.

## Usage

```bash
uv run python scripts/search.py "data structures" --display-language en --active-only
uv run python scripts/admin.py coverage embedding --role selected
uv run python scripts/mock_data.py load
```

The comparison command takes two course identities as positional arguments, and the structure command takes one canonical module identity as a positional argument, which the catalogue report supplies.
