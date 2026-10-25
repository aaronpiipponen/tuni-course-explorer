# Curriculum reads

The read repository serves detached course, module, and period objects to every curriculum feature, and one shared selector chooses each course's representative version.

## The repository and its shared loaders

`src/course_explorer/curriculum.py` holds the frozen, closed read DTOs and the reader protocols. `src/course_explorer/curriculum_repository.py` holds `CurriculumRepository`, which implements `CurriculumRead`, `CurriculumStructureRead`, and `CurriculumDiscoveryRead` over a `sessionmaker[Session]`. Each public read opens its own session, so every returned DTO is detached from the ORM.

`CurriculumRepository._scoped_courses` builds the one activity and identity scope. It selects whole `Course` rows, or the four activity/identity columns when `teaching_only` is set, orders by `Course.group_id`, applies `Course.is_active == active_only` when `active_only` is not `None`, and applies a `group_ids` membership filter when one is given. The remaining loaders build on it.

| Loader | Builds | Used by |
|---|---|---|
| `_load_courses` | `CatalogueCourse` through `_assemble_full_courses`, or `CatalogueTeachingCourse` through `_representative_teaching_texts(include_identity=True)` | `list_courses`, `list_teaching_courses`, `get_courses` |
| `_load_course_summaries` | `RepresentedCourseSummary` or the shared `CourseSummary` | `list_represented_summaries`, `get_represented_summaries`, `get_course_summaries` |
| `_load_modules` | `CatalogueModule`, or `CatalogueModuleLookup` when `lookup_only` is set | `list_modules`, `list_module_lookup`, `get_modules` |
| `_representative_teaching_texts` | `CatalogueRepresentativeTeachingText`, or `CatalogueTeachingCourseVersion` when `include_identity` is set | `list_teaching_courses`, `get_representative_teaching_texts`, `list_teaching_text_inputs` |
| `_module_periods_by_version` | the `CatalogueCurriculumPeriod` tuple of every module version | both module loaders |

The scoped getters (`get_courses`, `get_modules`, `get_course_summaries`, `get_represented_summaries`, `get_course_activities`, `get_representative_teaching_texts`) share those loaders and differ only by identity scope and projection. Each returns `()` before any I/O for an empty scope, and each omits a requested identity that the database does not hold.

`_require_representative_versions` is the one guard that turns a selected representative with no persisted version row into a `ValueError`, and every read that loads representative data calls it.

## The representative selector

`select_representative_source_ids(session, group_ids, *, current_academic_year_start, activity_window_years)` returns one exact source version identity or `None` per requested canonical group. One statement joins `Course`, `CourseVersion`, `CourseVersionCurriculumPeriod`, and `CurriculumPeriod`, keeps memberships with `CurriculumPeriod.academic_year_start <= current_academic_year_start`, groups by `(Course.group_id, CourseVersion.sisu_course_unit_id, CourseVersion.source_modification_ordinal)`, and selects `max(CurriculumPeriod.academic_year_start)` for each group. Python then ranks each row as `(2, year)` for the current academic year, `(1, year)` inside `is_within_activity_window`, and `(0, year)` otherwise, builds the candidate key `(rank, -1 if ordinal is None else ordinal, source_id)`, and keeps the greatest key per group.

`CurriculumRepository._representative_source_ids` groups the scoped courses by their stored `(activity_as_of_academic_year_start, activity_window_years)` pair and calls the selector once per distinct pair, so one read can rank different courses under different recorded windows. `NormalizationRepository.apply` calls the same function over the affected groups before and after applying a batch, and the difference is reported as `representative_changed_course_count`.

The selection rules the operator relies on are described in [Representative versions and activity](/docs/backend/catalogue/representative-versions.md). A change to the preference belongs in `select_representative_source_ids`, a change to the strict and fallback module candidate rules belongs in `module_version_candidates` and `_nearest_module_version`, and a change to the shared summary mapping belongs in `course_summary_from_fields`.

## The read protocols and their consumers

| Protocol | Methods | Consumers |
|---|---|---|
| `CurriculumRead` | `list_courses`, `list_teaching_courses`, `list_teaching_text_inputs`, `list_modules`, `list_module_lookup`, `list_represented_summaries`, `get_represented_summaries`, `list_course_code_identities`, `summary` | `CourseSearchService` and `UnifiedCourseSearchService` (`search/service.py`, `search/unified.py`), `CourseLookupService` (`search/lookup.py`), `run_catalogue_command` (`search/lookup_commands.py`), `TeachingTextService` (`teaching_text/service.py`), the translation selection (`translation/service.py`), the inference operational read (`inference/operational.py`) |
| `CurriculumGraphRead` | `get_courses`, `get_modules` | `PrerequisiteGraphCompiler` (`prerequisite/graph.py`), which requests exactly the identities its traversal discovers |
| `CurriculumStructureRead` | `get_modules`, `get_course_summaries` | `StudyStructureService` (`study_structure/service.py`), which requests the modules and course cards one selected rule tree references |
| `CurriculumDiscoveryRead` | `get_substitution_source_group_ids`, `get_prerequisite_candidate_group_ids` | the next-course command (`next_courses/commands.py`), which then compiles the candidates through the same graph compiler |

`CurriculumDiscoveryRead` extends `CurriculumGraphRead` because discovery compiles graphs over the identities it finds. Both discovery methods return sorted distinct canonical group identities, never payloads, and both are candidate supersets across the stored versions, so the current compiler alone decides real eligibility.

The remaining repository methods are used directly where a consumer needs one narrow projection. `get_course_activities` returns the four activity columns for inference publication and reconciliation, and `summary` returns the `CatalogueSummary`, the [Catalogue summary](/docs/reference/glossary.md#administration) counts, for the operator menu and the dataset verification.

## Period objects and module version selection

`CatalogueCurriculumPeriod` carries the official period identity plus the explicit `academic_year_start`, and `CatalogueModuleVersionIdentity.curriculum_periods` exposes the tuple of those objects per module version. Both module loaders build them in `_module_periods_by_version`, ordered by academic year and then by period identity, so no caller parses a period identity to learn its year.

`module_version_candidates(versions, *, academic_year_start, allow_nearest=False)` returns the versions usable for one academic year and preserves the input order. It returns every version with an exact membership in that academic year. Only when none exists does it consider the membership-free versions whose own `validity_start` and `validity_end` bounds contain the requested year. An empty result is a missing version and more than one result is ambiguous, so this helper selects a candidate set and never an arbitrary winner. Callers that can disclose the fallback opt into `allow_nearest`, which then returns the single nearest dated version through `_nearest_module_version`, choosing the greatest preceding year and otherwise the least following year, and breaking a same-year tie by the greatest `sisu_module_id`. `_fallback_year` supplies each version's comparison year from its best preceding period year, otherwise its nearest following period year, otherwise a validity bound.

| Caller | Call |
|---|---|
| `StudyStructureService._select_version` | strict call, then `no_current_version` or `ambiguous_version` when the set is empty or holds more than one version. An explicit selection outside that set raises `ValueError` and aborts the whole batch |
| `run_catalogue_command` | strict call, omitting a module with no candidate and keeping every eligible candidate of a group with its exact identity, validity bounds and period memberships for the browser's local version selector |
| `PrerequisiteGraphCompiler` | strict call first, then a disclosing `allow_nearest=True` call that records a `MODULE_VERSION_FALLBACK` ignored part |

## The shared course summary

`CourseSummary` is the one official summary every course-returning read reuses, carrying `group_id`, both official names, the representative's official code, the credit range, the active flag, and the official URL. `course_summary(course)` maps it from a full `CatalogueCourse` and raises `ValueError` when the course has no representative. `course_summary_from_fields` is the one mapping used by `_load_course_summaries`, so the projected read and the full read produce the identical DTO. `RepresentedCourseSummary` pairs the summary with the representative's `sisu_course_unit_id` and `source_hash` for consumers that must match durable semantic scores to the current representative.

`PrerequisiteGraphCompiler` calls `course_summary` on full courses, while `StudyStructureService` and the administrative reads use the scoped `get_course_summaries` projection. The catalogue command maps only the narrowing fields from `list_represented_summaries` and `list_module_lookup`, so its report carries no official URL, source hash, rule tree or teaching text. Its module candidates copy the already-projected version identity, validity bounds and period memberships, because the browser must distinguish several eligible versions of one group.

`src/course_explorer/search/projection.py` builds `LookupProjection` from one `list_represented_summaries(active_only=None)` read and one `list_module_lookup` read. The projection retains each official summary with the normalized code and name keys the lexical matchers compare, and it holds no title tokens. `CourseLookupService` consumes its rows for fuzzy, exact-code and substring matching, and `run_catalogue_command` maps the same rows and module identities into the narrowing report.

## Tests

`tests/db/test_curriculum_repository.py` proves the read seam against a normalized database. It asserts the selected representatives and their teaching text, the activity scopes, the agreement between every projected read and the corresponding full read, the SQL statements a projected read issues, the scoped getters, the omission of unknown and unrepresented identities, the module rule trees, and the `CatalogueSummary` counts against direct SQL aggregates. `tests/ingestion/test_normalization_repository.py` and `tests/ingestion/test_normalization_recovery.py` cover the selector through normalization, including the representative-change count, the tie-break fixture where two versions share a year and an absent ordinal, and the representative reselection after a changed version. `tests/search/test_search_service.py`, `tests/search/test_course_lookup.py`, `tests/study_structure/test_study_structure.py`, and the prerequisite tests cover the consumers over the same DTOs.
