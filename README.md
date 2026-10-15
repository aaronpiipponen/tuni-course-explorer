# TUNI Course Explorer

TUNI Course Explorer is a course-search and study-path service for Tampere University curriculum data. It combines an offline Python pipeline over PostgreSQL and pgvector with a read-only FastAPI backend and a React browser application.

The browser application searches courses by code, name and meaning, compares courses, draws official prerequisite structures and separately marked inferred ones, computes a minimum-new-credit route, lists what can be studied next, and keeps one browser-local study plan across every tab. The example setup in this repository runs on an invented dataset, not on university data.

![The five tabs of the application above a list of course search results](/docs/screenshots/app-shell.png)

## Features

The application has five tabs that share one browser-local study plan.

### Search

Search matches a query against course codes, course names and the teaching text. Exact code, substring, fuzzy name and semantic matching all run for every query, and the results are merged into one entry per course that lists each way the course matched.

![Search tab with one course that matched by substring, fuzzy and semantic search, each shown as a match source](/docs/screenshots/search-results.png)

### Compare

Compare places two courses side by side and measures how much their teaching text overlaps. Five meters show overall relatedness, content similarity, learning-outcome similarity, and, in each direction, how much of one course has a match in the other. One verdict summarizes them.

![Compare tab with two courses, the verdict Loosely related and five percentage meters](/docs/screenshots/compare-meters.png)

### Prerequisites

The graph shows the layered prerequisite structure of a course as AND and OR groups, with the completed or selected courses as the basis. The **Recommended** toggle adds recommended prerequisites, drawn apart from the required ones. The **Inferred** toggle adds prerequisites found by analysis, tagged as inferred so they stay separate from the official ones. **Find minimum route** computes the set of courses that needs the fewest new credits and highlights it on the graph.

![Prerequisites tab with the graph of one course, its AND and OR groups and the basis and toggle controls](/docs/screenshots/prerequisite-graph.png)

![The same graph with the minimum route highlighted, its new credits and the exact result shown](/docs/screenshots/minimum-route.png)

### Discover

Discover has two lists. **Next courses** shows the courses that can be studied next from a basis of completed or selected courses, in an **All** mode or an **At least one** mode, with how much of the required and recommended prerequisites each course covers. **Recommended** lists courses similar to the basis.

![Discover tab with a basis of two completed courses and one next course with its required and recommended coverage](/docs/screenshots/discover-next-courses.png)

### Structure of studies

This tab shows the official structure of a programme or module with credit totals per node. Courses can be marked complete, courses outside the structure appear under unplaced studies, and the structure can be edited in the browser to match a personal plan.

![Structure of studies tab with a programme, its module, completed courses and an unplaced completed course](/docs/screenshots/structure-of-studies.png)

### Profiles and language

The profile menu in the top bar is named after the active profile (**My plan** by default). It lists the saved profiles and creates new ones. A profile stores the selected and completed courses, exclusions and graph marks, structure edits and tab options. The FI/EN switch sets the interface wording and the language of official course and module names.

![Profile menu listing the default profile with its selected and completed counts, next to the FI and EN language switch](/docs/screenshots/profile-language.png)

## Data and limits

- Official facts come from Tampere University's public Kori curriculum data. Machine translations and inferred prerequisites are derived information, marked as such in the interface.
- Prerequisite inference runs separately from the website, on a model hosted by whoever operates the project. The website only shows the results.
- One browser `localStorage` store holds the profiles. Profiles stay in the browser that created them.
- Selection and completion use one canonical course identity in every tab.
- The application is read-only. It does not change the data and does not start ingestion, translation, embedding or inference.
- The interface does not establish enrolment eligibility, and its analysis is not verified by the university.

## Run your own copy

Requirements:

- Python 3.14.3
- [uv](https://docs.astral.sh/uv/)
- Node.js 20.19 or later with npm
- Docker with Docker Compose, for PostgreSQL with pgvector

Runtime configuration and deployment files are provided as examples under `examples/`. The files a running copy uses are local to each checkout and are ignored by Git.

1. Install the Python and browser dependencies.

   ```bash
   uv sync --locked
   npm --prefix web ci --no-audit --no-fund
   ```

2. Create the working folders, then copy the example files to their working paths:

   ```bash
   mkdir -p config/derived deploy
   ```

   - the seven `examples/config/*.toml` files into `config/`
   - `examples/config/wiki.json` into `config/wiki.json`
   - the two `examples/config/derived/*.json` files into `config/derived/`
   - `examples/.env.example` into `.env`
   - `examples/docker-compose.yml` into the repository root
   - `examples/deploy/Caddyfile` and `examples/deploy/systemd/tuni-course-explorer-web.service.in` into `deploy/`

3. Build the browser application. The build reads `config/wiki.json`, so it runs after the copy.

   ```bash
   npm --prefix web run build
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

Checks for the browser application:

```bash
npm --prefix web run typecheck
npm --prefix web run test
npm --prefix web run format:check
```

## Architecture

- [`src/course_explorer/`](src/course_explorer/): domain, ingestion, search, inference and persistence services.
- [`src/course_explorer_web/`](src/course_explorer_web/): the read-only FastAPI application that serves the browser application and its endpoints.
- [`web/`](web/): the React, TypeScript and Vite browser application.

Python services own behavior, PostgreSQL with pgvector stores normalized state and vectors, and Alembic owns schema changes. The browser application is a read-only client of the API. The offline pipeline that prepares the data runs outside the request path.

## License

This project is licensed under the MIT License. See [`LICENSE`](LICENSE).

## Independent project

This is an independent project. It is not affiliated with, endorsed by, or connected to Tampere University. Tampere University curriculum data and other university material are not covered by this project's software license and remain subject to their own terms. The example dataset in `data/mock/` is invented for this project and is not university data.
