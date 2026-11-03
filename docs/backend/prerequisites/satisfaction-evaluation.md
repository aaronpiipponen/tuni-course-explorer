# Satisfaction evaluation

The native evaluator folds one solver structure into a satisfaction family and a per-category coverage fraction, and the browser ports the same fold for the drawn box states.

## The fold inputs

`native/evaluator.cpp` owns the fixed-basis fold. It receives the compiled structures of one request bundle, the chosen basis of canonical course identities, and the two activity and category flags the compiler recorded, and it returns one outcome per structure.

The fold reads the calculation pieces alone. Each piece carries its kind-specific values, its ordered child slots and its evaluation flags, and an identical piece is stored once, so an equal requirement reached through two paths folds once and shares one answer. [Prerequisite compiler](/docs/backend/prerequisites/prerequisite-compiler.md#source-vocabulary-and-solver-structure) states the piece payload and its digest.

A course leaf in the basis satisfies the requirement at no charge, so an inactive course that the basis retains satisfies the courses that depend on it. A course leaf outside the basis is unsatisfied, and under `active_only` an inactive leaf is denied before it can satisfy anything. A leaf whose piece closes a cycle returns the zero family with the unresolved flag.

## The satisfaction fold

Each piece folds to a family of the basis courses that satisfy it, or reports that it is unresolved. The zero family means no selection satisfies the piece. The kinds fold as follows.

- A course leaf contributes its basis variable when it is in the basis. Otherwise it contributes the zero family, with the cycle flag carried from the compilation.
- A module block folds transparently over its one child. An expanded course joins its head with the descendant that the head stands for: a satisfiable descendant contributes the neutral family, and a head outside the basis must be satisfied together with it. A head in the basis returns its own family alone.
- An opaque credit piece with a zero source minimum is satisfied by the neutral family, and a positive source minimum is unsatisfied, because the fold selects no course for it.
- An unresolved piece is the zero family and marks the result unresolved.
- A credit piece filters its child family by the piece's credit bounds, and a course-count piece filters by the piece's count bounds. An absent lower bound is zero, and an absent upper bound leaves the family unbounded.
- An AND piece joins its children, an OR piece and a course-alternatives piece union them and OR their unresolved flags, and a cardinality piece unions the selections that hold between its lower and upper count.

The evaluator memoizes each piece within one compilation. The filters apply the bounds exactly without enumerating selections, so a requirement over a large choice rule folds in one family.

## Coverage

A coverage value is the share of the course slots of the best-covered option branch in one category. `CoverageEvaluator` folds the same pieces into a slot set.

- A course leaf contributes one slot, marked covered when the leaf's own family is known, so a basis course covers its slot and an unsatisfied one does not.
- A module block, credit piece and course-count piece pass their child's slots through, so their bounds decide satisfaction without adding a position.
- An opaque piece adds no slot, and an unresolved piece adds one uncovered position.
- An expanded course merges the slots of its head and its descendants.
- A course-alternatives piece counts its head course alone.
- An OR piece reports the child branch with the greatest covered fraction.
- An AND piece and a cardinality piece merge the slots of every child, so an uncovered position of a partly covered mandatory set lowers the share.

The fraction is the covered slots divided by the slots plus the unresolved positions. A category with no slot and no unresolved position carries no coverage value in the outcome rather than a zero share, so a course without a required or recommended category reports no value for that side.

## Outcomes and the bundle mapping

`evaluate_bundle` runs the family fold and the coverage fold once per structure in the bundle and returns one outcome per structure in bundle order. Each outcome carries the required and recommended coverage fractions and the flag that states whether the requested mode has a solution.

A structure produces no outcome when its root is in the basis, when it is inactive under the active scope, when it carries no category root, or when both categories hold no position. The Python outcome reports such a structure as `None`, and a category with no position reports `None` for that coverage value.

The eligibility rule of a mode reads those outcomes. Under **All**, every category the course carries must be satisfied. Under **Partially covered**, at least one slot of the required or recommended category must be covered, and a category the course does not carry is neutral.

`NativeBundle.evaluate(basis, *, mode)` in `src/course_explorer/prerequisite/native_compiler.py` calls the native evaluator for every compiled structure in one call. `evaluate_next_course_outcomes` in `src/course_explorer/next_courses/service.py` keys the returned outcomes by root group identity, and the materializer pairs an outcome with its structure by position. [Next-course coverage](/docs/backend/search-and-discovery/next-course-coverage.md) describes the discovery path that reads them.

## The browser's box states

The graph's box states are computed in the browser by `evaluateNodeStates` in `web/src/solver/satisfaction.ts`, which ports the same tri-state fold beside the route solver. That evaluator reads the cached solver structure and the live excluded courses, graph marks and chosen basis, and writes no state into the report. A saved node mark registers its calculation support as an attested witness at no new cost, and an excluded node mark denies that support, so a box state follows from the structure the browser already holds.

The server returns no computed box state, so a mark, an exclusion or a basis change re-evaluates the drawing without a request. [Prerequisite graph](/docs/backend/prerequisites/prerequisite-graph.md#box-states-and-the-drawing-inputs) describes the states the app shows.

## Tests

| File | Covers |
|---|---|
| `tests/next_courses/test_next_courses.py` | The native evaluator through the real direct compiler: both modes and their orders, required and recommended coverage with an absent category reported as `None`, the activity scope, and the retained inactive basis. |
| `web/src/solver/satisfaction.test.ts` | The browser fold over structures the server wrote: canonical completion identity, the AND, OR, cardinality, credit and count bounds, an expanded course that stops at a basis head, excluded courses, and the box states the browser derives without changing the held report. |
| `tests/native/test_native_library.py` | The missing or mismatched native prerequisite library that fails the compile call before any read. The evaluator loads the same library. |
