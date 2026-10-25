# Web server

The web package builds a read-only application, hands it a restricted process environment, and serves it on loopback sockets through one front router and the configured worker processes.

## Application construction

`create_app(*, frontend_directory: Path | None = None)` in `src/course_explorer_web/app.py` builds the whole surface. It creates `FastAPI(docs_url=None, redoc_url=None, openapi_url=None)`, includes the nine route modules in a fixed tuple, registers the two exception handlers, registers the frontend, adds `GZipMiddleware(minimum_size=500, compresslevel=6)`, and returns the application. The module also binds `app = create_app()`, which is the import string a worker process serves.

Construction reads no settings, opens no database context, creates no file, and contacts no provider. The routers read settings inside a handler alone, so importing `course_explorer_web.app` reads no configuration and opens no database.

## The route modules

Every dataset handler resolves one serving dataset, delegates once with that connection and returns the command's report through one serializer that adds the connection's identity. The gzip middleware compresses a response of at least 500 bytes, and the router forwards the encoded bytes. The front router records the usage line, so a worker process appends none. `POST /api/features` runs no command, because it projects two settings of `WebSettings` and the resolved dataset identity. `src/course_explorer_web/routes/prerequisite_inputs.py` holds `PrerequisiteGraphRequest` for the graph route.

| Route | Module | Request model | Command | Report |
|---|---|---|---|---|
| `POST /api/search` | `routes/search.py` | `SearchRequest` | `course_explorer.search.commands.run_search_command` | `UnifiedSearchReport` plus `dataset_identity` |
| `POST /api/catalogue` | `routes/catalogue.py` | `CatalogueRequest` | `course_explorer.search.lookup_commands.run_catalogue_command` | `CatalogueReport` plus `dataset_identity` |
| `POST /api/comparison` | `routes/comparison.py` | `ComparisonRequest` | `course_explorer.comparison.commands.run_course_comparison_command` | `CourseComparisonReport` plus `dataset_identity` |
| `POST /api/prerequisites` | `routes/prerequisites.py` | `PrerequisiteGraphRequest` | `course_explorer.prerequisite.commands.run_prerequisite_command` | `PrerequisiteGraphReport` plus `dataset_identity` and `max_compact_nodes` |
| `POST /api/next-courses` | `routes/next_courses.py` | `NextCoursesRequest` | `course_explorer.next_courses.commands.run_next_courses_command` | `NextCoursesReport` plus `dataset_identity` |
| `POST /api/recommendations` | `routes/recommendations.py` | `RecommendationsRequest` | `course_explorer.recommendations.commands.run_recommendations_command` | `RecommendationsReport` plus `dataset_identity` |
| `POST /api/study-structure` | `routes/study_structure.py` | `StudyStructureRequest` | `course_explorer.study_structure.commands.run_study_structures_command` | `StudyStructuresReport` plus `dataset_identity` |
| `POST /api/course-summaries` | `routes/course_summaries.py` | `CourseSummariesRequest` | `course_explorer.search.lookup_commands.run_course_summaries_command` | `CourseSummariesReport` plus `dataset_identity` |
| `POST /api/features` | `routes/features.py` | `FeaturesRequest` | None | `WebFeaturesReport` |

Two handlers pass their dumped request to the command: `POST /api/search` adds the site's semantic switch as `include_semantic`, and `POST /api/comparison` passes the dump as it is. `POST /api/catalogue` passes no input. `POST /api/course-summaries` passes `request.identifiers` positionally, and `POST /api/study-structure` passes `request.root_group_ids` positionally with `allow_unavailable` and the request's `module_versions` map.

Three handlers build one dumped dictionary and replace its `include_inferred` with the requested value combined with the site's inference switch: `POST /api/prerequisites`, `POST /api/next-courses` and `POST /api/recommendations`.

Every dataset handler passes the resolved connection as `database_settings`, and `POST /api/prerequisites` adds `max_drawing_elements=load_web_settings().prerequisite_graph_max_elements`.

Five handlers also pass retained caches. `POST /api/search` and `POST /api/catalogue` pass `projection_cache=cache.lookup_projection`. `POST /api/prerequisites` and `POST /api/next-courses` pass `source_cache=cache.prerequisite_sources`. `POST /api/recommendations` passes both `source_cache=cache.prerequisite_sources` and `chunk_cache=cache.descriptive_chunks`, where `cache = serving_caches(serving, load_web_settings())` for that request's resolved dataset.

Five handlers apply the site's feature switches to the call they make. `POST /api/search` adds `include_semantic=load_web_settings().embeddings_enabled` to the command call. `POST /api/comparison` and `POST /api/recommendations` raise `HTTPException(status_code=403, detail="Feature disabled")` when embeddings are off, before the command runs. `POST /api/prerequisites`, `POST /api/next-courses`, and `POST /api/recommendations` replace the dumped `include_inferred` with the requested value combined with the site's inference switch.

Every handler is a synchronous `def`, so FastAPI runs it in a thread rather than on the event loop, and each request owns its own engine lifetime inside the command. One request resolves its serving connection once, so the report it receives and the identity it publishes describe one database.

## The dataset-scoped retained caches

`serving_caches(serving, settings)` in `src/course_explorer_web/serving_cache.py` returns the three retained facilities of one serving dataset identity. One module-level slot holds the current set behind one lock. A request whose resolved identity matches receives the same instances, and a request whose identity differs builds a new set, so a retained row never outlives the dataset it was read from.

Each facility builds on its first use rather than at construction. Construction reads no database, opens no engine and touches no file.

| Facility | Consumed by | Retained graph |
|---|---|---|
| `LookupProjectionCache` in `src/course_explorer/search/projection.py` | `run_search_command` and `run_catalogue_command` | The normalized course rows and module identities of the dataset, built on the first lexical or catalogue read. |
| `PrerequisiteSourceFactCache` in `src/course_explorer/prerequisite/source_cache.py`, used through `ReusingCurriculumGraphRead` | `run_prerequisite_command`, `run_next_courses_command` and the recommendation command's discovery step | At most `WEB_PREREQUISITE_SOURCE_CACHE_ENTRIES` raw course and module facts in least-recently-used order, where an identity the dataset does not hold counts as one entry. |
| `DescriptiveChunkCache` in `src/course_explorer/embeddings/read.py` | The two descriptive chunk reads of `run_recommendations_command` | At most `WEB_CHUNK_CACHE_ENTRIES` tuples of descriptive chunk carriers keyed by the read triple, in least-recently-used order, where a triple with no compatible row counts as one entry. |

The lookup projection retains the official summary of every represented course, both names included, and the source-fact cache retains the raw course and module rows a graph read returned, with each selected representative version and its official text. The chunk cache retains descriptive chunk carriers with their text and vectors. No facility retains a user's eligibility, a basis profile, a candidate pool, query text or a compiled tree.

`WebSettings` carries the accounting shares. The per-process share is `WEB_LOOKUP_PROJECTION_CACHE_BYTES` plus `WEB_PREREQUISITE_SOURCE_CACHE_ENTRIES` times `WEB_PREREQUISITE_SOURCE_CACHE_ENTRY_BYTES` plus `WEB_CHUNK_CACHE_ENTRIES` times `WEB_CHUNK_CACHE_ENTRY_BYTES`. The validator `require_retained_cache_shares_within_aggregate` refuses a configuration whose `WEB_WORKERS` times that share exceeds `WEB_RETAINED_CACHE_AGGREGATE_BYTES`, and nothing measures a cache at runtime. The example sets 33554432 bytes, 8000 entries at 7006 bytes each, 497 entries at 137794 bytes each, and a 1073741824-byte aggregate, so one process holds a 158086050-byte share, two processes hold 316172100 bytes, and four processes hold 632344200 bytes. Six shares, 948516300 bytes, fit the aggregate, and seven shares, 1106602350 bytes, exceed it. The projection is one configured byte figure rather than a per-entry count.

## Request models and defaults

Every request model sets `model_config = ConfigDict(extra="forbid")`, so a field the model does not declare fails the request.

| Model | Fields |
|---|---|
| `SearchRequest` | `query: str`, `display_language: DisplayLanguage`, `semantic_min_score: float \| None = None`, `fuzzy_min_score: float \| None = None`, `include_inactive: bool = True` |
| `CatalogueRequest` | No fields, so the empty object is the whole body |
| `ComparisonRequest` | `course_a: str`, `course_b: str` |
| `PrerequisiteGraphRequest` | `target_code: str`, `selected_codes: tuple[str, ...] = ()`, `completed_codes: tuple[str, ...] = ()`, `include_recommended: bool = False`, `include_inferred: bool = False`, `active_only: bool = False` |
| `NextCoursesRequest` | `selected_courses: tuple[str, ...] = ()`, `completed_courses: tuple[str, ...] = ()`, `basis: str = "completed"`, `mode: str = "all"`, `display_language: DisplayLanguage`, `include_inferred: bool = False`, `active_only: bool = True` |
| `RecommendationsRequest` | Same fields and defaults as `NextCoursesRequest` |
| `StudyStructureRequest` | `root_group_ids: tuple[str, ...]`, `module_versions: dict[str, str] = {}`, `allow_unavailable: bool = False` |
| `CourseSummariesRequest` | `identifiers: tuple[str, ...] = ()` |
| `FeaturesRequest` | No fields, so the empty object is the whole body |

`DisplayLanguage` is `Literal["fi", "en"]` in `src/course_explorer/search/lookup.py`. A `None` score override leaves the command to use the configured threshold. `basis` and `mode` are plain strings here and are validated by the command, so an unsupported value becomes the command's own `ValueError`.

`SearchRequest.include_inactive` and the `active_only` field of `NextCoursesRequest` and `RecommendationsRequest` take their defaults from `INCLUDE_INACTIVE_DEFAULT` and `ACTIVE_ONLY_DEFAULT` in `src/course_explorer_web/serving.py`. The classifier reads the same two values, so the request model and the admission pricing share one default.

The graph route reads `load_web_settings()` and `load_search_settings()` on each request rather than at construction, so the drawing limit and the solver allocation limit come from the values the serving process started with. Every other route that applies a site switch reads the same settings the same way. A change to `PREREQUISITE_GRAPH_MAX_ELEMENTS`, `WEB_EMBEDDINGS_ENABLED` or `WEB_INFERENCE_ENABLED` in `config/web.toml` reaches the server after the launcher starts the process again.

## Reports and error handlers

Each dataset handler returns `dataset_report_response(report, serving, **metadata)` from `src/course_explorer_web/reports.py`. The serializer writes the command report in JSON mode and adds the top-level `dataset_identity` of the connection the handler resolved, plus any web-only metadata the route supplies. The graph route adds `max_compact_nodes`, because the limit belongs to the served site's policy rather than to the machine report. No machine report acquires a serving identity, and no connection or receipt field leaves the server.

`resolve_serving_dataset()` in `src/course_explorer_web/dataset.py` is the one serving-identity owner. It resolves the database and its selected receipt together through `load_database_settings_with_identity()`, requires the nonempty `COURSE_EXPLORER_WEB_GENERATION` process value, and hashes `[generation, selected_dataset_id]` with the product's canonical `json_sha256` and `ensure_ascii=False`. Raw database mode contributes a JSON null selection, so its identity depends on the generation alone. Only that digest leaves the server: no connection URL, host, database name, password, receipt content or process identity is reported. A missing generation value raises at the read boundary, so a serving process that was not started by the entry point fails its first cached read instead of serving without an identity.

`create_app` registers two handlers:

- `command_error` for `ValueError`. It re-raises when the exception is a `pydantic.ValidationError` and otherwise returns status 422 with `{"detail": str(exc)}`.
- `invalid_request` for `fastapi.exceptions.RequestValidationError`. It returns status 422 with the fixed `{"detail": "Invalid request"}` and echoes nothing from the body.

A `ValidationError` raised inside a command, and any other exception, are left to the server's default failure response, which carries status 500 and no report.

## The request usage record

`UsageMiddleware` in `src/course_explorer_web/router/usage.py` is a pure ASGI middleware that the front router wraps around its forwarding handler. A non-HTTP scope passes through on its own path. For an HTTP scope it captures the current UTC hour, rounded down by the shared owner `course_explorer.usage.rounded_usage_hour`, and the monotonic start time at entry, wraps `send` so it reads the status of the `http.response.start` message while passing every message through to the client, and appends exactly one record in a `finally` block after the forwarding handler returns or raises.

The append is the serving path's only file write. With `ADMISSION_ENABLED` true, the front router also holds its admission counters, activity timestamps and graph costs in its process memory, as [Admission control](#admission-control) describes. Only the router reads that state, nothing persists it or shares it between processes, and no usage report or administration surface reads it. The append adds one line to the checkout's `data/usage/requests`, which is neither authoritative catalogue data nor user data, and no aggregation or pruning runs inside a request. Each line is one compact JSON object with exactly four fields:

| Field | Meaning |
|---|---|
| `hour` | The request-start UTC hour rounded down, as an aware ISO timestamp |
| `route` | The fixed route label described below |
| `status` | The status the response started with, or 500 when the request failed before a response started |
| `duration_seconds` | Elapsed monotonic serving seconds until the inner application returned or raised, including ordinary response sends |

Every HTTP outcome of every address is recorded once: a successful feature, shell or asset read, a disabled-feature 403, a validation 422, an admission 429, a method 405, a 404 for an unknown path, and an unhandled failure that produces the server's 500. The record holds no method, identity, payload, exception, request URL, query or header.

The route label comes from the request path rather than from the worker process's routing metadata. Exactly `/` and `/docs` report themselves, a path equal to one of the nine fixed API paths reports that path, and a path equal to `/assets` or beginning `/assets/` reports `/assets`. Any other path reports `unmatched`. A requested asset name, an unknown path and a query string are therefore never retained.

The append runs in a thread pool thread, so a usage report holding the file's lock cannot block the event loop. An append failure propagates, including when it happens after the response was transmitted. The middleware reads no settings and resolves the usage file when a request is handled, so construction and import create no file.

## Admission control

`RouterApplication` in `src/course_explorer_web/router/app.py` decides whether a read is served, waits or is refused, and `AdmissionState` in `src/course_explorer_web/admission/state.py` holds its counters, activity timestamps, tickets and graph costs in process memory. `AdmissionSettings` in `src/course_explorer/config.py` reads the policy from `config/admission.toml` and the shared `WEB_WORKERS` value. `startup` builds the state from `host_cpu.core_count()` and starts the once-a-second sampler. Admission off leaves `state` as `None`, reads no core count and starts no sampler, and every read is then forwarded to the least busy worker process. The classes, the limits, the regimes, the queue and the refusal answers are on [Admission control](/docs/backend/interfaces/admission-control.md).

`src/course_explorer_web/admission/classify.py` owns the class and the cost of one request. `classify` returns a `Classification` of an `AdmissionClass` and a cost, `basis_size` counts the distinct nonblank identifier strings of the chosen basis list, and `active_only_from_body` applies `ACTIVE_ONLY_DEFAULT`. `recommendation_cost` and `next_courses_cost` evaluate `_curve_cost`: `origin_cost + slope * (basis - origin_basis)` up to the knee, then `tail_cost + tail_slope * (basis - knee_basis)`. The search class reads `INCLUDE_INACTIVE_DEFAULT` and charges `ADMISSION_SEARCH_INACTIVE_COST_CORE_SECONDS`, the graph class compares the cached cost with `ADMISSION_GRAPH_HEAVY_SECONDS`, and every other route that is not free is light. `graph_cost_field` in `src/course_explorer_web/admission/graph_cost.py` builds the cache field `<target>|<recommended>|<inferred>|<active>` from the request's `target_code` string as sent, so an official code and the canonical identity of the same course make two fields.

The example's recommendation curve is `0.4658 + 0.29709 * (b - 3)` core-seconds up to a basis of 50 and `14.429 + 0.13927 * (b - 50)` above it, and the scope that includes inactive courses uses `0.7563 + 0.39118 * (b - 3)` and `19.142 + 0.19679 * (b - 50)`. The next-courses curve is `0.19007 + 0.015076 * (b - 3)` and `0.89866 + 0.0084145 * (b - 50)` in the active-only scope, and `0.31199 + 0.031052 * (b - 3)` and `1.7715 + 0.012779 * (b - 50)` with inactive courses, where `b` is the basis size.

`RouterApplication._forward` measures a graph build from immediately before `client.send` to the end of the response body, so the elapsed time includes the worker process's compression. `POST /api/prerequisites` in `src/course_explorer_web/routes/prerequisites.py` sets `MEASURE_GRAPH_HEADER` on a response only when `request.target_code` is in `_root_identifiers(report)`, which returns `report.solver.root_group_id` plus the exact `code` of every `solver.courses` entry whose `group_id` is that root. `_forward` stores a marked response with `AdmissionState.record_graph_cost` under the serving dataset identity and the request field, and `_response_headers` strips the marker from the client's headers.

The marker gate covers the root's canonical identity and the exact official codes of the root course alone. A request that sends another spelling, including a lowercase official code, has its graph resolved and answered but records no cost, so a read of that field is light. Each spelling keys its own field, so a canonical identity and an official code hold one recorded cost each. The browser stores the course's `group_id` as `rootCourseId` (`web/src/features/prerequisites/RootBox.tsx` and `web/src/shared/course/CourseMenu.tsx`) and sends it as `target_code` (`web/src/features/prerequisites/usePrerequisiteInputs.ts`), so its builds satisfy the gate. `AdmissionState.graph_cost` returns `None` for an identity other than the stored one, and `record_graph_cost` clears the map when the identity changes, so the cache holds one cost per target string and flag combination of one dataset.

`src/course_explorer_web/admission/policy.py` owns the arithmetic. `regime` maps the load position to headroom at 0, saturated at 1 and middle between. `light_load_factor` is `1 - (1 - ADMISSION_LIGHT_LOAD_FLOOR) * p`, `light_rate_per_millisecond` divides the scaled rate by 60000, and `light_concurrency` is `max(1, int(ADMISSION_LIGHT_CONCURRENCY * factor))`. `heavy_budget` interpolates the two budget values by `p`, `heavy_queue_limit` picks the regime's cap, and `heavy_slots` is `max(1, min(ceil(ADMISSION_HEAVY_SLOTS - (ADMISSION_HEAVY_SLOTS - 1) * p), WEB_WORKERS - 1))`. `light_balance` refills a light bucket at its rate and caps it at the burst, and `heavy_balance` refills a heavy bucket at `budget / (ADMISSION_WINDOW_SECONDS * 1000)` per millisecond and caps it at the budget.

`sample` adds one host busy interval, drops intervals older than the window, divides the window's core-seconds by the window length and the core count, refreshes the light and heavy activity and stores the score and `load_position`. `_apply_score` computes the score's position between the headroom and saturation lines and latches saturation at the saturation line until the score falls below the release line. `_refresh_activity` counts a light admission and a heavy start inside the window and adds a running heavy read whose start has left it. `_identity` starts a cookie's light bucket at `ADMISSION_LIGHT_BURST` and its heavy bucket at the larger of the two budget values.

`admit_light` raises `AdmissionRefused` when the cookie's concurrency is used or its balance is below one token. `admit_heavy` charges `min(cost, budget)`, refunds the charge when `_acquire_slot` refuses at the queue cap, and registers the start after it takes a slot. `_acquire_slot` waits on one `asyncio.Condition` in first-in-first-out order, holds a queued ticket in place when the cap drops, and admits the head of the queue when a slot is free. `release_heavy` drops the ticket and wakes every waiter, and `release_light` drops the ticket and the identity once it is stale and idle. `expire` drops every identity that is idle for `ADMISSION_IDENTITY_TTL_SECONDS` and holds no ticket, `reset_meter` clears the CPU baseline, the buckets, the counts, the latch and the position while it leaves the activity timestamps, and `graph_cost` and `record_graph_cost` own the dataset-scoped cache.

`src/course_explorer_web/admission/identity.py` holds `COOKIE_NAME`, `identify` and `set_cookie_value`. `busy_cpu_seconds` in `src/course_explorer_web/admission/host_cpu.py` reads the first eight numeric fields of `/proc/stat`, subtracts idle and iowait, and converts the ticks with `SC_CLK_TCK`, and `core_count` raises when the host reports none. `_too_much_traffic` builds the one refusal as a `JSONResponse` with `{"detail": "Too much traffic"}`, status 429 and `Retry-After`.

`WorkerPool.choose` in `src/course_explorer_web/router/workers.py` excludes a worker process that carries a heavy request from a heavy placement and picks the lowest in-flight count with the lowest index on a tie, and `occupy` holds the count for the duration of the forward. The router's `httpx.AsyncClient` sets `max_keepalive_connections=0`, so one forwarded request opens a fresh loopback connection, and a connection failure raises instead of retrying or rerouting.

To change a limit, change the key in `config/admission.toml` and its field on `AdmissionSettings`. To change a bound's arithmetic, change `policy.py`, and to add an activity term to the score, change `sample` and `_refresh_activity`. To add a class, change `AdmissionClass` and `classify`. `tests/web/test_admission.py` covers the class and cost of every route, one pinned point of each curve, the basis and scope choice, each scaled limit, the score's interpolation and latch, the heavy activity window, the queue and the dataset-scoped graph cache. `tests/web/test_router.py` covers the heavy placement, the light placement and the unreadable meter, as the test table under [Extending the server and its tests](#extending-the-server-and-its-tests) lists.

## Frontend registration

`register_frontend(application, *, dist_directory)` in `src/course_explorer_web/frontend.py` adds three fixed addresses:

- `add_api_route("/", frontend_document, methods=["GET"], include_in_schema=False)` and the same registration for `/docs`. The handler returns `FileResponse(dist_directory / "index.html", media_type="text/html")`, so both addresses serve one shell document.
- `mount("/assets", StaticFiles(directory=dist_directory / "assets", check_dir=False), name="frontend-assets")`, which serves the build's asset directory and does not require it to exist at construction.

No catch-all route is registered, so an unknown path returns 404 rather than the shell document.

`create_app` passes `frontend_directory or Path(__file__).resolve().parents[2] / "web" / "dist"`, so the default is the checkout's built browser application. The `frontend_directory` keyword is the test seam for a built tree under a temporary path.

## The launcher and the environment handoff

`main()` in `src/course_explorer_web/launch.py` restricts what the serving process inherits:

1. It loads `WebSettings()` and composes the five families every site needs through the automatic file sources: `load_raw_database_settings()`, `NormalizationSettings()`, `SearchSettings()`, the web settings it loaded, and `AdmissionSettings()`.
2. It adds `EmbeddingSettings()` to that set only when `WEB_EMBEDDINGS_ENABLED` is true, so a site with embedding features off composes no embedding family and needs no hub artifact.
3. It starts the child environment with only the inherited `HOME`, `PATH`, and `LANG`.
4. It iterates `type(settings).model_fields`, takes each `field.validation_alias` that is a string, unwraps a `SecretStr` with `get_secret_value()`, and writes `environment[alias] = configuration.environment_value(value)`.
5. It sets `SETTINGS_SOURCE_MARKER` to `ENVIRONMENT_ONLY_SETTINGS_SOURCE`, the value `environment`.
6. It calls `os.execve(sys.executable, [sys.executable, "-m", "course_explorer_web"], environment)`, so the server process takes the place of the launcher process.

`configuration.environment_value` renders a boolean as `1` or `0` and a list, tuple, or mapping as compact JSON. The two hub vectors travel as JSON arrays and are decoded by the child's process-environment source.

Three consequences follow from the handoff.

- The child reads no configuration file. `ConfiguredSettings.settings_customise_sources` returns only the constructor and process sources when the marker is set, so `read_public_configuration` and `read_local_configuration` are never called in the serving process.
- The child environment holds the aliases of those families, the environment-only marker, and any inherited `HOME`, `PATH`, and `LANG` values. The database, normalization, search, web, and admission values always travel. The embedding family travels in full when the site serves embedding features, because `EmbeddingSettings` extends the embedding runtime settings, so that child also receives the generation batch size, the chunk window and overlap, the request timeout and retry values, the pinned artifact identity, and the two hub vectors. A site with embedding features off receives no embedding alias at all. The worker connection family, the translation family, the inference family, and the remaining configuration families do not travel, and no unrelated inherited variable is kept.
- `EmbeddingSettings()` resolves both hub artifacts while the launcher runs on a site that serves embedding features, so the launcher reads the hub files and the child receives the vectors inline. Rewriting the hub files therefore takes effect at the next launch, and a serving process uses the vectors it started with.

`load_raw_database_settings()` returns the configured connection without resolving the selected-dataset pointer, so the serving process resolves the pointer itself on each settings read.

## The entry point

`main()` in `src/course_explorer_web/__main__.py` owns the sockets, the process tree and the serving generation:

1. It reads `load_web_settings()`.
2. It writes one fresh `secrets.token_hex(16)` to `os.environ["COURSE_EXPLORER_WEB_GENERATION"]`, overwriting any inherited value. Every child inherits the same value, so all worker processes of one supervisor report one identity for one generated database selection.
3. It binds the public listener on `(settings.web_host, settings.web_port)` with `SO_REUSEADDR`, `TCP_NODELAY` and `listen`, and binds `settings.web_workers` worker process listeners on `(settings.web_host, 0)` with the same options. The public listener accepts connections from the moment it binds, so a client that connects while the children start waits in the kernel backlog.
4. It spawns every worker child first, with the command `python -m course_explorer_web.worker <worker descriptor> <readiness descriptor>`. Each worker spawn creates one pipe, and the supervisor holds only that pipe's read end: it is nonblocking, and the parent closes its own copy of the write end when the child starts. Each child receives a copy of the process environment and its own descriptors alone.
5. A worker process writes one byte to its own pipe after Uvicorn has completed its startup and accepts connections on its listener. An empty read, a closed pipe and an exit are not readiness, so that spawn leaves the barrier closed. The supervisor releases that pipe and leaves the process to exit supervision.
6. It spawns the router child with the command `python -m course_explorer_web.router <public descriptor> <worker ports>` and the public descriptor alone, and it does so only when every worker process has a live child that reported readiness through its own spawn's pipe. A worker process replacement is a fresh spawn with a fresh pipe, so a predecessor's readiness never releases the barrier. Once started, the router's exits and replacements follow the same rules. A worker process that hangs during startup without exiting leaves the public listener accepting connections into the kernel backlog, while systemd reports the unit active and the supervisor logs no startup-hang failure.
7. It holds its own copies of the descriptors open for its whole life, so a replacement child serves the same listener.
8. It polls every 0.5 seconds. When a child exits, it logs one line naming the role and the exit code and starts a replacement for that role on the same descriptor, so no port changes and the other children continue serving. The replacement receives the same generation value. No request is replayed. Only the exited process's in-flight requests fail, and a replacement router starts with fresh admission state. The barrier covers initial startup alone, so a worker process that fails after the router started takes the ordinary replacement path.
9. When one role exits `WEB_RESPAWN_EXIT_LIMIT` times inside `WEB_RESPAWN_WINDOW_SECONDS`, it stops every child, waits 10 seconds, kills the rest, and returns that child's nonzero code, or 1 when the code is 0. A SIGTERM or SIGINT stops every child the same way and returns 0 with no replacement. A signal reaches the supervisor while the router has not started.

`main()` returns an integer and `raise SystemExit(main())` publishes it. systemd supervises the one supervisor process. `Restart=on-failure` restarts the unit when the supervisor returns nonzero, and the default `KillMode=control-group` ends the router and every worker process together.

A full restart of the unit ends the old supervisor, which closes the public listener, and the replacement process binds the port again, so a client that connects inside that window reaches no listener. A replacement child starts on a descriptor the supervisor already holds, so that descriptor keeps accepting across the replacement.

The router serves with a five-second graceful-shutdown bound. SIGTERM closes the listener and cancels an in-flight request after that bound, so the supervisor's terminate wait reaches a prompt exit and only that request fails.

The router child serves the public descriptor with `access_log=False`, and each worker process serves its own descriptor the same way, including its own startup report. A worker process listener binds `127.0.0.1` on port 0, so the kernel chooses its port. The port is never written to configuration, docs, logs or a report, and the router receives it on its command line at start. The public descriptor is the configured `WEB_HOST` and `WEB_PORT`, so the edge reaches one listener.

Importing `course_explorer_web.app`, a route module, the router module or the worker module creates no generation value, so construction and import are file-free and side-effect free. The generation is a handoff inside the serving process, created after the launcher's `execve`, not an operator setting in `config/web.toml` or the environment file and not part of the launcher's alias allowlist. A unit restart therefore creates a fresh generation, while a replacement child receives the value of the running supervisor. An idle tab is not notified of that change, and an in-place change to served data in either database mode reaches the browser on its next uncached read or reload after the restart.

`TCP_NODELAY` is set on every listener because uvicorn's inherited-socket path does not enable it through asyncio. `access_log=False` turns off the uvicorn access log.

`WebSettings` in `src/course_explorer/config.py` reads `WEB_HOST`, `WEB_PORT`, `WEB_WORKERS`, `WEB_RESPAWN_EXIT_LIMIT`, `WEB_RESPAWN_WINDOW_SECONDS`, `PREREQUISITE_GRAPH_MAX_ELEMENTS`, `WEB_EMBEDDINGS_ENABLED`, `WEB_INFERENCE_ENABLED`, `WEB_RETAINED_CACHE_AGGREGATE_BYTES`, `WEB_LOOKUP_PROJECTION_CACHE_BYTES`, `WEB_PREREQUISITE_SOURCE_CACHE_ENTRIES`, `WEB_PREREQUISITE_SOURCE_CACHE_ENTRY_BYTES`, `WEB_CHUNK_CACHE_ENTRIES` and `WEB_CHUNK_CACHE_ENTRY_BYTES` from `config/web.toml`. The host must be `127.0.0.1`, the port must be a valid TCP port, and the process count, the respawn limit and window, the drawing limit, the aggregate and each share must be greater than 0. The two switches are required booleans with no code default.

The example sets `127.0.0.1`, 8037, 4, 3, 60, 500, `true`, `true`, 1073741824, 33554432, 8000, 7006, 497 and 137794. `WEB_WORKERS` is the number of worker processes behind the one router. `WEB_RESPAWN_EXIT_LIMIT` is the number of exits of one role inside `WEB_RESPAWN_WINDOW_SECONDS` seconds that stops the unit instead of starting another replacement.

`AdmissionSettings` in the same file reads the `ADMISSION_*` keys of `config/admission.toml` and the shared `WEB_WORKERS` key of `config/web.toml`, so one TOML key is read by both families. Its `require_consistent_policy` validator refuses `ADMISSION_ENABLED` with `WEB_WORKERS` below two, because the heavy slots cap at one fewer than the worker processes and the remaining worker process carries non-heavy work. A configuration with admission off and one worker process is valid.

Every count, duration, rate, budget, slot, queue limit and curve knee must be positive, and so must the fixed inactive-search cost and the length of each measurement window. The light load floor is positive and at most one, the three score weights are finite and at least 0, and the three score thresholds are finite, with `ADMISSION_SCORE_HEADROOM` positive and at most `ADMISSION_SCORE_RELEASE`, which is below `ADMISSION_SCORE_SATURATION`. The origin bases, origin costs, slopes and tail costs are at least 0, and each knee basis is above its curve's origin basis. The example values are listed in [Configuration](/docs/backend/configuration.md#subsystem-keys).

## Extending the server and its tests

To add a read:

1. Add a module under `src/course_explorer_web/routes/` with one closed request model and one handler that resolves the serving dataset, delegates once with its connection and returns `dataset_report_response(report, serving)`.
2. Add the router to the tuple in `create_app`.
3. Add the path to the fixed route-set assertion in `tests/web/test_boundary.py`.
4. Keep the business behavior in the owning command module rather than in the route.

The reverse holds for a behavior change: the search, comparison, prerequisite, discovery, and structure commands own their rules, and the route module owns only the request shape.

| Test file | Covers |
|---|---|
| `tests/web/test_boundary.py` | The exact route set, the POST-only API surface, the two shell GETs, the `/assets` mount, and a subprocess import check that loads none of the administration, translation, ingestion-command, and embedding-command modules. |
| `tests/web/test_frontend.py` | `/` and `/docs` each returning the built shell document, one built asset served under `/assets`, and the absence of a source-file route and of an unknown-path fallback. |
| `tests/web/test_feature_switches.py` | The 403 refusal of both embedding reads on a site with embeddings off, one delegate for each switch-affected read with the site's switch applied to the requested value, and one serving identity reported by every cached read for the resolved raw or selected database. |
| `tests/web/test_usage.py` | One recorded line per request through the router and one real worker process across a feature read, a validation failure, a disabled-feature refusal, an unknown path, a method mismatch, the shell, a served asset, a missing asset, an unhandled failure and a limited refusal, with the route label, the hour rounding, the field shape and no sentinel from the request. |
| `tests/web/test_admission.py` | The class of every route, one pinned point of each cost curve, the basis and scope choice, one middle-regime value of each scaled limit with the saturation light concurrency and the heavy slot cap, the score's interpolation, saturation entry and release over controlled host samples and light admissions, the heavy activity window over one ticket lifecycle, the dataset-scoped graph cost cache in process memory, the heavy queue's wait at saturation and its refusal at the cap, and one router run of a free read, two limited cookies, a malformed cookie, a heavy budget refusal, admission off without a cookie and the activity its admitted reads leave. |
| `tests/web/test_router.py` | Three concurrent heavy requests on three distinct worker processes, a held worker process skipped by the next light request with the lowest index on a tie, and an unreadable host counter that logs one error, clears the CPU baseline, the score and the latch, counts the admitted activity on the next good sample and stores no pre-outage CPU. |
| `tests/web/test_serving_cache.py` | Two successive lookups of one serving identity return the same three retained cache instances, and a different identity replaces all three. |
| `tests/web/test_launcher.py` | The environment allowlist, the database password, web keys and the admission switch present in the child, the worker target and an unrelated secret absent, the marker value, the child families rebuilding with file reads forbidden, the embedding aliases absent on a site with embeddings off, the supervisor binding the configured public port with `TCP_NODELAY`, one worker child per `WEB_WORKERS` on distinct ephemeral loopback descriptors, the one generation value in every child environment, a worker process replacement on its own descriptor while the other children continue, the third exit of one role stopping the unit with its nonzero code, and the router held back while one worker process reports no readiness and its replacement then reporting readiness through a fresh pipe. |
| `tests/web/test_api.py` | The `course-summaries` route over a real normalized test catalogue, including the order of the input identities, a repeated identity, and the exact report JSON. |
| `tests/search/test_lookup_commands.py` | The catalogue command's minimal projection, the no-argument catalogue adapter, and the empty summary shortcut. |
