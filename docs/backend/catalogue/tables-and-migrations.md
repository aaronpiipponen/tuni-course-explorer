# Tables and migrations

Two separate schema owners build a curriculum database and the feedback application store's database from their own Alembic migration chains.

The curriculum tables are declared as SQLAlchemy models in the `course_explorer.db.models` module, and one Alembic chain in the `migrations/` directory builds and changes the curriculum schema. A separate feedback application store schema declares its own metadata in `src/course_explorer/feedback/models.py` and has its own migration chain under `migrations_feedback/`.

## Conventions

`Base` in `src/course_explorer/db/models.py` is a `DeclarativeBase` carrying `NAMING_CONVENTION` on its `MetaData`, so a primary key, unique constraint, check constraint, foreign key, or index without an explicit name gets the conventional one. `FeedbackBase` in `src/course_explorer/feedback/models.py` declares the same convention values on its own `MetaData`.

`_enum(enum_type, name)` stores the declared enum values in a text column with a check constraint (`native_enum=False`, `create_constraint=True`), and its `values_callable` stores each member's value, so the allowed values live in the constraint rather than in a PostgreSQL enum type. `_not_blank(column)` adds the standard `btrim(column) <> ''` check. Closed sets that are not enumerations, such as the processing cycle stage, the failure reason, and the operator disposition, carry a literal check of their own. Every SHA-256 column carries a `~ '^[0-9a-f]{64}$'` check, except `source_snapshots.source_hash`, which carries the non-blank check only, and `course_embedding_search_groups.representative_source_hash`, which carries no check of its own.

Primary keys are `UUID` columns with a Python-side `uuid.uuid4` default, except `curriculum_periods.id`, which is the text identifier the source publishes, `course_texts`, keyed by `course_version_id`, `inference_course_processing`, keyed by `course_id`, and the composite keys on `course_version_curriculum_periods`, `module_version_curriculum_periods`, `inference_processing_targets`, and `course_embedding_neighbors`, whose two UUID key columns carry no default. `course_embedding_centroids` is keyed by the text `group_id` that references `courses.group_id`, `course_embedding_search_groups` and `course_embedding_search_blocks` by their integer `group_no` and `block_no`, and `course_embedding_search_meta` by the boolean `one_row`.

Timestamps are `DateTime(timezone=True)`. The `created_at`, `published_at`, and `started_at` columns carry a `now()` server default, and a table whose rows are updated in place also carries `updated_at` with `onupdate=now()`. The remaining timestamp columns carry no default: `derived_course_texts.generated_at`, `inferred_prerequisite_sets.generated_at`, `inferred_equivalence_groups.generated_at`, `inference_model_attempts.finished_at`, `ingestion_runs.finished_at`, and `course_embedding_chunks.translation_generated_at` are written by the code.

## Tables

### Capture records

| Model | Table | Key columns | Unique constraints and foreign keys |
|---|---|---|---|
| `IngestionRun` | `ingestion_runs` | `id`, `status`, `started_at`, `finished_at`, `raw_root_path`, `manifest_path` | `raw_root_path` and `manifest_path` non-blank |
| `SourceSnapshot` | `source_snapshots` | `id`, `ingestion_run_id`, `object_type`, `source_object_id`, `source_group_id`, `response_path`, `response_item_index`, `source_hash` | `uq_source_snapshots_response_position` on `(ingestion_run_id, response_path, response_item_index)`, an index on `(object_type, source_object_id)`, and `ingestion_run_id` referencing `ingestion_runs.id` with `RESTRICT` |

### Official catalogue

| Model | Table | Key columns | Unique constraints and foreign keys |
|---|---|---|---|
| `CurriculumPeriod` | `curriculum_periods` | `id`, `academic_year_start` | `id` non-blank, `academic_year_start > 0` |
| `Course` | `courses` | `id`, `group_id`, `first_listed_academic_year_start`, `last_listed_academic_year_start`, `is_active`, `activity_as_of_academic_year_start`, `activity_window_years` | `group_id` unique, the listed years ordered, the activity year and window positive |
| `CourseVersion` | `course_versions` | `id`, `course_id`, `sisu_course_unit_id`, `code`, `name_fi`, `name_en`, `credits_min`, `credits_max`, `official_url`, `document_state`, `validity_start`, `validity_end`, `source_revision`, `source_modification_ordinal`, `source_snapshot_id` | `sisu_course_unit_id` and `source_snapshot_id` unique, `course_id` referencing `courses.id` and `source_snapshot_id` referencing `source_snapshots.id` with `RESTRICT`, credits nonnegative and ordered, validity dates ordered, `source_revision` and `source_modification_ordinal` nonnegative |
| `CourseVersionCurriculumPeriod` | `course_version_curriculum_periods` | `course_version_id` and `curriculum_period_id` (composite primary key) | `course_version_id` referencing `course_versions.id` with `CASCADE`, `curriculum_period_id` referencing `curriculum_periods.id` with `RESTRICT` |
| `Module` | `modules` | `id`, `group_id` | `group_id` unique |
| `ModuleVersion` | `module_versions` | `id`, `module_id`, `sisu_module_id`, `module_type`, `code`, `name_fi`, `name_en`, `target_credits_min`, `target_credits_max`, `document_state`, `validity_start`, `validity_end`, `source_revision`, `source_modification_ordinal`, `source_snapshot_id` | `sisu_module_id` and `source_snapshot_id` unique, `module_id` referencing `modules.id` and `source_snapshot_id` referencing `source_snapshots.id` with `RESTRICT`, target credits nonnegative and ordered, validity dates ordered |
| `ModuleVersionCurriculumPeriod` | `module_version_curriculum_periods` | `module_version_id` and `curriculum_period_id` (composite primary key) | `module_version_id` referencing `module_versions.id` with `CASCADE`, `curriculum_period_id` referencing `curriculum_periods.id` with `RESTRICT` |
| `ModuleRuleNode` | `module_rule_nodes` | `id`, `module_version_id`, `parent_node_id`, `sibling_position`, `local_id`, `node_type`, `require_min`, `require_max`, `all_mandatory`, `description`, `credits_min`, `credits_max`, `count_min`, `count_max`, `referenced_group_id` | `uq_module_rule_nodes_parent_sibling_position` on `(parent_node_id, sibling_position)`, `uq_module_rule_nodes_id_module_version_id` on `(id, module_version_id)` to back the parent reference, the partial unique index `uq_module_rule_nodes_root` on `module_version_id` where `parent_node_id IS NULL`, the composite foreign key `fk_module_rule_nodes_parent_same_module` from `(parent_node_id, module_version_id)` to `(id, module_version_id)` with `CASCADE`, `module_version_id` referencing `module_versions.id` with `CASCADE`, each bound pair nonnegative and ordered, and `referenced_group_id` present exactly on `CourseUnitRule` and `ModuleRule` nodes |
| `OfficialPrerequisiteOption` | `official_prerequisite_options` | `id`, `target_course_version_id`, `option_index`, `requirement_kind` | `uq_prerequisite_options_target_kind_position` on `(target_course_version_id, requirement_kind, option_index)`, `target_course_version_id` referencing `course_versions.id` with `CASCADE` |
| `OfficialPrerequisiteOptionMember` | `official_prerequisite_option_members` | `id`, `prerequisite_option_id`, `member_index`, `member_type`, `referenced_group_id` | `uq_prerequisite_members_option_position` on `(prerequisite_option_id, member_index)`, `prerequisite_option_id` referencing `official_prerequisite_options.id` with `CASCADE` |
| `OfficialSubstitutionOption` | `official_substitution_options` | `id`, `source_course_version_id`, `option_index` | `uq_substitution_options_source_position` on `(source_course_version_id, option_index)`, `source_course_version_id` referencing `course_versions.id` with `CASCADE` |
| `OfficialSubstitutionOptionMember` | `official_substitution_option_members` | `id`, `substitution_option_id`, `member_index`, `course_group_id`, `credits` | `uq_substitution_members_option_position` on `(substitution_option_id, member_index)`, `substitution_option_id` referencing `official_substitution_options.id` with `CASCADE`, `credits` nonnegative when present |

### Teaching text

| Model | Table | Key columns | Unique constraints and foreign keys |
|---|---|---|---|
| `CourseText` | `course_texts` | `course_version_id`, `content_fi`, `content_en`, `outcomes_fi`, `outcomes_en`, `prerequisite_text_fi`, `prerequisite_text_en`, `additional_info_fi`, `additional_info_en` | `course_version_id` is the primary key and references `course_versions.id` with `CASCADE` |
| `DerivedCourseText` | `derived_course_texts` | `id`, `course_version_id`, `field`, `language`, `text`, `source_language`, `source_text_hash`, `translation_method`, `translation_model`, `generated_at` | `uq_derived_course_texts_version_field_language` on `(course_version_id, field, language)`, `course_version_id` referencing `course_versions.id` with `CASCADE`, `text` and the hash non-blank, the hash a 64-character SHA-256, source and target language different, and the model identity present exactly for a model translation |

### Embeddings

| Model | Table | Key columns | Unique constraints and foreign keys |
|---|---|---|---|
| `CourseEmbeddingChunk` | `course_embedding_chunks` | `id`, `course_version_id`, `field`, `language`, `chunk_index`, `text_origin`, `text`, `representative_source_hash`, `effective_text_hash`, `source_text_hash`, `chunk_text_hash`, `embedding_model`, `embedding_artifact_sha256`, `embedding_configuration_hash`, `translation_method`, `translation_model`, `translation_generated_at`, `status`, `embedding`, `updated_at` | `uq_course_embedding_chunks_version_field_language_index` on `(course_version_id, field, language, chunk_index)`, the HNSW index `ix_course_embedding_chunks_embedding_hnsw` over `embedding` with `vector_cosine_ops` and `m` 16 and `ef_construction` 64, `embedding` a `Vector(1024)` column whose dimension is `COURSE_EMBEDDING_DIMENSION` in `src/course_explorer/constants.py`, `course_version_id` referencing `course_versions.id` with `CASCADE`, every hash a 64-character SHA-256, the origin provenance consistent with the translation columns, and the lifecycle consistent: `completed` carries a vector and `pending` and `failed` carry none |
| `CourseEmbeddingNeighbor` | `course_embedding_neighbors` | `query_chunk_id`, `target_chunk_id`, `score` | `query_chunk_id` and `target_chunk_id` form the primary key, both chunk identities reference `course_embedding_chunks.id` with `CASCADE`, and `score` is a cosine in `[-1, 1]` |
| `CourseEmbeddingSearchGroup` | `course_embedding_search_groups` | `group_no`, `group_id`, `sisu_course_unit_id`, `representative_source_hash` | `group_no` is the primary key and `(group_id, sisu_course_unit_id, representative_source_hash)` is unique |
| `CourseEmbeddingSearchBlock` | `course_embedding_search_blocks` | `block_no`, `n`, `groups`, `norms`, `vectors` | `block_no` is the primary key, `n` is from 1 to 128, and `vectors` uses external storage |
| `CourseEmbeddingSearchMeta` | `course_embedding_search_meta` | `one_row`, `group_count` | `one_row` is the primary key and is true, and `group_count` is positive |
| `CourseEmbeddingCentroid` | `course_embedding_centroids` | `group_id`, `sisu_course_unit_id`, `representative_source_hash`, `embedding_configuration_hash`, `chunk_count`, `centroid`, `updated_at` | `group_id` is the primary key and references `courses.group_id` with `CASCADE`, `centroid` is a `bytea` of exactly 8192 bytes, `chunk_count` is positive, every hash is a 64-character SHA-256, and `sisu_course_unit_id` is non-blank |

### Inferred data

| Model | Table | Key columns | Unique constraints and foreign keys |
|---|---|---|---|
| `InferredPrerequisiteSet` | `inferred_prerequisite_sets` | `id`, `target_course_id`, `activity_as_of_academic_year_start`, `activity_window_years`, `coverage_state`, `eligible_source_count`, `processed_source_count`, `accepted_source_count`, `producer_kind`, `producer_name`, `producer_version`, `input_hash`, `payload_hash`, `expression`, `generated_at`, `published_at` | `uq_inferred_prerequisite_sets_target_course_id` on `target_course_id`, `target_course_id` referencing `courses.id` with `CASCADE`, the producer names non-blank, both hashes 64-character SHA-256 values, the counts ordered and nonnegative, the coverage state consistent with the counts, and the expression present exactly when the accepted count is positive |
| `InferredEquivalenceGroup` | `inferred_equivalence_groups` | `id`, `producer_kind`, `producer_name`, `producer_version`, `input_hash`, `payload_hash`, `inference`, `generated_at`, `published_at` | The producer names non-blank and both hashes 64-character SHA-256 values |
| `InferredEquivalenceGroupMember` | `inferred_equivalence_group_members` | `id`, `equivalence_group_id`, `course_id`, `activity_as_of_academic_year_start`, `activity_window_years` | `uq_inferred_equivalence_group_members_group_course` on `(equivalence_group_id, course_id)`, `equivalence_group_id` referencing `inferred_equivalence_groups.id` and `course_id` referencing `courses.id`, both with `CASCADE` |

### Inference pipeline state

| Model | Table | Key columns | Unique constraints and foreign keys |
|---|---|---|---|
| `InferencePipelineRun` | `inference_pipeline_runs` | `id`, `model_identity`, `runtime_identity`, `prompt_version`, `schema_version`, `pipeline_version`, `run_identity_sha256`, `configuration` | The identities non-blank and the run identity a 64-character SHA-256 |
| `InferenceTargetWork` | `inference_target_work` | `id`, `created_by_run_id`, `target_course_id`, `activity_as_of_academic_year_start`, `activity_window_years`, `work_key_sha256`, `status` | `uq_inference_target_work_target_work_key` on `(target_course_id, work_key_sha256)`, the index `ix_inference_target_work_status` on `status`, `created_by_run_id` referencing `inference_pipeline_runs.id` and `target_course_id` referencing `courses.id`, both with `RESTRICT` |
| `InferenceModelAttempt` | `inference_model_attempts` | `id`, `target_work_id`, `request_payload`, `finished_at` | `target_work_id` referencing `inference_target_work.id` with `RESTRICT` |
| `InferenceProposal` | `inference_proposals` | `id`, `target_course_id`, `source_attempt_id`, `proposal_version`, `identity_sha256`, `expression`, `equivalence` | `uq_inference_proposals_identity_sha256` on `identity_sha256`, `target_course_id` referencing `courses.id` and `source_attempt_id` referencing `inference_model_attempts.id`, both with `RESTRICT` |
| `InferenceCourseProcessing` | `inference_course_processing` | `course_id`, `teaching_text_sha256`, `processed`, `was_active`, `accepted_proposal_id`, `generation_attempt_count`, `disposition` | `course_id` is the primary key and references `courses.id` with `RESTRICT`, `accepted_proposal_id` references `inference_proposals.id` with `RESTRICT` and is nullable, the text hash a 64-character SHA-256, the counter nonnegative, and the disposition null or one of `done` and `failed` |
| `InferenceProcessingCycle` | `inference_processing_cycles` | `id`, `input_sha256`, `stage`, `created_at` | The index `ix_inference_processing_cycles_created_at` on `(created_at, id)`, the input a 64-character SHA-256, and the stage one of `multiview`, `rerank`, `inference`, `publication`, and `complete` |
| `InferenceProcessingTarget` | `inference_processing_targets` | `cycle_id` and `target_course_id` (composite primary key), `multiview_state`, `rerank_state`, `inference_state`, `pool_input`, `target_input`, `generation_work_key_sha256`, `generation_started`, `proposal_id`, `error_type` | `cycle_id` referencing `inference_processing_cycles.id`, `target_course_id` referencing `courses.id`, and `proposal_id` referencing `inference_proposals.id`, all with `RESTRICT`, `multiview_state` one of `pending`, `completed`, and `failed`, `rerank_state` and `inference_state` one of `pending`, `completed`, `skipped`, and `failed`, the generation work key a 64-character SHA-256 when present, and the error type a safe identifier at most 200 characters |
| `InferenceTargetFailure` | `inference_target_failures` | `id`, `cycle_id`, `target_course_id`, `stage`, `attempt_count`, `error_type`, `reason`, `exhausted`, `created_at` | The composite foreign key `fk_inference_target_failures_target` from `(cycle_id, target_course_id)` to `(cycle_id, target_course_id)` of `inference_processing_targets` with `RESTRICT`, the index `ix_inference_target_failures_cycle_target_created` on `(cycle_id, target_course_id, created_at, id)`, the stage one of `multiview`, `rerank`, `inference_preparation`, and `inference`, the attempt count positive, the error type a safe identifier, and the reason one of the 10 allowed values |

## Enumerations

`src/course_explorer/enums.py` is database-independent, and the ORM, ingestion, inference, and service modules import these values from it.

| Enumeration | Values | Columns |
|---|---|---|
| `IngestionRunStatus` | `running`, `completed`, `failed` | `ingestion_runs.status` |
| `SourceObjectType` | `course_unit`, `module` | `source_snapshots.object_type` |
| `ModuleType` | `DegreeProgramme`, `StudyModule`, `GroupingModule` | `module_versions.module_type` |
| `PrerequisiteRequirementKind` | `compulsory`, `recommended` | `official_prerequisite_options.requirement_kind` |
| `PrerequisiteMemberType` | `course`, `module` | `official_prerequisite_option_members.member_type` |
| `ModuleRuleType` | `CompositeRule`, `CreditsRule`, `CourseUnitCountRule`, `CourseUnitRule`, `ModuleRule`, `AnyCourseUnitRule`, `AnyModuleRule` | `module_rule_nodes.node_type` |
| `TeachingTextField` | `name`, `content`, `outcomes` | `derived_course_texts.field`, `course_embedding_chunks.field` |
| `TeachingTextLanguage` | `fi`, `en` | `derived_course_texts.language`, `derived_course_texts.source_language`, `course_embedding_chunks.language` |
| `TranslationMethod` | `manual`, `model` | `derived_course_texts.translation_method`, `course_embedding_chunks.translation_method` |
| `TeachingTextOrigin` | `official`, `derived` | `course_embedding_chunks.text_origin` |
| `CourseEmbeddingStatus` | `pending`, `completed`, `failed` | `course_embedding_chunks.status` |
| `InferredCoverageState` | `partial`, `complete` | `inferred_prerequisite_sets.coverage_state` |
| `InferredProducerKind` | `test`, `inference` | `inferred_prerequisite_sets.producer_kind`, `inferred_equivalence_groups.producer_kind` |
| `InferenceWorkStatus` | `pending`, `completed`, `failed` | `inference_target_work.status` |

The module also declares `InferenceRunStatus` and `InferenceAttemptStatus`, and the table above lists every enum-mapped column. The values are persisted and recorded in provenance identities, so changing a member's value changes stored bytes.

## Sessions

`src/course_explorer/db/session.py` owns every engine and transaction lifetime.

| Helper | Behavior |
|---|---|
| `create_database_engine(settings)` | Builds one engine from the `sqlalchemy_url` property of a settings value that implements `DatabaseConnectionSettings` with `pool_pre_ping=True` |
| `create_session_factory(engine)` | Builds a `sessionmaker` with `expire_on_commit=False`, so a caller can read loaded attributes after a successful commit |
| `database_context(settings, *, factory=None)` | Yields one session factory for any `DatabaseConnectionSettings` value. A supplied `factory` is yielded as given, and its engine lifetime belongs to the caller. Without one, the context builds an engine and disposes it when the caller exits, including on an exception |
| `session_scope(factory)` | Opens `factory.begin()`, commits successful work, and rolls back a raised exception |

`DatabaseConnectionSettings` is a protocol with one read-only `sqlalchemy_url` property. `DatabaseSettings` and `FeedbackSettings` each satisfy it with their own connection components, so the runtime callers and their arguments are the same for both databases.

## The feedback application store schema

The feedback application store schema lives in a separate database and owns two tables. `FeedbackBase` in `src/course_explorer/feedback/models.py` carries their metadata, and `alembic_feedback.ini` points its `script_location` at `migrations_feedback/`. The chain has the single head `20261103_feedback_0004`, and `require_feedback_schema` in `src/course_explorer/feedback/schema.py` refuses a database whose current heads differ from it or a repository that exposes more than one head.

| Model | Table | Key columns | Constraints |
|---|---|---|---|
| `FeedbackSubmission` | `feedback_submissions` | `id`, `created_at`, `answers`, `public_issue`, `publication_state`, `issue_url`, `publication_failure` | `id` is the primary key, `created_at` carries a `now()` server default, `answers` is nonnull JSONB, `issue_url` and `publication_failure` are nullable text, and the named check `current_publication_state` permits `private` for an opted-out row and `pending`, `uncertain`, `published`, `partial` or `failed` for an opted-in row |
| `FeedbackAttachment` | `feedback_attachments` | `id`, `feedback_id`, `field_id`, `filename`, `mime_type` | `id` is the primary key, `feedback_id` references `feedback_submissions.id` with `CASCADE`, the named check `mime_type_valid` permits `image/png` and `image/jpeg`, and the named check `filename_present` requires a nonempty submitted filename |

The Python service generates both identities before it writes, so the tables carry no identity default. `answers` holds only configured non-attachment field IDs and their stored string or null values. Attachment associations and their submitted filenames live in `feedback_attachments` alone. The extension revision backfills the filename of rows written before it from their generated identity. The submission row holds the explicit publication choice, its current state, the created issue link and one safe current failure. It carries no attempt history, claim token or dispatch field. A migration that changes the feedback application store schema is a revision in `migrations_feedback/versions/`.

`FeedbackService.list_submissions` reads the current feedback definition and selects rows in PostgreSQL: each supplied select filter is one JSONB text predicate, every text and textarea field is one escaped case-insensitive containment predicate, and one CASE expression ranks the earliest matching field in definition order. The order continues by `created_at DESC, id DESC`, so a submission appears once and same-group ties are newest first. Attachment metadata for the selected identities is fetched in one scoped query, and `get` and the listing share one projection.

`read_attachment` requires both the submission and attachment identities and returns standard base64 of the stored bytes with no filesystem path. `delete` reads exactly the named submission and its metadata, removes the owned files through `AttachmentStore.discard_submission`, deletes the row in the same transaction and reports success after the commit. The field directory and the attachment root belong to the feedback application store, and every other submission is untouched. File removal and the database commit are not one transaction: a file failure can leave a partial removal, and a database failure after file removal can leave the row, so both failures propagate.

Apply the chain to the database that `config/feedback.toml` names:

```bash
uv run python -m alembic -c alembic_feedback.ini upgrade head
```

The revision `20261027_feedback_0001` creates the two tables and their constraints. The revision `20261027_feedback_0002` adds the nullable `issue_url` and `publication_failure` columns and replaces the initial-choice check with the current-state check, preserving every stored row. The revision `20261103_feedback_0003` backfills the submitted filename of the rows written before it from their generated identity. The revision `20261103_feedback_0004` drops the stored byte size column and its check, and its downgrade raises. Each downgrade raises a `RuntimeError` rather than dropping retained feedback.

## Curriculum migration chain

`migrations/versions/` holds one file per revision, `alembic.ini` points `script_location` at `migrations`, and `migrations/env.py` takes `Base.metadata` from `course_explorer.db.models` as the schema authority. The chain, oldest first:

1. `20260910_0001` creates the `vector` extension and the initial tables: courses, curriculum periods, ingestion runs, source snapshots, course and module versions, course texts, both curriculum-period membership tables, module rule nodes, and the official prerequisite and substitution option tables.
2. `20260911_0002` makes `course_versions.credits_max` nullable for a source-unbounded maximum. Its downgrade refuses while an unbounded value exists.
3. `20260912_0003` creates `derived_course_texts` with its provenance constraints.
4. `20260912_0004` creates `course_embedding_chunks` with its hashes, origin and lifecycle checks, and the vector column.
5. `20260914_0005` creates `inferred_prerequisite_sets`.
6. `20260915_0006` creates `inferred_equivalence_groups` and `inferred_equivalence_group_members`.
7. `20260915_0007` adds the explicit required category to every stored inferred occurrence and recomputes each canonical payload hash.
8. `20260917_0008` creates the cosine HNSW index over `course_embedding_chunks.embedding`.
9. `20260917_0009` creates `inference_pipeline_runs`, `inference_target_work`, and `inference_model_attempts`.
10. `20260929_0010` links the preceding and following revisions and performs no schema or data change.
11. `20260929_0011` creates `inference_proposals` with its unique identity hash.
12. `20260930_0012` creates `inference_course_processing`, `inference_processing_cycles`, and `inference_processing_targets`.
13. `20261007_0013` creates `inference_target_failures` and its index.
14. `20261008_0014` drops the run lifecycle and identity columns, the target-work attempt columns, the attempt telemetry columns, the proposal diagnostics, the per-cycle payload and timestamp columns, and the target-checkpoint payload, stage-order, and failure checks. Its downgrade raises.
15. `20261008_0015` drops the embedding attempt telemetry columns, re-creates the chunk lifecycle check, and drops the source snapshot capture time. Its downgrade raises.
16. `20261012_0016` adds `inference_course_processing.generation_attempt_count` and `inference_processing_targets.generation_started`, both with a default and non-null.
17. `20261012_0017` adds the nullable `inference_course_processing.disposition` column and its closed choice check.
18. `20261014_0018` widens the `inference_target_failures.reason` check with `context_exceeded`.
19. `20261025_0019` drops the run prompt-content and schema hashes and the target-work input hash with their checks. Its downgrade raises.
20. `20261027_0020` creates `course_embedding_centroids` with its representative, configuration and hub hashes, its positive chunk count and its fixed-size centroid. Its downgrade drops the derived table.
21. `20261028_0021` creates `course_embedding_neighbors` with its composite key and its two cascading chunk references. Its downgrade drops the derived table.
22. `20261028_0022` installs the `course_embedding_search` extension, creates the three tables of the packed search relation, and drops the `hub_sha256` column and its format check from `course_embedding_centroids`. A centroid row carries no hub digest, because the hub pair of the serving artifact build is the one hub identity a read uses. Its downgrade restores the nullable digest column and its check, then drops the search tables and the extension.
23. `20261103_0023` drops `course_embedding_neighbors.rank` and its check and re-keys the derived table on `(query_chunk_id, target_chunk_id)`. Its downgrade recomputes the rank from the stored score order and restores the old key.

The curriculum head is `20261103_0023`. A revision that cannot restore the data it removes raises instead of dropping rows, so `20261008_0014`, `20261008_0015`, and `20261025_0019` apply in one direction only.

## Adding a migration

1. Create the revision:
   ```bash
   uv run python -m alembic revision -m "add x"
   ```
   The file written under `migrations/versions/` records the single current head in `down_revision`. A feedback revision uses `uv run python -m alembic -c alembic_feedback.ini revision -m "add x"` and is written under `migrations_feedback/versions/`.
2. Fill `upgrade()` and `downgrade()` with explicit operations, following the surrounding files. A `downgrade()` that cannot restore the data raises a `RuntimeError` with the reason, as `20261008_0014`, `20261008_0015`, `20261025_0019` and the feedback revision do.
3. Change the owning models in the same step: `src/course_explorer/db/models.py` for the curriculum chain, whose `Base.metadata` `migrations/env.py` uses, and `src/course_explorer/feedback/models.py` for the feedback chain, whose `FeedbackBase.metadata` `migrations_feedback/env.py` uses.
4. Keep one head per chain. `require_database_schema` in `src/course_explorer/datasets.py` checks the curriculum chain, `require_feedback_schema` in `src/course_explorer/feedback/schema.py` checks the feedback chain, and each raises when its repository exposes more than one head or its database holds another revision.
5. Apply the chain:
   ```bash
   uv run python -m alembic upgrade head
   uv run python -m alembic -c alembic_feedback.ini upgrade head
   ```
   `migrations/env.py` and `migrations_feedback/env.py` resolve their own target database through their settings loader, unless the caller publishes a connection under `config.attributes["connection"]`, which is how the tests migrate a connection they already own.

## Schema tests

The tests are marked `integration` and run against disposable `_test` databases. The curriculum tests use the database that `tests/conftest.py` migrates and truncates. The feedback tests use `tests/feedback/conftest.py`, which creates one database through `tests/support/database.py`, applies the feedback head and drops that database when the test ends.

| File | Covers |
|---|---|
| `tests/db/_schema_support.py` | The `integrity_records` and `two_course_versions` fixtures and the `derived_text_row`, `embedding_chunk_row`, and `inferred_set_row` builders |
| `tests/db/test_database_schema.py` | Table set parity with `Base.metadata.tables`, the installed `vector` extension, the additive column types and defaults, head reapplication that preserves markers, failures and decisions, the fresh chain built from `template0` over a supplied connection, the identity-column migration over populated results with its irreversible 0019 refusal, and the commit and rollback contract of `session_scope` |
| `tests/embeddings/test_centroid_repository.py` | The complete replacement of the centroid set in one transaction, and the stored row's representative identity, configuration hash, chunk count and 8192-byte centroid |
| `tests/feedback/conftest.py` | The feedback `_test` database migrated through `alembic_feedback.ini` and the temporary attachment root |
| `tests/feedback/test_feedback_service.py` | The feedback-only table set, the feedback head, the absent `vector` extension and the curriculum-metadata disjointness in `test_feedback_schema_is_independent_of_curriculum`, the preserved rows and null new outcomes of the feedback revision, the stored submission round trip through a freshly composed service, the refusal of invalid answers with no row or file, the refusal of malformed, truncated, oversized and excess uploads with no row or file, configured text-order search without duplicates, combined filters over every select, and the scoped attachment read and named deletion of one submission |
| `tests/db/test_curriculum_repository.py` | Normalization into the real schema and the catalogue read seam over it, including the unique source identity and the same-module parent rule |
| `tests/db/test_inferred_schema.py` | The category migration and the inferred set constraints, including a refused downgrade beside a recommended occurrence |
| `tests/db/test_teaching_embedding_schema.py` | The derived text provenance constraints, the chunk origin and lifecycle constraints, the vector dimension, and the cascade with a deleted course version |

`tests/conftest.py` provides the `database` fixture (one migrated, truncated test database) and the `migration_config` fixture, which binds an Alembic config to a caller-owned connection so every in-test upgrade and downgrade reuses the credential that connection already resolved.
