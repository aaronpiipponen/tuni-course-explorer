# Browser app

The browser app is a tab shell over one current profile, and every tab reads and writes the same browser-held course state.

## The shell and its tabs

The app fills the window as a grid of three rows: the shell header, the tab area, and the bottom of the shell. On a desktop viewport the header is a top bar that holds a button for each tab the site serves, the profile control, the language control and **Docs**, and the footer under the tab area holds the independent-project notice and a link to the source code repository at the address that `repositoryUrl` in `config/wiki.json` sets.

From 761 to 960 px the top bar holds the app name, **Docs**, the profile control and the language control on its first row and the tab buttons on a second row at least 56 px tall. At 961 px and wider the top bar is one 60 px row. A rule along the bottom of the top bar separates the header from the tab area.

On a phone the header is an empty safe-area strip, the bottom bar holds a button for each served tab and **More**, and **More** opens a sheet above the bar with the profile control, a row carrying the language control and a **Docs** button, and the same notice and source link. On desktop the **Docs** button is a transparent pill with a thin outline, and in the phone **More** sheet it is a filled accent pill. Each phone bar button carries a short label on one line and the full tab name as its accessible name.

Opening **My plan** in **More** hides the language/Docs row and the footer and grows the profile panel upward to its content height above the bottom bar.

The tabs are **Search**, **Compare**, **Prerequisites**, **Discover** and **Structure of studies**, and a site that serves no embedding features has no Compare tab. The app is available in Finnish and English, and the documentation wiki behind **Docs** is in English.

A [profile](/docs/reference/glossary.md#browser-app) is one named set of the app state. A browser with no saved state starts with one profile named My plan and the English language, and a fresh browser tab opens on the **Search** tab. The profile control shows the name of the current profile, and it opens the profile list with the selected and completed counts of each profile, a **New profile** form, a rename control, and a delete control.

On a phone the profile control is the first row of the **More** sheet, and its panel opens inside that sheet. On the phone shell the profile panel takes the first Escape, and a subsequent Escape closes **More** with focus back on **More**.

At 680 px and below the profile panel uses the compact scale: 26 px profile icons and help controls, a 32 px **New profile** field, 24 px **Save** and transfer controls, and 32 px export rows. From 681 to 760 px the phone shell keeps its wider content, the profile trigger is at least 44 px tall and the profile select is 48 px. A profile name wraps in full, and the panel has no scroll of its own because the **More** sheet is the one surface that scrolls.

**Search**, **Prerequisites** and **Discover** each carry a **?** button that opens the screen's help drawer. The drawer header stays in place and its body scrolls under it.

The drawer ends with one link to the guide of that screen, in the profile language and in the same browser tab: **Searching for courses** opens `/docs#guide-search`, **Exploring prerequisites** opens `/docs#guide-prerequisites`, and **Discovering courses** opens `/docs#guide-discover`.

On a phone a **?** drawer nested in an options sheet takes the first Escape, and a second Escape closes the sheet and returns focus to its trigger.

## The site's features

The app reads the site's two feature switches before it mounts the shell. The bootstrap asks the server for them once with the shell's own request, shows **Loading site features** while the answer is pending, and shows the ordinary failure notice if the request fails.

The answer also carries the identity of the dataset the server resolved, and the app mounts one bounded read cache for that identity above the tab panes. The answer lives for the visit and is not polled or retried, and a profile switch or an ordinary navigation does not ask for it again.

A site with embedding features serves comparison and recommendations, and a site with inference features serves inferred prerequisites and the controls and marks that describe them. Without the answer the app does not mount, because a switch it cannot read would leave a control serving a feature the server refuses.

A tab the site does not serve is absent from the shell's tab controls, the tab ring and its arrow keys. A stored open tab of a hidden **Compare** renders **Search** instead, and the stored value in the browser tab's session storage is left as it is until a deliberate navigation replaces it. The controls of a hidden feature are absent in the same way: the comparison entry of a course menu, the comparison slot mark on a card, the semantic help item of **Search**, the **Recommended** list of **Discover**, and the **Inferred** toggle and its help item of **Prerequisites**.

The dataset identity changes when the serving process restarts or when the site's selected dataset switches. Every cached read reports it, and a response carrying another identity clears the values the cache held for the previous one.

The cache holds successful reads, and successful structure reports also persist in a derived structure store scoped to the serving dataset identity, the report's root and the module-version selection that produced it. A reload therefore renders only the structures that belong to the current dataset and selections, before any structure request.

A selected-dataset switch is discovered on the next uncached read, while an in-place change to served data requires a restart and then an uncached read or a reload. A tab with no uncached read keeps the values it already holds until then, and nothing polls the identity or asks the server whether the data is fresh.

Hiding a control does not change any saved value. The two comparison slots, the saved **Discover** list, the saved **Inferred** toggle and the course sets are the profile's own values, and the profile holds them whether or not the site serves their controls. The open tab is not one of them: it belongs to the browser tab's own session storage, so a reload of that tab restores it and another tab keeps its own. No feature switch is part of the profile schema or of the saved envelope.

## Navigation and scrolling

A tab opens from its button in the desktop top bar or the phone bottom bar, from the arrow at either side of the tab area on desktop, or with the left and right arrow keys. The tabs the site serves form a ring, so the last tab leads back to the first, and a move travels the shorter way round the ring. An arrow key is ignored while the focus is in a text field, a text area, a select control or an editable element, and while a menu or a dialog is open.

At a phone width the arrows are absent, the shell has no top bar and no footer, and the served tabs sit in one bottom bar together with **More**: five tab items plus **More** on a site that serves every feature, and four plus **More** on a site without the embedding features. Each item is at least 44 px wide and 56 px tall, and the active tab alone carries the current mark. **More** opens the sheet of shared controls and closes on **Close**, on Escape or on a tap outside it, and it also closes when the shell leaves the phone width and returns closed when the width returns.

Neither resize dismissal moves focus to a hidden trigger.

While the open tab content scrolls down, the bottom bar hides and the tab area expands into its space. It returns on an upward scroll, at the top, or after a dismissal or choice that closes a course menu, sheet, picker, drawer, help panel or confirmation dialog, submits a search, or switches the Discover list. Scrolling inside a sheet, drawer, picker or menu leaves the bar alone, so that surface does not resize under the finger. This applies to the phone shell alone.

A horizontal swipe in the open tab selects the next tab when it moves left and the previous tab when it moves right, and the ring wraps in both directions. A swipe counts only after it travels 8 px with horizontal dominance, it selects one tab when it travels at least 48 px, and it works only with touch input. A vertical gesture scrolls the pane.

A gesture that starts on a course card, a structure course tile or a Discover result row follows its direction, so a horizontal one selects a tab and a vertical one scrolls. A gesture that starts on any other button, a link, a field, the prerequisite graph, the route and member stack, a drawer, a picker, a profile menu or an open dialog leaves the open tab unchanged, as does a gesture while a drawer, a picker, a menu or a dialog is open.

Only the open tab scrolls. The shell is one window-high grid, so the desktop top bar and the footer hold their places and the pane alone carries the scrollbar. On a phone the shell has no top bar and no footer, the pane begins at the top of the window below the safe-area strip, and the bottom bar holds its place under it until a downward scroll hides it. The viewport declaration asks for the on-screen keyboard to overlay the content, so a focused field does not resize the shell or move the bottom bar.

The pane that leaves during a transition takes no input and is hidden from assistive technology while it moves. The shell header reports its own height to the document root, and the help drawer and the structure drawer begin below that measured edge, so on a phone they clear the display cutout. The open profile panel paints above the arrows at either side of the tab area on desktop, so its help and export controls accept ordinary pointer input at every width, including 360 px. The left and right arrow keys wrap between the tabs, and at a desktop width the arrow buttons at either side of the tab area are shown.

The document matches the shell's height at every width, so the window carries no page scroll beside the shell. Opening the app, including the return from the documentation, places the window at the top.

Everything that moves follows the operating system's reduced-motion preference. With reduced motion a tab change, a drawer or a panel, a phone sheet or menu, the More utility row, the phone bottom bar, a profile notice, a two-option switch, a result arrival or re-sort, a meter, a graph layout, a route lighting, a skeleton and a wiki sidebar, page or anchor scroll draw their end state at once.

The static styles of each state show what it means: the selected switch option, the lit route edges, a loading label, and the content of an open panel.

## Profiles and shared course state

Everything a profile holds switches together: the language, the selection, the completion, and the settings of each tab. Switching the profile rebuilds the tab area, so every tab starts from the state of the profile that is current.

The open tab is not part of a profile. It belongs to the browser tab and lives in that tab's session storage, so a reload keeps it, another open browser tab keeps its own, and a fresh browser tab starts on **Search**. Switching, importing or restoring a profile leaves the open tab where it is, and opening a course's prerequisite graph from a card moves only the browser tab that asked for it.

The selection and the completion are shared by every tab. Selecting a course in one tab selects it in every other, and the same course menu opens on every course card. On a phone, a tap on a course card centers the card between the visible header and the action menu, adding temporary space below the list when the list cannot otherwise scroll that far.

The menu's title entry shows the course code in purple, the credits and the active or inactive status on its first row, with the status at the right in the ordinary card style and only the code in purple, then the full course name below, then a grey separator line, then **Add to comparison** on a site that serves embedding features, **Open prerequisite graph**, **Add to Unplaced studies**, **Mark completed**, and **Open in Sisu**. The name wraps to as many lines as it needs.

**Mark completed** completes a selected course in place. It asks once before adding a course that is not selected to **Unplaced studies** and completing it. Unmarking the completion leaves the course selected. In the structure drawer, the **Complete** control on a rule row's course places an unselected course in that rule and completes it, without that question.

**Add to Unplaced studies**, the route panel's add-all action and a member list's add-all action show one bottom notice with the number of courses the write added, or that every requested course is already selected, and the notice carries a **Structure of studies** link. **Open in Sisu** opens the official page of the course in another browser tab. A course that holds a comparison slot carries its slot letter on its card, and a site that serves no embedding features omits that letter from the card and from its accessible name.

A canceled touch scroll leaves Enter and Space available on the card that holds focus, and the scroll itself opens no menu.

## Language and labeled analysis

The app language belongs to the profile. The language control switches between FI and EN, and the change reaches every app-authored word and the official course names, which are shown in the chosen language when the catalogue holds one for it. Changing the language leaves the study state alone.

Data is labeled apart from the official data. Inferred prerequisites take part in the prerequisite graph only while **Inferred** is on, and only on a site that serves inference features. The Discover request carries `include_inferred` as the site's inference switch, so inferred prerequisites take part in its next-course and recommendation reads whenever the site serves inference features, with no toggle. A comparison states that it is course information analysis rather than official equivalence, and it notes when derived text took part. A recommended course notes derived text in the same way.

The prerequisite graph states the origin of every relationship it carries, which is official, inferred, or composed, and a course card carries the **inferred** mark only when no official relationship reaches that course, so a course that the official data also names reads as official. A next course that the basis reaches only through inferred prerequisites carries the **inferred** mark. [Prerequisite graph](/docs/backend/prerequisites/prerequisite-graph.md) describes those origins and the drawing they drive.

## Saved state and transient reports

The [browser state](/docs/reference/glossary.md#browser-app) is the saved state of every profile in the browser's local storage. A profile saves its language, its selection and completion, and the settings of each tab. Those settings are the search text and its activity scope, the two comparison slots and the comparison picker fields, the prerequisite root with its toggles and exclusions, the discovery list with its basis and scope, and the ordered programmes with their choices and places. The open tab lives in the browser tab's session storage instead.

What a profile saves and what a report holds are separate. The structure reports are the one server report written to browser storage, and a stored report answers only its own serving dataset identity, root and module-version selection.

Every other tab report lives only while its pane is on screen, with the successful values the app-level memory cache holds for their request keys. That memory cache is never part of a profile, and a structure store holds no user state, mark, completion or selection.

The submitted search is held apart from its pane: the submitted text and its report sit in a session that spans the tabs and lasts while the profile is open, so a move to another tab finds them there.

A change from a user action is written to storage before it is published, so a write that fails publishes nothing and shows a notice that names the failure.

The stored envelope is read back at startup and validated before the app starts: a schema version other than 3, a missing current profile, or a malformed profile or tab setting fails the start with a notice in English while the saved value is left as it is.

Each feature constructs requests from its relevant profile inputs and submitted values. The profiles belong to the browser that holds them.

Every tab of one browser shares the current profile. A save re-reads the saved state, applies its change to that value, and writes the result, and an open tab follows the browser's storage event. A course marked in one tab therefore appears in the other open tabs, a profile switch reaches them as well, and another tab's change is never overwritten by a stale copy of the state.

### Files and the failure screen

The profile control offers a compact **Import** control that takes one file through **Choose file** or by a drop, and a bottom row that carries the help drawer, **Copy Sisu import script** and **Export**.

The **Structure of studies** tab offers the same import area below **Add programme** while its programme list is empty. That area shows the **Import** heading, the **Choose file** and drop control, **Copy Sisu import script** and a **?** help drawer, without the export list.

The export list is open for several consecutive downloads, it sits below that row, and each row of it names one profile or **All saved data**. An exported profile does not become the current one. A profile downloads as `course-explorer-profile-<profile name>.json`, with each character that a file name cannot hold replaced by `_`, and the whole saved data downloads as `course-explorer-saved-data.json`.

Three kinds of file reach the import area, and the `type` field of the file decides what happens.

- A profile file asks for a confirmation that names the profile it holds, and **Import** creates a new current profile through the store, while a name that another profile holds is refused at that confirmation.
- A file of the whole saved state asks for a confirmation that states that it replaces every profile in this browser, and the page reloads after the replacement, so every open tab follows the replaced state.
- A Sisu capture asks for a confirmation with a **Profile name** field, names the captured programmes in order together with every item the capture left unresolved, and creates the profile with its captured hierarchy pending on the tab's first Structure of studies read.

A cancelled, dismissed or failed confirmation writes nothing, and a file of another kind, or a file whose content does not hold the current shape, is refused with a notice and changes nothing.

The help drawer of the bottom row explains the export, the import and the Sisu capture in three sections. In the empty **Structure of studies** import area the same drawer explains the import and the Sisu capture without the export section.

**Copy Sisu import script** copies the console script of [Sisu import script](/docs/guides/sisu-import.md) to the clipboard and reports **Sisu import script copied** in a green notice that closes after five seconds, or **Could not copy Sisu import script** when the copy fails. The copy leaves the profile menu open.

When the saved state cannot be read, the failure notice appears in place of the interface with **Export saved data** and **Reset saved data**, and that screen reads in English alone. The export downloads the stored text as it is, so a broken state can be repaired by hand. The reset asks for a confirmation titled **Reset saved data** that names the deletion of every profile, and it then starts again with one profile named My plan.

The diagram follows the feature read and the state that the other reads use. Before the shell mounts, the app asks the server for the site's feature switches and the serving dataset identity once and holds the answer for the visit.

A tab action is written into the browser tab's session storage before the open tab changes, and a course or settings action is written into the saved profiles before the current profile is published.

The current profile supplies the feature request inputs, a typed client sends them to the read-only web server as a read request, and the server report becomes the result that the open tab shows.

![The app asks the server for the site's feature switches and the serving dataset identity before the shell mounts, a tab action is written into the session storage that holds the open tab, and a course or settings action is written into the saved profiles. The current profile supplies the request inputs, the report returns as the result the open tab shows, and a successful report joins the memory cache while a structure report also joins the derived IndexedDB store under the serving identity, its root and its selection. Dashed boxes mark the transient reports, the memory cache and the structure store, which holds structure reports alone, and the accent arrow marks the read request.](/docs/diagrams/browser-state-flow.svg)

## Requests when a tab or a profile changes

A read belongs either to a tab pane or to the search session, and the two have different lifetimes.

A pane-owned read is cancelled when its inputs change or when the pane leaves the view, and a result that arrives after its request was cancelled is dropped. A pane therefore shows only a report that belongs to the inputs in force.

Each read has its own typed client, which posts its inputs as JSON to one same-origin route and returns the parsed report, and a response that is not successful becomes a failure the pane shows.

The prerequisite graph read is served from the app-level cache. One cache lives above the panes for as long as the feature bootstrap holds, so a graph that was read once is shown again when the pane reopens, when another tab is opened, and when the profile changes, as long as its structural inputs match.

Leaving the pane aborts a read that is still running and keeps every successful value. A cached value is shown without a request, and only a structural input the cache does not hold asks the server.

A successful prerequisite route calculation joins the same cache under a key that covers the dataset identity, the structural graph key, every live route input and the allocation limit. The minimum route runs in a browser worker over the solver structure of the held report, and [Graph layout](/docs/frontend/graph-layout.md) describes the modules that calculate it.

The route appears only on an explicit **Find minimum route** click: clearing it, changing an input, leaving the pane or remounting the pane clears the visible route, returning to earlier inputs does not restore it, and a further explicit click with the same inputs shows the held value without starting a worker.

The search session lives above the panes for as long as the app is open, and it holds the submitted text and its report rather than the text in the field. Only a submitted request is read, and a successful report joins the shared memory cache, so resubmitting the same request shows it without a new search request.

A move to another tab leaves the session in place, and a change to the app language or to the activity scope re-runs the submitted query even while another tab is shown. The session ends with the profile, so switching the profile drops the submitted search and its report.

Switching the profile rebuilds the tab area, so a pane-owned read of the previous profile is abandoned as well. An operation that finishes after a profile switch is checked against the profile that started it and writes nothing.

A failed read shows one notice in the profile language with a short summary, and the diagnostic text is shown as it arrived. A narrowing box reads the one cached minimal official catalogue and filters it locally, so it sends no request per keystroke and needs no debounce.

The Compare picker, the prerequisite course box, the programme picker and the drawer search hold every match in their list while only the visible rows, a few rows beyond the window and any row the keyboard or pointer reaches mount. The rows hold their official order, and the first and last match are always mounted so the list can be entered and left with Tab. The keyboard moves between the logical rows with Tab, Shift+Tab, the arrow keys, Home and End, including rows outside the window, and Enter or Space performs the focused row's action.

The shared course lookup that Compare and Prerequisites open suppresses a pick after a canceled touch scroll, so a scroll leaves Enter and Space available for the focused row and picks no course. The module and programme pickers and the drawer search carry no touch capture. The Search result list has its own window.

## Search, comparison and discovery

### Search

Search runs on an explicit submit. Only a submitted query is sent, and the report follows the text that was submitted rather than the text in the field. **Active only** and the language are part of the request, so a change to either re-runs the submitted query. An empty field submits nothing.

The report arrives in the tier order of the backend, and the tab draws each run of results that share a first match source as one tier under the name of that search method. A result lists every method that matched it. A query with no result shows an empty state.

On a desktop viewport the search field, the result groups and each result row share one aligned column. The search bar holds **Active only** inside it at the right, just before the submit button, and the **?** help sits outside the bar. A course name stays on one line in its row, and the shared course menu carries the complete name at any length.

At a phone width the search box sits in the middle of the tab while no report, loading state or error is shown. A search puts the box at the top of the tab and the results scroller under it.

The box is one bordered surface, and that border marks focus while the field has focus. It holds the magnifier, the growing query field and a 35 by 35 px submit button. Below the box, outside its outline, **Active only**, the **?** button and the result count sit on one row, with the count at the right. A border separates that fixed header from the results scroller.

A tap on a result centers it between that header and the action menu and opens the course menu, with temporary space below the list when the card cannot otherwise reach that position. The scroller is the only vertical scroll owner: it holds the error notices and the results.

In a result row the code, the comparison slot badge, the selected or completed badge and the activity share the first line, with the activity at the right. The name and its credits share the second line, the name takes the width before the credits and stays on one line with an ellipsis when it is longer, and the match marks close the row. The code and the name begin at one left edge. Adjacent result cards are separated by a small gap. The course menu scrolls within the screen when its content is taller than the viewport.

From 681 to 1199 px a result row sets the code and the comparison badge on the first line, the full title on one line on the second, the credits, the activity and the state on the third, and the match marks on the fourth. The title is cut by an ellipsis where the row is narrower than it, and the course menu carries the complete name.

A report whose query embedding request failed carries no semantic match, and the tab shows a localized notice above the results and draws the lexical matches as usual. The notice belongs to that report alone, so the next submitted search replaces it. A site that serves no semantic matching runs the lexical methods alone, and its tab shows neither the semantic help item nor that notice, because no semantic method ran and no provider was asked for a query vector.

### Compare

The comparison holds two slots, A and B. A course joins the first empty slot, and a course that already holds a slot is refused. While both slots are full, the app asks which of the two slots takes the course that was picked. Choosing a course that holds the other slot clears that slot. The report is keyed by the two courses alone in caller order and belongs to the shared memory cache.

Each occupied slot reads its own course summary, so replacing one slot reads only the course that takes it and leaves the other course's card in place. While a changed pair is read, the verdict reads **Comparing courses…**, each meter shows a dash in place of a percentage, and each bar holds its position. The bars move to the values of the returned report. A pair with an empty slot clears the meters.

At a phone width the two slots stack in one column. A filled slot is one bordered surface with a head row above a course band. The head row carries the slot letter A or B in a 28 px square at the left and the 36 px **Replace** and **Remove** controls at the right. The course band holds the code, the full wrapped name at 15 px, the credits and the activity, and the selected or completed badge below them.

An empty slot is one dashed surface at least 72 px tall that reads **+ Course A** or **+ Course B**, and the whole surface opens the picker. The five meters form one bordered surface, and each row puts the label and its description at the left and the percentage at the right on the first line, with the bar across the width on the line below.

The picker fills the tab area from 8 px below the top edge to 8 px above the bottom bar, with an 8 px margin on each side. Its header stays in place. The outlined search field holds the magnifier and the text, and **Active only** sits below it outside the outline. Each result is one bordered row. On a phone the code and action label share the first line and the name, clamped to two lines, follows, with the credits omitted. On a wider viewport the credits sit on the first line with the code. The whole row picks the course. The result list scrolls in the space below.

### Discover

Discover holds two lists, next courses and recommendations. Its settings are the list, the basis (the completed courses or every selected course), the activity scope, and, for next courses, the prerequisite mode **All** or **Partially covered**. The rendered **Partially covered** label is the `AT_LEAST_ONE` mode and the saved `at_least_one` value. It lists a course when any prerequisite is covered, including a course with every prerequisite covered. Recommendations use **All**, because a course that the chosen mode lists as a next course is never recommended. A site that serves no embedding features offers no **Recommended** list at all.

The request carries both course sets and the chosen basis, and inferred prerequisites take part on a site that serves inference features. An empty chosen basis sends no request and shows a prompt to select or complete courses. A successful list joins the shared memory cache under the chosen list and the request. The read is bound to the serialized list and request, so a change elsewhere in the profile starts no Discover read and the app leaves the result rows in place.

The results keep the backend order, each row carries its prerequisite coverage meters or its similarity meter, and the chosen list, mode, basis and scope are saved. Adding a course to comparison from a result row marks its card with the slot letter and starts no Discover read.

On a desktop viewport a result row fills the aligned column, its course name stays on one line, and its meters keep their own columns. From 681 to 1199 px a result row holds the course title on one line. The card and the meters stack in one column below 851 px, where the code, the name and the meter label share one left edge, and they sit side by side from 851 to 1199 px.

At a phone width a sticky header holds the **Next courses** and **Recommended** buttons, with a settings icon at the right. The icon opens a sheet above the bottom bar with the prerequisite mode, the basis, the activity scope and the **?** help. The sheet closes when the tab content leaves the phone width and returns closed when the width returns, without moving focus to a hidden trigger. The **?** sits at the bottom right, and **Active only** takes one column like the same control in Graph options.

A result row stacks the course card above its meters inside the row's own border. The card uses the same three-row layout as a search result, with a one-line title and its credits on the second line, and a derived-text mark closes the card. A next course that depends on inferred prerequisites carries the **inferred** mark beside its code on the first line.

At a phone width the basis chips show the course code alone, and the expanded basis list wraps each name instead of cutting it. The expanded basis opens in a picker that fills the tab area, and its list fills the space below the total line and scrolls there. Each basis row is a bordered card that opens the course menu, with a small gap between rows. A tapped basis row centers between the list top and the action menu, with temporary space below the list when needed. The whole row, meters included, opens the course menu. On a desktop viewport the menu opens below that row when the viewport has room below it. On a phone it opens as the course sheet from the bottom edge of the window.

On a site that serves no embedding features the tab shows the next-course list, and its controls write the basis, the prerequisite mode, the activity scope and whether the basis is expanded. The tab never writes the saved list value, so a profile that saved **Recommended** shows next courses there.

A coverage meter appears for a category whose prerequisite option holds course slots, so a category with no course prerequisites shows no meter at all, and **All** shows no coverage meter because the basis satisfies the prerequisite requirements of every course it lists.

The **?** drawer explains the open list's settings and its percentages, which are the two coverage meters of a next course and the similarity meter of a recommendation, together with the marks the site serves.

The behaviour of each read behind these tabs is described in [Search](/docs/backend/search-and-discovery/search.md), [Comparison](/docs/backend/search-and-discovery/comparison.md), [Next courses](/docs/backend/search-and-discovery/next-courses.md) and [Recommendations](/docs/backend/search-and-discovery/recommendations.md). The stored state and the request lifecycle are described in [Browser state](/docs/frontend/browser-state.md). The structure tab is described in [Structure editor](/docs/frontend/structure-editor.md), the prerequisite tab in [Prerequisite graph view](/docs/frontend/prerequisite-graph-view.md), and the wiki in [Documentation wiki](/docs/frontend/documentation-wiki.md).
