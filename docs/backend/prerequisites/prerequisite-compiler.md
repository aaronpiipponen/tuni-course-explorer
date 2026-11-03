# Prerequisite compiler

The prerequisite compiler turns one course's official and inferred requirement rules into one solver structure, and the native code assigns its identities and stores it once.

## Source vocabulary and solver structure

`src/course_explorer/prerequisite/domain.py` owns the closed expression vocabulary that stored inferred sets and equivalence groups publish and that the compiler reads. Every node is a frozen Pydantic model with `extra="forbid"` through `_PrerequisiteModel` in `_helpers.py`. `PrerequisiteExpression` is an `Annotated` union of ten node kinds discriminated by `type`. Provenance is four fields: `origin`, `official_kind`, `inferred_category`, and `inference`, with one valid shape enforced by `_validate_origin_shape`.

`src/course_explorer/prerequisite/structure.py` owns the calculation contract the services consume. A `PrerequisitePiece` is one provenance-free structural node with an ordered, possibly repeated `children` tuple of piece IDs and its kind-specific scalar payload. A `PrerequisiteSourceUse` binds one source position and one `PrerequisiteSourceFact` to a piece. A `PrerequisiteDiagnostic` records one located compilation problem or ignored source part. A `PrerequisiteSupportBinding` maps one course-scoped calculation support, `s:<owner>:p:<digest>`, to its uses, drawn nodes and markable boxes. Relationship members and the compact projection-context table belong to the structure for route lighting.

Piece, use, fact and diagnostic identities are content digests of flat canonical-JSON payloads that refer to already-assigned child IDs. A piece payload writes all 12 scalar fields, with `null` for a field its kind does not use, together with `manual_credits_min`, `module_rule` and `cycle_closing`, so equal structure shares one piece while different evaluation values cannot share an answer. Provenance, source position, owner and display equality never enter the calculation digest. Ordered paths through the use graph are the implicit occurrences, so no occurrence record, reaching-path table or recursive calculation tree exists.

`native/identity.cpp` is the one identity authority. It canonicalizes each payload, computes its SHA-256 digest with the library's own implementation, keeps one record per identity and freezes the objects reachable from the surviving roots into ID-sorted tables. Python receives those final identities and never derives, rehashes or re-interns one. Fact payloads hash the exact `InferenceNodeMetadata` JSON form, including the confidence string and default nested fields. The library links `libpq` for its database loader and carries its own SHA-256, so the host provides libpq and the C++ runtime and needs no OpenSSL.

## Compiler and fact loader

The compiler, the database fact loader, the identity tables, the structure emitter, the record view, the drawing projector and the evaluator are native, and `native/Makefile` builds them into one shared library from separate units. [Native libraries](/docs/architecture/native-libraries.md) states that container build and the host libraries the result loads.

`native/fact_model.h` declares the fact bundle and the typed source-position parts. `native/pgloader.cpp` opens one libpq connection per worker, fills one bundle per open handle with the canonical course, version, period, prerequisite, substitution, module, rule, inferred-set and equivalence facts read through bounded parameterized queries, and retains it. `native/compiler.cpp` builds the calculation DAG, the ordered source-key tuples and the canonical records.

`native/identity.cpp` assigns their identities, `native/projector.cpp` derives the drawing, `native/writer.cpp` and `native/structure_view.cpp` hold the compiled set and its frozen record view for one request bundle, `native/evaluator.cpp` folds the satisfaction and coverage outcomes, and `native/api.cpp` exposes the database and evaluation calls, with `native/library_api.cpp` holding the format version, error text, record accessor and bundle release shared by both libraries. The test-only `libcourse_prerequisite_fixtures.so` adds `native/fixture_reader.cpp` and `native/fixture_api.cpp` to build the same structures from an ordered record bundle without a database handle.

`src/course_explorer/prerequisite/native_compiler.py` loads the shared library and reads that typed record view through `ctypes`: ordered tables of final pieces, uses, facts, diagnostics, summaries, bindings, contexts, members and display nodes and edges. It constructs the frozen DTOs from those records and derives nothing.

Ordered records provide implicit positions. The native evaluator returns one outcome per structure in that order, and the materializer pairs outcomes and structures by position.

One process lock serializes this worker's fact-handle compile calls, so concurrent request threads never mutate the retained fact bundle. `src/course_explorer/prerequisite/native_handle.py` owns that handle and the connection string it was opened from, and `native_compiler.py` holds the library loader and the record materializer. The public facade is in `src/course_explorer/prerequisite/graph.py`, where `PrerequisiteGraphCompiler` holds the worker's native handle and delegates each compile call to `native_compiler`, so the compilation itself runs in native code. `compile` returns one `PrerequisiteGraphCompilation`, which holds the solver structure, the materialized drawing graph and its allowance, and `compile_direct_many` returns one compilation per represented candidate.

`compile_direct_many` enables recommended prerequisites, applies no exclusions, projects no drawing and stops ordinary course ancestors through the native `direct_only` flag while it indexes a non-root course's permitted substitution and equivalence offers. It asks for the narrow record view and returns one `DirectPrerequisiteSummaryCompilation` per represented candidate. That compilation pairs a frozen `PrerequisiteSolverSummary`, which holds the structure's root identity, academic year and the candidate's own course summary, with the request-local native bundle, and discovery reads those fields without materializing or walking the drawing records.

The library reports its interface version 5, and a missing or version-mismatched library raises one `ValueError` that names `scripts/build_native.py`. Each compilation carries the request-local native bundle until the command frees it after all its evaluations. The per-worker fact handle remains open across requests, so a repeated request issues no query.

## Construction and memoization

The native compiler records calculation nodes and source uses through native indices, then assigns each public identity in child-before-parent order and rewrites child references to those IDs.

Before compiling, the native compiler builds one request-local source index over the target's referenced closure through the same official, inferred and substitution dispatch, applying the enabled category, direct-self, missing-option and inactive-non-root pruning before following outgoing references. The index visits each `(kind, group, substitution policy, equivalence policy)` offering context once: the root begins with both policies off, ordinary course and module references reset them on, a substitution member enables only equivalences, and an offered equivalent enables neither. It includes the offered equivalence candidates and every surviving substitution option, so the source fragment reached from any prefix carries its valid equivalents.

One iterative Tarjan pass over the coarse course and module source graph assigns each source node one component ID per closure, so only a genuine cycle, or with inferred prerequisites enabled a represented course and the equivalents it offers, share one component. Each offered equivalence also records the edge back from the equivalent.

Course bodies, selected module bodies and source rule nodes are memoized inside the native compiler. A key names the source locator, the immediate owner course, the substitution and equivalence policy flags, and the ordered ancestor course and module identities filtered to the fragment's component. Acyclic prefixes are not in the key, so the same source re-reached through another acyclic path reuses the same use content while repeated child slots stay repeated. A memoized fragment replays its pending diagnostics, module summaries and inferred coverage records into the current compilation context.

Source uses retain their provenance and a source-local locator in the digest. Course bodies anchor the locator at `(group_id, sisu_course_unit_id, body)`, and selected module bodies and their rules at the selected module version, so a source reached through another parent keeps the same use. Incoming course and module references keep their own relationship use. Mandatory expanded heads never enter a module body, and module member IDs are memoized per source use.

## Official options, substitutions and collapse

The compiler gates each category before expansion and compiles `COMPULSORY` and, when enabled, `RECOMMENDED` options separately. Options are ordered by `option_index` and members by `member_index`. Each complete option is compiled in a branch-local pending-diagnostic context so a dropped option leaves no ghost diagnostic, coverage row or module summary, and the surviving members become one official AND piece.

An empty source option is recorded as the ignored kind `empty_option` and dropped. A whole option containing a missing-module piece is dropped when another usable official option or an enabled inferred option exists, recording `missing_module_alternative`. Otherwise the surviving options pool into an official OR.

A course member compiles into a course or expanded-course use, or an explicit `missing_course` unresolved use. A module member compiles into the inlined module block or `missing_module`.

### Directional substitutions

The compiler builds the head course use, the descendant body and the composed `expanded_course` piece. When the course carries substitution options, each option in `option_index` order becomes an official SUBSTITUTION AND. A singleton option collapses to its member. A member equal to the immediate owning course is dropped before expansion. A genuinely empty option records `empty_option`, and an option naming any nonexistent canonical course is dropped whole as `missing_substitution_course` without descendant or equivalence expansion.

### Collapse, mandatory positions and self-removal

The course's own branch, its substitution branches and its inferred equivalent branches form one flat composed `course_alternatives` OR. One mandatory-child rule is shared by head collection and pruning. Pruning collapses a non-mandatory repeated expanded course in a mandatory position to its bare head use and re-interns only affected ancestors. A module block is a traversal boundary for both operations: the collector contributes no member heads to the ordinary suppression set, and the pruner returns the module-block use as it is without descending into it.

A course member or module-rule `CourseUnitRule` naming its immediate owning course is the direct self occurrence and contributes nothing. A genuine indirect cycle is preserved: the compiler emits one course piece with `cycle_closing=true` and one `course_cycle` diagnostic at the actual closing use.

An occurrence whose offered equivalents include a course already on the ancestor path is dropped like a direct self occurrence: it returns no use, with no piece, diagnostic or cycle marker. The rule runs only when inferred prerequisites are enabled and the occurrence is offered equivalences, so the root counts as an ancestor.

[Cyclic graph compilation](/docs/experiments/graph-and-route-algorithms/cyclic-graph-compilation.md#the-rule-applied-in-the-product) records the roots whose expansion the rule bounds.

## Inferred composition and equivalence

The fact loader reads one active course's current inferred set once. An unavailable or stale set contributes nothing. A current set records its `InferredCoverageRecord` and exposes its stored expression. A current set with no expression records its coverage.

The compiler splits one stored inferred root into its required and recommended complete options and rejects a branch that switches category. It copies the stored course, AND and OR structure and expands each course leaf, dropping a direct self occurrence and any connector that loses every child. A recommended occurrence contributes nothing when recommended is disabled.

One category's official root and its inferred options pool into one flat logical OR. The equivalence reader returns each stored group in UUID order and preserves member order, skipping the represented member. Each offered equivalent expands as an inferred course occurrence carrying the group's metadata, with substitutions and equivalences disabled. The source index consumes the same candidates.

## Module expansion and unresolved states

One exact module version for the root's academic year is selected in one native call, which prefers an exact period membership and then a validity-bound match, and falls back to one nearest dated version and records `module_version_fallback`. The source index applies the same selection and records no fallback diagnostic. More than one exact candidate becomes `ambiguous_module_version`, and an absent module becomes `missing_module`.

The compiler detects a `module_cycle` against the in-component ancestor module path, inlines the selected version's rule through the memoized rule fragment, and wraps the result in a module-block piece. The module body and every rule node are anchored to the selected module and version identity, so repeated references share their compiled fragment while each incoming reference keeps its own module-block use. A stored version with no rule tree is the same whole-module unexpandable shape as a blank source composite. When the whole module is unexpandable and the source supplies whole-module target credits, the result is one childless official opaque piece charging its real source minimum. Otherwise the inlined contribution disappears and its diagnostics anchor at the nearest enclosing surviving use. The module-block piece carries the selected module identity, its source credit extent and its explicit member course IDs.

Module-rule dispatch emits an explicit `malformed_rule` unresolved piece for a shape that does not match its declared kind. An all-mandatory composite becomes a `MODULE_RULE` AND, a pick-N composite a cardinality piece retaining its source bounds, a credits rule a credit piece, a course-count rule a course-count piece, and a bounded rule over wholly unexpandable content an opaque piece or an `unknown_course_count` unresolved piece. A freely chosen `ANY_COURSE_UNIT_RULE` or `ANY_MODULE_RULE` is disclosed as `free_choice` and contributes nothing.

## Visibility gating, activity and exclusion

The native compiler applies the same visibility and activity rules as the command layer: a disabled recommended category is never loaded or compiled, an inactive course that is not retained is dropped under the activity scope, a retained inactive basis course is kept as a leaf, and an excluded represented course is recorded in `excluded_group_ids` and kept in the structure. Inferred coverage is emitted only for represented and root courses. Native code installs every display identity, binding, projection context and relationship member, and Python only constructs the exact frozen DTOs.

## The drawing and the evaluation

The native projector derives the drawn boxes, their identities, the support bindings and the projection contexts from the structure this page describes. [Prerequisite display projection](/docs/backend/prerequisites/display-projection.md) states the recipe walk, the module cards, the marks and the shared drawing identity.

The native evaluator folds the same pieces into the satisfaction family and the coverage fraction of one basis. [Satisfaction evaluation](/docs/backend/prerequisites/satisfaction-evaluation.md) states the fold, the outcomes and the browser port.

## Repositories, discovery and commands

`src/course_explorer/prerequisite/repository.py` defines `InferredPrerequisiteRepository` over the `InferredSetRead` and `InferredSetPublisher` protocols in `domain.py`. `read` returns `UNAVAILABLE`, `STALE_ACTIVITY_CONTEXT`, or the validated `CURRENT` set. `publish` validates canonical target identity, activity context, source leaves, evidence and coverage, then creates, replaces or leaves one target's set. `find_candidate_group_ids` is the bounded candidate read, and `reconcile_activity` removes stale sets.

`src/course_explorer/prerequisite/equivalence_repository.py` defines `InferredEquivalenceRepository` over `EquivalenceGroupRead` and `EquivalenceGroupPublisher`. `read_for_member` and `read_for_members` return each requested member's validated exact stored groups, kept distinct with no transitive closure. `publish`, `reconcile_activity` and `withdraw_absent_inference_groups` own group replacement, member activity pruning and below-two-member removal.

`src/course_explorer/prerequisite/commands.py` composes both public operations. `_prepare_prerequisite_command` resolves the target, selected, completed and excluded inputs through the [course resolver](/docs/reference/glossary.md#search-and-comparison), applies the completed-inside-selected rule, chooses the calculation basis, compiles the solver structure once and projects it once with the caller's drawing limit and display choice. `run_prerequisite_command` reports `PrerequisiteGraphReport` with the drawing allowance and its counts. `run_minimum_route_command` prepares the same structure without a drawing and runs the bundled TypeScript solver through Node, returning its JSON object. `_validate_node_keys` accepts complete valid box keys, `^s:.+:d:[0-9a-f]{24}$`. The web route passes the supervisor's preloaded projection, so the resolution issues no database read.

`src/course_explorer_web/routes/prerequisites.py` is the POST `/api/prerequisites` adapter. It masks `include_inferred` with `WEB_INFERENCE_ENABLED` from `config/web.toml` and adds the `dataset_identity` and `max_compact_nodes` fields the browser worker reads. `src/course_explorer_web/routes/prerequisite_inputs.py` defines the closed `PrerequisiteGraphRequest`. `scripts/prerequisites.py` is the command-line adapter over the same commands, and its `--route` flag dispatches to the Node machine route.

## Tests

The compiler is covered by the real disposable-database contract tests in `tests/prerequisite/test_graph_official.py`, `test_graph_inferred.py`, `test_graph_module_rules.py`, `test_graph_module_cycles.py`, `test_graph_activity.py`, `test_graph_equivalence.py`, `test_graph_failures.py`, `test_graph_projection.py`, `test_prerequisite_graph_repository.py`, `test_inferred_prerequisite_repository.py`, `test_inferred_equivalence_repository.py`, `test_prerequisite_domain.py` and `test_prerequisite_command.py`, and by the direct compilation and outcome mapping that `tests/next_courses/test_next_courses.py` exercises. The missing-library contract of `compile_direct_many` is in `tests/native/test_native_library.py`, and the graph route over a normalized catalogue is in `tests/web/test_api.py`.

Those tests seed their catalogue fixtures into a `_test` database and compile through the native loader and evaluator, so the calculation identities, coverage values and complete endpoint responses are checked against the native path. The session fixture fails with the build guidance from `scripts/build_native.py` when a serving library is absent, `tests/prerequisite/conftest.py` does the same for the fixture library, and a missing compiler or library is a test environment failure, not a skip.
