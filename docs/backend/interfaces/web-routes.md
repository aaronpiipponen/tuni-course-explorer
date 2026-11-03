# Web routes

The web package builds the feature application, its closed request models and its error handlers, and serves the built browser application from one worker process.

## Application construction

`create_app(*, frontend_directory: Path | None = None)` in `src/course_explorer_web/app.py` builds the whole surface. It creates `FastAPI(docs_url=None, redoc_url=None, openapi_url=None)`, includes the nine catalogue route modules and the feedback module in a fixed tuple, registers the two exception handlers, registers the frontend, adds `GZipMiddleware(minimum_size=500, compresslevel=6)`, and returns the application. The module also binds `app = create_app()`, which is the import string a worker process serves.

The compression measurement supports level 6 as the size and CPU compromise, as [Response compression levels](/docs/experiments/runtime-storage-and-serving/response-compression.md) records.

Construction reads no settings, opens no database context, creates no file, and contacts no provider. The routers read settings inside a handler alone, so importing `course_explorer_web.app` reads no configuration and opens no database. The feedback definition read and submission are synchronous handlers like the catalogue handlers, so a worker process runs them in a thread rather than on the event loop.

## The route modules

Every dataset command handler resolves one serving dataset and delegates once with that connection. All but the catalogue handler return the command's report through the one serializer that appends the connection's identity. `POST /api/features` is the second exception, because it resolves no connection and runs no command.

The catalogue handler serves the inherited identity-appended plain body, or the gzip form compressed from it, so its field order and bytes do not change and the report is never rebuilt. The supervisor builds both bodies once before it forks its workers, and the build directory holds the plain artifact alone. The gzip middleware compresses a response of at least 500 bytes when the request names gzip, and the router forwards the encoded bytes. The front router records the usage line, so a worker process appends none. The two catalogue answers and their `Vary` header are described under [serving state](/docs/backend/interfaces/serving-state.md#the-catalogue-artifact).

`POST /api/features` runs no command, because it projects two settings of `WebSettings` and the resolved dataset identity. `src/course_explorer_web/routes/prerequisite_inputs.py` holds `PrerequisiteGraphRequest` for the graph route.

| Route | Module | Request model | Command | Report |
|---|---|---|---|---|
| `POST /api/search` | `routes/search.py` | `SearchRequest` | `course_explorer.search.commands.run_search_command` | `UnifiedSearchReport` plus `dataset_identity` |
| `POST /api/catalogue` | `routes/catalogue.py` | `CatalogueRequest` | The current build's retained catalogue artifact | `CatalogueReport` plus `dataset_identity` |
| `POST /api/comparison` | `routes/comparison.py` | `ComparisonRequest` | `course_explorer.comparison.commands.run_course_comparison_command` | `CourseComparisonReport` plus `dataset_identity` |
| `POST /api/prerequisites` | `routes/prerequisites.py` | `PrerequisiteGraphRequest` | `course_explorer.prerequisite.commands.run_prerequisite_command` | `PrerequisiteGraphReport` plus `dataset_identity` and `max_compact_nodes` |
| `POST /api/next-courses` | `routes/next_courses.py` | `NextCoursesRequest` | `course_explorer.next_courses.commands.run_next_courses_command` | `NextCoursesReport` plus `dataset_identity` |
| `POST /api/recommendations` | `routes/recommendations.py` | `RecommendationsRequest` | `course_explorer.recommendations.commands.run_recommendations_command` | `RecommendationsReport` plus `dataset_identity` |
| `POST /api/study-structure` | `routes/study_structure.py` | `StudyStructureRequest` | `course_explorer.study_structure.commands.run_study_structures_command` | `StudyStructuresReport` plus `dataset_identity` |
| `POST /api/course-summaries` | `routes/course_summaries.py` | `CourseSummariesRequest` | `course_explorer.search.lookup_commands.run_course_summaries_command` | `CourseSummariesReport` plus `dataset_identity` |
| `POST /api/features` | `routes/features.py` | `FeaturesRequest` | None | `WebFeaturesReport` |
| `GET /api/feedback/definition` | `routes/feedback.py` | None | None | `FeedbackFormReport` |
| `POST /api/feedback` | `routes/feedback.py` | `FeedbackSubmissionRequest` | `FeedbackService.submit` | `FeedbackAcknowledgment` |

`routes/feedback.py` holds the two feedback handlers. `definition()` loads `FeedbackIntakeSettings` and `config/feedback-form.json` and returns the feedback definition with the configured repository, visibility and body bound. Neither handler resolves a serving dataset, and the feedback definition read opens no connection to the feedback application store. `submit()` decodes each `FeedbackUploadRequest.content_base64` as standard base64, builds `AttachmentUpload` values from its field, filename and bytes, and calls `feedback_context()` once, so the owning service holds the only answer, filename, upload and image validation. A committed submission returns status 201 with `FeedbackAcknowledgment`, which carries `accepted` and the state derived from the committed publication choice of the stored submission. Both answers are non-cacheable, and a failure answer names only a fixed detail or the exception class.

Two handlers pass their dumped request to the command: `POST /api/search` adds the site's semantic switch as `include_semantic`, and `POST /api/comparison` passes the dump as it is. `POST /api/catalogue` passes no input. `POST /api/course-summaries` passes `request.identifiers` positionally, and `POST /api/study-structure` passes `request.root_group_ids` positionally with `allow_unavailable` and the request's `module_versions` map.

Three handlers build one dumped dictionary and replace its `include_inferred` with the requested value combined with the site's inference switch: `POST /api/prerequisites`, `POST /api/next-courses` and `POST /api/recommendations`.

Every dataset command handler passes the resolved connection as `database_settings`, and `POST /api/prerequisites` adds `max_drawing_elements=settings.prerequisite_graph_max_elements` from the preloaded bundle.

The command handlers pass `session_factory=cache.database.factory()`, so the command reads through the serving engine instead of opening and disposing its own engine. The catalogue handler runs no command, so it passes no factory and returns the retained body. `scripts/search.py` wraps its one command call in `database_context` and passes that factory, so one search reads through one short-lived engine. Every other CLI adapter passes no factory, so its command opens and disposes its own engine for that one call.

Every dataset command handler also passes retained state. `POST /api/search` passes `projection=preloaded_lookup_projection()`, and `POST /api/catalogue` returns `cache.catalogue_body` or `cache.catalogue_gzip`.

`POST /api/prerequisites`, `POST /api/course-summaries` and `POST /api/next-courses` pass `projection=preloaded_lookup_projection()`, and the next-course handler adds `report_cache=cache.next_course_reports`. On a site that serves the embedding features, `POST /api/search`, `POST /api/comparison` and `POST /api/recommendations` call `cache.artifacts.embedding_reads()` and pass that build's reads, where `cache = serving_caches(serving)` for that request's resolved dataset.

The search handler passes the catalogue hub, the packed search group count and the shared query-embedding cache. The comparison handler passes both hubs, the embedding configuration identity of the preloaded bundle, the preloaded projection and the serving session factory. The recommendation handler passes both hubs, the shared store, `next_course_cache=cache.next_course_reports`, `centroid_cache=cache.course_centroids` and the same projection. A search on a site with the features off passes no hub and no group count. `POST /api/study-structure` passes `fragment_store=cache.artifacts.study_fragments`.

The prerequisite and next-course commands read their facts through the process's own native database handle in `src/course_explorer/prerequisite/native_handle.py`. One handle per worker holds the libpq connection and the canonical course, version, module, rule, inferred-set and equivalence facts of the request closure, and a repeated request issues no query. [Serving state](/docs/backend/interfaces/serving-state.md) describes each retained facility.

Five handlers apply the site's feature switches to the call they make. `POST /api/search` adds `include_semantic=settings.embeddings_enabled` to the command call. `POST /api/comparison` and `POST /api/recommendations` raise `HTTPException(status_code=403, detail="Feature disabled")` when embeddings are off, before the command runs. `POST /api/prerequisites`, `POST /api/next-courses`, and `POST /api/recommendations` replace the dumped `include_inferred` with the requested value combined with the site's inference switch.

Every handler is a synchronous `def`, so FastAPI runs it in a thread rather than on the event loop. A dataset command request reads through the serving engine that its dataset identity holds, and it resolves its serving connection once, so the report it receives and the identity it publishes describe one database.

## Request models and their bounds

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
| `FeedbackUploadRequest` | `field_id: StrictStr`, `filename: StrictStr`, `content_base64: StrictStr`, all excluded from the rendered form |
| `FeedbackSubmissionRequest` | `answers: dict[str, StrictStr \| None]`, `attachments: tuple[FeedbackUploadRequest, ...]`, `public_issue: StrictBool`, all required and excluded from the rendered form |

`DisplayLanguage` is `Literal["fi", "en"]` in `src/course_explorer/search/lookup.py`. A `None` score override leaves the command to use the configured threshold. `basis` and `mode` are plain strings here and are validated by the command, so an unsupported value becomes the command's own `ValueError`.

`SearchRequest.include_inactive` and the `active_only` field of `NextCoursesRequest` and `RecommendationsRequest` take their defaults from `INCLUDE_INACTIVE_DEFAULT` and `ACTIVE_ONLY_DEFAULT` in `src/course_explorer_web/serving.py`. The classifier reads the same two values, so the request model and the admission pricing share one default.

### The input bounds

`BoundedRequest` in `src/course_explorer_web/request_limits.py` is the base of every catalogue request model except `CatalogueRequest` and `FeaturesRequest`. Its after-validator reads the supervisor's `WebSettings` through `preloaded_serving_settings()` and refuses an input past a configured bound, so one validated configuration owns every count and length. Four keys of `config/web.toml` set them.

| Key | Field it bounds |
|---|---|
| `WEB_REQUEST_MAX_COURSE_ITEMS` | The identities in one course list, and the entries of one `module_versions` map |
| `WEB_REQUEST_MAX_IDENTIFIER_LENGTH` | Characters of one identity, official code, map key or module-version value |
| `WEB_REQUEST_MAX_QUERY_LENGTH` | Characters of one search query text |
| `WEB_REQUEST_BODY_MAX_BYTES` | Bytes of one request body the front router reads |

[Configuration](/docs/backend/configuration.md#subsystem-keys) states the configured values.

`WEB_REQUEST_MAX_COURSE_ITEMS` counts each declared course list of a model, so a request with two lists may carry that many identities in each. The model declares its list fields, its single-identifier fields, its identifier maps and its query text, and the one validator checks each declared field with its own rule. A `BoundedRequest` subclass with no declaration is checked by no bound.

The example body bound leaves about 9 KB above the largest legitimate body, which the comments of `config/web.toml` describe as a study-structure request with every input at its bound.

A bound produces one of two answers at two different layers. A body that exceeds `WEB_REQUEST_BODY_MAX_BYTES` is refused by the front router, before any worker process or admission decision, with status 413 and the fixed body `{"detail": "Request body refused"}`, and a client that disconnects inside that bounded read answers 400. An input over its count or length bound raises inside the request model's validator, so the request reaches the route as an invalid request and answers status 422 with the fixed body `{"detail": "Invalid request"}`. The validator raises `request_limits.py`'s own message for the crossed bound. That message is carried inside the `ValidationError` the request model raises, and the invalid-request handler answers the fixed body without echoing any validator text.

The graph route reads the drawing limit from the preloaded web settings and the allocation limit from the preloaded search settings, so both come from the values the supervisor resolved before it forked the workers. Every other route that applies a site switch reads the same preloaded bundle. A change to `PREREQUISITE_GRAPH_MAX_ELEMENTS`, `WEB_EMBEDDINGS_ENABLED` or `WEB_INFERENCE_ENABLED` in `config/web.toml`, to `PREREQUISITE_PATH_MAX_COMPACT_NODES` in `config/search.toml`, or to one of the four `WEB_REQUEST_*` keys reaches the server after the launcher starts the process again.

## Reports and error handlers

Each dataset handler returns `dataset_report_response(report, serving, **metadata)` from `src/course_explorer_web/reports.py`. The serializer writes the command report in JSON mode and adds the top-level `dataset_identity` of the connection the handler resolved, plus any web-only metadata the route supplies. The graph route adds `max_compact_nodes`, because the limit belongs to the served site's policy rather than to the machine report. No machine report acquires a serving identity, and no connection or receipt field leaves the server.

`create_app` registers two handlers:

- `command_error` for `ValueError`. It re-raises when the exception is a `pydantic.ValidationError` and otherwise returns status 422 with `{"detail": str(exc)}`.
- `invalid_request` for `fastapi.exceptions.RequestValidationError`. It returns status 422 with the fixed `{"detail": "Invalid request"}` and echoes nothing from the body. The two feedback paths add `Cache-Control: no-store` to that answer, and every other route returns that same answer.

A `ValidationError` raised inside a command, and any other exception, are left to the server's default failure response, which carries status 500 and no report.

## Frontend registration

`register_frontend(application, *, dist_directory)` in `src/course_explorer_web/frontend.py` adds the shell documents and one mounted asset directory:

- `add_api_route` for `/`, `/docs` and `/feedback` with `methods=["GET"]` and `include_in_schema=False`. Each returns `FileResponse(dist_directory / "index.html", media_type="text/html", headers={"Cache-Control": "no-cache"})`, so the three addresses serve one shell document that a browser revalidates after a rebuild.
- `mount("/assets", ImmutableAssetFiles(directory=dist_directory / "assets", check_dir=False), name="frontend-assets")`, which serves the build's asset directory and does not require it to exist at construction.

`ImmutableAssetFiles` overrides `file_response`. Every answer carries `Cache-Control: public, max-age=31536000, immutable`, because a build asset name contains its content hash. An `Accept-Encoding` that admits `br` or `gzip` receives the file of the same name with that suffix when the build wrote one, with the plain file's content type, `Content-Encoding` and `Vary: Accept-Encoding`. A request that admits neither, and an asset whose variant is absent, receives the plain file. The build writes a `.br` and a `.gz` variant beside every `.js`, `.mjs`, `.css`, `.html`, `.json` and `.svg` file through `web/tools/compress.mjs`, which covers the PDF.js worker module, and `GZipMiddleware` leaves a response that already carries `Content-Encoding` alone.

`accepts_encoding` in `src/course_explorer_web/accept_encoding.py` decides the two route-level precompressed choices: an asset variant and the catalogue body answer an encoding only when the request admits it with a positive weight, and a malformed weight makes that coding unacceptable. `GZipMiddleware` compresses every other response of at least 500 bytes by its own rule, which tests the header for the coding's name alone, so a request that sets gzip to zero weight receives the middleware's compressed plain catalogue body.

No catch-all route is registered, so an unknown path returns 404 rather than the shell document.

`create_app` passes `frontend_directory or Path(__file__).resolve().parents[2] / "web" / "dist"`, so the default is the checkout's built browser application. The `frontend_directory` keyword is the test seam for a built tree under a temporary path.

## Extending the surface and its tests

To add a read:

1. Add a module under `src/course_explorer_web/routes/` with one closed request model and one handler that resolves the serving dataset, delegates once with its connection and returns `dataset_report_response(report, serving)`.
2. Add the router to the tuple in `create_app`.
3. Add the path to the fixed route-set assertion in `tests/web/test_boundary.py`.
4. Keep the business behavior in the owning command module rather than in the route.

The reverse holds for a behavior change: the search, comparison, prerequisite, discovery, and structure commands own their rules, and the route module owns only the request shape. The two feedback paths sit outside `serving.Route`, the classifier and the catalogue admission budgets. Their site, size and hourly policy lives in the front router alone.

| Test file | Covers |
|---|---|
| `tests/web/test_boundary.py` | The exact route set, the fixed API methods including the feedback definition and submission, the three shell GETs, the `/assets` mount, and a subprocess import check that loads none of the administration, translation, ingestion-command, and embedding-command modules. |
| `tests/web/test_frontend.py` | `/`, `/docs` and `/feedback` each returning the built shell document with `Cache-Control: no-cache`, one built asset with immutable caching, its `.gz` and `.br` variants, the absence of a source-file route and of an unknown-path fallback. |
| `tests/web/test_feature_switches.py` | The 403 refusal of both embedding reads on a site with embeddings off, the catalogue answer from the opened set with no embedding read and no centroid cache, one delegate for each switch-affected read with the site's switch applied to the requested value, `test_graph_read_marks_the_root_id_and_its_official_code_for_measurement` for the graph read marked under the root's canonical identity or exact official code and not under another spelling, one serving identity reported by every cached read for the resolved raw or selected database, the preloaded lookup projection on the six routes that read it, the next-courses report cache, and the study-structure academic year and fragment store. |
| `tests/web/test_api.py` | The `course-summaries` route over a real normalized test catalogue, including the order of the input identities, a repeated identity, and the exact report JSON. |
| `tests/web/test_request_bounds.py` | `test_feature_routes_refuse_inputs_over_the_configured_bounds`: `POST /api/course-summaries` answers 422 for an identifier list one entry over `WEB_REQUEST_MAX_COURSE_ITEMS` and for one identifier one character over `WEB_REQUEST_MAX_IDENTIFIER_LENGTH`, and `POST /api/search` answers 422 for a query one character over `WEB_REQUEST_MAX_QUERY_LENGTH`. |
| `tests/web/test_router.py` | `test_router_refuses_an_oversized_body_without_forwarding`: a body one byte over `WEB_REQUEST_BODY_MAX_BYTES` answers 413 with the fixed detail before any worker process is called. |
| `tests/search/test_lookup_commands.py` | The catalogue command's minimal projection, the no-argument catalogue adapter, and the empty summary shortcut. |
