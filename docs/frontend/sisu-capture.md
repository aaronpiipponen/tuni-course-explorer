# Sisu capture

The Sisu capture validates a downloaded plan, parses its markup, prepares an import profile and places the pending hierarchy into the structure of studies.

## The capture boundary and the pending placement

`web/src/features/structure/sisu.ts` holds the capture boundary and the pending placement.

`validateSisuPlan(value)` is the recursive check of one capture hierarchy. It requires a non-array object, a nonempty programme array of module objects, the exact `course` and `module` discriminants, nullable nonempty string identities, the required nullable module `versionId`, a nonempty course code and name, a nullable module code, a boolean completion, and arrays of children, and it rejects two non-null top-level programme identities that agree because a programme has one top-level place. An unknown field is discarded, a repeated course occurrence is accepted, and every failure raises `Invalid Sisu plan file`.

`parseSisuCapture(value)` is the boundary of one downloaded capture. It requires a nonempty `markup` string, a module lookup record of group-id lists keyed by the status cell identity the page shows, and a course lookup record of `{ code, groupId }` hits keyed by the displayed code.

The markup is parsed with `DOMParser` as data and is never inserted into the document or evaluated, and the identity of every module and course comes from the lookup records alone: a course hit is matched on its exact code and its group ids are de-duplicated, and a module's list of group ids is de-duplicated, so one sole identity is used and zero or several identities leave the item unresolved.

The hierarchy is read from the module element that holds each row of the plan tree: the own name, the own code, the own status identity that supplies the exact version id when the group resolves, and the own direct module and course rows in document order.

A module with the graduation flag carries a degree header, and a top-level header with no graduation flag, no grouping title and no module information control is the education container, whose direct degree rows become the top-level programmes in their displayed order. A capture with no readable programme raises `Invalid Sisu plan file`.

`prepareSisuProfile(capture, name, language)` builds the profile one import creates: the language of the interface at confirmation, one ordered distinct selected identity per non-null captured course, a completion for every identity that any occurrence captured as completed, one exact version pair per resolved captured module, the resolved top-level programme identities in capture order, and one independent copy of the hierarchy in `pendingSisuImport`. Two different exact ids for one group raise `Sisu plan selects two versions of a module`, and the call reads no storage and sends no request. Choices, places and placed identities start empty. `BrowserStore.importProfile` then applies the shared trimmed-name, empty-name and duplicate-name rules.

`sisuImportBlocked(state)` answers whether one waiting capture sits beside saved structure edits. It is true exactly when `pendingSisuImport` is not null and one of the choice keys, the two placement maps or `placedCourseIds` holds an entry. A choice entry with an empty list counts, and a placement counts even when its target is `null`, because both are saved edits. Programme identities, version selections and the shared course sets alone do not count, because a prepared capture fills them without an edit.

`resolveSisuImport(state, content, unavailable)` returns `null` while no capture waits, while `sisuImportBlocked` is true, and while a read the capture needs has not settled: every resolved module identity of the capture, at any depth, needs a report or a recorded unavailable module, and every selected identity needs a summary or a recorded unavailable course. `captureModuleIds(capture)` returns that module list in capture order, and the pane reads it while the record is pending. Otherwise it returns one `StructureChange` and the issues of the placement, and it writes nothing.

- The available programmes are the captured ones whose report the content holds, and they are written in capture order. Each scope reads `officialHomes` again, so a module placed above it contributes its own official homes to the suppression below. A programme whose identity is unresolved or whose report is unavailable is named as an issue, its representable descendant courses are placed in the `u` bucket, and no education wrapper or invented group id is created.
- One walk per programme starts at the `programmeKey(groupId)` node of the forest. For a captured direct course or module it searches the parent's entries and every option through transparent and choice nodes, and it stops at the boundary of a nested module. A match of a course or a module contributes its choice path, selected through `nextChoices` only when a step is absent, and records the matched entry's `origin.ownerKey` as its place. The walk descends into a matched module's node for its captured children.
- A representable captured course outside the parent's official alternatives is placed on the parent module node with `placeCourse`, so it draws the added outline. An unresolved identity is named and left out, and a captured course outside the hydrated summaries is named, left out of the placed identities and removed from both course sets.
- A captured module outside the parent's official tree joins that parent through a `modulePlacements` entry, and the walk descends into the node `buildStructure(report, "<parentKey>/m:<id>")` builds from its own report, so its captured children are placed inside it and its uncaptured official content is suppressed. A module with no report at all is named as an issue, and its representable descendant courses are placed in the `u` bucket rather than a branch of that programme.
- Every official identity of one parent scope that the capture does not hold there is suppressed through a `null` placement, so a default projection cannot select content the capture does not hold. A captured course or module keeps its matched owning key, so a captured deselection or move is preserved rather than turned into a second card, and a matched module whose placement record exists keeps that recorded place rather than a suppression.
- An identity that one parent scope offers twice, a captured sibling module that the scope offers twice, a choice path step into an already chosen single option, and a captured sibling module whose identity repeats raise `Sisu choice is ambiguous` and the caller writes nothing.
- The returned change holds the next structure, the unavailable captured course identities in `removedCourseIds`, and `pendingSisuImport: null`. It carries no completion, so the callback's own course sets own the completion and a change another tab made while the reads waited is kept, and issues hold one name, a nullable code and one of `unresolved`, `module_not_placed` or `course_not_represented`.

## Where a change belongs

- A change to what a downloaded capture holds, to how its markup is read, or to how pending choices are placed belongs in `web/src/features/structure/sisu.ts`.

## Tests

| File | Covers |
|---|---|
| `web/src/features/structure/sisu.test.ts` | The parse and import of a capture into a reloadable profile that performs no fetch, the scoped placement of captured choices with suppressed uncaptured defaults and one atomic pending clear, the named omissions of a partial catalogue with its representable courses kept loose, and a waiting capture beside restored edits placing nothing |
