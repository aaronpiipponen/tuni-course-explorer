# Prerequisites

Prerequisite handling compiles one requirement expression per course and answers the graph and route requests from it.

## One compiled expression

One preparation resolves the target, the selected courses, the completed courses, and the exclusions into canonical identities and compiles the authoritative requirement tree for the target. The compiler folds the official prerequisite options, the inlined rules of the selected module versions, and, when the request asks for them, the published inferred prerequisites and equivalence groups into that tree. Inferred output is stored apart from the official catalogue and is drawn beside it. [Prerequisite compiler](/docs/backend/prerequisites/prerequisite-compiler.md) describes the compiler, its node vocabulary, and its unresolved parts.

## The graph

The graph operation projects the compiled tree into the drawing the **Prerequisites** tab renders, with one presentation state for each node. The basis, the exclusions, and the activity scope decide those states, and the inferred toggle takes part only on a site that serves the inference features. A script caller passes no drawing limit, and the web route applies the configured one. [Prerequisite graph](/docs/backend/prerequisites/prerequisite-graph.md) describes the drawing and its states.

## The minimum route

The route operation reads the same compiled tree and one basis, either the completed courses or every selected course, and returns the set of courses that meets the requirements with the fewest new credits, each course counted once. A basis course costs nothing and its own prerequisites are not expanded. The result is exact by default, and a request whose compact search space exceeds the configured limit restarts once as a bounded approximation that returns an approximate route or a No route found result. [Minimum route](/docs/backend/prerequisites/minimum-route.md) states every route outcome and the tie-break order.

The exact search, its pruning, and the bounded approximation are described in [Minimum route solver](/docs/backend/prerequisites/minimum-route-solver.md).
