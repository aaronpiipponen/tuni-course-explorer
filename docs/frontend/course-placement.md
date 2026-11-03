# Course placement and dragging

The structure of studies places each course card in a holder, and a drag or a click moves a course or a module and saves the card order.

The placement records and the selection migration are described in [Structure edits](/docs/frontend/structure-edits.md), the projection and the resolution of the tree in [Structure model](/docs/frontend/structure-model.md), and the measurements, travel tolerances and target selection behind a drag in [Structure pane](/docs/frontend/structure-pane.md).

## Dragging a course card

A drag starts on a course card alone. A programme row, a module row, a rule row and a lookup result take no drag. On a desktop a drag starts while the module drawer or the help drawer is open as well.

A desktop press arms the card after a 50-millisecond stationary hold, and a touch contact arms it after a 250-millisecond hold. An armed card shows a pickup ring inside its edge, and travel over 8 px before the hold ends the press without a drag. The card lifts on the first 4 px of movement after the hold, shifted up and enlarged by 1 percent around its centre, and the pickup highlight carries into the lifted copy. A release without movement is a click, so the card opens its menu. The lifted card follows the pointer or the finger, a dashed outline marks the slot it would take, and the other cards move aside around that slot.

Holding the card near the top or the bottom of the tab scrolls the tab while the drag continues. On a touch screen a quick tap, a scroll and a tab swipe keep their ordinary behaviour until the card lifts, and after the lift the drag owns the contact.

A drop on another displayed programme, module or **Unplaced studies** writes one structure change, and a drop inside the card's own grid changes only the card order. A drag applies the move without a question, whether the course is completed or the destination is another programme. A completed course keeps its completion and its place in the selection wherever it lands.

Escape, a lost contact and a window blur cancel the drag without writing. Reduced motion keeps the lifted card and the outline, applies the slot shifts at once and places the released card in its final slot immediately.

## Card order

The saved order holds canonical course identities and applies across every visible holder, so a course that has no ranked identity follows the ranked ones in its displayed order. A drop into another holder saves the sequence its cards show as their rank and leaves the order every other holder shows as it is. A reload, a profile switch and a profile or saved-data export and import keep the order. [Structure model](/docs/frontend/structure-model.md#resolution-precedence-and-single-render) states how a saved rank and an unranked card become the displayed order.

A reset clears the card ranks of the courses the named scope holds or restores. [Resetting a part](/docs/frontend/structure-editor.md#resetting-a-part) states the reset, its question, its outcomes and the ranks it clears.

## Selection and places

Every course on a structure card belongs to the profile's selection. A card in a module row or under **Unplaced studies** is content of the displayed structure or a course that was added, and the tab keeps the selection in step with the cards it draws. Selecting a course adds it to the selection, and marking one completed selects it as well.

The drawer is where a choice is made, and what it lists is not the selection. Its rule rows list the alternatives that a rule offers, and its search lists the narrowing results for a module, a course or a programme. An option joins the selection when it is chosen.

A course or a module that already has a place is moved rather than duplicated.

## Moving a course

Clicking a course that has a place into another module opens **Move here?**, which names the course and the containing programme or module that holds it. A course or a module that sits directly in **Unplaced studies** moves into a programme or a module at once without a confirmation of its own, because that list holds unplaced items by definition. A course or a module pulled out of a programme or a module is listed for confirmation, and a click move from any programme or module node asks.

## Moving a module

A module that already has a place moves through the addition confirmation: **Move here?** names the module and the containing programme or module that holds it, and names **the programme list** when the ordered programme list holds the module. A module the tree does not render adopts its official contents, and the courses and modules it pulls out of another holder are listed in that dialog.

A module moves with its whole current subtree, so the choices, the additions, the removals and the completions inside it travel with it and its old place disappears. A programme that an addition or a replacement promotes to a top-level slot moves the same way.

A module that the tree already renders offers the reset actions its own state allows beside **Move**: no reset for a module that already matches its official contents and holds no completed course, **Reset** when it holds a structural edit, **Reset all** when it holds completed courses, and both when it holds a structural edit and a completed course.

**Move** places a module that pulls nothing. A module that pulls courses or modules offers **Keep** and **Pull**, which place it there with the listed items kept where they are or pulled in. **Cancel** leaves the structure as it is. A brief notice reports the module that was added and, when **Pull** moved courses with it, how many courses moved with it.

## A returned course or module

A course or module returned to a displayed holder through a drag, a drawer rule row or a search result stores the exact official containing node when that holder officially names it, so the returned part shows its official presentation instead of the added mark. The return keeps the canonical identity, the exact selected module versions, the current subtree, the shared selection and the completion.

## Choices and remembered removals

A choice between alternatives is toggled in the drawer. A click adds the option when it is not chosen and removes it when it is, and the rule never drops another chosen option, so a choice that admits one option can hold several chosen options. The rule label states the official structure and is not enforced on a click. The removal of an official course or module from a node is remembered, so the node does not show it again.
