# Using the app on a phone

The app fits its tabs into a phone screen with a bottom bar, sheets for the shared controls and tab options, and a few gestures.

## The bottom bar

On a phone the app has no top bar and no footer. A bar at the bottom of the window holds one button for each tab the site serves and **More**, and the tab content fills the space above it. The buttons read **Search**, **Compare**, **Prereqs**, **Discover**, **Structure** and **More**. The full tab name is the accessible name of each button, so **Prereqs** reads as **Prerequisites** and **Structure** as **Structure of studies** to a screen reader. The open tab carries a line across the top of its button.

A site that serves no comparison shows no **Compare** button, and its tab ring holds the other four tabs.

While the open tab scrolls down, the bar leaves the window and the content takes its space. It returns at the top of the scroll area, when you scroll up, and after a menu, sheet, picker, drawer, help panel or confirmation dialog closes. A submitted search and a change of the Discover list bring it back as well.

## More, profiles and language

**More** opens a sheet above the bar. Its head row shows **More** at the left and **Close** at the right, then the profile control, then a row with the language control and **Docs**, and it ends with the notice that the project is independent and the link to its source code. The sheet scrolls inside itself when its content is taller than the space above the bar.

Selecting the profile name opens **Profiles** in the same sheet. The language and **Docs** row and the notice hide, and the panel grows upward with the profile list, the **New profile** form, the import area, **Copy Sisu import script** and **Export**. [Profiles and language](/docs/guides/profiles-and-language.md) covers these controls. **Close** or a tap outside the sheet returns to the app and puts the focus back on **More**.

![The More sheet on a phone, with More at the left of its head row and Close at the right, above the My plan profile row, a row holding FI, EN and Docs, and the independent-project notice above the source code link](/docs/screenshots/phone-more.png)

**Docs** opens the documentation wiki inside the app. On a phone the wiki header keeps the brand, **Docs** and **Back to the app**. A search field and a menu button sit above the breadcrumbs. The menu slides in from the right with the page list, another search field and **GitHub**, and **Back to the app** returns to the tab you left.

## Moving between tabs

Swipe left or right in the tab content to move to the next or previous tab. A swipe that starts on a course card, a Discover result row or a course tile in the structure follows its direction. A swipe that starts on another control, on the graph, or on an open drawer or menu leaves the open tab alone, and a vertical swipe scrolls the pane. The tabs form a ring, so the last tab leads back to the first, and a move takes the shorter way round.

An arrow key also moves between tabs, but it is ignored while the focus sits in a text field and while a menu or a dialog is open.

## Search

Before a search the field sits in the middle of the tab, with **Active only** and the **?** button below it. Press Enter or select the magnifier to run the search.

After a search the field sits in a header at the top of the tab, with **Active only**, the **?** button and the number of matches in a row below it. The results scroll under that header, and the field stays in place. The whole result row opens the course sheet above the bottom bar, with the shared actions of every tab. [Searching for courses](/docs/guides/search.md) explains the match methods and the result marks.

![The Search tab on a phone after a submitted query, with the query field and the Active only, help and match count row above a scrolling list of course results](/docs/screenshots/phone-search.png)

## Compare

On a phone the two slots stack one above the other. A filled slot shows its letter with **Replace** and **Remove** in a head row above the course, and the name wraps in full. The five meters put each label and its value on one line with the bar below.

The course picker opens above the bottom bar with a small margin on each side, scrolls inside that box, and carries **Close**, its filter field, **Active only** and the **+ add** rows. [Comparing two courses](/docs/guides/compare.md) explains the slots, the meters and the verdict.

![The Compare tab on a phone with two courses in stacked slots A and B, each head row holding Replace and Remove, above the five comparison meters](/docs/screenshots/phone-compare.png)

## Prerequisites

With a course open, the drawing fills the space between the top of the tab and the bottom bar. A header at the top shows the course code and opens **Graph options**, and a rail at the right holds **Recenter**, **Zoom in** and **Zoom out**. Course names wrap to their full text and a box grows to fit them. Drag and pinch inside the drawing to move and zoom it without moving the page or changing the tab.

**Graph options** opens a sheet. Its first button shows the course code, the name on one line and a swap icon, and the button reopens the course picker. The controls follow: **Completed** and **Selected** for the route basis, **Recommended**, **Inferred** on a site that serves inference, **Active only**, and the **?** help. A change here applies to the drawing and to the route.

![The Graph options sheet on a phone, with the root course button above the route basis switch, Recommended, Inferred and Active only controls and the help button](/docs/screenshots/phone-graph-options.png)

**Find minimum route** is a wide button above the bottom of the drawing. Its result opens as a sheet over the bottom of the drawing. The sheet scrolls inside itself and keeps the lit path visible above it. Its header gives the new credits and the full-route credits when there is a total, the outcome tag, **Expand** and a clear control that returns to the plain drawing. **Expand** grows the sheet over the drawing so the course list scrolls inside it, with **Add all missing courses to structure** fixed at the foot of the sheet.

![The Prerequisites tab on a phone after a minimum route, with the route sheet showing the new and full credits, the exact tag, Expand and Clear, over the lit drawing](/docs/screenshots/phone-minimum-route.png)

On a site that serves no inference features the sheet shows no **Inferred** control. [Exploring prerequisites](/docs/guides/prerequisites.md) explains the toggles, the marks and every route outcome.

## Discover

**Next courses** and **Recommended** sit as buttons in a header at the top of the tab that stays in place while the list scrolls, with a settings icon at the right. The icon opens **Discover options** with the basis, **Active only** and the **?** help. While **Next courses** is the open list the sheet also carries the **All** and **Partially covered** prerequisite mode, and **Recommended** leaves that mode out. A site that serves no embedding features shows **Next courses** alone.

Below the header the basis line counts your courses and names up to four of them, and the chip that counts the rest opens the full list with its credits. Each result row stacks the course card and its meters in one column inside the row's border. The **inferred** mark sits beside the course code. The whole row opens the course sheet. [Discovering courses](/docs/guides/discover.md) explains the lists, the coverage meters and the ranking.

![The Discover options sheet on a phone, with All and Partially covered, the Completed and Selected basis, Active only and the help button above the tab bar, over the Next courses list](/docs/screenshots/phone-discover-options.png)

## Structure of studies

Only a row at the top level of the list carries the **⋯** menu, which sits on the title row at the right, level with the expand control, and a module nested inside a row carries no **⋯** menu. A course card grows when its name wraps, and its **Complete** control stays at the foot. The card opens the course sheet, and **Complete** marks the course completed directly, without the **Mark completed?** dialog.

Selecting a module row opens its drawer as a sheet above the bottom bar. The sheet has **Close** at its head and one scroll for the rule, the content, the search and **Reset this module**. Search results open inside the sheet. A module with several eligible versions replaces the results with a version list that scrolls in its own area, and you place the module only when you choose a version. Escape closes the search first while it is open. With the search closed and no dialog or picker open, Escape closes the drawer and returns the focus to the row that opened it.

The drawer of a module inside a programme shows the module name and code in its head row with **Close** at the right, above the rule and credit totals, the search field, the rule sections and **Reset this module**.

![The drawer sheet of a module inside a programme on a phone, with the module name and code beside Close, the credit rule and totals above the search field, an all required section and a choose 1 section with their course rows and Complete controls, and Reset this module at the foot](/docs/screenshots/phone-structure.png)

**Add programme** opens the picker over the tab. A match with one eligible version is added when you choose it. A match with several replaces the results with **Choose module version**, **Cancel** and a **Select** action on each version. [Planning a structure of studies](/docs/guides/structure-of-studies.md) explains the tree, the rules and the confirmations.

## Closing a sheet or a dialog

The **More** sheet and the option sheets have **Close** at the head. Escape and a tap outside close the sheets, pickers, menus and dialogs, and the focus returns to the control that opened the surface. The structure drawer is a sheet above the bottom bar too, so a tap outside closes it, and a tap inside it, on its search, or in a dialog, menu or picker opened from it leaves it open. The bottom bar returns when the surface closes. A route sheet clears with its clear control, and leaving the tab or changing an option clears the route.

## Where to read more

- [Searching for courses](/docs/guides/search.md) for the four match methods, the result marks, and the activity option.
- [Comparing two courses](/docs/guides/compare.md) for the two slots, the five meters, and the verdict.
- [Exploring prerequisites](/docs/guides/prerequisites.md) for the prerequisite graph, its toggles, and the minimum route.
- [Discovering courses](/docs/guides/discover.md) for next courses, recommended courses, and the basis.
- [Planning a structure of studies](/docs/guides/structure-of-studies.md) for the official structure, its modules, and your own placements.
- [Profiles and language](/docs/guides/profiles-and-language.md) for named profiles and the interface language.
- [Sisu import script](/docs/guides/sisu-import.md) for capturing a plan in Sisu and importing it as a profile.
