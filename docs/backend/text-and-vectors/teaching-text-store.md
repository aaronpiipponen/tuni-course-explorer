# Teaching text store

The store holds the derived translations of the selected dataset, and this page describes its table, text resolution, the selector and provider, resumable work, and its sole write path.

## The derived table

`DerivedCourseText` in `src/course_explorer/db/models.py` maps the table `derived_course_texts`. One row is one derived translation of one field and target language for one exact course version, and `course_version_id` references `course_versions.id` with `CASCADE`.

The table refuses a duplicate `(course_version_id, field, language)` through `uq_derived_course_texts_version_field_language`. Its checks are `_not_blank("text")` and `_not_blank("source_text_hash")`, `source_and_target_languages_differ`, `source_text_hash_sha256` for a lowercase 64-character hash, and `method_model_consistent`, which allows a `manual` row with no `translation_model` and a `model` row with a non-blank one. The column list, the enum types, and the migration that creates the table are in [Tables and migrations](/docs/backend/catalogue/tables-and-migrations.md).

The table is written only through the seam in [The sole write path](#the-sole-write-path). No code path writes these rows into the official names of `course_versions` or into `course_texts`, and no read merges official and derived text into one field.

## The translation DTOs and the file loader

`DerivedTranslationInput` and `DerivedTranslation` in `src/course_explorer/teaching_text/service.py` are frozen, closed models on `_DerivedTranslationModel`. A blank `sisu_course_unit_id`, `text`, or `source_text` is refused, `generated_at` is required to be timezone-aware through `require_aware`, equal source and target languages are refused, `_method_model_consistent` applies the method and model rule of the table, and the persisted `source_text_hash` goes through `require_sha256`. The input DTO carries the exact `source_text`, and the persisted DTO carries the hash of that text instead.

`teaching_text_sha256` hashes the exact UTF-8 bytes of a non-blank string, so a trailing space changes the hash.

`load_translation_file` in `src/course_explorer/teaching_text/commands.py` reads one UTF-8 file, parses it with `json.loads`, refuses anything but a top-level array with at least one entry, and validates the array through `TypeAdapter(tuple[DerivedTranslationInput, ...])`. Malformed JSON, a non-array, an empty array, an extra field, and a malformed entry each raise `ValueError`, and the loader returns nothing partial, so a caller that writes only after a successful load never writes part of a file.

## Resolution and the coverage accumulator

`official_teaching_text` returns the non-blank official value of one field and language from a `CatalogueCourseVersion` or a `CatalogueRepresentativeTeachingText`, and it reads no other field, so the prerequisite text and the additional information of a version never enter the resolution.

`_resolve_cell` classifies one cell. It returns the resolved `EffectiveTeachingText` or `None`, one classification of `official`, `derived`, `stale`, or `missing`, and the current source hash of a stale cell. Official text wins. An official cell sets `text_hash` and `source_text_hash` to the hash of that same text, and a derived cell carries the recorded `source_text_hash` together with the method, model identity, and generation time of the row.

`_resolve_representative_cells` walks `TeachingTextField` and `TeachingTextLanguage` in declaration order, increments `counts[(field, language)][classification]`, appends one `StaleDerivedText` per stale cell with its `stored_source_text_hash` and `current_source_text_hash`, and returns the cells in that order.

`_resolve_teaching_inputs` is the single accumulator shared by the effective catalogue and the coverage read. It indexes the derived rows through `index_derived_translations`, which refuses two rows for one identity, counts the six cells, sorts `stale_texts` by group id, source id, field, and language, and lists the courses with no representative. It also records two course counts of the report: `name_only_course_count` for every Name-only course and `unembeddable_course_count` for every Unembeddable course.

For one cell, `official_count + derived_count + stale_count + missing_count` equals `representative_course_count`, because every represented course classifies each of its six cells exactly once.

`TeachingTextService.build_catalogue` resolves every representative and attaches `representative_source_hash` and `is_active` from the read rows. `TeachingTextService.coverage` reads `CurriculumRepository.list_teaching_text_inputs` and the same accumulator, so it returns the identical `TeachingTextCoverageReport` without materializing a `CatalogueCourse`, and `tests/teaching_text/test_teaching_text.py` and `tests/teaching_text/test_teaching_text_repository.py` prove the two reads agree.

The report and carrier DTOs are `EffectiveTeachingText`, `EffectiveCourseTeachingText`, `TeachingTextCoverageCount`, `TeachingTextCoverageReport`, and `EffectiveTeachingTextCatalogue`. `DerivedTranslationRead` in the same module is the read protocol the resolver consumes.

## The sole write path

`DerivedTranslationRepository.upsert` in `src/course_explorer/teaching_text/repository.py` is the only writer of the table, and `list_for_course_versions` is its only reader.

`_prepare_inputs` validates the whole batch before any write. It refuses two entries for one identity, refuses a version that `CurriculumRepository.get_representative_teaching_texts` did not return as a selected representative, refuses an entry whose target cell holds official text, refuses an entry whose source cell holds no official text in the stated source language, and refuses an entry whose `source_text` differs from that official text. It returns each prepared entry with the `teaching_text_sha256` of its source text, computed by the store rather than supplied by the caller, so one invalid entry leaves no row behind.

The prepared batch then runs in one transaction. A version id that is not stored is refused, the stored rows of the batch's version ids are loaded, and each `_translation_values` mapping is compared field by field. An absent row is inserted, an identical row is counted in `unchanged_count`, and a differing row is updated in place. The outcome is returned as `TranslationImportReport` with `requested_count`, `inserted_count`, `updated_count`, and `unchanged_count`. An empty sequence returns a zero report without touching the database.

The official names of `course_versions` and the rows of `course_texts` are never part of `_translation_values`.

## The selector

`select_translation_work` in `src/course_explorer/translation/service.py` returns a `TranslationWorkSelection`. `_collect` reads every course with `CurriculumRepository.list_teaching_courses(active_only=None)`, `_collect_translation_work` applies an optional `course_limit` to that order before it filters representatives, and `_collect_course_work` classifies the six cells of one course.

A cell whose official target text exists counts as `official_target`. Without it, the source is the same field in `_OPPOSITE_LANGUAGE[language]`, and a source cell with no official text counts as `missing_source`. Otherwise the cell becomes a `TranslationWorkItem` carrying the group id, the source identity, the field, the target language, the source language, the exact source text, and the hash of that text. The cell counts as `current_derived` when a stored row for the same identity has the same source language and source hash and is either `manual` or a model row whose `translation_model` equals `TranslationSettings.provenance_model`. Every other candidate cell is `pending` and appears in `items`.

The four counts are per field and language in `TranslationSelectionCount`, and `tests/translation/test_translation_service.py` proves that the pending counts sum to `len(selection.items)`. `_work_key` hashes the item identity together with the configured provenance model. Selection never writes, updates, or deletes a row.

## The provider

`TranslationProvider` in `src/course_explorer/translation/provider.py` is the only path that calls the translation runtime. It builds one `httpx.Client` from `TranslationSettings.base_url`, which is derived from the configured loopback host and port, with `trust_env=False`, `follow_redirects=False`, and the configured request timeout.

`_payload` posts to `v1/chat/completions` the configured alias, one `user` message whose single text part carries `source_lang_code`, `target_lang_code`, and the exact source text, the same two codes in `chat_template_kwargs`, the configured temperature and maximum tokens, and `stream: false`.

`_validate_inputs` refuses blank text and two equal languages before any request, and `translate` on a closed client raises `TranslationRequestError`.

`_validate_response` decodes the body through `decode_json_response` into `_ChatCompletionResponse` with `_ChatChoice` and `_ChatMessage` (`strict=True`, `extra="ignore"`). A response must carry `object` `chat.completion`, the configured alias as `model`, a non-blank `system_fingerprint` ending in a hyphen and the first nine characters of the configured runtime revision, exactly one choice at index 0 with the `assistant` role and `finish_reason` `stop`, and non-blank content without a NUL character. Anything else raises `TranslationContractError`.

`request_json_with_retries` in `src/course_explorer/http_retry.py` owns the attempt loop with `max_attempts=settings.translation_max_attempts`, `retry_backoff_seconds=settings.translation_retry_backoff_seconds`, `retry_contract_errors=True`, and the `before_request` and `request_scope` callbacks of the worker. An `httpx.TransportError`, a 429 or 5xx status, and a response that fails the runtime contract are retryable, the delay before attempt N is the configured backoff times `2 ** (N - 1)`, and every other status is terminal. A refusal before the first request raises `RequestNotStarted` before any I/O, and a refusal during a backoff raises the terminal request error instead of sleeping again.

`TranslationSettings.provenance_model` in `src/course_explorer/config.py` composes the persisted model identity from the model repository, the pinned revision, the artifact quantization, and the artifact SHA-256.

## The resumable worker and its evidence

`TranslationWorkerService.run` translates the selected items in their order. `_load_retained_output` reads a retained output through `load_translation_file` and refuses two entries for one identity, and `_validate_retained` refuses an entry that is not a candidate of the selected scope, an entry whose source language or source text differs from the official source, an entry that is not a model translation, and an entry from another provenance model.

Each success appends the entry and republishes the whole array in candidate order through `atomic_write_private_text` in `src/course_explorer/administration.py`, which writes a temporary file in the target directory, flushes and fsyncs it, sets mode 0600, and renames it over the target. `on_checkpoint` then runs with the retained count, and a failure record beside the output is deleted. `before_pending_item` is consulted immediately before the provider call, and a refusal ends the run without that call, so the retained output is the partial report.

`_translate_item` builds the `DerivedTranslationInput` from the item, the returned text, `TranslationMethod.MODEL`, the configured provenance model, and the clock. A provider failure other than `RequestNotStarted` writes one `TranslationFailureRecord` through `_write_failure` and re-raises. The record holds `work_key_sha256`, the cell, `source_text_hash`, `translation_model`, `failed_at`, `error_type`, and `error_message`, and `_safe_failure_message` accepts only a short fixed-shape provider message and otherwise returns the exception class name, so neither the source text nor the generated text reaches the file.

`run_translation_command` in `src/course_explorer/translation/commands.py` composes one database context, one `CurriculumRepository`, one `DerivedTranslationRepository`, one `TranslationProvider`, and one `TranslationWorkerService`, and closes the provider before the engine is disposed.

The administrative half lives in `src/course_explorer_admin/translation/`. `TranslationWorkerStage` implements the stage seam of `course_explorer_admin.worker_session`, and `course_explorer_admin.translation.controller_worker` is the module the adapter launches. `_publish_prepared_session` runs the selector on the session database and writes the prepared control and state, `run` owns the runtime and the checkpoint writes, `_retained_output_count` counts the retained output through the strict loader, `_export_worker_output_locked` hashes it into `TranslationControllerOutputManifest`, and `_finalize` imports it through the repository and writes `TranslationControllerImportReceipt`. `_read_import_receipt`, `_stop_updates`, and `_require_cleanup_evidence` keep the recorded counts in step with the retained evidence. The state DTOs are `TranslationControllerPolicy`, `TranslationControllerWorkerState`, `TranslationControllerStatus`, `TranslationControllerOutputManifest`, and `TranslationControllerImportReceipt` in `src/course_explorer_admin/translation/controller.py`, and `translation_stage()` in `src/course_explorer_admin/remote_stages.py` binds the adapter.

## Commands and tests

`scripts/admin.py translation <start|pause|resume|status|stop>` runs one session action through `course_explorer_admin.cli` and `run_translation_lifecycle_command`, and `scripts/admin.py coverage teaching-text` prints the `TeachingTextCoverageReport` of the selected dataset through `run_administrative_coverage`. The operator menu reaches the stage actions and the same report.

`tests/teaching_text/test_teaching_text.py` covers the resolution, the duplicate-key refusal, and the projected coverage read. `tests/teaching_text/test_teaching_text_command.py` covers the file loader. `tests/teaching_text/test_teaching_text_repository.py` is the opt-in PostgreSQL proof of the write path, its refusals, and the staleness report. `tests/translation/test_translation_service.py` covers the selector partition, the reuse rule, and the pending order. `tests/translation/test_translation_provider.py` covers the request shape, the retries, the response contract, and the content-free errors. `tests/translation/test_translation_recovery.py` covers retained-output validation, atomic publication, the failure record, and the lifecycle callbacks. `tests/admin/translation/` covers the prepared session, the shared control path, the one-time import, resumption from retained output, and the cleanup evidence.
