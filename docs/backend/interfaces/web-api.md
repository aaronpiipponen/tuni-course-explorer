# Web API

The web API answers ten fixed read commands, serves the browser application's shell documents, and embeds a query only for a semantic search.

## The fixed route set

The surface is fixed when the application is built: ten read commands under `/api/`, two shell documents for the browser application, and one mounted asset directory. No route writes data, starts a stage, or reaches the worker. [System boundaries](/docs/architecture/boundaries.md) describes that separation.

Every read command answers a POST request whose body is a closed JSON object. A read uses POST because one request carries a query, course identities, and toggles together, and a closed body states that shape exactly. Each request model refuses a field it does not declare.

## How a request is answered

One request is answered by one command. The route validates the body against its closed request model, calls one command once, and returns that command's own report as JSON. The command reads the [selected dataset](/docs/reference/glossary.md#administration) and returns one report, and nothing on the path is written.

![A request from the browser app is validated against a closed request model and reaches one fixed feature command. The command reads the selected dataset and, for a semantic search only, embeds the query text through the embedding service, shown with a dashed arrow. The command returns one JSON report to the browser app.](/docs/diagrams/web-request-flow.svg)

The unified search embeds the query text at request time through the service that produced the stored vectors, so a query vector and a stored vector come from one model. That call is the only embedding on the request path.

Every other piece of data a request reads was written before the request. Ingestion writes the official courses, modules, and rules, the embedding stage writes the teaching-text chunks and their vectors, and the inference stage writes the inferred prerequisites. A comparison and a recommendation read stored vectors, and neither embeds a query. A recommendation also runs the next-course calculation, so it reads prerequisites as well. [Embeddings](/docs/backend/text-and-vectors/embeddings.md) describes the stored vectors and the two hub files.

## What a request carries

A route that takes a course identity resolves it as a canonical identity first and an exact official code second. A blank input, an unknown input, and an official code held by more than one course each fail the request instead of resolving to a guess. The study-structure route takes one canonical module identity directly, and the search, course lookup, and module lookup routes take a text query instead.

`display_language` is the app language of the routes that render official names, and its value is `fi` or `en`. Five routes take it: search, course lookup, module lookup, next courses, and recommendations. The remaining routes report official text for both languages, so they take no language input.

The selected courses, the completed courses, the exclusions, the basis, the mode, and the category toggles are request inputs. The server stores no profile and returns none, so the [browser state](/docs/reference/glossary.md#browser-app) belongs to the browser that holds it.

## The routes

| Route | What it answers |
|---|---|
| `POST /api/search` | One unified search over one query. All four search methods run and their results merge to one entry per course. A request may carry its own semantic and fuzzy thresholds and set whether inactive courses take part. |
| `POST /api/course-lookup` | Every represented course whose displayed official name or official code contains the query, ignoring case, with no count cap. |
| `POST /api/module-lookup` | The modules of the current academic year whose displayed name or code contains the query. |
| `POST /api/comparison` | The five comparison meters and the verdict for two course identities. |
| `POST /api/prerequisites` | The prerequisite graph of one course with its node states. The configured drawing limit applies to the drawing. |
| `POST /api/minimum-route` | The minimum-new-credit route of one course, with its outcome. |
| `POST /api/next-courses` | The courses the chosen basis covers, under the chosen mode, with their required and recommended coverage. |
| `POST /api/recommendations` | The courses similar to the chosen basis, ranked, with near-duplicates left out. |
| `POST /api/study-structure` | The official structure of one degree programme or module. |
| `POST /api/course-summaries` | The official summary of each supplied identity, in the order supplied, with each repeated identity kept. |

Nine of the ten routes answer the same command that one script under `scripts/` runs, with the same inputs, and the graph route adds the drawing limit that a script caller does not apply. The summary route resolves a whole browser selection in one request, and an adapter under `scripts/` covers each of the other nine. [Command line](/docs/backend/interfaces/command-line.md) lists them.

The graph and the route are two requests of one command family. Both compile the same expression for the root, so the drawing and the calculation cannot describe different requirement sets. [Prerequisite graph](/docs/backend/prerequisites/prerequisite-graph.md) and [Minimum route](/docs/backend/prerequisites/minimum-route.md) describe the two operations.

## Outcomes and failures

A successful request returns status 200 and the command's report as JSON.

A search whose query embedding request fails against the embedding service answers with status 200, the exact-code, substring, and fuzzy matches it found, and `semantic_available` false in the report, as [Search](/docs/backend/search-and-discovery/search.md#when-the-query-embedding-request-fails) describes.

A body that does not match its closed request model is answered with status 422 and the fixed body `{"detail": "Invalid request"}`. The rejected input is not echoed.

A body the model accepts but the command rejects is answered with status 422 and the command's own message. The command rejects a blank query or identity, an unknown identity, an official code held by more than one course, a completed course outside the selected set, and a graph node key whose prefix is unsupported.

A validation failure raised inside a command, such as an invalid configuration value, is not reported as a caller error. The server answers with status 500. Any other unexpected failure answers with status 500 as well, with no report.

## Serving the browser app

Three fixed addresses serve the built browser application. `/` and `/docs` return its shell document, and `/assets` serves the compiled assets of the build. `/docs` is the address the **Docs** view opens, and [Documentation wiki](/docs/frontend/documentation-wiki.md) describes that view.

The three addresses are the whole frontend surface, so an unknown path returns the ordinary not-found response rather than the shell document.

The routes, the request models, the launcher, and the tests that hold this surface are described in [Web server](/docs/backend/interfaces/web-server.md).
