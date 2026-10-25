# Frontend

The frontend is the browser app over the tabs a site serves, the state it holds in the browser, the separate administration console and the documentation view that Docs opens.

## The app and its tabs

The app is one shell with a header, a tab area and a bottom row. On desktop the header is a top bar that carries a button for each tab the site serves, the profile control, the language control and **Docs**, and the footer holds the independent-project notice and the source link.

On a phone the header is an empty safe-area strip and one bottom bar carries the served tabs plus **More**, whose sheet holds the profile control, the language control and **Docs**. The app runs in Finnish and English.

The site's two feature switches decide which tabs and controls it serves, and the app reads them once before the shell mounts, together with the serving dataset identity that bounds the app-level read cache above the tab panes.

Each tab joins two sources: the reports it reads from the server, which describe the official catalogue, and the state the open profile holds in the browser, which is its language, its course selection and completion, its exclusions, and the choices and places of the structure tab. A list of course cards is a report, while the mark that says a course is completed is browser state. The narrowing boxes filter one cached minimal official catalogue locally, so a keystroke sends no request.

[Browser app](/docs/frontend/browser-app.md) describes the shell, its navigation and scrolling, the shared course state, the language and the labeled analysis, and the search, comparison and discovery reads.

## Browser state and the shared course actions

A profile is one named set of that state in the browser's local storage: its language, its course selection and completion, and the settings of each tab. The open tab belongs to the browser tab instead. One store owns the saved state, and every change is written to storage before it is published, so a profile is there after a reload and a failed write publishes nothing.

The selection and the completion are shared rather than owned by a tab. A course marked completed in the structure tab reads as completed in the graph, in discovery and on every card, and a course selected in one tab takes part in the basis of another. [System boundaries](/docs/architecture/boundaries.md) states why this state lives in the browser, and [Browser state](/docs/frontend/browser-state.md) describes the store, the profile operations, the per-feature slices and the read lifecycle.

## The structure editor and the structure model

The **Structure of studies** tab reads the official structure reports of its ordered programmes, placed modules and exact version selections in one batch, keeps them in memory and in a derived IndexedDB store keyed by the serving dataset identity, the root and the selection identity, and lays the profile's own choices and places over that content. A canonical module with several eligible versions is chosen explicitly, and a group that still needs one shows its own candidate picker. Selecting a course there adds it to the shared selection, and each course shows on one card.

[Structure editor](/docs/frontend/structure-editor.md) states the behaviour a reader can rely on, including the confirmations and the resets. [Structure model](/docs/frontend/structure-model.md) describes the projection and the resolution behind it, [Structure edits](/docs/frontend/structure-edits.md) the placement edits and the selection migration, [Structure pane](/docs/frontend/structure-pane.md) the pane and its reads, and [Sisu capture](/docs/frontend/sisu-capture.md) the import of a captured plan. [Structure of studies in the catalogue](/docs/backend/catalogue/study-structure.md) describes the official report itself.

## The prerequisite graph

The **Prerequisites** tab opens one course as the graph root and draws its prerequisite expression. Its controls choose the basis, whether recommended prerequisites take part, whether inferred prerequisites take part, and the activity scope. The **Inferred** control appears on a site that serves inference features, and on a site that serves none the tab draws official prerequisites alone. When the tree is too large to draw, the tab states the element count against the configured limit and points at the controls that shrink it. **Find minimum route** is a local calculation in a browser worker whose result is held only while its inputs match.

[Prerequisite graph](/docs/backend/prerequisites/prerequisite-graph.md) and [Minimum route](/docs/backend/prerequisites/minimum-route.md) state what the graph read compiles and returns and what the route calculation produces. [Prerequisite graph view](/docs/frontend/prerequisite-graph-view.md) describes the drawing, the node marks, and the temporary route panel. [Graph layout](/docs/frontend/graph-layout.md) describes the graph model and the solver modules behind the local calculation.

## The administration console

The administration console is a separate React application with its own manifest and its own build, served by the administration backend. It opens on a sign-in screen and serves the five tabs **Dashboard**, **Data preparation**, **Inference**, **Logs** and **Settings**. The [Administration console](/docs/operations/admin-console/README.md) how-to describes the tabs and their actions.

Each read and each action of a tab runs one fixed `scripts/admin.py` command, so a tab performs several reads: **Data preparation** reads three stage statuses and three reports, and **Logs** reads its shared inventory, command log, session and runtime logs and usage window. Enabled automatic panels follow the configured poll interval, while target lookup and target decisions, maintenance and the other actions are explicit commands.

A worker log read and the worker preflight run on an explicit request alone. The retained-server inference summary is one read shared by its four report panels. The summary and the two dataset listings read only while the site's dashboard reports the selected dataset enabled, and otherwise they show the pending read, the disabled reason or the dashboard failure. A command that ran and failed shows its own safe failure line.

The administration rebuild runs two fixed commands: the console build and the backend restart. Its confirmation states that it signs every operator out, and the next sign-in reads a fresh session.

[Administration console code](/docs/frontend/admin-console.md) describes the separate build, the module ownership, the typed clients and the session, polling and error flow, and [Administration console panels](/docs/frontend/admin-console-panels.md) describes each tab's panels, their reads and their routes.

## The documentation wiki

[Documentation wiki](/docs/frontend/documentation-wiki.md) describes the navigation, the page selection, the supported Markdown, and how a served copy shows an edit.

**Docs** opens the wiki inside the app. It is English, read-only and static. Its pages are the Markdown files that the wiki configuration file `config/wiki.json` names, rendered with their headings, their previous and next links and their own table of contents. A page that the configuration does not name is read on GitHub instead. The wiki carries the project's instructions, and it links to the developer pages, which sit under `docs/` beside the technical page of the same subject.
