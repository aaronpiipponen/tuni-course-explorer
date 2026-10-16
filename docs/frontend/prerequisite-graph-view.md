# Prerequisite graph view

The prerequisite graph view draws one course's requirement tree from the server report and offers a temporary minimum route beside the drawing.

## One input set for both reads

The pane keeps one snapshot of the profile inputs and sends it to both reads: the graph root, the selected courses, the completed courses, the excluded courses, the **Recommended** and **Inferred** toggles, the activity scope, the basis, and the marks placed on graph nodes. The basis is the set of courses that counts as already covered, and the **Route basis** control switches between the completed courses and every selected course. A completed course is always selected, so it is part of either basis.

The two reads are the prerequisite graph read and the minimum route read. Both resolve the same inputs and compile one [prerequisite expression](/docs/reference/glossary.md#prerequisites-and-routes), so the drawing and the route describe the same requirement set and cannot drift apart. [Prerequisite graph](/docs/backend/prerequisites/prerequisite-graph.md) states what the graph read compiles and returns, and [Minimum route](/docs/backend/prerequisites/minimum-route.md) states what the route read returns.

## When the pane reads

With no [graph root](/docs/reference/glossary.md#prerequisites-and-routes), the pane shows a prompt and **Choose course**. **Change** beside the root opens the same picker. The picker narrows courses by name or code, honors the activity scope, and opens the chosen course as the root.

The graph read runs only while the **Prerequisites** tab is open. Closing the tab cancels a pending read and drops its report, so opening the tab again asks for the graph again. A change to any input cancels the pending read and starts one read for the changed inputs, and a report that arrives after its request was cancelled is dropped.

A refresh of the same root leaves the last successful drawing on screen while the refreshed report is on its way. A change of root draws nothing until its own report arrives, and the pane shows a waiting state instead.

## What the server decides and what the browser draws

Every fact in the drawing comes from the report. The report states which course, module and connector nodes exist, which of them are met, marked or excluded, which node is the root, which nodes are drawn as inferred, and every located reason. The report also groups the connections that share their endpoints and their provenance class, so the drawing shows one connection for each reported entry.

The browser chooses where the drawing goes. It lays the nodes out to fit the pane, routes the connections between them, and animates a change of arrangement, so the report is the only source of which requirements exist and whether they are met.

The route decision is also the server's. The route read returns the courses, the tree occurrences and the outcome, and the pane lights and lists what it returns. Route outcomes and their meaning are stated in [Minimum route](/docs/backend/prerequisites/minimum-route.md).

The diagram follows the one input snapshot through the two reads to the browser.

![One profile input snapshot feeds the graph read and the explicitly started route read on the server. The graph read returns the graph report and the route read returns the route result. The browser lays the report out as the drawing and shows the route in the route panel, and the dashed box marks the browser drawing side, whose node states and routes come from the reports.](/docs/diagrams/graph-view-flow.svg)

## The root and shared nodes

The graph root is the course whose prerequisite graph is open. The pane shows its official code and name, **Change**, and **Recenter**. **Recenter** returns the view to the root, and it is available while the report allows a drawing.

One canonical course is one node. A course that several requirements need is drawn once, with its own requirements drawn once, and only the root carries the root mark. The first drawing of a root is centred on it.

## Course, module and connector nodes

Every node in the drawing has one kind, and the kind decides what the node shows and which controls it carries.

| Node | Shows | Controls |
|---|---|---|
| Course | The official code, name, credits and activity state of the course | Opens the shared course menu, and marks the course **Completed** or **Excluded** |
| Module | The label **module**, the module's official name, and the count of its official member courses, with **fulfilled** when its courses meet it | Opens the member panel, and marks the module node itself |
| Join | An **AND** or **OR** join | None |
| Numeric requirement | A pick range, a credit range, a course count, or the credit range of [unexpandable content](/docs/reference/glossary.md#prerequisites-and-routes) | Marks the node itself, like a module |
| Grouped requirement | The member course count of a grouped requirement | Opens the member panel |
| Reason | A located reason for a requirement that cannot be resolved | None |
| Ignored part | A muted note naming a source part that the calculation leaves out | None |

The member panel lists the official member courses and offers **Add all module courses to structure**. The ignored parts are the ones [Prerequisite graph](/docs/backend/prerequisites/prerequisite-graph.md#unresolved-requirements-and-ignored-parts) describes, and each sits beside the node it belongs to.

A [recommended prerequisite](/docs/reference/glossary.md#prerequisites-and-routes) is drawn apart from the required ones, as a dashed connection. A course node that only inferred occurrences reach carries the **inferred** mark and a distinct outline, and one that an official occurrence also reaches is drawn as official, so an official prerequisite is never shown as inferred.

## Marks on the graph

The two controls on a node differ by what the mark belongs to.

- A course node's completion writes the shared course sets, so a course marked [completed](/docs/reference/glossary.md#browser-app) in the graph reads as completed in every other tab.
- A course node's exclusion is a prerequisite setting of the profile. It belongs to both reads: an [excluded course](/docs/reference/glossary.md#prerequisites-and-routes) never counts as covered and no route passes through it, while the drawing shows the course and its own prerequisites.
- A module node and a numeric connector node carry [node marks](/docs/reference/glossary.md#prerequisites-and-routes) that name one graph node, never a course. Only the graph and the route read those marks, so completing or excluding a module rule does not complete or exclude any course. Marking a node as completed clears its exclusion, and excluding it clears its completion.

## The minimum route panel

**Find minimum route** starts one request for the same inputs as the drawing, and the control holds its place in the pane.

The result lives with the pane. A change to the root, the basis, the toggles, the activity scope, the course sets, the marks on the graph, or the open tab clears it back to the plain drawing, and clicking the control again clears it as well. While the request runs, the panel shows **Calculating…** and the connections dim.

A result lights its own path. The connections the route selects and the nodes on them are lit in order from the root outward, and everything else is dimmed. The panel header reads the new credits beside the full route credits, an exact route whose new credits are zero reads **Nothing new**, and the route is listed row by row under **Expand** and **Collapse**: a course the route adds, the unexpandable content it charges, and a course that the basis already covers marked done. **Add all missing courses to structure** adds the route's new courses to Unplaced studies.

The outcome decides what the panel says, and the drawing follows the outcome:

| Outcome | The panel and the drawing |
|---|---|
| **Exact minimum route** | The route rows, the new and full credits, and the lit path. |
| **Approximate route** | The same, with a note stating that the route is not guaranteed to be the minimum. |
| **No route found** | A note stating that the exact search was too large and the approximation gave up, the root marked **timeout**, and no rows. |
| **No route exists** | A note stating that every route is blocked by excluded or unavailable courses, with the blocked nodes lit and no rows. |
| **Route unresolved** | A note stating that some requirements cannot be resolved, with those nodes lit and no rows. |
| **Shortfall** | The route rows, with a note stating that a module rule is only partly met with active courses. |

## A drawing that is too large

`PREREQUISITE_GRAPH_MAX_ELEMENTS` in `config/web.toml` sets the largest number of drawing elements, counted as every node plus every edge, and the example sets 500. When the report states that the drawing is refused, the pane names the element count of the tree against the limit, suggests the controls that shrink it, and draws no nodes or connections.

The refusal concerns the drawing alone. **Find minimum route** and its panel stay in place, and the route read compiles the same expression and returns the same route either way.

## Waiting states and failures

While the first report of a root loads, the pane shows a waiting state with no drawing. A node takes no input while it is leaving the drawing or while the drawing is being laid out.

A failed read shows one notice that names the failure, and the pane draws no graph from it. A failed route read shows its notice in the route panel. A failed action, such as a refused completion, shows a notice beside the graph. A node or a connection that the refreshed report does not hold fades out of the drawing.

## What a change redraws

A change that adds or removes nodes or connections, such as a category toggle, produces another report and another arrangement, and the drawing moves between the two arrangements. A change of root draws its graph in place. A change that only alters node states, such as a completion or an exclusion, leaves the nodes and connections where they are, so only the marks change.

## Where to read more

[Graph layout](/docs/frontend/graph-layout.md) describes the graph model, the layout thread, the animated drawing and the route projection behind the pane. [Browser state](/docs/frontend/browser-state.md) describes the profile fields the pane reads and writes.
