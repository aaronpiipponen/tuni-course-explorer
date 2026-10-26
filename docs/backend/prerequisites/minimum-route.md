# Minimum route

A minimum route calculation returns the set of courses that meets a course's prerequisites with the fewest new credits.

## Fewest new credits

A route holds the courses a requirement needs and the basis does not cover. Its cost is the [new credits](/docs/reference/glossary.md#prerequisites-and-routes) of exactly those courses, each counted once. Course count never decides the route, so two cheap courses can cost less than one expensive course.

## One structure and one basis

An explicit calculation starts from the solver structure of the graph report the pane already holds. The graph read resolves the root, the toggles and the activity scope, compiles one solver structure, and returns it with the drawing. The calculation reads that structure without a second graph read or a second compilation, so the drawing and the calculation describe the same requirement set and cannot drift apart.

The browser combines the live profile inputs with the held structure on a shallow copy: the excluded courses and the two node-mark lists replace the structure's own values, and **Route basis** chooses either the completed set or every selected course. Both choices have the same effect: a course in the basis satisfies its requirement at no new cost, and its own prerequisites are not expanded below it. The held report is never mutated.

A site bounds the inference toggle. When `WEB_INFERENCE_ENABLED` is false in that site's `config/web.toml`, the graph read compiles no inferred prerequisite whatever the request asks for, so the held structure is official-only and the calculation from it is official-only. The switch bounds that read alone: official data is untouched, the toggle the browser saved in the profile is untouched, and the machine route command and the script adapter are the same on both kinds of site.

The calculation returns its own result and no drawing. The graph read and the compiler behind it are described in [Prerequisite graph](/docs/backend/prerequisites/prerequisite-graph.md).

## Exact by default

A calculation computes the exact route by default. `PREREQUISITE_PATH_MAX_COMPACT_NODES` in `config/search.toml` sets the [allocation limit](/docs/reference/glossary.md#prerequisites-and-routes), the largest size the exact attempt may build, and the example sets 700000. [Minimum-credit routes](/docs/experiments/graph-and-route-algorithms/minimum-credit-routes.md#the-size-limit-and-the-restart) gives the calibration of the limit and the measured greedy restart. The web response carries the configured value as `max_compact_nodes` beside the serving dataset identity, and the browser worker passes it to the solver. The machine route command reads the same setting and passes it to the same solver. When the exact attempt grows past that size, the calculation abandons it once and runs a single greedy search instead, so an oversized calculation returns an approximate route or a No route found result. The limit bounds the exact attempt only.

| Key | Meaning | Example |
|---|---|---|
| `PREREQUISITE_PATH_MAX_COMPACT_NODES` | The largest size the exact route attempt may build before the calculation runs one greedy search instead | 700000 |

The setting is a positive integer.

## Route outcomes

Every calculation ends in one [route outcome](/docs/reference/glossary.md#prerequisites-and-routes), and the app shows it as one label.

The diagram follows one route calculation from the solver structure through the exact search, the configured size limit, and the greedy search to the six outcomes.

![One exact search reads the same solver structure and basis as the graph. When the size limit is not exceeded, the exact search yields the exact minimum route, a shortfall from a reduced route, an unresolved route, or no route under the rules. When the size limit is exceeded, one greedy restart yields an approximate route or no route found.](/docs/diagrams/minimum-route-outcomes.svg)

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

Excluding a course blocks every route through it. The excluded course never counts as covered and never appears in the route, while its own prerequisites are usable through another route that does not pass through it. Excluding the graph root leaves the whole calculation with no route.

## The order of preference

A calculation minimizes the new credits first. When several routes share the lowest total, it prefers the route with the fewest distinct inactive new courses. When those rules leave a tie, the deterministic canonical identities decide, compared in sorted order: the new unexpandable content identities, the new course identities, and the witness identities. The same inputs always return the same route.

## What the result reports

Besides the route, a result carries the total new credits and the full route total, which adds the credits of the covered courses to the new credits. The course rows pair each new course with the drawn boxes it satisfies, name the covered courses the witnesses measure, and give the new unexpandable content with its credit minimum. The result also carries the excluded courses and excluded nodes that blocked a requirement, the located problems of the requirements the search denied, and the drawn nodes and lit member IDs the winning route selects. A Shortfall result carries one record per deficient module rule.

## The panel and the graph

The panel states both totals on one line, and it states the outcome label when the result carries no total. It adds a note for **Approximate route**, **No route found**, **No route exists**, **Route unresolved** and **Shortfall**. It lists the located problems for **No route exists**, **Route unresolved** and **No route found**, and the deficient module rules for **Shortfall**. The course rows and the unexpandable content rows appear for **Exact minimum route**, **Approximate route** and **Shortfall**, behind **Expand**, and **Add all missing courses to structure** adds the new courses to Unplaced studies. An exact route with no new credits reads **Nothing new**.

The graph lights the drawn nodes and connections of the selected route and dims the rest. For **No route exists** and **Route unresolved** it lights the problem nodes and the blocked node keys instead, and a **No route found** result lights the graph root alone.

## Repeated calculations

The route appears only after an explicit click. While a route is shown, the control reads **Clear minimum route** and a click clears it. Changing an input, leaving the pane or remounting the pane clears the visible route as well, and returning to earlier inputs does not bring it back.

A successful calculation joins the same bounded browser-memory cache that holds the graph reports. Its key covers the dataset identity, the structural graph key, every live route input and the allocation limit, so a changed basis, course set or mark never answers from another input's value. After the visible route is cleared, the control reads **Find minimum route** again, and a click with the same inputs shows the held value without a worker. The cache is never written to a profile or to browser storage.

The exact search, its pruning, and the greedy restart are described in [Minimum route solver](/docs/backend/prerequisites/minimum-route-solver.md).
