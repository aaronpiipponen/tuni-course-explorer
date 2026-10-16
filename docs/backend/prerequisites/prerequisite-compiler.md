# Prerequisite compiler

The prerequisite compiler turns one course's official and inferred requirement rules into a single authoritative expression tree, and projects a minimized drawing graph from that tree.

## Expression vocabulary

`src/course_explorer/prerequisite/domain.py` owns the closed expression vocabulary that official compilation, inferred publication, satisfaction, pathing, and graph projection share. Every node is a frozen Pydantic model with `extra="forbid"` through `_PrerequisiteModel` in `src/course_explorer/prerequisite/_helpers.py`.

`PrerequisiteExpression` is an `Annotated` union of 10 node kinds discriminated by the `type` field. The kinds are `CourseRequirement`, `ModuleRequirement`, `OpaqueCreditRequirement`, `ModuleBlockRequirement`, `AndRequirement`, `OrRequirement`, `CardinalityRequirement`, `CreditRequirement`, `CourseCountRequirement`, and `UnresolvedRequirement`.

`_RequirementBase` carries the four provenance fields `origin`, `official_kind`, `inferred_category`, and `inference`. `PrerequisiteOrigin` is `OFFICIAL`, `INFERRED`, or `COMPOSED`. `OfficialPrerequisiteKind` is `COMPULSORY`, `RECOMMENDED`, `MODULE_RULE`, or `SUBSTITUTION`. `InferredPrerequisiteCategory` is `REQUIRED` or `RECOMMENDED`. `_validate_origin_shape` in `_helpers.py` enforces exactly one shape: official nodes require `official_kind` and forbid `inferred_category` and `inference`, inferred nodes forbid `official_kind` and require `inferred_category` and `inference`, and composed nodes forbid all three.

`AndRequirement` and `OrRequirement` carry an optional `composed_role`. A composed conjunction requires `ComposedAndRole` (`LOGICAL` or `EXPANDED_COURSE`), a composed disjunction requires `ComposedOrRole` (`LOGICAL` or `COURSE_ALTERNATIVES`), and a non-composed node forbids the field. The field is excluded when `None`, so official and inferred payloads serialize byte-for-byte identically. `AndRequirement.validate_kind` requires an `EXPANDED_COURSE` role to hold exactly two children with a `CourseRequirement` head. `CardinalityRequirement`, `CreditRequirement`, `CourseCountRequirement`, and `OpaqueCreditRequirement` are official `MODULE_RULE` shapes, and `UnresolvedRequirement` allows any official kind. `ModuleRequirement` is official-only and never reaches a compiled tree, because the compiler inlines every module reference. `traversal.ExpressionEvaluator` raises `ValueError` for one.

`UnresolvedPrerequisiteReason` names `MISSING_COURSE`, `MISSING_MODULE`, `AMBIGUOUS_MODULE_VERSION`, `MALFORMED_RULE`, `COURSE_CYCLE`, `MODULE_CYCLE`, `UNKNOWN_COURSE_COUNT`, and `UNKNOWN_CREDIT_EXTENT`.

`parse_prerequisite_expression` and `dump_prerequisite_expression` wrap one `TypeAdapter` over `PrerequisiteExpression`. Decimals serialize as canonical fixed-point text through `_decimal_json` and the field serializers on `InferenceNodeMetadata`, `OpaqueCreditRequirement`, and `CreditRequirement`. `expression_course_leaf_group_ids` is the one course-leaf traversal: a `CourseRequirement` contributes its ID, the logical and cardinality kinds extend their children, the numeric wrappers and the module boundary descend their single child, and the module, opaque, and unresolved kinds contribute nothing.

`PrerequisiteNodeOccurrence` and `PrerequisiteGraphNodeState` are the request-local node records the projection and the feature command share. `PrerequisiteNodeProblem` is the located failure record with a `no_solution`, `unresolved`, or `shortfall` state.

## Compiler entry points and flow

`src/course_explorer/prerequisite/graph.py` defines `PrerequisiteGraphCompiler`, constructed with a `CurriculumGraphRead`, an `InferredSetRead`, and an `EquivalenceGroupRead`.

`compile_tree(target_group_id, ...)` validates the target, builds a `_CompilationContext`, prefetches inputs, and calls `_build_tree`. It returns a `PrerequisiteCalculationTree`. The visibility inputs `include_recommended` and `include_inferred` default to `False`, and `active_only`, `retained_group_ids`, `excluded_group_ids`, `completed_node_keys`, and `excluded_node_keys` complete the caller inputs.

`compile(target_group_id, ...)` calls `compile_tree` and returns a `PrerequisiteGraphCompilation` that pairs the tree with `project_prerequisite_graph(tree)`.

`compile_direct_many(target_group_ids, ...)` compiles only the candidates' own direct options and returns tuples of `DirectPrerequisiteCompilation`. Each entry carries the same per-root `PrerequisiteCalculationTree` plus the separate `required` and `recommended` category roots as `PrerequisiteExpression | None`. It enables recommended prerequisites, applies no exclusions, projects no drawing, and stops ordinary course ancestors through the `direct_only` context flag.

`_prefetch_inputs` warms the invocation-local read caches on a `DirectPrerequisiteReadContext` with a bounded superset of each frontier's referenced courses and modules, including substitution members and equivalence members. It is only a cache warmer. Every miss falls through to the on-demand `_load_courses` and `_load_modules` reads.

`_build_tree` produces the root's required and recommended pools through `_compile_category_pools`, classifies mandatory expanded heads with `_mandatory_expanded_heads`, rebuilds each pool with `_prune_redundant_expansions`, and joins the two surviving pools with one composed `LOGICAL` `AndRequirement`. It then records module occurrence boundaries, located ignored parts, cycle issues, node occurrences, and the represented course summaries into the returned tree.

### Structure and provenance keys

Every node carries a stable action identity. Canonical course, module-block, and opaque nodes use their own source identity. `_bind_expression` binds a `requirement:` key to each structural node, computed by `_source_structural_key` from the complete reaching source lineage, an explicit role, and the ordered children's own bound keys. `_stable_digest` keeps the key linear in tree size. `_rule_action_key`, `_part_action_key`, and `_opaque_work_key` derive the corresponding module-rule, disappeared-part, and opaque-work identities.

## Official options, substitutions and collapse

`_compile_category_pools` gates each category before expansion and calls `_compile_official_options` for `COMPULSORY` and, when enabled, `RECOMMENDED`. `_compile_official_options` orders options by `option_index` and members by `member_index`, compiles each complete option in a shallow branch-local copy of the context so a dropped option leaves no ghost issue, coverage row, module boundary, or ignored record, and wraps the surviving members in an official `AndRequirement` with role `official_option`. `_collapse_single_child_wrapper` reduces a one-child option to its member.

An empty source option is recorded as `PrerequisiteIgnoredPartKind.EMPTY_OPTION` and dropped before any expression is built. `_finish_official_options` drops a whole option that contains a `MISSING_MODULE` occurrence when another usable official option or an enabled inferred option exists, recording `MISSING_MODULE_ALTERNATIVE` for it, and otherwise pools the surviving options into an official `OrRequirement` with role `official_options`.

`_compile_prerequisite_member` compiles a course member into an expanded course leaf or an explicit `MISSING_COURSE` unresolved node, and a module member into the inlined module expansion or `MISSING_MODULE`.

### Directional substitutions

`_expand_course_requirement` wraps an expanded course's head leaf and descendant requirements in the composed `EXPANDED_COURSE` conjunction. When the course carries substitution options, `_compile_substitution_branches` compiles each option in `option_index` order into an official `SUBSTITUTION` `AndRequirement` with role `substitution_option`. A singleton option collapses to its member. A member equal to the immediate owning course is dropped before expansion. A genuinely empty option records `EMPTY_OPTION`, and an option naming any nonexistent canonical course is dropped whole as `MISSING_SUBSTITUTION_COURSE` without descendant or equivalence expansion.

### Collapse, mandatory positions and self-removal

The course's own branch, its substitution branches, and its inferred equivalent branches form one flat composed `COURSE_ALTERNATIVES` `OrRequirement`. `_mandatory_child_pairs` is the one owner of the mandatory-position classification, and `_mandatory_expanded_heads` collects the canonical IDs it marks. `_prune_redundant_expansions` collapses a non-mandatory repeated expanded occurrence of a course that an enclosing conjunction already expands in a mandatory position to a bare leaf, carrying the source node's action key, credit extent, module boundary, and ignored-part anchors onto the rebuilt copy.

A course member or module-rule `CourseUnitRule` that names its immediate owning course is the direct self occurrence. `_compile_prerequisite_member` and `_compile_course_unit_rule` return `None` for it before any lookup, expansion, summary registration, inferred read, equivalence read, or issue creation, so the enclosing connector drops that branch. A genuine indirect cycle is preserved: `_expand_course_requirement` records a `_CompiledCourseCycle` when the course is already on the ancestor path, and `_build_tree` emits `COURSE_CYCLE` only at the final surviving closure occurrence.

## Inferred composition and equivalence

`_read_inferred_expression` reads one active course's inferred set once through the cached `InferredSetRead`. An unavailable or stale set contributes no expression and no coverage record. A current set records its `InferredCoverageRecord` and returns its stored expression.

`_inferred_option_roots` splits one stored inferred root into its required and recommended complete options. `_require_category_homogeneous` rejects a branch that switches category. `_expand_inferred_options` and `_expand_inferred_expression` copy the stored course, AND, and OR structure and expand each course leaf into its own requirements, dropping a direct self occurrence and any connector that loses every child. A recommended occurrence returns `None` before expansion when recommended is disabled.

`_pool_category` joins one category's official root and its inferred options into a single flat composed `LOGICAL` `OrRequirement` through `_pool_options`, so an inferred option is a complete alternative to the official structure.

`_compile_equivalence_branches` reads each stored equivalence group containing the represented course in UUID order through `_read_equivalence_groups`, skips the represented member and any member already on the ancestor path, and offers each remaining member as an inferred course occurrence carrying the group's inference metadata and a category derived from the represented leaf. `_read_equivalence_groups` caches one read per canonical member and never merges groups, deduplicates members, or computes a transitive closure. Each offered equivalent expands with `allow_substitutions=False` and `allow_equivalences=False`, so it keeps its own ordinary prerequisites and real credits without chaining its own substitutes or groups.

## Module expansion and unresolved states

`_resolve_module_version` calls `module_version_candidates` for the root's academic year. One candidate is selected. An empty set falls back to one nearest dated version and records `MODULE_VERSION_FALLBACK` naming the requested year and the selected version. More than one candidate becomes `AMBIGUOUS_MODULE_VERSION`, and an absent module becomes `MISSING_MODULE`.

`_expand_module_requirement` detects a `MODULE_CYCLE` against the ancestor module path, inlines the selected version's rule through `_compile_module_rule`, and wraps the inlined result in a `ModuleBlockRequirement`. A stored version with no rule tree is the same whole-module unexpandable shape as a blank source composite. When the whole module's contents are unexpandable and the source supplies whole-module target credits, the result is one childless official `OpaqueCreditRequirement` charging its real source minimum. Otherwise the inlined contribution disappears, and its disclosures are anchored by an enclosing module or the root. `_record_module_boundary` retains the selected module's identity and member IDs beside the surviving expression, and `_iter_module_member_group_ids` collects the explicit official member courses.

`_compile_module_rule` dispatches on `ModuleRuleType` to `_compile_composite_rule`, `_compile_bounded_rule`, `_compile_course_unit_rule`, `_compile_module_reference_rule`, or `_compile_unrestricted_rule`. A source shape that does not match its declared kind becomes one explicit `MALFORMED_RULE` node through `_malformed_module_rule`. `_unexpected_rule_field` checks that only the named fields are populated. An all-mandatory composite compiles to an official `MODULE_RULE` `AndRequirement`, a pick-N composite to a `CardinalityRequirement` retaining its source bounds, a credits rule to a `CreditRequirement`, a course-count rule to a `CourseCountRequirement`, and a bounded rule over wholly unexpandable content to an `OpaqueCreditRequirement` or an `UNKNOWN_COURSE_COUNT` node. A freely chosen `ANY_COURSE_UNIT_RULE` or `ANY_MODULE_RULE` is disclosed as `FREE_CHOICE` and contributes nothing.

`PrerequisiteIgnoredPartKind` names every located disclosure: `EMPTY_OPTION`, `MISSING_SUBSTITUTION_COURSE`, `MISSING_MODULE_ALTERNATIVE`, `MODULE_VERSION_FALLBACK`, `FREE_CHOICE`, `UNEXPANDABLE_CONTENT`, and `ALL_MANDATORY_BOUNDS`. `PrerequisiteIgnoredPart` carries the source group paths, the referenced IDs, a short detail, and an optional selected module summary.

## Visibility gating, activity and exclusion

Each disabled category is pruned before descendant traversal, so a hidden recommended or inferred parent prevents all descendant compilation, summary registration, inferred reads, and issue creation for that branch. An inferred required occurrence needs `include_inferred` alone, and an inferred recommended occurrence needs both toggles.

`is_course_activity_eligible(tree, group_id, exception_group_ids, for_calculation=False)` is the one shared activity predicate. Under active-only scope the represented courses are the active courses and the retained inactive courses. `retained_group_ids` is the caller's raw retention input, distinct from course completion, and `_compile_category_pools` returns no requirements for an inactive non-root course outside it. An explicitly opened root compiles its own enabled official structure in every scope and never reads an inferred set when the root itself is inactive.

`excluded_group_ids` is copied onto the tree. It prunes no drawing node and no descendant, and `is_course_activity_eligible(..., for_calculation=True)` denies an excluded canonical ID before the activity and exception rules. `node_action(node, completed_node_keys=..., excluded_node_keys=...)` is the one shared node guard and returns `"excluded"` first and `"completed"` second.

## Drawing projection

`project_prerequisite_graph(tree, node_states=())` derives a `PrerequisiteDrawingGraph` from the tree alone. Its fields are `course_nodes`, `connector_nodes`, `edges`, `module_nodes`, `ignored_nodes`, and `node_states`.

A `PrerequisiteGraphCourseNode` has the identity `course:<group_id>`, an `action_key`, the course summary, `is_root`, the path flags `via_inferred` and `via_recommended`, the occurrence-provenance flags `has_official_provenance` and `has_inferred_provenance`, the drawing-only marker `display_as_inferred`, and `is_excluded`. Repeated occurrences of one canonical course aggregate into one node. `display_as_inferred` is derived after every visible occurrence is known: it is true only for a non-root node with inferred provenance and no official provenance.

A `PrerequisiteGraphConnectorNode` has the identity `connector:<occurrence_id>`, a `PrerequisiteGraphConnectorKind`, its provenance, any cardinality, credit, or count bounds, an optional referenced group ID, an optional unresolved reason, and optional detail or member IDs.

A `PrerequisiteGraphEdge` groups every relationship that shares its endpoints and provenance class. Each `PrerequisiteGraphEdgeRelationship` keeps its own provenance, its terminal `occurrence_ids`, and its ordered elided-gate `condition_occurrence_ids`, so no evidence or gate chain is ever unioned.

A `PrerequisiteGraphModuleNode` has the identity `module:<occurrence_id>`, the selected module summary, the occurrence's official kind, its official member course cards, and any credit bounds. A `PrerequisiteGraphIgnoredNode` has the identity of its `PrerequisiteIgnoredPart.part_id`.

Backend-owned compaction elides only drawing structure. A logical `AndRequirement` or `OrRequirement` occurrence that loses every drawn child disappears, one with exactly one drawn branch forwards that branch and records the elided gate through `_elide_gate`, and a same-operator nesting folds into its surviving parent through `_fold_logical_branch` unless it is a module boundary, a numeric constraint, an expanded-course boundary, or a manually marked source node. A childless connector such as `OpaqueCreditRequirement` or `UnresolvedRequirement` is drawn as a diagnostic leaf. `_ignored_anchor_parent` resolves each disclosure to its containing module, its anchored node, or the root, and never fabricates a course node. Course path flags are read through `_course_path_flags`, which forwards a bare inferred or recommended occurrence's category through the exact composed `EXPANDED_COURSE` and `COURSE_ALTERNATIVES` wrappers.

## Satisfaction and node states

`src/course_explorer/prerequisite/satisfaction.py` owns the fixed-basis satisfaction fold. `PrerequisiteSatisfactionSession` indexes the tree's node occurrences and cycle locations once and builds one memoizing evaluator over one `_WitnessFamilies` owner. `_WitnessFamilies` subclasses the zero-suppressed decision DAG core `_Families` in `src/course_explorer/prerequisite/_families.py`, so cardinality and credit or count filtering stay exact without enumerating selections.

`evaluate_prerequisite_satisfaction` returns the tri-state `PrerequisiteSatisfactionState` for the whole tree. `evaluate_prerequisite_expression` evaluates one selected subtree through the same fold, and `evaluate_prerequisite_node_states` returns one aggregated `PrerequisiteGraphNodeState` per stable action key with course completion, manual completion, basis satisfaction, and exclusion kept separate. The bottom-up dispatch that satisfaction and pathing share lives in `traversal.ExpressionEvaluator`, and `conjunction_is_unresolved` is the one shared conjunction-unresolved rule. A completed expanded course skips its expanded descendants, while a selected but incomplete basis course satisfies its own node and its prerequisite closure.

## Repositories, discovery and commands

`src/course_explorer/prerequisite/repository.py` defines `InferredPrerequisiteRepository` over the `InferredSetRead` and `InferredSetPublisher` protocols in `domain.py`. `read` returns `UNAVAILABLE`, `STALE_ACTIVITY_CONTEXT`, or the validated `CURRENT` set. `publish` validates canonical target identity, activity context, source leaves, evidence, and coverage, then creates, replaces, or leaves one target's set. `find_candidate_group_ids` is the bounded JSONPath candidate read that returns active targets whose stored expression names any requested source course, and `reconcile_activity` removes stale sets.

`src/course_explorer/prerequisite/equivalence_repository.py` defines `InferredEquivalenceRepository` over `EquivalenceGroupRead` and `EquivalenceGroupPublisher`. `read_for_member` and `read_for_members` return each requested member's validated exact stored groups, with groups kept distinct and no transitive closure. `publish`, `reconcile_activity`, and `withdraw_absent_inference_groups` own group replacement, member activity pruning, and below-two-member removal.

`src/course_explorer/prerequisite/commands.py` composes both public operations. `_prepare_prerequisite_command` resolves the target, selected, completed, and excluded inputs through `CourseLookupService.resolve_courses`, applies the completed-inside-selected rule, chooses the calculation basis, and compiles the tree exactly once. `run_prerequisite_command` then evaluates node states and projects the drawing into a `PrerequisiteGraphReport`, and `prerequisite_drawing_allowance` counts the nodes and edges into a `PrerequisiteDrawingAllowance`. `run_minimum_route_command` composes the same preparation and calls `calculate_minimum_new_credits` from `src/course_explorer/prerequisite/path.py`. `_validate_node_keys` accepts only the `_SUPPORTED_NODE_PREFIXES`.

`src/course_explorer_web/routes/prerequisites.py` is the POST `/api/prerequisites` adapter, and it forwards the configured drawing limit. `src/course_explorer_web/routes/prerequisite_inputs.py` defines the closed `PrerequisitesRequest`. `scripts/prerequisites.py` is the command-line adapter over the same commands, and its `--route` flag dispatches to the minimum-route operation.

## Tests

The compiler and its projection are covered by `tests/prerequisite/test_graph_official.py` for official options and directional substitutions, `test_graph_inferred.py` for inferred composition, coverage, pooling, and category filtering, `test_graph_equivalence.py` for equivalence alternatives and their path cost, `test_graph_module_rules.py` for module-rule expansion and version selection, `test_graph_module_cycles.py` for module and course cycles, `test_graph_activity.py` for activity scope and excluded nodes, `test_graph_failures.py` for self-occurrence dropping and inactive roots, `test_graph_projection.py` for deduplication, connection grouping, collapse, and path flags, and `test_graph_scoped_reads.py` for scoped reads and direct-many parity.

The expression contracts are covered by `tests/prerequisite/test_prerequisite_domain.py`. Satisfaction is covered by `tests/prerequisite/test_prerequisite_satisfaction.py`. The repository boundaries are covered by `tests/prerequisite/test_prerequisite_graph_repository.py`, `test_inferred_prerequisite_repository.py`, and `test_inferred_equivalence_repository.py`. The commands, the drawing allowance, and the command-line adapter are covered by `tests/prerequisite/test_prerequisite_command.py`.
