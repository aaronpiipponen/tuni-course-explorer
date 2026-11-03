# Web supervisor

The supervisor validates the serving artifacts, resolves one settings bundle, builds the shared state, forks the worker processes and starts the front router.

## The launcher and the environment handoff

`main()` in `src/course_explorer_web/launch.py` restricts what the serving process inherits:

1. It loads `WebSettings()` and composes the seven families every site needs through the automatic file sources: `load_raw_database_settings()`, `NormalizationSettings()`, `SearchSettings()`, the web settings it loaded, `AdmissionSettings()`, `FeedbackSettings()` and `FeedbackIntakeSettings()`.
2. It adds `EmbeddingRuntimeSettings()` to that set only when `WEB_EMBEDDINGS_ENABLED` is true, so a site with embedding features off composes no embedding family. The artifact set supplies every site's catalogue and study fragments, and a site that serves the embedding features also takes its hub pair and packed search group count from it.
3. It starts the child environment with only the inherited `HOME`, `PATH`, and `LANG`, and it sets `PYTHONPATH` to the `src` directory that holds the loaded `course_explorer` package, so the child imports the package this launcher loaded rather than an installed one.
4. It iterates `type(settings).model_fields`, takes each `field.validation_alias` that is a string, unwraps a `SecretStr` with `get_secret_value()`, and writes `environment[alias] = configuration.environment_value(value)`.
5. It sets `SETTINGS_SOURCE_MARKER` to `ENVIRONMENT_ONLY_SETTINGS_SOURCE`, the value `environment`.
6. It sets `MALLOC_ARENA_MAX` from `WEB_MALLOC_ARENA_MAX`, so glibc reads the arena cap at the supervisor's process start and the router and forked workers inherit it.
7. It calls `os.execve(sys.executable, [sys.executable, "-m", "course_explorer_web"], environment)`, so the server process takes the place of the launcher process.

`configuration.environment_value` renders a boolean as `1` or `0` and a list, tuple, or mapping as compact JSON.

Two consequences follow from the handoff.

- The child reads no settings file or environment file. `ConfiguredSettings.settings_customise_sources` returns only the constructor and process sources when the marker is set, so `read_public_configuration` and `read_local_configuration` are never called in the serving process. A feedback request reads `config/feedback-form.json` through the feedback service, because that file is the feedback definition rather than a settings source.
- The child environment holds the aliases of those families, the environment-only marker, `MALLOC_ARENA_MAX`, `PYTHONPATH` with the `src` directory that holds the loaded package, and any inherited `HOME`, `PATH`, and `LANG` values. The database, normalization, search, web, admission and feedback connection and intake values always travel. The embedding runtime family travels when the site serves embedding features, so that child receives the generation batch size, the chunk window and overlap, the request timeout and retry values, and the pinned artifact identity. A site with embedding features off receives no embedding alias at all. The worker connection family, the translation family, the inference family, the remaining configuration families, and any `FEEDBACK_GITHUB_TOKEN`, administration key or worker key do not travel, and no unrelated inherited variable is kept.

`load_raw_database_settings()` returns the configured connection without resolving a dataset pointer. The supervisor resolves the Selected dataset once before it forks its workers, and no worker resolves the pointer for a request.

## Startup and validation

`main()` in `src/course_explorer_web/__main__.py` owns the serving settings bundle, the preloaded artifact set, the lookup projection, the shared cache regions, the sockets, the process tree and the serving generation:

1. It writes one fresh `secrets.token_hex(16)` to `os.environ["COURSE_EXPLORER_WEB_GENERATION"]`, overwriting any inherited value. Every child inherits the same value, so all worker processes of one supervisor report one identity for one generated database selection. [Serving state](/docs/backend/interfaces/serving-state.md#the-serving-dataset-identity) describes the identity that value produces.
2. It reads `load_web_settings()`.
3. It resolves the serving dataset, resolves the site's embedding configuration once through `embedding_configuration_for_site` from the web settings it loaded, creates the one `httpx.Client` the workers share for query embeddings only when that configuration exists, and stores one `ServingSettings` bundle that every worker route reads. It then opens the artifact set once through `preload_serving_artifacts()`, which appends the serving identity to the catalogue artifact and compresses that body. On a site that serves the embedding features the bundle derives the embedding configuration identity from the resolved configuration. An opening failure stops startup before any listener is bound.
4. It opens the dataset connection, builds the lookup projection through `build_lookup_projection` and disposes the engine before any child starts. It then creates the next-course report region and, when the site serves embedding features, the query-embedding region. The fork is single-threaded because this runs before signal handlers, listeners or threads exist. A projection or region failure stops startup.
5. It binds the public listener on `(settings.web_host, settings.web_port)` with `SO_REUSEADDR`, `TCP_NODELAY` and `listen`, and binds `settings.web_workers` worker listeners on `(settings.web_host, 0)` with the same options. The public listener accepts connections from the moment it binds, so a client that connects while the children start waits in the kernel backlog.

The bundle it stores holds the web settings, the search settings, the resolved embedding configuration or `None` on a site without embedding features, the configured academic year start, the resolved serving dataset, the embedding configuration identity and the shared query-embedding client. A route reads a member of that bundle instead of loading a family, hashing a configuration or resolving the pointer itself.

On a site that serves the embedding features the identity is derived from the resolved configuration on its first read and cached for the process lifetime, so every search, comparison and recommendation request of the supervisor reports under it and a worker request does not hash the embedding settings again. The client uses the embedding base address and `SEARCH_EMBEDDING_REQUEST_TIMEOUT_SECONDS`, belongs to the supervisor, and is closed when the supervisor stops. A site with the features off holds `None` for the embedding configuration, the identity and the client.

The preloaded artifact set shares the supervisor's lifetime. An opened build and its embedding directory fix the files they hold, so a completed artifact build reaches a served site only through a restarted supervisor, and that restart is the one an artifact build needs. [Operations](/docs/operations/README.md#derived-files-served-data-and-the-web-restart) owns that restart procedure.

## The fork, the readiness barrier and replacement

6. It forks every worker from the preloaded supervisor with `_fork_worker`. Each worker inherits its listener, its own readiness pipe, the read-only lookup projection and the shared cache regions, closes the other roles' listeners and readiness pipes, and calls `worker.main(listener_fd=..., readiness_fd=...)`.
7. A worker writes one byte to its own pipe after Uvicorn has completed startup and accepts connections on its listener. An empty read, a closed pipe and an exit are not readiness, so that fork leaves the barrier closed. The supervisor releases that pipe and leaves the worker to exit supervision.
8. It spawns the router child with `python -m course_explorer_web.router <public descriptor> <worker ports>` and the public descriptor alone, and it does so only when every worker has a live child that reported readiness through its own pipe. A worker replacement is a fresh fork with a fresh pipe, so a predecessor's readiness never releases the barrier. Once started, the router's exits and replacements follow the same rules.
9. It holds its own copies of the descriptors open for its whole life, so a replacement child serves the same listener.
10. It polls every 0.5 seconds. It reaps worker exits with `os.waitpid` and router exits through the subprocess, logs one line naming the role and the exit code, and starts a replacement for that role on the same descriptor, so no port changes and the other children continue serving. A worker replacement is another fork from the same supervisor and inherits the same settings bundle, read-only projection and shared cache regions. The replacement receives the same generation value. A dataset identity change replaces the whole supervisor, not one worker. No request is replayed. Only the exited process's in-flight requests fail, and a replacement router starts with fresh admission state. The barrier covers initial startup alone, so a worker that fails after the router started takes the ordinary replacement path.
11. When one role exits `WEB_RESPAWN_EXIT_LIMIT` times inside `WEB_RESPAWN_WINDOW_SECONDS`, it stops every child, waits `TERMINATE_SECONDS` (10 seconds), kills the rest, and returns that child's nonzero code, or 1 when the code is 0. A SIGTERM or SIGINT stops every child the same way and returns 0 with no replacement. A signal reaches the supervisor while the router has not started.

`main()` returns an integer and `raise SystemExit(main())` publishes it. systemd supervises the one supervisor process. `Restart=on-failure` restarts the unit when the supervisor returns nonzero, and the default `KillMode=control-group` ends the router and every worker process together.

The router child resolves the serving dataset once in its own `startup` and holds it for the life of the process, so its admission decisions and its graph cost cache describe one dataset identity. A router that resolves no generation value fails its startup.

## Sockets, shutdown and import

A full restart of the unit ends the old supervisor, which closes the public listener, and the replacement process binds the port again, so a client that connects inside that window reaches no listener. A replacement child starts on a descriptor the supervisor already holds, so that descriptor continues to accept across the replacement.

The router serves with a five-second graceful-shutdown bound. SIGTERM closes the listener and cancels an in-flight request after that bound, so the supervisor's terminate wait reaches a prompt exit and only that request fails.

The router child serves the public descriptor with `access_log=False`, and each worker process serves its own descriptor the same way, including its own startup report. A worker process listener binds `127.0.0.1` on port 0, so the kernel chooses its port. The port is never written to configuration, docs, logs or a report, and the router receives it on its command line at start. The public descriptor is the configured `WEB_HOST` and `WEB_PORT`, so the edge reaches one listener.

Importing `course_explorer_web.app`, a route module, the router module or the worker module creates no generation value, so construction and import are settings-file-free and side-effect free. The generation is a handoff inside the serving process, created after the launcher's `execve`, not an operator setting in `config/web.toml` or the environment file and not part of the launcher's alias allowlist. A unit restart therefore creates a fresh generation, while a replacement child receives the value of the running supervisor. An idle tab is not notified of that change, and an in-place change to served data in either database mode reaches the browser on its next uncached read or reload after the restart.

`TCP_NODELAY` is set on every listener because uvicorn's inherited-socket path does not enable it through asyncio. `access_log=False` turns off the uvicorn access log.

## The settings the supervisor reads

`WebSettings` in `src/course_explorer/config.py` reads `WEB_HOST`, `WEB_PORT`, `WEB_WORKERS`, `WEB_MALLOC_ARENA_MAX`, `WEB_RESPAWN_EXIT_LIMIT`, `WEB_RESPAWN_WINDOW_SECONDS`, `PREREQUISITE_GRAPH_MAX_ELEMENTS`, `WEB_EMBEDDINGS_ENABLED`, `WEB_INFERENCE_ENABLED`, `WEB_NEXT_COURSE_REPORT_CACHE_BYTES`, `WEB_QUERY_EMBEDDING_CACHE_BYTES` and the four `WEB_REQUEST_*` bounds from `config/web.toml`. The host must be `127.0.0.1`, the port must be a valid TCP port, and the process count, the malloc arena count, the respawn limit and window, the drawing limit, each region and each request bound must be greater than 0. The two switches are required booleans with no code default.

The example sets `127.0.0.1`, 8037, 4, 2, 3, 60, 500, `true`, `true`, 100663296 and 50331648. `WEB_WORKERS` is the number of worker processes behind the one router. `WEB_MALLOC_ARENA_MAX` is the glibc malloc arenas per web process, which the launcher passes as `MALLOC_ARENA_MAX`. `WEB_RESPAWN_EXIT_LIMIT` is the number of exits of one role inside `WEB_RESPAWN_WINDOW_SECONDS` seconds that stops the unit instead of starting another replacement.

`AdmissionSettings` in the same file reads the `ADMISSION_*` keys of `config/admission.toml` and the shared `WEB_WORKERS` key of `config/web.toml`, so one TOML key is read by both families. Its `require_consistent_policy` validator refuses `ADMISSION_ENABLED` with `WEB_WORKERS` below two, because the heavy slots cap at one fewer than the worker processes and the remaining worker process carries non-heavy work. A configuration with admission off and one worker process is valid.

Every admission count, duration, rate, budget, slot, queue limit and curve knee must be positive, and so must the fixed inactive-search cost and the length of each measurement window. The light load floor is positive and at most one, the three score weights are finite and at least 0, and the three score thresholds are finite, with `ADMISSION_SCORE_HEADROOM` positive and at most `ADMISSION_SCORE_RELEASE`, which is below `ADMISSION_SCORE_SATURATION`. The origin bases, origin costs, slopes and tail costs are at least 0, and each knee basis is above its curve's origin basis. The example values are listed in [Configuration](/docs/backend/configuration.md#subsystem-keys).

## Tests

| Test file | Covers |
|---|---|
| `tests/web/test_launcher.py` | The environment allowlist, the database password, web keys, the admission switch and both feedback families present in the child, the worker target, a synthetic feedback token and an unrelated secret absent, the marker value, the child families rebuilding with file reads forbidden, the embedding aliases absent on a site with embeddings off, the supervisor binding the configured public port with `TCP_NODELAY`, one worker child per `WEB_WORKERS` on distinct ephemeral loopback descriptors, the one generation value in every child environment, and a real four-worker supervisor on an embeddings-off build that holds the catalogue and the study fragments alone, with real router and disposable database: a search response through the router, one worker killed, a replacement forked on the same descriptor and the identical response after the replacement. |
