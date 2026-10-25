# TUNI Course Explorer

TUNI Course Explorer explores Tampere University curriculum data through a React browser app and a read-only FastAPI backend, with an offline Python pipeline over PostgreSQL and pgvector.

The browser application searches courses by code, name and meaning, compares courses, draws official prerequisite structures and separately marked inferred ones, computes a minimum-new-credit route, lists what can be studied next, and keeps one browser-local study plan across every tab.

The app is available at [course-explorer.duckdns.org](https://course-explorer.duckdns.org/). Its [wiki](https://course-explorer.duckdns.org/docs) holds the guides to each tab and the documentation of how the system behaves. Installation, self-hosting and the code-level documentation are read in [`docs/`](/docs/) in this repository.

The example setup in this repository runs on an invented dataset, not on university data.

![The five tabs of the application above a list of course search results](/docs/screenshots/app-shell.png)

## Features

The application has five tabs that share one browser-local study plan. A site sets in `config/web.toml` whether it serves the embedding features (the **Compare** tab, the **Recommended** list and semantic search) and the inference features (the **Inferred** toggle and inferred prerequisites), and the app leaves out what the site does not serve.

### Search

Search matches a query against course codes, course names and the teaching text. Exact code, substring and fuzzy name matching run for every query, semantic matching runs as well on a site that serves the embedding features, and the results are merged into one entry per course that lists each way the course matched.

![Search tab with one course that matched by substring, fuzzy and semantic search, each shown as a match source](/docs/screenshots/search-results.png)

### Compare

Compare places two courses side by side and measures how much their teaching text overlaps. Five meters show overall relatedness, content similarity, learning-outcome similarity, and, in each direction, how much of one course has a match in the other. One verdict summarizes them.

![Compare tab with two courses, the verdict Loosely related and five percentage meters](/docs/screenshots/compare-meters.png)

### Prerequisites

The graph shows the layered prerequisite structure of a course as AND and OR groups, with the completed or selected courses as the basis. The **Recommended** toggle adds recommended prerequisites, drawn apart from the required ones. The **Inferred** toggle adds prerequisites found by analysis to the same graph and marks them inferred. **Find minimum route** computes the set of courses that needs the fewest new credits and highlights it on the graph.

![Prerequisites tab with the graph of one course, its AND and OR groups and the basis and toggle controls](/docs/screenshots/prerequisite-graph.png)

![The same graph with the minimum route highlighted, its new credits and the exact result shown](/docs/screenshots/minimum-route.png)

### Discover

Discover has two lists. **Next courses** shows the courses that can be studied next from a basis of completed or selected courses, in an **All** mode or a **Partially covered** mode, with a coverage meter for each category that holds course prerequisites. **All** lists fully covered courses without a coverage meter. **Recommended** lists courses similar to the basis.

![Discover tab in the Partially covered mode, with a basis of three completed courses and two next-course rows that each carry a Required meter](/docs/screenshots/discover-next-courses.png)

### Structure of studies

This tab shows an ordered list of programmes, each with the official structure of a degree programme or module and credit totals per node. **Add programme** ends the list, every programme row carries a menu that replaces, resets or deletes it, courses can be marked complete, and courses no programme holds appear under **Unplaced studies**. The structure can be edited in the browser to match a personal plan.

![Structure of studies tab with one programme and one module row, their courses including completed ones, the Add programme row and the Unplaced studies row](/docs/screenshots/structure-of-studies.png)

### Profiles and language

The profile menu in the top bar is named after the active profile (**My plan** by default). It lists the saved profiles and creates new ones. A profile stores the selected and completed courses, exclusions and graph marks, the ordered programmes with their edits, and the tab options. The open tab belongs to the browser tab instead, so switching a profile never moves it. The FI/EN switch sets the interface wording and the language of official course and module names.

The same menu exports one profile or all saved data as a file and imports those files for transfer between browsers or backup. [Profiles and language](/docs/guides/profiles-and-language.md#exporting-a-profile-or-the-saved-data) describes the file controls and their confirmations.

![The profile menu lists My plan and Alternative plan with their selected and completed counts, next to the FI and EN language switch with EN pressed](/docs/screenshots/profile-menu.png)

### Sisu plan import

A script copied from the profile menu reads an open plan in Sisu's **Structure of studies** view and downloads one capture file. Importing that file creates one browser-local profile with the plan's programmes, choices and completions, and the exact module versions Sisu showed.

The script runs in the Sisu browser tab. It reads the open page and asks the public Kori interface for the modules and courses the plan shows, without sending the Sisu login cookies. [Sisu import script](/docs/guides/sisu-import.md) gives the capture and import steps.

![The Import Sisu plan dialog with a typed profile name and the captured programme listed above Cancel and Import](/docs/screenshots/sisu-import-dialog.png)

## Admission control

The web server uses a browser cookie to apply admission control to nine fixed API POST paths. With `ADMISSION_ENABLED` true in `config/admission.toml`, reads are classified as free, light or heavy. Light reads have rate and concurrency limits. Heavy reads use a budget of estimated processing cost and wait in a queue for a shared slot.

The limits adjust to server load, using the host's CPU use and the admitted request activity. An admitted heavy read has a fixed estimated charge, and a refused read returns HTTP 429 with a retry delay. [Admission control](/docs/backend/interfaces/admission-control.md) describes the classes, budgets, queues and settings.

## Data and limits

- Official facts come from Tampere University's public Kori curriculum data. Machine translations and inferred prerequisites are derived information, marked as such in the interface.
- Prerequisite inference runs separately from the website, on a model hosted by whoever operates the project. The website only shows the results.
- One browser `localStorage` store holds the profiles. Profiles stay in the browser that created them.
- Selection and completion use one canonical course identity in every tab.
- The application is read-only. It does not change the data and does not start ingestion, translation, embedding or inference.
- The interface does not establish enrolment eligibility, and its analysis is not verified by the university.

## Administration console

The administration console is a separate signed-in browser application with its own backend, running the fixed administration commands. Its five tabs are **Dashboard**, **Data preparation**, **Inference**, **Logs** and **Settings**.

The console reports the website, host, database and model runtime, controls the preparation stages, records inference decisions, reads logs and usage, and manages configuration, datasets and backups. The course application is a read-only API client. Preparation and maintenance run through the console or the administration command.

![The administration console on the Dashboard tab, with the five tabs above the serving state, website, host, database and embedding runtime panels](/docs/screenshots/admin-console-dashboard.png)

[Administration console](/docs/operations/admin-console/README.md) covers signing in, the tabs and their panels.

## Run your own copy

Requirements:

- Python 3.14.3
- [uv](https://docs.astral.sh/uv/)
- Node.js `^20.19.0 || >=22.12.0` with npm
- Docker with Docker Compose, for PostgreSQL with pgvector

Runtime configuration and deployment files are provided as examples under `examples/`. The files a running copy uses are local to each checkout and are ignored by Git.

1. Install the Python and browser dependencies.

   ```bash
   uv sync --locked
   npm --prefix web ci --no-audit --no-fund
   npm --prefix admin-web ci --no-audit --no-fund
   ```

2. Create the working folders, then copy the example files to their working paths:

   ```bash
   mkdir -p config/derived deploy
   ```

   - the nine `examples/config/*.toml` files into `config/`
   - `examples/config/wiki.json` into `config/wiki.json`
   - the two `examples/config/derived/*.json` files into `config/derived/`
   - `examples/.env.example` into `.env`
   - `examples/docker-compose.yml` into the repository root
   - `examples/deploy/Caddyfile` and `examples/deploy/systemd/tuni-course-explorer-web.service.in` into `deploy/`

3. Build the browser application, the machine solver bundle and the administration console. The browser application's build reads `config/wiki.json`, so it runs after the copy. `solver:build` writes `web/.solver-cli/cli.js`, the bundle that the machine minimum-route command runs through Node.

   ```bash
   npm --prefix web run build
   npm --prefix web run solver:build
   npm --prefix admin-web run build
   ```

4. Edit `.env`: set a database password and keep the file readable only by you (mode 0600).

5. Place the embedding model file named by `EMBEDDING_ARTIFACT_URL`, `EMBEDDING_ARTIFACT_PATH` and `EMBEDDING_ARTIFACT_SHA256` at the configured path. The project does not download it. The embedding image is built from `docker/embedding/Dockerfile`.

6. Build and start the database and the embedding service.

   ```bash
   uv run python -m course_explorer_admin.compose -- build
   uv run python -m course_explorer_admin.compose -- up -d --wait db embedding
   ```

7. Create the schema and load the example dataset.

   ```bash
   uv run python -m alembic upgrade head
   uv run python scripts/mock_data.py load
   ```

8. Start the site.

   ```bash
   bash scripts/run_web.sh
   ```

The example dataset in `data/mock/` is invented. Its courses, modules, prerequisites and structure rules are not university data, and its embedding vectors are bundled with it, so nothing needs to be generated.

The lint, Python, database, browser application and console checks for a local checkout are in [Local checks](/docs/testing/local-checks.md).

## Architecture

- [`src/course_explorer/`](/src/course_explorer/): domain, ingestion, search, inference and persistence services.
- [`src/course_explorer_admin/`](/src/course_explorer_admin/): the administration command, with the operator menu, the four preparation stages and their lifecycle.
- [`src/course_explorer_web/`](/src/course_explorer_web/): the read-only FastAPI application that serves the browser application and its endpoints.
- [`src/course_explorer_admin_web/`](/src/course_explorer_admin_web/): the separate signed-in administration backend that runs the fixed administration commands for the console.
- [`scripts/`](/scripts/): the administration command, the example data loader, thin command-line adapters over the read commands, and the launchers of the web server and the administration backend.
- [`web/`](/web/): the React, TypeScript and Vite browser application.
- [`admin-web/`](/admin-web/): the React, TypeScript and Vite administration console.

Python services own behavior, PostgreSQL with pgvector stores normalized state and vectors, and Alembic owns schema changes. The browser application is a read-only client of the API. The offline pipeline that prepares the data runs outside the request path.

## License

This project is licensed under the MIT License. See [`LICENSE`](/LICENSE).

## Independent project

This is an independent project. It is not affiliated with, endorsed by, or connected to Tampere University. Tampere University curriculum data and other university material are not covered by this project's software license and remain subject to their own terms. The example dataset in `data/mock/` is invented for this project and is not university data.
