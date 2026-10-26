# Prerequisites

Prerequisite handling compiles one solver structure per graph root, answers the graph read from it and supplies the local route calculation.

## One solver structure

One preparation resolves the target, the selected courses, the completed courses, and the exclusions into canonical identities and compiles the authoritative solver structure for the target. The structure holds each identical calculation piece once, with ordered child slots, and every source position as one compact use carrying its provenance fact. The compiler folds the official prerequisite options, the inlined rules of the selected module versions, and, when the request asks for them, the published inferred prerequisites and equivalence groups into that structure. Inferred output is stored apart from the official catalogue and draws in the same graph with its own provenance. [Prerequisite compiler](/docs/backend/prerequisites/prerequisite-compiler.md) describes the compiler, the pieces it interns, and its unresolved parts.

## The graph

The graph operation derives the drawing from that structure and returns the structure, the drawing and the drawing allowance. The web response adds the serving dataset identity and the configured allocation limit. The browser computes the box states from the held structure and the live course state, and the inferred toggle takes part only on a site that serves the inference features. A script caller passes no drawing limit, and the web route applies the configured one. [Prerequisite graph](/docs/backend/prerequisites/prerequisite-graph.md) describes the report and its drawing.

## The minimum route

The route calculation reads the same solver structure and one basis, either the completed courses or every selected course, and returns the set of courses that meets the requirements with the fewest new credits, each course counted once. A basis course costs nothing and its own prerequisites are not expanded. The browser runs the calculation in a background worker for an explicit Find, and the machine route command runs the same solver through Node. The result is exact by default. A calculation whose exact attempt exceeds the configured limit runs one scalar greedy derivation, which returns an approximate route or a No route found result. Only the exact attempt is bounded by the limit. [Minimum route](/docs/backend/prerequisites/minimum-route.md) states every route outcome and the tie-break order.

The exact search, its pruning, and the greedy restart are described in [Minimum route solver](/docs/backend/prerequisites/minimum-route-solver.md).

[Graph and route algorithm experiments](/docs/experiments/graph-and-route-algorithms/README.md) covers the allocation-limit calibration, the applied cycle cut, the drawing-allowance measurements and the structural route deduplication.
