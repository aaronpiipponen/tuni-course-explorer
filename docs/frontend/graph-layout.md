# Graph layout

Graph layout turns the server's prerequisite report into positioned drawing nodes and connections, and lights the path a returned route selects.

## The three hooks

`usePrerequisiteInputs` in `web/src/features/prerequisites/usePrerequisiteInputs.ts` reads ten profile values through `useProfileSelector` and the open tab from `useActiveTab` in `web/src/app/sessionTab.ts`, and builds one `PrerequisitesRequest`: `target_code`, `completed_codes`, `selected_codes`, `excluded_codes`, `include_recommended`, `include_inferred`, `active_only`, `basis`, `completed_node_keys` and `excluded_node_keys`. It returns the request, its `key` as `JSON.stringify(request)`, and `active` as `activeTab === "prerequisites"`. With no root the request is `null`, so a pane with no root asks for nothing.

`usePrerequisiteReport` in `web/src/features/prerequisites/usePrerequisiteReport.ts` owns the graph read.

- With no request or an inactive pane it resets the result to no report, no loading and no error.
- The effect depends on `[key, active]`, creates one `AbortController`, and aborts it on cleanup, so a key change and a pane exit both cancel the pending read.
- On a key change it holds the report when the root identity matches and clears it for a different root, and it sets `loading` with no error.
- A settled read is dropped when its signal is aborted, and a rejection becomes an `Error`.
- The render-time guard withholds a result whose `key` or `root` differs from the live ones: a different root reads as `loading: true` with a null report, and a same-root mismatch returns the held report.

`useMinimumRoute` in `web/src/features/prerequisites/route/useMinimumRoute.ts` owns the explicit route read, and only `find` starts a request.

- `find` returns without a request when the pane is inactive or the request is null, aborts the previous controller, stores a replacement in a ref, captures `initiatingKey`, and sets `calculating`.
- A settled read applies only when its signal is not aborted, its controller is the current one, and `currentKey.current` equals `initiatingKey`.
- `clear` aborts, drops the controller ref and writes the empty route state.
- An effect runs `discard` on `[key, active]` and on unmount, so a changed input and a pane exit both clear the route.
- The returned session is withheld unless the pane is active, the request exists and `state.key === key`, which prevents a result from showing against inputs that have moved on before the cleanup runs.
- `setExpanded` toggles the row disclosure. Neither the route hook nor the graph hook writes to the store.

## The graph model

`buildGraphModel(report, language)` in `web/src/features/prerequisites/graph/model.ts` maps the report to `ModelNode` and `ModelEdge` arrays and a `rootId`. Node kinds are `course`, `module`, `connector` and `ignored`, and the footprint of each comes from `NODE_SIZES` in `web/src/features/prerequisites/graph/sizes.ts`: `course` 210 by 104, `module` 210 by 100, `junction` 54 by 28, `label` 132 by 28 and `constraint` 150 by 64. A connector takes the constraint size for `cardinality`, `credits`, `course_count` and `opaque_credits`, the junction size for `and` and `or`, and the label size otherwise. `markable` is true for a module node and for a numeric connector.

`connectorLabel` renders the `and`, `or`, `cardinality`, `credits`, `course_count`, `opaque_credits` and `internal_requirement` kinds through `uiText`, and the `unresolved` kind through `reasonText` on its `unresolved_reason`, or on its own kind token when that is null. `range` collapses a minimum and maximum pair into the `min+`, `≤max` and `a–b` forms. A connector subtitle comes from `diagnosticText` with its located reason and detail, or from `reasonText` for a reason without a detail. An `internal_requirement` connector carries `members`, the tree courses whose identities are in `member_group_ids`. Node states are indexed by `action_key` from `node_states`, so a node's state is looked up and never derived in the browser.

Edge identity is `${source_node_id}>${target_node_id}-${index}` from the report order, and each edge keeps the report's `relationships`, a `recommended` flag from the first relationship's `official_kind` or `inferred_category`, and a `parentIndex` that is the first-seen index of its source node. `connectionChain(model, nodeId)` walks the connections from a node through connector nodes and returns the node and edge sets that a hover or an open panel highlights.

## Layout thread

`web/src/features/prerequisites/graph/elk.ts` creates one lazy `ELK` instance whose `workerFactory` returns the bundled `elkjs` layout thread, and `layoutWithElk` calls its `layout`, so every layout runs off the main thread. `layoutGraph` in `web/src/features/prerequisites/graph/layout.ts` sends each model node as a child with its footprint and each model edge as an edge, with `elk.algorithm` `layered`, `elk.direction` `DOWN`, `elk.edgeRouting` `ORTHOGONAL`, and the spacing values in `SPACING`: node to node 40, layer to layer 80, edge to node 24 and edge to edge 14.

The result is read into a node map of positions and sizes and an edge map of point lists, each list being the first section's start point, bend points and end point. The root position is then subtracted from every node and every point, so the root sits at the origin and a structure change never shifts the drawing under the viewport.

`useGraphLayout` in `web/src/features/prerequisites/graph/useGraphLayout.ts` keys its work on a signature of the root identity, each node identity and kind, and each edge identity. A change to node states alone leaves the signature identical, so the held layout is returned with the model and no layout runs. A changed signature holds the previous graph while the root identity matches, clears it for a different root, and drops a settled layout whose effect was cleaned up.

## The animated frame

`useAnimatedGraph` in `web/src/features/prerequisites/graph/useAnimatedGraph.ts` returns one `AnimatedGraphFrame` of nodes and edges, each with a position, an opacity and an `exiting` flag.

- The first graph, a changed root, and a frame whose geometry already equals the target publish the exact target with no transition. `sameGeometry` compares every node position and footprint and every edge point list.
- Any other change animates over `duration` 600 ms with a cubic ease. A node interpolates its position and footprint and fades in or out, and an exiting node holds its frame on screen until the animation ends.
- Under the operating system's reduced-motion preference the exact target frame is published with no transition: every node takes its target position and footprint at full opacity, an exiting node leaves the frame at once, and no glide or fade runs. The classes of the frame supply the static route lighting, dimming and selection styles.
- An edge whose points changed is fully transparent at the midpoint, where its drawn geometry swaps from the previous route to the new one, so a layout change never shows a slanted partial route.
- An edge whose points are identical produces no fade and no movement, so a drawing-neutral refresh moves nothing.
- The final tick publishes the exact target frame and cancels the pending animation frame, and the effect cancels it on cleanup.

## The canvas and the renderer components

`web/src/features/prerequisites/graph/PrerequisiteGraph.tsx` wraps `GraphCanvas` in `ReactFlowProvider`. `nodeTypes` maps the four kinds to `CourseNode`, `ModuleNode`, `ConnectorNode` and `IgnoredNode`, and `edgeTypes` maps `prereq` to `PrerequisiteEdge`.

`GraphCanvas` holds the hover, open-menu and open-panel identities, so only one of them highlights at a time. Nodes and edges are rebuilt from the animated frame on every render and offset by 40 and 30 units, and each node supplies `measured` with its fixed footprint so React Flow keeps the handle bounds of a controlled node. `interactionDisabled` is set while a node is exiting or a layout runs, and the course, module and connector node components render `inert` with that flag.

The rendering state on the canvas:

- `routing` is true when a route result exists or a route request is pending. Every node and edge the route lights holds full opacity and everything else is dimmed, and a course node that only the selected basis covers carries `selectedOnly`.
- `lit` comes from `buildRouteView`. `lit.levels` supplies the `route-delay-<level>` class and the `--dl` style that spreads the lighting from the root outward.
- Without a route, a hovered or open node lights its `connectionChain` instead.
- A node that an `approximation_failed` result marks carries the `timeout` flag, and an inactive course node renders at reduced opacity.
- `PrerequisiteEdge` draws the ELK point list as a polyline with a rounded corner per bend, plus a dark halo edge and the parent hue as the stroke. A `recommended` edge is dashed. The component carries the fade opacity and the lighting delay on its own group, because React Flow hands an edge's style to the edge component rather than to its wrapper group.

`centerRoot` sets the viewport so the root sits at the top of the panel, without animation on the first layout of a root and with a 450 ms animation from **Recenter** while the operating system asks for normal motion, and with no animation under the reduced-motion preference, which `PrerequisitesPane` calls through `recenterRef`. The open panel closes when a layout starts, and the open menu or panel closes when the node it names leaves the model. Dragging, connecting, selecting and keyboard focus are all off, and the zoom range is 0.15 to 2.2.

`CourseNode` renders a `CourseTile` with the shared course menu and with **Complete** and **Exclude** actions that call `toggleCompleted` and `toggleExcludedCourse`. `ModuleNode` and a numeric `ConnectorNode` render **Complete** and **Exclude** actions that call `toggleNodeCompleted` and `toggleNodeExcluded` with the node's `actionKey`. Opening a module or an internal-requirement connector sets the panel identity, and `MemberPanel` lists its `members` with the shared course rows and the module add control.

## The route projection

`web/src/features/prerequisites/route/route.ts` projects a returned `PrerequisitePath` against the report and the model.

`buildRouteSummary(graph, path, language)`:

- `edgeLights(relationships, selected)` is true when some relationship has one of its `occurrence_ids` in the selected set and every `condition_occurrence_ids` entry in it, so one supplied connection lights through any complete member relationship of its own.
- Rows exist for the `exact`, `approximate` and `shortfall` states: every `new_courses` entry first as uncovered, then every course node that a lit connection reaches and that is not new, as covered.
- `newCredits` comes from `total_new_credits` and `fullCredits` adds the credits of the covered course nodes. A null total means no credits.
- `problems` are de-duplicated by `occurrence_id|action_key|reason`, and each carries the title of its action key resolved through the course, module or connector nodes.
- `shortfalls` resolve a module or connector title and read as a course count or a credit comparison.
- `missingCourseIds` is the new course identities, and `blockedCourseIds` and `blockedNodeTitles` come from `blocked_excluded_group_ids` and `blocked_excluded_node_keys`.

`buildRouteView(graph, path, model, summary)` adds the lit sets: the root always, the endpoints of every lit connection for a route that exists, and for `no_solution` and `unresolved` the problem action keys, the blocked node keys and the blocked courses. An `approximation_failed` result lights the root alone. `lit.levels` is a breadth-first distance from the root over the model edges, and the canvas turns it into the lighting delay.

`RoutePanel` renders the outcome label, the note, the credit header, the rows and the add control. A course row is keyed `${group_id}-${covered}-${index}` and an unexpandable row `${work_key}-${index}`, so two entries of one course in one list stay distinct. `RouteControl` toggles between `find` and `clear`, and it is disabled while the graph loads or a route request runs, unless a result is already shown so that the control can clear it.

## The refused-drawing boundary

`PrerequisitesPane` is the early boundary of the drawing. It renders the empty state with no root, the loading skeleton while `graphLoading && !report`, `ErrorNotice` when the report read failed, `PrerequisiteGraph` when `report.drawing.allowed` is true, and `RefusedGraph` otherwise. `RefusedGraph` renders the same `RouteControl` and `RoutePanel` in the same stage layout, so the explicit route operation works while the drawing is refused. The pane computes the route summary with `useMemo` from the report and the route result and passes it to both branches.

## Graph actions and stored state

`web/src/features/prerequisites/actions.ts` exports `setPrerequisitesRoot`, `setPrerequisitesQuery`, `setPrerequisitesActiveOnly`, `setPrerequisitesBasis`, `setIncludeRecommended`, `setIncludeInferred`, `toggleExcludedCourse`, `toggleNodeCompleted` and `toggleNodeExcluded`. Every writer goes through the local `update` helper and `store.updateCurrent`. `toggleNode` adds or removes one `actionKey` in `completedNodeKeys` or `excludedNodeKeys` and drops it from the opposite list when it is added. `web/src/features/prerequisites/state.ts` holds `PrerequisitesState` and `initialPrerequisitesState()`, and `validateProfileState` in `web/src/state/validation.ts` projects a saved slice onto those fields.

## Tests

| File | Covers |
|---|---|
| `web/src/features/prerequisites/actions.test.ts` | The node marks persisted across a reload, the shared course sets left empty by them, and the opposite mark cleared by a completion or an exclusion |
| `web/src/features/prerequisites/route/route.test.ts` | The lit connections and nodes, the new plus covered credit total, one drawn edge per supplied connection, a grouped connection lit only through a complete member relationship, and the rows, problems, shortfalls and missing identities of every path state |

## Where a change belongs

- A report field the drawing should show belongs in `buildGraphModel` or `connectorLabel` in `model.ts`, together with the renderer component that draws it.
- A node footprint belongs in `NODE_SIZES`, and a spacing or routing value belongs in `SPACING` and in the `layoutOptions` of `layoutGraph`.
- A transition belongs in `useAnimatedGraph`, and the layout reuse rule belongs in the signature of `useGraphLayout`.
- A route presentation rule belongs in `route.ts`, and the row, note or control that shows it belongs in `RoutePanel` or `RouteControl`.
- A stored prerequisite setting belongs in `state.ts`, in `validateProfileState` in `web/src/state/validation.ts`, and in the action that writes it.
