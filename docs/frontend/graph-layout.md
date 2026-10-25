# Graph layout

Graph layout turns the server's prerequisite report into positioned drawing nodes and connections, and lights the path a returned route selects.

## The hooks and the graph key

`usePrerequisiteInputs` in `web/src/features/prerequisites/usePrerequisiteInputs.ts` reads the profile values through `useProfileSelector`, the site's inference switch from `useWebFeatures`, and the open tab from `useActiveTab` in `web/src/app/sessionTab.ts`. It returns two things.

The complete snapshot is `request`, its `key` as `JSON.stringify(request)`, and `active` as `activeTab === "prerequisites"`. `request` is a `PrerequisitesRequest`: the root, the selected, completed and excluded courses, the **Recommended** and **Inferred** toggles, the activity scope, the basis, and the two node-mark lists. `include_inferred` is `includeInferred && inference_enabled`, so the snapshot carries inferred prerequisites only when the profile toggle is on and the site serves inference features. The explicit route calculation consumes this snapshot, and its `key` changes on every basis, mark and course-set change even when the graph key does not.

The structural snapshot is `graphRequest: PrerequisiteGraphRequest | null`, `graphKey: string | null`, `graphInputError: Error | null` and `graphInputsPending: boolean`. The graph request carries the root, the selected and completed course sets, the **Recommended** toggle, the effective inferred value and the activity scope. Its course sets hold only the inactive selected and completed courses that **Active only** must retain, so the graph is independent of the basis, the exclusions and every mark.

- Under **Active only**, the hook asks `useCourseSummaries` for the sorted unique selected identities, so a selected course the current graph does not draw still contributes its real activity flag. The inactive selected identities and their inactive completed subset become the graph request's two sets.
- With **Active only** off, or with no root, those sets are empty.
- A summary failure becomes `graphInputError`. While a required summary is pending the hook keeps the last resolved structural sets and starts no read, so a pending classification neither drops a successful graph nor restarts an identical read. It reports `graphInputsPending` true then, because the retained input is not a settled calculation input. A settled summary that omits a requested selected identity also becomes `graphInputError` with the fixed `Invalid request` message rather than guessing an activity flag.
- `graphKey` is `JSON.stringify(["prerequisites", root, includeRecommended, effectiveInferred, activeOnly, retainedInactive])`, where the retained array is the effective selected and completed union. No language, profile identity, basis, exclusion, mark, active selected identity or course ordering enters it.

`usePrerequisiteReport` in `web/src/features/prerequisites/usePrerequisiteReport.ts` owns the graph read through the app-level cache.

- A cache hit publishes the held report without a request.
- A resolved key that the cache does not hold starts one `AbortController` read, and the effect cleanup aborts it, so a changed key, a pane exit and an unmount all cancel the pending read.
- A fresh successful response is stored with `cache.put(report.dataset_identity, graphKey, report)` before it is published, and neither an error nor an aborted response enters the cache.
- A same-root read holds the last successful report while it runs, and a different root never shows it.
- Leaving the pane aborts a pending read and does not delete successful entries, so reopening the pane or switching back to a held structural input shows the report again without a request.
- `ready` is true only when the pane is active, the root has no pending classification and no input error, the graph key is resolved, and the settled result belongs to that exact key and root. A held same-root report while changed structural inputs load is not ready.

`useMinimumRoute(inputs, report, graphReady)` in `web/src/features/prerequisites/route/useMinimumRoute.ts` owns the explicit local calculation, and only `find` starts a worker.

- The route key is `JSON.stringify(["minimum-route", report.dataset_identity, inputs.graphKey, inputs.key, report.max_compact_nodes])`, and it is null unless the pane is active, the graph is ready, a report is held and the request exists.
- `find` returns when the route key, the request or the report is null, and when the cache identity differs from the report's dataset identity. It aborts a previous controller, reads the cache under the route key, and installs a held successful outcome without starting a worker. A worker result or error that arrives after its calculation was aborted or replaced, or after the route key or the report changed, is discarded. A result is also discarded when the cache identity no longer matches the report's dataset identity.
- On a miss it calls `withLiveInputs(report.solver, request)` for the shallow structure copy and the selected or completed basis, passes the report's allocation limit, and calls `calculateRouteInWorker` with the controller's signal. The held report and its structure tables are never mutated.
- A settled worker result is accepted only when its signal is not aborted, its controller is the current one, its route key and report reference are current, and the cache still holds the report's dataset identity. The hook stores the outcome with `cache.put` before it publishes it, including a no-solution or approximation-failed outcome, and stores no exception or aborted work.
- `clear` aborts, drops the controller ref and writes the empty route state, and it leaves successful cache values in place.
- An effect runs `discard` on a changed route key, a replaced report and unmount, so changed inputs, readiness loss, a pane exit and a new report abort the worker and clear the visible route.
- The returned session is withheld unless the route key is current, the held report is the current one and the cache identity matches, which prevents a result from showing against inputs that have moved on before the cleanup runs.
- `setExpanded` toggles the row disclosure. Neither the route hook nor the graph hook writes to the store. The visible route stays transient, and returning to earlier inputs never restores it without another explicit click.

## The solver modules

The solver is the pure TypeScript under `web/src/solver/` that evaluates a prerequisite solver structure. It contains the zero-suppressed family core, the shared piece fold, the satisfaction session and the complete minimum-new-credit route search. The route search covers the exact search, the Active-only module shortfall and the scalar approximation that follows an exact attempt past the configured allocation limit. The modules import nothing from React or the page. The graph tab imports the satisfaction evaluator through `web/src/features/prerequisites/graph/localState.ts`, and the route hook imports the solver through the browser worker.

`web/src/features/prerequisites/route/worker.ts` runs one solver request in a disposable browser worker, and `workerClient.ts` creates one worker per uncached explicit click. The hook in `useMinimumRoute.ts` owns the transient result, the shared cache and the cancellation of obsolete work.

`web/src/solver/request.ts` dispatches one machine solver request to the route solver. `web/src/solver/cli.ts` reads one such request from standard input and writes its result, and the machine route command runs it through Node. The browser evaluates the drawing's box states directly, so there is no node-state operation on that dispatcher.

The tests in `web/src/solver/` run the modules on structures the server wrote. The Python exporters under `tests/prerequisite/` write those structures from the real builder, and [Solver fixtures](/docs/testing/solver-fixtures.md) owns the seven files and their regeneration commands. The graph report carries no computed box states.

## The graph model

`buildGraphModel(report, language, nodeStates)` in `web/src/features/prerequisites/graph/model.ts` maps the report and one state array to `ModelNode` and `ModelEdge` arrays and a `rootId`. Node kinds are `course`, `module`, `connector` and `ignored`, and the footprint of each comes from `NODE_SIZES` in `web/src/features/prerequisites/graph/sizes.ts`: `course` 210 by 104, `module` 210 by 100, `junction` 54 by 28, `label` 132 by 28 and `constraint` 150 by 64. A connector takes the constraint size for `cardinality`, `credits`, `course_count` and `opaque_credits`, the junction size for `and` and `or`, and the label size otherwise. `markable` is true for a module node and for a numeric connector.

A `ModelNode` carries a nullable `markKey`, the node's own display identity when the server marks the box, so one saved key drives every calculation piece behind it. Its `state` is the `GraphNodeState` the pane computed for the same `node_id`. No client-side aggregation across source keys exists. A saved box key is fixed request input: it never changes a fold or a display identity, and an undrawn key is inert until the same identity returns. A course node is never markable. `ModelEdge` carries the server's `edge_id`, its member-ID list and its `inferred_only` flag.

`connectorLabel` renders the `and`, `or`, `cardinality`, `credits`, `course_count`, `opaque_credits` and `internal_requirement` kinds through `uiText`, and the `unresolved` kind through `reasonText` on its `reason`, or on its own kind token when that is null. `range` collapses a minimum and maximum pair into the `min+`, `≤max` and `a–b` forms. A connector subtitle comes from `diagnosticText` with its located reason and detail, or from `reasonText` for a reason without a detail. An `internal_requirement` connector carries `members`, the course summaries whose identities are in `member_group_ids`. Node state facts are indexed by `node_id`. A course's completion and exclusion and a module or numeric node's live manual completion and exclusion are read from the profile state, so a mark changes with its control.

The server supplies one connection per endpoint pair. `ModelEdge.id` is the server's `edge_id`, and it carries the server's `member_ids` and `inferred_only` flag plus the first-seen index of its source node for the layout hue. Route lighting tests membership in `path.lit_members`, never a re-evaluated selection. An unresolved course or module reference or a missing member course raises an error naming the display node and the missing identity, and a display with no root course node raises an error naming the solver root, instead of drawing a partial graph.

`connectionChain(model, nodeId)` answers a hover or an open panel with two independent directional walks from the requested node. The parent walk follows a connection only into its source and the child walk only into its target, each walk continues through every non-course box, and each stops at a course. A course highlight therefore holds its nearest course parents on every incoming branch and its nearest course children on every outgoing branch, and a box highlight holds its nearest course boundaries on both sides. A connection beyond a course boundary, such as a sibling behind a shared parent, is not lit.

`evaluateGraphNodeStates(report, request)` in `web/src/features/prerequisites/graph/localState.ts` is the one local-state entry. It returns an empty array for a refused display. Otherwise it calls `withLiveInputs(report.solver, request)` in `web/src/solver/structure.ts` for the shallow structure copy and the basis, and calls `evaluateNodeStates` with the display nodes and the live completed set. Every solver structure table is shared by reference and the cached report is unchanged.

## Layout thread

`web/src/features/prerequisites/graph/elk.ts` creates one lazy `ELK` instance whose `workerFactory` returns the bundled `elkjs` layout thread, and `layoutWithElk` calls its `layout`, so every layout runs off the main thread. `layoutGraph` in `web/src/features/prerequisites/graph/layout.ts` sends each model node as a child with its footprint and each model edge as an edge, with `elk.algorithm` `layered`, `elk.direction` `DOWN`, `elk.edgeRouting` `ORTHOGONAL`, and the spacing values in `SPACING`: node to node 40, layer to layer 80, edge to node 24 and edge to edge 14.

The result is read into a node map of positions and sizes and an edge map of point lists, each list being the first section's start point, bend points and end point. The root position is then subtracted from every node and every point, so the root sits at the origin and a structure change never shifts the drawing under the viewport.

`web/src/shared/viewport.ts` declares both app breakpoints: `PHONE_SHELL_QUERY` at 760 px for the shell and `PHONE_CONTENT_QUERY` at 680 px for the tab content. The shared `useMediaQuery` hook in `web/src/shared/useMediaQuery.ts` reads either one. The shell's swipe ring reads the shell query once through the hook, and the prerequisite pane and the graph node sizes read the content query through the hook, as do the Search and Discover panes. The same module exports `OVERLAY_SELECTORS`, the shared overlay vocabulary that the swipe ring and the phone bottom bar read.

`usePhoneGraphSizes` in `web/src/features/prerequisites/graph/usePhoneGraphSizes.ts` owns the phone footprint. It reads the phone match through `useMediaQuery(PHONE_CONTENT_QUERY)`, and it holds one measurement map for the content key. The key holds the root identity, the language and each node's identity, kind, title and subtitle, so a mark, the basis, the route and the viewport transform leave the key unchanged.

`useGraphNodeHeight` observes one course or module root with a border-box `ResizeObserver` and reports `Math.ceil` of its block size. The observed element sits below the React Flow viewport transform, so its size is the element's own CSS height at any zoom. A content-key change reconnects every mounted observer, so an equal height also enters the map. The observer disconnects on a mode, identity, callback or unmount change.

`GraphCanvas` lays out the report with the `NODE_SIZES` footprints first. On a phone it replaces the height of each course and module node with its measured height when one exists and uses the base width and every other node and edge value. Desktop uses the model exactly. The first layout of a root therefore uses the base footprint, and a content or language change produces another layout once the measurement arrives.

`useGraphLayout` in `web/src/features/prerequisites/graph/useGraphLayout.ts` keys its work on a signature of the root identity, each node identity and kind, each node's footprint width and height, and each edge identity. A change to node states with every footprint equal leaves the signature identical, so the held layout is returned with the model and no layout runs. The pane recomputes the states, the model rebinds them, and the viewport stays where it is. A changed footprint produces another layout. A changed signature holds the previous graph while the root identity matches, clears it for a different root, and drops a settled layout whose effect was cleaned up.

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

`GraphCanvas` holds the hover, open-menu and open-panel identities, so only one of them highlights at a time. Nodes and edges are rebuilt from the animated frame on every render and offset by 40 and 30 units, and each node supplies `measured` with its fixed footprint so React Flow keeps the handle bounds of a controlled node. Each course and module node also carries `--graph-node-min-height` from the matching `NODE_SIZES` value, so the phone stylesheet uses the base footprint as a minimum while the box grows with wrapped content. `CourseNode` attaches the observer to its `.graph-course` root and `ModuleNode` to its `.graph-module` root. `interactionDisabled` is set while a node is exiting or a layout runs, and the course, module and connector node components render `inert` with that flag.

The rendering state on the canvas:

- `routing` is true when a route result exists or a route calculation is pending. Every node and edge the route lights holds full opacity and everything else is dimmed, and a course node that only the selected basis covers carries `selectedOnly`.
- `lit` comes from `buildRouteView`. `lit.levels` supplies the `--dl` style that spreads the lighting from the root outward.
- Without a route, a hovered or open node lights its `connectionChain` instead.
- A node that an `approximation_failed` result marks carries the `timeout` flag, and an inactive course node renders at reduced opacity.
- `PrerequisiteEdge` draws the ELK point list as a polyline with a rounded corner per bend, plus a dark halo edge and the parent hue as the stroke. It maps the model's `inferred` flag to an `inferred` class on both paths, and `graph.css` dashes only the foreground path through `.react-flow__edge-path.prereq-edge.inferred.line`, so a connection whose members are all inferred is dashed and one with any official member is solid. The component carries the fade opacity and the lighting delay on its own group, because React Flow hands an edge's style to the edge component rather than to its wrapper group.

`centerRoot` sets the viewport so the root sits at the top of the panel, without animation on the first layout of a root and with a 450 ms animation from **Recenter** while the operating system asks for normal motion, and with no animation under the reduced-motion preference. The root sits 30 px below the panel top on desktop and 72 px below it on a phone, clear of the floating controls. The desktop **Recenter** control calls the function through `recenterRef`, and the phone rail calls the same function beside Zoom in and Zoom out, which call the drawing's own zoom and keep its 0.15 to 2.2 range. The open panel closes when a layout starts, and the open menu or panel closes when the node it names leaves the model. Dragging, connecting, selecting and keyboard focus are all off.

`CourseNode` renders a `CourseTile` with the shared course menu and with **Complete** and **Exclude** actions. **Complete** goes through `useCourseCompletion`, the shared completion hook, and **Exclude** calls `toggleExcludedCourse`. It reads its completion, exclusion, and selected-only basis mark from the live profile state. `ModuleNode` and a numeric `ConnectorNode` render **Complete** and **Exclude** actions that call `toggleNodeCompleted` and `toggleNodeExcluded` with the node's `markKey`. Their live marks read that one saved box key, with exclusion precedence. The module's **fulfilled** mark is the aggregated `completed_by_courses` fact. Opening a module or an internal-requirement connector sets the panel identity, and `MemberPanel` lists its `members` with the shared course rows and the module add control.

## The route projection

`web/src/features/prerequisites/route/route.ts` projects a returned `PrerequisitePath` against the report and the model.

`buildRouteSummary(graph, path, language)`:

- The browser does not re-select the route's occurrences. An edge lights when any of its server-supplied member IDs is in `path.lit_members`.
- Rows exist for the `exact`, `approximate` and `shortfall` states: every `new_courses` entry first as uncovered, then every `covered_courses` entry that is not new, as covered. The covered set is the server's witness set, independent of the drawing allowance.
- `newCredits` comes from `total_new_credits` and `fullCredits` adds the credits of the covered course nodes. A null total means no credits.
- `problems` are grouped by drawn node, reason and detail for presentation only, and each carries the title of its `node_id` resolved from the display and course summaries.
- `shortfalls` resolve a module or connector title through their `node_id` and read as a course count or a credit comparison.
- `missingCourseIds` is the new course identities, and `blockedCourseIds` and `blockedNodeTitles` come from `blocked_excluded_group_ids` and `blocked_excluded_node_keys`.

`projectRoute(structure, drawing)` in `web/src/solver/route-projection.ts` runs inside the solver and turns one chosen drawing derivation into the route's lit members and selected nodes. It indexes the projected contexts and relationship members, starts from the root context paired with the drawing root, and collects each visited context's member IDs. It follows only the child slots the selected drawing node carries, pairs each with that slot's child context, and memoizes by context identity and drawing node identity, so one shared selected child visits every context that selects it. A missing context, member or child slot and a mismatched owner or piece raise an error. The selected nodes are the root plus the source and target endpoints of the lit members. An unchosen alternative, including an equal-cost one, contributes no member.

`buildRouteView` then lights those identities. The worker, the Node host and the renderer read the same result fields, so no renderer component, worker module or page applies a second selection rule.

`buildRouteView(path, model, summary)` adds the lit sets: the root and the returned `selected_nodes` identities for a route that exists, and for `no_solution` and `unresolved` the problem and blocked node IDs. The solver derives the route's endpoints. An `approximation_failed` result lights the root alone. `lit.levels` is a breadth-first distance from the root over the model edges, and the canvas turns it into the lighting delay.

`RoutePanel` renders the outcome label, the note, the credit header, the rows and the add control. A course row is keyed `${group_id}-${covered}-${index}` and an unexpandable row `${work_key}-${index}`, so two entries of one course in one list stay distinct. `RouteControl` toggles between `find` and `clear`, and it is disabled while the graph is not ready or a route calculation runs, unless a result is already shown so that the control can clear it.

## The refused-drawing boundary

`PrerequisitesPane` is the early boundary of the drawing. It renders the empty state with no root, the loading skeleton while `graphLoading && !report`, `ErrorNotice` when the report read or the activity classification failed, `PrerequisiteGraph` when `report.drawing.allowed` is true, and `RefusedGraph` otherwise. For the allowed drawing it memoizes `evaluateGraphNodeStates(report, inputs.request)` from the held report and the live snapshot and passes the result as `nodeStates`. A refused drawing computes none. `RefusedGraph` renders the same `RouteControl` and `RoutePanel` in the same stage layout, so the explicit route operation works while the drawing is refused. The pane computes the route summary with `useMemo` from the report and the route result and passes it to both branches.

## Graph actions and stored state

`web/src/features/prerequisites/actions.ts` exports `setPrerequisitesRoot`, `setPrerequisitesQuery`, `setPrerequisitesActiveOnly`, `setPrerequisitesBasis`, `setIncludeRecommended`, `setIncludeInferred`, `toggleExcludedCourse`, `toggleNodeCompleted` and `toggleNodeExcluded`. Every writer goes through the local `update` helper and `store.updateCurrent`. `toggleNodeCompleted` and `toggleNodeExcluded` take one `markKey` and change exactly that saved box key in one store update. Adding a mark removes the same key from the opposite list. Other keys and every course set are untouched. `web/src/features/prerequisites/state.ts` holds `PrerequisitesState` and `initialPrerequisitesState()`, and `validateProfileState` in `web/src/state/validation.ts` projects a saved slice onto those fields.

## Tests

| File | Covers |
|---|---|
| `web/src/features/prerequisites/actions.test.ts` | One box-key mark toggled in one update, the opposite mark cleared, the shared course sets left empty, and an undrawn current key retained |
| `web/src/features/prerequisites/graph/model.test.ts` | The nearest course parents and children of a course highlight, and the nearest course boundaries of a box highlight, with no grandparent, grandchild or sibling |
| `web/src/solver/satisfaction.test.ts` | The local state entry over a server-built structure, with live marks and exclusions and the held solver left unchanged |
| `web/src/features/prerequisites/route/route.test.ts` | Returned member lighting, one edge per server connection, the new plus covered credit total with and without a display, and the rows, problems, shortfalls and missing identities of every path state |
| `web/src/solver/route-contracts.test.ts` | One compiled structure whose two modules share a hidden member, where the selected connection endpoints carry the lit nodes and the unchosen module box is not lit, and the exact occurrence tests: one coherent equal-cost module occurrence and module-local choices under different parent bounds |
| `web/src/solver/route-approximation.test.ts` | The size-limited restart and one coherent equal-cost module occurrence in an approximate result |

## Where a change belongs

- A report field the drawing should show belongs in `buildGraphModel` or `connectorLabel` in `model.ts`, together with the renderer component that draws it.
- A node footprint belongs in `NODE_SIZES`, and a spacing or routing value belongs in `SPACING` and in the `layoutOptions` of `layoutGraph`.
- A phone node height belongs in `usePhoneGraphSizes` and the node's own root ref, and the base minimum stays in `NODE_SIZES`.
- A viewport breakpoint belongs in `web/src/shared/viewport.ts`. A breakpoint value that drives rendering reads it through `useMediaQuery`, and a scroll or input effect that needs the current match at event time reads the query through `matchMedia`, as the scroll-hide effect in `PhoneTabBar.tsx` reads the shell query.
- A transition belongs in `useAnimatedGraph`, and the layout reuse rule belongs in the signature of `useGraphLayout`.
- A route presentation rule belongs in `route.ts`, and the row, note or control that shows it belongs in `RoutePanel` or `RouteControl`.
- A stored prerequisite setting belongs in `state.ts`, in `validateProfileState` in `web/src/state/validation.ts`, and in the action that writes it.
