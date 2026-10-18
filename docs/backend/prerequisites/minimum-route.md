# Minimum route

A minimum route request returns the set of courses that meets a course's prerequisites with the fewest new credits.

## Fewest new credits

A route holds the courses a requirement needs and the basis does not cover. Its cost is the [new credits](/docs/reference/glossary.md#prerequisites-and-routes) of exactly those courses, each counted once. Course count never decides the route, so two cheap courses can cost less than one expensive course.

## One expression and one basis

A route request takes the same inputs as the prerequisite graph read: the graph root, the Recommended and Inferred toggles, the activity scope, the selected and completed course sets, the basis, the excluded courses, and the graph-node marks. Both operations resolve those inputs, compile one prerequisite expression from them, and read the same chosen basis. The drawing and the calculation therefore describe the same requirement set and cannot drift apart.

The basis is either the completed courses or every selected course, chosen by **Route basis**. The route uses exactly one of them, and the two choices have the same effect: a course in the basis satisfies its requirement at no new cost, and its own prerequisites are not expanded below it.

The route request returns its own result and no drawing. The graph read and the compiler behind both are described in [Prerequisite graph](/docs/backend/prerequisites/prerequisite-graph.md).

## Exact by default

A route request computes the exact route by default. `PREREQUISITE_PATH_MAX_COMPACT_NODES` in `config/search.toml` sets the largest size the exact attempt may build, and the example sets 700000. When the exact attempt grows past that size, the request abandons it once and runs a single greedy search instead, so an oversized request returns an approximate route or a No route found result. The limit bounds the exact attempt only.

| Key | Meaning | Example |
|---|---|---|
| `PREREQUISITE_PATH_MAX_COMPACT_NODES` | The largest size the exact route attempt may build before the request runs one greedy search instead | 700000 |

The setting is a positive integer.

## Route outcomes

Every request ends in one [route outcome](/docs/reference/glossary.md#prerequisites-and-routes), and the app shows it as one label.

The diagram follows one route request from the compiled expression through the exact search, the configured size limit, and the greedy search to the six outcomes.

![One exact search reads the same compiled prerequisite expression and basis as the graph. When the size limit is not exceeded, the exact search yields the exact minimum route, a shortfall from a reduced route, an unresolved route, or no route under the rules. When the size limit is exceeded, one greedy restart yields an approximate route or no route found.](/docs/diagrams/minimum-route-outcomes.svg)

| Interface label | Code state | Meaning | What it returns |
|---|---|---|---|
| **Exact minimum route** | `exact` | A known route is the global minimum new-credit set. | The route and its total new credits, together with the located problems of the requirements it denied while finding the route. |
| **Approximate route** | `approximate` | The exact attempt exceeded the size limit and the greedy search found a valid route. | The route and its total new credits, with no claim that the route is the global minimum. |
| **No route found** | `approximation_failed` | The exact attempt exceeded the size limit and the greedy search found no valid route. | No route and no total, with one root problem that reports the search as too large. |
| **Route unresolved** | `unresolved` | Unresolved structure could yield a cheaper route than any known one. | No route and no total, with the located problems and any blocking condition. |
| **No route exists** | `no_solution` | No route meets the requirements under the rules. | No route and no total, with the located problems of the blocked requirements. |
| **Shortfall** | `shortfall` | Only active courses are allowed, and a module rule falls below its own lower bound. | The largest route the active courses allow, its total new credits, and one record per deficient module rule. |

## What the route charges

A course in the basis costs nothing, and the route does not expand that course's own prerequisites, so a basis course removes its requirement subtree from the route in either basis mode. A course outside the basis costs its own credits and brings its own prerequisites into the route.

A course that several branches of the requirement need is counted once, so the route charges its credits once. The same unexpandable content needed on several branches is charged once as well.

Excluding a course blocks every route through it. The excluded course never counts as covered and never appears in the route, while its own prerequisites are usable through another route that does not pass through it. Excluding the graph root leaves the whole request with no route.

## The order of preference

A request minimizes the new credits first. When several routes share the lowest total, it prefers the route with the fewest distinct inactive new courses. When those rules leave a tie, the deterministic canonical identities decide, compared in sorted order: the new unexpandable content identities, the new course identities, and the witness identities. The same inputs always return the same route.

## What the result reports

Besides the route, a result carries the total new credits, the new courses with the tree occurrences each one satisfies, and the new unexpandable content with its credit minimum. It also reports the excluded courses and excluded nodes that blocked a requirement, the located problems of the requirements the search denied, and the tree occurrences the winning route selects. A Shortfall result carries one record per deficient module rule.

The exact search, its pruning, and the bounded approximation are described in [Minimum route solver](/docs/backend/prerequisites/minimum-route-solver.md).
