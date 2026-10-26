# Minimum route solver

The solver folds the calculation pieces of one solver structure into the exact minimum-new-credit route, with one greedy restart after an oversized exact attempt.

## Entry point and result types

`calculateMinimumNewCredits(structure, basisGroupIds, maxCompactNodes = null)` in `web/src/solver/route.ts` is the public entry point. It throws for a non-positive `maxCompactNodes`, calls `evaluateSatisfaction(structure, basisGroupIds)` once, and returns one `MinimumRoute`. The chosen basis supplies the zero-cost course set. A completed node mark enters separately: `withLiveInputs` writes the profile's `completed_node_keys` onto the structure, and `nodeOverride` registers each marked support as one attested witness at no new cost. An excluded node mark returns the empty frontier with one `excluded_node` problem.

`MinimumRoute` extends the wire `PrerequisitePath` with `satisfaction` (`SatisfactionEvaluation`), `blockers` (`PathBlocker`) and `inferred_coverage`. The wire path carries `state` (`PrerequisitePathState`), `new_courses` (`PathCourse`, each holding a `CourseSummary` and its sorted drawn `node_ids`), `total_new_credits` (compact credit text or `null`), `shortfalls` (`PathShortfall`), `blocked_excluded_group_ids`, `new_opaque_work` (`PathOpaqueWork` with `work_key`, `credits_min` and `node_ids`), `selected_nodes`, `lit_members`, `covered_courses`, `facts`, `problems` (`PathProblem` with `node_id`, `support_id` and `fact_id`) and `blocked_excluded_node_keys`. `SatisfactionEvaluation` carries the root identity, the two visibility inputs, the activity scope, the sorted basis identities and the requirements state.

`PrerequisitePathState` is the six-valued union (`exact`, `approximate`, `approximation_failed`, `unresolved`, `no_solution`, `shortfall`). `PathBlocker.kind` separates `unresolved_requirement` from `course_cycle`, and `PathShortfall.kind` separates `all_mandatory`, `cardinality`, `credits` and `course_count`. Count families fill `required_count`, `achieved_count` and `count_deficit`, and `credits` fills the three credit fields.

`calculateMinimumNewCredits` decides the state. It evaluates satisfaction once, and an excluded graph root then returns a `no_solution` result with one `excluded_node` root problem before `solvePath` runs. A satisfied requirement returns `exactZero`. Otherwise `solvePath` returns `exact`, `unresolved`, `no_solution` or `shortfall`, and the `PathSizeLimitExceeded` escape returns `approximate` or `approximation_failed` through `solveGreedyPath`.

## Candidates, frontier and the support DAG

`PathCandidate` in `web/src/solver/route-candidate.ts` is the value one node fold carries. `witnessGroupIds` are the canonical course witnesses that enclosing credit and count nodes measure. `newGroupIds` is the complete recursively required not-basis course closure and is the sole course cost set. `newOpaqueWorkIds` is the opaque work closure, `witnessNonCourseIds` holds typed `(kind, identity)` pairs for opaque and attested witnesses, `evidence` is the set of `(kind, identity, support_id)` labels, and `shortfalls` is the branch's module deficits.

`PathFrontier` in `web/src/solver/route-frontier.ts` pairs one `PathFamilies` owner with `partitions`, a map from the sorted shortfall list to a `KeyedPartition`. Each partition holds one support handle, one provenance trace index and one drawing annotation, so shortfall identities are part of the partition key and are never merged across keys. `neutral`, `empty`, `union`, `join`, `filter`, `partitionUnknown`, `projectWitnesses`, `withoutEmptyModuleMarker`, `attachShortfall` and `restrict` are its operations. `withDrawingSlot` and `withDrawingNode` add one native child slot or one native node boundary without a family operation.

`PathFamilies` in `web/src/solver/route-families.ts` subclasses `Families` in `web/src/solver/families.ts`. A variable is a tagged `(first occurrence rank, kind, identity, role)` tuple. `pathGroupOrder(structure)` assigns the rank from the first-visit native piece order, and an expanded-course head precedes its descendants because it is the first ordered child. The `kind` is `course`, `opaque` or `attested`, and the `role` is `witness` or `new`, so a canonical course, an opaque block and a manual attested completion are distinct, and a measured witness is distinct from the cost set. The rank fixes one fold variable order and never enters a public tie.

The inherited `Families` core supplies `singleton`, `union`, `join`, `filter`, `project`, `splitByPredicate`, `removeEmpty`, `intersection`, `restrictVariable`, `joinPreimage`, `projectPreimage`, `contains` and `maxWeightStrictlyBelow`, so no fold materializes a member set. Zero suppression in the core collapses a zero high branch away, which makes the DAG compact. `PathFamilies` adds the weight functions `creditWeight`, `countWeight`, `newCreditWeight`, `inactiveNewWeight`, `isUnknownCredit` and `isUnknownCount`, the attested registration `registerAttested`, and the exact folds `minimumNewCredits`, `minimumInactiveNewCount` and `bestSupport`. The size check raises `PathSizeLimitExceeded` when the interned node count plus the trace count first exceeds `maxCompactNodes`.

The trace records one operation of the transient provenance DAG with its input indices, an optional typed label and the drawing annotation of each input. `reconstructEvidence` walks the trace backwards from the selected member and propagates the allowed family through `intersection`, `joinPreimage` and `projectPreimage`, so every valid derivation's labels are unioned and a rejected route leaks nothing. The unioned evidence feeds the candidate keys and the public facts, so the drawing scope never narrows the evidence.

Pruning is exact. Zero suppression merges equal families, the inclusive-bound `filter` drops only members outside the bounds, and `project` removes only witness distinctions. A cost or inactivity fold then restricts one partition to its minimum support, and the identity walk selects inside that restricted family, so no member is compared against another by an approximation.

## Node folds

`PathEvaluator` extends `PieceEvaluator` in `web/src/solver/traversal.ts`. The shared dispatcher applies `nodeOverride` first, then dispatches by explicit piece kind under its owner course. A scoped calculation support is `s:<owner>:p:<piece>`. The same piece is folded once per owner. The solver folds each node kind as follows.

- `and`: `combineFrontiers` joins the child candidate frontiers from `PathFrontier.neutral`.
- `or` and `course_alternatives`: unions the child candidate frontiers per shortfall key and ORs their unresolved flags.
- `cardinality`: `rows[count]` holds the family selecting exactly `count` child positions, and the result unions every count from `require_min` through `min(require_max or len(children), len(children))`. The count is the number of selected child positions.
- `credits` and `course_count`: `partitionUnknown` splits the child family with `isUnknownCredit` or `isUnknownCount`, `filter` returns the known members inside the inclusive bounds with `creditWeight` or `countWeight`, and an unknown member becomes a located unresolved problem instead of emptying the known alternatives.
- `course`: an eligible leaf contributes a witness variable and, only outside the basis, a new variable. An ineligible leaf yields no candidate and one located problem.
- `opaque_credits`: a zero source minimum is the neutral frontier, and a positive minimum contributes one witness and one new-charge identity keyed by `work_key`, so repeated identical work is charged once.
- `module_block`: folds transparently over its child under the same owner.
- `unresolved`: returns no candidates, sets `has_unresolved_alternative`, and emits one `PathBlocker`.

## Expanded courses and module shortfalls

The dispatcher sends `expanded_course` to its own `expandedCourse` fold before the general child fold. Its head switches the owner for the descendant slot. An eligible head contributes a witness and one new charge when it is outside the basis. A head in the basis returns the head frontier and never evaluates its descendants. Otherwise the descendant frontier is folded and `projectWitnesses` removes the descendant witnesses before the head frontier joins it, so the descendant charges, evidence and deficits are part of the joined support while only the head is measured.

Module shortfall reduction runs only under `active_only` and only on the primary pass. The all-course diagnostic re-evaluates the same node with every represented course activity-eligible and reduction disabled, which is the proof that activity scope alone caused the failure. The activity-fill check requires both that diagnostic and a real reduction of the node under the basis scope. The module-position classifier marks each child position, the conjunction reduction records one `all_mandatory` deficit per activity-empty position, the cardinality reduction reports the largest selectable count below `require_min`, and the bounded reduction reports the greatest reachable witness total or count strictly below the node's minimum through `maxWeightStrictlyBelow`. A position that failed for any other reason yields no group, so the rule is unreducible and its strict outcome holds.

## Cycle paths and drawn lighting

`cycleSupportPaths` keeps one shortest record per `(use, owner)` context. The path cost counts course transitions, and the lexicographic tuple of child-slot indices traversed from the root use is the deterministic tie carrier. The record retains one valid shortest course path from the root to each cycle-closing support, so a blocker never lists a reaching prefix as part of a calculation identity.

`exactResult` passes the chosen drawing derivation to `projectRoute`, which walks the projected context table with that derivation and lights the members its selected occurrences own. The drawn route nodes are the root plus the source and target endpoints of those lit members. The selected occurrences and the public facts are independent results: the facts keep every feasible label, and the drawing keeps one derivation.

## Chosen drawing derivation

`web/src/solver/route-derivation.ts` owns the request-local drawing types. A `DrawingNode` holds one local integer identity, the native owner and piece, and its child slots. `DrawingNodePool.node` sorts children by native slot and interns equal `(owner, piece, child slots)` content within one calculation, so a shared occurrence keeps one node and no parent pointer or reaching path is stored. `DrawingTraceRef` annotates an operation trace: a plain reference reads the same trace the evidence walk reads, a node reference wraps the child-slot fragments below it into one semantic node, and a slot reference places one semantic node in its native child slot.

`PathFamilies.reconstructDrawing` normalizes the selected member to unique path variables in path order, requires the outermost fragment to be a node and returns that node. `PathFamilies.selectDrawing` owns the recursive memo. It keys every fragment by reference identity and the ordered member keys, and it caches neutral, node and child-slot fragments. A pair evaluates once through `selectDrawingUncached`, and every nested node, slot, union, identity, join and projection selection returns through `selectDrawing`, so one shared reference and member pair expands once before `DrawingNodePool` interns the node it produces.

A union takes the first stored input whose support contains the exact member, an identity restriction follows its one input, a join uses `firstJoinPair`, and a projection uses `firstProjectPreimage`. Both selectors read family handles only and never construct, union, join or project a family. The join selector tries the low/high, high/low and high/high branches in that order and allows a variable in both operands, so an overlapping pair is found without subtracting one operand from the member. The projection selector tries a removed witness as absent and then present, restores the present witness into the returned member, and follows a retained variable only when it matches the next target variable. A member with no feasible preimage and an unknown operation raise an error.

Drawing annotations allocate no family node and no trace node. Every operation trace records its inputs once, the size check counts only interned family nodes plus trace nodes, and the exact-to-greedy transition depends only on that size check.

`GreedyPathEvaluator` builds the same node shape from its existing choices. A leaf creates a childless frame for its native owner and piece, and `combine` places each input route in a supplied native slot, defaulting to input order. An `or` node passes the chosen child's original native index, `cardinality` passes the selected positions' native indices, and an expanded course passes head slot zero and descendant slot one. A module block and a numeric bound wrap their chosen child in a module or bound frame at slot zero. The cardinality extension rebuilds the operation frame from its selected positions' native indices, and the recursive child replacement reuses the native slots of the frame that carries the route's own owner and piece. Both re-intern any transparent module prefix through the pool. The drawing field enters no candidate evidence, selection key, scalar cost, validity check or memo key, so a greedy choice and its outcome depend only on the route fields the fold already compares.

`projectRoute(structure, drawing)` indexes the projected contexts and relationship members, requires the native root context, and starts from the pair of that context and the drawing root. Each visited pair collects the context's member IDs and follows only the child slots the selected drawing node carries, pairing each with that slot's child context. The walk memoizes by context identity and drawing node identity, so one selected child shared by several contexts visits every pair. A missing context, member or child slot and a mismatched owner or piece raise an error. The union of the collected members is the one lit set, and the selected nodes are the root plus the endpoints of those members. An unchosen alternative contributes no member even when its support occurs in the unioned evidence.

## Allocation limit and the greedy restart

The size check compares the interned node count plus the trace count with the configured limit and raises on the first excess. Only the exact attempt is bounded by the configured limit, and the greedy restart has no allocation cap. `calculateMinimumNewCredits` catches `PathSizeLimitExceeded`, runs `solveGreedyPath` once, and re-raises when no limit was set, so the exact attempt is bounded and the greedy restart is not.

`GreedyPathEvaluator` is a second `PieceEvaluator` that derives one scalar `GreedyRoute` per piece without building families. `or` chooses the viable child that minimizes `candidateSelectionKey` under the route's scalar cost. `cardinality` sorts the viable positions by that key plus their index, takes the first `require_min` as the selection, and takes the next positions up to the maximum as extension positions. `credits` and `course_count` extend the chosen prefix while its witness measure is below the lower bound, and never exceed a source maximum. Extensions come from the chosen derivation only, so a discarded OR branch is never revisited. The validity check certifies every guard, position count and nested numeric bound, and a route that fails it is discarded.

A valid greedy route becomes an `approximate` result with the same result types as an exact one. A missing or invalid route calls `approximationFailed`, which returns `approximation_failed`, no route and no total, and one root problem whose reason is `search_too_large`.

[Minimum-credit routes](/docs/experiments/graph-and-route-algorithms/minimum-credit-routes.md#the-size-limit-and-the-restart) records the calibration of the limit and the corrected approximate totals.

## Exclusion blocks and located problems

The primary fold threads three collectors. `blocked_excluded_group_ids` collects the canonical course group IDs that the activity and exclusion check denied to the calculation. `blocked_excluded_node_keys` collects the scoped supports whose node mark denied them, and the result maps them to the drawn node IDs their bindings carry. One `PathProblem` is appended per local failure, expanded once per distinct provenance fact bound to the support, with its drawn `node_id`, `support_id`, `fact_id`, state, reason and optional referenced group. The reduction and all-course diagnostic passes and the greedy evaluator run with the collectors disabled or separate, so only the primary fold's failures reach the result. `mergeShortfalls` and `mergeBlockers` deduplicate and sort the two record families.

## Tie order

Selection has three stages, and the variable rank appears in none of them.

1. `PathFamilies.bestSupport` folds the least `newCreditWeight` total over one partition, restricts the family to that exact total, folds the least `inactiveNewWeight` count, and then walks the restricted family to fix the sorted tuple of new opaque work identities, new course identities, course witness identities and non-course witness identities. `supportKey` orders the resulting `BestSupport`.
2. `frontierCandidate` selects the partitions whose `supportKey` is smallest, reconstructs evidence for those contenders only, and compares them by `candidateSelectionKey`: total new credits, then the count of distinct inactive new courses, then the sorted new opaque work identities, new course identities, witness course identities, non-course witness identities and evidence labels.
3. `candidateSortKey` breaks a tie left by the earlier stages with the sorted witness set, new set, opaque set, non-course witness set, evidence and shortfall records.

`buildNewCourses` and `buildOpaqueWork` then turn the winning candidate into the result rows, and `exactResult` sums the course and opaque credit minima into `total_new_credits`.

## Hosts and command wiring

The browser host is `web/src/features/prerequisites/route/worker.ts`. It receives one `SolverRequest`, calls `runRequest` in `web/src/solver/request.ts` once, and posts the returned `MinimumRoute`. `workerClient.ts` creates one worker per uncached explicit calculation, posts once, and settles on the result, its error or cancellation. The worker imports no React, DOM, profile, configuration, HTTP or Node CLI module.

The machine host is `run_minimum_route_command(target_code, *, completed_codes, selected_codes, excluded_codes, include_recommended, include_inferred, active_only, basis, completed_node_keys, excluded_node_keys)` in `src/course_explorer/prerequisite/commands.py`. It returns the JSON object the bundled solver wrote.

1. `_prepare_prerequisite_command` resolves the target, selected, completed and excluded inputs through `CourseLookupService.resolve_courses`, and rejects a completed course outside a non-empty selected set. It also rejects a completed or excluded node key that is not a graph-box key of the form `s:<owner>:d:<24 hex>`, and sorts and deduplicates each validated key list. The shape check reads the key string alone, and a well-formed key that names no drawn box in the compiled structure changes nothing.
2. It chooses the calculation basis: the completed set, or the effective selected set when `basis="selected"`. Without selected input the effective selected set is the completed set. This one set is the route's sole calculation basis.
3. It compiles one solver structure through `PrerequisiteGraphCompiler.compile_structure(...)` and projects it once with `include_display=False`, disposes the database context, and returns one `_PrerequisiteCommandContext`.
4. `_node_route` sends `{"operation": "route", structure, basis_group_ids, max_compact_nodes}` to `node web/.solver-cli/cli.js` through `_run_node_solver` and returns the parsed result. A missing bundle raises `FileNotFoundError` naming `npm --prefix web run solver:build`, and a nonzero exit or unparsable output raises `RuntimeError` with standard error.

`scripts/prerequisites.py --route` prints that JSON. The graph operation `run_prerequisite_command` shares the same preparation in points one to three and returns the drawing report instead. The web server exposes no route endpoint and starts no solver process.

`SearchSettings.prerequisite_path_max_compact_nodes` in `src/course_explorer/config.py` reads `PREREQUISITE_PATH_MAX_COMPACT_NODES` from `config/search.toml` and requires a value greater than 0. The web graph route reports the value as `max_compact_nodes`, and the machine command reads it for the same solver.

## Tests

| File | Covers |
|---|---|
| `web/src/solver/route-minimum.test.ts` | The global course union and the new-credit objective over the local course count, expanded courses and directional substitutions, a logical composed AND that charges every incomplete child, numeric wrappers that measure witnesses while the total adds the closure, unresolved cycles and no-solution, a large nested choice rule, repeated opaque work charged once, and the unknown-measure bounds. |
| `web/src/solver/route-contracts.test.ts` | Coverage fidelity, the deterministic ties over equal credits, activity, and canonical identity, a basis head satisfying its expanded prerequisites at zero cost, zero-credit ties independent of the source child order, projected evidence reconstruction, the activity tie over distinct new courses, one coherent equal-cost module occurrence, and module-local choices under different parent bounds. |
| `web/src/solver/route-activity.test.ts` | Activity eligibility, an excluded branch beside another route, an excluded substitution member, and a descendant reused through a route that avoids its excluded head. |
| `web/src/solver/route-approximation.test.ts` | The size-limited restart, shared-prerequisite and repeated-opaque dedup in the greedy fold, prefix extension for numeric bounds, the `approximation_failed` contract, the greedy expanded head stopping at the basis, and the one coherent equal-cost module occurrence of an approximate result. |
| `web/src/solver/route-module-shortfall.test.ts` | The maximum active-only result and the exact deficit for each module rule family, including nested deficits. |
| `web/src/solver/route-module-failures.test.ts` | Shortfall is activity-only, and ordinary, impossible, upper-bound, unresolved, cyclic, and expanded-course failures hold their strict outcomes. |
| `web/src/solver/request.test.ts` | The one dispatcher over one written solver request. |
| `web/src/features/prerequisites/route/useMinimumRoute.test.ts` | The explicit worker calculation, the shared cache hit on a repeat click, and the discard of obsolete work on an input, readiness, report, dataset, pane or unmount change. |
| `tests/prerequisite/test_prerequisite_command.py` | The two basis selections, root exclusion, the drawing refusal that is independent of the route result, and the CLI contract over the Node command. |

The route as the app presents it is described in [Minimum route](/docs/backend/prerequisites/minimum-route.md).
