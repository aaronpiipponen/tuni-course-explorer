# Planning a structure of studies

The Structure of studies tab shows the official structure of a degree programme or module and lets you place, complete and remove courses inside it.

## Choosing the root

The tab follows one degree programme or module at a time. That choice is the structure root, and the whole tree is drawn from it.

Open **Structure of studies** before any root is set and the tab asks you to pick a programme or module to build your structure of studies. Select **Choose root** to open the picker. The filter narrows programmes and modules by name or by code, and each match shows its code, its name, and whether it is a programme or a module. Pick one to load its tree.

Select **Change root** to open the same picker. Picking the root that is already open closes the picker without a change. Picking a different root discards the choices and the places of the structure that is open and rebuilds the tree from the official content of the chosen root. That pick reports **Root changed: customisation discarded, completed courses retained**, and the first pick that sets a root reports no notice. A course that the chosen structure places becomes selected. A course that the previous structure placed and the chosen one does not leaves the selection, unless it is completed.

## Reading the tree

Each module of the root is a row, expanded when the tab opens, with a control that collapses it. The root itself is a row of the same kind. A row carries the module name, its code, whether it is a programme, a module, or Unplaced studies, and the credits of the courses placed under it, written as selected first and completed second, such as `15 | 5 cr`.

A course is drawn as a card with its code, its name, its credits, and whether it is active. Each card opens the [course menu](/docs/guides/README.md#shared-course-state), with **Add to Unplaced studies**, **Mark completed**, and the other shared actions. Each card also carries **Complete**, which marks that course completed. A completed card shows **Completed** and reads as completed in every other tab.

Where a rule offers a choice between alternatives, the tree shows the alternatives you chose, and you pick among them in the drawer. A rule that only groups other rules adds no row of its own, so the tree shows the content it wraps.

An official reference that cannot be resolved is shown as a note in place of its content, for example **Module not found**, **Course is missing**, **This module has no rule**, or **Unresolved requirement**.

![The Structure of studies tab with its Change root and Reset all controls, a programme row and module rows, an Unplaced studies row, and course cards that carry a Completed mark and a Complete control.](/docs/screenshots/structure-of-studies.png)

## Reading the rules

The drawer of a module lists its content under the rule that applies to it, and the app labels that rule.

A rule that pairs a credit target with a choice shows both parts, joined by a middle dot, such as **min 20 cr · choose 1**.

The drawer of a module leads with the rule of that module. For a module or a degree with target credits the rule is that credit extent, such as `180 cr`. The credits on a row count the courses placed under it, and the same two totals appear in the drawer with the words **selected** and **completed**.

## Unplaced studies

Unplaced studies is the last row of the tree. It holds the courses in your selection that no module of the displayed structure holds.

A course arrives there in one of these ways:

- The course menu item **Add to Unplaced studies** adds it from any card in the app.
- A completed course that is moved out of a module is listed under Unplaced studies with its completion.
- A selected course that the chosen structure does not hold is listed there.

With no root set, **Add to Unplaced studies** opens **Choose a root first**, which explains that Unplaced studies belong to your structure of studies and names the courses to add. Pick a programme or module in that prompt to start the structure, and the courses are added to Unplaced studies once it loads. **Cancel** closes the prompt and leaves the selection as it is.

Select a course row in the Unplaced studies drawer to take that course out of the selection. A completed course in that drawer opens the **Completed course** dialog instead.

## Placing courses from the drawer

Select the name of a module row to open its drawer. The drawer leads with the rule of that module and its credit totals, then lists its content and a search. A drawer with no content reads **This module is empty.**, or **No option selected yet.** for a choice where nothing is picked.

The search field asks you to search courses, modules and degrees to add. The buttons **All**, **Courses**, **Modules** and **Degrees** narrow the results to one kind. Each result shows its code, its name, and either its credits or the kind of module it is. Pick a result to place it in the module that you opened. A course is placed there as a card with a dashed outline. A module arrives with its own content, its row carries the **added** mark, and the app reports that it was added, together with how many of your courses moved with it when any did.

Adding a module reads its structure before it is placed, and the row shows as busy until the read finishes. If the course or the module is already in that module, the app reports **Already in this module**.

A rule that offers alternatives is decided in the drawer too. The section heading is the rule label, and its rows are the options. Select a row to choose it and select it again to drop it. The first selection reports **Selection made**, and a change to a selection that already exists reports **Selection changed: completed courses kept, other courses dropped**. A course that loses its place leaves the selection unless it is completed, and a completed course is held in the selection under Unplaced studies.

![The drawer of a module, leading with the module's credit rule and its selected and completed credit totals, then the search field that adds courses, modules and degrees, an all required section and a choose 1 section with their course rows and Complete controls, and Reset this module at the foot.](/docs/screenshots/structure-drawer.png)

## Moving a course that already has a place

Every course and module appears in one place at a time. Placing one that already has a place opens **Move here?**, which names the course or module and the place that holds it, such as a module or Unplaced studies. Select **Move** to place it there, or **Cancel** to leave the structure as it is. A move of a module carries the courses it contributes with it.

## Removing a course

Courses are taken out in the drawer of the module that holds them. Select a course row in the drawer content to remove it from that module.

An uncompleted course leaves the selection with it. A completed course opens **Completed course**, which offers two outcomes:

- **Move** places the course under Unplaced studies and preserves its completion.
- **Remove** takes it out of the selection and removes its completion, so the course leaves both course sets in every tab.

**Cancel**, or Escape, closes the dialog and leaves everything as it is.

> [!WARNING]
> **Remove** in the **Completed course** dialog removes the completion itself. The course is then neither selected nor completed anywhere in the app.

![The Completed course dialog over the Structure of studies tab, naming the course code and offering Move, Remove, and Cancel.](/docs/screenshots/structure-completed-course-dialog.png)

Select a module row in the drawer content to remove that module and the courses that it contributes from the displayed structure. A completed course among them preserves its completion and appears under Unplaced studies, and an uncompleted course among them leaves the selection.

## Resetting a part or the whole

The drawer ends with a reset control for the part that it shows, **Reset this degree** for the root programme and **Reset this module** for a module. In the Unplaced studies drawer the control reads **Reset this module** as well.

A reset returns the choices and the places inside that part to the official ones, and a course inside the part goes back to its official place. A completed course preserves its completion through the reset, and the app reports **Module reset to its official contents**.

A reset of Unplaced studies clears the places held there. A course with an official place goes back to it, an uncompleted course that was placed there leaves the selection, and a completed course preserves its completion. The app reports **Unplaced studies reset**.

**Reset all** opens **Reset all structure changes?**, with **Cancel** and **Reset**. **Reset** restores the whole official structure and reports **Reset to the official structure**. A course with an official place returns to it, a completed course with no official place is held under Unplaced studies, and an uncompleted course that was added without an official place leaves the selection.

> [!CAUTION]
> A reset discards the choices and the places of the part that it resets. Changing the root discards them for the whole structure.

## Your edits and the official structure

The root, the choices, and the places belong to the open [profile](/docs/guides/profiles-and-language.md), so the tab opens with them again the next time you visit it. The official structure that the server sends is the published structure, shared by every profile. Another profile holds its own structure, and **Reset all** is how the open profile returns to the official one.

How the tab projects the official rules, resolves your choices and places, and stores them in the profile is described in [Structure editor](/docs/frontend/structure-editor.md).
