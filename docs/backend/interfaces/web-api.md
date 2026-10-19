# Web API

The web API answers 10 dataset read commands plus one feature read, serves the browser application's shell documents, and embeds a query only where the site serves semantic matching.

## The fixed route set

The surface is fixed when the application is built: 11 read routes under `/api/`, two shell documents for the browser application, and one mounted asset directory. 10 of those routes run one dataset command each, and `POST /api/features` reports the site's two feature switches. No route writes authoritative data, starts a stage, or reaches the worker. The serving middleware appends one request record to the site's own usage file, and that record is the serving path's only write. Building the application reads no configuration file, and a route reads the site's web settings when it handles a request. [System boundaries](/docs/architecture/boundaries.md) describes that separation.

Every read route answers a POST request whose body is a closed JSON object. A read uses POST because one request carries a query, course identities, and toggles together, and a closed body states that shape exactly. Each request model refuses a field it does not declare, and the feature read declares no field, so its body is the empty object.

## How a request is answered

A dataset read request is answered by one command. The route validates the body against its closed request model, calls one command once, and returns that command's own report as JSON. The feature read runs no command, because it projects two settings of the site's own `config/web.toml`. The command reads the [selected dataset](/docs/reference/glossary.md#administration) and returns one report, and no route writes authoritative data.

![The request flow: a browser request passes request validation into either one fixed dataset command or the feature read, which runs no command. The dataset command reads the selected dataset and returns one JSON report to the browser, and a semantic search sends its query text to the embedding service, shown with a dashed arrow. The serving middleware appends one request record per request to the usage file.](/docs/diagrams/web-request-flow.svg)

The diagram shows the path of one request. The feature read answers `POST /api/features` with the site's two switches. The serving middleware outside the route appends one record per request to the site's own usage file, whatever the outcome, as [Web server](/docs/backend/interfaces/web-server.md#the-request-usage-record) describes. The record holds the request-start hour, the fixed route label, the status and the duration.

The unified search embeds the query text at request time through the service that produced the stored vectors, so a query vector and a stored vector come from one model. That call is the only embedding on the request path, and a site whose `WEB_EMBEDDINGS_ENABLED` is false makes no embedding request at all.

Every other piece of data a request reads was written before the request. Ingestion writes the official courses, modules, and rules, the embedding stage writes the teaching-text chunks and their vectors, and the inference stage writes the inferred prerequisites. A comparison and a recommendation read stored vectors, and neither embeds a query. A recommendation also runs the next-course calculation, so it reads prerequisites as well. [Embeddings](/docs/backend/text-and-vectors/embeddings.md) describes the stored vectors and the two hub files.

## What a request carries

A route that takes a course identity resolves it as a canonical identity first and an exact official code second. A blank input, an unknown input, and an official code held by more than one course each fail the request instead of resolving to a guess. The study-structure route takes one canonical module identity directly, and the search, course lookup, and module lookup routes take a text query instead.

`display_language` is the app language of the routes that render official names, and its value is `fi` or `en`. Five routes take it: search, course lookup, module lookup, next courses, and recommendations. The remaining routes report official text for both languages, so they take no language input.

The selected courses, the completed courses, the exclusions, the basis, the mode, and the category toggles are request inputs. The server stores no profile and returns none, so the [browser state](/docs/reference/glossary.md#browser-app) belongs to the browser that holds it.

## The routes

| Route | What it answers |
|---|---|
| `POST /api/search` | One unified search over one query. On a site that serves semantic matching all four search methods run and their results merge to one entry per course, and a site with embedding features off runs the three lexical methods. A request may carry its own semantic and fuzzy thresholds and set whether inactive courses take part. |
| `POST /api/course-lookup` | Every represented course whose displayed official name or official code contains the query, ignoring case, with no count cap. |
| `POST /api/module-lookup` | The modules of the current academic year whose displayed name or code contains the query. |
| `POST /api/comparison` | The five comparison meters and the verdict for two course identities. |
| `POST /api/prerequisites` | The prerequisite graph of one course with its node states. The configured drawing limit applies to the drawing. |
| `POST /api/minimum-route` | The minimum-new-credit route of one course, with its outcome. |
| `POST /api/next-courses` | The courses the chosen basis covers, under the chosen mode, with their required and recommended coverage. |
| `POST /api/recommendations` | The courses similar to the chosen basis, ranked, with near-duplicates left out. |
| `POST /api/study-structure` | The official structure of one degree programme or module. |
| `POST /api/course-summaries` | The official summary of each supplied identity, in the order supplied, with each repeated identity kept. |
| `POST /api/features` | The site's two serving switches, as `{"embeddings_enabled": ..., "inference_enabled": ...}`. |

Nine of the 10 dataset routes answer the same command that one script under `scripts/` runs. Shared command ownership does not mean identical inputs: a route combines the site's semantic and inference switches into the call it makes, so a site with embedding features off runs the lexical methods alone and a site with inference off reads official data alone. The graph route adds the drawing limit that a script caller does not apply. The summary route resolves a whole browser selection in one request, and an adapter under `scripts/` covers each of the other nine. [Command line](/docs/backend/interfaces/command-line.md) lists them.

The graph and the route are two requests of one command family. Both compile the same expression for the root, so the drawing and the calculation cannot describe different requirement sets. [Prerequisite graph](/docs/backend/prerequisites/prerequisite-graph.md) and [Minimum route](/docs/backend/prerequisites/minimum-route.md) describe the two operations.

## Site features

The two switches of the site's `config/web.toml` decide which features its reads serve, and the server applies them whatever the request asks for.

With `WEB_EMBEDDINGS_ENABLED` false, comparison and recommendations refuse the request with status 403 and the fixed body `{"detail": "Feature disabled"}` before any command runs. A search request runs without the semantic method: the command composes the three lexical methods alone and reports `semantic_available` false with a tier order that omits `semantic`.

With `WEB_INFERENCE_ENABLED` false, the prerequisite graph, the minimum route, the next courses, and the recommendations replace the requested `include_inferred` with the requested value combined with the site switch. A request that asks for inferred data on such a site therefore reads official data alone. The request, the report and the command hold the same inputs and fields, and a stored preference of the browser is untouched.

## Outcomes and failures

A successful request returns status 200 and the command's report as JSON.

A search whose query embedding request fails against the embedding service answers with status 200, the exact-code, substring, and fuzzy matches it found, and `semantic_available` false in the report, as [Search](/docs/backend/search-and-discovery/search.md#when-the-query-embedding-request-fails) describes. The notice that search shows for that failure is separate from a site that serves no semantic matching, as [Search](/docs/backend/search-and-discovery/search.md) describes.

A body that does not match its closed request model is answered with status 422 and the fixed body `{"detail": "Invalid request"}`. The rejected input is not echoed.

A body the model accepts but the command rejects is answered with status 422 and the command's own message. The command rejects a blank query or identity, an unknown identity, an official code held by more than one course, a completed course outside the selected set, and a graph node key whose prefix is unsupported.

A validation failure raised inside a command, such as an invalid configuration value, is not reported as a caller error. The server answers with status 500. Any other unexpected failure answers with status 500 as well, with no report.

## Serving the browser app

Three fixed addresses serve the built browser application. `/` and `/docs` return its shell document, and `/assets` serves the compiled assets of the build. `/docs` is the address the **Docs** view opens, and [Documentation wiki](/docs/frontend/documentation-wiki.md) describes that view.

The three addresses are the whole frontend surface, so an unknown path returns the ordinary not-found response rather than the shell document.

The routes, the request models, the launcher, and the tests that hold this surface are described in [Web server](/docs/backend/interfaces/web-server.md).
