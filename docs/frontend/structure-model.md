# Structure model

The structure model projects each official report into display rows and resolves the profile's ordered programmes, choices, places and exact module-version selections into one rendered tree.

## Programmes and the forest

`web/src/features/structure/model.ts` holds the pure projection. It normalizes an official rule tree into nodes, options, and rule groups, and it derives every key from the position of the rule among its siblings.

`programmeKey(groupId)` returns `p:<encodeURIComponent(groupId)>`, the browser node-key prefix of one top-level programme. The prefix is a key, not a second entity identity, and the canonical module identity stays the programme identity everywhere else.

`buildProgrammeForest(reports, language = "en")` projects the supplied reports in their given order with `buildStructure(report, programmeKey(report.root.module.group_id), language)`, stamps each direct entry's kind as `programme`, appends the `UNPLACED_KEY` (`u`) bucket, and returns one transparent `$structure` wrapper. The bucket rule reads `any studies` and its title reads `Unplaced studies`. The forest's direct entries are its ordered programmes, and no education title or header is drawn. Programme kind comes from that position alone, so a top-level bare module is a programme row and a report nested elsewhere is a module.

`buildStructure(report, key = "r", language = "en")` builds one module node from the report's root. The root rule key is `<key>/<sibling_position>` when the root rule is a non-mandatory composite, a credits rule, or a course-unit-count rule, and `<key>` otherwise.

`moduleNode(module, key, language, ruleKey)` builds one module node:

- The node kind is `module`. The official `DegreeProgramme` type grants no interaction kind, so every nested caller of `moduleNode` produces a module node. The type selects display nouns alone, through `nodeWordingKind` in `presentation.ts`.
- The rule label is the target-credit range when the module carries target credits, an empty label for an unrestricted `AnyCourseUnitRule` or `AnyModuleRule`, and `ruleLabel(module.rule, language)` otherwise.
- The entries come from `project(module.rule, ruleKey, ruleGroups, key, [], language)`.
- When the module rule is a `CourseUnitRule` or a `ModuleRule` and the projection produced no rule group, `requiredRuleOptions(entries)` turns its entries into one required group whose `requiredCount` is the option count.

`ruleLabel(rule, language)` reads a `CompositeRule` as `all required` or a choose range, a `CreditsRule` and a `CourseUnitCountRule` as `range(min, max, unit, language)`, `AnyCourseUnitRule` as `any course`, `AnyModuleRule` as `any module`, and `CourseUnitRule` plus `ModuleRule` as `required`. Any other node type throws `Unsupported structure rule type`.

`project(rule, key, ruleGroups, ownerKey, choicePath, language)` walks one rule. A child key is `<key>/<sibling_position>`, and the branch decides the shape:

| Rule | Result |
|---|---|
| `CourseUnitRule` with a course | A `course` entry stamped with the origin |
| `CourseUnitRule` without a course | A `note` entry from `reasonText(rule.unresolved ?? "course_not_represented", language)` |
| `ModuleRule` with a module | A nested module node whose rule key is `<key>/<module.rule.sibling_position>`, stamped with the origin |
| `ModuleRule` without a module | A `note` entry from `reasonText(rule.unresolved ?? "module_not_found", language)` |
| `AnyCourseUnitRule` or `AnyModuleRule` | No entries |
| All-mandatory composite | The projected children in order, one required group from `requiredRuleOptions`, and the nested groups |
| Composite whose `require_min` equals its child count and whose `require_max` is null or at least that count | One transparent group holding the projected children, one required group, and the nested groups |
| Positive credits or count rule with one all-mandatory composite child | The child's entries, one required group carrying the credit minimum, and the nested groups |
| Positive credits or count rule whose single child is a composite with one all-mandatory grandchild | That grandchild's entries, one required group, and the nested groups |
| Any other composite, credits rule, or count rule | A `choice` node |

A `choice` node takes its options from the child projections that carry entries. Its `single` flag is true when the option rule is a composite with `require_max` of 1, its title names the option count with the noun its option entries share, which is courses, degree programmes, other modules, or options when the entries differ in kind, and `autoSelectSingleWrapper` is true when one option holds one nested choice. A rule group is added for a choice that holds a selectable entry, is not auto-selected, and whose `requiredCount` comes from `require_min` for a composite or from zero otherwise.

`setOptionOrigin` stamps the entries of each option with `ownerKey` and the choice path, extends the path through a nested choice, and keeps the leaf owner of a transparent wrapper. `hasSelectableRuleEntries` decides whether a group's options hold anything a reader can choose, and `requiredRuleOptions` flattens a transparent wrapper and skips a nested choice.

## Display nouns and the node kind

`web/src/features/structure/presentation.ts` owns the words a node shows. `nodeWordingKind(node)` returns `programme` for a node whose positional `kind` is `programme` or whose module carries the official `DegreeProgramme` type, and `module` otherwise. Action and notice nouns read it. `nodeKindLabel(node, language)` reads the official type for a programme or module node instead: a degree programme reads **programme** and a bare module reads **module**, so a direct top-level bare module carries the module marker while its position grants the programme menu and reset. The positional kind labels a choice, a group or the bucket. The drawer footer, the drawer empty text, the reset question title, the removal question title, the reset notice and the two destination notices read `nodeWordingKind`.

The result selects words alone. It never changes a node's `kind`, its place in the forest, its controls or its actions, so a nested degree programme keeps the drawer, the search, the reset and the removal of a module.

## Resolution, precedence and single render

`resolveStructure(root, edits, content, language)` returns a `ResolvedNode` tree. It walks once with `seenCourses` and `seenModules`, the latter seeded with the root module identity, so a course or module named in two branches is shown once.

- For a choice node the visited entries are the entries of the options in `edits.choices[node.key]`. An `autoSelectSingleWrapper` node with no stored option uses all of its options instead. The `chosen` list records the options in force.
- A `course` entry whose `edits.coursePlacements[id]` is a string other than the node key is pushed to `removed` and not shown, and so is an entry with a `null` placement. Every other occurrence of the identity is suppressed by `seenCourses`.
- A `node` entry with a module follows the same precedence through `edits.modulePlacements[id]` and `seenModules`.
- A `note` entry that names an `ambiguous_version` module reference follows that same placement and `seenModules` precedence, and a suppressed note shows no text. Every shown ambiguity note adds its group to the node's `versionSelectionRequiredIds`, which merges every visited child's list in encounter order, including an explicitly added module's subtree.
- The place overrides act before first-occurrence deduplication, so a recorded place wins over the first official occurrence of the identity.
- A module identity that a forest holds as one of its direct programmes is reserved against the nested occurrences of the same module, and the direct entries are visited in list order, so a top-level programme cannot disappear because another programme also references it.
- After the entries, every `edits.coursePlacements` entry whose target is this node, whose entity the node does not already hold, and whose identity is not shown is added from `content.courses` with `added: true`, and a missing summary throws `Missing placed course summary`.
- The same pass over `edits.modulePlacements` builds the added module through `buildStructure(report, "<key>/m:<id>", language)` and throws `Missing placed module report` when the report is absent.
- Added content therefore comes only from the placement maps, so a placement that names no visited node is shown nowhere.

`officialHomes(root, edits, content)` records every node key where the official tree names each course and module identity, and for each stored module placement with a string target and a report it walks the projection of that module as well.

`indexResolved(root)` walks the resolved tree into `byKey`, `courseAt`, and `moduleAt` maps. `nextChoices(choices, node, optionKey)` sets the sole option for a `single` node and returns the same object when it is already that option, and toggles the option otherwise. `displayContents(resolved)` flattens a choice or transparent child into its parent, so the drawn tree holds no empty wrapper row.

`contentSource(resolved, kind, id)` walks the displayed children of each visited node once and returns the node that displays one course or one child module, or `null` when none does. A course inside a chosen option or a transparent wrapper is therefore attributed to its displayed holder, and a module identity to its displayed parent. `moduleSource(resolved, moduleId)` wraps it for a module, and `courseSource(resolved, courseId)` wraps it for a course. The placement code uses `courseSource` for the holder name of a move, and no caller infers an ancestor from a key prefix.

## Placement edits, the pane and the Sisu capture

The placement records and the shared course sets are described in [Structure edits](/docs/frontend/structure-edits.md). The pane's display input, hydration, dialogs and programme operations are described in [Structure pane](/docs/frontend/structure-pane.md). The downloaded plan, its parsing and its pending placement are described in [Sisu capture](/docs/frontend/sisu-capture.md).

## Where a change belongs

- A rule kind that the tab should render differently belongs in `project` and `ruleLabel` in `model.ts`, together with the display case in `displayContents` when the node should not be drawn as a row of its own.

## Tests

| File | Covers |
|---|---|
| `web/src/features/structure/model.test.ts` | The projection of the rule kinds into rows, groups, and choices in both languages, the required group of the root, the note of an unresolved module, the auto-selected wrapper, the origin of an option's entries, and the resolution of moves, removals, restores, added modules, and single render |
