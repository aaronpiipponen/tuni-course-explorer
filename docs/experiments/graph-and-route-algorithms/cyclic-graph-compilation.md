# Cyclic graph compilation blowup

This report records why four prerequisite graph roots could not be prepared under 120 seconds or a 4.295 GB cap, and which cycle cut fixed it.

**Evidence status:** Corrected. **Run dates:** 19 and 20 October 2026.

## The question

The **Prerequisites** tab compiles one solver structure per graph root and projects a drawing from it. With Recommended and Inferred on, four spot-checked roots either reached a 120-second preparation timeout or exhausted a 4.295 GB address-space cap. The investigation asked where the time went, whether the compiler, the drawing projection or the route solver caused it, and whether the structure build could be made cheap without changing what it returns.

The route solver reads the same solver structure and is a separate calculation. The first profile therefore measured graph reads and route reads independently. The diagnosis then ran the compiler in process with no HTTP request, so network transfer and client waiting could not be mistaken for compile time. The compiler, its pieces and its projection are described in [Prerequisite compiler](/docs/backend/prerequisites/prerequisite-compiler.md). The exact search and its bounded approximation are described in [Minimum route solver](/docs/backend/prerequisites/minimum-route-solver.md).

The answer was that the compiler unfolds every acyclic path through one dense cluster of equivalent courses. An acyclic path visits no course twice, and the number of such paths through that cluster is exponential. No memo key tried could share the distinct trees, and no output-preserving polynomial build was found. A fix has to change where a cycle is cut.

## Scope and fixed inputs

The four graph roots are labelled Root A to Root D in the order of the final timing table. They are identified by canonical course identity, not by course code.

| Item | Value |
|---|---|
| Dataset | One selected dataset |
| Graph roots | Four spot-checked roots, Root A to Root D |
| Initial profile courses | MATH.MA.880, MATH.MA.725, PSY.324, KAT.MARK.399, KAT.MARK.310, KAT.MARK.304, KIE.SUY.420, COMP.CS.500, COMP.CS.110, COMP.CS.200 |
| Toggles | Recommended on, Inferred on |
| Activity scope | Active only on for the diagnosis and the final timings, on and off for the initial profile |
| Course state | Empty for the initial profile, not separately recorded for the four graph timing commands |
| Display | Drawing projection enabled |
| Address-space cap | 4.295 GB |
| Preparation timeout | 120 seconds |
| Command timeout | 300 seconds for the final timing commands |
| Available memory | About 9.6 GB before the capped diagnosis |
| Isolation | One course at a time, foreground, no HTTP request |

The run used a 4-core aarch64 server with 23.6 GB of RAM. The available-memory figure is the free-memory check before the capped diagnosis, not a fixed hardware condition.

One root ended in a `MemoryError` under the 4.295 GB cap. The other three reached the 120-second preparation timeout. The required-only scenario of each of the four roots completed in both solvers with equal results, so the failures were preparation limits under Recommended and Inferred, not solver differences. The cap was not raised for the diagnosis.

The route comparison used eight course codes with Inferred on, each with and without Recommended, and three course codes with Inferred off, each with and without Recommended. The parity comparison used the same four roots and the route solver through Node.

## Initial request profile

The initial profile ran the 10 listed codes with Active only on and off. It used one repetition per row, an empty course state, Recommended and Inferred on, and the web routes for the graph and the route. The compile, projection, satisfaction and serialization columns are separate in-process measurements of the same command functions. They are not the HTTP request's own timing and do not sum to the graph wall time.

| Course | Active only | Graph (s) | Route (s) | Route state | Compile (ms) | Projection and prepare (ms) | Satisfaction (ms) | Serialization (ms) | Solver (ms) | Route CPU (s) |
|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|
| MATH.MA.880 | on | 3.89 | 8.24 | approximate | 2,915 | 502 | 239 | 81 | 4,449 | 7.3 |
| MATH.MA.880 | off | 13.10 | 15.47 | approximation_failed | 4,395 | 5,664 | 1,996 | 339 | 4,906 | 14.4 |
| MATH.MA.725 | on | 12.47 | 17.84 | approximate | 6,188 | 5,103 | 771 | 518 | 5,580 | 16.4 |
| MATH.MA.725 | off | 28.40 | 30.34 | approximate | 7,609 | 15,578 | 3,414 | 875 | 6,479 | 28.9 |
| PSY.324 | on | 1.97 | 5.92 | approximate | 1,621 | 59 | 32 | 13 | 3,729 | 5.2 |
| PSY.324 | off | 2.30 | 5.65 | approximate | 1,649 | 219 | 117 | 29 | 3,745 | 4.9 |
| KAT.MARK.399 | on | 2.51 | 3.14 | unresolved | 1,939 | 167 | 109 | 32 | 692 | 2.3 |
| KAT.MARK.399 | off | 2.90 | 6.14 | unresolved | 2,386 | 399 | 225 | 90 | 3,343 | 5.3 |
| KAT.MARK.310 | on | 1.25 | 1.37 | unresolved | 1,128 | 40 | 20 | 7 | 92 | 0.8 |
| KAT.MARK.310 | off | 1.35 | 1.95 | unresolved | 1,100 | 63 | 27 | 11 | 480 | 1.3 |
| KAT.MARK.304 | on | 1.27 | 1.30 | unresolved | 1,072 | 40 | 17 | 7 | 86 | 0.8 |
| KAT.MARK.304 | off | 1.99 | 1.67 | unresolved | 1,015 | 67 | 29 | 10 | 473 | 1.1 |
| KIE.SUY.420 | on | 0.83 | 0.76 | exact | 562 | 24 | 7 | 4 | 25 | 0.4 |
| KIE.SUY.420 | off | 0.83 | 0.79 | exact | 613 | 39 | 14 | 7 | 36 | 0.5 |
| COMP.CS.500 | on | 0.36 | 0.26 | exact | 135 | 1.7 | 0.6 | 0.4 | 1.5 | 0.1 |
| COMP.CS.500 | off | 0.26 | 0.34 | exact | 137 | 7.2 | 2.6 | 1.0 | 6.8 | 0.2 |
| COMP.CS.110 | on | 0.31 | 0.28 | exact | 108 | 0.4 | 0.1 | 0.1 | 0.5 | 0.2 |
| COMP.CS.110 | off | 0.25 | 0.24 | exact | 104 | 1.7 | 0.7 | 0.4 | 1.6 | 0.1 |
| COMP.CS.200 | on | 0.23 | 0.56 | exact | 97 | 0.4 | 0.1 | 0.1 | 0.5 | 0.2 |
| COMP.CS.200 | off | 0.23 | 0.23 | exact | 99 | 1.7 | 0.6 | 0.3 | 1.6 | 0.1 |

The graph reads took 0.23 to 28.40 seconds and the route reads 0.23 to 30.34 seconds. On MATH.MA.725 with Active only off, the graph read took 28.40 seconds. In the in-process split, compilation took 7.609 seconds, projection and preparation 15.578 seconds, satisfaction 3.414 seconds and serialization 0.875 seconds. Projection was the largest single stage on that root. The route read took 30.34 seconds, and its solver alone took 6.479 seconds with 28.9 seconds of process CPU.

On MATH.MA.880 with Active only off, compilation took 4.395 seconds, projection and preparation 5.664 seconds and the solver 4.906 seconds. The small roots took 0.23 to 0.36 seconds per graph read and 0.23 to 0.56 seconds per route read.

The chart shows the stage measurements for the two largest courses with Active only on and off.

![Compile, projection and preparation, satisfaction and serialization times for MATH.MA.880 and MATH.MA.725 with Active only on and off, showing projection and preparation as the largest stage on both Active only off profiles.](/docs/charts/graph-cyclic-initial-stage-costs.svg)

The graph responses were 0.004 to 92.98 MB uncompressed and 0.001 to 3.55 MB after local gzip compression. The server sent no compressed response, so the gzip values measure compressibility, not transfer size. The drawing limit of 500 elements refused the drawing on most large targets, including MATH.MA.880 with 1,805 and 14,217 elements and MATH.MA.725 with Active only off at 9,105 elements. The drawing was fully built, serialized and sent. The limit bounds what the browser may draw, not what the server computes.

### The abandoned YKT.SOA.303 request

YKT.SOA.303 ran past the client's 240-second timeout on both its graph and route requests. The server kept computing for about 30 minutes, at about 1.7 to 1.8 GB resident per process, until the web service was restarted. A closed client connection does not cancel a synchronous request that is already running. The course has no valid HTTP row because no request completed within the client's wait.

In process, YKT.SOA.303 compiled in 18.5 seconds with Active only on and 41.1 seconds with Active only off. Its projection had not finished after 56 seconds and 33 seconds. These are preparation limits, not route solver differences. The initial profile therefore records 10 courses with a completed HTTP row, not 11.

## The blowup mechanism

The four roots share one dense cluster. The request-local source index is an index of the courses and modules a root can reach, with one strongly connected component ID per source node. The index held 75 nodes. One component held 43 courses for one root, 42 for a second and 52 for a third. Across the roots the component held two inferred equivalence groups of 27 and 12 courses, 26 and 12, or 36 and 12, plus four single courses. The component held 940 equivalence edges, and 606 equivalence candidates lay outside it. Inner out-degree ran from one to 22.

| Observation | Value |
|---|---:|
| Source index nodes | 75 |
| Component size by root | 43, 42 and 52 courses |
| Equivalence group sizes in the component | 27 and 12, 26 and 12, or 36 and 12 courses |
| Single courses in the component | 4 |
| Equivalence edges inside the component | 940 |
| Equivalence candidates outside the component | 606 |
| Inner out-degree | one to 22 |
| Course expansion calls in 40 seconds | 294,000 |
| Distinct courses reached | 63 |
| Expansion depth | 31 |
| Calls for each of two courses | 37,000 |
| Memo entries after 25 seconds | 46,000 |

The compiler memoizes a compiled course body under its source locator, its immediate owner, its substitution and equivalence policy flags, and the ordered ancestor course and module identities filtered to the component. In a dense component that ancestor key is an acyclic path. The recursive course expansion ran 294 thousand times in 40 seconds over 63 distinct courses at depth 31, with no sign of ending. The same two courses took 37 thousand calls each. The memo held 46 thousand entries after 25 seconds and almost never hit.

Each set of ancestors cuts a different part of the cluster, so the distinct trees are exponentially many. A memo can only share equal trees. The measurement therefore did not show a slow hash or a poor constant factor. It showed an output that is itself exponential in the number of distinct acyclic paths.

### Key and boundary attempts

The first key reduction replaced the ordered ancestor path with the ancestor set. That cut the key count fivefold, and reducing the key did not help.

A second key kept only the ancestors the fragment can still reach, tested with a flag-exact source graph. This boundary key kept 18 matrix and diagnostic scenarios byte-identical on both the solver hashes and the display hashes. On the slow root the key count and the interned piece count grew linearly in time, reaching 5,500 keys and 14,000 pieces at 40 seconds. The distinct trees were exponential, so the boundary key preserved output without making the build cheap.

A third variant also dropped the module ancestor order from the key. That changed the detail text of a module cycle, of the form `module cycle: a -> b -> c`, so the order had to stay in the key.

The investigation concluded that no exact output-preserving memo fix existed for this structure. A fix by construction has to change the cycle cut. The rule alters the structure only where an equivalence offer reaches a course whose offered equivalent is already an ancestor.

## Cycle-cut alternatives

A cycle cut decides when a course occurrence closes a cycle instead of expanding again. The alternatives were compared on build time and memory, on whether the structure changed, and on the routes they produced.

| Cycle handling | Build result | Structure and route effect | Outcome |
|---|---|---|---|
| Exact expansion | No finish in 120 seconds, or `MemoryError` at the 4.295 GB cap | The output before the change | Not a fix |
| Ancestor-set memo key | Key count cut fivefold, build did not finish | Not evaluated for full byte identity | Not a fix |
| Boundary-only ancestor key | Slow root reached 5,500 keys and 14,000 pieces at 40 seconds, growing at the cutoff | 18 matrix and diagnostic scenarios byte-identical | Preserved output, not cheap |
| Module ancestor order dropped | Not measured | Module cycle detail text changed | Rejected |
| Cycle-closing leaf | 0.8 to 1.6 seconds per root, 107 to 114 MB resident | Structure changed in 13 of 22 matrix scenarios, routes changed from exact to unresolved in five of 16 | Rejected |
| Dropped occurrence | 2.36 to 3.01 seconds per complete command | Six Inferred-off outputs byte-identical, 16 Inferred-on outputs equal in state and credits, two approximate course sets differed | Selected and applied |

### The cycle-closing leaf prototype

The first prototype patched the compiler in memory and changed nothing in the tree. It closed a cycle when the occurrence, or any course sharing an equivalence group with it, already sat on the ancestor path. It also added the reverse edge of every offered equivalence to the source index so the in-component ancestor filter stayed sound.

The four roots built in 0.8 to 1.6 seconds each at 107 to 114 MB resident. These are in-process build times and resident memory values, not complete command times.

The rule was not confined to cyclic clusters. The structure changed in 13 of 22 matrix scenarios, including scenarios with Recommended off. The route solver treats any viable cycle leaf as unresolved. Closing as a cycle-closing leaf changed routes from exact to unresolved in five of the 16 route scenarios tried. The affected scenarios were PSY.324, KAT.MARK.310, KAT.MARK.304 and KIE.SUY.420 with Inferred on. KIE.SUY.420 went from 35 credits to unresolved. All four roots that failed preparation came out unresolved. The prototype was rejected.

### The dropped occurrence

The alternative dropped the occurrence, as a direct self occurrence is dropped. It produced no piece, no diagnostic and no cycle marker. In the prototype comparison it kept all 16 route runs equal to the routes measured before the change, with the same state, credits and route courses. Three of the four roots that failed preparation returned `exact` at six, zero and zero new credits, and the fourth returned `unresolved`. The three totals are not attributed to individual roots. In principle it can under-count when an equivalent's own prerequisites cost more than the dropped branch saves.

This alternative was selected and applied. The final comparison narrowed the prototype's route claim in two approximate cases, described below.

## Final measurements

### Complete command times

The four complete graph commands ran with Recommended and Inferred on and Active only on. They prepared the graph structure and did not run the route calculation. Each exited 0 with a wall time of 2.36 to 3.01 seconds including interpreter start, under the 300-second command timeout, and did not hit the 4.295 GB cap.

| Root | Wall (s) | Peak (MB) |
|---|---:|---:|
| Root A | 2.76 | 111.19 |
| Root B | 2.77 | 111.24 |
| Root C | 2.36 | 111.36 |
| Root D | 3.01 | 111.52 |

The four commands took 2.76, 2.77, 2.36 and 3.01 seconds. The process high-water mark uses 1,024 bytes per recorded unit, converted to decimal MB and rounded to 0.01 MB. The measurement is process-wide and includes the interpreter, imports and the whole command. It is not the compiler's allocation alone.

The chart shows the four complete command times.

![Complete command wall times for the four spot-checked roots after the cycle cut, showing 2.36 to 3.01 seconds per root.](/docs/charts/graph-cyclic-final-complete-runs.svg)

The final values are complete command wall times. The prototype's 0.8 to 1.6 seconds measured the in-process build and its resident memory, not a complete command.

### Route comparison

The 22 route commands compared the routes before and after the change. Six Inferred-off outputs were byte-identical. All 16 Inferred-on outputs kept their state and total new credits. Every output whose state was not approximate kept every route course identity.

Two approximate outputs each replaced one course identity:

| Output | Replaced identity | Replacement |
|---|---|---|
| MATH.MA.880, Recommended and Inferred on | `uta-ykoodi-48279` | `otm-c7233e84-953d-4e97-b4c4-8343702494c1` |
| MATH.MA.725, Recommended and Inferred on | `uta-ykoodi-48279` | `otm-c7233e84-953d-4e97-b4c4-8343702494c1` |

Both were approximate, and an approximate route course set is one valid choice among ties. PSY.324 was also approximate, and its route course identities were equal. The final claim is therefore not route-set identity on all 16 Inferred-on outputs. It is byte identity on six Inferred-off outputs and equal state and total new credits on 16 Inferred-on outputs, with two approximate course sets differing by one course each.

### Parity

The parity comparison after the change held 48 scenario rows, 12 per root. Each root covered five toggle combinations with an empty and a non-empty basis, plus two spot scenarios with the empty basis. All 48 rows reported `states: compared`, `equal: true` and zero differences. The eight spot rows were equal.

The parity check compares the Python and Node route solvers on the same prepared structure. It does not compare the structure before and after the cycle cut. A 48-row equality on four roots is not a broad guarantee for other roots, other datasets or other toggle combinations.

## The rule applied in the product

The selected rule is part of the compiler. An occurrence that is offered equivalences is dropped when one of its offered equivalents already sits on the ancestor path, with the root counted as an ancestor. The drop leaves no piece, diagnostic or cycle marker. A course that is itself an ancestor keeps its cycle-closing course piece and its course-cycle diagnostic. The check runs only with Inferred on and the occurrence offered equivalences. The source index records the reverse edge of every offered equivalence so a course and its offered equivalents share a component.

The applied rule and its interaction with self occurrences are described in [Prerequisite compiler](/docs/backend/prerequisites/prerequisite-compiler.md#collapse-mandatory-positions-and-self-removal). The graph's treatment of equivalence groups is described in [Prerequisite graph](/docs/backend/prerequisites/prerequisite-graph.md#equivalence-groups-and-substitutions).

## Interpretation and untested questions

Observed: the exponential cost sat in the compiler before the drawing projection. The four failed roots did not complete preparation, so neither the projection nor the route solver supplied a result for them. The initial profile also shows that projection can be the largest stage on large roots that do complete, so compile and projection have to be reported separately. The route solver is a separate cost and did not cause the four preparation failures.

Observed: the boundary key preserved 18 scenarios byte for byte, but it did not stop the growth on the slow root. The distinct trees, not the hash or the memo constant, are the cause.

Interpreted: dropping an occurrence whose offered equivalent is an ancestor removes the exponential family of acyclic paths by treating that occurrence like a self occurrence. It changes the structure wherever such an equivalence offer reaches an ancestor. That is why structure equality cannot be assumed even when state and credits stay equal.

Failed hypothesis: no key reduction or cycle-leaf rule tried both preserved the exact output and made the build cheap. The cycle-leaf rule was cheap but changed five of 16 routes to unresolved.

Untested: the dropped-occurrence rule can in principle under-count when an equivalent's own prerequisites cost more than the dropped branch saves. No case of that under-count was recorded. The final structure was not compared with the exact expansion at all. Route output was compared on the 22 measured commands, not on other datasets or other roots. The final rule was timed with Active only on, not with Active only off.

## Limitations

- The evidence covers one selected dataset on one 4-core aarch64 server with 23.6 GB of RAM. It also covers one run of the initial profile and one timing run per root. About 9.6 GB was available before the capped diagnosis.
- The initial profile excludes the four failed roots. YKT.SOA.303 has no valid HTTP row because the client timed out and the server request was not cancelled.
- The compile, projection, satisfaction and serialization values are in-process calls of the same command functions. They are not HTTP latency and do not sum to the graph wall time.
- The initial profile is one repetition per course and activity setting, with an empty course state and no concurrent load reported. It does not establish a stable mean or a tail. The summary table is the recorded evidence.
- The 22 route commands were compared without a stated course basis for each command. The parity comparison states its empty and non-empty bases.
- "No finish" means no finish within the 120-second preparation timeout and the 4.295 GB cap. It is not an unbounded runtime measurement.
- The prototype was patched in memory and changed nothing in the tree. Its 0.8 to 1.6 second build times and 107 to 114 MB resident values are not complete command measurements.
- The peak memory is process-wide. It includes the interpreter, imports and the whole command, and its decimal MB conversion is rounded to 0.01 MB.
- The 22-command route comparison is not a structure comparison. It shows byte identity on six Inferred-off outputs and state and credit equality on 16 Inferred-on outputs, with two approximate course sets differing by one course each.
- The 48 parity rows are solver parity on the same prepared structure for four roots. They are not evidence of broad equivalence or of structure identity.
- The final comparison did not count changed structures. The 13 of 22 structure-change count belongs to the prototype, not to the final rule.
- The under-count case of the dropped-occurrence rule is untested. The final rule's timing with Active only off is untested.
- The report makes no claim about semantic identity. Equal route state and credits do not imply an equal structure or an equal route course set.

## Setup details

| Item | Value |
|---|---|
| Dataset | One selected dataset |
| Hardware | 4-core aarch64 server, 23.6 GB of RAM |
| Compiler | Python, run in process |
| Route solver | Bundled TypeScript solver through Node |
| Initial profile | 10 codes, Active only on and off, one repetition, empty course state |
| Blowup diagnosis | Four roots, one at a time, no HTTP |
| Toggles | Recommended on, Inferred on |
| Address-space cap | 4.295 GB |
| Preparation timeout | 120 seconds |
| Timing command timeout | 300 seconds |
| Available memory | About 9.6 GB before the capped diagnosis |
| Peak memory unit | Process high-water mark converted to decimal MB |
| Warmup | None reported |
| Concurrent load | None reported |

The route comparison ran eight codes with and without Recommended under Inferred on, and three codes with and without Recommended under Inferred off. The parity comparison ran four roots with 12 rows each. The initial profile ran graph and route reads through the web routes. The diagnosis and the final timings ran without an HTTP request.

## Open questions

- Whether the dropped-occurrence rule under-counts new credits when an equivalent's own prerequisites cost more than the dropped branch saves. Untested.
- Whether the final structure and route output equal the exact expansion on other roots, other datasets or with Active only off. Untested.
- Whether a symbolic method over the strongly connected component can preserve the exact structure without enumerating acyclic paths. Untested.
- Whether the initial profile's stage shares hold on repeated runs or under concurrent load. Untested.
