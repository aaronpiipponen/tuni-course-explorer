# Structure model

The structure model projects the official report into display rows and resolves the profile's choices and places into one rendered tree.

## Projection and rule interpretation

`web/src/features/structure/model.ts` holds the pure projection. It normalizes the official rule tree into nodes, options, and rule groups, and it derives every key from the position of the rule among its siblings.

`buildStructure(report, key = "r", language = "en")` builds the root node. The root rule key is `r/<sibling_position>` when the root rule is a non-mandatory composite, a credits rule, or a course-unit-count rule, and `r` otherwise.

`moduleNode(module, key, language, ruleKey)` builds one module node:

- The node kind is `programme` when `module.module_type` is `DegreeProgramme`, and `module` otherwise.
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

A `choice` node takes its options from the child projections that carry entries. Its `single` flag is true when the option rule is a composite with `require_max` of 1, its title names the option count as courses, modules, or options, and `autoSelectSingleWrapper` is true when one option holds one nested choice. A rule group is added for a choice that holds a selectable entry, is not auto-selected, and whose `requiredCount` comes from `require_min` for a composite or from zero otherwise.

`setOptionOrigin` stamps the entries of each option with `ownerKey` and the choice path, extends the path through a nested choice, and keeps the leaf owner of a transparent wrapper. `hasSelectableRuleEntries` decides whether a group's options hold anything a reader can choose, and `requiredRuleOptions` flattens a transparent wrapper and skips a nested choice.

`withUnplaced(root, language)` wraps the root and the `UNPLACED_KEY` (`u`) bucket in one transparent node, where the bucket rule reads `any studies` and its title reads `Unplaced studies`.

## Resolution, precedence and single render

`resolveStructure(root, edits, content, language)` returns a `ResolvedNode` tree. It walks with `seenCourses` and `seenModules`, the latter seeded with the root module identity, so a course or module named in two branches is shown once.

- For a choice node the visited entries are the entries of the options in `edits.choices[node.key]`. An `autoSelectSingleWrapper` node with no stored option uses all of its options instead. The `chosen` list records the options in force.
- A `course` entry whose `edits.coursePlacements[id]` is a string other than the node key is pushed to `removed` and not shown, and so is an entry with a `null` placement. Every other occurrence of the identity is suppressed by `seenCourses`.
- A `node` entry with a module follows the same precedence through `edits.modulePlacements[id]` and `seenModules`.
- After the entries, every `edits.coursePlacements` entry whose target is this node, whose entity the node does not already hold, and whose identity is not shown is added from `content.courses` with `added: true`, and a missing summary throws `Missing placed course summary`.
- The same pass over `edits.modulePlacements` builds the added module through `buildStructure(report, "<key>/m:<id>", language)` and throws `Missing placed module report` when the report is absent.
- Added content therefore comes only from the placement maps, so a placement that names no visited node is shown nowhere.

`officialHomes(root, edits, content)` records every node key where the official tree names each course and module identity, and for each stored module placement with a string target and a report it walks the projection of that module as well.

`indexResolved(root)` walks the resolved tree into `byKey`, `courseAt`, and `moduleAt` maps. `nextChoices(choices, node, optionKey)` sets the sole option for a `single` node and returns the same object when it is already that option, and toggles the option otherwise. `displayContents(resolved)` flattens a choice or transparent child into its parent, so the drawn tree holds no empty wrapper row.

## Placement edits and scoped reset

`web/src/features/structure/edits.ts` holds the pure placement edits.

- `place(edits, field, homes, id, target)` deletes the old entry of the identity, writes the target when it is not null, and writes a `null` target only when the identity has an official home. An identity with no official home is dropped instead, so nothing dangles. `placeCourse` and `placeModule` bind the course and module fields.
- `placeModuleWithCourses(root, edits, content, moduleId, targetKey, placedCourseIds)` places the module, resolves the tree to find the destination node of that module, resolves the mandatory projection of the destination module with `emptyEdits()` and `NO_CONTENT`, maps each identity of `placedCourseIds` to the node that holds it, and returns the count of moved courses with the next edits.
- `resetScope(edits, homes, scopeKey)` drops the choices whose key is inside the scope and the placements whose target is inside it or whose official home is inside it. A key is inside the scope when it equals the scope or starts with `<scopeKey>/`.

## Selection migration and the shared sets

`web/src/features/structure/actions.ts` holds the only writer that moves the structure slice and the shared course sets together.

`applyStructure(store, next, removedCourseIds = [], discardUncompletedCourseIds = [])`:

1. A course named by `state.structure.placedCourseIds` that the next projection does not hold, and that is not completed, is dropped from the selection.
2. An identity of `discardUncompletedCourseIds` that is not completed is dropped as well.
3. An identity of `removedCourseIds` leaves both course sets.
4. The selection that is left keeps its order, and every identity of `next.placedCourseIds` that is absent is appended.
5. The structure slice is written as the next root, choices, course placements, module placements, and placed identities.

A completed course is never dropped from the selection by steps 1 to 3, which is what keeps a completion across a root change, a reset, and a module deselection.

`resetUnplaced(store, tree, content)` resolves the tree, collects the courses of the `u` subtree and the selected courses outside the whole structure, drops the `u` choices, keeps a placement whose target is outside the bucket, turns a placement into the bucket into `null` when the identity has an official home outside it, and commits the resulting projection with the collected identities as uncompleted discards.

`removeFromSelection(store, courseId)` drops the identity from both course sets.

## Pane hooks, dialogs and root changes

`web/src/features/structure/StructurePane.tsx` composes the tab:

- `useStructureReport(rootGroupId)` reads the report, and `withUnplaced(buildStructure(report, "r", language), language)` builds the tree in the profile language.
- `usePlacedContent(courseIds, moduleIds)` hydrates the summaries and reports that the placement maps name, and the pane holds the last complete input so a refresh in the profile language does not blank the tree.
- `resolveStructure` produces the displayed tree, and an effect compares the displayed identities with `placedCourseIds` and commits through `applyStructure` when they differ.
- `useStructureEditor` owns the mutations. `choose` writes the next choices through `nextChoices`. `addCourse` extends the placed content with the summary and places the course, and it reports `Already in this module` when the course already sits there. `selectRuleCourse` and `selectRuleModule` write the options of the choice path and then the place. `toggleRuleCourseCompleted` places the course when it has no place and then toggles the completion. `deselectRuleCourse(course, removeCompletion)` takes the place away and names the identity in `removedCourseIds` only when the completion goes with it, and a loose completed course whose completion is kept returns without a change. `resetNode` calls `resetUnplaced` for the bucket and `resetScope` otherwise, and `resetAll` commits `emptyEdits()` with the loose selected identities as uncompleted discards.
- `useChooseRoot` loads a root report and commits `withUnplaced(buildStructure(report))` with empty edits, which is the one path that clears every edit.

`StructureDrawer` owns the two questions a change can raise. `MoveConfirmDialog` appears when `courseHome` or `moduleHome` names another node, and the move runs at once when it does not. `CompletedCourseDeselectDialog` appears for a completed course and offers the loose move or the removal with the completion. The drawer reads `editor` through a ref so a formatter created at click time uses the live `courseHome` and `moduleHome`. `ResetStructureDialog` confirms **Reset all**, and `RootPromptDialog` loads a root through `useChooseRoot` before `useFreeChoiceAdd` adds the pending courses.

`useNotice` shows one message for 2200 ms and stores a formatter, so the message renders in the language in force when it is shown.

## Request handling

`useStructureReport` reads the root report through `useLookup`, keyed on the root identity, so a root change and an unmount abort the pending read. `usePlacedContent` runs its own effect keyed on the serialized course and module identity lists, starts one `AbortController` for the identities it is missing, drops a settled result whose controller was aborted, and aborts the controller on cleanup, so a change to either list and an unmount cancel the pending read. It throws `Requested course summary is missing` when the read omits a requested identity.

`useChooseRoot.choose` and `useStructureEditor.addModule` call `readStudyStructure` directly. Each aborts its own previous operation, captures `store.getSnapshot().currentProfileId` before the request, returns without a write when the signal is aborted or the profile changed, and re-reads the current edits after the wait. `addModule` re-resolves the tree with the current edits and throws `A module cannot be added inside itself` or `Structure root changed while adding a module`, and it returns a notice of `Already in this module` when the destination already holds the module.

`errorPresentation` maps these messages, and the projection and resolution messages, to `UI_TEXT` keys, so each failure reads in the profile language.

## Where a change belongs

- A rule kind that the tab should render differently belongs in `project` and `ruleLabel` in `model.ts`, together with the display case in `displayContents` when the node should not be drawn as a row of its own.
- A change to how a place is stored, cleared, or discarded belongs in `edits.ts` and in `applyStructure` in `actions.ts`.
- A drawer row or dialog to add belongs in `StructureDrawer` with its own component beside it, and an editor operation to add belongs in `useStructureEditor` so every write of the tab goes through `commit`.

## Tests

| File | Covers |
|---|---|
| `web/src/features/structure/model.test.ts` | The projection of the rule kinds into rows, groups, and choices in both languages, the required group of the root, the note of an unresolved module, the auto-selected wrapper, the origin of an option's entries, and the resolution of moves, removals, restores, added modules, and single render |
| `web/src/features/structure/edits.test.ts` | `resetScope` discarding only what is scoped to a node, a removal of an identity with no official home leaving no entry, and an added module using the resolved destination key while the selected courses and the completion are kept |
| `web/src/features/structure/actions.test.ts` | The deselection of a completion, the explicit removal that takes the completion too, the module lifecycle outside the bucket, the retained completion of a deselected module, and the Unplaced studies reset restoring the official structure |
