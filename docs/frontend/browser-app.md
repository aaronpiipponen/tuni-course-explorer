# Browser app

The browser app is a tab shell over one current profile, and every tab reads and writes the same browser-held course state.

## The shell and its tabs

The app fills the window as a grid of three rows: the top bar, the tab area, and the footer. The top bar holds a button for each tab the site serves, the profile control, the language control, and **Docs**. The footer holds the independent-project notice and a link to the source code repository at the address that `repositoryUrl` in `config/wiki.json` sets. The tabs are **Search**, **Compare**, **Prerequisites**, **Discover** and **Structure of studies**, and a site that serves no embedding features has no Compare tab. The app is available in Finnish and English, and the documentation wiki behind **Docs** is in English.

A [profile](/docs/reference/glossary.md#browser-app) is one named set of the app state. A browser with no saved state starts with one profile named My plan and the English language, and a fresh browser tab opens on the **Search** tab. The profile control shows the name of the current profile, and it opens the profile list with the selected and completed counts of each profile, a **New profile** form, a rename control, and a delete control.

## The site's features

The app reads the site's two feature switches before it mounts the shell. The bootstrap asks the server for them once with the shell's own request, shows **Loading site features** while the answer is pending, and shows the ordinary failure notice if the request fails. The answer lives for the visit and is not polled, retried or written to storage, and a profile switch or an ordinary navigation does not ask for it again. A site with embedding features serves comparison and recommendations, and a site with inference features serves inferred prerequisites and the controls and marks that describe them. Without the answer the app does not mount, because a switch it cannot read would leave a control serving a feature the server refuses.

A tab the site does not serve is absent from the top bar, the tab ring and its arrow keys. A stored open tab of a hidden **Compare** renders **Search** instead, and the stored value in the browser tab's session storage is left as it is until a deliberate navigation replaces it. The controls of a hidden feature are absent in the same way: the comparison entry of a course menu, the comparison slot mark on a card, the semantic help item of **Search**, the **Recommended** list of **Discover**, and the **Inferred** toggle and its help item of **Prerequisites**.

Hiding a control does not change any saved value. The two comparison slots, the saved **Discover** list, the saved **Inferred** toggle and the course sets are the profile's own values, and the profile holds them whether or not the site serves their controls. The open tab is not one of them: it belongs to the browser tab's own session storage, so a reload of that tab restores it and another tab keeps its own. No feature switch is part of the profile schema or of the saved envelope.

## Navigation and scrolling

A tab opens from its top bar button, from the arrow at either side of the tab area, or with the left and right arrow keys. The tabs the site serves form a ring, so the last tab leads back to the first, and a move travels the shorter way round the ring. An arrow key is ignored while the focus is in a text field, a text area, a select control or an editable element, and while a menu or a dialog is open.

Only the open tab scrolls. The shell is one window-high grid, so the top bar and the footer hold their places and the pane alone carries the scrollbar. The pane that leaves during a transition takes no input and is hidden from assistive technology while it moves. The open profile panel paints above the arrows at either side of the tab area, so its help and export controls accept ordinary pointer input at every width, including 360 px. The left and right arrow keys wrap between the tabs, and the arrow buttons at either side of the tab area are always shown.

Everything that moves follows the operating system's reduced-motion preference. With reduced motion a tab change, a drawer or a panel, a profile notice, a two-option switch, a result arrival or re-sort, a meter, a graph layout, a route lighting, a skeleton and a wiki sidebar, page or anchor scroll draw their end state at once. The static styles of each state show what it means: the selected switch option, the lit route edges, a loading label, and the content of an open panel.

## Profiles and shared course state

Everything a profile holds switches together: the language, the selection, the completion, and the settings of each tab. Switching the profile rebuilds the tab area, so every tab starts from the state of the profile that is current.

The open tab is not part of a profile. It belongs to the browser tab and lives in that tab's session storage, so a reload keeps it, another open browser tab keeps its own, and a fresh browser tab starts on **Search**. Switching, importing or restoring a profile leaves the open tab where it is, and opening a course's prerequisite graph from a card moves only the browser tab that asked for it.

The selection and the completion are shared by every tab. Selecting a course in one tab selects it in every other, and the same course menu opens on every course card: **Add to comparison** on a site that serves embedding features, **Open prerequisite graph**, **Add to Unplaced studies**, **Mark completed**, and **Open in Sisu**. Marking a course completed also selects it, and unmarking the completion leaves the course selected. **Open in Sisu** opens the official page of the course in another browser tab. A course that holds a comparison slot carries its slot letter on its card, and a site that serves no embedding features omits that letter from the card and from its accessible name.

## Language and labeled analysis

The app language belongs to the profile. The language control switches between FI and EN, and the change reaches every app-authored word and the official course names, which are shown in the chosen language when the catalogue holds one for it. Changing the language leaves the study state alone.

Data is labeled apart from the official data. Inferred prerequisites take part in the prerequisite graph only while **Inferred** is on, and only on a site that serves inference features. The Discover request carries `include_inferred` as the site's inference switch, so inferred prerequisites take part in its next-course and recommendation reads whenever the site serves inference features, with no toggle. A comparison states that it is course information analysis rather than official equivalence, and it notes when derived text took part. A recommended course notes derived text in the same way.

The prerequisite graph states the origin of every relationship it carries, which is official, inferred, or composed, and a course card carries the **inferred** mark only when no official relationship reaches that course, so a course that the official data also names reads as official. A next course that the basis reaches only through inferred prerequisites carries the **inferred** mark. [Prerequisite graph](/docs/backend/prerequisites/prerequisite-graph.md) describes those origins and the drawing they drive.

## Saved state and transient reports

The [browser state](/docs/reference/glossary.md#browser-app) is the saved state of every profile in the browser's local storage. A profile saves its language, its selection and completion, and the settings of each tab. Those settings are the search text and its activity scope, the two comparison slots and the comparison picker fields, the prerequisite root with its toggles and exclusions, the discovery list with its basis and scope, and the ordered programmes with their choices and places. The open tab lives in the browser tab's session storage instead.

What a profile saves and what a report holds are separate. No report is written to storage. A pane-owned read runs when its pane is opened with its inputs in place, and again when its inputs change, so the report it received lives only while that pane is on screen. The submitted search is held apart from its pane: the submitted text and its report sit in a session that spans the tabs and lasts while the profile is open, so a move to another tab finds them there.

A change from a user action is written to storage before it is published, so a write that fails publishes nothing and shows a notice that names the failure. The stored envelope is read back at startup and validated before the app starts: a schema version other than 2, a missing current profile, or a malformed profile or tab setting fails the start with a notice in English while the saved value is left as it is. Each feature constructs requests from its relevant profile inputs and submitted values. The profiles belong to the browser that holds them.

Every tab of one browser shares the current profile. A save re-reads the saved state, applies its change to that value, and writes the result, and an open tab follows the browser's storage event. A course marked in one tab therefore appears in the other open tabs, a profile switch reaches them as well, and another tab's change is never overwritten by a stale copy of the state.

### Files and the failure screen

The profile control offers a compact **Import** control that takes one file through **Choose file** or by a drop, and a bottom row that carries the help drawer, **Copy Sisu import script** and **Export**. The export list is open for several consecutive downloads, it sits below that row, and each row of it names one profile or **All saved data**. An exported profile does not become the current one. A profile downloads as `course-explorer-profile-<profile name>.json`, with each character that a file name cannot hold replaced by `_`, and the whole saved data downloads as `course-explorer-saved-data.json`.

Three kinds of file reach the import area, and the `type` field of the file decides what happens. A profile file asks for a confirmation that names the profile it holds, and **Import** creates a new current profile through the store, while a name that another profile holds is refused at that confirmation. A file of the whole saved state asks for a confirmation that states that it replaces every profile in this browser, and the page reloads after the replacement, so every open tab follows the replaced state. A Sisu capture asks for a confirmation with a **Profile name** field, names the captured programmes in order together with every item the capture left unresolved, and creates the profile with its captured hierarchy pending on the tab's first Structure of studies read. A cancelled, dismissed or failed confirmation writes nothing, and a file of another kind, or a file whose content does not hold the current shape, is refused with a notice and changes nothing.

The help drawer of the bottom row explains the export, the import and the Sisu capture in three sections. **Copy Sisu import script** copies the console script of [Sisu import script](/docs/guides/sisu-import.md) to the clipboard and reports **Sisu import script copied** in a green notice that closes after five seconds, or **Could not copy Sisu import script** when the copy fails. The copy leaves the profile menu open.

When the saved state cannot be read, the failure notice appears in place of the interface with **Export saved data** and **Reset saved data**, and that screen reads in English alone. The export downloads the stored text as it is, so a broken state can be repaired by hand. The reset asks for a confirmation titled **Reset saved data** that names the deletion of every profile, and it then starts again with one profile named My plan.

The diagram follows the feature read and the state that the other reads use. Before the shell mounts, the app asks the server for the site's feature switches once and holds the answer for the visit. A tab action is written into the browser tab's session storage before the open tab changes, and a course or settings action is written into the saved profiles before the current profile is published. The current profile supplies the feature request inputs, a typed client sends them to the read-only web server as a read request, and the server report becomes the result that the open tab shows.

![The app asks the server for the site's feature switches before the shell mounts. A tab action is written into the browser tab's session storage that holds the open tab, and a course or settings action is written into the saved profiles. The current profile supplies the request inputs, and the report returns as the result the open tab shows. Dashed boxes mark the reports that are never persisted, and the accent arrow marks the read request.](/docs/diagrams/browser-state-flow.svg)

## Requests when a tab or a profile changes

A read belongs either to a tab pane or to the search session, and the two have different lifetimes.

A pane-owned read is cancelled when its inputs change or when the pane leaves the view, and a result that arrives after its request was cancelled is dropped. A pane therefore shows only a report that belongs to the inputs in force. Each read has its own typed client, which posts its inputs as JSON to one same-origin route and returns the parsed report, and a response that is not successful becomes a failure the pane shows.

The search session lives above the panes for as long as the app is open, and it holds the submitted text and its report rather than the text in the field. A move to another tab leaves the session in place, and a change to the app language or to the activity scope re-runs the submitted query even while another tab is shown. The session ends with the profile, so switching the profile drops the submitted search and its report.

Switching the profile rebuilds the tab area, so a pane-owned read of the previous profile is abandoned as well. An operation that finishes after a profile switch is checked against the profile that started it and writes nothing.

A failed read shows one notice in the profile language with a short summary, and the diagnostic text is shown as it arrived. A narrowing box waits 200 ms after the last keystroke before it asks the server, and another keystroke cancels the pending question.

## Search, comparison and discovery

### Search

Search runs on an explicit submit. Only a submitted query is sent, and the report follows the text that was submitted rather than the text in the field. **Active only** and the language are part of the request, so a change to either re-runs the submitted query. An empty field submits nothing.

The report arrives in the tier order of the backend, and the tab draws each run of results that share a first match source as one tier under the name of that search method. A result lists every method that matched it. A query with no result shows an empty state.

A report whose query embedding request failed carries no semantic match, and the tab shows a localized notice above the results and draws the lexical matches as usual. The notice belongs to that report alone, so the next submitted search replaces it. A site that serves no semantic matching runs the lexical methods alone, and its tab shows neither the semantic help item nor that notice, because no semantic method ran and no provider was asked for a query vector.

### Compare

The comparison holds two slots, A and B. A course joins the first empty slot, and a course that already holds a slot is refused. While both slots are full, the app asks which of the two slots takes the course that was picked. Choosing a course that holds the other slot clears that slot. The report is keyed by the two courses alone and is transient.

### Discover

Discover holds two lists, next courses and recommendations. Its settings are the list, the basis (the completed courses or every selected course), the activity scope, and, for next courses, the prerequisite mode **All** or **At least one**. Recommendations use **All**, because a course that the chosen mode lists as a next course is never recommended. A site that serves no embedding features offers no **Recommended** list at all.

The request carries both course sets and the chosen basis, and inferred prerequisites take part on a site that serves inference features. An empty chosen basis sends no request and shows a prompt to select or complete courses. The results keep the backend order, each row carries its prerequisite coverage meters or its similarity meter, and the chosen list, mode, basis and scope are saved.

On a site that serves no embedding features the tab shows the next-course list, and its controls write the basis, the prerequisite mode, the activity scope and whether the basis is expanded. The tab never writes the saved list value, so a profile that saved **Recommended** shows next courses there. A coverage meter appears for a category whose prerequisite option holds course slots, so a category with no course prerequisites shows no meter at all, and **All** shows no coverage meter because the basis satisfies the prerequisite requirements of every course it lists. The **?** drawer explains the open list's settings and its percentages, which are the two coverage meters of a next course and the similarity meter of a recommendation, together with the marks the site serves.

The behaviour of each read behind these tabs is described in [Search](/docs/backend/search-and-discovery/search.md), [Comparison](/docs/backend/search-and-discovery/comparison.md), [Next courses](/docs/backend/search-and-discovery/next-courses.md) and [Recommendations](/docs/backend/search-and-discovery/recommendations.md). The stored state and the request lifecycle are described in [Browser state](/docs/frontend/browser-state.md). The structure tab is described in [Structure editor](/docs/frontend/structure-editor.md), the prerequisite tab in [Prerequisite graph view](/docs/frontend/prerequisite-graph-view.md), and the wiki in [Documentation wiki](/docs/frontend/documentation-wiki.md).
