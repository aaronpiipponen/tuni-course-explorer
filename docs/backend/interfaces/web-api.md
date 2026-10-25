# Web API

The web API answers eight dataset read commands plus one feature read that reports the serving dataset identity, and it embeds a query only where the site serves semantic matching.

## The fixed route set

The surface is fixed when the application is built: nine read routes under `/api/`, two shell documents for the browser application, and one mounted asset directory. Eight of those routes run one dataset command each, and `POST /api/features` reports the site's two feature switches and the identity of the dataset it serves. No route writes authoritative data, starts a stage, or reaches the worker. The web server's front router, the one process that serves the site's loopback port, appends one request record to the site's own usage file, and that append is the serving path's one file write. With `ADMISSION_ENABLED` true, the router also holds its admission counters and activity timestamps in its process memory, and nothing persists them. Building the application reads no configuration file, and a route reads the site's web settings when it handles a request. [System boundaries](/docs/architecture/boundaries.md) describes that separation.

Every read route answers a POST request whose body is a closed JSON object. A read uses POST because one request carries a query, course identities, and toggles together, and a closed body states that shape exactly. Each request model refuses a field it does not declare, and the feature read declares no field, so its body is the empty object.

## How a request is answered

A dataset read request is answered by one command. The route validates the body against its closed request model, resolves the serving dataset once, calls one command once with that connection, and returns that command's report as JSON with the same connection's `dataset_identity`. Every cached read therefore pairs its report with the database it read. The feature read runs no command, because it projects two settings of the site's own `config/web.toml`. The command reads the [selected dataset](/docs/reference/glossary.md#administration) and returns one report, and no route writes authoritative data.

![The request flow: a browser request passes the front router, which forwards it to one of the worker processes, and request validation then accepts either one fixed dataset command or the feature read, which runs no command. The dataset command reads the selected dataset and returns one JSON report to the browser, and a semantic search sends its query text to the embedding service, shown with a dashed arrow. The front router admits the request and appends one request record per request to the usage file.](/docs/diagrams/web-request-flow.svg)

The diagram shows the path of one request. The feature read answers `POST /api/features` with the site's two switches and the serving dataset identity. The front router outside the route admits or refuses a POST to a fixed API path, forwards it to one worker process, and appends one record per request to the site's own usage file whatever the outcome, as [Web server](/docs/backend/interfaces/web-server.md#the-request-usage-record) describes. The worker process runs the application that validates the body and runs the route. The record holds the request-start hour, the fixed route label, the status and the duration. [Admission control](/docs/backend/interfaces/admission-control.md) describes the admission step and the heavy placement.

The unified search embeds the query text at request time through the service that produced the stored vectors, so a query vector and a stored vector come from one model. That call is the only embedding on the request path, and a site whose `WEB_EMBEDDINGS_ENABLED` is false makes no embedding request at all.

Every other piece of data a request reads was written before the request. Ingestion writes the official courses, modules, and rules, the embedding stage writes the teaching-text chunks and their vectors, and the inference stage writes the inferred prerequisites. A comparison and a recommendation read stored vectors, and neither embeds a query. A recommendation also runs the next-course calculation, so it reads prerequisites as well. [Embeddings](/docs/backend/text-and-vectors/embeddings.md) describes the stored vectors and the two hub files.

## What a request carries

A route that takes a course identity resolves it as a canonical identity first and an exact official code second. A blank input, an unknown input, and an official code held by more than one course each fail the request instead of resolving to a guess. The study-structure route takes canonical root identities and one optional exact version identity per canonical group directly, the catalogue route takes no input, and the search route takes a text query instead.

`display_language` is the app language of the routes that render official names, and its value is `fi` or `en`. Three routes take it: search, next courses, and recommendations. The remaining routes report official text for both languages, so they take no language input.

The selected courses and the completed courses are request inputs. The next-courses and recommendations routes take the basis and the mode as well, and the prerequisite route takes the two category toggles. The server stores no profile and returns none, so the [browser state](/docs/reference/glossary.md#browser-app) belongs to the browser that holds it.

The graph route takes the structural subset alone: the root course, the selected and completed course sets, the **Recommended** and **Inferred** toggles, and the activity scope. The two course sets serve one purpose, the retention of selected or completed inactive courses that the scope would otherwise leave out. Graph marks, the calculation basis and the excluded courses belong to the browser, and a request that carries one of them is refused as an invalid request. The browser combines them with the held solver structure when it calculates a route in a disposable browser worker.

## The routes

| Route | What it answers |
|---|---|
| `POST /api/search` | One unified search over one query. On a site that serves semantic matching all four search methods run and their results merge to one entry per course, and a site with embedding features off runs the three lexical methods. A request may carry its own semantic and fuzzy thresholds and set whether inactive courses take part. |
| `POST /api/catalogue` | The minimal official catalogue the browser narrows locally: every represented course's canonical identity, code, FI and EN names, credits and activity flag, and every canonical module's eligible version candidates with their exact version identity, kind, code, FI and EN names, validity bounds and period memberships. It carries no official URL, course representative source identity, teaching text, description or prerequisite. |
| `POST /api/comparison` | The five comparison meters and the verdict for two course identities. |
| `POST /api/prerequisites` | The solver structure of one course, the drawing when the configured drawing limit permits it, the identity of the dataset the read resolved, and the configured solver allocation limit. The report carries no computed box states. |
| `POST /api/next-courses` | The courses the chosen basis covers, under the chosen mode, with their required and recommended coverage. |
| `POST /api/recommendations` | The courses similar to the chosen basis, ranked, with near-duplicates left out. |
| `POST /api/study-structure` | The official structure of every supplied root identity over one shared read under the request's `module_versions` map, the roots that could not be projected when `allow_unavailable` is true, and the roots that need an explicit version selection, reported as `version_selection_required`. |
| `POST /api/course-summaries` | The official summary of each supplied identity, in the order supplied, with each repeated identity kept. |
| `POST /api/features` | The site's two serving switches and its serving dataset identity, as `{"embeddings_enabled": ..., "inference_enabled": ..., "dataset_identity": ...}`. |

Six dataset routes answer the same command that one script under `scripts/` runs: search, catalogue, comparison, prerequisites, next courses, and recommendations. Shared command ownership does not mean identical inputs: a route combines the site's semantic and inference switches into the call it makes, so a site with embedding features off runs the lexical methods alone and a site with inference off reads official data alone. The graph route adds the drawing limit that a script caller does not apply. The structure route answers the batch command whose single-root form is the script adapter, and the summary route resolves a whole browser selection in one request without a separate script adapter. [Command line](/docs/backend/interfaces/command-line.md) lists them.

The graph read is the browser's one prerequisite request. It compiles the solver structure for the root, so the drawing and any calculation from that structure describe the same requirement set. A refused drawing carries the solver structure and its located reasons. The graph route resolves one serving connection and passes it to the command, so the identity it reports and the structure it returns come from the same database resolution. A route is calculated in the browser from that response, and the machine route command compiles the same structure through the same command module. [Prerequisite graph](/docs/backend/prerequisites/prerequisite-graph.md) and [Minimum route](/docs/backend/prerequisites/minimum-route.md) describe the graph response and the calculation.

## The serving dataset identity

Every dataset read reports one opaque `dataset_identity` beside its report, and `POST /api/features` reports it beside the two feature switches. It is the canonical digest of the serving process's generation value and the selected dataset identity, or of the generation value and a JSON null when the site reads its configured database directly. A selected receipt switch changes it on the next read, a restarted feature web server changes it, and no other event does.

The identity is the freshness boundary of the browser's reads. A response carrying a different identity clears the values the browser held for the previous one, and a hit against the held identity sends no request. The browser applies it to one memory cache of successful reads and one persistent store of structure reports. The local narrowing boxes filter the cached catalogue, so typing sends no request. An in-place change to served data in either database mode requires a restarted feature web server and then an uncached read or reload, because a restart notifies no idle tab. Nothing on the serving path polls, revalidates or reports the identity on a schedule.

The two switches of the site's `config/web.toml` decide which features its reads serve, and the server applies them whatever the request asks for.

With `WEB_EMBEDDINGS_ENABLED` false, comparison and recommendations refuse the request with status 403 and the fixed body `{"detail": "Feature disabled"}` before any command runs. A search request runs without the semantic method: the command composes the three lexical methods alone and reports `semantic_available` false with a tier order that omits `semantic`.

With `WEB_INFERENCE_ENABLED` false, the prerequisite graph, the next courses, and the recommendations replace the requested `include_inferred` with the requested value combined with the site switch. A request that asks for inferred data on such a site therefore reads official data alone. The request, the report and the command hold the same inputs and fields, and a stored preference of the browser is untouched.

## Outcomes and failures

A successful request returns status 200 and the command's report as JSON. A worker process compresses a response larger than the gzip middleware's 500-byte threshold when the caller accepts gzip, and the router forwards the encoded bytes and their headers. The decoded body is identical.

### Admission responses

With `ADMISSION_ENABLED` true, a light read over its per-user limit and a heavy read over its budget or its queue cap answer `429` with `{"detail": "Too much traffic"}` and the `Retry-After` header. A heavy read that finds the queue below its cap waits for a slot without a time limit, and each admitted heavy read runs on a worker process that carries no other heavy request. With admission enabled, every response to a path under `/api/` sets the anonymous `tce_anon` cookie. `POST /api/features` and `POST /api/course-summaries` are free reads and are never limited, queued or counted. [Admission control](/docs/backend/interfaces/admission-control.md) states the classes, their limits and the placement.

A search whose query embedding request fails against the embedding service answers with status 200, the exact-code, substring, and fuzzy matches it found, and `semantic_available` false in the report, as [Search](/docs/backend/search-and-discovery/search.md#when-the-query-embedding-request-fails) describes. The notice that search shows for that failure is separate from a site that serves no semantic matching, as [Search](/docs/backend/search-and-discovery/search.md) describes.

A body that does not match its closed request model is answered with status 422 and the fixed body `{"detail": "Invalid request"}`. The rejected input is not echoed.

A body the model accepts but the command rejects is answered with status 422 and the command's own message. The command rejects a blank query or identity, an unknown identity, an official code held by more than one course, and a completed course outside the selected set. Every API read of a serving process with no generation value fails instead of reporting an identity it cannot derive.

A validation failure raised inside a command, such as an invalid configuration value, is not reported as a caller error. The server answers with status 500. Any other unexpected failure answers with status 500 as well, with no report.

## Serving the browser app

Three fixed addresses serve the built browser application. `/` and `/docs` return its shell document, and `/assets` serves the compiled assets of the build. `/docs` is the address the **Docs** view opens, and [Documentation wiki](/docs/frontend/documentation-wiki.md) describes that view.

The three addresses are the whole frontend surface, so an unknown path returns the ordinary not-found response rather than the shell document.

The routes, the request models, the launcher, and the tests that hold this surface are described in [Web server](/docs/backend/interfaces/web-server.md).
