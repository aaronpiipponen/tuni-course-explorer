# Invariants and their enforcement

This page records the invariants the TUNI Course Explorer code enforces, naming the module that owns each rule and the tests that cover it where a test exists.

The table indexes every invariant with its owner module and its test file. The one invariant without a test is held by the shape of the code it names. Each section below states the rule in full with every enforcer and every covering test.

| Invariant | Owner | Test file |
|---|---|---|
| [Official and inferred prerequisites are stored apart](#official-and-inferred-prerequisites-are-stored-apart) | `src/course_explorer/ingestion/normalization_repository.py` | `tests/prerequisite/test_inferred_prerequisite_repository.py` |
| [Only teaching text is embedded](#only-teaching-text-is-embedded) | `src/course_explorer/embeddings/generation.py` | `tests/embeddings/test_course_embedding_generation.py` |
| [Prerequisite expressions keep AND and OR semantics and canonical identity](#prerequisite-expressions-keep-and-and-or-semantics-and-canonical-identity) | `src/course_explorer/prerequisite/domain.py` | `tests/prerequisite/test_prerequisite_domain.py` |
| [The minimum route minimizes new credits and counts each course once](#the-minimum-route-minimizes-new-credits-and-counts-each-course-once) | `web/src/solver/route.ts` | `web/src/solver/route-minimum.test.ts`, `web/src/solver/route-contracts.test.ts` |
| [Schema changes go through Alembic migrations](#schema-changes-go-through-alembic-migrations) | `migrations/versions/` | `tests/db/test_database_schema.py` |
| [Only the current schema and format are read](#only-the-current-schema-and-format-are-read) | `src/course_explorer/administration.py` | `tests/administration/test_administration.py` |
| [Inference reads no official prerequisite structure](#inference-reads-no-official-prerequisite-structure) | `src/course_explorer/inference/context.py` | `tests/inference/test_inference_context.py` |
| [Model output is validated before use and failures are recorded](#model-output-is-validated-before-use-and-failures-are-recorded) | `src/course_explorer/inference/domain.py` | `tests/inference/test_inference_target_pass.py` |
| [A broad or transitive foundation is suppressed from the direct options](#a-broad-or-transitive-foundation-is-suppressed-from-the-direct-options) | `src/course_explorer/inference/proposals.py` | `tests/inference/test_inference_proposals.py` |
| [Stages resume from a checkpoint and process pending, failed, or changed work only](#stages-resume-from-a-checkpoint-and-process-pending-failed-or-changed-work-only) | `src/course_explorer_admin/lifecycle.py` | `tests/admin/test_lifecycle.py` |
| [Every stage exposes one lifecycle](#every-stage-exposes-one-lifecycle) | `src/course_explorer_admin/cli.py` | `tests/admin/test_lifecycle.py`, `tests/admin/test_remote_lifecycle.py` |
| [Adapters hold no business logic](#adapters-hold-no-business-logic) | `scripts/` | No test file |
| [The course-exploration web server never mutates authoritative data, starts a stage, or reaches the worker](#the-course-exploration-web-server-never-mutates-authoritative-data-starts-a-stage-or-reaches-the-worker) | `src/course_explorer_web/app.py`, `src/course_explorer_web/admission/` | `tests/web/test_boundary.py`, `tests/web/test_feature_switches.py`, `tests/web/test_usage.py`, `tests/web/test_admission.py` |
| [Credentials live outside tracked files](#credentials-live-outside-tracked-files) | `src/course_explorer/config.py` | `tests/config/test_configuration_sources.py`, `tests/web/test_launcher.py`, `tests/admin/test_operator_commands.py` |
| [The administration backend checks the lock, exact site, session and CSRF token before every route](#the-administration-backend-checks-the-lock-exact-site-session-and-csrf-token-before-every-route) | `src/course_explorer_admin_web/middleware.py` | `tests/admin_web/test_security.py`, `tests/admin_web/test_commands.py`, `tests/admin_web/test_routes.py` |

## Data

### Official and inferred prerequisites are stored apart

Normalization writes official option, substitution, and module-rule rows from the captured source. The inference publication writes inferred sets and equivalence groups into their own tables, and the inferred store rejects a node whose origin is not inferred at every occurrence in the expression. No inference run can write, replace, or relabel an official row.

Enforced by `src/course_explorer/ingestion/normalization_repository.py` (the only writer of `OfficialPrerequisiteOption` and `OfficialSubstitutionOption`), `src/course_explorer/inference/publication.py` (`publish_current_cohort`), and `src/course_explorer/prerequisite/repository.py` (`InferredPrerequisiteRepository.publish` with `_validate_storable_expression`).

Covered by `tests/prerequisite/test_inferred_prerequisite_repository.py::test_publish_rejects_official_unsupported_unknown_self_or_unevidenced_inference_nodes` and `tests/inference/test_inference_publication_repository.py::test_publish_idempotent_complete_empty_and_recommended_through_the_stores`.

### Only teaching text is embedded

`build_course_embedding_chunks` reads the effective text cells of each representative version: the name, content, and learning-outcome fields only. Prerequisite text never reaches a chunk, a work key, or a vector.

Enforced by `src/course_explorer/embeddings/generation.py` (`build_course_embedding_chunks` over the `TeachingTextField` set that the effective-text catalogue produces).

Covered by `tests/embeddings/test_course_embedding_generation.py::test_build_chunks_preserves_field_language_origin_and_source_provenance`.

### Prerequisite expressions keep AND and OR semantics and canonical identity

The compiler builds one solver structure per request from the source prerequisite expressions. The solver structure carries AND groups, OR groups, the source facts with their official and inferred categories, and the inlined rules of a selected module version as strict validated pieces. Every course leaf resolves to one canonical group identity, so selection, completion, and exclusion act on the same course in every tab.

Enforced by `src/course_explorer/prerequisite/domain.py` (`AndRequirement`, `OrRequirement`, `CourseRequirement`) and `src/course_explorer/prerequisite/graph.py` (`PrerequisiteGraphCompiler.compile_structure`, which builds the solver structure, resolves the rules of a selected module version, and records every unresolved part, and `DirectPrerequisiteCompilation`, which pairs that structure with the required and recommended category roots).

Covered by `tests/prerequisite/test_graph_official.py::test_compiler_preserves_official_or_of_and_recommended_and_directional_substitutions` and `tests/prerequisite/test_prerequisite_domain.py::test_expression_union_round_trips_every_node_kind_without_flattening`.

### The minimum route minimizes new credits and counts each course once

The route search minimizes new credits. One course that several branches need is counted once. The exact search runs first. A calculation whose exact attempt exceeds `PREREQUISITE_PATH_MAX_COMPACT_NODES` runs one scalar greedy derivation instead, and the result marks that route as approximate. Only the exact attempt is bounded by the configured limit, and the greedy derivation has no allocation cap.

Enforced by `web/src/solver/route.ts` (`calculateMinimumNewCredits`, `solvePath`, `solveGreedyPath`, `buildNewCourses`) over the shared fold in `web/src/solver/route-families.ts`. The browser runs the solver in `web/src/features/prerequisites/route/worker.ts`, and the machine command runs it through Node in `src/course_explorer/prerequisite/commands.py` (`run_minimum_route_command`).

Covered by `web/src/solver/route-minimum.test.ts::minimum path uses global union and new credits not local course count` and `web/src/solver/route-minimum.test.ts::repeated unexpandable module work is charged once`.

### Schema changes go through Alembic migrations

Every table, index, and constraint is created by a migration in one chain, and each migration names the single revision before it. A database is read only at the executing checkout's one migration head.

Enforced by `migrations/versions/` (head `20261025_0019`) and `src/course_explorer/datasets.py` (`require_database_schema`).

Covered by `tests/db/test_database_schema.py::test_shared_migration_chain_builds_fresh_head_schema` and `tests/db/test_database_schema.py::test_head_schema_matches_metadata_and_preserves_operator_decision`.

### Only the current schema and format are read

State files are loaded strictly into a closed model, and a payload that does not match the model fails the read. The inference result contract accepts only the `v2` schema version. A stored prerequisite expression outside the current node vocabulary fails the read instead of falling back to official-only output.

Enforced by `src/course_explorer/administration.py` (`load_private_model`), `src/course_explorer/inference/domain.py` (`target_result_model`), and `src/course_explorer/prerequisite/domain.py` (`parse_prerequisite_expression`).

Covered by `tests/administration/test_administration.py::test_administrative_json_and_model_round_trip`, `tests/admin/test_operator_database.py::test_worker_schema_mismatch_refuses_before_work`, and `tests/prerequisite/test_prerequisite_graph_repository.py::test_inferred_recommended_toggle_matrix_flows_through_postgresql_and_command`.

## Inference

### Inference reads no official prerequisite structure

The target packet carries the target and its ranked candidates with identity, activity context, and effective text only. Official prerequisite options never enter a packet, a candidate query, or a prompt, and the rendered request carries no label, no rank, and no target-shaped example.

Enforced by `src/course_explorer/inference/context.py` (`InferenceTargetPacket`, `catalogue_identity_sha256`) and `src/course_explorer/inference/target_pass.py` (`render_target_request`).

Covered by `tests/inference/test_inference_context.py::test_packet_hash_binds_current_teaching_provenance_without_official_labels` and `tests/inference/test_inference_target_pass.py::test_render_never_leaks_labels_ranks_or_same_target_example`.

### Model output is validated before use and failures are recorded

One model call returns one complete target result that is parsed strictly against the `v2` contract and then checked against the request's own descriptors. Every named code must resolve to exactly one canonical group, a course cannot be both required and recommended, and the target cannot name itself. A rejected result, a request failure, or a capacity failure becomes a durable target failure record with a closed reason and no course text.

Enforced by `src/course_explorer/inference/domain.py` (`parse_target_result`, `validate_target_result_acceptance`), `src/course_explorer/inference/provider.py` (`StructuredJsonProvider.generate_json`), and `src/course_explorer/inference/scheduling_repository.py` (`record_target_failure`).

Covered by `tests/inference/test_inference_target_pass.py::test_terminal_request_and_contract_failures_retain_safe_evidence` and `tests/inference/test_inference_target_pass.py::test_result_rejects_unknown_direct_or_equivalence_code`.

### A broad or transitive foundation is suppressed from the direct options

The directness outcome `too_basic_transitive` marks a candidate that sits below the entry level of the target, and the result contract rejects a result that also lists a suppressed candidate as a direct option. Proposal composition reads official structure only after the model output exists and leaves a broad or transitive foundation out of the target's direct options.

Enforced by `src/course_explorer/inference/domain.py` (`InferenceSuppressedCandidate`, `InferenceTargetResultV2.validate_complete_result`) and `src/course_explorer/inference/proposals.py` (`compose_target_proposal`).

Covered by `tests/inference/test_inference_proposals.py::test_reject_ambiguous_or_multi_set_without_inventing_grouping` and `tests/inference/test_inference_domain.py::test_target_result_preserves_complete_grouped_contract`.

## Pipeline

### Stages resume from a checkpoint and process pending, failed, or changed work only

Each stage writes one state file naming its current session and its checkpoint, so a stopped or interrupted stage resumes at the first unfinished unit of work. Desired work is compared with stored work by content hash, so a rerun embeds, translates, or generates only pending, changed, or failed work.

Enforced by `src/course_explorer_admin/lifecycle.py` (`run_lifecycle_command`, `LifecycleState`), `src/course_explorer/embeddings/generation.py` (`CourseEmbeddingService.run` through `CourseEmbeddingRepository.reconcile`), and `src/course_explorer/inference/scheduling_repository.py` (`begin_cycle`, `record_target_failure`, `read_target_failures`).

Covered by `tests/admin/test_lifecycle.py::test_local_lifecycle_actions_checkpoint_pause_stop_and_resume_pending`, `tests/inference/test_inference_target_pass.py::test_run_reuses_completed_work_and_explicitly_retries_failed_work`, and `tests/inference/test_inference_job.py::test_generation_checkpoint_yield_resumes_same_calculation`.

### Every stage exposes one lifecycle

Ingestion, embedding, translation, and inference share one lifecycle with the five actions start, pause, resume, status, and stop. One dispatcher validates the stage and the action and delegates once to the owning module, and every stage answers with the same status shape.

Enforced by `src/course_explorer_admin/lifecycle.py` (`run_lifecycle_command`), `src/course_explorer_admin/cli.py` (`_STAGES`, `_ACTIONS`), and `src/course_explorer_admin/commands.py` (`run_administrative_command`).

Covered by `tests/admin/test_lifecycle.py::test_local_lifecycle_actions_checkpoint_pause_stop_and_resume_pending`, which runs the five actions through `run_lifecycle_command` for the ingestion and embedding stages, and `tests/admin/test_remote_lifecycle.py::test_remote_due_checkpoint_reboots_and_continues_same_session`, which runs the translation and inference stage lifecycle commands through `course_explorer_admin.remote_stages`. The stage and action sets in `cli.py` are the closed grammar over the same five actions, and no test names them directly.

### Adapters hold no business logic

Each script under `scripts/` parses its arguments and delegates once to one package entry point, and `scripts/admin.py` delegates once to the administrative dispatcher, so behavior lives in `course_explorer` and `course_explorer_admin` only.

Enforced by `scripts/search.py`, `scripts/admin.py`, `scripts/prerequisites.py`, and the other adapters in that directory, each of which calls one command function.

This invariant has no test of its own. No test loads a script, and the adapter shape holds the rule. The tests of an owning command call it at its public boundary, and [Command adapters](/docs/backend/interfaces/command-adapters.md#adding-an-adapter) lists them.

## Web

### The course-exploration web server never mutates authoritative data, starts a stage, or reaches the worker

The `course_explorer_web` package exposes read commands and fixed shell documents only, and it imports no administration module, no translation module, and no ingestion or embedding command module. One supervisor starts the front router on the configured loopback port and the worker processes on ephemeral loopback ports. The launcher hands the supervisor a closed environment, so no stage control value, model credential, or worker connection value can reach it.

The site's two feature switches are implemented. `WebSettings` validates `WEB_EMBEDDINGS_ENABLED` and `WEB_INFERENCE_ENABLED` from `config/web.toml`, the launcher composes the embedding family only on a site that serves embedding features, the feature read reports that pair, and each affected read enforces it. The feature read also reports one opaque dataset identity derived from the serving generation and the selected dataset, and every cached read reports that same value beside its report. The web graph route adds the configured allocation limit beside the report. The serving process resolves one connection, injects it into the command and serializes the report with that connection's identity, so the report and its identity come from one resolution. The serving parent creates the generation before it starts its worker processes. A restarted web server changes the identity, and a selected-receipt switch changes it on the next read without a restart.

An idle tab discovers neither change until an uncached read, and the browser's bounded read cache clears when it reads another identity. The browser app holds one memory cache of successful reads and one IndexedDB store of structure reports, both scoped to that identity. A structure report is additionally scoped to the exact per-profile module-version map that produced it, so another selection never answers it.

The browser reads only its schema-3 envelope and `/3` transfer files. A stored value or a file of another shape fails validation and changes nothing in the browser. The recovery screen exports the stored envelope text exactly as stored or resets browser storage after confirmation, and the file input refuses an import file of another type or shape.

The serving path writes one request record per request to the site's own usage file and holds transient admission counters in the front router's process memory, and those two are its writes. `UsageMiddleware` observes the response status, the fixed route label and the monotonic duration, and `append_usage_record` writes one line under one exclusive lock on that file. The usage report reads the same file with the same lock, so a record that arrives while a report rewrites the retained lines is preserved, and no record starts a second store.

`RouterApplication` classifies a POST to one of the nine fixed API paths, takes the light or heavy ticket of the anonymous cookie, places each heavy request on a worker process with no heavy request, and records the elapsed cost of a prerequisite graph build from immediately before the forward to the end of the response body. `AdmissionState` holds the counters, the light and heavy activity timestamps, tickets, cookie keys and graph costs alone, has no persistence, and only the router reads them.

Enforced by these owners:

- Supervision and launch: `src/course_explorer_web/__main__.py` (`main`), `src/course_explorer_web/worker.py` (`main`), `src/course_explorer_web/launch.py` (`main`).
- The front router: `src/course_explorer_web/router/__main__.py` (`main`), `src/course_explorer_web/router/app.py` (`RouterApplication`, `create_router`), `src/course_explorer_web/router/workers.py` (`WorkerPool`), `src/course_explorer_web/router/usage.py` (`UsageMiddleware`, `_route_label`).
- Admission: `src/course_explorer_web/admission/state.py` (`AdmissionState`), `src/course_explorer_web/admission/host_cpu.py` (`busy_cpu_seconds`, `core_count`), `src/course_explorer_web/admission/classify.py` (`classify`), `src/course_explorer_web/admission/policy.py` (`regime`, `light_load_factor`, `heavy_budget`, `heavy_queue_limit`, `heavy_slots`), `src/course_explorer_web/admission/identity.py` (`identify`, `set_cookie_value`), `src/course_explorer_web/admission/graph_cost.py` (`graph_cost_field`), and `src/course_explorer/config.py` (`AdmissionSettings`).
- The read routes and their reports: `src/course_explorer_web/app.py` (`create_app`), `src/course_explorer_web/serving.py` (`Route`, `route_of`, `MEASURE_GRAPH_HEADER`), `src/course_explorer_web/dataset.py` (`resolve_serving_dataset`), `src/course_explorer_web/reports.py` (`dataset_report_response`), `src/course_explorer_web/routes/features.py` (`features`), the switch reads in `src/course_explorer_web/routes/search.py`, `comparison.py`, `recommendations.py`, `prerequisites.py` and `next_courses.py`, the catalogue route `src/course_explorer_web/routes/catalogue.py`, and `src/course_explorer/study_structure/service.py` (`StudyStructureService.read_many`), which reads several roots over one shared projection.
- The usage record: `src/course_explorer/usage.py` (`append_usage_record`, `read_usage_report`).
- Outside the serving package: the browser worker `web/src/features/prerequisites/route/worker.ts` and its client `workerClient.ts` run the route calculation, and `web/src/shared/course/narrowing.ts` applies the local official narrowing.

Covered by `tests/web/test_boundary.py::test_web_surface_is_read_only`, `tests/web/test_launcher.py::test_web_launcher_excludes_operator_credentials`, `tests/web/test_feature_switches.py::test_disabled_embedding_features_refuse_reads`, `tests/web/test_feature_switches.py::test_site_feature_switch_bounds_delegated_policy`, `tests/web/test_feature_switches.py::test_cached_reads_report_one_serving_dataset_identity`, `tests/web/test_admission.py::test_routes_take_their_admission_class_and_cost`, `tests/web/test_admission.py::test_score_scales_admission_and_holds_saturation_until_release`, `tests/web/test_admission.py::test_heavy_activity_counts_recent_starts_and_older_running_requests_once`, `tests/web/test_admission.py::test_graph_cost_cache_is_dataset_scoped`, `tests/web/test_admission.py::test_router_limits_cookies_and_records_refusals`, `tests/web/test_admission.py::test_heavy_queue_waits_at_saturation_and_refuses_at_its_cap`, `tests/web/test_router.py::test_heavy_requests_place_on_workers_without_a_heavy_request`, `tests/web/test_router.py::test_light_requests_forward_to_the_least_busy_worker` and `tests/web/test_router.py::test_router_treats_an_unreadable_meter_as_unloaded`.

The catalogue command and the usage records are covered by `tests/search/test_course_lookup.py::test_catalogue_command_selects_strict_module_candidates`, `tests/web/test_usage.py::test_http_requests_record_only_safe_route_usage`, `tests/admin/test_usage.py::test_usage_report_aggregates_window_and_prunes_retention` and `tests/admin/test_usage.py::test_usage_append_and_prune_preserve_concurrent_records`.

The separate administration surface is implemented in its own package, whose authentication, exact-site, session, lock, record, fixed-command and separately built console boundaries are described in [System boundaries](/docs/architecture/boundaries.md) and on [Administration backend](/docs/backend/interfaces/admin-backend.md). The enforcers and tests above cover the course-exploration web server, the usage record it appends, and the usage report over that file.

## Administration

### The administration backend checks the lock, exact site, session and CSRF token before every route

One process serves the administration backend, and `AdminAdmissionMiddleware` applies one order to every HTTP request before any route runs. A present lock refuses with a bare `403` and an empty body, whatever the file holds. A request must carry exactly one `Host` header equal to the configured origin's netloc, and a supplied `Origin` must equal the configured origin exactly.

A read-only request of exactly `/` or of a path beginning `/assets/` is admitted here, before its cookie is read, so the built console shell and its built assets load without a session. That request creates no session, touches no session, executes no command and records nothing. `GET /auth/session` reuses the session of its cookie or creates an anonymous one within the process-wide anonymous session creation limit, and a fresh grant beyond the limit answers the empty `429` with `Cache-Control: no-store` and a ceiling-rounded `Retry-After`. `POST /auth/login` needs a live session of any kind to carry its CSRF token, so a sign-in without one is refused at the site boundary. Every other address needs an authenticated live session.

Every state-changing method needs that exact `Origin` and a live session whose `X-CSRF-Token` matches. The session of an admitted request is refreshed only after every check above has passed. A refused request reaches no handler, records no credential attempt and refreshes no idle clock. A failure answers one content-free JSON 500 naming the exception class alone.

The administration packages own the state behind that boundary. `AdminSecurity` holds the sessions and the creation times of its fresh anonymous sessions in memory, so a restart ends the sessions and clears the count, and it persists only the failed-attempt count, the lock and the sole command log under `data/admin-web/`. `src/course_explorer_admin/credentials.py` owns the argon2id credential file, and `src/course_explorer_admin_web/command_log.py` owns the bounded log and holds no captured output, argument or credential. [Console access and records](/docs/operations/admin-console/access-and-records.md) states the same order and the two records for an operator.

Every console feature request is authenticated and runs fixed `scripts/admin.py` commands through `FixedCommandRunner`, whose closed discriminated union admits a shape and builds its argument list. One request runs exactly one admitted command. The route of the Administration rebuild runs two: its build command synchronously, and its restart command as the successful response's background task, after the final response body send. The runner's labels are fixed source text, so no target id, dataset id, disposition argument or report payload reaches the log. The console's own React application is built separately from `admin-web/` into `admin-web/dist`, which `src/course_explorer_admin_web/frontend.py` serves as the shell and one assets mount.

Enforced by `src/course_explorer_admin_web/middleware.py` (`AdminAdmissionMiddleware`), `src/course_explorer_admin_web/security.py` (`AdminSecurity`, `AnonymousSessionRateLimited`, `FAILED_LOGIN_LIMIT`, `LOCK_FILENAME`), `src/course_explorer_admin_web/command_log.py` (`CommandLog`), `src/course_explorer_admin_web/runner.py` (`FixedCommandRunner`, `_command_label`), and `src/course_explorer_admin_web/frontend.py` (`register_frontend`).

Covered by `tests/admin_web/test_security.py::test_admin_requests_enforce_host_origin_and_csrf`, `tests/admin_web/test_security.py::test_admin_lockout_persists_and_blocks_every_request`, `tests/admin_web/test_security.py::test_admin_sessions_expire_at_idle_or_total_limit`, `tests/admin_web/test_security.py::test_admin_login_issues_protected_server_session`, `tests/admin_web/test_security.py::test_admin_logout_revokes_only_its_session`, `tests/admin_web/test_commands.py::test_admin_command_runner_executes_only_fixed_commands`, `tests/admin_web/test_commands.py::test_admin_command_log_retains_only_bounded_safe_entries`, `tests/admin_web/test_routes.py::test_admin_feature_route_runs_its_fixed_command`, `tests/admin_web/test_routes.py::test_admin_restart_waits_for_response_completion`, and `tests/admin_web/test_command_log_read.py::test_command_log_command_reads_the_sole_owner`.

The anonymous session budget is covered by `tests/admin_web/test_security.py::test_anonymous_session_budget_is_server_wide_and_spares_live_sessions` and `tests/admin_web/test_security.py::test_anonymous_session_budget_recovers_at_the_rolling_window`.

## Configuration

### Credentials live outside tracked files

The database password and the three worker connection values are read from the ignored `.env` file through the settings layer. No tracked TOML file carries them, a secret is held wrapped while settings validate, and a validation failure renders no input.

The administration credential is stored as a hash file rather than as an environment value. A site's account is written through the fixed `password` command as an argon2id hash in `data/admin-web/password`, so no plaintext password and no credential in tracked configuration exists, and the web surface holds no route that writes it.

Enforced by `src/course_explorer/config.py` (`DatabaseSettings.postgres_password`, `hide_input_in_errors`), `src/course_explorer/configuration.py` (`read_local_configuration`), `src/course_explorer_admin/credentials.py` (`set_admin_password`, `read_admin_credential`), and `src/course_explorer_web/launch.py` (`main`).

Covered by `tests/config/test_configuration_sources.py::test_loads_automatic_configuration_and_applies_override_precedence`, `tests/web/test_launcher.py::test_web_launcher_excludes_operator_credentials`, and `tests/admin/test_operator_commands.py::test_operator_commands_report_status_refuse_bad_input_and_map_nothing`.
