# Web API

The web API answers eight dataset reads, one feature read, the current feedback definition and one anonymous feedback submission.

## The fixed route set

The surface is fixed when the application is built: nine read routes under `/api/`, the feedback definition read and submission write, three shell documents for the browser application, and one mounted asset directory. Seven of the eight dataset read routes run one dataset command each, the catalogue route serves the current build's retained body without running a command, and `POST /api/features` reports the site's two feature switches and the identity of the dataset it serves. `GET /api/feedback/definition` reports the current feedback definition, and `POST /api/feedback` hands one submission to the separate feedback application store.

No route writes authoritative catalogue or user data, starts a stage, or reaches the worker. The web server's front router, the one process that serves the site's loopback port, appends one request record to the site's own usage file, and that append is the serving path's own file write. An admitted feedback submission is retained by the separate feedback application store through its owning service. With `ADMISSION_ENABLED` true, the router also holds its admission counters and activity timestamps in its process memory, and nothing persists them. Building the application reads no configuration file, and a route reads the settings it needs when it handles a request. [System boundaries](/docs/architecture/boundaries.md) describes that separation.

Every dataset read route answers a POST request whose body is a closed JSON object. A dataset read uses POST because one request carries a query, course identities, and toggles together, and a closed body states that shape exactly. Each request model refuses a field it does not declare, and the feature read declares no field, so its body is the empty object. The feedback definition read is a GET with no body, and the feedback submission is a POST whose closed body carries the answers, the attachment carriers and the explicit choice.

## How a request is answered

A dataset read request is answered by one command. The route validates the body against its closed request model, resolves the serving dataset once, calls one command once with that connection, and returns that command's report as JSON with the same connection's `dataset_identity`. The catalogue route is the one exception to the command serializer: it returns the current build's retained plain body with the identity appended, or the gzip form compressed from that body, so the bytes keep their field order without rebuilding the report. The route chooses the gzip form only for a client that admits gzip with a positive weight, and it sends that form with `Content-Encoding: gzip` and `Vary: Accept-Encoding`. The route's plain answer carries no encoding header and no route-supplied `Vary`.

Every cached read therefore pairs its report with the database it read. The feature read runs no command, because it projects two settings of the site's own `config/web.toml`. The command reads the [Selected dataset](/docs/reference/glossary.md#administration) and returns one report, and no route writes authoritative data. [Serving state](/docs/backend/interfaces/serving-state.md#the-catalogue-artifact) states the two catalogue answers.

![The dataset request flow: a browser request passes the front router, which forwards it to one of the worker processes. Request validation accepts the closed request model, and the route runs one fixed dataset command that reads the selected dataset and returns one command report to the browser. A semantic search sends its query text to the embedding service, shown with a dashed arrow.](/docs/diagrams/web-request-flow.svg)

The diagram follows one dataset read. The feature read answers `POST /api/features` with the site's two switches and the serving dataset identity. The front router outside the route admits or refuses a catalogue POST to a fixed API path, forwards it to one worker process, and appends one record per request to the site's own usage file whatever the outcome, as [Front router](/docs/backend/interfaces/front-router.md#the-request-usage-record) describes. The worker process runs the application that validates the body and runs the route. The record holds the request-start hour, the fixed route label, the status and the duration. [Admission control](/docs/backend/interfaces/admission-control.md) describes the admission step and the heavy placement.

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
| `GET /api/feedback/definition` | The current feedback definition with the configured `repository`, `visibility` and `max_request_bytes`. No stored submission, database address, attachment root or credential appears in it. |
| `POST /api/feedback` | The narrow committed acknowledgment of one stored feedback submission. |

Five dataset routes answer the same command that one script under `scripts/` runs: search, comparison, prerequisites, next courses, and recommendations. The catalogue route serves the current build's retained artifact and runs no command, while its script adapter runs the catalogue command. Shared command ownership does not mean identical inputs: a route combines the site's semantic and inference switches into the call it makes, so a site with embedding features off runs the lexical methods alone and a site with inference off reads official data alone. The graph route adds the drawing limit that a script caller does not apply. The structure route answers the batch command whose single-root form is the script adapter, and the summary route resolves a whole browser selection in one request without a separate script adapter. [Command line](/docs/backend/interfaces/command-line.md) lists them.

The graph read is the browser's one prerequisite request. It compiles the solver structure for the root, so the drawing and any calculation from that structure describe the same requirement set. A refused drawing carries the solver structure and its located reasons. The graph route resolves one serving connection and passes it to the command, so the identity it reports and the structure it returns come from the same database resolution. A route is calculated in the browser from that response, and the machine route command compiles the same structure through the same command module. [Prerequisite graph](/docs/backend/prerequisites/prerequisite-graph.md) and [Minimum route](/docs/backend/prerequisites/minimum-route.md) describe the graph response and the calculation.

## The serving dataset identity

Every dataset read reports one opaque `dataset_identity` beside its report, and `POST /api/features` reports it beside the two feature switches. It is the canonical digest of the serving process's generation value and the Selected dataset identity, or of the generation value and a JSON null when the site has no Selected pointer and reads its configured database directly. The supervisor resolves the pointer once, so the identity holds for its whole lifetime, and a restarted feature web server creates a fresh generation and reports another identity. A Selected pointer change reaches the site through the restart procedure that [Operations](/docs/operations/README.md#derived-files-served-data-and-the-web-restart) states, because the supervisor resolves the dataset, fixes the lookup projection and creates the shared caches for its lifetime.

The identity is the freshness boundary of the browser's reads. A response carrying a different identity clears the values the browser held for the previous one, and a hit against the held identity sends no request. The browser applies it to one memory cache of successful reads, one persistent discovery cache of next-course and recommendation reports, and one persistent store of structure reports. The local narrowing boxes filter the cached catalogue, so typing sends no request. An in-place change to served data in either database mode requires a restarted feature web server and then an uncached read or reload, because a restart notifies no idle tab. Nothing on the serving path polls, revalidates or reports the identity on a schedule.

The two switches of the site's `config/web.toml` decide which features its reads serve, and the server applies them whatever the request asks for.

With `WEB_EMBEDDINGS_ENABLED` false, comparison and recommendations refuse the request with status 403 and the fixed body `{"detail": "Feature disabled"}` before any command runs. A search request runs without the semantic method: the command composes the three lexical methods alone and reports `semantic_available` false with a tier order that omits `semantic`.

With `WEB_INFERENCE_ENABLED` false, the prerequisite graph, the next courses, and the recommendations replace the requested `include_inferred` with the requested value combined with the site switch. A request that asks for inferred data on such a site therefore reads official data alone. The request, the report and the command hold the same inputs and fields, and a stored preference of the browser is untouched.

## The feedback surface

The two feedback paths are the backend of the feedback surface. Both are anonymous and both answer with `Cache-Control: no-store`. `GET /api/feedback/definition` loads `config/feedback-form.json` from the checkout root and returns `{"definition": ..., "repository": ..., "visibility": ..., "max_request_bytes": ...}`. The feedback definition carries the ordered fields, the bilingual labels, the options, the upload limits and the issue mapping. The repository and visibility are the configured destination metadata, and the body bound is the configured ceiling. The read opens no connection to the feedback application store and returns no stored submission, attachment, path or token.

`POST /api/feedback` accepts one closed JSON object with three fields. `answers` maps each current text or select field ID to its text or null. `attachments` is an array of objects carrying `field_id`, the submitted `filename` and a standard `content_base64` value, with no media type, profile or visibility field. `public_issue` is the explicit boolean publication choice. The worker decodes each carrier as standard base64, requires the filename to be a bounded plain basename, and passes the answer mapping, the decoded uploads and the choice to the feedback service once. The feedback definition retains the only field, count, size, filename and real PNG or JPEG validation.

A committed submission answers status 201 with `{"accepted": true, "publication_state": "private" | "pending"}`. The state is derived from the submission's own committed publication choice, so `pending` states that an opt-in submission awaits its feedback publication and does not claim that an issue exists. It is the initial acknowledgment, not the row's current publication state: a sender can advance the row to another outcome between the commit and the response, and the anonymous answer reports `private` or `pending` and carries no issue link. The answer carries no submission identity, answer text, image bytes or local path.

The front router admits the write only for the exact Host and Origin of the site's external app address, which is `WEB_APP_URL` of `config/web.toml` without its optional root slash. A missing, repeated, `null` or foreign Origin, and a missing, repeated or foreign Host, answers 403 before the body is read. Forwarded host and protocol headers are ignored. The media type must be `application/json` with any parameters, otherwise the request answers 415. A declared `Content-Length` above `FEEDBACK_MAX_REQUEST_BYTES` answers 413 before any body byte is read, a malformed or repeated length answers 400, and a chunked body without a length is bounded by the same byte count as it streams. A disconnect inside the bounded read answers 400 and forwards nothing.

An admitted attempt charges the anonymous browser and the site in one transient rolling-hour allowance. The allowance is `FEEDBACK_BROWSER_SUBMISSIONS_PER_HOUR` per browser cookie and `FEEDBACK_SITE_SUBMISSIONS_PER_HOUR` for the whole site, 5 and 30 in the example. The charge is taken after the site, media-type and declared-length checks and before the body is read, so an invalid or oversized body spends it. A refusal answers 429 with `Retry-After` in whole seconds, and the allowance holds no refund, persisted history, address or fingerprint. It belongs to the front router's process memory, so a replacement router starts empty. A fresh browser cookie gets a fresh browser allowance and shares the site allowance.

Both feedback paths use the same anonymous `tce_anon` cookie as the catalogue reads, and they set it even when `ADMISSION_ENABLED` is false. A feedback request takes no light or heavy admission token and is not charged against the catalogue limits.

## Outcomes and failures

A successful dataset read returns status 200 and the command's report as JSON. `GZipMiddleware` compresses a response of at least 500 bytes that carries no `Content-Encoding`, and it decides from its own test of the `Accept-Encoding` header for the coding's name alone. A request that names gzip with a zero weight therefore receives a compressed response. The router forwards the encoded bytes and their headers. The decoded body is identical.

### Admission responses

With `ADMISSION_ENABLED` true, a light read over its per-user limit and a heavy read over its budget or its queue cap answer `429` with `{"detail": "Too much traffic"}` and the `Retry-After` header. A heavy read that finds the queue below its cap waits for a slot without a time limit, and each admitted heavy read runs on a worker process that carries no other heavy request.

With admission enabled, the front router sets the anonymous `tce_anon` cookie on every request to a catalogue `/api/` path that it admits or refuses after the body read. A body refused at `WEB_REQUEST_BODY_MAX_BYTES`, and a client that disconnects inside that bounded read, are answered before the router sets any cookie, so that refusal carries none. The two feedback paths set the same cookie whether admission is on or off. `POST /api/features` and `POST /api/course-summaries` are free reads and are never limited, queued or counted. [Admission control](/docs/backend/interfaces/admission-control.md) states the classes, their limits and the placement, and the same page states the separate feedback allowance.

A search whose query embedding request fails against the embedding service answers with status 200, the exact-code, substring, and fuzzy matches it found, and `semantic_available` false in the report, as [Search](/docs/backend/search-and-discovery/search.md#when-the-query-embedding-request-fails) describes. The notice that search shows for that failure is separate from a site that serves no semantic matching, as [Search](/docs/backend/search-and-discovery/search.md) describes.

A body that does not match its closed request model is answered with status 422 and the fixed body `{"detail": "Invalid request"}`. The rejected input is not echoed. The feedback paths add `Cache-Control: no-store` to that answer.

A request input past its configured bound is refused at one of two layers. A body larger than `WEB_REQUEST_BODY_MAX_BYTES` answers status 413 with `{"detail": "Request body refused"}` at the front router, before any worker process runs, and a client that disconnects inside that read answers 400. An input past `WEB_REQUEST_MAX_COURSE_ITEMS`, `WEB_REQUEST_MAX_IDENTIFIER_LENGTH` or `WEB_REQUEST_MAX_QUERY_LENGTH` fails the request model, so it answers the same 422 as a body the model does not accept. The four keys and the fields each one bounds are listed in [Web routes](/docs/backend/interfaces/web-routes.md#the-input-bounds).

A body the model accepts but the command rejects is answered with status 422 and the command's own message. The command rejects a blank query or identity, an unknown identity, an official code held by more than one course, and a completed course outside the selected set. Every API read of a serving process with no generation value fails instead of reporting an identity it cannot derive.

A validation failure raised inside a command, such as an invalid configuration value, is not reported as a caller error. The server answers with status 500. Any other unexpected failure answers with status 500 as well, with no report.

### Feedback responses

A feedback refusal from the front router is `403`, `400`, `413`, `415` or `429` with the fixed body `{"detail": "Feedback request refused"}`, `Cache-Control: no-store` and, for `429`, `Retry-After`. A refused site, media-type or declared-length check sets no cookie, and a quota or streamed-body refusal carries the established anonymous cookie.

A decoded answer, filename or image the feedback definition refuses answers 422 with `{"detail": "Invalid feedback"}` and no-store. A failure of the feedback application store or attachment write answers 500 with `{"error": "<exception class>"}` and no-store, and no input, path or stored identity reaches the answer. A successful submission is the one 201 acknowledgment described above.

## Serving the browser app

Four fixed addresses serve the built browser application. `/`, `/docs` and `/feedback` return its shell document, and `/assets` serves the compiled assets of the build. `/docs` is the address the **Docs** view opens, and [Documentation wiki](/docs/frontend/documentation-wiki.md) describes that view.

The four addresses are the whole frontend surface, so an unknown path returns the ordinary not-found response rather than the shell document.

The routes and their request models are described in [Web routes](/docs/backend/interfaces/web-routes.md), the serving state and its retained artifact set in [Serving state](/docs/backend/interfaces/serving-state.md), the supervisor and its launcher in [Web supervisor](/docs/backend/interfaces/web-supervisor.md), and the front router's usage, feedback and admission boundaries in [Front router](/docs/backend/interfaces/front-router.md).
