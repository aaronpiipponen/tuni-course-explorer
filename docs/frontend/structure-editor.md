# Structure editor

The structure editor shows the official structure of studies and applies the choices, additions and resets that belong to the open profile.

## The official report and the profile's own parts

The tab shows one [structure root](/docs/reference/glossary.md#discovery-and-the-structure-of-studies) at a time. Its official modules, courses and rules come from the server as one structure of studies report for the configured academic year, so the same report serves every reader and only the root identity travels with the request. The profile adds its own parts on top: the choices it makes between alternatives, the places it gives to the courses and modules it adds or moves, and the identity of the root.

The report is read when the tab is opened with a root set, and again when the root changes. [Structure of studies in the catalogue](/docs/backend/catalogue/study-structure.md) describes the report itself.

The diagram follows the two inputs of the tab through a user action to the saved profile and the shared selection.

![The official structure report and the saved profile edits together produce the displayed structure. A user action chooses, moves or resets a module, course or option, which saves the profile edits and updates the shared selection. A selected course with no place is listed under Unplaced studies, and a completed course left without a place keeps its completion and is shown there.](/docs/diagrams/structure-editing-flow.svg)

## Choosing the root

With no root, the tab shows a prompt and **Choose root**. The picker narrows the programmes and modules by name or by code with a text filter, and it lists the matches in the order the read returns, which places the degree programmes before the other modules and orders each group by the displayed name and the code. Each row is marked as a programme or a module and carries its code and its name. Picking one loads its report and makes it the root. **Change root** opens the same picker, and picking the current root closes the picker without a change.

Changing the root discards the choices and the places of the previous structure and starts from the official content of the chosen root. A course that the chosen structure holds becomes selected, and a course of the previous structure that the chosen one does not hold leaves the selection unless it is completed. A completed course is kept by the change.

## Modules, courses and choices

Each module of the root is a row that opens expanded and carries a control to collapse it, and the root itself is a row of the same kind. A row shows the name, the code and kind, the selected credits and the completed credits. Opening the row body shows the drawer of that module, which leads with the official rule of the module and the same credit totals, and a course that was added carries the **added** mark.

Official content that the rule requires from everyone is shown directly as course cards, with the official code, name, credits and activity state of each course. A rule that offers a choice between alternatives is shown as a choice, and its drawer names how many options it offers and marks the options that are chosen. A rule that only wraps other rules is shown as the content it wraps, so a wrapper never adds a step. A reference the official data cannot resolve is shown as a note with its reason.

Each course card carries a control that marks the course completed and unmarks it. The completion belongs to the shared course sets, so a course marked here reads as completed in every other tab.

The drawer of a module also adds content. Its search box narrows courses, modules and degrees by name or by code, and one result is added to that module. An added module is nested inside the module that received it, and a module cannot be added inside itself. Adding a module reads its report, and the row shows as busy until the report arrives.

## Selection, places and moving

Every course on a structure card belongs to the profile's selection. A card in a module row or under Unplaced studies is content of the displayed structure or a course that was added, and the tab keeps the selection in step with the cards it draws. Selecting a course adds it to the selection, and marking one completed selects it as well. A course is shown on one card at a time, so a course that already has a place is not drawn again in another node of the displayed structure.

The drawer is where a choice is made, and what it lists is not the selection. Its rule rows list the alternatives that a rule offers, and its search lists the narrowing results for a module, a course or a degree. An option joins the selection when it is chosen.

A course or a module that already has a place is moved rather than duplicated. Selecting such a course into another module, or moving a placed course or module into a node, opens **Move here?**, which names the item and the node that holds it. **Move** places it there, and **Cancel** leaves the structure as it is. A move of a module carries the courses it contributes with it, and a brief notice reports how many courses moved.

A choice between alternatives is toggled in the drawer. A choice that admits one option holds a single option, and a choice that admits several holds every option that is selected. The removal of an official course or module from a node is remembered, so the node does not show it again.

## Unplaced studies

[Unplaced studies](/docs/reference/glossary.md#discovery-and-the-structure-of-studies) is the part of the tab that holds the profile's courses with no place. A selected course that the displayed structure does not hold is listed there, and choosing one in that drawer takes it out of the selection.

The course menu item **Add to Unplaced studies** adds a course to it. With no root set, a root prompt names the courses to add and offers the programme and module picker. Picking a root there loads it and then adds the courses to Unplaced studies, and cancelling the prompt leaves the selection as it is.

## Deselecting a course or a module

Deselecting a course takes away its place. A course that is not completed leaves the selection with it.

A completed course is always selected, so a deselection of one opens **Completed course**, which offers two outcomes. **Move** places it under Unplaced studies and preserves its completion. **Remove** takes it out of the selection together with its completion, so the course leaves both course sets and every tab reads that at once. **Cancel**, or Escape, leaves the selection as it is.

Deselecting a module takes the courses it holds out of the displayed structure. A completed course among them holds its completion and its place in the selection, and appears under Unplaced studies, while an uncompleted course among them leaves the selection.

## Resetting a part or the whole

The drawer of a module or of the degree ends with a reset control for that part, **Reset this degree** for the root and **Reset this module** for a module or for Unplaced studies. A reset restores the official choices and the official places inside the degree or the module, and a course inside the part returns to its official place. A reset of Unplaced studies clears the places there, returns a course to its official place when the structure holds one for it, and takes an uncompleted course that was placed there out of the selection. A completed course keeps its completion through a reset.

**Reset all** opens **Reset all structure changes?**, whose **Reset** button restores the whole official structure. A course with an official place returns to it, a completed course with no official place is held in the selection under Unplaced studies, and an uncompleted course added without an official place leaves the selection. Changing the root has the same effect on the previous structure as **Reset all** has on the current one.

## Stored state, waiting and failure

The root, the choices and the places belong to the profile, so they are there each time the tab is opened, and the server answers a structure read from the official data alone. Reading the official report, adding a module, and loading the content of a placed course each show a waiting state.

A failed read or a failed add shows a notice with the failure. While the placed content of a structure loads, the pane keeps the structure it drew last and re-projects it in the current language, and a failure of that read replaces the tree with the notice. An add that finishes after the root changed fails with a notice and writes nothing. A module move whose destination cannot be resolved fails with a notice that names the failure.

The rule projection, the resolution of the choices and the places, and the tests that cover them are described in [Structure model](/docs/frontend/structure-model.md).
