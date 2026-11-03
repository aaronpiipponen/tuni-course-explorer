# Graph and route algorithm experiments

Seven reports measure the prerequisite compiler and the minimum-credit route search, from the exact attempt to the report body the browser receives.

## The question the line asks

A prerequisite graph begins with one course and its requirement tree. The server compiles that tree into a [solver structure](/docs/reference/glossary.md#prerequisites-and-routes), and the same structure serves two readers. The [minimum route](/docs/reference/glossary.md#prerequisites-and-routes) search finds the courses that meet the [graph root](/docs/reference/glossary.md#prerequisites-and-routes) with the fewest [new credits](/docs/reference/glossary.md#prerequisites-and-routes). The drawing projection turns the structure into the [display pieces](/docs/reference/glossary.md#prerequisites-and-routes) and connections that the [prerequisite graph](/docs/backend/prerequisites/prerequisite-graph.md) shows in the **Prerequisites** tab.

A route answer carries more than a credit total. It states a [route outcome](/docs/backend/prerequisites/minimum-route.md#route-outcomes), the courses it charges, the requirements it leaves unresolved, the mark or exclusion that blocked a branch, and whether the answer is a proven minimum, an approximation or a refusal. The line treated that contract as part of the result, so a faster or smaller answer that changed one of those fields did not count as an improvement.

Seven questions followed:

1. Can the exact route be trusted on the captured catalogue, including where it must refuse to answer, and what may the calculation claim after its [allocation limit](/docs/reference/glossary.md#prerequisites-and-routes)?
2. Do the Python and TypeScript implementations return the same route from the same prepared structure?
3. Does solving each identical subexpression once make the exact search faster with the same route and the same occurrence evidence, which is the set of occurrence labels a route result attributes to each course? A structural subexpression is one subtree of a solver structure with its provenance fields ignored.
4. Why did four graph roots fail to prepare inside the time and memory caps, and which cycle cut fixes that without changing what the build returns?
5. Can one report carry the calculation and the drawing from two identities without losing the route? The measured report that carries both is called the compact report here.
6. How large is the report body, what does its projection cost, and what does the drawing allowance allow?
7. Can the compiler, the identities, the projection and the record view move into native code without changing a byte, and what does each move cost?

## The costs the line separates

The line keeps four costs apart that one request time hides.

| Cost | What it covers | Bound in these measurements |
|---|---|---|
| Compilation | Building one solver structure for a root from the catalogue, before any search or drawing | No product setting bounded it |
| Route search | The exact attempt over that structure and the one greedy pass after the allocation limit | `PREREQUISITE_PATH_MAX_COMPACT_NODES` at 700,000 compact nodes and traces, with no cap on the greedy pass |
| Drawing projection | Turning the structure into display pieces, connections and support bindings | `PREREQUISITE_GRAPH_MAX_ELEMENTS` at 500 elements decides whether the browser may draw the result |
| Payload | The serialized report body, raw and compressed | No product setting bounded it |

The separation matters because a limit on one cost does not bound another. The drawing limit decides what the browser may draw. In the baseline it did not bound the server's projection work or the bytes it sent, because the measured baseline projected, serialized and sent a drawing that the allowance refused. A refused drawing therefore also cost projection work and bytes. The compact report projects the drawing to its element count and reports no drawing when the allowance refuses it, but the limit does not bound compilation or solving.

## The build each measurement belongs to

The measurements of 9 and 10 October and of 19 and 20 October 2026 ran on a build whose compiler, drawing projector and route search were Python. That build is the subject of the compilation, route, payload, deduplication and compact results.

The product compiles the structure in native code, hashes the calculation and display identities there and calculates the route in the TypeScript solver. The 28 to 31 October measurements compare five native stages with the Python implementations they replaced, and they re-proved the calculation and display identities byte for byte.

One comparison spans both builds. [Route solver parity](/docs/experiments/graph-and-route-algorithms/route-solver-parity.md) compared the Python calculation with the TypeScript solver on the same prepared structure. The cycle rule and the two-identity model are part of the product, and [Native prerequisite compilation and identity](/docs/experiments/graph-and-route-algorithms/native-prerequisite-compilation.md) measures their cost.

## The reports

- [Minimum-credit routes](/docs/experiments/graph-and-route-algorithms/minimum-credit-routes.md) covers the bounded exact attempt, the greedy restart, the seven-case acceptance, the ordinary route comparison and two unresolved-rate samples.
- [Route solver parity](/docs/experiments/graph-and-route-algorithms/route-solver-parity.md) compares the Python and TypeScript implementations on the shared matrix and on a seeded 200-course spot check.
- [Structural route deduplication](/docs/experiments/graph-and-route-algorithms/structural-route-deduplication.md) tests a memo that solves one structural subexpression once per route calculation.
- [Cyclic graph compilation cost](/docs/experiments/graph-and-route-algorithms/cyclic-graph-compilation.md) asks where four failing graph roots spent their preparation time and which cycle cut bounded the work.
- [Compact graph identity](/docs/experiments/graph-and-route-algorithms/compact-graph-identity.md) asks whether one report can serve the calculation and the drawing from two identities, and what happens when their identities disagree.
- [Graph report payload and projection](/docs/experiments/graph-and-route-algorithms/graph-report-payload-and-projection.md) compares the compact report body, its projection stage, its drawing allowance and its route result with the earlier report.
- [Native prerequisite compilation and identity](/docs/experiments/graph-and-route-algorithms/native-prerequisite-compilation.md) measures five native stages against the Python implementations and the drawing endpoint in the completed product.

## Headline results

| Report | Run dates | Result that stands |
|---|---|---|
| [Minimum-credit routes](/docs/experiments/graph-and-route-algorithms/minimum-credit-routes.md) | 9 to 10 October 2026 | A bounded exact search with one greedy restart at 700,000 compact nodes. The three approximate routes charge 204.00, 211.00 and 194.00 new credits, one all-courses case returns a marked `search_too_large` failure, the two ordinary route reports with pre-edit baselines were byte-identical to them, and no unresolved-rate effect is established. |
| [Route solver parity](/docs/experiments/graph-and-route-algorithms/route-solver-parity.md) | 20 October 2026 | 506 of the 510 scenarios compared equal on every field. Four were not compared because preparation failed. |
| [Structural route deduplication](/docs/experiments/graph-and-route-algorithms/structural-route-deduplication.md) | 19 October 2026 | No material exact gain. Route outcome, credits and course set matched in all 330 paired comparisons, occurrence evidence differed in 117, and the mechanic was not promoted. |
| [Cyclic graph compilation cost](/docs/experiments/graph-and-route-algorithms/cyclic-graph-compilation.md) | 19 and 20 October 2026 | The four complete graph commands finish in 2.36 to 3.01 seconds under the applied cycle cut. In a separate comparison of 22 route commands, six Inferred-off outputs were byte-identical and the 16 Inferred-on outputs kept their state and total new credits, with two approximate course sets differing by one course each. The final comparison did not measure structure equality. A cycle-closing leaf built each of the four roots in 0.8 to 1.6 seconds at 107 to 114 MB resident in an in-process build, but it changed the structure in 13 of 22 matrix scenarios and changed five of 16 routes from exact to unresolved, so it was rejected. |
| [Compact graph identity](/docs/experiments/graph-and-route-algorithms/compact-graph-identity.md) | 19 and 20 October 2026 | A reversed-order counterexample forced two identities. The 22-case fixture matched the product in 21 cases, with one expected mismatch. |
| [Graph report payload and projection](/docs/experiments/graph-and-route-algorithms/graph-report-payload-and-projection.md) | 20 October 2026, against a baseline of 19 October 2026 | The body on MATH.MA.725 with Active only off fell from 92.98 MB raw to 3.60 MB raw and from 3.55 MB to 0.69 MB gzip. 104 of 110 route rows were identical, six were valid higher-credit approximate routes, and the allowance allowed 82 drawings and refused 28. |
| [Native prerequisite compilation and identity](/docs/experiments/graph-and-route-algorithms/native-prerequisite-compilation.md) | 28 to 31 October 2026 | Every compared output was byte-identical. The native compile cost 0.0024 to 0.0513 core-seconds against 0.6083 to 2.0297 for the Python compile and evaluation, the next-course endpoint took 3.57 to 5.62 times fewer core-seconds, and the drawing endpoint fell 66.4 to 86.7 percent on the official targets. |

## The matrix, the samples and what they share

### The dataset and the machines

The graph line read one selected dataset of the captured Tampere University curriculum, for the academic years 2006-2007 to 2026-2027 with a three-year activity window set by `ACTIVE_ACADEMIC_YEAR_WINDOW`. The example dataset that an installation loads is not this data. The [Experiments section](/docs/experiments/README.md) states the catalogue counts and the hardware of the other lines.

The 9 and 10 October measurements record no machine. The 19 and 20 October measurements ran read only on a 4-core aarch64 server with 24.1 GB of RAM. The 28 to 31 October measurements ran on an aarch64 Neoverse N1 machine with four logical cores and 24.1 GB of RAM, with PostgreSQL 18.6 and pgvector 0.8.6.

### The five toggle combinations

Every course in the shared matrix ran with five toggle combinations. Only the last one leaves Active only off.

| Combination | Recommended | Inferred | Active only |
|---|---|---|---|
| `required-only` | off | off | on |
| `recommended` | on | off | on |
| `inferred` | off | on | on |
| `recommended+inferred` | on | on | on |
| `recommended+inferred-active-off` | on | on | off |

### The courses and the bases

The matrix fixed eleven courses. The eight targets were MATH.MA.880, MATH.MA.725, PSY.324, KAT.MARK.399, KAT.MARK.310, KAT.MARK.304, KIE.SUY.420 and YKT.SOA.303. The three controls were COMP.CS.500, COMP.CS.110 and COMP.CS.200.

Each course ran with two [bases](/docs/reference/glossary.md#prerequisites-and-routes). The empty basis held no completed courses. The nonempty basis held the first up to five distinct active official course leaves in compiled tree order, excluding the target, taken from the default required-only active-only structure. MATH.MA.880 and YKT.SOA.303 had no eligible leaf in that structure, so their nonempty cases repeat the empty basis.

Eleven courses with five combinations and two bases give 110 scenarios. A matrix row names one course, one combination and one basis.

### The samples

The reports used different parts of the matrix and added samples of their own.

| Sample | Size | Report |
|---|---|---|
| Seven-case acceptance | 7 commands | [Minimum-credit routes](/docs/experiments/graph-and-route-algorithms/minimum-credit-routes.md) |
| Shared matrix | 110 scenarios | [Structural route deduplication](/docs/experiments/graph-and-route-algorithms/structural-route-deduplication.md), [Graph report payload and projection](/docs/experiments/graph-and-route-algorithms/graph-report-payload-and-projection.md), [Route solver parity](/docs/experiments/graph-and-route-algorithms/route-solver-parity.md) |
| Deduplication repetitions | 660 runs, 330 paired comparisons | [Structural route deduplication](/docs/experiments/graph-and-route-algorithms/structural-route-deduplication.md) |
| Parity spot check | 200 courses with 2 scenarios each, 400 scenarios | [Route solver parity](/docs/experiments/graph-and-route-algorithms/route-solver-parity.md) |
| Fixture set | 22 cases | [Compact graph identity](/docs/experiments/graph-and-route-algorithms/compact-graph-identity.md) |
| Four graph roots | 4 roots, 22 route commands, 48 parity rows | [Cyclic graph compilation cost](/docs/experiments/graph-and-route-algorithms/cyclic-graph-compilation.md) |
| Initial request profile | 10 courses with Active only on and off | [Cyclic graph compilation cost](/docs/experiments/graph-and-route-algorithms/cyclic-graph-compilation.md) |
| Unresolved-rate samples | 200 and 200 courses, with a 43-course source-bearing subset | [Minimum-credit routes](/docs/experiments/graph-and-route-algorithms/minimum-credit-routes.md) |
| Native stages | 5 recorded fact bundles, 5 drawing targets, 4 next-course requests, 101 final-matrix rows | [Native prerequisite compilation and identity](/docs/experiments/graph-and-route-algorithms/native-prerequisite-compilation.md) |

The seven cases were MATH.MA.880 and MATH.MA.725, each with and without Active only, plus KAT.MARK.310, KAT.MARK.304 and KAT.MARK.399 with Active only. All seven ran with Recommended on, Inferred off, an empty basis and no exclusion or node mark. The parity comparison read the 110 matrix scenarios and its own 400 spot-check scenarios, which gives 510 scenarios and 506 compared.

These counts do not form one sample. They differ in population, draw method and cap, and no value adds across them.

### The caps

The caps are separate measurement conditions, not one budget.

| Cap | Value | Where it applied |
|---|---|---|
| Allocation limit | 700,000 compact nodes and traces | Seven cases, matrix, compact passes, parity |
| Address-space cap | 4.295 GB | Matrix, parity, cyclic work, compact passes |
| Preparation or per-solve timeout | 120 s | Cyclic work, parity, compact passes |
| Whole-command cap | 10 s | Seven cases, one unresolved-rate sample |
| Command timeout | 300 s | Four final cyclic graph commands |
| Client wait | 240 s | Initial request profile |
| Drawing allowance | 500 elements | Compact passes, native drawing targets |
| Per-route cap | 20 s | Option-bearing unresolved-rate sample |

A capped case proves only that the command did not finish within its cap. A memory cap and a time cap fail differently. One of the four failing roots ended in a `MemoryError` under the 4.295 GB address-space cap, and three reached the 120-second preparation timeout. The allocation limit bounds the exact attempt, and the greedy restart has no allocation cap of its own.

### The measurement forms

The reports used four measurement forms, and the forms are not an end-to-end comparison.

| Form | What it times | Where |
|---|---|---|
| HTTP request with a 240 s client wait | The whole request, including response transfer | Initial request profile, baseline graph bodies |
| In-process, one scenario at a time, no HTTP | The stages inside one command | Deduplication, compact and payload passes, cyclic diagnosis, the Python side of parity |
| One Node subprocess per call | Whole subprocess wall time, including process startup | The TypeScript side of parity |
| Process core-seconds plus the database container delta | One endpoint call | Native stages |

Stage timers from an in-process pass do not sum to a request time. The compact baseline and the compact passes therefore compare server stages and body sizes, not browser latency.

The initial profile, the compact and payload passes and the four final cyclic commands took one run per case. The seven cases took one command each. The parity matrix ran once. The deduplication matrix took three repetitions per variant, and the native stage values are medians of three samples.

## What the line establishes

Four changes are in the product. The exact route is bounded at 700,000 compact nodes with one greedy restart. A cycle occurrence is dropped when an offered equivalent already sits on the ancestor path. The graph report carries ordered calculation pieces, order-independent display pieces and explicit support bindings. The compiler, the identities, the projection and the record view are native. Structural route deduplication was not promoted, and the cycle-closing leaf was rejected.

The line separates the bounded calculation from the command that contains it. The allocation limit bounds the exact attempt, not compilation or the greedy pass, so a command can miss a wall-clock cap while the calculation returns a valid approximate route or a marked failure. The approximate totals are what one greedy pass built from its ranking, not minima. The parity and cycle-cut results are empirical on one dataset and one machine per period. The parity comparison found no difference on its compared scenarios, and the applied cycle cut kept route outcome and total new credits, but the final comparison did not measure structure equality. Structural deduplication kept the route fields and changed occurrence evidence, which is why it was not promoted.

The report body and the native port are separate costs. The compact report cut the largest measured body and the projection stage, and it kept most route rows identical. The drawing allowance refused the drawings over 500 elements, and a refused drawing carries the solver structure, bindings and contexts. The native port returned byte-identical output and cut the next-course and drawing endpoints, but no measured case delivered the body over a network or rendered it in a browser, and no x86 host or other dataset was measured.

## What the line does not establish

- The cohorts in the samples table do not pool, and no value adds into one saving.
- No measurement joins the four costs into one route latency. Compilation, search, projection and payload were timed on separate boundaries, and some passes omitted one or more of them. No compressed body was delivered over a network, parsed or rendered.
- Every equality result is empirical on one dataset, one machine per period and the measured inputs. The native byte parity covers its five targets, nine saved bodies and 101 final-matrix rows, not every structure.

## Untested questions

Each question below is untested.

- Whether a course-count objective, or a course-count tie after credits, would select materially different requirement sets from the credit objective.
- Whether a lower or higher `PREREQUISITE_PATH_MAX_COMPACT_NODES` would keep ordinary output while moving more large structures to an approximate route, and how far the approximate totals sit from an exact minimum.
- Whether the four uncompared parity scenarios compare equal if the preparation memory or time limit were raised, and whether equality holds on another dataset or basis.
- Whether the dropped-occurrence rule under-counts new credits when an equivalent's own prerequisites cost more than the dropped branch saves, and whether its structure and route output equal the exact expansion on other roots.
- Whether sharing only large duplicate subtrees helps, and whether a memo entry can carry every occurrence's derivation rather than one representative derivation.
- Whether the six higher-credit approximate routes persist on another catalogue, another basis or another module drawing.
- Whether the smaller compressed body produces an end-to-end gain in a browser, including transfer, parse and render, and whether the native result holds on an x86 host, another dataset or a browser render.
- Whether the mark rules hold for a course with two identical module bodies and across a full client-state migration.
