# Prerequisite graph view

The prerequisite graph view draws one course's requirement tree from the server report and offers a temporary minimum route beside the drawing.

## The graph input and the route input

The pane keeps one complete snapshot of the profile inputs: the graph root, the selected courses, the completed courses, the excluded courses, the **Recommended** toggle, the **Inferred** toggle on a site that serves inference features, the activity scope, the basis, and the marks placed on graph nodes. The basis is the set of courses that counts as already covered, and the **Route basis** control switches between the completed courses and every selected course. A completed course is always selected, so it is part of either basis.

The explicit route calculation combines that complete snapshot with the solver structure of the held graph report. The graph read takes its structural subset: the root, the selected and completed course sets, the two category toggles and the activity scope. Its course sets serve one purpose, the retention of selected or completed inactive courses under **Active only**, and the request carries no basis, exclusions or marks.

The box states belong to the browser. The pane evaluates them from the held report and the live snapshot, so completing, excluding, marking or changing the basis updates the drawing at once without a graph request. The drawing and the explicit route describe the same requirement set, because the calculation reads the solver structure of the held report. [Prerequisite graph](/docs/backend/prerequisites/prerequisite-graph.md) states what the graph read compiles and returns, and [Minimum route](/docs/backend/prerequisites/minimum-route.md) states what the calculation produces.

## When the pane reads

With no [graph root](/docs/reference/glossary.md#prerequisites-and-routes), the pane shows a prompt and **Choose course**. **Change** beside the root opens the same picker. The picker narrows courses by name or code from the cached minimal official catalogue, honors the activity scope locally, and opens the chosen course as the root.

The graph read runs only while the **Prerequisites** tab is open. Closing the tab cancels a pending read and drops its report, while every successful report stays in the app-level read cache. A structural input the cache holds is shown again with no request when the pane reopens, when another tab is opened, or when the profile changes. A structural input the cache does not hold asks the server, and a report that arrives after its request was cancelled is dropped.

The graph key changes with the root, the **Recommended** and **Inferred** toggles, the activity scope, and the effective inactive retention under **Active only**. Under **Active only** the pane also reads the selected courses' summaries to learn which of them are inactive, because a selected course the graph does not draw can still need retention. A summary request is separate from the graph read.

While that classification is pending the pane starts no graph read and keeps the drawing it holds, and a summary failure is shown as a read failure. Each settled classification covers every requested selected identity, and a response that omits one is refused instead of guessing its activity. Completing or uncompleting an inactive course that is already retained does not change the retained set, and with **Active only** off a change to either course set causes no graph read at all.

A refresh of the same root leaves the last successful drawing on screen while the refreshed report is on its way. A change of root draws nothing until its own report arrives, and the pane shows a waiting state instead.

The pane calculates nothing while the report is not ready. Readiness requires an active root, a settled activity classification, no input error, a resolved structural key and a settled response for that exact key and root. A held same-root report while changed structural inputs load is not ready, so **Find minimum route** stays disabled until the matching report has settled.

## What the server decides and what the browser draws

The report supplies the drawing's requirement structure and its located reasons. It states which course, module, connector and ignored nodes exist, which node is the root, which nodes are drawn as inferred, and which courses a module collects. It also groups every relationship that shares both endpoints into one connection, so the drawing shows one connection for each reported entry.

The browser computes each box's state from that report and the live profile state, so a mark, an exclusion and the basis reach the drawing without a server read. The browser also chooses where the drawing goes. It lays the nodes out to fit the pane, routes the connections between them, and animates a change of arrangement, so the report is the only source of which requirements exist and of every located reason.

The stage holds the route control, the drawing and the route and member panel stack. At 680 px and below the stage fills the pane from the top of the window to the bottom bar and the drawing fills the stage. A header across the top of the stage carries the root code and opens the **Graph options** sheet, a rail at the top right holds Recenter and the two zoom controls, the route control is a pill 12 px above the pane bottom, and the route and member results open in sheets over the bottom of the drawing. From 681 to 760 px the shell is the phone shell and the drawing follows its 681 to 760 rules: the controls sit in flow and the route result occupies its stack.

The route decision is a local browser calculation. **Find minimum route** starts one disposable worker over the held solver structure and the live snapshot, and the pane lights and lists what the worker returns. No server route request exists. Route outcomes and their meaning are stated in [Minimum route](/docs/backend/prerequisites/minimum-route.md).

The diagram follows the graph report and the live inputs into the browser calculation.

![The live profile inputs supply the graph read's structural subset, and the read returns one graph report carrying the solver structure, the serving dataset identity and the allocation limit. The graph report feeds the solver structure to the browser worker and draws the graph, a successful route joins the shared cache and becomes the route result, and the route result lights the drawing and fills the route panel.](/docs/diagrams/graph-view-flow.svg)

## The root and shared nodes

The graph root is the course whose prerequisite graph is open. On desktop the pane shows its official code and name, **Change**, and **Recenter**. **Recenter** returns the view to the root, and it is available while the report allows a drawing.

At 680 px and below the pane fills the height between the top of the window and the bottom bar. A header across the top of the stage shows the root code and opens the **Graph options** sheet. The sheet begins with one full-width root button that shows the course code, the course name on one line with an ellipsis, and a swap icon, and the whole button opens the root picker. The basis, **Recommended**, **Inferred**, **Active only** and help controls follow, and the **?** control sits at the bottom right of the sheet.

A **?** drawer nested in the sheet takes the first Escape, and a second Escape closes the sheet and returns focus to the header trigger. The sheet closes when the window leaves the phone width and returns closed.

The rail at the top right renders at 680 px and below, with **Recenter**, **Zoom in** and **Zoom out** as 38 by 38 px buttons. Recenter centres the root with 72 px clear above it, and the two zoom controls use the drawing's own 0.15 to 2.2 range. From 681 px up **Recenter** is a button in the root row beside **Change**, and the drawing zooms through scroll and pinch gestures within the same range.

One canonical course is one node. A course that several requirements need is drawn once, with its own requirements drawn once, and only the root carries the root mark. Identical drawn structure under one owner is drawn once for every node kind, including a logical group, a numeric constraint, a module or degree node, a diagnostic, and an ignored annotation. The connections that reach and leave the shared node carry every relationship's own fact, and each relationship member is selected by the calculation piece that owns it. A graph-only mark on the shared box covers every calculation piece it represents. The first drawing of a root is centred on it.

## Course, module and connector nodes

Every node in the drawing has one kind, and the kind decides what the node shows and which controls it carries.

| Node | Shows | Controls |
|---|---|---|
| Course | The official code, name, credits and activity state of the course | Opens the shared course menu, and marks the course **Completed** or **Excluded**. An unselected course is completed after one confirmation |
| Module | The label **module**, the module's official name, and the count of its collected member courses, with **fulfilled** when its courses meet it | Opens the member panel, and marks the module node itself |
| Join | An **AND** or **OR** join | None |
| Numeric requirement | A pick range, a credit range, a course count, or the credit range of [unexpandable content](/docs/reference/glossary.md#prerequisites-and-routes) | Marks the node itself, like a module |
| Grouped requirement | The member course count of a grouped requirement | Opens the member panel |
| Reason | A located reason for a requirement that cannot be resolved | None |
| Ignored part | A muted note naming a source part that the calculation leaves out | None |

Opening a course sheet pans the drawing so the tapped node sits above the sheet, and the zoom, the marks and the graph inputs keep their values.

At 680 px and below every course and module name wraps to its full text, and the box grows to the height its content needs. The base footprint is a minimum, and the box follows the content height.

The member panel lists the official member courses, and for a module it also offers **Add all module courses to structure**. A module nested inside another module contributes its courses to the outer module's list, so one module box opens the flattened list. A course that the drawing reaches outside its module draws its own course box with its own prerequisites.

A member's external prerequisite attaches to its module box, a whole-module prerequisite draws that module's box, and two modules that share a member each show their own connection to the member's external prerequisite. The add-all action reports the number of courses the write added in the shared bottom notice, or that every member is already selected, and that notice links to **Structure of studies**.

The ignored parts are the ones [Prerequisite graph](/docs/backend/prerequisites/prerequisite-graph.md#unresolved-requirements-and-ignored-parts) describes, and each sits beside the node it belongs to.

A connection is dashed only when every relationship it stands for is inferred, so a connection that also stands for an official [prerequisite](/docs/reference/glossary.md#prerequisites-and-routes) is solid. Required and recommended relationships draw with the same line style. A course node that only inferred occurrences reach carries the **inferred** mark and a distinct outline, and one that an official occurrence also reaches is drawn as official, so an official prerequisite is never shown as inferred.

Hovering or opening a course lights the paths to all its direct parent courses and all its direct prerequisite courses through the boxes between them. Hovering or opening an AND or OR join or a module box lights upward to its nearest course parent on each incoming branch and downward to every nearest course child. Each walk stops at the first course it reaches, so a grandparent, a grandchild and a sibling that only a reversal at a shared parent would reach are not lit.

## Marks on the graph

A mark appears with the control that sets it, because the browser evaluates the drawing's box states from the profile's own course and node state. No graph request carries a mark.

- A course node's completion writes the shared course sets, so a course marked [completed](/docs/reference/glossary.md#browser-app) in the graph reads as completed in every other tab. A selected course completes at once, and an unselected course completes after one confirmation that adds it to Unplaced studies.
- A course node's exclusion is a prerequisite setting of the profile. The drawing marks it locally, and the explicit route calculation carries it: an [excluded course](/docs/reference/glossary.md#prerequisites-and-routes) never counts as covered and no route passes through it, while the drawing shows the course and its own prerequisites.
- A module box and a numeric box carry [node marks](/docs/reference/glossary.md#prerequisites-and-routes) keyed by the box's own scoped identity, never by a course. A box may stand for several calculation pieces, and one saved key covers every one of them. A saved key whose box the drawing does not include applies again when the box returns. The drawing applies a box mark locally, and only the explicit route calculation also consumes the saved keys, so completing or excluding a module rule does not complete or exclude any course. Marking a box as completed clears its exclusion, and excluding it clears its completion.

## The minimum route panel

**Find minimum route** starts one disposable browser worker for the held structure and the same inputs as the drawing. On desktop the control holds its place in the pane. At 680 px and below the control is a pill 12 px above the pane bottom, 12 px from each side and 48 px tall.

The visible result lives with the pane. A change to the root, the basis, the toggles, the activity scope, the course sets, the marks on the graph, or the pane leaving the view clears it back to the plain drawing, and clicking the control again clears it as well. Returning to earlier inputs shows the plain drawing again, and only another explicit click shows a held value. A successful outcome is kept in the same bounded read cache as the graph reports under a key that covers the dataset identity, the structural graph key, every live route input and the allocation limit, so a repeat click with the same inputs shows it without a worker. The cache is never written to a profile or to browser storage. While the calculation runs, the panel shows **Calculating…** and the connections dim.

A result lights its own path. The connections the route selects and the nodes on them are lit in order from the root outward, and everything else is dimmed. The panel header reads the new credits beside the full route credits, an exact route whose new credits are zero reads **Nothing new**, and the route is listed row by row under **Expand** and **Collapse**: a course the route adds, the unexpandable content it charges, and a course that the basis already covers marked **completed** or **selected**.

Every route node other than the root belongs to a selected connection, so a box that no selected connection meets is not lit. The root always lights, including when no new course is needed.

A route lights one chosen drawn occurrence per alternative. Two equal-cost alternatives do not both light: one chosen occurrence lights and the other stays dim. When a route requires two occurrences at once, both light, so two modules that share a member show both of their connections to the shared course. A shared box shows the union of the chosen occurrences that reach it. The calculation, the credits, the route rows and the public facts do not depend on which occurrence the drawing chooses.

The route panel and the member panel share one scrollable stack at the right of the drawing. At 680 px and below a collapsed route result opens a sheet over the bottom of the drawing at the pane width, at most 46 percent of the viewport height and 420 px. Expanding it fills the tab area above the bottom bar.

The expanded sheet has a fixed header with the total on one line, the status, **Collapse** and **Clear**, a scrolling course list, and a fixed **Add all missing courses to structure** control while the expanded list has missing courses. The phone rows omit the credits and carry the completion or selection mark beside the activity mark at the right. A **Clear** control in the header clears the route, the lit path is visible above the sheet, and a drag or a pinch on the drawing above the sheet pans or zooms it. A member sheet uses the same place and bound.

The purple glow is drawn around that stack, so it stays visible outside the clipping that keeps a closed disclosure out of the layout. The stack scrolls when its open panels exceed the pane height, and **Expand** and **Collapse** move the course list through the same disclosure animation. On desktop an expanded route panel fills the right side of the stage between its top and bottom insets, and its scrolling course list uses a thin purple scrollbar.

**Add all missing courses to structure** adds the route's new courses to Unplaced studies and reports the number it added in the shared bottom notice, or that every route course is already present. The panel names each blocked or unresolved requirement with its reason above the course list, and an active-only shortfall lists each deficient module rule with its achieved and required count or credits. Those entries are visible while the course list is collapsed.

The outcome decides what the panel says, and the drawing follows the outcome:

| Outcome | The panel and the drawing |
|---|---|
| **Exact minimum route** | The route rows, the new and full credits, and the lit path. |
| **Approximate route** | The same, with a note stating that the route is not guaranteed to be the minimum. |
| **No route found** | A note stating that the exact search was too large and the approximation gave up, the root failure listed, the root marked **timeout**, and no rows. |
| **No route exists** | A note stating that no route meets every requirement, one entry for each blocked requirement, and the blocked nodes lit. |
| **Route unresolved** | A note stating that some requirements cannot be resolved, one entry for each unresolved requirement, with those nodes lit and no rows. |
| **Shortfall** | The route rows, with a note stating that a module rule is only partly met with active courses, and one entry for each deficient module rule. |

## A drawing that is too large

`PREREQUISITE_GRAPH_MAX_ELEMENTS` in `config/web.toml` sets the largest number of drawing elements, counted as every node plus every edge, and the example sets 500. When the report states that the drawing is refused, the pane names the element count of the drawing against the limit, suggests the controls that shrink it, and draws no nodes or connections, while the route works from the solver structure. On a site that serves inference features the suggestion is **Tip: turn off Recommended or Inferred, or turn on Active only, to shrink the graph.** On a site that serves none it is **Tip: turn off Recommended, or turn on Active only, to shrink the graph.**

The refusal concerns the drawing alone. **Find minimum route** and its panel stay in place, and the calculation reads the same solver structure and returns the same route either way.

The drawings allowed and refused at the 500-element limit are measured in [Compact graph identity and projection](/docs/experiments/graph-and-route-algorithms/compact-graph-identity-and-projection.md#drawing-allowance).

## Waiting states and failures

While the first report of a root loads, the pane shows a waiting state with no drawing. A node takes no input while it is leaving the drawing or while the drawing is being laid out.

A failed read shows one notice that names the failure, and the pane draws no graph from it. A failed route calculation shows its notice in the route panel. A failed action, such as a refused completion, shows a notice beside the graph. A node or a connection that the refreshed report does not hold fades out of the drawing.

## What a change redraws

A change that adds or removes nodes or connections, such as a category toggle or the inactive retention of a selected course, produces a structural key that the cache may not hold, and its report produces another arrangement that the drawing moves between. A change of root draws its graph in place. A change that only alters box states, such as a completion, an exclusion, a node mark or the basis, leaves the held report in place and changes the box marks without a graph read. The drawing holds its layout while every measured node height is equal, and a phone layout runs when a state-driven mark changes a node's rendered height. The viewport transform is the same in both cases.

## Where to read more

[Graph layout](/docs/frontend/graph-layout.md) describes the graph model, the layout thread, the animated drawing and the route projection behind the pane. [Browser state](/docs/frontend/browser-state.md) describes the profile fields the pane reads and writes.
