# Structure of studies in the catalogue

The structure of studies is the official rule tree of each requested programme or module root for the configured academic year, projected as modules, courses, and rules.

## What the projection is

The projection reads each canonical module's selected official version and returns its typed rule tree: the modules it names, the courses it names, and the official rules in the order the university states them. A batch read projects several roots over one shared module and course-summary map. Every rule node keeps its kind, its position among its siblings, its bounds, and the reference it names.

It is a separate projection from the prerequisite graph. The graph compiles the source prerequisite expression into one [solver structure](/docs/reference/glossary.md#prerequisites-and-routes) for its calculation, with its cardinality, credit, and course-count bounds carried as calculation pieces, while the structure of studies preserves the official rule tree as the university published it. A structure read answers from the stored official module versions and course summaries, so it runs no inference, and it reads no course selection, completion state, exclusion, or language preference.

The diagram follows one batch read from the requested roots to the structure report.

![The requested roots enter one batch read that loads every module once and shares one course-summary map, and version selection takes one official version per root or an explicit selection. A root with several candidates and no selection is listed in version_selection_required. A read that allows unavailable roots collects a root in unavailable_root_group_ids when its identity matches no module, when it has no version for the year, or when its version has no stored rule, and every other root is projected as its official rule tree, with the report carrying the projected roots and both identity lists.](/docs/diagrams/structure-projection.svg)

## The root and the version

A structure read takes one or more canonical root identities, each a [programme](/docs/reference/glossary.md#discovery-and-the-structure-of-studies). The browser sends every identity it is missing in one request, and the read answers for all of them over one shared projection. The single-root command keeps one root identity for the command line. A root that another node already displays reads from the held batch report, and the interface reads a root when it joins its ordered list.

The academic year is the configured current academic year, `CURRENT_ACADEMIC_YEAR` in `config/curriculum.toml`. The example sets `2026-2027`, so the projection uses the academic year that starts in 2026.

A projected root carries exactly one version for that year. A version is a candidate when it is a member of that exact academic year's curriculum periods, or, when the module has no such membership, when it carries no period membership and its own validity bounds contain the year. No nearest-year fallback applies, so a root whose versions are all tied to other years is unavailable. [Prerequisite graph](/docs/backend/prerequisites/prerequisite-graph.md) is the reader that accepts a single nearest dated version for a module reference and discloses the fallback. [Representative versions and activity](/docs/backend/catalogue/representative-versions.md) states the shared candidate rule.

A request may carry one explicit version identity per canonical group. It is authoritative for the groups it names and must belong to that group's eligible set. The read refuses any other identity and never substitutes a version, and a refusal fails the whole batch even when unavailable roots are collected. A group without an entry keeps the ordinary unique-candidate resolution. The map is request-local, and an unrelated entry is never loaded or validated because a profile can hold selections outside the requested closure.

## The seven rule kinds

The rule tree preserves the seven official rule kinds.

| Rule kind | What the rule states |
|---|---|
| Composite rule | A group of child rules, with either every child required or a minimum and a maximum number of children that count. |
| Credits rule | A credit range for the studies under it. |
| Course unit count rule | A course count range for the studies under it. |
| Course unit rule | One named course. |
| Module rule | One named module. |
| Any course unit rule | A freely chosen course. |
| Any module rule | A freely chosen module. |

An unrestricted rule names no course and no module, and a bounded rule carries its own range and one child.

## Resolved courses and modules

A course unit rule resolves to the shared course summary of the course it names, which carries both official names, the code, the credits, the official URL, and the activity state. A course that the tree names in two places is the same course in both.

A module rule resolves to a nested module: the selected version's summary, its target credits, and its own projected rule tree, built the same way as the root. A module that the tree references in two separate branches is projected in each branch, and a module reference that points at a module on the path from the root is reported as a cycle instead.

Each projected node carries the official rule fields, the course or module it resolves to, and the unresolved reason, so the interface renders the official constraint the rule states.

## Unresolved nodes and their reasons

A reference that cannot be resolved is an [unresolved requirement](/docs/reference/glossary.md#prerequisites-and-routes) and appears in the structure as a node with a reason, so the reader sees the official rule that asks for it and the reason it has no content. The node carries an empty course or module and one of these reasons.

| Reason | Meaning |
|---|---|
| `course_not_represented` | The rule names a course the catalogue has no summary for. |
| `module_not_found` | The rule names a module the catalogue does not hold, or it names no module. |
| `no_current_version` | The module has no version for the academic year. |
| `ambiguous_version` | A nested module has more than one version for the academic year and the request holds no explicit selection. |
| `missing_rule` | The selected version of the module has no stored rule. |
| `module_cycle` | The reference points at a module already on the path from the root. |

An unresolved node is a fact about the stored data. It is reported as it stands, it never fails the read, and no content is invented for it.

## Root failures

A root is unavailable when its identity names no module, when it has no version for the academic year, or when its selected version has no stored rule. A root with more than one eligible version and no explicit selection is a separate `version_selection_required` outcome: a single-root read fails, and a batch reports those root identities in `version_selection_required` regardless of `allow_unavailable`, so the browser can offer the group picker instead of treating the programme as absent. A read that allows unavailable roots collects those identity, version, and rule failures in `unavailable_root_group_ids` and returns every projectable root. An explicit version that is not eligible for its group is neither outcome: the read refuses it and the whole batch fails, even when unavailable roots are collected. Every other failure propagates.

An unresolved node below a root never fails the read.

## Inactive courses

The projection applies no activity filter. A course the tree names is projected with its shared summary, including its activity state, so an inactive course appears in the structure of studies and is marked inactive.

Placement, moves, resets, and the **Unplaced studies** part of the tab belong to the browser, and [Structure editor](/docs/frontend/structure-editor.md) describes them.

The read seam, the service contract, the serialization, the traversal, and the tests that cover them are described in [Structure projection](/docs/backend/catalogue/structure-projection.md).
