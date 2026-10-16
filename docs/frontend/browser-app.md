# Browser app

The browser app is a five-tab shell over one current profile, and every tab reads and writes the same browser-held course state.

## The shell and its tabs

The app fills the window as a grid of three rows: the top bar, the tab area, and the footer. The top bar holds a button for each of the five tabs, the profile control, the language control, and **Docs**. The tabs are **Search**, **Compare**, **Prerequisites**, **Discover** and **Structure of studies**. The app is available in Finnish and English, and the documentation wiki behind **Docs** is in English.

A [profile](/docs/reference/glossary.md#browser-app) is one named set of the app state. A browser with no saved state starts with one profile named My plan, the English language, and the **Search** tab open. The profile control shows the name of the current profile, and it opens the profile list with the selected and completed counts of each profile, a **New profile** form, a rename control, and a delete control.

## Navigation and scrolling

A tab opens from its top bar button, from the arrow at either side of the tab area, or with the left and right arrow keys. The five tabs form a ring, so the last tab leads back to the first, and a move travels the shorter way round the ring. An arrow key is ignored while the focus is in a text field or a list control, and while a menu or a dialog is open.

Only the open tab scrolls. The shell is one window-high grid, so the top bar and the footer hold their places and the pane alone carries the scrollbar. The pane that leaves during a transition takes no input and is hidden from assistive technology while it moves.

## Profiles and shared course state

Everything a profile holds switches together: the language, the open tab, the selection, the completion, and the settings of each tab. Switching the profile rebuilds the tab area, so every tab starts from the state of the profile that is current.

The selection and the completion are shared by all five tabs. Selecting a course in one tab selects it in every other, and the same course menu opens on every course card: **Add to comparison**, **Open prerequisite graph**, **Add to Unplaced studies**, **Mark completed**, and **Open in Sisu**. Marking a course completed also selects it, and unmarking the completion leaves the course selected. **Open in Sisu** opens the official page of the course in another browser tab. A course that holds a comparison slot carries its slot letter on its card.

## Language and labeled analysis

The app language belongs to the profile. The language control switches between FI and EN, and the change reaches every app-authored word and the official course names, which are shown in the chosen language when the catalogue holds one for it. Changing the language leaves the study state alone.

Data is labeled apart from the official data. Inferred prerequisites take part only while **Inferred** is on. A comparison states that it is course information analysis rather than official equivalence, and it notes when derived text took part. A recommended course notes derived text in the same way.

The prerequisite graph states the origin of every relationship it carries, which is official, inferred, or composed, and a course card carries the **inferred** mark only when no official relationship reaches that course, so a course that the official data also names reads as official. A next course that the basis reaches only through inferred prerequisites carries the **inferred** mark. [Prerequisite graph](/docs/backend/prerequisites/prerequisite-graph.md) describes those origins and the drawing they drive.

## Saved state and transient reports

The [browser state](/docs/reference/glossary.md#browser-app) is the saved state of every profile in the browser's local storage. A profile saves its language, its open tab, its selection and completion, and the settings of each tab. Those settings are the search text and its activity scope, the two comparison slots and the comparison picker fields, the prerequisite root with its toggles and exclusions, the discovery list with its basis and scope, and the structure root with its choices and places.

What a profile saves and what a report holds are separate. No report is written to storage. A pane-owned read runs when its pane is opened with its inputs in place, and again when its inputs change, so the report it received lives only while that pane is on screen. The submitted search is held apart from its pane: the submitted text and its report sit in a session that spans the tabs and lasts while the profile is open, so a move to another tab finds them there.

A change from a user action is written to storage before it is published, so a write that fails publishes nothing and shows a notice that names the failure. The stored envelope is read back at startup and validated before the app starts: a schema version other than 1, a missing current profile, or a malformed profile or tab setting fails the start with a notice in both languages while the saved value is left as it is. Each feature constructs requests from its relevant profile inputs and submitted values. The profiles belong to the browser that holds them.

The diagram follows a change from the user action that makes it to the report that a tab shows.

![A user action writes browser storage before the updated profile becomes visible, and the stored state is restored at startup. Feature inputs reach the read-only web server through the API client, and the response supplies the displayed result. Dashed boxes mark reports that are never persisted, and the accent arrow marks the read request.](/docs/diagrams/browser-state-flow.svg)

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

### Compare

The comparison holds two slots, A and B. A course joins the first empty slot, and a course that already holds a slot is refused. While both slots are full, the app asks which of the two slots takes the course that was picked. Choosing a course that holds the other slot clears that slot. The report is keyed by the two courses alone and is transient.

### Discover

Discover holds two lists, next courses and recommendations. Its settings are the list, the basis (the completed courses or every selected course), the activity scope, and, for next courses, the prerequisite mode **All** or **At least one**. Recommendations use **All**, because a course that the chosen mode lists as a next course is never recommended.

The request carries both course sets and the chosen basis, and inferred prerequisites take part. An empty chosen basis sends no request and shows a prompt to select or complete courses. The results keep the backend order, each row carries its prerequisite coverage meters or its similarity meter, and the chosen list, mode, basis and scope are saved.

The behaviour of each read behind these tabs is described in [Search](/docs/backend/search-and-discovery/search.md), [Comparison](/docs/backend/search-and-discovery/comparison.md), [Next courses](/docs/backend/search-and-discovery/next-courses.md) and [Recommendations](/docs/backend/search-and-discovery/recommendations.md). The stored state and the request lifecycle are described in [Browser state](/docs/frontend/browser-state.md). The structure tab is described in [Structure editor](/docs/frontend/structure-editor.md), the prerequisite tab in [Prerequisite graph view](/docs/frontend/prerequisite-graph-view.md), and the wiki in [Documentation wiki](/docs/frontend/documentation-wiki.md).
