# Browser app

The browser app is a tab shell over one current profile, and every tab reads and writes the same browser-held course state.

## The shell and its tabs

The app fills the window as a grid of three rows: the shell header, the tab area, and the bottom of the shell. On a desktop viewport the header is a top bar that holds a button for each tab the site serves, **Feedback**, **Docs**, the profile control and the language control, and the footer under the tab area holds the independent-project notice, a link to the source code repository at the address that `repositoryUrl` in `config/wiki.json` sets, and the curriculum source line. The curriculum source line states that Tampere University curriculum data is retrieved from Tampere University's Sisu KORI API.

From 761 to 960 px the top bar holds the `course-explorer/tuni` mark, **Feedback**, **Docs**, the profile control and the language control on its first row and the tab buttons on a second row at least 56 px tall. At 961 px and wider the top bar is one 60 px row. A rule along the bottom of the top bar separates the header from the tab area.

On a phone the header is an empty safe-area strip, the bottom bar holds a button for each served tab and **More**, and **More** opens a sheet above the bar with the profile control, a row carrying the language control at the left and the **Feedback** and **Docs** buttons as one right-aligned pair, and the same notice, source link and curriculum source line. On desktop **Feedback** and **Docs** are transparent pills with a thin outline, while on the phone both use the same filled accent pill and height. Each phone bar button carries a short label on one line and the full tab name as its accessible name.

Opening **My plan** in **More** hides the language, **Feedback** and **Docs** row and the footer, and grows the profile panel upward to its content height above the bottom bar.

The tabs are **Search**, **Compare**, **Prerequisites**, **Discover** and **Structure of studies**, and a site that serves no embedding features has no Compare tab. The app is available in Finnish and English, and the documentation wiki behind **Docs** is in English.

A [profile](/docs/reference/glossary.md#browser-app) is one named set of the app state. A browser with no saved state starts with one profile named My plan and the English language, and a fresh browser tab opens on the **Search** tab. The profile control shows the name of the current profile, and it opens the profile list with the selected and completed counts of each profile, a **New profile** form, a rename control, and a delete control.

On a phone the profile control is the first row of the **More** sheet, and its panel opens inside that sheet. On the phone shell the profile panel takes the first Escape, and a subsequent Escape closes **More** with focus back on **More**.

At 680 px and below the profile panel uses the compact scale: 26 px profile icons and help controls, a 32 px **New profile** field, 24 px **Save** and transfer controls, and 32 px export rows. From 681 to 760 px the phone shell keeps its wider content, the profile trigger is at least 44 px tall and the profile select is 48 px. A profile name wraps in full, and the panel has no scroll of its own because the **More** sheet is the one surface that scrolls.

**Search**, **Compare**, **Prerequisites**, **Discover** and **Structure of studies** each carry a **?** button that opens the screen's help drawer, and the profile panel and the empty **Structure of studies** import area carry their own **?** buttons. The drawer header stays in place and its body scrolls under it with the shared thin accent scrollbar.

Help links sit inside the heading, term or explanation they belong to, in the profile language and in the same browser tab. The Search drawer links its activity option, its method heading and its results entry to the search guide, and its Semantic method to the technical search page. The Prerequisites drawer links its basis, its inferred option and its route and graph entries to the prerequisite guide, and its inferred evidence to the inference experiments.

The Discover drawer links its mode and basis to the guide, its category coverage and similarity entries to their technical pages, and its inferred mark to the inference experiments. The Compare drawer links the **Compare** entry, the overall-relatedness and overlap meters, the verdict and the missing-value entry to the comparison pages. The Structure of studies drawer links its structure actions to the structure guide and **Profiles and import** to the profile guide. The profile drawer links the profile control, the export and the import to the profile guide, and the Sisu capture to the import guide. The empty import area holds the import and Sisu plan sections alone.

On a phone a **?** drawer nested in an options sheet takes the first Escape, and a second Escape closes the sheet and returns focus to its trigger.

## The site's features

The app reads the site's two feature switches before it mounts the shell. The bootstrap asks the server for them once with the shell's own request, shows **Loading site features** while the answer is pending, and shows the ordinary failure notice if the request fails.

The answer also carries the serving dataset identity, and the app mounts one bounded read cache and one bounded persistent discovery cache for that identity above the tab panes. The answer lives for the visit and is not polled or retried, and a profile switch or an ordinary navigation does not ask for it again.

A site with embedding features serves comparison and recommendations, and a site with inference features serves inferred prerequisites and the controls and marks that describe them. Without the answer the app does not mount, because a switch it cannot read would leave a control serving a feature the server refuses.

A tab the site does not serve is absent from the shell's tab controls, the tab ring and its arrow keys. A stored open tab of a hidden **Compare** renders **Search** instead, and the stored value in the browser tab's session storage is left as it is until a deliberate navigation replaces it. The controls of a hidden feature are absent in the same way: the comparison entry of a course menu, the comparison slot mark on a card, the semantic help item of **Search**, the **Recommended** list of **Discover**, and the **Inferred** toggle and its help item of **Prerequisites**.

Every cached read reports the serving dataset identity, and a response carrying another identity clears the values the cache held for the previous one.

The read cache holds successful reads. A successful discovery report also persists, so a reload shows the report the browser holds for the same next-course or recommendation request without a server read, and a successful structure report renders across a reload before any structure request and only for the serving dataset and the selections that produced it. [Browser state](/docs/frontend/browser-state.md#async-reads-cancellation-and-request-identity) states the discovery cache's entries and the bound on its stored envelope.

The serving dataset identity changes when the serving process restarts, so a change of the Selected pointer and an in-place change to served data both reach a browser after the restart that [Operations](/docs/operations/README.md#derived-files-served-data-and-the-web-restart) states, and then on an uncached read or a reload. A tab with no uncached read keeps the values it already holds until then, and nothing polls the identity or asks the server whether the data is fresh.

Hiding a control does not change any saved value. The two comparison slots, the saved **Discover** list, the saved **Inferred** toggle and the course sets are the profile's own values, and the profile holds them whether or not the site serves their controls. The open tab is not one of them: it belongs to the browser tab's own session storage, so a reload of that tab restores it and another tab keeps its own. No feature switch is part of the profile schema or of the saved envelope.

## The feedback page

**Feedback** opens `/feedback` as its own page rather than a course tab, and a direct reload of the page reads the form again. The app, documentation and feedback pages share one history entry each, so **Return to app** and the browser's back action restore the app entrance and the tab that was open. [Feedback page](/docs/frontend/feedback-page.md) states the form, its image limits, the derived publication default, the acknowledgment states and the failures.

## Navigation and scrolling

A tab opens from its button in the desktop top bar or the phone bottom bar, from the arrow at either side of the tab area on desktop, or with the left and right arrow keys. The tabs the site serves form a ring, so the last tab leads back to the first, and a move travels the shorter way round the ring. An arrow key is ignored while the focus is in a text field, a text area, a select control or an editable element, and while a menu or a dialog is open.

At a phone width the arrows are absent, the shell has no top bar and no footer, and the served tabs sit in one bottom bar together with **More**: five tab items plus **More** on a site that serves every feature, and four plus **More** on a site without the embedding features. Each item is at least 44 px wide and 56 px tall, and the active tab alone carries the current mark. **More** opens the sheet of shared controls and closes on **Close**, on Escape or on a tap outside it, and it also closes when the shell leaves the phone width and returns closed when the width returns.

Neither resize dismissal moves focus to a hidden trigger.

While a course drag is active the bottom bar keeps its current visibility, whatever the pane's autoscroll does. Otherwise, while the open tab content scrolls down, the bottom bar hides and the tab area expands into its space. It returns on an upward scroll, at the top, or after a dismissal or choice that closes a course menu, sheet, picker, drawer, help panel or confirmation dialog, submits a search, or switches the Discover list. Scrolling inside a sheet, drawer, picker or menu leaves the bar alone, so that surface does not resize under the finger. This applies to the phone shell alone.

A horizontal swipe in the open tab selects the next tab when it moves left and the previous tab when it moves right, and the ring wraps in both directions. A swipe counts only after it travels 8 px with horizontal dominance, it selects one tab when it travels at least 48 px, and it works only with touch input. A vertical gesture scrolls the pane.

A gesture that starts on a course card, a structure course tile or a Discover result row follows its direction, so a horizontal one selects a tab and a vertical one scrolls. A structure course card keeps that behavior until its hold activates a drag: a quick tap opens its menu, travel before the hold scrolls or swipes as before, and an activated drag holds the open tab and the tab ring until it ends. While the body carries `course-dragging`, the swipe handlers release any pending swipe, the arrow keys select nothing and the phone bar records a scroll position without hiding or revealing itself, so the drag owns the input and the bar keeps the place it had. Escape cancels the drag. A gesture that starts on any other button, a link, a field, the prerequisite graph, the route and member stack, a drawer, a picker, a profile menu or an open dialog leaves the open tab unchanged, as does a gesture while a drawer, a picker, a menu or a dialog is open.

Only the open tab scrolls. The shell is one window-high grid, so the desktop top bar and the footer hold their places and the pane alone carries the scrollbar. On a phone the shell has no top bar and no footer, the pane begins at the top of the window below the safe-area strip, and the bottom bar holds its place under it until a downward scroll hides it. The viewport declaration asks for the on-screen keyboard to overlay the content, so a focused field does not resize the shell or move the bottom bar.

The pane that leaves during a transition takes no input and is hidden from assistive technology while it moves. A pane's content rides with it as one piece: a row that would otherwise animate its arrival, its position or a meter holds that motion until the pane stops, so nothing inside the pane travels at its own speed. The shell header reports its own height to the document root, and the help drawer and the structure drawer begin below that measured edge, so on a phone they clear the display cutout. The open profile panel paints above the arrows at either side of the tab area on desktop, so its help and export controls accept ordinary pointer input at every width, including 360 px. The left and right arrow keys wrap between the tabs, and at a desktop width the arrow buttons at either side of the tab area are shown.

The document matches the shell's height at every width, so the window carries no page scroll beside the shell. Opening the app, including the return from the documentation or the feedback page, places the window at the top. The documentation page scrolls the document itself, and the feedback page scrolls in its own full-height pane.

Everything that moves follows the operating system's reduced-motion preference. With reduced motion a tab change, a drawer or a panel, a phone sheet or menu, the More utility row, the phone bottom bar, a profile notice, a changing notice, a two-option switch, a result arrival or re-sort, a meter, a graph layout, a route lighting, a skeleton and a wiki sidebar, page or anchor scroll draw their end state at once.

The static styles of each state show what it means: the selected switch option, the lit route edges, a loading label, and the content of an open panel.

## Profiles and shared course state

Everything a profile holds switches together: the language, the selection, the completion, and the settings of each tab. Switching the profile rebuilds the tab area, so every tab starts from the state of the profile that is current.

The open tab is not part of a profile. It belongs to the browser tab and lives in that tab's session storage, so a reload keeps it, another open browser tab keeps its own, and a fresh browser tab starts on **Search**. Switching, importing or restoring a profile leaves the open tab where it is, and opening a course's prerequisite graph from a card moves only the browser tab that asked for it.

The selection and the completion are shared by every tab. Selecting a course in one tab selects it in every other, and the same course menu opens on every course card. On a phone, a tap on a course card centers the card between the visible header and the action menu, adding temporary space below the list when the list cannot otherwise scroll that far.

The menu's title entry shows the course code in purple, the credits and the active or inactive status on its first row, with the status at the right in the ordinary card style and only the code in purple, then the full course name below, then a grey separator line. The name wraps to as many lines as it needs. [Shared course state](/docs/guides/README.md#shared-course-state) states the actions below the separator and the Unplaced studies action that the course's own state allows.

**Mark completed** completes a selected course in place, and **Remove completion** clears the mark and leaves the course selected. [Shared course state](/docs/guides/README.md#shared-course-state) states the bottom notices those actions show and the question that a course outside the selection raises. The graph's **Complete** button adds an unselected course to Unplaced studies with the added notice, changes the tint of a course already in the structure without a notice, and shows no notice when it removes a completion. In the structure drawer, the **Complete** control on a rule row's course places an unselected course in that rule and completes it, without that question.

Each course action and each add-all action shows its result through the notice provider, and [shared course state](/docs/guides/README.md#shared-course-state) states the words and the link of each notice. A notice that added no course carries no link.

The bottom notice area stacks every visible notice in one centred column, with a gap between them, so a newer notice neither replaces nor covers an older one. Each stack belongs to the tab that showed it and moves with that tab's slide. A transient notice closes after 2.2 seconds. A notice that carries a persistent key stays until that key is dismissed, and showing the same key again replaces that notice's words in place. A notice can link one phrase inside its words, and the link runs through the same action boundary as a notice button.

On desktop the stack sits above the app footer's top border. On the phone it rises above an open course, programme or profile menu, a bottom sheet, the minimum-route control or its route and member result, and it returns when that overlay or control goes. It sits above their scrims too.

A result tall enough to reach the notice pushes it off the top of the window rather than covering the result. A stack keeps its place while it leaves with its tab. Over a dialog, a confirmation, a picker or an open help drawer the stack keeps its bottom position: it sits above the scrim and below the panel of a dialog that does not fill the screen, and it sits above a full-screen surface, every picker and the help drawer. [Shared interface components](/docs/frontend/shared-interface.md#notices) describes the provider, the stack and the placement rules.

**Open in Sisu** opens the official page of the course in another browser tab. A course that holds a comparison slot carries its slot letter on its card, and a site that serves no embedding features omits that letter from the card and from its accessible name.

A canceled touch scroll leaves Enter and Space available on the card that holds focus, and the scroll itself opens no menu.

## Language and labeled analysis

The app language belongs to the profile. The language control switches between FI and EN, and the change reaches every app-authored word and the official course names, which are shown in the chosen language when the catalogue holds one for it. Changing the language leaves the study state alone.

Data is labeled apart from the official data. Inferred prerequisites take part in the prerequisite graph only while **Inferred** is on, and only on a site that serves inference features. The Discover request carries `include_inferred` as the site's inference switch, so inferred prerequisites take part in its next-course and recommendation reads whenever the site serves inference features, with no toggle. A comparison states that it is course information analysis rather than official equivalence, and it notes when derived text took part. A recommended course notes derived text in the same way.

The prerequisite graph states the origin of every relationship it carries, which is official, inferred, or composed, and a course card carries the **inferred** mark only when no official relationship reaches that course, so a course that the official data also names reads as official. A next course that the basis reaches only through inferred prerequisites carries the **inferred** mark. [Prerequisite graph view](/docs/frontend/prerequisite-graph-view.md) states the marks the drawing carries and how it draws an origin.

## Saved state and transient reports

The [browser state](/docs/reference/glossary.md#browser-app) is the saved state of every profile in the browser's local storage. A profile saves its language, its selection and completion, and the settings of each tab. Those settings are the search text and its activity scope, the two comparison slots and the comparison picker fields, the prerequisite root with its toggles and exclusions, the discovery list with its basis and scope, and the ordered programmes with their choices, places and card order. The open tab lives in the browser tab's session storage instead.

What a profile saves and what a report holds are separate. Two server reports reach browser storage: a successful discovery report joins the discovery cache, and a structure report joins the derived structure store. Each stored report answers only its own serving dataset identity, and a stored structure report also answers only its own root and module-version selection.

Every other tab report lives only while its pane is on screen, with the successful values the read cache holds for their request keys. The read cache is never part of a profile, and the derived structure store holds no user state, mark, completion or selection.

The submitted search is held apart from its pane: the submitted text and its report sit in a session that spans the tabs and lasts while the profile is open, so a move to another tab finds them there.

A change from a user action is written to storage before it is published, so a write that fails publishes nothing and shows a notice that names the failure.

The stored envelope is read back at startup and validated before the app starts: a schema version other than 3, a missing current profile, or a malformed profile or tab setting fails the start with a notice in English while the saved value is left as it is.

Each feature constructs requests from its relevant profile inputs and submitted values. The profiles belong to the browser that holds them.

Every tab of one browser shares the current profile. A save re-reads the saved state, applies its change to that value, and writes the result, and an open tab follows the browser's storage event. A course marked in one tab therefore appears in the other open tabs, a profile switch reaches them as well, and another tab's change is never overwritten by a stale copy of the state.

### Files and the failure screen

The profile control offers a compact **Import** control that takes one `.json` or `.pdf` file through **Choose file** or by a drop, and a bottom row that carries the help drawer, **Copy Sisu import script** and **Export**.

The **Structure of studies** tab offers the same import area below **Add programme** while its programme list is empty. That area shows the **Import** heading, the **Choose** prompt and drop control, **Copy Sisu import script** and a **?** help drawer, without the export list.

The export list is open for several consecutive downloads, it sits below that row, it opens with **Select which file to export** above its rows, and each row of it names one profile or **All saved data**. An exported profile does not become the current one. A profile downloads as `course-explorer-profile-<profile name>.json`, with each character that a file name cannot hold replaced by `_`, and the whole saved data downloads as `course-explorer-saved-data.json`.

Four kinds of file reach the import area. A `type` field decides the JSON kinds, and the PDF path is chosen by the `application/pdf` MIME type or a `.pdf` suffix.

- A profile file asks for a confirmation that names the profile it holds. A new name gets **Import**, which creates a new current profile through the store. A name that another profile holds gets **Overwrite** instead, the confirmation states that it replaces that profile's saved data and makes it current, and the notice **A profile with that name already exists** enters above the buttons.
- A file of the whole saved state asks for a confirmation that states that it replaces every profile in this browser, and the page reloads after the replacement, so every open tab follows the replaced state.
- A Sisu capture asks for a confirmation with a **Profile name** field, names the captured programmes in order together with every item the capture left unresolved, and creates the profile with its captured hierarchy pending on the tab's first Structure of studies read. A typed name that another profile holds applies the same **Overwrite** rule and the same notice.
- A supported Sisu plan PDF runs through the lazy decoder and the browser-local match, then asks in the same confirmation with a **Profile name** field. The dialog names the programmes, a module that waits for a version choice, and every omitted item with its reason and any official candidates. Confirming creates the profile with the same pending hierarchy, with the same **Overwrite** rule for a typed name that another profile holds. The gathered match reads agree on one dataset identity in each read batch, and cancel writes nothing.

A cancelled, dismissed or failed confirmation writes nothing, and a file of another kind, or a file whose content does not hold the current shape, is refused with a notice and changes nothing.

The help drawer of the bottom row explains profiles, export, import with the PDF steps, and the Sisu capture in four sections. In the empty **Structure of studies** import area the same drawer explains the import and the Sisu plan without the profile and export sections.

**Copy Sisu import script** copies the console script of [Importing a Sisu plan](/docs/guides/sisu-import.md) to the clipboard and reports **Sisu import script copied** in a green notice that closes after five seconds, or **Could not copy Sisu import script** when the copy fails. The copy leaves the profile menu open.

When the saved state cannot be read, the failure notice appears in place of the interface with **Export saved data** and **Reset saved data**, and that screen reads in English alone. The export downloads the stored text as it is, so a broken state can be repaired by hand. The reset asks for a confirmation titled **Reset saved data** that names the deletion of every profile, and it then starts again with one profile named My plan.

The diagram follows the feature read and the state that the other reads use. Before the shell mounts, the app asks the server for the site's feature switches and the serving dataset identity once and holds the answer for the visit.

A tab action is written into the browser tab's session storage before the open tab changes, and a course or settings action is written into the saved profiles before the current profile is published.

The current profile supplies the feature request inputs, a typed client sends them to the read-only web server as a read request, and the server report becomes the result that the open tab shows.

![The app asks the server for the site's feature switches and the serving dataset identity before the shell mounts, a tab action is written into the session storage that holds the open tab, and a course or settings action is written into the saved profiles. The current profile supplies the request inputs, the report returns as the result the open tab shows, a successful report joins the read cache, a discovery report joins the discovery cache, and a structure report joins the derived structure store. Dashed boxes and lines mark cached, transient or derived values, and the accent arrow marks the read request.](/docs/diagrams/browser-state-flow.svg)

## Requests when a tab or a profile changes

A read belongs either to a tab pane or to the search session, and the two have different lifetimes.

A pane-owned read is cancelled when its inputs change or when the pane leaves the view, and a result that arrives after its request was cancelled is dropped. A pane therefore shows only a report that belongs to the inputs in force, and a response that is not successful becomes a failure the pane shows. [Browser state](/docs/frontend/browser-state.md) states the read rule, the cache and the request identity behind each pane.

The prerequisite graph read is served from the read cache. One cache lives above the panes for as long as the feature bootstrap holds, so a graph that was read once is shown again when the pane reopens, when another tab is opened, and when the profile changes, as long as its structural inputs match.

Leaving the pane aborts a read that is running and keeps every successful value. A cached value is shown without a request, and only a structural input the cache does not hold asks the server.

A successful prerequisite route calculation joins the same cache under the graph's structural key and the live route inputs. The minimum route runs in a browser worker over the solver structure of the held report, and [Graph layout](/docs/frontend/graph-layout.md#the-hooks-and-the-graph-key) states the key it is held under and the modules that calculate it.

The route appears only on an explicit **Find minimum route** click: clearing it, changing an input, leaving the pane or remounting the pane clears the visible route, returning to earlier inputs does not restore it, and a further explicit click with the same inputs shows the held value without starting a worker. The held drawing, its route control and its route stay on screen while the pane slides out and go with it, and the pane's reads stop once it has left.

The search session lives above the panes for as long as the app is open, and it holds the submitted text and its report rather than the text in the field. Only a submitted request is read, and a successful report joins the shared read cache, so resubmitting the same request shows it without a new search request.

A move to another tab leaves the session in place, and a change to the app language or to the activity scope re-runs the submitted query even while another tab is shown. The session ends with the profile, so switching the profile drops the submitted search and its report.

Switching the profile rebuilds the tab area, so a pane-owned read of the previous profile is abandoned as well. An operation that finishes after a profile switch is checked against the profile that started it and writes nothing.

A failed read shows one notice in the profile language with a short summary, and the diagnostic text is shown as it arrived. A narrowing box reads the one cached minimal official catalogue and filters it locally, so it sends no request per keystroke and needs no debounce.

The Compare picker, the prerequisite course box, the programme picker and the drawer search hold every match in their list, so Tab enters the list at its first match and leaves it after its last one. The keyboard moves between all of its rows with Tab, Shift+Tab, the arrow keys, Home and End, including the rows that are not on screen, and Enter or Space performs the focused row's action. A long list draws only a window of its rows, which [Browser state](/docs/frontend/browser-state.md#async-reads-cancellation-and-request-identity) describes.

The shared course lookup that Compare and Prerequisites open suppresses a pick after a canceled touch scroll, so a scroll leaves Enter and Space available for the focused row and picks no course. The module and programme pickers and the drawer search carry no touch capture. The Search result list has its own window.

## The tab layouts

The Search, Compare and Discover tabs arrange their controls and their reports at the desktop, intermediate and phone widths. [Tab layouts](/docs/frontend/tab-layouts.md) states the Search, Compare and Discover layouts, including their phone controls, their result rows and their pickers.

The behaviour of each read behind those tabs is described in [Search](/docs/backend/search-and-discovery/search.md), [Comparison](/docs/backend/search-and-discovery/comparison.md), [Next courses](/docs/backend/search-and-discovery/next-courses.md) and [Recommendations](/docs/backend/search-and-discovery/recommendations.md). The stored state and the request lifecycle are described in [Browser state](/docs/frontend/browser-state.md). The structure tab is described in [Structure editor](/docs/frontend/structure-editor.md), the prerequisite tab in [Prerequisite graph view](/docs/frontend/prerequisite-graph-view.md), and the wiki in [Documentation wiki](/docs/frontend/documentation-wiki.md).
