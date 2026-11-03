# Structure projection

The structure of studies service projects selected official module versions into container summaries, shared course summaries, and their typed rule trees.

## The read seam

`CurriculumStructureRead` in `src/course_explorer/curriculum.py` is the protocol the service depends on:

- `get_modules(group_ids)` returns the identical full `CatalogueModule` DTOs `list_modules` builds, with their sorted versions.
- `get_course_summaries(group_ids)` returns the shared official `CourseSummary` for the requested canonical courses, omits an unknown or unrepresented identity, and applies no activity filter.

`CurriculumRepository` in `src/course_explorer/curriculum_repository.py` implements both. `CatalogueModule` holds `group_id` and its `versions`. `CatalogueModuleVersion` adds `source_hash`, `target_credits_min`, `target_credits_max`, `document_state`, and the nullable `rule`, and it inherits the identity, names, validity bounds, and `curriculum_periods` memberships.

## The service contract

`StudyStructureService(curriculum, *, academic_year_start)` in `src/course_explorer/study_structure/service.py` holds the batch read.

`read_many(root_group_ids, *, allow_unavailable=False, module_versions=None, fragment_store=None)`:

1. Deduplicates the roots in caller order and normalizes `module_versions` once to a mapping, returning an empty `StudyStructureBatch` before any repository read when the request is empty.
2. Reads every requested module once through `get_modules(tuple_of_roots)`, seeding one `module_map` for the whole call.
3. Projects each root through `_project_root` over one shared `course_summaries` map, so a course card loaded for one root is not read again for another.
4. Collects a `StudyStructureRootUnavailable` identity in `unavailable_root_group_ids` only when `allow_unavailable` is true, and an ambiguous root without a selection in `version_selection_required` regardless of that flag. Every other failure propagates.

`_project_root` selects the one version through `_select_version`, raises `StudyStructureVersionSelectionRequired` when that returns `ambiguous_version`, raises `StudyStructureRootUnavailable` when the identity is absent or the selected version carries no stored rule, and calls `_project_module` with `ancestor_group_ids=(module.group_id,)`.

A single root goes through `run_study_structure_command` in `src/course_explorer/study_structure/commands.py`, which delegates to the batch command. Both maps are request-local and live for the one call, so the service holds no state between reads.

## Models and serialization

`StudyStructureUnresolved` is a `Literal` of the six reasons: `course_not_represented`, `module_not_found`, `no_current_version`, `ambiguous_version`, `missing_rule`, and `module_cycle`.

`StudyStructureRule` subclasses `CatalogueModuleRule`, so it inherits `node_type`, `sibling_position`, `local_id`, `require_min`, `require_max`, `all_mandatory`, `credits_min`, `credits_max`, `count_min`, `count_max`, and `referenced_group_id`. It redeclares `children` as `tuple[StudyStructureRule, ...]`, excludes the inherited `description` field from serialization, and adds `course` (a `CourseSummary` or `None`), `module` (a `StudyStructureModule` or `None`), and `unresolved`. `StudyStructureRule.model_rebuild()` and `StudyStructureModule.model_rebuild()` resolve the mutual reference between the rule and the nested module.

`StudyStructureModule` is frozen with `extra="forbid"` and holds `module` (a `ModuleSummary`), `target_credits_min`, `target_credits_max`, and `rule`.

`StudyStructureReport` in `src/course_explorer/study_structure/commands.py` is frozen with `extra="forbid"` and holds `academic_year_start` and `root`. `StudyStructuresReport` holds `academic_year_start`, `roots`, `unavailable_root_group_ids` and `version_selection_required`, and `StudyStructureBatch` in the service holds the roots and both root settlements.

A projected rule carries the official node identity, so `model_dump_json` of a rule reproduces the source node's fields with the projected `children`, `course`, `module`, and `unresolved` values and without `description`. A `Decimal` bound serializes as a fixed-point JSON string, so `target_credits_min` of 180 reads `"180"` and `credits_min` of 5 reads `"5"`.

## Version selection

`_select_version(module, module_versions)` calls `module_version_candidates(module.versions, academic_year_start=...)` from `src/course_explorer/curriculum.py` with the default `allow_nearest=False`, so the strict candidate set applies: exact academic-year memberships win, and, only when none exists, membership-free versions whose validity bounds contain the requested year are considered. A supplied exact identity must belong to that candidate set, or the read raises `ValueError`. It is never replaced by another version. Without an entry, an empty set returns the reason `no_current_version`, and more than one candidate returns `ambiguous_version`. The service never falls back to a version tied to another year.

The prerequisite graph compiler does not use this helper. The native compiler selects the module version in one call: an exact period membership first, then a validity-bound match, then the nearest dated version, and it records a `module_version_fallback` ignored part naming the requested year and the selected version when it falls back. `tests/study_structure/test_study_structure.py::test_structure_preserves_official_containers_rules_and_courses` covers the strict policy over its `exact_year`, `validity` and `ambiguous_year` scenarios.

## Traversal, course fetching, and cycle detection

`_project_module(module, version, *, ancestor_group_ids, course_summaries, module_map, module_versions)` builds the container and walks the rule tree:

- `_iter_rule_nodes(rule)` yields the nodes of one rule tree in order, starting with its root. `_prefetch_modules` collects the `referenced_group_id` of every `COURSE_UNIT_RULE` it yields and skips a null reference, and it adds the reference of a `MODULE_RULE` to its pending set instead of walking into that module here.
- `_prefetch_modules` follows module-rule references and version candidates to a fixed point, reads every reachable module in batches, and collects every direct course reference. It reads every collected course summary once through `get_course_summaries`, in batches of 1000 when needed, and passes the completed map into the projection. A course the read omits is absent from the map, which the projection reports as `course_not_represented`.
- `_project_rule(rule, ...)` copies the official fields with `rule.model_dump(exclude={"children", "description"})` and then resolves the one reference the node carries. A `COURSE_UNIT_RULE` takes its summary from the map. A `MODULE_RULE` takes a nested module. Every other node rebuilds its `children` in order.

`_resolve_nested_module(rule, *, ancestor_group_ids, course_summaries, module_map, module_versions)` classifies a module reference:

- A null reference is `module_not_found`.
- A reference already in `ancestor_group_ids` is `module_cycle`, so the walk stops at the repeated module.
- `_load_module(group_id, module_map)` reads an unloaded identity once through `get_modules` and stores the result, including a negative result, so a repeated reference is not read again. A missing module is `module_not_found`.
- The referenced module's version selection runs the same explicit-or-sole policy under the request's map, and an absent selection whose group is ambiguous keeps the typed reason on the node.
- A selected version with no rule is `missing_rule`.
- Otherwise the module is projected with the reference appended to `ancestor_group_ids`.

Cycle detection reads the ancestor path alone, so the same module referenced in two separate branches is projected in both, and a reference that closes a loop over its own ancestors is reported once at the closing node.

## Study fragments

The serving-artifact build writes one fragment file for the serving database and academic year. It
holds one entry per canonical module root: the projected root payload, an unavailable marker or a
version-selection marker. The build reads every root through the batched service with
`allow_unavailable=True` and records the root count, the projectable count, the two marker counts, the
file size and the build cost. A web read passes `cache.artifacts.study_fragments`, and the service
answers a root the file holds unless the request supplies explicit module versions. A root absent from
the file, or any explicit version selection, uses the batched read path. A missing fragment file
raises at artifact open and names `scripts/admin.py serving-artifacts`.

## Failure boundaries

Four root outcomes belong to one root alone, and each is a `ValueError`:

| Condition | Message content |
|---|---|
| The root identity is unknown | `unknown module <identity> for academic year <year>` |
| The root has no version | `module <identity> has no unique current version for academic year <year>: <reason>` |
| The root has several versions and no explicit selection | `module <identity> has several current versions for academic year <year> and no explicit selection` |
| The selected root version has no rule | `module <identity> version <sisu_module_id> has no stored rule` |

A batch settles each root's own identity, missing-version and selection-required outcome separately, and `allow_unavailable` decides whether a root it cannot provide is listed as unavailable or aborts the batch. An explicit selection that is not eligible for its group is neither of those: it raises `ValueError` from the version-selection step, so the whole batch aborts even when unavailable roots are allowed.

Every further failure is data, except an explicit identity outside its group's eligible set, which propagates as a `ValueError` even when unavailable roots are collected. A nested module reference, a nested version selection, and a nested rule lookup all resolve to a typed reason on the node, and a course reference without a summary resolves to `course_not_represented`. An unresolved node keeps its official fields, so a reader sees the rule and its reason together.

## The command and the CLI

`run_study_structures_command(root_group_ids, *, allow_unavailable=False, module_versions=None, fragment_store=None, database_settings=None, academic_year_start=None, session_factory=None)` in `src/course_explorer/study_structure/commands.py` rejects a blank root with `ValueError` before any settings load. A supplied academic year is used as given, and otherwise the command reads `load_normalization_settings().current_academic_year_start` once. It resolves one database connection, constructs the service over `CurriculumRepository`, calls `read_many` once with the selection map and the supplied fragment store, and returns the report including `version_selection_required`.

A supplied session factory is used as the session factory and is never disposed here, so its owner disposes the engine. `run_study_structure_command(root_group_id, *, module_versions=None)` delegates to the batch and raises `StudyStructureVersionSelectionRequired` when its sole root needs a selection instead of indexing an empty roots tuple.

`scripts/study_structure.py` takes one positional `root_group_id`, repeatable `--module-version GROUP_ID=VERSION_ID` selections and prints `report.model_dump_json()` as one line. It rejects a duplicate group argument. `POST /api/study-structure` accepts `root_group_ids`, `module_versions` and `allow_unavailable` and returns the batch report with the serving dataset identity.

## Tests

| File | Covers |
|---|---|
| `tests/study_structure/test_study_structure.py` | The full structure over an in-memory read for the exact-year and validity selection, every inherited official field and the child order of the whole tree, the nested module and its inactive course, the choice bounds, the credits and count ranges, the unrestricted rules, the excluded `description`, fixed-point decimal serialization, and the report round-trip. The degree and study roots are read as one batch over shared maps. It also covers a missing nested course, a missing nested module, an ambiguous nested year, an ancestor cycle, an unknown root, and an ambiguous root in strict and allowed-unavailable modes. It proves an explicit root-and-nested pair selects the exact official content, and that a foreign or ineligible-year identity is refused even when unavailable roots are collected. It also builds the fragment file and proves a fragment hit reads no module or summary, an explicit version selection bypasses the fragment, and unavailable and version-selection markers answer without a batch read. |
| `tests/study_structure/test_study_structure_command.py` | The blank root refused before any settings load, the batch map forwarded to the service, the single-root CLI delegating one root, its repeatable selections and duplicate-group refusal, and a rejected unknown argument. |

The behaviour as the app presents it is described in [Structure of studies in the catalogue](/docs/backend/catalogue/study-structure.md).
