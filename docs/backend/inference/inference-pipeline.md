# Inference pipeline

The inference package turns effective text into validated proposals through selection, rerank, generation, and publication.

## Modules and entry points

The package is `src/course_explorer/inference/`. Each module owns one part of the pipeline.

| Module | Owns |
|---|---|
| `context.py` | The label-free packet and reference DTOs, the multiview fusion helper, and the catalogue and text identities |
| `context_repository.py` | `InferenceCandidateRepository`, the exact best-chunk cosine ranking over stored vectors |
| `operational.py` | `OperationalCatalogue`, the multiview pool and shortlist DTOs, and `materialize_selection_packet` |
| `operational_selection.py` | `represented_identities`, `rank_multiview_pool`, `render_rerank_course_text`, `score_rerank_pairs`, and `FINAL_CANDIDATE_MAX` |
| `routing.py` | `select_fitting_variant` and `run_routed_operational_target`, the fit-only choice of a local key |
| `provider.py` | `StructuredJsonProvider` and `RerankProvider`, the two loopback HTTP clients |
| `prompts.py` | `load_prompt_pack` and the versioned prompt pack |
| `domain.py` | `InferenceTargetResultV2` and the acceptance rules for untrusted model output |
| `evidence.py` | The run, work, request, and completion DTOs and their canonical identities |
| `evidence_repository.py` | `InferenceEvidenceRepository`, the run, work, and completion store |
| `target_pass.py` | `render_target_request`, `prepare_target_request`, `target_work_identity`, and `run_target`, the whole-target writer |
| `scheduling.py` | The marker, cycle, checkpoint, and failure DTOs and the membership predicate |
| `scheduling_repository.py` | `InferenceSchedulingRepository`, the mutable scheduling store |
| `proposals.py` | `compose_target_proposal` and the equivalence aggregation |
| `proposal_repository.py` | `InferenceProposalRepository`, the append-only proposal store |
| `proposal_commands.py` | `compose_proposal_from_work`, the one-shot composition entry |
| `publication.py` | `prepare_current_publication` and `publish_current_cohort`, the final-store writer |
| `job.py` | `run_inference_job` and `InferenceJobProgress` |
| `diagnostics.py` | `PublicationDiagnostics`, `InferenceCoverageSummary`, and `strict_ancestor_warnings` |
| `failures.py` | The fixed failure vocabulary and the target-scoped exception types |

The stage entry points form one path. `prepare_operational_catalogue(curriculum, teaching_text, embedding_settings)` in `operational.py` reads the catalogue and effective text once per batch and returns one `OperationalCatalogue`. `select_operational_multiview_pool(...)` returns one `OperationalPoolInput`, and `rerank_operational_pool(...)` returns one `OperationalTargetInput`. `run_routed_operational_target(...)` in `routing.py` materializes the packet and calls `run_operational_target(...)`, which delegates to `run_target(...)`. `run_inference_job(...)` in `job.py` drives all of them and calls `compose_proposal_from_work(...)` and `publish_current_cohort(...)`.

The packet DTOs in `context.py` carry each course's identity (`group_id`, `sisu_course_unit_id`, `representative_source_sha256`), its `course_code`, its `is_active` flag, its activity year and window, and each effective teaching cell's `field`, `language`, `text`, `origin`, `text_sha256`, and `source_text_sha256`. `InferenceCandidatePacket` carries the packet course alone, and `InferenceTargetPacket` adds `packet_version` and `embedding_configuration_sha256` and refuses a candidate set that repeats an identity or contains the target.

## Identities and hashes

Every identity is a canonical JSON SHA-256 from `course_explorer.hashing.canonical_json_sha256`, so one hashing dialect exists for the whole package.

| Helper | Hashes |
|---|---|
| `processing_text_sha256` in `context.py` | The sorted effective `(field, language, text)` cells alone |
| `catalogue_identity_sha256` in `context.py` | Canonical identity, activity context, representative source, effective cell hashes, and the compatible embedding configuration hash |
| `selection_references_sha256` in `context.py` | One compact ordered selection of target and candidate references |
| `request_sha256` in `target_pass.py` | One rendered request, system prompt, user prompt, schema name, and JSON schema |
| `target_input_sha256` in `target_pass.py` | The selected packet digest and the rendered request digest |
| `run_identity_sha256` in `evidence.py` | The model, runtime, prompt, schema, pipeline, and route identity |
| `work_key_sha256` in `evidence.py` | One target activity context, a transient input digest, and run identity |
| `embedding_state_sha256` in `context_repository.py` | The scoped chunk state of the supplied current course pairs under one embedding configuration hash |
| `processing_cycle_input_sha256` in `scheduling.py` | The catalogue identity, the embedding-state digest, and the selection, context, and rerank settings |
| `official_snapshot_sha256` in `proposals.py` | The target identity, activity context, representative source, and direct official prerequisite and substitution options |
| `proposal_identity_sha256` in `proposals.py` | The work key, the completion id, the official snapshot, and the proposal version |

`InferencePipelineRunSpec.from_contracts(settings, execution=...)` builds the run spec from the configured prompt, schema, and pipeline versions and the selected execution. `prepare_target_request` rejects a prompt pack whose version differs from `INFERENCE_PROMPT_VERSION` before tokenization. A proposal id is `uuid5(NAMESPACE_URL, identity_sha256)`.

## Domain validation and the prompt pack

`InferenceTargetResultV2` in `domain.py` is the only accepted complete-result shape. It holds `required` and `recommended` tuples of `InferenceRequirementSetV2`, a tuple of `InferenceEquivalenceProposalV2`, and one `InferenceRoutingMetadata`. Its `validate_complete_result` rejects a repeated `requirement_id`, a logically duplicate option or group, a course that is both required and recommended, a suppressed candidate that is also a direct option, and a duplicate equivalence membership. A confidence must be a finite number between 0 and 1, and `_validate_confidence` refuses a quoted string and a boolean. Every option and every equivalence group carries an explicit `finding_flags` array, which the `v2` wire shape requires and which may be empty. `InferenceSuppressedCandidate` refuses the `direct_prerequisite` outcome, and `DirectnessOutcome` carries `too_basic_transitive` as a first-class outcome. Findings use `OptionFlag` and `EquivalenceFlag`.

`parse_target_result(raw_json, schema_version)` parses the document as strict JSON with decimal numbers and then validates it, so a duplicate key or a non-finite number fails. `target_result_model` accepts only `v2`. `target_result_json_schema` rewrites the Decimal confidence union into one numeric schema carried by the rendered request. The class docstring is Python documentation, and `_V2_RESULT_WIRE_DESCRIPTION` is the explicit root schema description. The emitted schema text, including the model and enum descriptions and this root description, participates in request and work identity.

`validate_target_result_acceptance(result, *, target_group_id, course_groups_by_code)` is the one shared acceptance rule. It allows at most one requirement set per category, resolves only the codes the result names to exactly one canonical group each, and rejects an unknown code, an ambiguous code, and the target as its own direct or suppressed source. `resolve_result_codes` in `context.py` builds the code map from the request descriptors and calls it.

The prompt pack loads from package resources under `src/course_explorer/inference/prompts/<version>/`, one `system.md` and one `examples.json`. `load_prompt_pack` accepts `v9` and hashes both byte sequences into `content_sha256`. `PromptPack.examples_for_target` returns the examples in file order without any example whose answer is the target course, and `render_target_request` excludes a matching course code as well. `PromptCourse` holds teaching fields with explicit origins, so a prompt model carries teaching text and origins alone.

## Provider and the target pass

`StructuredJsonProvider` posts one schema-constrained request to `v1/chat/completions` per `generate_json` call and validates the envelope, the configured alias, the runtime fingerprint suffix, the usage counts, and the timing rates before returning one `StructuredGeneration`. `count_prompt_tokens` renders the same chat template through `apply-template` and counts through `tokenize` in one bounded preparation loop. `classify_inference_request_error` maps a rejected request status, a retryable status, and a transient transport error to `InferenceTargetRequestError`, and every other failure to `InferenceRequestError`.

`RerankProvider.score` posts one query and document pair to `v1/rerank` and returns one validated finite `RerankScore` at index zero. Each client makes one request per call and raises a content-free error class, so a prompt, a response body, pair text, and a credential stay out of every error.

`select_fitting_variant(settings, prompt_tokens)` in `routing.py` returns the first ordered key whose `context_size` and `achieved_max_context` both fit `prompt_tokens + INFERENCE_MAX_TOKENS + INFERENCE_FIT_HEADROOM_TOKENS`, and returns `None` when no key fits. `run_routed_operational_target` prepares the request and its digests once before token counting, counts the tokens through a loaded key when one is loaded, loads the first key on genuine first use, switches to the larger no-MTP key only when only it fits, and raises `TargetContextError` when neither fits and no oversize route is supplied. The token counter, the planned-identity callback, and the selected provider all consume that one prepared request and the one route-bound identity.

`render_target_request(packet, pack, schema_version)` builds one deterministic request. The system prompt is the pack's system text plus the curated examples as sorted compact JSON, and the user prompt is sorted compact JSON of the target and the ordered candidate descriptors.

`prepare_target_request(value, pack, settings, *, packet)` renders that request once and returns a transient `PreparedTargetRequest` with the request digest and target input digest. `target_work_identity(value, settings, execution, *, packet, prepared)` binds the selected execution, the activity context, and the prepared digests into one work request without rendering again.

`run_target(value, settings, repository, provider, execution, *, packet, identity, ...)` creates the run, claims the work with `identity.input_sha256`, reuses completed work, reserves each attempt through the scheduling owner, calls the provider once per request, parses and accepts the result, and writes one completion. It owns the whole-target retry loop, which is unbounded on the local route and bounded by `provider.max_attempts` on any other route.

`operational_selection.py` holds the selection mechanics. `render_rerank_course_text` writes the course code and the effective cells only and truncates once to the configured character bound. `score_rerank_pairs` scores every pair once and returns the deterministic ranking. `rank_multiview_pool` queries each configured field view once and fuses the views, and `fuse_candidate_views` in `context.py` sums `1 / (rank_offset + view_rank)`.

## Evidence and scheduling repositories

`InferenceEvidenceRepository` in `evidence_repository.py` owns one transaction per operation over `inference_pipeline_runs`, `inference_target_work`, and `inference_model_attempts`. `create_run` selects or inserts the one run for a run identity. `claim_work(run_id, request, input_sha256)` inserts, returns, or reuses the one work row for a work key and validates the live target activity context. The digest is hashed into the work key, and the work row stores that key. `retry_work` resets a failed row to pending, `fail_work` marks a pending row failed, and `record_completion` accepts the untrusted result through `resolve_result_codes` before it writes one completion with the work status in one transaction. `read_completion`, `read_work`, and `read_work_by_id` are the scoped reads.

`InferenceSchedulingRepository` in `scheduling_repository.py` owns the marker, cycle, checkpoint, and failure tables. `reconcile_courses` creates, resets, and refreshes markers. `read_seed_proposals` and `_selected_proposal_ids` fix the accepted-pointer authority. `begin_cycle` resumes a matching unfinished cycle or inserts a fresh multiview cycle and carries each marker's decision onto that cycle's target rows.

`checkpoint` applies only legal stage transitions through `_validate_transition` and manages the compact pool and shortlist payload lifecycles. `record_target_failure` marks the executing stage failed and appends one `TargetFailureRecord`. `reserve_generation_attempt` returns the durable lifetime ordinal and the calculation-first flag.

`set_stage` advances one adjacent forward stage after `_require_stage_settled`. `accept_target` sets the inference stage completed, the proposal pointer, and the marker's processed flag in one transaction. `finish_cycle` requires the publication stage, the recomputed input digest, and full marker coverage, then bulk-marks every course and completes the cycle.

`prune_retained_state` deletes proposals, completions, work, and runs that no marker or current-cycle generation work key references. `_require_skip` re-derives the shared membership predicate before a legitimate skip, and `_require_cycle_terminal` guards the finish.

`set_target_disposition(target_group_id, disposition)` accepts `None`, `done`, or `failed`. A nonnull value projects onto the current cycle's checkpoint through `_apply_target_disposition`, which sets only the inference state and a safe error type. A nonnull-to-`None` clear calls `_clear_target_to_automatic`, which reopens the inference state, clears the proposal pointer, retains a recoverable completed selection, and rewinds the cycle to the target's earliest nonterminal stage. `read_operator_failed_target_group_ids` reports the terminal operator failures.

## Proposals and publication

`compose_target_proposal(work, attempt, descriptors, target, referenced_courses, proposal_version)` in `proposals.py` is pure. It reads the completion's uncomposed result, resolves only the named codes, builds the per-category pools, applies `_dedup_option` against the direct official plain-course options, applies `_compose_equivalence` against the official single-course substitutes, and returns one `TargetProposal` with `AcceptedOptionFlags` copied from the result.

`_official_plain_options` retains the target's direct official options whose members are all course-typed, maps `compulsory` to required and every other kind to recommended, and `_dedup_option` absorbs an inferred option whose member set is a subset of an official option of the same category, removes the members named by an official option of the other category, and returns nothing when no member is left.

`_compose_equivalence` drops the group that exactly equals the target plus one official single-course substitute and retains every other group. `compose_proposal_from_work` reads the completion and work rows, then reads the target and the candidate group IDs the result names through `named_candidate_group_ids`, so it reads those identities from the catalogue alone.

`InferenceProposalRepository.save` appends one proposal per identity, reuses an identical identity, rejects a conflicting one, and releases the consumed completion payload in the same transaction.

Publication reads the cohort, validates every accepted pointer by its foreign-key target ownership, builds one complete `InferredSetPublication` per accepted target and one `EquivalenceGroupPublication` per distinct member tuple, and writes them through `InferredPrerequisiteRepository` in `src/course_explorer/prerequisite/repository.py` and `InferredEquivalenceRepository` in `src/course_explorer/prerequisite/equivalence_repository.py`. `_reject_incomplete_cohort` refuses a cohort that omits a live inference-published target, and `_done_without_output_count` lets an explicit done target count as published once its output is withdrawn. `strict_ancestor_warnings` in `diagnostics.py` reports an accepted option that is also a strict ancestor of another accepted option, and it changes no stored result.

## Job orchestration and progress

`run_inference_job(factory, *, runtime, before_unit, before_request, on_checkpoint, on_generation_attempt_checkpoint=None, oversize_route=None, clock=utc_now)` loads the settings families once, prepares one catalogue, requires current chunks for the active targets, reconciles markers, resumes or begins one cycle, and dispatches the cycle's stage chain. `_eligible` gates one target's stage on its own pending or failed state and a completed upstream stage, and `_ordered_units` orders ordinary target courses first and an operator-failed target course last. `execute_unit` owns the bounded retry for multiview, rerank, and preparation, and it records one summary episode for a bounded stage. `InferenceJobProgress` is derived from the in-memory state and marker maps, the process-local transition counter, and the invocation-local exhausted set, so the counters live in one place.

`on_generation_attempt_checkpoint` is called after every committed whole-target generation failure, which is where the worker samples its reboot clock. `InferenceJobRuntime` supplies the owned runtime's load, unload, and request scope. A control refusal raises the cooperative `RequestNotStarted` and returns the unfinished cycle, and the publication stage raises `InferenceTargetsFailed` after publishing the useful results when any target course is failed.

## Admin controller and disposition

`course_explorer_admin/inference/controller.py` owns the retained-session contracts. `InferenceControllerPolicy` carries `configuration_sha256` from `inference_configuration_sha256`, which covers the generation, embedding, context, selection, rerank, and rerank-input settings plus the prompt content hash. `InferenceControllerWorkerState` is the schema-2 lifecycle matrix, and `InferenceControllerStatus` adds the per-stage progress projection. `load_inference_dataset_session` requires an inference session, the configured derived database name, and an unbounded session.

`course_explorer_admin/inference/controller_worker.py` is the worker stage body. `InferenceWorkerStage` forwards one `run_inference_job` call under the live `before_unit` and `before_request` gates, which read the requested action and the latched reboot clock, and `_finalize` publishes the retained cohort once and writes the import receipt. `course_explorer_admin/reboot.py` owns `WorkerGpuClock`, which accumulates loaded time and samples at a checkpoint, and `worker_gpu_reboot_due`, which reports whether a saved sample reached `WORKER_GPU_REBOOT_INTERVAL_MINUTES`.

`course_explorer_admin/inference/disposition.py` is the server-side surface. `_disposition_context` resolves the selected-dataset switch and the live schema head of the selected database for a read. A write additionally requires a verified returned receipt and all stages idle, and it takes the datasets action lock. `read_inference_target_disposition` reads one decision without taking that lock, and `set_inference_target_disposition` writes the decision first and then runs `publish_current_cohort` once, so an identical repeat repairs a failed publication.

## Tables and tests

| Table | Holds |
|---|---|
| `inference_pipeline_runs` | One shared execution identity per coarse identity, with its model, runtime, prompt, schema, pipeline, and route |
| `inference_target_work` | One work row per target and work key, with its activity context and status |
| `inference_model_attempts` | One completion row per completed generation, with its payload and finish time |
| `inference_proposals` | One immutable proposal row per identity, with its expression envelope and equivalence candidates |
| `inference_course_processing` | The teaching-text marker, the was-active fact, the accepted pointer, the lifetime attempt counter, and the decision |
| `inference_processing_cycles` | One processing cycle with its input digest and current stage |
| `inference_processing_targets` | One checkpoint per cycle and target, with the three stage states, the pool and shortlist payloads, the generation work key, and the proposal pointer |
| `inference_target_failures` | One retained failure episode per cycle and target, with its stage, fixed reason, and exhaustion flag |
| `inferred_prerequisite_sets` | The current inferred set of one target course with its coverage state and counts |
| `inferred_equivalence_groups` and `inferred_equivalence_group_members` | One inferred equivalence group and its member courses |

The model definitions are in `src/course_explorer/db/models.py`, and the migrations are in `migrations/versions/`.

| Test file | Covers |
|---|---|
| `tests/inference/test_inference_context.py` | Label-free packet and reference hashes, the deterministic multiview fusion, and the split selection that byte-matches the combined selector |
| `tests/inference/test_inference_candidate_repository.py` | The exact best-chunk ranking over current compatible chunks, inactive sources, the rejection of a stale identity or a missing target chunk, and the scoped embedding-state digest |
| `tests/inference/test_inference_domain.py` | The untrusted grouped result: required and recommended OR-of-AND alternatives, equivalence members, and suppressed directness identities |
| `tests/inference/test_inference_prompts.py` | Package-relative loading, the content hash, and the exclusion of an official target label |
| `tests/inference/test_inference_provider.py` | Returned content and model/runtime attribution, the token-counting loop, indexed rerank scores, redacted failures, and cooperative control |
| `tests/inference/test_inference_evidence.py` | Run and work identity derivation |
| `tests/inference/test_inference_evidence_repository.py` | Run reuse, completed-work reuse, retry, failure visibility, and the rejection of an unknown, inactive, or stale target |
| `tests/inference/test_inference_target_pass.py` | The label-free request, the work key, reuse, explicit retry, the semantic rejections, and the pre-claim refusal |
| `tests/inference/test_inference_proposals.py` | Category pools, the direct-official dedup, the substitution drop, and the ambiguity and multi-set rejections |
| `tests/inference/test_inference_proposal_repository.py` | One row per identity, reuse, and the refusal of failed or stale input |
| `tests/inference/test_inference_publication_repository.py` | Idempotent publication, the complete empty result, the withdrawal of a done target's output, and the retained-pointer validation |
| `tests/inference/test_inference_coverage_repository.py` | Bootstrap and pointer authority, the done cohort, the cycle counters, and the refusal of a broken selected pointer |
| `tests/inference/test_inference_scheduling_repository.py` | Marker reset rules, strict checkpoints, cycle resume, the generation reservation, legitimate skips, guarded finish, and the durable operator decision |
| `tests/inference/test_inference_routing.py` | The fit-only key choice, the execution profile, and the preparation failure that is separate from a fit failure |
| `tests/inference/test_inference_job.py` | Control refusal, the oversize capacity failure, durable exhaustion, the invalid-result retry, the resumed calculation, and the disposition clear |
| `tests/inference/test_inference_job_repository.py` | Job resume over real checkpoints, acceptance, and the final stores |
| `tests/admin/inference/test_inference_controller_worker.py` | The reboot checkpoint after a completed unit and a failed attempt, and the interrupted resume |
| `tests/admin/inference/test_inference_worker_database.py` | Partial worker publication that preserves the unfinished cycle and the real results |
| `tests/admin/test_checkpoint_reboot.py` | The loaded-time clock and the restart handshake |
| `tests/admin/test_operator_database.py` | The disposition guards on the selected, returned, current dataset |
