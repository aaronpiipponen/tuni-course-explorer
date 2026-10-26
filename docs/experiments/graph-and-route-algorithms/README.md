# Graph and route algorithm experiments

Four experiments cover graph compilation, minimum-credit routes, route deduplication, and the graph report's structure, drawing and payload.

## The question the line asked

A prerequisite graph begins with one course and its requirement tree. The server compiles that tree into a [solver structure](/docs/reference/glossary.md#prerequisites-and-routes), and the same structure serves two readers. The [minimum route](/docs/reference/glossary.md#prerequisites-and-routes) search finds the courses that meet the [graph root](/docs/reference/glossary.md#prerequisites-and-routes) with the fewest [new credits](/docs/reference/glossary.md#prerequisites-and-routes). The drawing projection turns the structure into the [display pieces](/docs/reference/glossary.md#prerequisites-and-routes) and connections the [prerequisite graph](/docs/backend/prerequisites/prerequisite-graph.md) shows in the **Prerequisites** tab.

A route answer carries more than a credit total. It states a [route outcome](/docs/backend/prerequisites/minimum-route.md#route-outcomes), the courses it charges, the requirements it leaves unresolved, the mark or exclusion that blocked a branch, and whether the answer is a proven minimum, an approximation or a refusal. The line treated that contract as part of the result, so a faster or smaller answer that changed one of those fields did not count as an improvement.

Four questions followed:

1. Can the exact route be trusted on the captured catalogue, including where it must refuse to answer?
2. What happens when an exact attempt grows past its [allocation limit](/docs/reference/glossary.md#prerequisites-and-routes), and what may the calculation claim after the one greedy restart?
3. Why did four graph roots fail to compile inside 120 seconds or a 4.295 GB address-space cap, and which cycle cut fixes that without changing what the build returns?
4. Can identical structure be solved once, and can one report carry the calculation and the drawing from two identities without losing the route?

The first two belong to route search, the third to compilation, and the fourth to the solver and the report together. A further parity section asked a fifth question: do the Python and TypeScript implementations return the same route from the same prepared structure?

## The four costs

The line separates four costs that one request time hides.

| Cost | What it covers | Where the line measured it |
|---|---|---|
| Compilation | Building one solver structure for a root from the catalogue, before any search or drawing | The seven-case route commands, the 110-scenario tree build, and the compact compile stage |
| Route search | The exact attempt over that structure and the one greedy pass after the allocation limit | The seven-case component timings, the 110-scenario solve totals, and the parity solver calls |
| Drawing projection | Turning the structure into display pieces, connections and support bindings | The baseline graph profile and the compact project stage |
| Payload | The serialized report body, raw and compressed | The baseline and compact graph bodies |

The separation matters because each cost has its own limit. The exact route search is bounded by `PREREQUISITE_PATH_MAX_COMPACT_NODES`, set to 700,000 compact nodes and traces, and the greedy restart has no allocation cap. Drawing is bounded by `PREREQUISITE_GRAPH_MAX_ELEMENTS`, set to 500 elements, which decides whether the browser may draw the result. Compilation and payload have no product setting that bounds them in these measurements. A limit on one cost did not bound another.

The baseline graph profile shows the distinction in the measured costs. The drawing was fully built, serialized and sent even when the 500-element limit refused it. The drawing limit therefore bounded what the browser could draw, not the server's projection work or the payload it sent. A refused drawing also cost projection work and bytes.

## The order of the line

The order below is conceptual, not the order in which the runs were taken. It follows one root from the route it must answer, to the structure that route reads, to an attempt to share that structure, and to the report that carries it to the browser.

### Minimum-credit routes

[Minimum-credit routes](/docs/experiments/graph-and-route-algorithms/minimum-credit-routes.md) covers the route search from the first exact calculation through the allocation limit, the greedy restart and the scalar correction. The exact attempt is bounded by allocation size rather than elapsed time, and a calculation past 700,000 nodes abandons the exact attempt once and runs a single greedy pass. The report records the calibration of that limit near three solver seconds, the seven-case acceptance sequence, the ordinary route comparisons, two unresolved-rate samples and the parity comparison of the two implementations.

The result that stands is a bounded exact search with one approximate restart. The corrected seven-case totals are 204.00 credits for MATH.MA.880 active only, 211.00 for MATH.MA.725 active only and 194.00 for MATH.MA.725 all courses. MATH.MA.880 all courses returns a marked `search_too_large` failure under the cap rather than a route. The parity comparison found no difference in the 110-scenario matrix or in 396 of the 400 spot-check scenarios, and left four preparation failures uncompared.

### Cyclic graph compilation

[Cyclic graph compilation](/docs/experiments/graph-and-route-algorithms/cyclic-graph-compilation.md) asks where four graph roots spent their preparation time and why no output-preserving memo key made the build cheap. A cycle cut decides when a course occurrence closes a cycle instead of expanding again. The compiler unfolds every acyclic path through one dense cluster of equivalent courses, and the number of such paths is exponential. A key that kept only the ancestors a fragment can reach preserved 18 scenarios byte for byte but did not stop the growth, so the fix had to change where a cycle is cut.

The report records the rejected and applied cycle cuts. A cycle-closing leaf built each root in 0.8 to 1.6 seconds in process but changed the structure in 13 of 22 scenarios and turned five of 16 routes from exact to unresolved, so it was rejected. The applied rule drops an occurrence when an offered equivalent already sits on the ancestor path, with the root counted as an ancestor. The four complete graph commands took 2.36 to 3.01 seconds. The final comparison left six Inferred-off outputs byte-identical and route outcome and credits equal on 16 Inferred-on outputs, and it did not preserve structure identity. Two approximate course sets differ by one course.

### Structural route deduplication

[Structural route deduplication](/docs/experiments/graph-and-route-algorithms/structural-route-deduplication.md) tested a memo that solves one structural subexpression once per route calculation. The identity keeps the fields that change evaluation and drops provenance, so an official option and an inferred option can share a solve. Provenance is the origin, official kind, inferred category and inference metadata of a source node. The memo key also carries the [basis](/docs/reference/glossary.md#prerequisites-and-routes), the activity exception, whether a module shortfall is allowed, the mark state and the relative cyclic occurrences, and the memo is disabled when an exclusion or a [node mark](/docs/reference/glossary.md#prerequisites-and-routes) is present.

The experiment used eleven courses, 110 scenarios and three repetitions per variant, which gives 660 runs and 330 paired comparisons. The route outcome, total new credits and course set matched in every comparison. The exact search did not become materially faster. Exact scenarios above 10 ms stayed between 0.92x and 1.16x, the whole matrix ran from 0.53x to 1.86x, and 18 scenarios exceeded the allocation limit in both variants. Occurrence evidence differed in 117 of the 330 comparisons. The mechanic was not promoted.

An occurrence here is one position where a structural subexpression appears. Occurrence evidence is the set of occurrence labels a route result selects and attributes to each course. A reused subexpression reconstructs one valid derivation from the representative occurrence, while the baseline exact search unions the labels of every valid derivation. That is why the route could match while the labels did not.

### Compact graph identity and projection

[Compact graph identity and projection](/docs/experiments/graph-and-route-algorithms/compact-graph-identity-and-projection.md) asks whether one report can serve the calculation and the drawing from two structures, and what happens when their identities disagree. The design started from one content-addressed piece graph, with display pieces keyed by the containing course and the piece identity.

A small fixture reversed that assumption. Official `OR(a, b)` and inferred `OR(b, a)` produce one display piece, because the display fingerprint sorts its children, while the ordered calculation identity produces two piece IDs. The display conversion refused that display piece and reported that it spans two scoped identities. The report therefore keeps an ordered calculation identity and an order-independent display identity, joined by explicit [support bindings](/docs/reference/glossary.md#prerequisites-and-routes) from each calculation support to the display pieces and marks it covers. That is the identity lesson the line carries. A display piece can stand for more than one [calculation piece](/docs/reference/glossary.md#prerequisites-and-routes), and the report has to state which calculation pieces and marks a display piece covers.

Before the measured matrix, a fixture set of 22 cases compared the two-structure result with the product. Twenty-one matched, and one control without the cycle marker mismatched exactly as predicted.

The measured matrix then compared the two-structure report with the earlier report over 110 cases. The two bodies use different schemas, so the comparison is whole body against whole body. In the first compact pass, the whole body on MATH.MA.725 active off fell from 92.98 MB to 3.52 MB raw, and from 3.55 MB to 0.68 MB compressed. That pass omitted member closures and conditional module obligations, which the first correction restored.

The maximum projection after the first correction was 15,706.5 ms, then 593.5 ms after the second correction and 600.5 ms in the module-drawing pass. The connection gate table on the YKT.SOA.303 case with active only off fell from 38,523 to 2,845 records after the second correction, then rose to 3,348 in the final pass. The final pass kept 104 of the 110 cases identical, recorded six valid approximate cases with higher credit totals, allowed 82 drawings and refused 28 at 500 elements. It recorded no parity for the new unexpandable content.

## Headline results

| Report | Run date | Question | Result that stands |
|---|---|---|---|
| Minimum-credit routes | 9 to 10 October and 20 October 2026 | Can the exact route be bounded and restarted, and do two implementations agree? | Corrected approximate totals of 204.00, 211.00 and 194.00 credits, one marked size failure, 506 parity scenarios compared and equal, and four uncompared |
| Cyclic graph compilation | 19 and 20 October 2026 | Why did four roots fail to compile, and which cycle cut fixes it? | Four roots that hit the cap finish as commands in 2.36 to 3.01 seconds, with route outcome and credits preserved but structure identity not |
| Structural route deduplication | 19 October 2026 | Does solving each identical subexpression once make the exact search faster with the same result? | No consistent exact gain, route fields equal in 330 paired comparisons, occurrence evidence different in 117, not promoted |
| Compact graph identity and projection | 19 and 20 October 2026 | Can one report carry calculation and drawing from two identities without losing the route? | A reversed-order counterexample forced two identities, projection maxima of 15,706.5, 593.5 and 600.5 ms across the corrected passes, 104 identical cases and six higher-credit approximate cases, 82 allowed and 28 refused, no unexpandable content parity |

The route line ends with a bounded calculation and a parity result. The exact solver does not finish every measured structure. The compilation line ends with four complete graph commands of 2.36 to 3.01 seconds, under a rule that changes structure where an equivalence offer reaches an ancestor. The deduplication line ends without a product change. The compact line ends with a smaller body than the baseline on four large cases: MATH.MA.880 and MATH.MA.725, each with Active only on and off. Its maximum projection stage is lower, with 104 of 110 cases identical and six valid approximate cases that differ.

## The matrix, the samples and what they share

The graph line read one selected dataset of the captured Tampere University curriculum, for the academic years 2006-2007 to 2026-2027 with a three-year activity window set by `ACTIVE_ACADEMIC_YEAR_WINDOW`. The catalogue holds 11,086 courses, of which 4,543 are active, and 9,901 eligible module versions. The example dataset an installation loads is not this data. Every measurement ran read only on one 4-core aarch64 server with 23.6 GB of RAM.

The shared matrix fixed eleven courses. The eight targets were MATH.MA.880, MATH.MA.725, PSY.324, KAT.MARK.399, KAT.MARK.310, KAT.MARK.304, KIE.SUY.420 and YKT.SOA.303. The three controls were COMP.CS.500, COMP.CS.110 and COMP.CS.200. Each course ran with five toggle combinations and two bases, which gives 110 scenarios. The five combinations were `required-only`, `recommended`, `inferred`, `recommended+inferred` and `recommended+inferred-active-off`. The bases were an empty basis and the first up to five distinct active official course leaves in compiled tree order, excluding the target. MATH.MA.880 and YKT.SOA.303 had no eligible leaf in that default tree, so their nonempty cases repeat the empty basis.

The reports used different parts of the matrix. The seven-case acceptance used MATH.MA.880 and MATH.MA.725, each with and without active only, plus KAT.MARK.310, KAT.MARK.304 and KAT.MARK.399. The deduplication experiment ran the 110 scenarios three times per variant, which gives 660 runs. The compact report measured one pass per version of the code and ran four passes. The parity comparison used the 110 scenarios and added a spot check of 200 active courses with two scenarios each, which gives 400 scenarios. These counts do not form one sample.

The limits and caps are separate measurement conditions. The allocation limit was 700,000 in the seven-case acceptance, the deduplication matrix, the compact passes and the parity comparison. The later seven-case commands ran under a 10-second external cap that covered process start, the database read, compilation, the calculation and serialization. The deduplication and compact passes ran under a 4.295 GB address-space cap, one case at a time, with 120-second limits. The cyclic work used a 4.295 GB cap and a 120-second preparation timeout, with a 300-second command timeout for the final timings. A capped case proves only that the command did not finish in time.

Two measurement forms appear. The baseline graph and route profile went through HTTP with a 240-second client wait, and its request time includes transfer. The deduplication, compact and parity measurements ran locally, one scenario at a time, with no HTTP connection. Stage timers from the in-process passes do not sum to a request time, and the two forms are not an end-to-end comparison. The compact baseline and the compact passes therefore compare server stages and body sizes, not browser latency.

The unresolved-rate samples are separate from all of these. One sample drew 200 active courses whose representative version had a nonempty official prerequisite option, with a fixed seed and a 20-second cap per route. The other drew 200 active courses in a deterministic order derived from each identity, with a 10-second cap per whole command. The source-bearing subset of the later sample is 43 courses, of which 42 completed. Those cohorts are not paired with each other or with the seven-case acceptance.

The line ran in two periods. The route work ran on 9 and 10 October 2026, and the graph, deduplication, parity and compact work ran on 19 and 20 October 2026.

## Corrections and reversals

| Earlier result | Correction | Result that stands |
|---|---|---|
| An unresolved share of 14.29 percent fell to 1.5 percent, read as a paired improvement | The samples differ in population, draw method, denominator and cap, and the courses are not paired | Each rate describes its own sample, with conservative readings of 16 percent and 2.0 percent. No effect size stands. |
| The passing seven-case totals were 218.00, 198.00 and 194.00 credits | The scalar correction changed additive-cost accounting and the greedy ranking | 204.00, 211.00 and 194.00 credits, with the same route outcomes |
| The first deduplication control run returned a route | It promoted an empty-support partition into a zero-cost route. A separate first structural key exhausted the address space on a tree with 123,883 occurrences | Reuse skips empty-support partitions. Both pre-fix runs are excluded from the 660 runs. |
| Solving each subexpression once would make the exact search faster with the same evidence | The exact search showed no consistent direction, and a reused obligation reconstructs one derivation | No material exact gain, 117 evidence differences, and the mechanic was not promoted |
| One scoped calculation piece could identify one display piece | Official `OR(a, b)` and inferred `OR(b, a)` produce one display piece from two ordered pieces, and the conversion refused it | The applied report has two identities, with an explicit binding from each calculation support to the display pieces and marks that support covers |
| The initial compact report reached a 386 ms maximum projection | That projection omitted the member closures and conditional module obligations the first correction restored | 15,706.5 ms at the first correction, 593.5 ms after the second, and 600.5 ms in the module-drawing pass |
| The compact report kept 108 identical cases and two equal-credit approximate differences | The module-drawing pass changed which valid route the bounded approximate search returns | 104 identical cases and six valid approximate cases with higher credit totals. No exact route differs. |
| The [drawing allowance](/docs/reference/glossary.md#prerequisites-and-routes) allowed 80 cases and refused 30 | Structural module drawing changed the element counts | 82 allowed and 28 refused at 500 elements |
| A cycle-closing leaf made the four roots cheap | It changed the structure in 13 of 22 scenarios and turned five of 16 routes from exact to unresolved | The leaf was rejected. The dropped occurrence was selected and applied. |

The applied cycle cut changes output where an equivalence offer reaches an ancestor. It drops an occurrence when an offered equivalent already sits on the ancestor path, with the root counted as an ancestor, and it runs only with inferred prerequisites on and the occurrence offered equivalences. The rule leaves acyclic structures and structures without equivalence offers as they are. The final comparison left six Inferred-off outputs byte-identical and route outcome and credits equal on 16 Inferred-on outputs. It did not compare structure before and after the cut, and two approximate course sets differ by one course.

Two earlier route results were also corrected. KIE.SUY.420 first returned exact at 35.00 credits with a single 35-credit block of unexpandable content and no courses. It ends at 35.00 credits with seven courses and no unexpandable charge. The selection follows the tie order, where the seven-course route has an empty tuple of new unexpandable content identities, which wins after equal new credits. YKT.SOA.303 ends at nine courses and 45.00 credits. PSY.324 exceeded the 10-second cap in each affected attempt and has no route to report.

## What the line applied

| Change | Status | What the evidence covers |
|---|---|---|
| Exact route bounded at 700,000 compact nodes with one greedy restart | Selected and applied | Seven-case acceptance and the 110-scenario matrix |
| Occurrence dropped when an offered equivalent is already an ancestor | Selected and applied | Four roots and 22 route commands |
| Two-structure graph report with ordered calculation pieces, order-independent display pieces and support bindings | Applied | 22 fixture cases and four 110-case passes |
| Shared TypeScript route solver for the browser and the machine route command | In use | 506 compared parity scenarios |
| Structural route deduplication | Not promoted | 330 paired comparisons |

The ordinary route output did not move for COMP.CS.500 and KIE.SUY.420. Both returned reports byte-identical to the pre-edit baselines captured before the final remediation, and the corrected revision repeated the comparison with the same result. COMP.CS.500 returned 14.00 credits and three courses, and KIE.SUY.420 returned 35.00 credits and seven courses. One earlier saved KIE.SUY.420 result differs in its drawn node-state list, with the route, the credits and the outcome equal.

## What the line does not establish

- The four reports are not one comparison. They use different versions of the code, different cohorts and different cost boundaries, so their values do not add into one saving and their counts do not form one shared cohort.
- The approximate totals are not minima. The 204.00, 211.00 and 194.00 credit results are what one greedy pass built from its ranking, and the six compact cases with higher credit totals are valid routes, not optimality evidence.
- The cycle cut changes structure wherever an equivalence offer reaches an ancestor. Equal route outcomes and credits on the 16 Inferred-on commands do not establish structure identity, and the final structure was not compared with the exact expansion.
- The compact pass is in process. It measured compilation, projection, solving and serialization, not HTTP transfer, browser parsing or rendering. It delivered none of its compressed bodies over a network.
- The compact comparison has no parity for the new unexpandable content, because the baseline report held no such field. Six cases differ, so the line does not establish parity for every case.
- The drawing limit bounds what the browser may draw. It does not bound compilation, solving or the body the server builds and sends.
- No measurement joins the four costs into one route latency. Compilation, search, projection and payload were timed on separate boundaries, and some passes omitted one or more of them.
- The parity result covers one dataset, one server and one seeded sample. Four scenarios were not compared because preparation failed, and equality on the rest is empirical rather than a proof about every structure.

## Untested questions

Each question below is untested.

- Whether a course-count objective, or a course-count tie after credits, would select materially different requirement sets from the credit objective.
- Whether a lower or higher `PREREQUISITE_PATH_MAX_COMPACT_NODES` would keep the same ordinary output while moving more large structures from a capped miss to an approximate route.
- Whether the four uncompared parity scenarios would compare equal if the preparation memory or time limit were raised.
- Whether the dropped-occurrence rule under-counts new credits when an equivalent's own prerequisites cost more than the dropped branch saves.
- Whether the final cycle-cut structure and route output equal the exact expansion on other roots, other datasets or with active only off.
- Whether sharing only large duplicate subtrees keeps the exact attempt below the allocation limit or lowers the tree build and payload cost.
- Whether a memo entry can carry every occurrence's derivation, rather than one representative derivation, and preserve the selected occurrence set exactly at an acceptable cost.
- Whether the six higher-credit approximate routes persist on another catalogue, another basis or another module drawing.
- Whether the smaller compressed body produces an end-to-end gain in a browser, including transfer, parse and render.
