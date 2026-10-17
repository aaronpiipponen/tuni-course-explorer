# Planning a structure of studies

The Structure of studies tab shows the official structure of each of its programmes and lets you place, complete, replace and remove courses inside them.

## Adding a programme

The tab holds an ordered list of programmes, and each one is a degree programme or a module. The list starts empty, and **Add programme** sits between the last programme and **Unplaced studies**.

Select **Add programme** to open the picker. The filter narrows programmes and modules by name or by code, and each match shows its code, its name, and whether it is a programme or a module. Pick one to add it at the end of the list and read its tree. The courses that its official structure proves required are placed in it and selected. A programme that the list already holds is refused with **Programme is already added**. A programme that already sits somewhere in your structure moves to the end of the list with everything you had put inside it, and it asks for that move first. The picker is open again after a course dialog that you cancel, so you can pick another programme.

Each programme row carries a **⋯** control, which opens its menu:

- **Replace programme** asks which programme takes its place, closes the picker, and then asks you to confirm.
- **Reset programme** restores that programme's official content.
- **Delete programme** removes it from the list and always asks first, whether or not the programme holds a change or a completed course. Deleting the last programme returns the tab to its empty list with **Add programme** and **Unplaced studies**.

![A top-level programme row with its ⋯ control, and the menu it opens below the row listing Replace programme, Reset programme and Delete programme, the last in red.](/docs/screenshots/structure-programme-menu.png)

**Replace programme** names the programme that leaves and the programme that takes its place, and it lists the courses that the replacement pulls out of another holder. When it lists a course, the answer is **Keep**, which replaces the programme and leaves each listed course where it is shown now, or **Pull**, which replaces it and moves them in. When the replacement already sits somewhere in your structure, the dialog also names that place, because the replacement moves from there with everything inside it and pulls no course. **Reset programme** always asks, with **Cancel** at the left edge and **Reset** beside it, and **Reset all** joins them at the right only when the programme holds completed courses. **Reset** restores the programme's official content and preserves its completed courses, and **Reset all** also clears the completions the programme holds immediately before the reset. **Delete programme** asks with **Cancel** at the left, then **Delete**, and it adds **Delete all** beside **Delete** when the programme holds completed courses. **Cancel**, Escape, and a click outside the dialog change nothing, and no other programme and no loose course is affected.

A completed course of the affected programme keeps its completion and takes its official place in the new content, and with no official place left it is listed under **Unplaced studies**. An uncompleted course of the affected programme leaves your selection. **Delete all** drops the programme's completed courses and their completions as well. A course that the official structure requires comes back from **Reset all** selected and uncompleted when the programme held it before the reset; a course returned from another place by **Pull** was not held there, so it keeps its completion.

![The Structure of studies tab with two programme rows, each carrying a ⋯ menu before its credit counters, completed course cards under them, the Add programme row between the last programme and Unplaced studies, and the Unplaced studies row last.](/docs/screenshots/structure-of-studies.png)

## Reading the tree

Each module of a programme is a row, expanded when the tab opens, with a control that collapses it. The programme itself is a row of the same kind. A row carries the module name, its code, whether it is a programme, a module, or Unplaced studies, and the credits of the courses placed under it, written as selected first and completed second, such as `15 | 5 cr`. Only a row at the top level of the list carries the programme menu. A degree programme added inside a programme or a module shows the word programme where the row is labelled, and every control and every action on it matches a module.

A course is drawn as a card with its code, its name, its credits, and whether it is active. Each card opens the [course menu](/docs/guides/README.md#shared-course-state), with **Add to Unplaced studies**, **Mark completed**, and the other shared actions. Each card also carries **Complete**, which marks that course completed. A completed card shows **Completed** and reads as completed in every other tab.

Where a rule offers a choice between alternatives, the tree shows the alternatives you chose, and you pick among them in the drawer. A rule that only groups other rules adds no row of its own, so the tree shows the content it wraps.

An official reference that cannot be resolved is shown as a note in place of its content, for example **Module not found**, **Course is missing**, **This module has no rule**, or **Unresolved requirement**.

## Reading the rules

The drawer of a module lists its content under the rule that applies to it, and the app labels that rule.

A rule that pairs a credit target with a choice shows both parts, joined by a middle dot, such as **min 20 cr · choose 1**.

The drawer of a module leads with the rule of that module. For a module or a programme with target credits the rule is that credit extent, such as `180 cr`. The credits on a row count the courses placed under it, and the same two totals appear in the drawer with the words **selected** and **completed**.

## Unplaced studies

Unplaced studies is the last row of the tree. It holds the courses in your selection that no programme or module holds.

A course arrives there in one of these ways:

- The course menu item **Add to Unplaced studies** adds it from any card in the app.
- A completed course that is moved out of a module is listed under Unplaced studies with its completion.
- A selected course that no programme holds is listed there.

**Add to Unplaced studies** adds the course at once, whether or not the programme list holds a programme. A course added while the programme list is empty appears in this list.

Select a course row in the Unplaced studies drawer to take that course out of the selection. A completed course in that drawer opens the **Completed course** dialog instead, which offers **Cancel** and **Remove** alone and states that the removal takes the course out of your selection together with its completion.

## Placing courses from the drawer

Select the name of a module row to open its drawer. The drawer leads with the rule of that module and its credit totals, then lists its content and a search. A drawer with no content reads **This module is empty.**, **This programme is empty.** when the row is a programme, or **No option selected yet.** for a choice where nothing is picked.

The search field reads **Add a course, module or programme**. The buttons **All**, **Courses**, **Modules** and **Programmes** narrow the results to one kind. Each result shows its code, its name, and either its credits or the kind of module it is. Pick a result to place it in the module that you opened, which closes the search. A course is placed there as a card with a dashed outline. A module arrives with its own content, its row carries the **added** mark, the courses that its official structure proves required are placed in it and selected, and the app reports that it was added, together with how many of your courses moved with it when any did.

Adding a module reads its structure before it is placed, and the row shows as busy until the read finishes. If the course or the module is already in that module, the app reports **Already in this module**, or **Already in this programme** when the row is a programme.

A rule that offers alternatives is decided in the drawer too. The section heading is the rule label, and its rows are the options. Select a row to choose it and select it again to drop it. The first selection reports **Selection made**, and a change to a selection that already exists reports **Selection changed: completed courses kept, other courses dropped**. A course that loses its place leaves the selection unless it is completed, and a completed course is held in the selection under Unplaced studies.

![The drawer of a module, leading with the module's credit rule and its selected and completed credit totals, then the search field that adds courses, modules and programmes, an all required section and a choose 1 section with their course rows and Complete controls, and Reset this module at the foot.](/docs/screenshots/structure-drawer.png)

## One place for a course

A course shows on one card at a time. The later addition wins: adding or replacing a programme, or adding a module, that officially holds a course already shown elsewhere moves the course into the new holder, and keeps its completion and its selection. Before that addition writes anything, one dialog lists every course that will move and the place each one is in now, and **Move** applies the whole addition when it lists nothing. When it lists courses, the answer is **Keep**, which applies the addition and leaves each listed course where it is shown now, or **Pull**, which applies it and moves them in. When the addition moves the module itself, the dialog reads **Move here?** and names the module and the place that holds it, or **the programme list** when the list of programmes holds the module, and it lists the courses the addition pulls out of another holder when it pulls any. **Cancel**, Escape, and a click outside the dialog change nothing, and the **Add programme** picker stays open so you can pick again. There is no dialog when nothing moves. A course of a holder that is new to the structure and sits directly in **Unplaced studies** moves without being listed, while a holder that already has a place keeps everything it holds, the courses in Unplaced studies included. **Replace programme** shows the same list inside its own confirmation, which also names the place that already holds the replacement programme when a place does.

## Moving a course that already has a place

Every course and module appears in one place at a time. Placing one that already has a place opens **Move here?**, which names the course or module and the place that holds it, such as a module, Unplaced studies, or **the programme list** when the ordered list of programmes holds it. Select **Move** to place it there, or **Cancel** to leave the structure as it is.

A move of a module takes the whole of it along, so the alternatives you chose inside it, the courses and modules you added or removed there, and the completions all arrive with it, its old place disappears, and nothing inside it returns to the official structure. A module that the programme list holds leaves that list when it is placed in a node, so it appears only in the place you put it. A module that an addition or a replacement promotes to the top level of the list moves the same way, so a programme that you replace with a programme it contains keeps that programme and everything inside it. The move pulls no course out of another programme or a module, so a course that another holder shows stays there and nothing is added inside the moved item.

A course or a module that sits directly in **Unplaced studies** moves into a programme or a module without a prompt of its own, because that list holds unplaced items by definition. A course that an addition pulls out of a programme or a module is listed for confirmation, and a move from a programme or a module asks first.

## Removing a course

Courses are taken out in the drawer of the module that holds them. Select a course row in the drawer content to remove it from that module.

An uncompleted course leaves the selection with it. A completed course opens **Completed course**, which offers these outcomes:

- **Move** places the course under Unplaced studies and preserves its completion.
- **Remove** takes it out of the selection and removes its completion, so the course leaves both course sets in every tab.

A completed course that already sits under Unplaced studies carries **Cancel** and **Remove** alone, and the dialog states that the removal takes the course out of your selection together with its completion, because keeping a course loose there changes nothing.

**Cancel**, or Escape, closes the dialog and leaves everything as it is.

> [!WARNING]
> **Remove** in the **Completed course** dialog removes the completion itself. The course is then neither selected nor completed anywhere in the app.

![The Completed course dialog over the Structure of studies tab, naming the course code and offering Move, Remove, and Cancel.](/docs/screenshots/structure-completed-course-dialog.png)

Select a module row in the drawer content to remove that module and the courses that it contributes from the displayed structure. A completed course among them preserves its completion and appears under Unplaced studies, and an uncompleted course among them leaves the selection. A module that holds completed courses, or whose contents differ from its official structure, asks first: **Delete** keeps that outcome, and **Delete all** drops those courses and their completions with the module. **Delete all** appears only when the module holds completed courses. **Cancel** sits alone at the left of the question, and the delete controls sit together at the right. A module at its official structure with no completed course leaves at once without a question, and a saved choice or place that leaves its contents unchanged is not a difference. A degree programme nested inside another programme or a module follows the same rule as a module, with the word programme in its question.

## Resetting a part

The drawer of a module ends with **Reset this module**, and the drawer of a top-level programme ends with **Reset programme**, which is the same operation as the row menu's **Reset programme** and asks with the same question. A degree programme nested inside another programme or a module reads **Reset programme** as well, and its operation stays a module's.

A module or a programme resets through one compact question with **Cancel** at the left and **Reset** beside it, and **Reset all** joins them at the right only when the part holds completed courses. **Reset programme** asks from the row menu and from the drawer, and **Reset this module** asks from the drawer, at every press, whatever the part's contents and completions are. When the reset returns a course to the part from another holder, a second question follows with **Cancel** at the left and **Keep** and **Pull** at the right: it lists every returned course with the place it is in now, **Pull** returns those courses to the part, **Keep** leaves each of them where it is, and **Cancel** cancels the whole reset and changes nothing. A part that holds no completed course and returns a course asks only that second question. **Cancel**, Escape and a click outside a question change nothing.

**Reset** returns the choices and the places inside that part to the official ones, and a course inside the part goes back to its official place. A course whose official place is inside the part and which another holder shows now returns there only when the second question is answered **Pull**, and **Keep** leaves it in that other holder. A completed course inside the part keeps its completion, and when the restored content gives it no place it is listed under **Unplaced studies**. **Reset all** applies the same restoration and also clears the completions that the part holds: a course that the part held before the reset comes back selected and uncompleted, a course returned from another place by **Pull** keeps its completion, and a completed course that leaves the restored content leaves your selection together with its completion. A completed course that another programme or **Unplaced studies** holds is not affected. A reset reports **Programme reset to its official contents** or **Module reset to its official contents**, for the word its part carries.

A reset of Unplaced studies clears the places held there and asks nothing. A course with an official place goes back to it, an uncompleted course that was placed there leaves the selection, and a completed course preserves its completion. The app reports **Unplaced studies reset**.

> [!CAUTION]
> A reset discards the choices and the places of the part that it resets. Replacing or deleting a programme discards them for that programme alone.

## Your edits and the official structure

The programmes, the choices, and the places belong to the open [profile](/docs/guides/profiles-and-language.md), so the tab opens with them again the next time you visit it. The official structure that the server sends is the published structure, shared by every profile. Another profile holds its own structure, and **Reset programme** on a row is how one programme of the open profile returns to the official content.

How the tab projects the official rules, resolves your choices and places, and stores them in the profile is described in [Structure editor](/docs/frontend/structure-editor.md).
