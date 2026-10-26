# Compact graph identity and projection

This report measures the two-structure prerequisite graph report, from its calculation and display identities to its payload, projection and route parity.

**Evidence status:** Corrected. **Run dates:** 19 and 20 October 2026.

## The question

The [prerequisite graph](/docs/backend/prerequisites/prerequisite-graph.md) of one course sent a full calculation tree beside a fully built drawing. Both carried every occurrence of every requirement. One occurrence could be reached by several paths, and the drawing recorded each source occurrence separately. On the largest measured target the body reached 92.98 MB, and a projection stage took 15,578 ms before the response was serialized and sent.

The drawing limit did not reduce that work. Most large targets were refused by the 500-element drawing limit, yet the refused drawing was fully built, serialized and sent. The route result was separate from that drawing, so the payload carried presentation material that the browser could not draw.

The design question was whether one report could serve the calculation and the drawing from two structures. The calculation would be one globally shared directed acyclic graph of content-addressed pieces with ordered child slots. The drawing would be a per-course set of order-independent boxes. The two would need a shared answer for five things: box identity, saved marks, provenance, numeric multiplicity and cycles. Route lighting had to name the boxes and connections of the chosen route without sending every reaching path.

A second question followed the first. If the two structures keep different identities, how does a route answer reach the drawing, and how does a saved mark reach every calculation piece behind one box?

## The baseline report

The baseline measured one row per course and activity setting, 20 rows in all, each carrying one graph and one route request, with an empty course state and Recommended and Inferred on. The requests went through HTTP. One repetition was taken. The server sent no compression, and the recorded gzip size is `gzip -9` of the body.

| Course | Setting | Graph (s) | Raw (MB) | gzip (MB) | Compile (ms) | Project and prepare (ms) | Route (s) | Solver (ms) | Route outcome |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| MATH.MA.880 | Active only on | 3.89 | 6.76 | 0.47 | 2,915 | 502 | 8.24 | 4,449 | Approximate route |
| MATH.MA.880 | Active only off | 13.10 | 28.02 | 1.70 | 4,395 | 5,664 | 15.47 | 4,906 | No route found |
| MATH.MA.725 | Active only on | 12.47 | 65.76 | 1.66 | 6,188 | 5,103 | 17.84 | 5,580 | Approximate route |
| MATH.MA.725 | Active only off | 28.40 | 92.98 | 3.55 | 7,609 | 15,578 | 30.34 | 6,479 | Approximate route |

Across the 10 courses with a valid HTTP row, graph request time ranged from 0.23 s to 28.40 s, the raw body from 0.004 MB to 92.98 MB, the gzip body from 0.001 MB to 3.55 MB, and route time from 0.23 s to 30.34 s. Projection and preparation was the largest server stage on the large Active-only-off trees.

YKT.SOA.303 had no valid HTTP row. Its HTTP graph and route requests ran past the client's 240 s timeout, and the server kept computing them for about 30 minutes at 1.7 to 1.8 GB resident each, until the web service was restarted. In-process it compiled in 18.5 s with Active only on and 41.1 s off, and its projection had not finished after 56 s and 33 s. That target is excluded from the HTTP comparison and appears only in the in-process matrix.

The MATH.MA.880 Active-only-off body of 28.0 MB had two large parts:

- The calculation tree held 12.73 MB, including requirements 5.76 MB, node occurrences 4.96 MB, issues 1.66 MB, module occurrences 0.14 MB and courses 0.12 MB. The listed parts sum to 12.64 MB, leaving 0.09 MB of the tree unaccounted for by the recorded parts.
- The drawing held 15.30 MB: edges 6.31 MB, of which relationship members 4.73 MB including occurrence and condition evidence 2.23 MB, and endpoints 1.02 MB. Node states held 3.43 MB, course nodes 2.98 MB, connector nodes 2.15 MB, mark groups 0.32 MB and module nodes 0.11 MB.

The occurrence records and reaching paths account for most of that body. The drawing projection was the largest server stage.

## Two structures

One graph read returns one solver structure, one drawing, the support bindings between them and the drawing allowance. The browser route worker reads the held solver structure with the live profile inputs. It does not recompile the graph.

One graph read is one request, and its drawing allowance reports the counts of courses, nodes and connections against the configured drawing limit. The drawing carries the boxes and connections, and the route calculation returns one of the six [route outcomes](/docs/reference/glossary.md#prerequisites-and-routes).

The diagram shows one graph request returning the solver structure with its support bindings, the drawing and the drawing allowance, and the route calculation reading the held solver structure with the live profile inputs.

![One graph request returns the solver structure with its support bindings, the drawing of boxes and connections, and the drawing allowance of element counts against the limit. The route calculation reads the held solver structure with the live profile inputs and returns one of six route outcomes.](/docs/diagrams/prerequisite-graph-report.svg)

The solver structure is one global directed acyclic graph. A [calculation piece](/docs/reference/glossary.md#prerequisites-and-routes) is one provenance-free structural node. Its identity is a content digest of its kind, its kind-specific value and the ordered identities of its child pieces.

```text
calculation piece   p:<digest> = digest(kind, kind value, ordered child piece IDs)
calculation support s:<owner>:p:<piece>
display piece       s:<owner>:d:<fingerprint>
```

The applied identity also carries the manual credit minimum, the module rule and the cycle-closing marker. Equal structure therefore shares one piece, and two nodes with different evaluation values cannot share an answer. Children stay an ordered list and may repeat. Arity and numeric multiplicity live in the slot list, not in an occurrence record.

The owner is the canonical course of the nearest enclosing expanded-course branch, and the graph root owns its own tree. Owner is traversal context, not part of the piece. The same piece reached under two courses is one calculation piece and two scoped supports. The solver folds it once per owner. A shared piece can therefore have a different result for each owner, and a mark applies only where its box is.

The display identity is separate. It is the course owner plus a fingerprint of the displayed kind, the displayed values and the sorted unique fingerprints of the drawn children. Courses are global terminals. A logical group whose children reach exactly one unique drawn target collapses to that target, even when several source occurrences lead to it. Nested groups with the same operator fold before any attachment is emitted.

The report carries both structures and the [support bindings](/docs/backend/prerequisites/prerequisite-compiler.md#shared-drawing-identity). A binding maps one scoped calculation support to its source uses, its drawn node IDs and the markable boxes it stands for. A hidden head, an elided wrapper, a structural nested module and a module body bind to their nearest emitted containing box. No binding points at a box the drawing does not emit.

The design expected the two structures to share `(owner, piece)` and need no conversion table. The reversed-order test below ended that expectation for display identity. The applied report carries explicit support bindings instead, and the client never assumes that a calculation identity and a display identity are the same string.

### Provenance and drawing equality

Provenance is the origin, official kind, inferred category and inference metadata of a source node. It is held on the source uses and facts and never enters the calculation digest. An official AND and an inferred AND of the same structure become one piece and one display piece. In the fixture that case had seven occurrences and four pieces.

The drawing shows provenance in two places. A course box carries the inferred marker only when inferred provenance reaches it and no official provenance does. A connection is dashed only when every relationship behind it is inferred, and any official relationship makes it solid. Required and recommended relationships use the same line style.

The fingerprint ignores provenance, official kind, inferred category, inference metadata, mark state, child order, multiplicity, unexpandable content work keys and localized names. That is what lets one box stand for several source occurrences. It also means a mixed box can have no single provenance. The prototype took a located problem's provenance from a representative occurrence, and its fixture set had no case where two occurrences of one box would report different provenance.

### Numeric multiplicity

Ordered child slots may repeat. A two-of-three cardinality requirement over `(a, a, b)` keeps both `a` slots, and the route selects `a` with the same credits. A repeated OR branch is part of the calculation without changing the route.

The drawing may collapse those repeated slots into one display piece, because the fingerprint sorts and deduplicates its child fingerprints. The calculation keeps both slots. Two unexpandable content blocks whose displayed values are equal can likewise be distinct calculation pieces under one display piece. A saved mark on that box reaches every one of them.

### Cycles

A genuine indirect cycle becomes one course piece with the cycle-closing marker and one course-cycle diagnostic at the actual closing use. Every ancestor piece that contains the closing occurrence differs from the ancestor of a normal occurrence.

Without that marker a memoized normal occurrence answers for the closing occurrence. The control without the marker returns an Exact minimum route with two credits and no blocker. The product returns Route unresolved with a course-cycle blocker on the root path through `a`. With the marker the case matches.

A cycle case can place a normal and a closing occurrence on one connection. In the prototype fixture, the product recorded one relationship member with both terminal occurrences, and the compact display split that member by terminal identity, carrying each part's own gate set. The fixture records two such splits. The applied report holds one member per endpoint pair and complete source fact, and a projected context records the members its occurrence selects.

### Marks and route lighting

A node mark names one markable display piece. The report binds every calculation support to the display pieces and markable boxes it represents. A mark on one box applies to every calculation piece behind it, including opposite child orders and repeated numeric slots. A saved key for a box the drawing does not emit has no effect and applies again when the same display identity returns. A structurally nested module has no box, so a saved key for one is inert.

Marking one box that stands for three source occurrences made the product expand the mark to three occurrence action keys, while the prototype's compact tree applied it through one scoped support, because the three branches are one piece. Both results were No route exists, and each product mark group mapped to one box. Marking owner A's box excluded only A's occurrences, left B's box clear, and the route was exact through B. Marking a module excluded one module box, both results were No route exists, and one located excluded-node problem was reported.

A connection groups the relationships between one pair of boxes. The applied report holds one member per endpoint pair and complete source fact, `m:<digest>`, with `member_id`, `source_node_id`, `target_node_id` and `fact_id`. Route lighting selects one drawing derivation. `projectRoute` pairs each projected context with the drawing node the chosen route selected, requires that the context's owner and piece match the node, collects the member IDs that context owns, and follows only the child slots the node carries. The node set is the root plus the source and target endpoints of the lit members, so `selected_nodes` holds drawn `course:` and `s:<owner>:d:<fingerprint>` identities. An unchosen alternative contributes no member even when its calculation support lies in the route's evidence, so it is drawn dim.

The prototype's member predicate was different. It tested the member's terminal identity and a gate set against the selected scoped supports. In the prototype fixture, the product reported three identical excluded-node problems for the three sources of one box, and the compact result reported one. All 21 prototype route cases had the same lit member set as the product, the prototype predicate held for every lit member, and no gate lay outside its owner.

## The reversed-order counterexample

The counterexample reversed two children. Official `OR(a, b)` and inferred `OR(b, a)` under one AND draw one OR box, because the drawing fingerprint sorts its children. The ordered calculation identity produces two piece IDs. The display conversion refused the box and reported that it spans two scoped identities.

Sorting child IDs fixes permutation alone. It does not fix numeric-slot multiplicity or two unexpandable content blocks with equal drawings. Those are separate calculation pieces that the required drawing equality can share.

The resolution is the support binding. Display identity keys the box by its drawing fingerprint, not by one piece. The graph report binds each `s:<owner>:p:<piece>` to the drawn node IDs and markable box IDs it represents. A box can stand for two ordered pieces. A mark on the box reaches every piece behind it. A route lights the boxes and members of one chosen drawing derivation: `projectRoute` collects the members each selected context owns and reports their endpoints as drawn node IDs. A support may bind several boxes when a shared course is reached from several owners.

| Structure | Identity | Child order | Repeated slots | Provenance |
|---|---|---|---|---|
| Calculation | `p:<digest>` of kind, value and ordered child piece IDs | Ordered | Kept | Excluded |
| Display | `s:<owner>:d:<fingerprint>` of kind, values and sorted unique child fingerprints | Order-independent | Collapsed | Excluded |

The counterexample overturned the single-key assumption. The applied report keeps ordered calculation identity and order-independent display identity side by side, with an explicit binding between them. The test was one small in-process fixture with no selected dataset, network request or product data write.

## Fixture evidence

The design test ran 22 cases in process. It read no selected dataset and made no HTTP request. Every run took a few seconds. Two cases compiled a small course catalogue through the compiler. The other 20 were fixture trees.

`occ` is the number of calculation-tree occurrences, `pieces` the global DAG nodes, `scoped supports` the distinct `(owner, piece)` calculation supports and `evals` the compact route's memo entries. A scoped support is not a drawn box, so the drawn node count is a separate measure. The single AND and OR case drew seven nodes for seven supports, the two-owner case drew eight nodes for 11 supports, the repeated course leaf drew four nodes for three supports, the 25-branch scaling case drew five nodes for four supports and the compiled module case drew two nodes for four supports.

| Case | occ | pieces | scoped supports | evals | Lit compact/product | States | Status |
|---|---:|---:|---:|---:|---|---|---|
| Single AND and OR | 7 | 7 | 7 | 7 | 5/5 | equal | match |
| Single AND and OR with basis | 7 | 7 | 7 | 7 | 5/5 | equal | match |
| Mixed provenance, identical AND | 7 | 4 | 4 | 4 | 5/5 | equal | match |
| Elided gate | 4 | 4 | 4 | 4 | 3/3 | equal | match |
| Repeated course leaf | 4 | 3 | 3 | 3 | 3/3 | equal | match |
| Repeated course leaf, partial basis | 4 | 3 | 3 | 3 | 3/3 | equal | match |
| Three identical AND siblings | 10 | 4 | 4 | 4 | 3/3 | equal | match |
| Three identical OR branches | 10 | 4 | 4 | 4 | 4/4 | equal | match |
| 25 identical OR branches | 76 | 4 | 4 | 4 | 4/4 | equal | match |
| Two owners, same inner AND | 11 | 8 | 11 | 9 | 5/5 | equal | match |
| Cardinality, repeated child | 4 | 3 | 3 | 3 | 2/2 | equal | match |
| Credits OR, repeated branch | 5 | 4 | 4 | 4 | 3/3 | equal | match |
| Unresolved alternative | 3 | 3 | 3 | 3 | 0/0 | equal | match |
| Unresolved alternative with basis | 3 | 3 | 3 | 0 | 0/0 | equal | match |
| Impossible credit bound | 2 | 2 | 2 | 2 | 0/0 | equal | match |
| Cycle at second copy | 3 | 3 | 3 | 3 | 0/0 | equal | match |
| Cycle control without marker | 3 | 2 | 2 | 2 | 2/0 | equal | expected mismatch |
| Cycle at second copy with basis | 3 | 3 | 3 | 0 | 0/0 | equal | match |
| Mark on three identical OR branches | 10 | 4 | 4 | 2 | 0/0 | equal | match |
| Mark on owner A's box only | 11 | 8 | 11 | 7 | 5/5 | equal | match |
| Product compiler, two owners | 11 | 8 | 11 | 9 | 5/5 | equal | match |
| Product compiler, module | 4 | 4 | 4 | 4 | 1/1 | equal | match |

The prototype set is 22 cases, 21 matches and one expected mismatch. It has zero core mismatches, zero state mismatches, 21 of 21 equal lit member sets, zero gate-scope violations, zero scoped-box conflicts and two member splits. All 22 cases have equal box states, including the cycle control without the marker.

The two-owner case has one inner AND piece used under owners A and B, eight global pieces, 11 scoped supports, eight drawn nodes and three pieces that occur under more than one owner. The solver records nine evaluations for 11 occurrences. The compiled two-owner case reports the same counts. The scaling case has 76 occurrences in four pieces, four scoped supports and five drawn nodes, with 25 branches over one AND piece, two course leaf pieces and one root OR piece.

The fixture covers Exact minimum route, No route exists, Route unresolved and zero-credit results. Shortfall and approximation are not exercised. It uses small trees only. The scaled case is a synthetic 25-branch tree, not a catalogue measurement.

The 21 matching prototype fixtures are evidence for the identity, mark and lighting rules on small trees. They are not a validity proof for the measured report. The compact display was converted from the product projection, so the fixture proves the identifiers but not a projector that computes every inferred flag, ignored annotation and synthetic diagnostic connection from the piece graph. The prototype also built its DAG by walking every occurrence, which is not the compiler's construction path.

## The measured matrix

Every measured pass ran the same 110 cases: 11 courses, five combinations and two bases. The courses were `MATH.MA.880`, `MATH.MA.725`, `PSY.324`, `KAT.MARK.399`, `KAT.MARK.310`, `KAT.MARK.304`, `KIE.SUY.420`, `YKT.SOA.303`, `COMP.CS.500`, `COMP.CS.110` and `COMP.CS.200`.

The five combinations were `required-only`, `recommended`, `inferred`, `recommended+inferred` and `recommended+inferred-active-off`. `required-only` compiles with Recommended and Inferred off. `recommended` enables Recommended. `inferred` enables Inferred. `recommended+inferred` enables both, and the Active-only-off combination also applies Active only off.

The two bases were an empty basis and a fixed nonempty basis recorded for each course. Every case used one selected dataset of the captured curriculum. Both bases are empty for MATH.MA.880 and YKT.SOA.303, so their nonempty rows repeat the empty basis.

| Dimension | Value |
|---|---|
| Courses | 11 |
| Combinations | 5 |
| Bases | 2 |
| Cases per pass | 110 |
| Drawing limit | 500 elements |
| Allocation limit | 700,000 compact nodes |
| Case timeout | 120 s |
| Address-space cap | 4.295 GB |
| Hardware | 4-core aarch64 server, 23.6 GB of RAM |
| Capacity | One case at a time, one process per case |

Each case resolved its target, compiled the structure, projected once with the configured drawing limit, evaluated presentation states when the drawing was permitted, serialized the report, solved the route and serialized the route. The stage timers cover compile, project, state evaluation, graph serialization, solve and route serialization. The per-case total is larger than the sum of those stages, so the stages do not sum to it.

| Pass | Available memory before each case (GB) |
|---|---:|
| Initial compact | 7.5 to 8.7 |
| First correction | 7.9 to 8.4 |
| Second correction | 9.4 to 10.2 |
| Module drawing | 9.3 to 9.7 |

No case made an HTTP request, scanned the catalogue or shared the server with a concurrent heavy job. The matrix ran in process. The profile's graph and route seconds are HTTP request times that include response transfer, and the matrix's stage times do not. The two are not an end-to-end comparison.

The comparison records the result state, the total credits, the saved course set and the new unexpandable content. The baseline summary holds no unexpandable content field, so parity of the new unexpandable content is not recorded in any pass. No such parity is claimed. The gzip figures are measured compressed sizes of the serialized body. No case delivered that body over a network to a browser.

The [drawing limit](/docs/backend/prerequisites/prerequisite-graph.md#the-drawing-limit) is `PREREQUISITE_GRAPH_MAX_ELEMENTS`, set to 500 elements. It counts every node plus every edge and is applied before any display object is built. The [allocation limit](/docs/backend/prerequisites/minimum-route.md#exact-by-default) is `PREREQUISITE_PATH_MAX_COMPACT_NODES`, set to 700,000. The exact attempt is bounded by it, and an oversized attempt restarts once with the greedy search. The drawing limit never applies to solving.

## Initial compact report

The initial pass completed all 110 cases in 387 s. It compared 108 rows identical in result kind and saved course set, two equal-credit approximate course-set differences and zero changes from Approximate route to Exact minimum route. The drawing limit allowed 92 rows and refused 18.

The compact body is a different schema from the baseline. It carries the solver structure, the drawing, the support bindings and the allowance. The baseline carried the calculation tree and the full drawing. The sizes below compare whole bodies, not identical fields.

Both tables below are the empty basis with Recommended and Inferred on. The Setting column gives the activity scope.

| Course | Setting | Baseline raw (MB) | Compact raw (MB) | Compact gzip (MB) |
|---|---|---:|---:|---:|
| MATH.MA.880 | Active only on | 6.76 | 1.23 | 0.18 |
| MATH.MA.880 | Active only off | 28.02 | 3.60 | 0.67 |
| MATH.MA.725 | Active only on | 65.76 | 1.36 | 0.22 |
| MATH.MA.725 | Active only off | 92.98 | 3.52 | 0.68 |

The initial compact body was smaller in all four course-and-activity cases, and gzip reduced it further.

The chart compares the baseline and compact bodies for those four cases.

![Graph report payload for MATH.MA.880 and MATH.MA.725, each with Active only on and off. The baseline raw body is larger than the initial compact raw body in all four cases, and the compact gzip body is smaller again.](/docs/charts/graph-compact-payload.svg)

On MATH.MA.725 Active only off the raw body fell from 92.98 MB to 3.52 MB and the gzip body fell from 3.55 MB to 0.68 MB. On MATH.MA.880 Active only off the raw body fell from 28.02 MB to 3.60 MB. YKT.SOA.303, which had no valid HTTP row, produced a compact body of 5.73 MB raw and 1.00 MB gzip with Active only off.

The projection and prepare stage in the HTTP profile was 15,578 ms on MATH.MA.725 Active only off and 5,664 ms on MATH.MA.880 Active only off, inside graph requests of 28.40 s and 13.10 s and beside route requests of 30.34 s and 15.47 s. The largest compact projection stage was 386 ms on MATH.MA.880 Active only off. The profile request includes HTTP and response transfer around its server stages, and the compact stage is in process. The two are not an end-to-end comparison.

| Course | Setting | Compile (ms) | Project (ms) | Solve (ms) | Total (ms) | Route and credits |
|---|---|---:|---:|---:|---:|---|
| MATH.MA.880 | Active only on | 2,264 | 104 | 4,946 | 7,598 | Approximate route, 198 cr |
| MATH.MA.880 | Active only off | 2,985 | 386 | 3,590 | 7,269 | No route found |
| MATH.MA.725 | Active only on | 3,542 | 77 | 5,057 | 8,958 | Approximate route, 193 cr |
| MATH.MA.725 | Active only off | 4,818 | 273 | 3,512 | 8,923 | Approximate route, 206 cr |
| YKT.SOA.303 | Active only on | 3,587 | 57 | 6,516 | 10,476 | Approximate route, 55 cr |
| YKT.SOA.303 | Active only off | 4,935 | 118 | 7,155 | 12,538 | Approximate route, 10 cr |

The two differing rows were YKT.SOA.303 with `recommended+inferred` (Active only on) in both bases. Both bases are empty for that target. Both results kept the Approximate route outcome and 55 credits and differed by one canonical course.

| Basis | Baseline course | Compact course |
---|---|---|
| empty | YKT.200 | YKT.235 |
| nonempty | YKT.200 | YKT.235 |

A focused probe checked both saved course sets against the native satisfaction service. Both satisfy the requirements and sum to 55 credits. The candidate closures cost 20 and 10 credits despite equal 5-credit course minima. An equal final cost therefore does not establish a local tie or a globally canonical approximate winner.

The initial pass kept the tie-break order and replaced the final tie-break coordinate with sorted shared identities, so the final comparison uses shared identities instead of occurrence evidence. Removing that coordinate in an isolated diagnostic left the compact winner in place, so the difference is not attributed to that coordinate alone. The first divergence is not isolated.

The drawing was refused for 18 rows in this pass, including six rows for each of MATH.MA.880 and MATH.MA.725. Their display node and edge counts are zero while their solver structures are in the payload. The projection behind these counts omitted member closures and conditional module obligations, so its refusal count and element counts describe an incomplete drawing and are not comparable with the corrected passes.

## First correction

The initial projection omitted member closures and conditional module obligations. The first correction restored them. The drawing then carried the member connections and conditional module subtrees that the calculation required, and its element count grew.

For YKT.SOA.303 Active only off, the initial rows recorded 1,017 pieces, 18,071 uses and 943 elements. The corrected rows recorded 905 pieces, 1,352 uses, 38,523 gates, 4,377 members and 5,679 elements. The first corrected projection recorded a gate table of 38,523 records for the hidden member connections. That count is the gate growth the second correction removed.

All 110 cases completed in 432 s. Compile ranged from 37.3 ms to 3,782.8 ms with a median of 366.7 ms. Project ranged from 0.1 ms to 15,706.5 ms with a median of 11.4 ms. Solve ranged from 0.1 ms to 6,666.0 ms with a median of 19.7 ms. The per-case total ranged from 315.7 ms to 26,097.0 ms with a median of 711.5 ms.

Raw graph JSON ranged from 1,766 to 15,361,045 bytes and gzip graph JSON from 690 to 2,915,937 bytes. Raw route JSON ranged from 470 to 72,596 bytes and gzip route JSON from 268 to 13,580 bytes. The comparison found 108 identical rows and two equal-credit approximate differences. The drawing allowance was 80 allowed rows and 30 refused rows.

The initial pass reported a largest compact projection of 386 ms. This correction reported 15,706.5 ms. The initial 386 ms measured a projection that omitted the closures this pass restored, so it is not a like-for-like improvement over the baseline or over the corrected projection.

## Second correction

The second correction rebuilt the source closure over source components, the offered equivalence candidates and unique drawn targets. It also rebuilt the compact gate table. The hidden-member gate growth disappeared.

All 110 cases completed in 405 s. Compile ranged from 33.7 ms to 4,535.7 ms with a median of 362.9 ms. Project ranged from 0.1 ms to 593.5 ms with a median of 13.6 ms. Solve ranged from 0.1 ms to 6,719.6 ms with a median of 22.4 ms. The per-case total ranged from 304.4 ms to 11,710.6 ms with a median of 745.6 ms.

Raw graph JSON ranged from 1,766 to 4,393,468 bytes and gzip graph JSON from 690 to 724,395 bytes. Raw route JSON ranged from 470 to 73,028 bytes and gzip route JSON from 268 to 13,558 bytes. The comparison found 108 identical rows and two equal-credit approximate differences. The drawing allowance was 80 allowed rows and 30 refused rows.

For YKT.SOA.303 Active only off, the corrected rows carried 1,017 pieces, 1,471 uses, 3,161 bindings, 2,845 gates, 4,685 members and 6,039 elements. The gate table fell from 38,523 to 2,845 records over the wider source closure. The largest gate table anywhere in the pass was 3,176 records.

The gate table belongs to the measured projection in these passes. The applied relationship member carries no gate field, and the applied route lighting reads the projection contexts.

| Pass | Row | Gate records |
|---|---|---:|
| First correction | YKT.SOA.303 Active only off | 38,523 |
| Second correction | YKT.SOA.303 Active only off | 2,845 |
| Second correction | Largest table in the pass | 3,176 |
| Module drawing | YKT.SOA.303 Active only off | 3,348 |

The gate record count is plotted for the same row across the two corrections and the module-drawing pass.

![Gate records for YKT.SOA.303 with Recommended and Inferred on, Active only off, in the first and second corrected passes and the module-drawing pass. The count falls from 38,523 to 2,845 records and then rises to 3,348.](/docs/charts/graph-compact-gates.svg)

The largest projection stage fell from 15,706.5 ms to 593.5 ms. The piece and use counts include the offered equivalence candidates that enter the source closure, and the drawing element count moves with the unique drawn-target identity.

All 30 refused rows report no drawing. Each keeps its solver structure, support bindings, projection contexts, members and located reasons. The route result is available.

## Final module drawing

The module-drawing pass measured the structural nested-module rule. A structurally nested module contributes its cards and external obligations to one enclosing module box, and an independent member occurrence has its own closure. The independent closure adds calculation pieces.

### Drawing allowance

The pass allowed 82 rows and refused 28 under the 500-element limit. The two corrected passes before it each allowed 80 and refused 30. KAT.MARK.399 with `recommended` draws 437 elements instead of 648 and fits the limit.

Among the 80 rows allowed in both the second correction and the final pass, 42 keep their element count, 34 lose between two and 61 elements, and four gain seven or 11 elements. Module-heavy YKT.SOA.303 Active only off moves from 6,039 to 5,913 elements, and its gate records rise from 2,845 to 3,348 in both bases.

YKT.SOA.303 with `recommended+inferred` grows from 1,714 to 2,626 elements and is refused. Its native structure grows from 573 pieces and 785 uses to 852 pieces and 1,137 uses, because the independent member closure that the drawing rule requires adds calculation pieces. Its gate records grow from 3,176 to 4,147. The 38,523-record gate table does not return.

| Pass | Allowed | Refused | Limit |
|---|---|---:|---:|
| First correction | 80 | 30 | 500 |
| Second correction | 80 | 30 | 500 |
| Module drawing | 82 | 28 | 500 |

The table covers the two corrected passes and the module-drawing pass. The initial pass allowed 92 rows and refused 18 with a projection that omitted member closures and conditional module obligations, so its counts describe an incomplete drawing and are not a fourth comparable result.

The allowance is plotted across the three corrected passes.

![Rows allowed and refused by the 500-element drawing limit in the first correction, second correction and module-drawing passes. The final pass allows 82 rows and refuses 28.](/docs/charts/graph-compact-allowance.svg)

Every refused row reports no drawing and keeps its native structure, support bindings, projection contexts, members and located reasons. The route result is authoritative and separate. The machine route compiles a solver structure with no drawing, so the drawing limit does not bound solving.

### Route parity

The final pass supersedes the earlier parity count. The first three measured passes each recorded 108 identical rows and two equal-credit approximate differences. The module-drawing pass records 104 identical rows and six valid approximate routes whose credit total is higher than the baseline. The 108 and two are not the final result. In the final rows that light a route, `selected_nodes` holds drawn `course:` and `s:<owner>:d:<fingerprint>` identities, and `lit_members` holds the member IDs the chosen contexts own. The measured module-drawing rows report this shape rather than `s:<owner>:p:<piece>` calculation supports.

The route parity baseline is separate from the graph profile above. It is the route result of the unmodified product route search measured in the [structural route deduplication](/docs/experiments/graph-and-route-algorithms/structural-route-deduplication.md) matrix. That matrix ran an instrumented copy of the search on its own compiled structures, with the same empty basis and the same fixed nonempty basis for each course and the same 700,000 allocation limit.

The compact pass compiled its own structures with the module-drawing rule applied. The comparison therefore spans two builds and two compiled structures, and it does not rerun the baseline on the compact structure. It cannot separate the effect of the compact build, the compact structure or the greedy ordering. The comparison also does not establish that the compact build or compiled structure matches the seven-case acceptance in [Minimum-credit routes](/docs/experiments/graph-and-route-algorithms/minimum-credit-routes.md).

| Pass | Identical rows | Differing approximate rows |
|---|---:|---:|
| Initial compact | 108 | 2 |
| First correction | 108 | 2 |
| Second correction | 108 | 2 |
| Module drawing | 104 | 6 |

The parity counts are plotted across the four measured passes.

![Rows identical to the baseline and rows with a differing approximate route in each measured pass. The final module-drawing pass has 104 identical rows and six differing approximate rows, against 108 and two in the earlier passes.](/docs/charts/graph-compact-parity.svg)

The final summary has 104 identical rows, six differing approximate rows and zero rows where the Exact minimum route differs.

| Result | Rows |
|---|---:|
| Identical result kind and saved course set | 104 |
| Approximate, higher credit total, different valid set | 6 |
| Exact minimum route differs | 0 |

The six rows are three course and combination pairs in both bases.

| Course | Combination | Bases | Baseline route and credits | Measured route and credits | Change |
|---|---|---|---|---|---|
| MATH.MA.880 | `recommended` | empty, nonempty | Approximate route, 194 cr | Approximate route, 204 cr | 2 courses added |
| MATH.MA.880 | `recommended+inferred` | empty, nonempty | Approximate route, 198 cr | Approximate route, 203 cr | 1 course replaced by 2 |
| YKT.SOA.303 | `recommended+inferred` | empty, nonempty | Approximate route, 55 cr | Approximate route, 60 cr | 1 course added |

The 204 credits on the MATH.MA.880 `recommended` row are a separate measurement from the 204.00 credits of the MATH.MA.880 active-only seven-case result in [Minimum-credit routes](/docs/experiments/graph-and-route-algorithms/minimum-credit-routes.md). The two runs used different builds and different matrices, and an Approximate route carries no minimum guarantee, so the equal total does not confirm either result.

Every measured route satisfies the compiled structure in its own case. Loading the baseline course set as the basis also satisfies each measured structure, so the extra courses are not additional obligations. Interpreted: the compact structure may have changed which valid route the bounded approximate search returned. The comparison does not establish that cause, because the baseline and the compact pass used different builds and compiled structures and the greedy ordering was not isolated.

The Approximate route outcome carries no minimum guarantee. The Exact minimum route and every row with that outcome match the baseline, and no Approximate route became an Exact minimum route. The comparison labels these rows unexplained because its classifier accepts only identical rows, requirement-correct improvements and equal-credit approximate sets. The pass records them as approximate valid routes with a higher credit total.

Each of the three earlier passes recorded two equal-credit approximate differences. The final six are higher-credit approximate sets. Neither group is an exact optimum claim, and neither supports blanket parity.

### Timing after the corrections

The largest projection stage was 15,706.5 ms in the first correction, 593.5 ms in the second correction and 600.5 ms in the module-drawing pass. The second correction removed the gate growth, and the module-drawing pass held projection near the same level while the active-off gate table rose from 2,845 to 3,348 records.

| Pass | Cases | Largest project (ms) | Median project (ms) |
|---|---:|---:|---:|
| First correction | 110 | 15,706.5 | 11.4 |
| Second correction | 110 | 593.5 | 13.6 |
| Module drawing | 110 | 600.5 | 12.4 |

The largest projection is plotted across the three corrected passes.

![Largest projection stage across all cases in the first corrected pass, the second corrected pass and the module-drawing pass. The value falls from 15,706.5 ms to 593.5 ms and is 600.5 ms in the final pass.](/docs/charts/graph-compact-projection.svg)

The module-drawing pass completed all 110 rows. The sum of its per-case totals is 234.6 s, not the wall-clock duration of the pass. Compile ranged from 33.6 ms to 4,739.9 ms with a median of 320.1 ms. Project ranged from 0.1 ms to 600.5 ms with a median of 12.4 ms. Solve ranged from 0.1 ms to 6,829.2 ms with a median of 22.0 ms. The per-case total ranged from 304.4 ms to 12,195.3 ms with a median of 638.1 ms.

Raw graph JSON ranged from 1,766 to 4,467,054 bytes and gzip graph JSON from 690 to 747,733 bytes. Raw route JSON ranged from 470 to 78,411 bytes and gzip route JSON from 268 to 12,030 bytes. The pass paused at its first approximate route difference for investigation, then ran the remaining cases. A rerun of MATH.MA.880 with `recommended` and an empty basis produced the same row.

## Corrections that stand

| Earlier result | Correction | Result that stands |
|---|---|---|
| One scoped calculation piece identifies one display piece. | Official `OR(a, b)` and inferred `OR(b, a)` draw one box from two ordered pieces, and the conversion is refused. | Display identity is the drawing fingerprint, and support bindings connect each calculation support to the display pieces and markable boxes it stands for. |
| The initial compact projection reached 386 ms at its maximum. | The first correction restored omitted member and module closures, and its gate table reached 38,523 records. | The second correction records 2,845 gate records for the YKT.SOA.303 Active-only-off row and a 593.5 ms maximum. The module-drawing pass records 3,348 gate records for the same row in both bases and a 600.5 ms maximum. |
| 108 identical rows and two equal-credit approximate differences. | The module-drawing pass changed the bounded approximate choice. | 104 identical rows and six valid higher-credit approximate rows. No Exact minimum route differs. |
| 80 allowed and 30 refused rows. | Structural module drawing changes the element counts. | 82 allowed and 28 refused rows. |

## What the evidence supports

The fixture evidence supports the identity rules on small trees. Ordered calculation pieces that ignore provenance preserve route outcomes, box states and lit member sets against the product. A cycle-closing occurrence needs its own piece. A saved mark on one display box reaches every calculation piece the binding gives it. In the prototype, gates and terminals lit per member, and located problems collapsed per box. The applied route result lights the members that the chosen derivation's projected contexts own and reports drawn course and display identities.

The measured evidence supports three statements about the report size and stages. The compact body is smaller than the baseline body in the four large course-and-activity cases. The largest corrected projection stage is below the largest baseline project-and-prepare stage, as a server-stage comparison. The second correction cut the gate table from 38,523 to 2,845 records and projection from 15,706.5 ms to 593.5 ms, and the module-drawing pass raised the gate table to 3,348 records while projection stayed at 600.5 ms.

The measured evidence supports these parity counts for this matrix: 104 identical rows, six valid higher-credit approximate rows and zero rows where the Exact minimum route differs. It supports 82 allowed and 28 refused drawings at 500 elements.

The evidence does not support a general optimality claim. An Approximate route carries no minimum guarantee. It does not support blanket parity either, because six rows differ and parity of the new unexpandable content is unmeasured. It does not establish an end-to-end latency gain, a network delivery gain or a browser rendering gain. The profile included HTTP and response transfer, and the matrix did not.

## Limitations

- Each measured pass completed one matrix on one server, and no repetition, variance or confidence interval is recorded. The module-drawing pass paused at its first approximate route difference, ran the remaining rows and reran one investigated case.
- The fixture set covers small trees, with one synthetic 25-branch case. It does not exercise a large course, approximation, shortfall, a dataset read or a browser.
- The fixture display was converted from the product projection. It proves identifiers and lighting, not the measured projector that computes every display flag from the pieces.
- The measured matrix is in process. It measures compilation, projection, solving and serialization, not HTTP requests, response transfer, browser parsing or rendering.
- The gzip values are compressed serialized bodies. The profile server sent no compression, and no measured case delivered a compressed response to a browser.
- The drawing was refused for 28 rows in the final pass. Their display counts are absent, and their solver structures are retained.
- The baseline has no unexpandable content field. No parity of the new unexpandable content is claimed.
- The six final approximate differences have higher credit totals than the baseline. They are valid routes, not equal-cost alternatives and not optimality evidence.
- The route parity baseline is a different build from the compact pass. Its compiled structure is not the compact structure, so the six differences cannot be attributed to the compact build, the compact structure or the greedy ordering.
- The first route divergence is not isolated. Removing the final support identity coordinate leaves the measured winner in place.
- The prototype scoped a calculation support by the nearest expanded course, and its fixture set had no course with two identical module bodies. The applied display identity is the course owner plus the drawing fingerprint, so equal drawn module bodies under one course share one box.
- In the prototype, a mixed display box's located problem took its provenance from one representative occurrence. No fixture distinguishes two provenance choices for one box. The applied route result reports one problem per local failure, once for each distinct provenance fact bound to its support.
- The prototype fixture set exercised one gated member on a connection and never two members with different gate sets. The applied report holds no gate field: a connection carries one member per endpoint pair and complete source fact, and a projected context records the members its occurrences select.
- The prototype did not exercise the configured allocation limit, so its fixtures do not show whether a smaller deduplicated structure moves an outcome from Approximate route to Exact minimum route. The applied calculation bounds only the exact attempt and restarts once with the greedy search.

## Untested questions

- Whether the six higher-credit approximate routes persist on another catalogue, another basis or another module drawing is untested.
- Whether the smaller compressed body produces an end-to-end gain in a browser, including transfer, parse and render, is untested.
- Whether the mark rules hold for a course with two identical module bodies, and across a full client-state migration, is untested.
