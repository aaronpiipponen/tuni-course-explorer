# Frontend

The frontend is the five-tab browser app, the profile state it holds in the browser, and the documentation view it opens from Docs.

## The app and its tabs

The app is one shell with a top bar, a tab area and a footer. The top bar carries a button for each of the five tabs, the profile control, the language control and **Docs**, and the app runs in Finnish and English. Each tab joins two sources: the reports it reads from the server, which describe the official catalogue, and the state the open profile holds in the browser, which is its language, its course selection and completion, its exclusions, and the choices and places of the structure tab. A list of course cards is a report, while the mark that says a course is completed is browser state.

[Browser app](/docs/frontend/browser-app.md) describes the shell, its navigation and scrolling, the shared course state, the language and the labeled analysis, and the search, comparison and discovery reads.

## Browser state and the shared course actions

A profile is one named set of that state in the browser's local storage: its language, its open tab, its course selection and completion, and the settings of each tab. One store owns the saved state, and every change is written to storage before it is published, so a profile is there after a reload and a failed write publishes nothing.

The selection and the completion are shared rather than owned by a tab. A course marked completed in the structure tab reads as completed in the graph, in discovery and on every card, and a course selected in one tab takes part in the basis of another. [System boundaries](/docs/architecture/boundaries.md) states why this state lives in the browser, and [Browser state](/docs/frontend/browser-state.md) describes the store, the profile operations, the per-feature slices and the read lifecycle.

## The structure editor and the structure model

The **Structure of studies** tab reads one structure root from the server and lays the profile's own choices and places over the official content. Selecting a course there adds it to the shared selection, and the tab shows each course on one card.

[Structure editor](/docs/frontend/structure-editor.md) states the behaviour a reader can rely on, including the confirmations and the resets, and [Structure model](/docs/frontend/structure-model.md) describes the projection and the resolution behind it. [Structure of studies in the catalogue](/docs/backend/catalogue/study-structure.md) describes the official report itself.

## The prerequisite graph

The **Prerequisites** tab opens one course as the graph root and draws its prerequisite expression. Its controls choose the basis, whether recommended prerequisites take part, whether inferred prerequisites take part, and the activity scope. When the tree is too large to draw, the tab states the element count against the configured limit and points at the controls that shrink it. **Find minimum route** is a separate request whose result is held only while its inputs stay the same.

[Prerequisite graph](/docs/backend/prerequisites/prerequisite-graph.md) and [Minimum route](/docs/backend/prerequisites/minimum-route.md) state what those reads compile and return. [Prerequisite graph view](/docs/frontend/prerequisite-graph-view.md) describes the drawing, the node marks, and the temporary route panel.

## The documentation wiki

[Documentation wiki](/docs/frontend/documentation-wiki.md) describes the navigation, the page selection, the supported Markdown, and how a served copy shows an edit.

**Docs** opens the wiki inside the app. It is English, read-only and static. Its pages are the Markdown files that the wiki configuration file `config/wiki.json` names, rendered with their headings, their previous and next links and their own table of contents. A page that the configuration does not name is read on GitHub instead. The wiki carries the project's instructions, and it links to the developer pages, which sit under `docs/` beside the technical page of the same subject.
