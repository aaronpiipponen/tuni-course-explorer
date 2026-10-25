# Prerequisite compiler

The prerequisite compiler turns one course's official and inferred requirement rules into one
solver structure, and the projector derives the drawing from that structure.

## Source vocabulary and solver structure

`src/course_explorer/prerequisite/domain.py` owns the closed expression vocabulary that stored
inferred sets and equivalence groups publish and that the compiler reads. Every node is a frozen
Pydantic model with `extra="forbid"` through `_PrerequisiteModel` in `_helpers.py`.
`PrerequisiteExpression` is an `Annotated` union of ten node kinds discriminated by `type`.
Provenance is four fields: `origin`, `official_kind`, `inferred_category`, and `inference`, with one
valid shape enforced by `_validate_origin_shape`.

`src/course_explorer/prerequisite/structure.py` owns the calculation contract the services consume.
A `PrerequisitePiece` is one provenance-free structural node with an ordered, possibly repeated
`children` tuple of piece IDs and its kind-specific scalar payload. A `PrerequisiteSourceUse` binds
one source position and one `PrerequisiteSourceFact` to a piece. A `PrerequisiteDiagnostic` records
one located compilation problem or ignored source part. A `PrerequisiteSupportBinding` maps one
course-scoped calculation support, `s:<owner>:p:<digest>`, to its uses, drawn nodes and markable
boxes. Relationship members and the compact projection-context table belong to the structure for
route lighting.

Identities are content digests of flat payloads that refer to interned child IDs. `intern_piece`
writes all 12 fields of `_SCALAR_FIELDS` into the payload, with `null` for a field its kind does not
use, together with `manual_credits_min`, `module_rule` and `cycle_closing`, so equal structure
shares one piece while different evaluation values cannot share an answer. Provenance, source
position, owner and display equality never enter the calculation digest. Ordered paths through the
use graph are the implicit occurrences, so no occurrence record, reaching-path table or recursive
calculation tree exists.

`PrerequisiteStructureBuilder` is the request-local interner. `intern_piece`, `intern_fact`,
`intern_use` and `intern_diagnostic` assign every identity. `finish` freezes the objects reachable
from the surviving roots into ID-sorted tuples.

## Compiler entry points and flow

`src/course_explorer/prerequisite/graph.py` defines `PrerequisiteGraphCompiler`, constructed with a
`CurriculumGraphRead`, an `InferredSetRead`, and an `EquivalenceGroupRead`.

`compile_structure(target_group_id, ...)` validates the target, builds a `_CompilationContext`,
prefetches inputs and returns a `PrerequisiteSolverStructure`. The visibility inputs
`include_recommended` and `include_inferred` default to `False`. `active_only`,
`retained_group_ids`, `excluded_group_ids`, `completed_node_keys` and `excluded_node_keys` complete
the caller inputs.

`compile(target_group_id, ...)` returns a `PrerequisiteGraphCompilation` from
`project_prerequisite_graph(structure)`: the bound solver structure and its one permitted display.

`compile_direct_many(target_group_ids, ...)` compiles only the candidates' own direct options. Each
`DirectPrerequisiteCompilation` holds the `solver` structure, `required_use_id` and
`recommended_use_id`, which reference that structure's own use table. It enables recommended
prerequisites, applies no exclusions, projects no drawing and stops ordinary course ancestors
through the `direct_only` context flag while it indexes a non-root course's permitted
substitution and equivalence offers.

`_prefetch_inputs` warms the invocation-local read caches with a bounded superset of each
frontier's referenced courses and modules. It is only a cache warmer. Every miss falls through to
the on-demand `_load_courses` and `_load_modules` reads.

`_build_structure` builds the request-local source index, produces the root's required and
recommended pools through `_compile_category_pools`, classifies mandatory expanded heads with
`_mandatory_expanded_heads`, rebuilds each pool with `_prune_redundant_expansions`, and joins the
surviving pools with one composed logical AND. Mandatory-head classification and pruning both stop
at a module block: a module body is its own calculation context, so a member's independent
occurrence elsewhere keeps its own closure while the module body is never rewritten. It then freezes
the represented course summaries, module summaries, diagnostics, coverage and frozen tables.

### Construction and memoization

The compiler interns every piece while constructing it: children first, then the parent from their
piece IDs and its own use from their use IDs. Before compiling, it builds one request-local source
index over the target's referenced closure through the same official, inferred and substitution
source dispatch, applying the enabled category, direct-self, missing-option and inactive-non-root
pruning before following outgoing references. The index visits each `(kind, group, substitution
policy, equivalence policy)` offering context once: the root begins with both policies off, ordinary
course and module references reset them on, a substitution member enables only equivalences, and an
offered equivalent enables neither. It includes the offered equivalence candidates and every
surviving substitution option, so the source fragment reached from any prefix carries its valid
equivalents. It reuses the scoped course and module read caches and loads no catalogue.

One Tarjan pass over the coarse course/module source graph assigns each source node one
component ID per closure, so an acyclic chain has distinct components, and only a genuine cycle or,
with inferred prerequisites enabled, a represented course and the equivalents it offers share one.
Each offered equivalence also records the edge back from the equivalent. With inferred
prerequisites disabled the index holds no equivalence edge and reads no group.

Course bodies, selected module bodies and source rule nodes are memoized in that file's module-local
fragment owners. A key names the source locator, the immediate owner course, the substitution and
equivalence policy flags, and the ordered ancestor course and module identities filtered to the
fragment's component. Acyclic prefixes are not in the key, so the same source re-reached through
another acyclic path reuses the same use IDs while repeated child slots stay repeated. A completed
cyclic-context fragment is retained. A fragment that closes a cycle to an in-component ancestor
keeps its own key and its explicit cycle-closing use. A memoized fragment replays its pending
diagnostics, module summaries and inferred coverage records into the current compilation context.
Module expansion anchors every pending diagnostic at its nearest surviving use.

Source uses retain their provenance and a source-local locator in the digest. Course bodies anchor
the locator at `(group_id, sisu_course_unit_id, body)`, and selected module bodies and their rules at
the selected module version, so a source reached through another parent keeps the same use. Incoming
course and module references keep their own relationship use. `_mandatory_expanded_heads` visits each
`(piece, mandatory)` once and does not enter a module body, and `_module_member_group_ids` memoizes
its member result per source use.

## Official options, substitutions and collapse

`_compile_category_pools` gates each category before expansion and calls
`_compile_official_options` for `COMPULSORY` and, when enabled, `RECOMMENDED`. Options are ordered
by `option_index` and members by `member_index`. Each complete option is compiled in a branch-local
copy of the context so a dropped option leaves no ghost diagnostic, coverage row or module
summary, and the surviving members become one official AND piece.

An empty source option is recorded as `PrerequisiteIgnoredPartKind.EMPTY_OPTION` and dropped.
`_finish_official_options` drops a whole option containing a `MISSING_MODULE` piece when another
usable official option or an enabled inferred option exists, recording
`MISSING_MODULE_ALTERNATIVE`, and otherwise pools the surviving options into an official OR.

`_compile_prerequisite_member` compiles a course member into a course or expanded-course use, or
an explicit `MISSING_COURSE` unresolved use, and a module member into the inlined module block or
`MISSING_MODULE`.

### Directional substitutions

`_expand_course_requirement` builds the head course use, the descendant body and the composed
EXPANDED_COURSE piece. When the course carries substitution options,
`_compile_substitution_branches` compiles each option in `option_index` order into an official
SUBSTITUTION AND. A singleton option collapses to its member. A member equal to the immediate
owning course is dropped before expansion. A genuinely empty option records `EMPTY_OPTION`, and an
option naming any nonexistent canonical course is dropped whole as
`MISSING_SUBSTITUTION_COURSE` without descendant or equivalence expansion.

### Collapse, mandatory positions and self-removal

The course's own branch, its substitution branches and its inferred equivalent branches form one
flat composed COURSE_ALTERNATIVES OR. `_mandatory_children_inherit` is the one owner of the
mandatory-position child rule, and `_mandatory_child_pairs` and `_mandatory_expanded_heads` both
consume it. `_mandatory_expanded_heads` collects the canonical IDs it marks,
`_prune_redundant_expansions` collapses a non-mandatory repeated expanded course in a mandatory
position to its bare head use, and it re-interns only affected ancestors. A module block is a
traversal boundary for both operations: the collector contributes no member heads to the ordinary
suppression set, and the pruner returns the module-block use unchanged without descending into it.

A course member or module-rule `CourseUnitRule` naming its immediate owning course is the direct
self occurrence and contributes nothing. A genuine indirect cycle is preserved: the compiler emits
one course piece with `cycle_closing=true` and one `COURSE_CYCLE` diagnostic at the actual closing
use, so a shared normal occurrence can never answer for it.

An occurrence whose offered equivalents include a course already on the ancestor path is dropped
like a direct self occurrence: `_expand_course_requirement` returns no use, with no piece,
diagnostic or cycle marker. The rule runs only when inferred prerequisites are enabled and the
occurrence is offered equivalences, so an offered equivalent is never tested and the root counts as
an ancestor.

## Inferred composition and equivalence

`_read_inferred_expression` reads one active course's inferred set once through the cached
`InferredSetRead`. An unavailable or stale set contributes nothing. A current set records its
`InferredCoverageRecord` and returns its stored expression.

`_inferred_option_roots` splits one stored inferred root into its required and recommended complete
options, and `_require_category_homogeneous` rejects a branch that switches category.
`_expand_inferred_options` and `_expand_inferred_expression` read the stored course, AND and OR
structure and expand each course leaf, dropping a direct self occurrence and any connector that
loses every child. A recommended occurrence contributes nothing when recommended is disabled.

`_pool_category` joins one category's official root and its inferred options into one flat logical
OR. `_equivalence_candidates` is the one owner of a represented member's exact offered candidates:
it reads each stored group in UUID order, preserves member order, skips the represented member and
returns the group with its candidate identity. `_compile_equivalence_branches` consumes it and
offers each member as an inferred course occurrence carrying the group's metadata. Each offered
equivalent expands with substitutions and equivalences disabled. The source index consumes the same
candidates, so a candidate's ordinary prerequisites belong to the scoped source authority.

## Module expansion and unresolved states

`_resolve_module_version` calls the shared `_select_module_version` for the root's academic year. One
exact candidate is selected. An empty set falls back to one nearest dated version and
`_resolve_module_version` records `MODULE_VERSION_FALLBACK`, and the source index applies the
same selection and records no fallback diagnostic. More than one candidate becomes
`AMBIGUOUS_MODULE_VERSION`, and an absent module becomes `MISSING_MODULE`.

`_expand_module_requirement` detects a `MODULE_CYCLE` against the in-component ancestor module
path, inlines the selected version's rule through the memoized `_compile_module_rule`, and wraps the
inlined result in a module-block piece. The module body and every rule node are anchored to the
selected module/version identity, so repeated references share their compiled fragment while each
incoming reference keeps its own module-block use. A stored version with no rule tree is the same
whole-module unexpandable shape as a blank source composite. When the whole module is unexpandable
and the source supplies whole-module target credits, the result is one childless official opaque
piece charging its real source minimum. Otherwise the inlined contribution disappears and its
diagnostics anchor at the nearest enclosing surviving use. The module-block piece carries the
selected module identity, its source credit extent and its explicit member course IDs.

`_compile_module_rule` dispatches on `ModuleRuleType` and emits an explicit `MALFORMED_RULE`
unresolved piece for a shape that does not match its declared kind. An all-mandatory composite
becomes a MODULE_RULE AND, a pick-N composite a cardinality piece retaining its source bounds, a
credits rule a credit piece, a course-count rule a course-count piece, and a bounded rule over
wholly unexpandable content an opaque piece or an `UNKNOWN_COURSE_COUNT` unresolved piece. A freely
chosen `ANY_COURSE_UNIT_RULE` or `ANY_MODULE_RULE` is disclosed as `FREE_CHOICE` and contributes
nothing.

`PrerequisiteIgnoredPartKind` names every located disclosure: `EMPTY_OPTION`,
`MISSING_SUBSTITUTION_COURSE`, `MISSING_MODULE_ALTERNATIVE`, `MODULE_VERSION_FALLBACK`,
`FREE_CHOICE`, `UNEXPANDABLE_CONTENT`, and `ALL_MANDATORY_BOUNDS`. A `PrerequisiteDiagnostic`
carries the kind, its fact, referenced IDs, a short detail and an optional module identity. The
affected use carries its diagnostic ID.

## Visibility gating, activity and exclusion

Each disabled category is pruned before descendant traversal, so a hidden recommended or inferred
parent prevents all descendant compilation, summary registration, inferred reads and diagnostic
creation for that branch. An inferred required occurrence needs `include_inferred` alone, and an
inferred recommended occurrence needs both toggles.

`is_course_activity_eligible(structure, group_id, exception_group_ids, for_calculation=False)` is
the one shared activity predicate. Under active-only scope the represented courses are the active
courses and the retained inactive courses. `retained_group_ids` is the caller's raw retention input.
An explicitly opened root compiles its own enabled official structure in every scope and never
reads an inferred set when the root itself is inactive.

`excluded_group_ids` is copied onto the structure. It prunes no drawing node and no descendant, and
`is_course_activity_eligible(..., for_calculation=True)` denies an excluded canonical ID before the
activity rules. `structure.node_action(structure, support_id, completed_node_keys=...,
excluded_node_keys=...)` is the one shared support guard and returns `"excluded"` first and
`"completed"` second.

## Display projection

`src/course_explorer/prerequisite/projection.py` owns the one projection:
`project_prerequisite_graph(structure, *, max_drawing_elements=None, include_display=True)`. It
builds one normalized display recipe per `(owner, use, member set, module-body flag, structural
module flag, parent operator, path flags)` context, then collects the reachable
`(recipe, parent box, nearest box)` context DAG and emits nodes, connections, bindings, diagnostics
and projection contexts on a shallow frozen solver copy. Elided recipes are flattened during that
walk. The walk emits only reachable attachments. Every recipe caches its set of drawn targets: a
visible recipe holds its own fingerprint, and a hidden recipe holds the union of its children's and
decorations' cached sets. Logical elision, internal-requirement eligibility and module/connector
identity all read that one set, so unique displayed targets decide elision while the recipe holds
every direct child reference and source binding.

The projector keys each occurrence by its recipe's stable context key, its parent drawn box and its
nearest drawn box, and gives it the identity `c:` plus a content digest of that flat tuple. Each
`PrerequisiteProjectionContext` stores the native owner and piece, the native child slots as
`(slot, context_id)` pairs and the member IDs that occurrence selects. A repeated flat key resolves
to one row, so both native paths to a shared occurrence reference the same child context without
enumerating reaching paths. The outermost emission returns the root context ID.

A visible occurrence emits its node and its incoming endpoint and fact attachment, binds its
supports to its own node and associates that attachment with its own context. A transparent
occurrence emits no edge: it binds to `binding_key` when it has one and otherwise to the inherited
nearest box, and its children keep the inherited parent and nearest boxes. An expanded occurrence
places its descendants at `descendant_anchor`, so a visible head anchors its closure while a hidden
head inherits the containing box. A display-only internal-requirement summary sits at its enclosing
connector's drawn anchor, and its attachment is associated with the native child context of the slot
that selects it, so a summary lights with its own child rather than with every sibling under one
support.

`PrerequisiteDisplayNode` carries a content-addressed identity, its display kind, owner, course or
module identity, numeric bounds, reason/detail, member and diagnostic IDs, the path flags,
provenance flags, the inferred-card marker and `markable`. For unresolved nodes `reason` is the
unresolved reason. For ignored nodes it is the ignored kind. `markable` is true exactly for module,
cardinality, credits, course-count and opaque-credit boxes. `PrerequisiteDisplayEdge` groups every
relationship between one endpoint pair, lists its member IDs and is `inferred_only` when every
member fact is inferred. `PrerequisiteDrawingGraph` holds the sorted nodes and edges.
`PrerequisiteDrawingAllowance` carries the configured limit and the unique reachable counts.

The projector preserves canonical course nodes, unique-child logical elision, same-operator folding,
module member cards, internal-requirement options and genuine numeric boundaries.

### Module cards and nested modules

One drawn module holds the flattened course cards of the module rules it contains. A structurally
nested module contributes its cards and external obligations to that enclosing box and emits no box
of its own. The member list already reaches through a structural nested module and stops at an
expanded course head. A whole-module prerequisite met inside a member's own closure draws that
module's box, because an expanded-course boundary resets the structural context.

### Hidden heads and origin flags

A hidden module-member head contributes no global course box. Its source use and fact bind to its
containing box, while its real external obligations attach to the containing module as a conditional
subtree. The subtree attachments belong to the member and expanded child contexts, so a basis-covered
member never lights its unselected closure. Only a visible course occurrence contributes its origin
flags, so a hidden official member never suppresses an independently visible inferred-only card.

A structural nested module's directly attached diagnostics are classified as contained while it is
built, so the disappeared-module synthesis creates no nested box. The ignored annotation sits at its
ordinary binding anchor, and every emitted node is root-reachable.

### Marks and the allowance

A saved mark never changes a recipe identity or a fold decision. The allowance counts the unique
reachable node IDs and endpoint records before any display DTO is materialized, so a refused or
route-only projection receives its bindings, projection contexts and members. The configured
`WebSettings.prerequisite_graph_max_elements` limit never applies to solving.

### Shared drawing identity

A display identity is `(course owner, content fingerprint)`: the displayed kind, its displayed
values and the sorted unique fingerprints of its drawn children. A logical group whose children
reach exactly one unique drawn target collapses to that target even when it lists several source
occurrences. Each occurrence holds its own recipe reference, binding and native context row.
Courses are global terminals. Provenance, official kind, inferred category, inference metadata,
mark state, child order, multiplicity, work keys and localized names never separate equal drawings.
A mark is fixed input: a saved key for a box that a normalized drawing does not emit has no
effect and applies again if the same identity returns. A structurally nested module emits no box, so
a saved key for one has no effect.

The compact bindings map every scoped calculation support to the drawn nodes and markable boxes it
represents. A hidden head, an elided wrapper, a structural nested module and a module-body support
bind to their nearest emitted containing box, so no binding points to an un-emitted node. A mark on
one box therefore applies to every calculation piece behind it, including opposite child orders and
repeated numeric slots, while the calculation keeps each slot. A support may bind several boxes when
a shared course is reached from several owners.

A connection's members group by endpoint pair and complete fact, and one member is attributed to
the union of its attachments' context IDs. Its identity is `m:` plus a digest of the endpoint pair
and the fact, so alternative occurrences of one endpoint pair and fact share one member. Each selecting
context stores the member IDs its occurrences own, and a purely synthetic diagnostic attachment has
no context and never lights. The drawing carries no computed node or member state. The browser's
`projectRoute` in `web/src/solver/route-projection.ts` pairs each projected context with the
selected drawing node for it, collects the members that context owns and follows only the child
slots the node carries, and it derives the route's drawn nodes from the root plus the source and
target endpoints of those lit members. A support that binds several drawn locations therefore
contributes only the locations a chosen occurrence meets.

## Satisfaction

`src/course_explorer/prerequisite/satisfaction.py` owns the fixed-basis satisfaction fold.
`PrerequisiteSatisfactionSession(structure, basis_group_ids, *, apply_graph_marks=True)` builds one
memoizing `PieceEvaluator` over the calculation pieces. `_WitnessFamilies` subclasses the
zero-suppressed decision DAG core `_Families`, so cardinality and credit or count filtering stay
exact without enumerating selections.

`evaluate_prerequisite_satisfaction(structure, basis_group_ids)` returns the tri-state
`PrerequisiteSatisfactionState` for the whole structure over one basis.
`evaluate_prerequisite_piece(structure, piece_id, basis_group_ids, *, owner_group_id=None)`
evaluates one selected piece through the same fold. The shared bottom-up dispatch lives in
`traversal.PieceEvaluator`, and `conjunction_is_unresolved` is the one shared conjunction-unresolved
rule.

The Python fold serves the prerequisite read that [Next courses](/docs/backend/search-and-discovery/next-courses.md)
makes. The graph's box states are computed in the browser by `evaluateNodeStates` in
`web/src/solver/satisfaction.ts`, which ports the same tri-state fold beside the route solver. That
evaluator reads the cached solver structure and the live excluded courses, graph marks and chosen
basis, and writes no state into the report.

## Repositories, discovery and commands

`src/course_explorer/prerequisite/repository.py` defines `InferredPrerequisiteRepository` over the
`InferredSetRead` and `InferredSetPublisher` protocols in `domain.py`. `read` returns `UNAVAILABLE`,
`STALE_ACTIVITY_CONTEXT`, or the validated `CURRENT` set. `publish` validates canonical target
identity, activity context, source leaves, evidence and coverage, then creates, replaces or leaves
one target's set. `find_candidate_group_ids` is the bounded candidate read, and
`reconcile_activity` removes stale sets.

`src/course_explorer/prerequisite/equivalence_repository.py` defines
`InferredEquivalenceRepository` over `EquivalenceGroupRead` and `EquivalenceGroupPublisher`.
`read_for_member` and `read_for_members` return each requested member's validated exact stored
groups, kept distinct with no transitive closure. `publish`, `reconcile_activity` and
`withdraw_absent_inference_groups` own group replacement, member activity pruning and below-two-
member removal.

`src/course_explorer/prerequisite/commands.py` composes both public operations.
`_prepare_prerequisite_command` resolves the target, selected, completed and excluded inputs
through `CourseLookupService.resolve_courses`, applies the completed-inside-selected rule, chooses
the calculation basis, compiles the solver structure once and projects it once with the caller's
drawing limit and display choice. `run_prerequisite_command` reports `PrerequisiteGraphReport`
with the drawing allowance and its counts. `run_minimum_route_command` prepares the same structure
without a drawing and runs the bundled TypeScript solver through Node, returning its JSON object.
`_validate_node_keys` accepts complete valid box keys, `^s:.+:d:[0-9a-f]{24}$`.

`src/course_explorer_web/routes/prerequisites.py` is the POST `/api/prerequisites` adapter. It
masks `include_inferred` with `WEB_INFERENCE_ENABLED` from `config/web.toml` and adds the
`dataset_identity` and `max_compact_nodes` fields the browser worker reads.
`src/course_explorer_web/routes/prerequisite_inputs.py` defines the closed
`PrerequisiteGraphRequest`. `scripts/prerequisites.py` is the command-line adapter over the same
commands, and its `--route` flag dispatches to the Node machine route.

## Tests

Compiler and projection tests live under `tests/prerequisite/`. `test_graph_official.py` covers
official options and directional substitutions, `test_graph_inferred.py` inferred composition and
coverage, `test_graph_equivalence.py` equivalence alternatives, `test_graph_module_rules.py`
module-rule expansion and version selection, and `test_graph_module_cycles.py` cycles.

`test_graph_activity.py` covers activity scope and excluded nodes, `test_graph_failures.py`
self-occurrence dropping, `test_graph_projection.py` structure sharing, marks and members, and
`test_graph_scoped_reads.py` scoped reads and repeated shared bodies.

`test_prerequisite_satisfaction.py` covers the satisfaction fold. `test_prerequisite_command.py`
covers the commands, the drawing allowance and the independent route operation.
`test_prerequisite_domain.py` covers the expression vocabulary, the mixed official and inferred expression round-trip, and canonical decimal serialization.
`test_inferred_prerequisite_repository.py` covers inferred-set publication, replacement and read
states, the rejection of unsupported nodes and activity reconciliation.
`test_inferred_equivalence_repository.py` covers equivalence-group publication, read validation,
member pruning and withdrawal.
