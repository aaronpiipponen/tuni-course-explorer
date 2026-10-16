# Structure projection

The structure of studies service projects one selected official module version into container summaries, shared course summaries, and its typed rule tree.

## The read seam

`CurriculumStructureRead` in `src/course_explorer/curriculum.py` is the protocol the service depends on:

- `get_modules(group_ids)` returns the identical full `CatalogueModule` DTOs `list_modules` builds, with their sorted versions.
- `get_course_summaries(group_ids)` returns the shared official `CourseSummary` for the requested canonical courses, omits an unknown or unrepresented identity, and applies no activity filter.

`CurriculumRepository` in `src/course_explorer/curriculum_repository.py` implements both. `CatalogueModule` holds `group_id` and its `versions`. `CatalogueModuleVersion` adds `source_hash`, `target_credits_min`, `target_credits_max`, `document_state`, and the nullable `rule`, and it inherits the identity, names, validity bounds, and `curriculum_periods` memberships.

## The service contract

`StudyStructureService(curriculum, *, academic_year_start)` in `src/course_explorer/study_structure/service.py` holds one read method.

`read(root_group_id)`:

1. Reads the root through `get_modules((root_group_id,))` and raises `ValueError` when the identity is absent.
2. Selects the one version through `_select_version`.
3. Raises `ValueError` when the selected version carries no stored rule.
4. Calls `_project_module` with `ancestor_group_ids=(module.group_id,)`, an empty `course_summaries` map, and a `module_map` seeded with the root module.

Both maps are request-local and live for the one call, so the service holds no state between reads.

## Models and serialization

`StudyStructureUnresolved` is a `Literal` of the six reasons: `course_not_represented`, `module_not_found`, `no_current_version`, `ambiguous_version`, `missing_rule`, and `module_cycle`.

`StudyStructureRule` subclasses `CatalogueModuleRule`, so it inherits `node_type`, `sibling_position`, `local_id`, `require_min`, `require_max`, `all_mandatory`, `credits_min`, `credits_max`, `count_min`, `count_max`, and `referenced_group_id`. It redeclares `children` as `tuple[StudyStructureRule, ...]`, excludes the inherited `description` field from serialization, and adds `course` (a `CourseSummary` or `None`), `module` (a `StudyStructureModule` or `None`), and `unresolved`. `StudyStructureRule.model_rebuild()` and `StudyStructureModule.model_rebuild()` resolve the mutual reference between the rule and the nested module.

`StudyStructureModule` is frozen with `extra="forbid"` and holds `module` (a `ModuleSummary`), `target_credits_min`, `target_credits_max`, and `rule`.

`StudyStructureReport` in `src/course_explorer/study_structure/commands.py` is frozen with `extra="forbid"` and holds `academic_year_start` and `root`.

A projected rule carries the official node identity, so `model_dump_json` of a rule reproduces the source node's fields with the projected `children`, `course`, `module`, and `unresolved` values and without `description`. A `Decimal` bound serializes as a fixed-point JSON string, so `target_credits_min` of 180 reads `"180"` and `credits_min` of 5 reads `"5"`.

## Version selection

`_select_version` calls `module_version_candidates(module.versions, academic_year_start=...)` from `src/course_explorer/curriculum.py` with the default `allow_nearest=False`, so the strict candidate set applies: exact academic-year memberships win, and, only when none exists, membership-free versions whose validity bounds contain the requested year are considered. An empty set returns the reason `no_current_version`, and more than one candidate returns `ambiguous_version`. The service never falls back to a version tied to another year.

The prerequisite graph compiler is the one caller that opts into `allow_nearest=True`, and it records a `MODULE_VERSION_FALLBACK` ignored part naming the requested year and the selected version when it does. `tests/study_structure/test_study_structure.py` covers the strict policy, and `tests/prerequisite/test_graph_module_rules.py` covers the fallback.

## Traversal, course fetching, and cycle detection

`_project_module(module, version, *, ancestor_group_ids, course_summaries, module_map)` builds the container and walks the rule tree:

- `_collect_course_refs(rule)` yields the `referenced_group_id` of each `COURSE_UNIT_RULE`, does not descend into a `MODULE_RULE`, and skips a null reference. It recurses through every other node, so the direct course references of one module are collected before the walk.
- The module fetches the identities that are not already in `course_summaries` in one `get_course_summaries` call, deduplicated through `dict.fromkeys`, and stores each returned summary in the request-local map. A course the read omits is absent from the map, which the projection reports as `course_not_represented`.
- `_project_rule(rule, ...)` copies the official fields with `rule.model_dump(exclude={"children", "description"})` and then resolves the one reference the node carries. A `COURSE_UNIT_RULE` takes its summary from the map. A `MODULE_RULE` takes a nested module. Every other node rebuilds its `children` in order.

`_resolve_nested_module(rule, *, ancestor_group_ids, course_summaries, module_map)` classifies a module reference:

- A null reference is `module_not_found`.
- A reference already in `ancestor_group_ids` is `module_cycle`, so the walk stops at the repeated module.
- `_load_module(group_id, module_map)` reads an unloaded identity once through `get_modules` and stores the result, including a negative result, so a repeated reference is not read again. A missing module is `module_not_found`.
- The referenced module's version selection runs the same strict policy, and its reason becomes the node's reason.
- A selected version with no rule is `missing_rule`.
- Otherwise the module is projected with the reference appended to `ancestor_group_ids`.

Cycle detection reads the ancestor path alone, so the same module referenced in two separate branches is projected in both, and a reference that closes a loop over its own ancestors is reported once at the closing node.

## Failure boundaries

Three `ValueError` branches belong to the root alone:

| Condition | Message content |
|---|---|
| The root identity is unknown | `unknown module <identity> for academic year <year>` |
| The root has no version or more than one | `module <identity> has no unique current version for academic year <year>: <reason>` |
| The selected root version has no rule | `module <identity> version <sisu_module_id> has no stored rule` |

Every further failure is data. A nested module reference, a nested version selection, and a nested rule lookup all resolve to a typed reason on the node, and a course reference without a summary resolves to `course_not_represented`. An unresolved node keeps its official fields, so a reader sees the rule and its reason together.

## The command and the CLI

`run_study_structure_command(root_group_id)` in `src/course_explorer/study_structure/commands.py` rejects a blank root with `ValueError` before any settings load, reads `load_normalization_settings().current_academic_year_start` once, opens one `database_context`, constructs the service over `CurriculumRepository`, reads the root, and returns the report.

`scripts/study_structure.py` takes one positional `root_group_id` and prints `report.model_dump_json()` as one line. `POST /api/study-structure` accepts `root_group_id` and returns the same serialized report.

## Tests

| File | Covers |
|---|---|
| `tests/study_structure/test_study_structure.py` | The full structure over an in-memory read for the exact-year and validity selection, every inherited official field and the child order of the whole tree, the nested module and its inactive course, the choice bounds, the credits and count ranges, the unrestricted rules, the excluded `description`, fixed-point decimal serialization, and the report round-trip. It also covers a missing nested course, a missing nested module, an ambiguous nested year, an ancestor cycle, an unknown root, and an ambiguous root. |
| `tests/study_structure/test_study_structure_command.py` | The blank root refused before any settings load, the CLI delegating one identity and printing one report line, and a rejected unknown argument. |

The behaviour as the app presents it is described in [Structure of studies in the catalogue](/docs/backend/catalogue/study-structure.md).
