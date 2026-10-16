# Web server

The web package builds a fixed read-only application, hands it a restricted process environment, and serves it on one bound loopback socket.

## Application construction

`create_app(*, frontend_directory: Path | None = None)` in `src/course_explorer_web/app.py` builds the whole surface. It creates `FastAPI(docs_url=None, redoc_url=None, openapi_url=None)`, includes the ten route modules in a fixed tuple, registers the two exception handlers, registers the frontend, and returns the application. The module also binds `app = create_app()`, which is the import string the entry point serves.

Construction reads no settings, opens no database context, and contacts no provider. The routers read settings inside a handler alone, so importing `course_explorer_web.app` reads no configuration and opens no database.

## The route modules

Every handler delegates once and returns the command's report. `PrerequisitesRequest` lives in `src/course_explorer_web/routes/prerequisite_inputs.py` and is shared by the two prerequisite routes.

| Route | Module | Request model | Command | Report |
|---|---|---|---|---|
| `POST /api/search` | `routes/search.py` | `SearchRequest` | `course_explorer.search.commands.run_search_command` | `UnifiedSearchReport` |
| `POST /api/course-lookup` | `routes/course_lookup.py` | `CourseLookupRequest` | `course_explorer.search.lookup_commands.run_course_lookup_command` | `CourseLookupReport` |
| `POST /api/module-lookup` | `routes/module_lookup.py` | `ModuleLookupRequest` | `course_explorer.search.lookup_commands.run_module_lookup_command` | `ModuleLookupReport` |
| `POST /api/comparison` | `routes/comparison.py` | `ComparisonRequest` | `course_explorer.comparison.commands.run_course_comparison_command` | `CourseComparisonReport` |
| `POST /api/prerequisites` | `routes/prerequisites.py` | `PrerequisitesRequest` | `course_explorer.prerequisite.commands.run_prerequisite_command` | `PrerequisiteGraphReport` |
| `POST /api/minimum-route` | `routes/minimum_route.py` | `PrerequisitesRequest` | `course_explorer.prerequisite.commands.run_minimum_route_command` | `MinimumCreditPathEvaluation` |
| `POST /api/next-courses` | `routes/next_courses.py` | `NextCoursesRequest` | `course_explorer.next_courses.commands.run_next_courses_command` | `NextCoursesReport` |
| `POST /api/recommendations` | `routes/recommendations.py` | `RecommendationsRequest` | `course_explorer.recommendations.commands.run_recommendations_command` | `RecommendationsReport` |
| `POST /api/study-structure` | `routes/study_structure.py` | `StudyStructureRequest` | `course_explorer.study_structure.commands.run_study_structure_command` | `StudyStructureReport` |
| `POST /api/course-summaries` | `routes/course_summaries.py` | `CourseSummariesRequest` | `course_explorer.search.lookup_commands.run_course_summaries_command` | `CourseSummariesReport` |

Nine handlers call their command with `**request.model_dump()`. `POST /api/course-summaries` passes `request.identifiers` positionally. `POST /api/prerequisites` adds `max_drawing_elements=load_web_settings().prerequisite_graph_max_elements`, and `POST /api/minimum-route` passes no drawing limit.

Every handler is a synchronous `def`, so FastAPI runs it in a worker thread rather than on the event loop, and each request owns its own engine lifetime inside the command.

## Request models and defaults

Every request model sets `model_config = ConfigDict(extra="forbid")`, so a field the model does not declare fails the request.

| Model | Fields |
|---|---|
| `SearchRequest` | `query: str`, `display_language: DisplayLanguage`, `semantic_min_score: float \| None = None`, `fuzzy_min_score: float \| None = None`, `include_inactive: bool = True` |
| `CourseLookupRequest` | `query: str`, `display_language: DisplayLanguage`, `include_inactive: bool = True` |
| `ModuleLookupRequest` | `query: str`, `display_language: DisplayLanguage` |
| `ComparisonRequest` | `course_a: str`, `course_b: str` |
| `PrerequisitesRequest` | `target_code: str`, `completed_codes: tuple[str, ...] = ()`, `selected_codes: tuple[str, ...] = ()`, `excluded_codes: tuple[str, ...] = ()`, `include_recommended: bool = False`, `include_inferred: bool = False`, `active_only: bool = False`, `basis: str = "completed"`, `completed_node_keys: tuple[str, ...] = ()`, `excluded_node_keys: tuple[str, ...] = ()` |
| `NextCoursesRequest` | `selected_courses: tuple[str, ...] = ()`, `completed_courses: tuple[str, ...] = ()`, `basis: str = "completed"`, `mode: str = "all"`, `display_language: DisplayLanguage`, `include_inferred: bool = False`, `active_only: bool = True` |
| `RecommendationsRequest` | Same fields and defaults as `NextCoursesRequest` |
| `StudyStructureRequest` | `root_group_id: str` |
| `CourseSummariesRequest` | `identifiers: tuple[str, ...] = ()` |

`DisplayLanguage` is `Literal["fi", "en"]` in `src/course_explorer/search/lookup.py`. A `None` score override leaves the command to use the configured threshold. `basis`, `mode`, and the node keys are plain strings here and are validated by the command, so an unsupported value becomes the command's own `ValueError`.

The graph route reads `load_web_settings()` on each request rather than at construction, so the drawing limit comes from the values the serving process started with. A change to `PREREQUISITE_GRAPH_MAX_ELEMENTS` in `config/web.toml` reaches the drawing after the launcher starts the process again.

## Reports and error handlers

Each handler returns `Response(content=report.model_dump_json(), media_type="application/json")`, so the body is the command's own frozen report with no envelope and no status override.

`create_app` registers two handlers:

- `command_error` for `ValueError`. It re-raises when the exception is a `pydantic.ValidationError` and otherwise returns status 422 with `{"detail": str(exc)}`.
- `invalid_request` for `fastapi.exceptions.RequestValidationError`. It returns status 422 with the fixed `{"detail": "Invalid request"}` and echoes nothing from the body.

A `ValidationError` raised inside a command, and any other exception, are left to the server's default failure response, which carries status 500 and no report.

## Frontend registration

`register_frontend(application, *, dist_directory)` in `src/course_explorer_web/frontend.py` adds three fixed addresses:

- `add_api_route("/", frontend_document, methods=["GET"], include_in_schema=False)` and the same registration for `/docs`. The handler returns `FileResponse(dist_directory / "index.html", media_type="text/html")`, so both addresses serve one shell document.
- `mount("/assets", StaticFiles(directory=dist_directory / "assets", check_dir=False), name="frontend-assets")`, which serves the build's asset directory and does not require it to exist at construction.

No catch-all route is registered, so an unknown path returns 404 rather than the shell document.

`create_app` passes `frontend_directory or Path(__file__).resolve().parents[2] / "web" / "dist"`, so the default is the checkout's built browser application. The `frontend_directory` keyword is the test seam for a built tree under a temporary path.

## The launcher and the environment handoff

`main()` in `src/course_explorer_web/launch.py` restricts what the serving process inherits:

1. It composes five settings families through the automatic file sources: `load_raw_database_settings()`, `NormalizationSettings()`, `EmbeddingSettings()`, `SearchSettings()`, and `WebSettings()`.
2. It starts the child environment with only the inherited `HOME`, `PATH`, and `LANG`.
3. It iterates `type(settings).model_fields`, takes each `field.validation_alias` that is a string, unwraps a `SecretStr` with `get_secret_value()`, and writes `environment[alias] = configuration.environment_value(value)`.
4. It sets `SETTINGS_SOURCE_MARKER` to `ENVIRONMENT_ONLY_SETTINGS_SOURCE`, the value `environment`.
5. It calls `os.execve(sys.executable, [sys.executable, "-m", "course_explorer_web"], environment)`, so the server process takes the place of the launcher process.

`configuration.environment_value` renders a boolean as `1` or `0` and a list, tuple, or mapping as compact JSON. The two hub vectors travel as JSON arrays and are decoded by the child's process-environment source.

Three consequences follow from the handoff.

- The child reads no configuration file. `ConfiguredSettings.settings_customise_sources` returns only the constructor and process sources when the marker is set, so `read_public_configuration` and `read_local_configuration` are never called in the serving process.
- The child environment holds the aliases of those five families, the environment-only marker, and any inherited `HOME`, `PATH`, and `LANG` values. The database, normalization, search, and web values travel, and the embedding family travels in full, because `EmbeddingSettings` extends the embedding runtime settings. The child therefore also receives the generation batch size, the chunk window and overlap, the request timeout and retry values, the pinned artifact identity, and the two hub vectors. The worker connection family, the translation family, the inference family, and the remaining configuration families do not travel, and no unrelated inherited variable is kept.
- `EmbeddingSettings()` resolves both hub artifacts while the launcher runs, so the launcher reads the hub files and the child receives the vectors inline. Rewriting the hub files therefore takes effect at the next launch, and a serving process uses the vectors it started with.

`load_raw_database_settings()` returns the configured connection without resolving the selected-dataset pointer, so the serving process resolves the pointer itself on each settings read.

## The entry point

`main()` in `src/course_explorer_web/__main__.py` owns the socket and the process count:

1. It reads `load_web_settings()`.
2. It creates `socket.socket(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP)`, sets `SO_REUSEADDR` to 1 and `TCP_NODELAY` to 1, and binds `(settings.web_host, settings.web_port)`.
3. It calls `uvicorn.run("course_explorer_web.app:app", host=settings.web_host, port=settings.web_port, fd=listener.fileno(), workers=settings.web_workers, access_log=False)`.

The listener is passed to uvicorn by file descriptor, so the configured workers serve one bound loopback socket. `TCP_NODELAY` is set on the listener because uvicorn's inherited-socket path does not enable it through asyncio. `access_log=False` turns off the uvicorn access log.

`WebSettings` in `src/course_explorer/config.py` reads `WEB_HOST`, `WEB_PORT`, `WEB_WORKERS`, and `PREREQUISITE_GRAPH_MAX_ELEMENTS` from `config/web.toml`. The host must be `127.0.0.1`, the port must be a valid TCP port, and the process count and the drawing limit must be greater than 0. The example sets `127.0.0.1`, 8037, 2, and 500.

## Extending the server and its tests

To add a read:

1. Add a module under `src/course_explorer_web/routes/` with one closed request model and one handler that delegates once and returns `Response(report.model_dump_json(), media_type="application/json")`.
2. Add the router to the tuple in `create_app`.
3. Add the path to the fixed route-set assertion in `tests/web/test_boundary.py`.
4. Keep the business behavior in the owning command module rather than in the route.

The reverse holds for a behavior change: the search, comparison, prerequisite, discovery, and structure commands own their rules, and the route module owns only the request shape.

| Test file | Covers |
|---|---|
| `tests/web/test_boundary.py` | The exact route set, the POST-only API surface, the two shell GETs, the `/assets` mount, and a subprocess import check that loads none of the administration, translation, ingestion-command, and embedding-command modules. |
| `tests/web/test_frontend.py` | `/` and `/docs` each returning the built shell document, one built asset served under `/assets`, and the absence of a source-file route and of an unknown-path fallback. |
| `tests/web/test_launcher.py` | The environment allowlist, the database password and web keys present in the child, the worker target and an unrelated secret absent, the marker value, the child families rebuilding with file reads forbidden, and the entry point binding the configured loopback port with `TCP_NODELAY` set. |
| `tests/web/test_api.py` | The `course-summaries` route over a real normalized test catalogue, including the order of the input identities, a repeated identity, and the exact report JSON. |
| `tests/search/test_lookup_commands.py` | The API rejection of a blank lookup query as status 422 with the command's message. |
