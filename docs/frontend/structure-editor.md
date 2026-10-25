# Structure editor

The structure editor shows the official structure of each of its ordered programmes and applies the choices, additions and resets that belong to the open profile.

## Programmes and the official report

The tab holds an ordered list of top-level programmes. A programme is a degree programme or a bare module, each with its own official tree, and the global **Unplaced studies** row sits after the last of them. The official modules, courses and rules of a programme come from the server as a structure of studies report for the configured academic year, so the same report serves every reader.

A request carries the root identities and the profile's exact module-version selections, and a held report answers only its own serving dataset identity and selection identity. The tab reads every missing root in one batch, holds the reports in the shared memory cache and in a derived IndexedDB store keyed by both identities, and renders a held report across a reload before any structure request.

The profile adds its own parts on top: the choices it makes between alternatives, the places it gives to the courses and modules it adds or moves, and the ordered programme list itself.

The report of a programme is read when the programme joins the list, and every missing report is read in one batch when the tab needs it. A held report of the same serving identity and selection identity renders at once. [Structure of studies in the catalogue](/docs/backend/catalogue/study-structure.md) describes the report itself.

The diagram follows the two inputs of the tab through a user action to the saved profile and the shared selection.

![The official programme reports and the saved profile edits together produce the displayed programmes. A user action chooses, moves or resets a module, course or option, which saves the profile edits and updates the shared selection. A selected course with no place is listed under Unplaced studies, and a completed course left without a place keeps its completion and is shown there.](/docs/diagrams/structure-editing-flow.svg)

## Adding, replacing and deleting a programme

**Add programme** is a full-width row between the last programme and **Unplaced studies**, and it is there in an empty configuration as well. While the list holds no programme, the same area also offers the **Import** area of [Profiles and language](/docs/guides/profiles-and-language.md#importing-a-file), with **Choose file**, a drop target, **Copy Sisu import script** and a **?** help drawer that explains the import and the Sisu plan, and the same three confirmations, without the export controls. A grey rule separates that import area from **Unplaced studies**.

**Add programme** opens the programme picker and adds the chosen programme at the end of the list. A programme that the list already holds is refused with **Programme is already added** and writes nothing. A programme that another node of the tree displays moves to the end of the list with its whole current contents, and the holder move confirmation described under Shared courses and the later addition covers it.

Each top-level programme row carries a **⋯** control before its credit counters. On a phone it sits on the title row at the right, level with the expand control at the left. Its menu holds **Replace programme**, **Reset programme** and **Delete programme**, in that order, and the last of them is muted red. Nested module rows carry no menu, and a degree programme nested inside another programme or module is a nested module row, so it carries no menu and every control and action on it matches a module. Its kind label, its reset control, its reset question and its removal question name it a programme, because the official degree type selects those nouns alone. A menu opens and closes like every other menu, and it needs no confirmation of its own.

The picker narrows programmes and modules by name or by code over the one cached minimal official catalogue, and a keystroke sends no request. It lists the matches with the degree programmes before the other modules, then by each row's displayed name and code, then by canonical group identity. The picker holds every match in the list and mounts only the visible rows, a few rows beyond the window and any row the keyboard reaches, with the first and last match always mounted. The keyboard moves between the logical rows with Tab, Shift+Tab, the arrow keys, Home and End, including rows outside the window, and Enter or Space activates the focused row.

One row stands for one canonical module group, shows its official code and name alone, and its virtual-list key is the canonical group identity. The group matching rule is stated in [Search](/docs/backend/search-and-discovery/search.md#the-minimal-official-catalogue). The matching candidates of one group are compared by displayed name and code, with the exact version identity as the last tie-break, and that order picks the name and code the row displays. Display order selects no version.

A group with one eligible version adds that version at once. A group with several eligible versions replaces the results with one **Cancel** control before the shared version picker for that group, which lists every eligible version with its validity bounds, curriculum periods and full exact identity. The ambiguous hand-off writes nothing, a version reaches the structure only after an explicit pick in the picker, and **Cancel** restores the query text with focus in its field.

At widths up to 760 pixels a row sets its code on the first line and its name on the second, the name wraps at any character, and the whole row is the activation target. At 680 pixels and below the name clamps to two lines. Across those widths the hand-off's version list scrolls inside its own 300-pixel bound, while the ordinary root search list keeps the pane's full height.

A structure keeps at most one exact version per canonical group. A root group the server settles as needing a selection, and a nested group whose ambiguity the resolved projection keeps while no Sisu capture waits, each show one inline version picker above the tree: every candidate of that group with the shared label and a native **Select** action, no text query and no arbitrary default. A selection writes only its own map entry. While any group needs a selection, normal reconciliation, pending Sisu placement and tree or programme mutations are suspended so no saved structure is reconciled away, and the picker is reachable even when a required root report is absent.

A nested reference belongs to the plan only while it is selected and unsuppressed: a placement that names another node excludes its whole subtree, an option the profile does not choose contributes nothing, and a reset that clears a branch's choices drops that branch. The drawer can offer unselected optional content as a note without requiring its version. A root the server settles as needing a selection asks for one whatever the edits remove. While a Sisu capture waits, only the server's settlement of the roots the capture requests asks for a version, and the projection's nested requirements join the gate once the capture is placed.

A pick that would select a second version of a group already holding another raises **Another version of this module is already selected** and writes nothing. It never replaces a customised subtree in place. An identity imported from a schema-3 profile or a Sisu capture that is not eligible for its group is a whole-pane error, keeps the stored or pending data unchanged, and offers no automatic substitution or recovery picker.

An operation that removes a group from the displayed tree forgets that group's version entry in the same write, while every group the tree renders keeps its own entry. A removed programme, module or optional descendant is therefore added again with any explicit version, and the selection of a retained group never changes. A selection for a group the tree has not displayed yet keeps its entry.

The kind marker follows the official module type, so a top-level bare module reads **module** while it holds the programme menu and reset of its position. Choosing a search row with one eligible version places that exact version, and a row with several opens its version picker first. The same picker serves **Replace programme**, where the picked group and its exact version become the replacement.

**Add programme** and **Replace programme** open the same picker, pinned to the visible tab area in the same place whatever the scroll position of the tab, and it never moves to the control that opened it. On a phone it fills the tab area from the top edge to the bottom bar. The backdrop of that picker covers the whole pane, the tree's padding and the strip above the first row included, and its presses reach nothing behind it, and the picker narrows while a drawer is open.

Dismissing the picker with Escape, **Close** or a press outside it returns focus to the control that opened it, and focus moves to **Add programme** when that control has left the document. A pick that adds the programme restores focus the same way once the addition finishes.

A **Replace programme** pick of the programme that already holds the replaced place writes nothing and closes the picker with the same focus restoration when the version the place renders equals the picked one. A missing hydrated version of that place fails the pick with **Programme is unavailable** and keeps the picker open, and a different hydrated version raises **Another version of this module is already selected**.

A **Replace programme** pick of a different programme closes the picker into that replacement's confirmation, whose first control receives focus and which returns focus to the captured control when it is cancelled. A replacement preview that fails or is refused keeps the picker closed, opens no confirmation and restores focus to the captured control, or to **Add programme** when it has left the document. The picker of **Add programme** is open again when a course-pull dialog is cancelled or a pick fails.

**Replace programme** names the programme that leaves and the programme that takes its place in its own confirmation. That confirmation states that the replaced programme's customisation and its uncompleted courses leave the structure while its completed courses are kept, it lists the pulled courses, and a replacement programme that another node already displays reads with the place that holds it, because the replacement moves from there with its whole contents. The confirmation carries **Cancel** and **Replace**, and a replacement that pulls a course carries **Keep** and **Pull** in place of **Replace**, so the answer states whether those courses move in.

**Reset programme** opens the shared compact reset question, which asks in every state with one short description: **Reset** preserves the completed courses, and **Reset all** stands beside it only when the programme holds a completed course, which it clears.

**Delete programme** removes that programme, and it works for the last one as well, which returns the tab to an empty configuration with **Add programme** and **Unplaced studies**. A deletion through the row menu always asks, and its question names the programme and offers **Cancel**, **Delete** and, when the programme holds a completed course, **Delete all**, which drops the programme's completed courses from the selection and the completion as well and takes them out of the tree.

**Cancel**, Escape and a click outside a dialog write nothing. **Cancel** sits at the left edge of each of these questions, with the remaining actions together at the right. A dialog restores focus to the control that opened it, and after a replacement or a deletion focus moves to **Add programme**.

A completed course of the affected programme keeps its completion and its place in the selection. It takes its first official place in the next content, or the place a surviving programme gives it, and with no official place left it is listed under **Unplaced studies**. An uncompleted course that the affected programme held leaves the selection. Every other programme and the loose courses under **Unplaced studies** keep their state. **Reset all** clears the completion of every course the affected part holds, so a course the part held before the reset comes back selected and uncompleted, a course returned from another place by **Pull** keeps its completion, and a discarded one leaves the selection with its completion. A completion that another holder owns is not affected.

Replacing, resetting or deleting a programme discards the choices and the places inside its scope, and a replacement programme that the tree already displays keeps its own subtree, which moves to the replaced position with it. A course that the affected programme held through a placement does not fall back into a programme the action leaves alone. A completed one is placed under **Unplaced studies** instead, and an uncompleted one leaves the display, so the other programme shows it as an official row that is not selected. Resetting the programme that holds the other node returns the course to its official contents there.

## Shared courses and the later addition

A course shows on one card at a time. The later addition wins: adding or replacing a programme, or adding a module, that officially holds a course already shown in another node moves the course into the new holder, keeps its completion and its place in the selection, and draws the move like any other move, while a holder the tree already displays is moved with its whole subtree and takes no course from another holder. First-occurrence order decides the courses that no such operation placed, so the first programme that holds a course draws it, and a later occurrence contributes neither a second card nor credits. An addition places the unavoidable official content of the added holder and selects it, including a module the stored records leave out of the tree and the courses that module holds, while a genuine optional alternative stays unselected.

Before an addition writes anything, one confirmation lists every course that moves and the containing programme or module that draws it now. **Cancel**, Escape and a click outside the dialog write nothing, with the **Add programme** picker still open for another pick. An addition that lists no course carries **Move**, which applies it whole. An addition that lists courses carries **Keep** and **Pull** beside **Cancel** at the right: **Pull** applies the addition and moves the listed courses in, and **Keep** applies it with every listed course left in the containing programme or module that shows it now. There is no prompt when neither the holder nor a course moves.

A course of a holder the tree does not render that sits directly in **Unplaced studies** moves without being listed, while a holder the tree renders keeps every course it holds there.

**Replace programme** shows that list inside its own named confirmation when its replacement pulls courses, and the confirmation also names the place that displays the replacement programme when a node does, so one prompt covers the replacement. An addition that moves the module itself covers both in that one confirmation: the title reads **Move here?**, the description names the module and the containing programme or module that holds it, or **the programme list** when the ordered programme list holds the module, and the list of moving courses follows when it has any. **Add programme** asks the same way when another node already displays the added programme.

A module that the drawer search or a rule row selects is written only after the same confirmation, which asks for nothing when neither the module nor a course moves, and a module that sits directly in **Unplaced studies** moves into a programme or a module without a module sentence of its own.

Adding a module reads its report, and the row shows as busy until it arrives. An added module is nested inside the node that received it and carries the **added** mark, and a module cannot be added inside itself. A course that sits directly in **Unplaced studies** always carries the solid outline, because that list is not part of any official structure.

A holder that the tree does not render before the addition takes its own scope's official defaults, so a choice or a place stored inside that scope does not survive into the added holder.

The addition resolves the holder identity at its new place, so the holder's own record, a removal record included, does not suppress it. A place outside the added holder and a removal record stay as they are, because the clearing touches only records whose target is inside the holder.

Placing such a course or module in the holder moves it there, and a module brings its current content with it under the same **Move here?** confirmation.

A holder the tree already renders moves with its whole current subtree, so its choices, the courses and modules it adds or removes, the customisation inside those and every completion travel to the new place, nothing of it resets and its old place disappears.

A module that the ordered programme list holds leaves that list as it is placed, so its entry renders at the destination node alone.

The same rule covers a promotion out of a nested position into a top-level slot, so replacing a programme with a programme that it displays keeps the replacement and its whole subtree while the replaced programme's other content follows the replacement outcome.

A holder the tree does not render pulls its official courses out of the nodes that render them and lists them in the addition confirmation with the holders of the tree the operation starts from, and **Keep** leaves each of those courses in the containing programme or module that shows it now. A move and a promotion pull no course, so an official course another programme or module renders at the time of the move stays there, and no official course of the moved holder is filled in or restored.

## Modules, courses and choices

Each module of a programme is a row that opens expanded and carries a control to collapse it, and the programme itself is a row of the same kind. A row shows the name, the code and kind, the selected credits and the completed credits.

Programme nouns follow the official degree type, so a degree programme nested inside another programme or module reads as a programme there as well. A choice whose options are all degree programmes reads **Programmes to choose from:** followed by the option count, a choice of other modules reads **Modules to choose from:**, a choice of direct courses reads **Courses to choose from:**, and every other entry kind reads **Options to choose from:**. Interaction kind follows position alone, so a row that is not a direct entry of the forest has the controls and the actions of a module.

Opening the row body shows the drawer of that module, which leads with the official rule of the module and the same credit totals, and a course that was added carries the **added** mark. Opening a drawer resizes the tree beside it, and the row text and its chevron hold their proportions through that change. The drawer's own slide follows the operating system's reduced-motion preference and takes its open position at once with reduced motion.

On the phone shell the drawer is a sheet from 8 px below the measured header to the top of the bottom bar, full width with a 16 px top radius, one vertical scroll for all its content, and its results open inside the sheet. The drawer's **Close** is the compact text pill at every width, on desktop and on a phone. The drawer search closes on Escape first. Otherwise an overlaid programme picker takes one Escape alone, and a subsequent Escape closes the drawer and returns focus to the row that opened it. On the phone shell a press outside the sheet closes it and returns focus to the row that opened it, while a press inside the drawer, on its search, or in a dialog, menu or picker it opened leaves the drawer open. At wider widths the drawer is a side panel, and a press on the tree reaches it while the panel is open.

Official content that the rule requires from everyone is shown directly as course cards, with the official code, name, credits and activity state of each course. On a desktop viewport every card has the same width and height. A two-line name occupies a fixed title area above the facts and the completion control, and a one-line name spreads the spare card height equally between the code, the name, the facts and the completion control, so those gaps match and a long name does not change the card size.

At widths up to 600 pixels a card has a minimum height of 110 pixels, and from 601 to 680 pixels it has a minimum height of 116 pixels. A one-line name spreads the spare height equally between the code, the name, the facts and the completion row, so the gaps between them match, the **Complete** control keeps the same bottom padding as it has under a two-line name, and the card padding stays constant. A longer name grows the card.

A tree row name and a drawer row name wrap at any character, and the code, kind, credit counters and row actions sit inside the row. A rule that offers a choice between alternatives is shown as a choice, and its drawer names how many options it offers and marks the options that are chosen. A rule that only wraps other rules is shown as the content it wraps, so a wrapper never adds a step. A reference the official data cannot resolve is shown as a note with its reason.

Each course card carries a control that marks the course completed and unmarks it. The completion belongs to the shared course sets, so a course marked here reads as completed in every other tab. The drawer's **Complete** control on a rule row places an unselected course in that rule and completes it, without the **Mark completed?** question that the shared course menu and the graph ask.

The drawer of a module also adds content. Its search box narrows courses, modules and programmes by name or by code over the same cached catalogue, and one result is added to that module. The drawer search holds every match in each section and mounts only the visible rows, a few rows beyond the window and any row the keyboard reaches, with the first and last match of each section always mounted. Tab moves between the logical rows, including rows outside the window, Home and End reach the first and last row, and Enter or Space activates the focused result. With **All** selected, Tab leaves the last course row for the first module row, and Shift+Tab leaves the first module row for the last course row.

A course pick resolves the full official summary of that one identity before the addition, and a failure reaches the ordinary error notice. A module or programme result shows its official code and name alone and stands for one canonical group. The group matching rule is stated in [Search](/docs/backend/search-and-discovery/search.md#the-minimal-official-catalogue).

One eligible version is added straight away. Several versions replace both result sections with one **Cancel** control before the shared version picker for that group inside the open results, and an outside press or Escape closes the open search. The picker's own list scrolls in a bounded window of 300 pixels at every width. **Cancel** restores the results, the query and the category with focus in the search field, and in the picker the exact version reaches the structure only after an explicit pick.

## Selection, places and moving

Every course on a structure card belongs to the profile's selection. A card in a module row or under Unplaced studies is content of the displayed structure or a course that was added, and the tab keeps the selection in step with the cards it draws. Selecting a course adds it to the selection, and marking one completed selects it as well.

The drawer is where a choice is made, and what it lists is not the selection. Its rule rows list the alternatives that a rule offers, and its search lists the narrowing results for a module, a course or a programme. An option joins the selection when it is chosen.

A course or a module that already has a place is moved rather than duplicated. Selecting such a course into another module opens **Move here?**, which names the course and the containing programme or module that holds it.

A module that already has a place moves through the addition confirmation: **Move here?** names the module and the containing programme or module that holds it, and names **the programme list** when the ordered programme list holds the module. A module the tree does not render adopts its official contents, and the courses it pulls out of another holder are listed in that dialog.

A module moves with its whole current subtree, so the choices, the additions, the removals and the completions inside it travel with it and its old place disappears, and a programme that an addition or a replacement promotes to a top-level slot moves the same way.

**Move** places a module that pulls no course there, and a module that pulls courses offers **Keep** and **Pull**, which place it there with the listed courses kept where they are or pulled in. **Cancel** leaves the structure as it is. A brief notice reports the module that was added and, when **Pull** moved courses with it, how many courses moved with it.

A course or a module that sits directly in **Unplaced studies** moves into a programme or a module at once without a confirmation of its own, because that list holds unplaced items by definition, while a course pulled out of a programme or a module is listed for confirmation, and a move from any programme or module node asks.

A choice between alternatives is toggled in the drawer. A choice that admits one option holds a single option, and a choice that admits several holds every option that is selected. The removal of an official course or module from a node is remembered, so the node does not show it again.

## Unplaced studies

[Unplaced studies](/docs/reference/glossary.md#discovery-and-the-structure-of-studies) is the part of the tab that holds the profile's courses with no programme. A selected course that no displayed structure holds is listed there, and choosing one in that drawer takes it out of the selection. The drawer keeps its added-course section while the row is open, so a course that leaves the list animates out of it and the empty list collapses instead of vanishing.

The course menu item **Add to Unplaced studies** adds a course to it at once, whether or not the programme list holds a programme. The two add-all actions, **Add all missing courses to structure** and **Add all module courses to structure**, add their courses the same way. Each of the three actions shows one bottom notice with the number of courses the write added, or that every requested course is already selected, and the notice carries a **Structure of studies** link that opens this tab.

## Deselecting a course or a module

Deselecting a course takes away its place. A course that is not completed leaves the selection with it.

A completed course is always selected, so a deselection of one opens **Completed course**, which offers two outcomes. **Move** places it under Unplaced studies and preserves its completion. **Remove** takes it out of the selection together with its completion, so the course leaves both course sets and every tab reads that at once. A course that already sits under **Unplaced studies**, a selected course shown loose there included, offers **Cancel** and **Remove** alone with the description that states the removal of the selection together with its completion, because keeping a course loose in that list changes nothing. **Cancel**, or Escape, leaves the selection as it is.

Deselecting a module takes the courses it holds out of the displayed structure. A completed course among them holds its completion and its place in the selection, and appears under Unplaced studies, while an uncompleted course among them leaves the selection.

A module whose current contents differ from the contents its own place draws for it with its own official defaults, or that holds completed courses, asks first, with **Delete** for that outcome and **Delete all**, which drops those courses from the selection and the completion with the module, and **Delete all** appears only when the module holds a completed course.

The question always carries one short description that names the part: without a completed course it states that the part leaves the structure, and with a completed course it adds the choice between keeping the completed courses under Unplaced studies and removing them with their completions.

A module whose contents are the ones its own placement gives it, a course that placement pulled out of another holder included, deselects with no question, and a stored record that leaves those contents unchanged, such as an empty choice list, a chosen option that renders the same contents, or a place at an official home, is not a difference. A nested degree programme uses this same path, and only a top-level programme's **⋯** menu always asks.

## Resetting a part

The drawer of a module ends with **Reset this module**, and the drawer of a top-level programme ends with **Reset programme**, which is the same operation as the row menu's **Reset programme**, the same shared question and the same outcome for the named programme. A nested degree programme reads **Reset programme** and holds the same module interactions, so it opens that shared question with the module operation.

The shared reset question is one compact panel with **Cancel** at the left and **Reset** beside it, and **Reset all** joins them at the right only when the affected scope holds a completed course. Its one short description names the part in every state, **This restores this programme's official content.** for a programme and **This restores this module's official content.** for a module, and a scope that holds a completed course adds **Keep completed courses, or clear their completions too.**, with the FI resource carrying the Finnish counterpart of each sentence.

**Reset programme** asks from the row menu and from the drawer, and **Reset this module** asks from the drawer, at every press, whatever the scope's contents and completions are: no press reaches a reset without the question. A reset whose scope returns courses to it from other nodes asks a second question after that answer, with **Cancel** at the left and **Keep** and **Pull** at the right: it lists every returned course with the containing programme or module that shows it now, **Pull** applies the reset and returns those courses to the scope, **Keep** applies it with each of them left in the containing programme or module that shows it now, and **Cancel** cancels the whole reset and writes nothing. A scope that holds no completed course and returns a course asks through that second question alone.

**Reset** restores the official choices and the official places inside that scope and preserves every completed course. **Reset all** applies that same restoration and clears the completions that the scope holds before the write, so a course the scope held before the reset comes back selected and uncompleted, a course returned from another place by **Pull** keeps its completion, and a completed course the reset discards leaves the selection with its completion, and a scope that holds a completion and no change at all clears that completion through it.

A completion that another holder owns is not cleared, and no reset writes to another programme or to a loose course. The drawer of **Unplaced studies** ends with the reset of that list, which clears the places there, returns a course to its official place when a structure holds one for it, and takes an uncompleted course that was placed there out of the selection. A completed course that a reset leaves without a place is listed under **Unplaced studies**.

A reset reports **Programme reset to its official contents** or **Module reset to its official contents** for the word its target carries, and the reset of **Unplaced studies** reports **Unplaced studies reset**.

## Stored state, waiting and failure

The ordered programmes, the choices and the places belong to the profile, so they are there each time the tab is opened, and the server answers a structure read from the official data alone. Reading an official report, adding a module, and loading the content of a placed course each show a waiting state, and only the first load shows a skeleton tree.

A profile created from a Sisu capture holds one pending hierarchy, and the tab places it on its first read of the official programmes and of every module the capture holds, because a module the official rule does not name needs its own report to render.

While that record is pending the tab runs no ordinary reconciliation and the structure content shows its loading state, with the required version pickers reachable above that state. The placement waits while the server settles a root group of the capture as needing a version selection, so no editing surface reaches the pre-placement choice maps. The capture's nested references demand no version before placement, and the resolved projection contributes their requirements once the capture is placed.

The placement is one store write: it writes the choices, the places, the placed identities and the end of the pending record together, and a completion or language change another tab made while the reads waited is preserved. A failure of the placement shows its notice, applies nothing and leaves the pending record in place. When the placement finishes, the ordinary reconciliation and the editing controls resume.

A profile restored from a profile file or a saved-data file can hold saved choices, places or placed identities together with a waiting capture, because all three are profile data. An entry counts even when its choice list is empty or its place is `null`, and a non-empty placed identity list counts on its own. The tab then places nothing and performs no structure write, and one notice above the structure reads **Sisu import paused to preserve saved edits. Your profile is unchanged.**.

The profile keeps every saved choice and place, and the waiting capture, as the file supplied them, and no version picker, skeleton or tree is drawn. The Add row and the drawer are unavailable while the notice stands. The hold belongs to resolution rather than to the view, so a read, a language change or another tab's completion causes no placement write, and the profile holds the saved choices, places and waiting capture the file supplied. The required version pickers are not drawn, so no version selection reaches the held profile.

An explicit file import installs the validated file through its ordinary owner. Derived read caches are not profile data.

The issues of a placement, which are the captured items the tab could not place, appear in one notice above the tree. Each names the item and gives its reason, and the notice is visible until it is dismissed.

A failed read or a failed add shows a notice with the failure. The pane checks whether every programme report and every string placement's report or summary exists before it builds a forest, then projects one display input per render. While placed content loads, it keeps the last complete input of the same serving identity and re-projects it in the current language, and a failure of that read shows the notice in place of the tree.

The same waiting state holds while the report of a module another tab placed, or the summary of a course another tab placed, arrives. An add that finishes after the programme list changed is refused without a write, and its picker stays open for another pick.

The ordinary reconciliation reuses the current display projection and writes only while the stored structure still matches the rendered snapshot and no Sisu capture is pending, so a later edit or completion is not answered from an older render. A confirmation whose module or course moves changed while it waited fails with a notice and writes nothing. A module move whose destination cannot be resolved fails with a notice that names the failure, and a missing programme report fails with **Programme is unavailable** rather than drawing an incomplete list.

The rule projection, the resolution of the choices and the places, the placement of a pending Sisu capture, and the tests that cover them are described in [Structure model](/docs/frontend/structure-model.md).
