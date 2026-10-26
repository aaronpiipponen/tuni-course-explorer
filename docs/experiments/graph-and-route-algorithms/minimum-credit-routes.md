# Minimum-credit routes

This report records the exact minimum-credit route calculation, its size limit and restart, and the comparison of its two implementations.

**Evidence status:** Corrected. **Run dates:** 9 to 10 October and 20 October 2026.

A claimed improvement in the unresolved rate was rejected as an unpaired comparison, and the first passing route totals were superseded after a solver correction.

The [Experiments section](/docs/experiments/README.md) states the catalogue and the evidence labels. The [glossary](/docs/reference/glossary.md) defines new credits, route outcome and allocation limit. The [Minimum route](/docs/backend/prerequisites/minimum-route.md) page states every outcome, what a route charges and the preference order. The [Minimum route solver](/docs/backend/prerequisites/minimum-route-solver.md) page describes the calculation as it stands. This report states what the experiments measured and where each measurement stopped.

## The question

A route calculation answers which courses meet a course's prerequisites with the fewest new credits. The calculation minimizes new credits, so two cheap courses can cost less than one expensive course. Every answer must also be explainable: which courses it charges, which requirements stay unresolved, which course or node mark blocked a branch, and whether the answer is a proven minimum, an approximation or a refusal.

Four questions shaped the work:

1. Could the exact calculation be trusted on the captured catalogue, including where it must refuse to answer?
2. What happens when an exact attempt grows too large to finish, and what may the calculation claim then?
3. Does the size limit and the added report fields leave an ordinary route's output the same?
4. Do the two implementations that then existed return the same route from the same prepared structure?

Two failure modes motivated the second question. An exact search that never finishes returns nothing, and an approximation that presents itself as a minimum is wrong. The work therefore separated three things that one timeout hides: the size of the exact search, the external wall clock of the command, and the outcome the calculation returns.

## What the calculation minimizes

A route costs the credits of every course it needs that the basis does not cover, each course counted once. The calculation minimizes that total. A course in the basis costs nothing, and the route does not expand that course's own prerequisites, so a basis course removes its requirement subtree from the calculation. A course that several branches need is charged once, and a distinct block of unexpandable content is charged its minimum credit once.

An exact candidate keeps two course sets apart. The witnesses are the courses that an enclosing credit or course-count requirement measures. The new-course closure is the complete set of not-basis courses the branch requires, and it is the only course cost set. A course can be a witness without being in the closure, and a shared course enters the closure once.

The logical and numeric rules are solved over those sets together, not branch by branch. An AND group needs every member, an OR group needs one, a cardinality node selects between its bounds, and a credit or course-count node measures its witnesses inside an inclusive bound. Expanded-course prerequisites and directional substitutions take part in the same global search. An unknown credit or count becomes a located unresolved problem instead of removing the known alternatives. A course cycle never becomes a takeable exact leaf, because a cycle is reported as a blocker rather than as a free course.

Two rules about unresolved structure follow from that. A known zero-cost candidate is exact even when an unresolved alternative went unused, because the known route already costs nothing. A positive known cost is unresolved when unknown structure could be cheaper. Incomplete inference coverage does not itself prevent an exact result for the published expression.

## The initial exact calculation

The initial exact calculation was one pure optimizer over the compiled requirement tree. It took the caller's canonical completion set and no visibility, repository, configuration or persistence input. It returned selected-course occurrence evidence, the satisfaction evaluation, copied inferred coverage and one of three outcomes: exact, unresolved or no solution. The later calculation also supported an active-only shortfall, carrying the maximum achievable under the activity scope and each deficient module rule. An unresolved or no-solution result carried no course list or credit total.

On the selected dataset the calculation returned an unresolved result with no courses and no total for one target. Solver work measured 0.38 to 0.48 seconds on that graph, and two other targets solved exactly below 0.01 seconds. A 10-second whole-command assertion from that work was rejected as mis-scoped. The bulk compiler reads consumed roughly 10 to 15 seconds before the route calculation began, so the assertion measured compilation rather than routing. End-to-end acceptance was left to the sizing work described below.

## The size limit and the restart

The exact attempt is bounded by an allocation size, not by elapsed time. The check counts the compact nodes and traces the exact attempt builds and raises when that count first exceeds `PREREQUISITE_PATH_MAX_COMPACT_NODES`. The calculation then abandons the exact attempt once and runs a single greedy pass with no allocation cap.

The greedy pass builds one valid route from the ranking it can see. Its route satisfies the source rules but is not a global minimum, and an activity shortfall it reports lists actual witnesses rather than a proved maximum. When no valid route is found, the result is `approximation_failed`, with no route, no total, and one root problem whose reason is `search_too_large`. That reason is an application size limit, not a wall-clock event. The app presents an approximate result as **Approximate route** and a failed restart as **No route found**.

```text
exact_attempt(structure, maxCompactNodes):
  count compact nodes and provenance traces while the exact PATH fold builds them
  abort once when the count first exceeds maxCompactNodes
  return the exact outcome

solve(structure):
  if the requirements are already satisfied or the root is excluded: return that outcome
  try exact_attempt(structure, PREREQUISITE_PATH_MAX_COMPACT_NODES)
  on the size-limit abort:
    run one scalar greedy pass with no allocation cap and no elapsed-time limit of its own
    if the greedy route is valid: return approximate route
    return approximation_failed with root problem reason search_too_large
```

The limit was calibrated by counting the compact nodes and traces allocated during the exact attempt, starting the clock when the exact attempt begins and giving the exact attempt a high temporary ceiling. Each command was capped externally at 10 seconds.

| Input | Flags | Sampled compact count | Solver seconds | Outcome under the external cap |
|---|---|---:|---:|---|
| MATH.MA.880 | recommended | 790,000 | 3.043 | unfinished at the cap |
| MATH.MA.880 | recommended, active only | 800,000 | 3.089 | unfinished at the cap |
| MATH.MA.725 | recommended | 320,000 | 1.338 | unfinished at the cap |
| MATH.MA.725 | recommended, active only | 140,000 | 0.632 | unfinished at the cap |
| KAT.MARK.310 | recommended, active only | under 20,000 | 0.134 | shortfall, total 0 |
| KAT.MARK.304 | recommended, active only | under 20,000 | 0.136 | shortfall, total 0 |
| KAT.MARK.399 | recommended, active only | about 60,000 | 1.533 | exact, total 180.00 |

A guarded profile of the largest structure reached 700,000 compact nodes and traces at 2.672 seconds, and the final calibration sampled 700,000 at 2.8841 seconds and 740,000 at 3.0379 seconds. The selected value is 700000 for `PREREQUISITE_PATH_MAX_COMPACT_NODES`, which keeps the trigger near three solver seconds. The instrumentation sampled every 10,000 entries and added small overhead, so the calibration is approximate.

Every command in the timing and acceptance tables ran under an external wall cap: 30 seconds in the first timings and 10 seconds for the later ones. The cap covers process startup, the database read, request compilation, the calculation and serialization. A capped row means that no complete report was produced. It is not a route outcome, and no state or credit is inferred for it.

## The attempt sequence

The same seven cases ran at every attempt: MATH.MA.880 and MATH.MA.725, each with and without active only, and KAT.MARK.310, KAT.MARK.304 and KAT.MARK.399. Recommended prerequisites were on, inferred prerequisites were off, the basis was empty, and no exclusion or node mark was set. The first timings measured the command body alone, not the whole subprocess. The later seven-case acceptance values cover complete commands, so the first times are not compared with the later ones.

The four mathematics cases:

| Attempt | Cap | MATH.MA.880 active only | MATH.MA.880 all courses | MATH.MA.725 active only | MATH.MA.725 all courses |
|---|---|---|---|---|---|
| Exact search, first timings | 30 s | no report | no report | no report | no report |
| Exact search | 10 s | no report | no report | no report | no report |
| Fallback, gate failed | 10 s | no report | no report | no report | no report |
| Bounded remediation, gate failed | 10 s | no report | no report | no report | no report |
| Passing attempt | 10 s | approximate, 218.00 cr, 8.255 s | marked failure, 7.743 s | approximate, 198.00 cr, 9.321 s | approximate, 194.00 cr, 9.119 s |
| Corrected re-run | 10 s | approximate, 204.00 cr, 7.291 s | marked failure, 6.256 s | approximate, 211.00 cr, 7.832 s | approximate, 194.00 cr, 7.505 s |

The three KAT cases:

| Attempt | Cap | KAT.MARK.310 | KAT.MARK.304 | KAT.MARK.399 |
|---|---|---|---|---|
| Exact search, first timings | 30 s | shortfall, 0 cr | shortfall, 0 cr | exact, 180.00 cr |
| Exact search | 10 s | shortfall, 0 cr, 2.83 s | shortfall, 0 cr, 2.79 s | exact, 180.00 cr, 7.74 s |
| Fallback, gate failed | 10 s | shortfall, 0 cr, 2.868 s | shortfall, 0 cr, 2.817 s | exact, 180.00 cr, 7.616 s |
| Bounded remediation, gate failed | 10 s | shortfall, 0 cr, 2.326 s, deficit 65 | shortfall, 0 cr, 2.386 s, deficit 65 | exact, 180.00 cr, 5.081 s |
| Passing attempt | 10 s | shortfall, 0 cr, 2.053 s | shortfall, 0 cr, 2.069 s | exact, 180.00 cr, 3.500 s |
| Corrected re-run | 10 s | shortfall, 0 cr, 0.889 s | shortfall, 0 cr, 0.896 s | exact, 180.00 cr, 2.078 s |

### The first two gates failed

The size-bounded fallback returned no complete report for the four mathematics cases under the 10-second cap, and the required seven-case gate was not passed. The three KAT cases completed: two shortfalls at zero credits and one exact route at 180.00 credits.

The bounded remediation that followed measured the exact allocation again and confirmed the 700,000 trigger near three solver seconds. It left the four mathematics cases at the cap, between 10.005 and 10.012 seconds, so it did not bring every case under the target. Those four rows are latency misses, not approximation failures, and the trigger and failure contract were not changed.

The whole-command ceiling was not reached by compiling the request alone. A bounded diagnostic, not an acceptance retry, measured MATH.MA.880 active only in two parts: 5.5 seconds of compilation and 59.0 seconds of exact PATH search that returned an exact route. The 30-second acceptance cap was reached inside that exact PATH fold, not during compilation. Those two component times exceed 30 seconds, so the diagnostic did not establish that the complete command fits the external 30-second command budget, and no whole-command time is inferred from it. A later profiled run of the compilation with a forced approximate pass spent 7.136 seconds compiling under profiler overhead and was filtering inside the greedy pass at the cap. No state or credit was inferred from either capped run.

### The passing attempt

The next attempt measured 1.541 seconds for the unprofiled compilation of the MATH.MA.880 all-courses structure. Its seven-case run returned a complete report for all seven cases under the 10-second cap. An initial batch and a final confirmation batch both ran, and both returned the same states. The table gives the final batch.

MATH.MA.880 active only returned an approximate route of 218.00 credits. MATH.MA.725 returned approximate routes of 198.00 credits active only and 194.00 credits all courses. MATH.MA.880 all courses returned `approximation_failed` with `search_too_large`, no route and no total. That is a marked failure returned under the cap, not a latency miss. The two KAT shortfalls stayed shortfalls at zero credits, and KAT.MARK.399 stayed exact at 180.00 credits.

The three KAT times in that attempt were lower than in the preceding attempts, and the mathematics cases completed instead of reaching the cap. The KAT outcomes and the KAT credit totals did not change.

### The scalar correction

The correction addressed additive-cost accounting and attested-node accounting, and it changed the greedy ranking. An attested node is a module or numeric node that a node mark records as manually completed. The calculation counts it as one satisfied witness and charges the credit minimum the node carries. The seven cases therefore ran again on the corrected revision. The states did not change, and two approximate totals moved.

| Case | Passing attempt (cr) | Corrected re-run (cr) |
|---|---:|---:|
| MATH.MA.880 active only | 218.00 | 204.00 |
| MATH.MA.725 active only | 198.00 | 211.00 |
| MATH.MA.725 all courses | 194.00 | 194.00 |

The chart compares the three approximate totals between the passing attempt and the corrected re-run.

![New credits of the three approximate large-case routes before and after the scalar correction. MATH.MA.880 active only falls from 218 to 204 credits, MATH.MA.725 active only rises from 198 to 211, and the all-courses MATH.MA.725 route is 194 credits in both.](/docs/charts/graph-route-minimum-approximate-credits.svg)

The totals moved in opposite directions: MATH.MA.880 active only fell from 218.00 to 204.00 credits and MATH.MA.725 active only rose from 198.00 to 211.00. Interpretation: an approximate total is what one greedy pass built from the changed ranking. The movements follow a correction to accounting and ranking, rather than a controlled comparison of approximation quality against an exact minimum. The corrected totals are the ones that stand.

### Where the time goes

A whole-command time combines request compilation, the exact attempt, the greedy pass and the remaining service time. The component timings wrapped those calls separately, so the components do not overlap, and each command's JSON output was byte-identical to the result the service returned.

| Case | Compilation (s) | Exact attempt (s) | Greedy pass (s) | Other (s) | Total (s) | Outcome |
|---|---:|---:|---:|---:|---:|---|
| MATH.MA.880 active only | 1.565 | 2.382 | 1.432 | 1.912 | 7.291 | approximate, 204.00 cr |
| MATH.MA.880 all courses | 1.542 | 2.349 | 0.531 | 1.835 | 6.256 | marked failure |
| MATH.MA.725 active only | 2.066 | 2.261 | 1.148 | 2.357 | 7.832 | approximate, 211.00 cr |
| MATH.MA.725 all courses | 1.998 | 2.342 | 0.828 | 2.337 | 7.505 | approximate, 194.00 cr |
| KAT.MARK.310 active only | 0.289 | 0.069 | 0.000 | 0.531 | 0.889 | shortfall, 0 cr |
| KAT.MARK.304 active only | 0.301 | 0.068 | 0.000 | 0.527 | 0.896 | shortfall, 0 cr |
| KAT.MARK.399 active only | 0.746 | 0.559 | 0.000 | 0.773 | 2.078 | exact, 180.00 cr |

The chart plots the stage times of the four large-case commands.

![Component times of the four large-case calculations after the scalar correction. Compilation takes 1.542 to 2.066 seconds, the exact attempt 2.261 to 2.382 seconds, and the greedy pass 0.531 to 1.432 seconds.](/docs/charts/graph-route-minimum-component-times.svg)

Compilation takes 1.542 to 2.066 seconds across the four cases, the exact attempt 2.261 to 2.382 seconds, and the greedy pass 0.531 to 1.432 seconds. An unprofiled compilation of the MATH.MA.880 all-courses structure took 1.541 seconds, while a profiled attribution of the same kind of compilation took 6.883 seconds, of which 239 scoped course reads took 4.665 seconds. The profiled figure is an attribution, not normal elapsed time, and the two are not compared.

## Ordinary route comparisons

The ordinary comparisons asked whether the added report fields and the size limit change a normal route. Four ordinary cases appear in the evidence: COMP.CS.110, COMP.CS.200, COMP.CS.500 and KIE.SUY.420.

COMP.CS.110 and COMP.CS.200 stayed exact with one new course and 5.00 credits each when the reports gained empty fields. Their course, module and credit fields were identical, and the drawing added availability locations for hidden inactive prerequisites: connector nodes rose from two to 15 for COMP.CS.110 and from one to nine for COMP.CS.200. That change is drawing only. A later retest of the same two returned exact again, one course (COMP.CS.100) and 5.00 credits each.

The initial pre-edit baseline was not captured. The first command failed settings validation, and the next failed database credential loading. No baseline was recorded or synthesized.

The size-limited reports were therefore compared with an uncapped exact run of the same checkout. COMP.CS.500 and KIE.SUY.420 returned exact reports that were byte-identical under the cap and without it. The active-only comparison returned 20.00 credits for COMP.CS.500 and 35.00 for KIE.SUY.420. That establishes capped and uncapped equality, but it cannot replace a pre-edit baseline.

A pre-edit baseline was captured before the final remediation: complete reports for COMP.CS.500 and KIE.SUY.420 with all courses, recommended prerequisites on, inferred prerequisites off and an empty basis. After the remediation both reports were identical to those baselines byte for byte, and the corrected revision repeated the comparison with the same result. COMP.CS.500 returned 14.00 credits and three courses, and KIE.SUY.420 returned 35.00 credits and seven courses.

One earlier saved KIE.SUY.420 result differs in its drawn node-state list: 143 action-key states there and 151 in the final result, with all 143 present and eight structural keys added. The route, the credits and the path outcome are equal, and the final capped report equals its uncapped counterpart in full.

## The unresolved-rate claim and its correction

A 200-course sample measured how often the calculation ends unresolved. Two samples exist, and a claim that compared them was rejected.

### The two samples

| Record | Population | Sample | Cap | Outcomes | Unresolved share |
|---|---|---|---|---|---|
| Earlier sample | active courses with a nonempty official prerequisite option | 200, fixed seed | 20 s per route | 163 exact, 5 no solution, 28 unresolved, 4 timeouts | 28 of 196, 14.29% |
| Later sample | active courses in a deterministic order derived from each identity | 200 | 10 s per whole command | 192 exact, 4 no solution, 3 unresolved, 1 timeout | 3 of 200, 1.5% |

The conservative reading of the earlier sample counts the timeouts with the unresolved cases and gives 32 of 200, or 16 percent. The conservative reading of the later sample gives four of 200, or 2.0 percent.

The two samples differ in three ways that matter. The earlier sample kept only active courses whose representative version had a nonempty official prerequisite option and drew 200 of them with a fixed seed. The later sample drew 200 active courses in a deterministic order derived from each identity with no option filter. The earlier cap was 20 seconds per route, and the later cap was 10 seconds for the whole command. The courses are not paired across the two samples.

The claim that the rate fell from 14.29 percent to 1.5 percent is rejected as an effect-size claim. It is not evidence that a corrected calculation improved the unresolved rate. Each figure stands only as a description of its own sample and cap, and the same course is not followed from one sample to the other.

### The source-bearing subset

Within the later sample, 43 courses carry at least one official prerequisite option. Those are the courses whose result can be traced to an official prerequisite of their own rather than to an empty requirement set.

| Metric | Count |
|---|---:|
| Sampled | 200 |
| Not represented | 0 |
| With an official prerequisite option | 43 |
| Attempted | 43 |
| Completed | 42 |
| Exact, no solution and unresolved among the completed | 35, 4 and 3 |
| Timed out at the 10 s cap | 1 (MATH.MA.721) |
| Errors or unattempted | 0 and 0 |

The shares are three of 42, or 7.14 percent, three of 43, or 6.98 percent, and four of 43, or 9.30 percent when the timeout joins the unresolved cases. These are observations on the revision at which the sample was saved, before the calculation corrections. They describe that revision and are not compared for effect size with the corrected calculation.

### The three unresolved cases

The three unresolved courses of the later sample were KIE.SUY.420, PSY.324 and YKT.SOA.303. Re-runs after the calculation corrections resolved two of them exactly and left the third over the cap.

KIE.SUY.420 first returned exact at 35.00 credits with zero courses and one 35-credit block of unexpandable content charged once. The final revision returned exact at 35.00 credits with seven courses and no unexpandable charge. An earlier explanation of that selection was incorrect. The selection follows the tie order: after equal new credits, the sorted new unexpandable-content identities decide, and the empty tuple of the seven-course route wins. The block appears in the graph with its source classification, and no course is invented for it.

YKT.SOA.303 returned exact at 45.00 credits and nine courses with no unexpandable charge. Two occurrences of a 25-credit module with no expandable members and one 20-credit nested constraint draw as obligations, and the chosen route uses neither occurrence as a charge. PSY.324 exceeded the 10-second cap in each affected-case attempt, was capped, and was not retried.

The two node marks changed only the calculated result. Completing the 35-credit block for KIE.SUY.420 returned exact at 0.00 credits without completing or adding any member course. Excluding it returned exact at 35.00 credits through another alternative, with the exclusion winning. Both results echoed the mark and left the shared selected and completed sets empty, so a module mark never entered shared course state.

## Route solver parity

The route calculation is one TypeScript solver. The browser runs it in a background worker, and the machine route command runs the same solver through Node. The parity comparison asked whether that solver and the Python calculation then in use returned the same route from the same prepared structure: the same outcome, new credits, route course set, problems, blockers, satisfaction and drawn box states.

### Inputs and method

The comparison read the selected dataset and ran one scenario at a time with no HTTP connection. Its matrix held 11 targets: MATH.MA.880, MATH.MA.725, PSY.324, KAT.MARK.399, KAT.MARK.310, KAT.MARK.304, KIE.SUY.420, YKT.SOA.303, COMP.CS.500, COMP.CS.110 and COMP.CS.200. Each target ran with two bases and five toggle combinations, which gives 110 scenarios.

The two bases were empty and nonempty. The empty basis had no completed courses. The nonempty basis held the first up to five distinct active official course leaves in compiled tree order, excluding the target, taken from the default required-only active-only structure and used for every combination. The five combinations were `required-only`, `recommended`, `inferred`, `recommended+inferred` and `recommended+inferred-active-off`. The first four apply Active only on, and the last applies Active only off.

The spot check drew 200 distinct canonical course identities from the sorted active catalogue with a fixed seed (20261020). Each sampled course ran two scenarios with the empty basis: required only active only, and recommended and inferred active only. That gives 400 scenarios.

Each scenario was prepared once, with the drawing included, so both solvers read the same solver structure, the same basis and the same configured allocation limit. The Python side ran the calculation in process and evaluated the node states for the drawing. The Node side ran one subprocess per call over standard input and read one JSON result from standard output.

Route results were compared field by field: state, total new credits, the new courses in order with their drawn nodes, new unexpandable work, selected nodes, lit members, shortfalls, blocked excluded courses and node keys, problems, facts by fact identity, covered courses by group identity, satisfaction, blockers and inferred coverage. Box states were compared by node identity on all four flags. Only the credit text rendering differed between the two wire forms, and it was compared by value after conversion to exact hundredths.

The first spot-check process ran 96 courses and stopped when its resident set reached the 4.295 GB address-space cap. The comparison then returned freed memory to the operating system after each course and ran at most 20 courses per process. The remaining 104 courses ran in six processes of at most 20 courses, and the resident set measured 143 MB to 149 MB after every course. No comparison or solver code changed. A later change to the comparison names a route-side failure instead of claiming a box-state comparison, and neither run had a route-side failure, so no result row changes.

### Results

| Run | Scenarios | Equal | Different | Uncompared | Box states compared |
|---|---:|---:|---:|---:|---:|
| Matrix, 11 targets | 110 | 110 | 0 | 0 | 110 |
| Spot check, 200 courses | 400 | 396 | 0 | 4 | 396 |

The matrix outcomes were identical in both solvers: 76 exact, 16 approximate, 14 unresolved, two `approximation_failed` and two no solution. The spot-check required-only scenarios were 200 exact. The spot-check recommended and inferred scenarios were 179 exact, 16 unresolved and one approximate, with four preparation outcomes instead of a comparison.

No difference occurred in either run, so no difference had to be judged as a correct requirement-level difference between the implementations.

### Timings and the Node boundary

| Course | Python median (ms) | Node median (ms) | Python max (ms) | Node max (ms) | Python total (ms) | Node total (ms) |
|---|---:|---:|---:|---:|---:|---:|
| MATH.MA.880 | 3656.1 | 3359.3 | 6665.9 | 6804.8 | 30739.1 | 28204.4 |
| MATH.MA.725 | 2665.7 | 1923.5 | 5132.3 | 3790.8 | 23148.5 | 17551.4 |
| PSY.324 | 445.8 | 545.9 | 3961.7 | 3046.1 | 14698.7 | 12517.0 |
| KAT.MARK.399 | 424.9 | 469.6 | 3807.6 | 2519.4 | 10608.3 | 8372.1 |
| KAT.MARK.310 | 39.4 | 132.8 | 402.8 | 514.8 | 921.9 | 1796.0 |
| KAT.MARK.304 | 39.2 | 143.0 | 402.4 | 484.3 | 960.0 | 1852.9 |
| KIE.SUY.420 | 17.8 | 90.8 | 28.7 | 108.6 | 184.2 | 921.4 |
| YKT.SOA.303 | 75.9 | 313.9 | 6424.6 | 6496.6 | 25388.6 | 24250.7 |
| COMP.CS.500 | 1.1 | 53.7 | 5.8 | 66.9 | 17.3 | 532.5 |
| COMP.CS.110 | 0.4 | 46.8 | 1.5 | 53.9 | 4.3 | 470.8 |
| COMP.CS.200 | 0.4 | 46.2 | 1.4 | 63.4 | 5.2 | 482.3 |

The Python column is the in-process solve call. The Node column is the whole subprocess wall time, including process startup of about 42 to 54 milliseconds. The totals sum the ten scenarios of one course, and the median is over those ten scenarios.

COMP.CS.110 solves in a median 0.4 milliseconds in process and 46.8 milliseconds through Node, so its Node time is startup rather than solving. The large cases are dominated by the solve: MATH.MA.880 has a Python median of 3656.1 milliseconds and a Node median of 3359.3 milliseconds, and its Python maximum is 6665.9 milliseconds against a Node maximum of 6804.8 milliseconds.

The spot check adds two subprocesses per scenario, one for the route and one for the box states. Its median Node time is 45 milliseconds and its maximum 5302 milliseconds, and its median Python time is 0.2 milliseconds and its maximum 5321 milliseconds. No scenario came near the 120-second side timeout.

These are process wall times on one server, not browser latency. They say nothing about how quickly a route appears in the app, and the equality result is empirical on this cohort rather than a proof for every structure.

### The four uncompared scenarios

Four recommended and inferred spot-check scenarios have no comparison. One preparation ended in `MemoryError` under the 4.295 GB address-space cap, and three exceeded the 120-second preparation timeout.

| Preparation outcome | Scenarios |
|---|---:|
| `MemoryError` under the 4.295 GB cap | 1 |
| Preparation timeout at 120 s | 3 |

The required-only scenario of each of the four courses is equal. Each uncompared scenario measures the Python structure build and drawing projection under the cap, before either solver runs, so it proves nothing about parity. The cap was not raised.

> [!IMPORTANT]
> The four uncompared scenarios are neither solver differences nor evidence of equality. They are preparation failures in one implementation, and the comparison records them separately from the 396 scenarios it compared.

## What stands

The unresolved-rate comparison does not stand. The two samples are unpaired in population, draw method, denominator and cap, so neither rate measures the effect of the calculation corrections. Each rate describes its own sample.

The route totals that stand are the corrected ones. MATH.MA.880 active only returns an approximate route of 204.00 credits, MATH.MA.725 active only one of 211.00 credits, and MATH.MA.725 all courses one of 194.00 credits. The 218.00 and 198.00 totals of the passing attempt are superseded. MATH.MA.880 all courses returns a marked `search_too_large` failure under the cap, and that failure is a returned outcome rather than a latency miss.

KIE.SUY.420 ends at seven courses and 35.00 credits with no unexpandable charge, and YKT.SOA.303 ends at nine courses and 45.00 credits. PSY.324 was never completed under the 10-second cap and has no route to report.

The ordinary route output for COMP.CS.500 and KIE.SUY.420 was byte-identical in every comparison: capped against uncapped on one checkout, and after the remediation and the correction against their pre-edit reports. The comparison of two implementations found no difference on any compared field.

## Limitations

The seven-case outcomes come from one dataset and one server, and the first timings have no repeat for confidence. The external caps are measurement limits, so a capped row proves only that the command did not finish in time. The allocation trigger bounds search size, not compilation time or total command time.

The approximate totals are not minima, and the greedy pass has no allocation cap of its own. The marked all-courses failure shows that a size-triggered restart can find no valid route for a structure that compiles.

The unresolved-rate samples are small and unpaired. The source-bearing subset has 43 courses, and its shares carry no reported interval. The three unresolved cases were re-run individually, not sampled again, so the corrected states of those three do not give a corrected rate for the 200-course sample.

The parity result covers one dataset, one server, one run and one seeded sample of 200 active courses. Its four uncompared scenarios are preparation failures, and its timings include Node process startup. Equality of two implementations on these scenarios is an empirical result, not a proof about every possible structure.

## Setup details

The measurements read one selected dataset of the captured Tampere University curriculum, for the academic years 2006-2007 to 2026-2027 with a three-year activity window. The catalogue held 11,086 courses, of which 4,543 were active, and 9,901 eligible module versions. The example dataset that an installation loads is not this data.

For the seven-case acceptance, recommended prerequisites were on and inferred prerequisites were off. The basis was empty and no exclusion or node mark was set, except where the node-mark cases say otherwise. The parity matrix adds its own toggle combinations and its nonempty basis. The allocation limit was 700000 for `PREREQUISITE_PATH_MAX_COMPACT_NODES`.

The whole-command times cover process startup, the database read, the request compilation, the calculation and serialization, and each case ran under its external cap. The component times were measured by wrapping the compilation, the exact attempt and the greedy pass separately, and the reported total is the service time.

The work ran on a 4-core aarch64 server with 23.6 GB of RAM. The parity comparison ran one scenario at a time under a 4.295 GB address-space cap, with 9.45 to 9.66 GB available before every process.

## Untested questions

1. Whether a course-count objective, or a course-count tie after credits, would select materially different requirement sets from the credit objective. The experiments measured credits only.
2. Whether a lower or higher `PREREQUISITE_PATH_MAX_COMPACT_NODES` would keep the same ordinary output while moving more large structures from a capped miss to an approximate route. Only 700,000 was measured for acceptance.
3. Whether the four uncompared parity scenarios would compare equal if the preparation memory or time limit were raised. The cap was not raised, so the question stayed open.
