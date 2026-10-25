# Structure edits

The structure edits hold the profile's placement records, move a relocated scope's records, and write the structure slice together with the shared course sets.

## Placement edits, addition precedence and scoped reset

`web/src/features/structure/edits.ts` holds the pure placement edits.

- `place(edits, field, homes, id, target)` deletes the old entry of the identity, writes the target when it is not null, and writes a `null` target only when the identity has an official home. An identity with no official home is dropped instead. `placeCourse` and `placeModule` bind the course and module fields.
- `insideScope(scopeKey, key)` answers whether a key is the scope key itself or sits under it, and `resetScope` uses it to drop the choices whose key is inside the scope and the placements whose target is inside it or whose official home is inside it.
- `moveScope(edits, content, from, to)` rewrites the records one moved scope owns for the node keys it renders at in its destination place.

  The two renderings come from the same official rule and the same placement records, so `scopeKeys` pairs their nodes and their choice options in the order the rule names them, pairs a module a record places inside the scope by identity, and reads each key from the projection on its own side, because a module's contents take their keys from the rule key of its own root rule rather than from a plain extension of its node key. A pair that does not line up raises `A moved scope does not match its new place`.

  A record under the moved node key that no paired node names holds a place the destination rendering does not have and leaves the state, a choice key and a placement target take their paired key, and a removal or a placement outside the moved node describes an identity and stays as it is.

  `replacedScopeHomes(homes, movedKey)` returns the official homes the clearing of a replaced scope reads, with the homes of every identity the moved subtree names removed, so the clearing keeps the removals and the places of the subtree that moves out of it while the replaced programme's own records clear with it.
- `hasScopedEdits(root, edits, content, scopeKey)` resolves the forest with the stored edits and again with the candidate `holderPulls(root, edits, holderNode, content, false).edits`, which is the state a held identity shows when its own place draws it with its own official defaults, and compares the two targets as `scopeValue` tuples. The current target must resolve or the call raises `Structure target is unavailable`, and a candidate that does not render the target counts as a difference.

  A tuple holds the node key, the module identity, the rendered course identities, the notes the projection shows and its children tuples, so a record that leaves the rendered contents the same, such as an empty choice list, a chosen option that renders the same contents, or a place at an official home, is not a difference, and neither is a course the candidate pulls out of another holder into the scope. `Homes` is the exported map type the placement helpers share.
- `holderPulls(afterTree, afterEdits, holderNode, content, present, pull = true)` returns the next edits of one added holder and the courses that move with them. The holder node is resolved on its own rule, so each record is the holder's own first place for a module or a course it officially renders, and the module records name the node whose entries render the module. Each listed move's `from` formatter reads `courseSource` on the tree resolved from `afterTree` and `afterEdits` before the holder's scope records are cleared, so a course a chosen option draws names its containing programme or module rather than the choice title.

  The `present` flag is whether the tree renders the holder before the operation's own writes, which means the operation moves the holder. A moved holder returns `afterEdits` and an empty move list, so the whole current subtree it holds travels untouched: a removed identity stays removed, a course it renders elsewhere inside its own scope or directly in the `u` bucket keeps that place, an official course another programme or module renders stays there, and no module takes its official place again. A holder the tree does not render adopts its scope's official defaults, because the records `clearScope` drops from that scope are removed before the restoration, and a module the cleared projection renders nowhere takes its official place again, which brings the courses inside it with it.

  A place or a removal outside the holder stays as it is, because the clearing touches only records whose key or target is inside the holder, so the holder restores only the official identities that render nowhere. The courses are read against a projection that includes those restored module records, and a course the cleared projection does not render at its own node takes the place of that node again.

  The move list reads the tree before the scope's records are cleared, so a course of the holder's own rule that the tree renders outside the holder is listed as a move from the node the tree shows there and takes the holder's own place, while a course that renders nowhere or that renders directly in the `u` bucket is not listed and keeps its place.

  `pull` is whether the listed courses move in: a kept course keeps the record it holds and no place is written for it, so the node outside the scope keeps rendering it and the adopted official contents render without it.
- `keepCoursePlacements(edits, previous, pulls)` returns edits with the placement record of each listed course as the previous edits hold it, and with no record for a course that holds none. A scope clear drops the record of a course whose official home is inside the cleared scope, which is what returns that course to the scope, so this is the owner that keeps such a course where it is: `holderPulls` reads it for a kept addition, and the reset owners read it for a kept reset.
- `scopePulls(root, edits, content, scopeKey)` returns the courses one scope's reset returns to it from the nodes that render them. It resolves the tree with the stored edits and again under `resetScope` for that scope, and a course that renders outside the scope in the first projection and inside it in the second is listed with the containing programme or module that renders it, read through `courseSource` on the pre-operation tree. A course that renders directly in the `u` bucket is not listed, and a course another node renders through the official rule rather than through a record of its own is not returned by the clearing and is not listed.
- `placeModuleWithCourses(root, edits, content, moduleId, targetKey, from?, pull = true)` places the module, resolves the tree to find the destination node of that module, and returns `holderPulls` for that destination together with the next edits. Its `from` node is the pre-operation rendering of the module in the caller's own tree, which `modulePlacement` reads from the tree the choice extension has not reached, an omitted node reads the module of the supplied edits, and a rendered module moves with its subtree through `moveScope` before the placement resolves. The courses a module it does not render pulls belong to the caller's confirmation, `pull` decides whether that placement moves them in, and a moved module pulls none.
- `clearedScopePlacements(affected, edits, afterTree, afterEdits, content, clearedKey, touched, completedCourseIds)` returns the records that keep a cleared scope's courses out of the nodes the action does not touch. A course that the cleared scope held through a string placement, and that the next projection renders in a node outside `touched`, is placed in `u` when it is completed and removed from the tree when it is not.

## Selection migration and the shared sets

`web/src/features/structure/actions.ts` holds the only writer that moves the structure slice and the shared course sets together.

`applyStructure(store, change)` runs the callback inside `store.updateCurrent` with the current profile state. A callback that returns `null` leaves the state as it is and writes nothing. Otherwise the returned `next` structure and its explicit identities migrate the shared sets:

1. A course named by `state.structure.placedCourseIds` that the next projection does not hold, and that is not completed, is dropped from the selection.
2. An identity of `discardUncompletedCourseIds` that is not completed is dropped as well.
3. An identity of `removedCourseIds` leaves both course sets, so the removal of a completed course takes its completion with it.
4. The selection that is left keeps its order, and every identity of `next.placedCourseIds` that is absent is appended.
5. The structure slice is written as the next programme list, the exact version selections, the choices, the course placements, the module placements, and the placed identities.
6. `pendingSisuImport` is written from the change when the change supplies it and kept as it is when the change omits the field, so one write places a pending capture and clears it together.

A completed course is never dropped by steps 1 and 2, which is what keeps a completion across a programme replacement, a reset, and a module deselection. An explicit removal is the operation that drops it.

`programmeOutcome(state, operation, content, completedCourseIds, pull)` is the one owner of the programme operations. It computes the next programme list, the scoped edits, the pulled courses and the uncompleted discards of one `ProgrammeOperation`:

- `{ kind: "add", groupId, versionId }` refuses a programme the list already holds with `Programme is already added`, appends the identity, and adopts the appended programme's official defaults while it records the courses that programme pulls. The picked exact id joins the prospective version map, and an entry that disagrees with the stored map refuses the write. A programme another node of the tree displays moves to the list with its whole current subtree, which `moveScope` rewrites for the top-level key. The addition drops that programme's own placement record before the after tree resolves, because the ordered list renders the identity and a record, a removal record included, would suppress its entry.
- `{ kind: "replace", groupId, replacementGroupId, versionId }` keeps the affected position, refuses an identity that another top-level position holds, reads the replacement node of the state that starts the operation, clears the old scope with `resetScope`, and records the courses the replacement pulls. The picked exact id joins the prospective version map under the same conflict rule.

  A replacement programme that the tree already displays keeps its own subtree: `moveScope` rewrites its records for the top-level key and the clearing reads the official homes without the keys of the moved node, so the moved choices, additions and removals survive while the replaced programme's own records clear around them, and the replacement's own placement record is dropped before the after tree resolves, because the ordered list renders the identity and a record, a removal record included, would suppress its entry.

  A replacement the tree does not display adopts its official defaults, and its clearing and its adoption both read the edits that already dropped that record, so a removal record of that identity does not suppress its top-level entry.
- `{ kind: "reset", groupId }` applies the clearing outcome with the same identity, and it lists the courses that clearing returns to the scope through `scopePulls`.
- `{ kind: "delete", groupId }` removes the identity and clears the same scope, and it works for the last programme.
- A missing programme or a report the content lacks raises `Programme is unavailable`, and no branch fetches, falls back or writes.

`changeProgrammes(store, operation, content, removeCompletedCourses = false, pull = true, moduleVersions?)` runs that outcome inside `applyStructure` and writes the full next structure with the uncompleted discards of the affected programme. Its trailing `moduleVersions` is the prospective selection the operation's reports were read under, it defaults to the stored map, and an entry that disagrees with the stored map raises `Another version of this module is already selected` without a write. Its `removeCompletedCourses` flag is the destructive choice of the entry point that offers one.

For a delete it is **Delete all**: the affected programme's completed courses join `removedCourseIds`, which takes them out of both course sets, and a `null` placement takes them out of the tree so no surviving programme brings them back. For a reset it is **Reset all**, which passes the prepared ordinary change to `resetCompletionChange`. An ordinary reset and every delete without the flag write the ordinary change.

Its `pull` flag is whether the addition, the replacement and the reset move the listed courses in, and a kept reset keeps its listed records through `keepCoursePlacements`. The write resolves the current forest from the callback's current stored structure and passes it with the final projection to `forgetRemovedModuleVersions`, so the departing programme and every nested module it rendered lose their version entries while retained groups keep theirs.

`resetCompletionChange(state, scopeKey, content, ordinary)` adds the destructive reset outcome to one prepared ordinary reset change. It resolves the pre-reset forest from the callback's state and requires the target node, raises `Programme is unavailable` or `Structure target is unavailable` when either is absent, and reads `removedCompleted` as the intersection of that node's subtree identities with `state.completedCourseIds`, so only a completion the scope actually holds is cleared.

It copies the ordinary change's course placements and leaves its choices, module placements and programme list as they are. A restored placement is kept when the candidate projection locates that identity inside `scopeKey`, and set to `null` otherwise, so a discarded completion cannot fall back into an untouched holder and a restored mandatory course is selected.

It returns the ordinary change with the final placement map, the final placed identities, and `removedCourseIds` equal to `removedCompleted`, and it preserves the ordinary change's uncompleted discards and pending-import field. `applyStructure` removes `removedCourseIds` from both course sets before it appends the placed identities, which is the order that selects a restored mandatory course as uncompleted.

`programmeMoves(state, operation, content)` returns the listed moves of the same outcome, so an interface confirms them before the write and a cancelled confirmation writes nothing, and it answers a reset with the courses that reset returns to its scope through `scopePulls`. `displayedPlace(state, content, groupId)` returns the localized node that displays one identity of that state, and a direct `u` bucket entry answers with no node because that bucket holds unplaced items by definition.

`resetUnplaced(store, content)` resolves the forest, collects the courses of the `u` subtree and the selected courses outside the whole forest, drops the `u` choices, keeps a placement whose target is outside the bucket, turns a placement into the bucket into `null` when the identity has an official home outside it, and commits the resulting projection with the collected identities as uncompleted discards.

`removeFromSelection(store, courseId)` drops the identity from both course sets.

## Where a change belongs

- A change to how a place is stored, cleared, or discarded belongs in `edits.ts` and in `applyStructure` in `actions.ts`.
- A change to a programme operation belongs in `programmeOutcome` in `actions.ts`, which the write and the move list share.

## Tests

| File | Covers |
|---|---|
| `web/src/features/structure/edits.test.ts` | `resetScope` discarding only what is scoped to a node, a removal of an identity with no official home leaving no entry, and an added module using the resolved destination key while the selected courses and the completion are kept, with no listed move when the courses follow their module, the real pane drawing that module and its course under the destination node, and a passive mount and remount preserving the saved structure and course sets |
| `web/src/features/structure/actions.test.ts` | The deselection of a completion, the explicit removal that takes the completion too, a shared course moving into an added holder and staying out of an untouched holder, the scoped programme replace and reset that keep the other programme and the loose courses, the deletion of a programme including the last one, the module lifecycle outside the bucket, and the Unplaced studies reset restoring the official structure |
