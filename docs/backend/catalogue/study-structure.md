# Structure of studies in the catalogue

The structure of studies is the official rule tree of one programme or module root for the configured academic year, projected as modules, courses, and rules.

## What the projection is

The projection reads one canonical module's selected official version and returns its typed rule tree: the modules it names, the courses it names, and the official rules in the order the university states them. Every rule node keeps its kind, its position among its siblings, its bounds, and the reference it names.

It is a separate projection from the prerequisite graph. The graph compiles a minimized requirement expression with numeric constraints folded in, while the structure of studies preserves the official rules as the university published them. A structure read answers from the stored official module versions and course summaries, so it runs no inference, and it reads no course selection, completion state, exclusion, or language preference.

The diagram follows one read from the root identity to the structure report.

![A canonical programme or module root enters version selection for the configured academic year, and the selected version is walked as its official rule tree. A course reference resolves to a shared course summary, a module reference resolves to a nested module whose own rule tree is walked, and a reference that cannot be resolved appears as a node with a reason. All of them are part of the structure report.](/docs/diagrams/structure-projection.svg)

## The root and the version

A structure read takes one canonical root identity, which is a [programme](/docs/reference/glossary.md#discovery-and-the-structure-of-studies). The browser sends the identity of each programme it holds, one ordinary read at a time, and the read answers for that root alone. The interface issues that same read when a programme joins its ordered list and when it needs the report again.

The academic year is the configured current academic year, `CURRENT_ACADEMIC_YEAR` in `config/curriculum.toml`. The example sets `2026-2027`, so the projection uses the academic year that starts in 2026.

Exactly one version of the root is selected for that year. A version is a candidate when it is a member of that exact academic year's curriculum periods, or, when the module has no such membership, when it carries no period membership and its own validity bounds contain the year. Exactly one candidate is required and no nearest-year fallback applies, so a root whose versions are all tied to other years fails the read. [Prerequisite graph](/docs/backend/prerequisites/prerequisite-graph.md) is the reader that accepts a single nearest dated version for a module reference and discloses the fallback. [Representative versions and activity](/docs/backend/catalogue/representative-versions.md) states the shared candidate rule.

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
| `ambiguous_version` | The module has more than one version for the academic year. |
| `missing_rule` | The selected version of the module has no stored rule. |
| `module_cycle` | The reference points at a module already on the path from the root. |

An unresolved node is a fact about the stored data. It is reported as it stands, it never fails the read, and no content is invented for it.

## Root failures

A read fails when the root identity names no module, when the root has no version for the academic year, when it has more than one version for it, or when the selected version of the root has no stored rule. The error names the root identity, and a version failure also names the academic year and the reason.

An unresolved node below the root never fails the read.

## Inactive courses

The projection applies no activity filter. A course the tree names is projected with its shared summary, including its activity state, so an inactive course appears in the structure of studies and is marked inactive.

Placement, moves, resets, and the **Unplaced studies** part of the tab belong to the browser, and [Structure editor](/docs/frontend/structure-editor.md) describes them.

The read seam, the service contract, the serialization, the traversal, and the tests that cover them are described in [Structure projection](/docs/backend/catalogue/structure-projection.md).
