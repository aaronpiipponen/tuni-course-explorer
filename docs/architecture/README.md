# Architecture

TUNI Course Explorer serves the app from a read-only request path and prepares its course data along a separate preparation path.

## The request path and the preparation path

A read starts in the browser app and ends in the web server. The web server serves the two shell documents and the compiled assets of the browser app, and it answers 10 dataset command reads plus one [feature read](/docs/backend/interfaces/web-api.md) over the prepared data. Nothing on this path writes authoritative catalogue or user data, starts a stage, or reaches the worker. One ASGI middleware appends one request record per request to the site's own usage file, as [System boundaries](/docs/architecture/boundaries.md) states, and that record is neither catalogue nor user data. The reads enforce the site's two feature switches, which decide whether semantic matching, the Compare feature, the Recommended list and the inferred data are served, and the feature read reports that pair to the browser.

The preparation path starts at the administration command. Its four stages fill the data that the reads consume. Ingestion captures the public curriculum source, validates the capture, and writes official courses, modules, versions, and rules. Embedding writes the teaching-text chunks and their vectors. Translation writes translated teaching text beside the official text. Inference writes inferred prerequisites and equivalence groups. Ingestion and embedding run on the machine that runs the administration command, and translation and inference run on the worker.

The two paths meet at two shared artifacts. The PostgreSQL database with pgvector holds the selected dataset: the stages write it, and the web server reads it. The usage file under `data/usage/requests` is the second: each serving process appends one request record per request, and the administration command's usage report reads and prunes it. [System context](/docs/architecture/system-context.md) describes the parts of the system, what each part does, and the settings that decide which database a process reads.

## The three surfaces

The course-exploration app reads through its web server. An operator works through two further surfaces: the numbered operator menu or one machine command of `scripts/admin.py`, and a separate administration surface with an [Administration console](/docs/operations/admin-console/README.md) and an [Administration backend](/docs/backend/interfaces/admin-backend.md), its own frontend, its own configuration and its own process.

Both operator surfaces reach the same owners. The menu and the machine command delegate once to the administration dispatcher over the stage and dataset services, and the Administration console runs those same fixed commands and returns their reports. It therefore owns no second service path and no second controller.

The Administration backend authenticates its operator in `src/course_explorer_admin_web/`. One process binds the configured loopback address, admits each request through one admission middleware, serves the three authentication routes, the built console shell and its built assets, holds its sessions in memory and its failed-attempt count, lock and command log on disk, and runs the fixed administration commands over the owners the menu uses. Its console is a separate React application built from `admin-web/`, and its five tabs are Dashboard, Data preparation, Inference, Logs and Settings over the fixed feature routes. The static shell and asset reads are the one anonymous exception, checked after the lock and the exact site and before any cookie is read. The backend creates a fresh anonymous session within the [server-wide creation limit](/docs/operations/admin-console/access-and-records.md#the-anonymous-session-creation-limit), and a spent limit answers `429`. [Console access and records](/docs/operations/admin-console/access-and-records.md) states the admission order, the sessions, the lock and both records.

The enforced assertions in this area cover the course-exploration web package and the Administration backend. [System boundaries](/docs/architecture/boundaries.md) states that separation, [Administration backend](/docs/backend/interfaces/admin-backend.md) describes the package, [Administration console code](/docs/frontend/admin-console.md) describes the separate build, and [Operations](/docs/operations/README.md) describes the operator's access to both surfaces.

## One behavior behind every surface

A read in the browser and the equivalent machine command reach the same command function. Search is one function that both the search route and the search script call, and the prerequisite graph read and the minimum route read are two operations over one prepared calculation that the prerequisite route and the prerequisite script both call. A web route validates its inputs and returns the report of the command. A machine adapter parses its arguments and delegates once. One implementation therefore answers the browser app and the machine commands alike, and neither surface restates the behavior of the other.

## Course state in the browser

The selected and completed courses, the exclusions, and the app language belong to a profile in the browser state, which the browser holds in local storage. A profile holds the settings of each tab as well, so switching the profile rebuilds every tab from the state of the chosen profile. The open tab belongs to the browser tab that shows it.

The web server stores no profile and returns none. The selected and completed courses reach it only as request inputs, and a read that needs courses accepts the canonical course identities and the toggles the browser sends. A course carries one canonical identity, so a selection made in one tab counts the same in every other tab and in every request.

## Official data and inferred data

Official data is what the ingestion stage writes from the public curriculum source. Inferred prerequisites and equivalence groups are stored in their own tables with their own coverage state, and the inference stage writes inferred output without modifying an official row. The inferred store refuses an expression whose nodes do not all carry inferred origin, so a derived claim cannot appear as an official statement.

A translation is stored beside the text it was made from and does not replace it. Official text takes precedence, and a translation whose recorded source text differs from the official text is stale, reported, and left out of the effective text.

The inference stage runs language models on the worker, and the web server holds no model credential and no worker connection value.

## Where the separations are enforced

The separations on this page are structural, and each one is enforced in code. [System boundaries](/docs/architecture/boundaries.md) describes the read-only web surface, the browser-held state, the split between official and inferred data, inference on local models on the worker, configuration ownership, the single schema and format, and the administration boundary. [Invariants and their enforcement](/docs/architecture/invariants.md) names the module that owns each rule and the tests that cover it.
