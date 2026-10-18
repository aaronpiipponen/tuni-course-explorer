# Minimum route solver

The solver folds one compiled prerequisite calculation tree into the exact minimum-new-credit route, with one bounded greedy restart for an oversized search.

## Entry point and result DTOs

`calculate_minimum_new_credits(tree, basis_group_ids, *, max_compact_nodes=None)` in `src/course_explorer/prerequisite/path.py` is the public entry point. It raises `ValueError` for a non-positive `max_compact_nodes`, calls `evaluate_prerequisite_satisfaction(tree, basis_group_ids)` once, and returns one `MinimumCreditPathEvaluation`. The chosen basis is the sole zero-cost set: no separate completed history reaches the solver.

`MinimumCreditPathEvaluation` carries `satisfaction` (`PrerequisiteSatisfactionEvaluation`), `state` (`PrerequisitePathState`), `new_courses` (`PrerequisitePathCourse`, each holding a `CourseSummary` and its sorted `occurrence_ids`), `total_new_credits` (`Decimal | None`), `blockers` (`PrerequisitePathBlocker`), `shortfalls` (`PrerequisiteModuleShortfall`), `inferred_coverage`, `blocked_excluded_group_ids`, `new_opaque_work` (`PrerequisitePathOpaqueWork` with `work_key`, `credits_min`, `occurrence_ids`), `selected_occurrence_ids`, `problems` (`PrerequisiteNodeProblem`), and `blocked_excluded_node_keys`. `PrerequisiteSatisfactionEvaluation` carries the root identity, the two visibility inputs, the activity scope, the sorted basis identities, and the requirements state.

`PrerequisitePathState` is the six-valued `StrEnum` (`exact`, `approximate`, `approximation_failed`, `unresolved`, `no_solution`, `shortfall`). `PrerequisitePathBlockerKind` separates `unresolved_requirement` from `course_cycle`, and `PrerequisiteModuleShortfallKind` separates `all_mandatory`, `cardinality`, `credits`, and `course_count`. Count families fill `required_count`, `achieved_count`, and `count_deficit`, and `credits` fills the three credit fields.

`calculate_minimum_new_credits` decides the state. An excluded graph root returns a `no_solution` result with one `excluded_node` root problem before any fold. A satisfied requirement returns `_exact_zero`. Otherwise `_solve_path` returns `exact`, `unresolved`, `no_solution`, or `shortfall`, and the `_PathSizeLimitExceeded` escape returns `approximate` or `approximation_failed` through `_solve_greedy_path`.

## Candidates, frontier and the support DAG

`_PathCandidate` is the frozen dataclass one node fold carries. `witness_group_ids` are the canonical course witnesses that enclosing credit and count nodes measure. `new_group_ids` is the complete recursively required not-basis course closure and is the sole course cost set. `new_opaque_work_ids` is the opaque work closure, `witness_non_course_ids` holds typed `(kind, identity)` pairs for opaque and attested witnesses, `evidence` is a `frozenset` of `(kind, identity, occurrence_id)` labels, and `shortfalls` is the branch's module deficits.

`_PathFrontier` pairs one `_PathFamilies` owner with `partitions`, a `dict[tuple[PrerequisiteModuleShortfall, ...], _PathPartition]`. Each `_PathPartition` holds one support handle and one provenance trace index, so shortfall identities are part of the partition key and are never merged across keys. `neutral`, `empty`, `union`, `join`, `filter`, `partition_unknown`, `project_witnesses`, `without_empty_module_marker`, `attach_shortfall`, and `restrict` are its operations.

`_PathFamilies` in `src/course_explorer/prerequisite/path.py` subclasses `_Families` in `src/course_explorer/prerequisite/_families.py`. A variable is a tagged `(first_occurrence_rank, kind, identity, role)` quadruple. `_path_group_order(tree.requirements)` assigns the rank from the authoritative expression's first course or opaque occurrence in depth-first order, and an expanded-course head precedes its descendants because it is the first ordered child. The `kind` is `course`, `opaque`, or `attested`, and the `role` is `witness` or `new`, so a canonical course, an opaque block, and a manual attested completion are distinct, and a measured witness is distinct from the cost set. The rank fixes one fold variable order and never enters a public tie.

The inherited `_Families` core supplies `singleton`, `union`, `join`, `filter`, `project`, `split_by_predicate`, `remove_empty`, `intersection`, `restrict_variable`, `join_preimage`, `project_preimage`, `contains`, and `max_weight_strictly_below`, so no fold materializes a member set. Zero suppression in `_make` collapses a `ZERO` high branch away, which makes the DAG compact. `_PathFamilies` adds the weight functions `credit_weight`, `count_weight`, `new_credit_weight`, `inactive_new_weight`, `is_unknown_credit`, and `is_unknown_count`, the attested registration `register_attested`, and the exact folds `minimum_new_credits`, `minimum_inactive_new_count`, and `best_support`. `_check_size` raises `_PathSizeLimitExceeded` when `len(self._nodes) + len(self._traces)` first exceeds `max_compact_nodes`.

`_PathTrace` records one operation of the transient provenance DAG with its input indices and an optional typed label. `reconstruct_evidence` walks the trace backwards from the selected member and propagates the allowed family through `intersection`, `join_preimage`, and `project_preimage`, so every valid derivation's labels are unioned and a rejected route leaks nothing.

Pruning is exact. Zero suppression merges equal families, the inclusive-bound `filter` drops only members outside the bounds, and `project` removes only witness distinctions. A cost or inactivity fold then restricts one partition to its minimum support, and the identity walk selects inside that restricted family, so no member is compared against another by an approximation.

## Node folds

`_PathEvaluator` is a frozen dataclass extending `ExpressionEvaluator` in `src/course_explorer/prerequisite/traversal.py`. The shared dispatcher applies `node_override` first, then dispatches by node type and computes a child occurrence identity as `f"{occurrence_id}.{index}"`. The solver folds each node kind as follows.

- `conjunction` (AND): `_combine_frontiers` joins the child candidate frontiers from `_PathFrontier.neutral`.
- `alternatives` (OR): unions the child candidate frontiers per shortfall key and ORs their unresolved flags.
- `cardinality`: `rows[count]` holds the family selecting exactly `count` child positions, and the result unions every count from `require_min` through `min(require_max or len(children), len(children))`. The count is the number of selected child positions.
- `bounded` (credit and course count): `partition_unknown` splits the child family with `is_unknown_credit` or `is_unknown_count`, `filter` returns the known members inside the inclusive bounds with `credit_weight` or `count_weight`, and an unknown member becomes a located unresolved problem instead of emptying the known alternatives.
- `course`: an eligible leaf contributes a witness variable and, only outside the basis, a new variable. An ineligible leaf yields no candidate and one located problem.
- `opaque_credits`: a zero source minimum is the neutral frontier, and a positive minimum contributes one witness and one new-charge identity keyed by `work_key`, so repeated identical work is charged once.
- `module_block`: folds transparently over its child at occurrence `f"{occurrence_id}.0"`.
- `unresolved`: returns no candidates, sets `has_unresolved_alternative`, and emits one `PrerequisitePathBlocker`.

## Expanded courses and module shortfalls

`expanded_course` handles the compiler's `EXPANDED_COURSE` composed AND. An eligible head contributes a witness and one new charge when it is outside the basis. A head in the basis returns the head frontier and never evaluates its descendants. Otherwise the descendant frontier is folded and `project_witnesses` removes the descendant witnesses before the head frontier joins it, so the descendant charges, evidence, and deficits are part of the joined support while only the head is measured.

Module shortfall reduction runs only under `active_only` and only on the primary pass. `_all_course_diagnostic_allows_shortfall` re-evaluates the same node with every represented course activity-eligible and reduction disabled, which is the proof that activity scope alone caused the failure. `_activity_fills_module_position` requires both that diagnostic and a real reduction of the node under the basis scope. `_module_positions` classifies each child position, `_reduce_module_conjunction` records one `all_mandatory` deficit per activity-empty position, `_reduce_cardinality` reports the largest selectable count below `require_min`, and `_reduce_bounded` reports the greatest reachable witness total or count strictly below the node's minimum through `max_weight_strictly_below`. A position that failed for any other reason yields no group, so the rule is unreducible and its strict outcome holds.

## Allocation limit and the greedy restart

`_check_size` compares the interned node count plus the trace count with the configured limit and raises on the first excess. `calculate_minimum_new_credits` catches `_PathSizeLimitExceeded`, runs `_solve_greedy_path` once, and re-raises when no limit was set, so the exact attempt is bounded and the greedy restart is not.

`_GreedyPathEvaluator` is a second `ExpressionEvaluator` that derives one scalar `_GreedyRoute` per occurrence without building families. `alternatives` chooses the viable child that minimizes `_candidate_selection_key(..., ranking_cost=route.scalar_cost)`. `cardinality` sorts the viable positions by that key plus their index, takes the first `require_min` as the selection, and takes the next positions up to the maximum as `extension_positions`. `bounded` extends the chosen prefix through `_next_extensions` while its witness `_metric` is below the lower bound, and it never exceeds a source maximum. Extensions come from the chosen derivation only, so a discarded OR branch is never revisited. `_valid` certifies every guard, position count, and nested numeric bound, and a route that fails it is discarded.

A valid greedy route becomes an `approximate` result with the same DTOs as an exact one. A missing or invalid route calls `_approximation_failed`, which returns `approximation_failed`, no route and no total, and one root problem whose reason is `search_too_large`.

## Exclusion blocks and located problems

`_evaluate_primary_candidates` threads three collectors into the primary fold. `blocked_excluded_group_ids` collects the canonical excluded courses that `is_course_activity_eligible` denied to the calculation, and `blocked_excluded_node_keys` collects the graph-only excluded node action keys that `node_action` denied. `_record_problem` appends one `PrerequisiteNodeProblem` per local failure with its occurrence, action key, state, reason, provenance, and optional referenced group. The reduction and all-course diagnostic passes and the greedy evaluator run with the collectors disabled or separate, so only the primary fold's failures reach the result. `_merge_shortfalls` and `_merge_blockers` deduplicate and sort the two record families.

## Tie order

Selection has three stages, and the variable rank appears in none of them.

1. `_PathFamilies.best_support` folds the least `new_credit_weight` total over one partition, restricts the family to that exact total, folds the least `inactive_new_weight` count, and then walks the restricted family with `_least_identities` to fix the sorted tuple of new opaque work identities, new course identities, course witness identities, and non-course witness identities. `_support_key` orders the resulting `_BestSupport`.
2. `_frontier_candidate` selects the partitions whose `_support_key` is smallest, reconstructs evidence for those contenders only, and compares them by `_candidate_selection_key`: total new credits, then the count of distinct inactive new courses, then the sorted new opaque work identities, new course identities, witness course identities, non-course witness identities, and evidence labels.
3. `_candidate_sort_key` breaks a tie left by the earlier stages with the sorted witness set, new set, opaque set, non-course witness set, evidence, and shortfall records.

`_build_new_courses` and `_build_opaque_work` then turn the winning candidate into the result rows, and `_exact_result` sums the course and opaque credit minima into `total_new_credits`.

## Command and route wiring

`run_minimum_route_command(target_code, *, completed_codes, selected_codes, excluded_codes, include_recommended, include_inferred, active_only, basis, completed_node_keys, excluded_node_keys)` in `src/course_explorer/prerequisite/commands.py` composes the operation.

1. `_prepare_prerequisite_command` resolves the target, selected, completed, and excluded inputs through `CourseLookupService.resolve_courses`, rejects a completed course outside a non-empty selected set, and rejects a course key in `completed_node_keys` in favour of the shared completed-course input.
2. It chooses the calculation basis: the completed set, or the effective selected set when `basis="selected"`. Without selected input the effective selected set is the completed set. This one set is the route's sole calculation basis.
3. It compiles one tree through `PrerequisiteGraphCompiler.compile_tree(...)` with the two toggles, `active_only`, the retained selected set, the canonical exclusions, and the graph-node marks, disposes the database context, and returns one `_PrerequisiteCommandContext`.
4. It calls `calculate_minimum_new_credits(context.tree, context.basis_group_ids, max_compact_nodes=load_search_settings().prerequisite_path_max_compact_nodes)`.

`POST /api/minimum-route` in `src/course_explorer_web/routes/minimum_route.py` forwards one `PrerequisitesRequest` from `src/course_explorer_web/routes/prerequisite_inputs.py` and returns `report.model_dump_json()`. `scripts/prerequisites.py --route` prints the same JSON. The graph operation `run_prerequisite_command` shares the same preparation in points 1 to 3 and returns the drawing report instead.

`SearchSettings.prerequisite_path_max_compact_nodes` in `src/course_explorer/config.py` reads `PREREQUISITE_PATH_MAX_COMPACT_NODES` from `config/search.toml` and requires a value greater than 0.

## Tests

| File | Covers |
|---|---|
| `tests/prerequisite/test_path_minimum.py` | The global course union and the new-credit objective over the local course count, expanded courses and directional substitutions, a logical composed AND that charges every incomplete child, numeric wrappers that measure witnesses while the total adds the closure, unresolved cycles and no-solution, a large nested choice rule, repeated opaque work charged once, and the unknown-measure bounds. |
| `tests/prerequisite/test_path_contracts.py` | Coverage fidelity, the deterministic ties over equal credits, activity, and canonical identity, a basis head satisfying its expanded prerequisites at zero cost, zero-credit ties independent of the tree's child order, projected evidence reconstruction, and the activity tie over distinct new courses. |
| `tests/prerequisite/test_path_activity.py` | Activity eligibility, an excluded branch beside another route, an excluded substitution member, and a descendant reused through a route that avoids its excluded head. |
| `tests/prerequisite/test_path_approximation.py` | The size-limited restart, shared-prerequisite and repeated-opaque dedup in the greedy fold, prefix extension for numeric bounds, the `approximation_failed` contract, and the greedy expanded head stopping at the basis. |
| `tests/prerequisite/test_path_module_shortfall.py` | The maximum active-only result and the exact deficit for each module rule family, including nested deficits. |
| `tests/prerequisite/test_path_module_failures.py` | Shortfall is activity-only, and ordinary, impossible, upper-bound, unresolved, cyclic, and expanded-course failures hold their strict outcomes. |
| `tests/prerequisite/test_prerequisite_command.py` | The two basis selections, root exclusion, the drawing refusal that is independent of the route result, and the CLI contract. |

The route as the app presents it is described in [Minimum route](/docs/backend/prerequisites/minimum-route.md).
