# Serving request cost and admission curves

This report prices each endpoint before and after the CPU port and fits the two-segment admission curves that make a recommendation or next-course request heavy at one core-second.

**Evidence status:** Comparative. **Run dates:** 30 October 2026.

## The question

[Admission control](/docs/backend/interfaces/admission-control.md) prices each heavy API read in core-seconds and charges that estimate against a cookie's heavy budget before the read takes a global slot. A recommendation or next-course read is priced by a configured two-segment curve, a search that includes inactive courses by a fixed charge, and a prerequisite graph by the elapsed time recorded for an earlier build of the same request field.

A price that is too low admits work the server cannot carry, and a price that is too high refuses work it could serve. Two questions follow. First, what does each endpoint cost on the product tree against the tree before the CPU port, at equal output? Second, which curve prices the recommendation and next-course classes so that a request becomes heavy at about one core-second, and does that curve agree with the measured means around that point?

The CPU port moved the fuzzy-name score, the recommendation scorer and the prerequisite compiler and drawing projection into three native libraries that Python loads, as [Native libraries](/docs/architecture/native-libraries.md) describes. The pre-port tree runs the same work in Python. A core-second is one second of CPU on one core, summed over the web, database and embedding cgroups.

## Method and setup

### The matched endpoint matrix

Both sides served one disposable copy of [the catalogue the experiments read](/docs/experiments/README.md#the-catalogue-the-experiments-read), 11,086 courses, from four worker processes, with one isolated embedding service. The product copy built its native libraries inside the copy. The pre-port copy is pure Python. The runs used a four-core aarch64 server, the serving specification recorded under [the experiments hardware](/docs/experiments/README.md#the-hardware).

The measured window reads the CPU counters of the web cgroup, which holds the supervisor, front router and four workers, and of the database and embedding container cgroups. Client decompression and JSON validation run after it. Each cached case measured three genuine cache misses on distinct request bodies of the same shape on each side. Each recommendation or next-course miss loads its own prerequisite closure and report work. [Serving load measurement method](/docs/experiments/runtime-storage-and-serving/serving-load-method.md) states the warm-up and distinct-miss protocol, the cache-event check and the counter sampler that the matrix shares.

The matrix holds 101 matched rows. The recommendation and next-course bases come from the 500-course pool that the capacity workload uses, chosen by the lowest SHA-256 of `<seed>:<group_id>` with seed 20261030. Those rows carry inference enabled, which is the shape the capacity workload sends. Each search label measured the same three distinct query texts on both sides, so its mean and range span query difficulty as well as runtime. The capacity results measured on the same pool are in [Serving capacity](/docs/experiments/runtime-storage-and-serving/serving-capacity.md).

Every value in the endpoint table is a mean over its three samples with the minimum and maximum in parentheses, and every change is the recorded percentage between the two means. An overlapping range is stated as an overlap, and no difference is called noise without a matched measurement. The [serving load measurement method](/docs/experiments/runtime-storage-and-serving/serving-load-method.md) also states what the serving measurements do not establish.

### The curve fit and its acceptance rule

The 115 measured cases produced 106 fit inputs: 94 recommendation and next-course rows, 10 graph rows and two inactive-search rows. The four curves use only the 64 inference-enabled recommendation and next-course rows. The other 30 rows in those classes are official-only measurements and do not enter the curves. Each curve point is a mean over 10 genuine distinct misses, and every measured basis carries equal weight.

The origin basis is fixed at basis 3 for all four classes. The knee is searched over every integer from the smallest to the largest measured basis. For each knee the fit solves eight coefficient subsets built from a base, a head and a tail term, rejects a subset with a negative coefficient, and selects the feasible subset with the smallest squared residual.

A candidate curve is accepted only when both conditions hold. Its applied rounded value at each measured basis around the 1.0-second crossing, and one measured basis on each side, lies inside that point's minimum-to-maximum range. Its cutoff falls between the last measured mean below 1.0 and the first measured mean at or above 1.0. A class with no accepted candidate reports its smallest-residual candidate with acceptance marked as failed.

The crossing and the near-point predictions are computed from the rounded configuration values the router reads, not from the fitted coefficients. A cutoff therefore always matches the curve that is charged.

The diagram follows one class through the fit and the acceptance check.

![One class passes from the workload matrix to its basis means, an integer knee search and eight coefficient subsets. The acceptance check either applies the curve and its cutoff where the applied curve reaches 1.0 core-second, or reports the smallest-residual curve with acceptance failed.](/docs/diagrams/serving-admission-fit-acceptance.svg)

## Endpoint cost before and after the CPU port

The recommendation and next-course rows are the inference-enabled forms that the admission fit uses, and the graph rows name their form.

| Endpoint | Pre-port core-seconds (min to max) | Product core-seconds (min to max) | Change |
|---|---|---:|---:|
| Search, title | 0.5014 (0.4047 to 0.6510) | 0.2762 (0.2246 to 0.3738) | -44.9% |
| Search, code | 0.3797 (0.3666 to 0.3887) | 0.1984 (0.1866 to 0.2089) | -47.8% |
| Search, inactive title | 0.8111 (0.7806 to 0.8326) | 0.2288 (0.2001 to 0.2455) | -71.8% |
| Recommendations, 20 active | 1.3611 (0.2710 to 2.1214) | 0.5035 (0.2973 to 0.6653) | -63.0% |
| Recommendations, 20 inactive | 1.2002 (0.2951 to 1.8745) | 0.4586 (0.2493 to 0.6003) | -61.8% |
| Recommendations, 40 active | 3.3782 (2.6896 to 4.0722) | 0.7095 (0.6599 to 0.7612) | -79.0% |
| Recommendations, 40 inactive | 5.0273 (4.0611 to 6.0477) | 0.7496 (0.6839 to 0.8015) | -85.1% |
| Recommendations, 50 active | 3.6121 (3.0195 to 4.4343) | 0.7050 (0.6787 to 0.7346) | -80.5% |
| Recommendations, 50 inactive | 6.0849 (4.8836 to 6.7990) | 0.8120 (0.7622 to 0.8767) | -86.7% |
| Recommendations, 60 active | 4.6779 (3.6009 to 5.8094) | 0.8154 (0.7160 to 0.9754) | -82.6% |
| Recommendations, 60 inactive | 6.4053 (5.0504 to 7.2412) | 0.9296 (0.7689 to 1.0464) | -85.5% |
| Next courses, 20 active | 1.1916 (0.9854 to 1.5005) | 0.1883 (0.1645 to 0.2159) | -84.2% |
| Next courses, 20 inactive | 1.9979 (1.6420 to 2.1905) | 0.2029 (0.1866 to 0.2348) | -89.8% |
| Next courses, 40 active | 1.5766 (1.4919 to 1.6324) | 0.2476 (0.2452 to 0.2518) | -84.3% |
| Next courses, 40 inactive | 2.4068 (2.2308 to 2.6250) | 0.2625 (0.2579 to 0.2678) | -89.1% |
| Next courses, 50 active | 1.1346 (0.6809 to 1.6381) | 0.2437 (0.2094 to 0.2793) | -78.5% |
| Next courses, 50 inactive | 1.3909 (0.9554 to 1.8330) | 0.2482 (0.2300 to 0.2577) | -82.2% |
| Next courses, 60 active | 1.2143 (0.7344 to 1.4963) | 0.2522 (0.2309 to 0.2662) | -79.2% |
| Next courses, 60 inactive | 2.9071 (0.9584 to 4.3038) | 0.6299 (0.2415 to 1.3025) | -78.3% |
| Largest graph, official | 0.4514 (0.4233 to 0.5066) | 0.1450 (0.1426 to 0.1475) | -67.9% |
| Largest graph, inferred | 1.2660 (1.2105 to 1.3380) | 0.2380 (0.2130 to 0.2798) | -81.2% |
| Comparison | 0.0365 (0.0361 to 0.0368) | 0.0208 (0.0203 to 0.0212) | -43.1% |
| Study fragments, 20 roots | 0.7200 (0.7091 to 0.7323) | 0.0086 (0.0083 to 0.0089) | -98.8% |
| Study read, unavailable roots | 0.5441 (0.5339 to 0.5529) | 0.0069 (0.0068 to 0.0072) | -98.7% |
| Study read, explicit version | 0.0260 (0.0241 to 0.0277) | 0.0264 (0.0230 to 0.0326) | +1.6% |
| Catalogue identity | 0.0219 (0.0205 to 0.0232) | 0.0195 (0.0184 to 0.0213) | -11.0% |
| Catalogue, gzip | 0.1198 (0.1185 to 0.1219) | 0.0055 (0.0045 to 0.0069) | -95.4% |

Every one of the 101 matched rows is cheaper on the product tree except the study read that names an explicit version. It measured 0.0264 core-seconds against 0.0260, 1.6 percent higher, with a product range of 0.0230 to 0.0326 and a pre-port range of 0.0241 to 0.0277. The ranges overlap and the product median is lower, 0.02347 against 0.02605 core-seconds, on an endpoint of about 26 milliseconds. The matched mean reads higher and is reported as measured.

The chart shows eight representative shapes. Each pair is the pre-port mean and the product mean of the same shape.

![Core-seconds per request for eight representative endpoints before the CPU port and on the product. Every product bar is lower, the product bars span 0.2029 to 0.9296 core-seconds, and the widest gap is the basis-60 inactive recommendation at 6.4053 core-seconds before the port and 0.9296 after it.](/docs/charts/serving-endpoint-cost-pre-post.svg)

The comparison is a cost comparison at equal output. The search and next-course response bodies matched byte for byte. Six recommendation rows differed only at the stored-neighbour tie break, and every course common to both sides agreed within 1.28e-13.

## The admission curve form

Each recommendation and next-course class is priced by a two-segment line with an origin, a knee and a tail.

```text
cost = origin_cost + slope x (basis - origin_basis)     at or below the knee
cost = tail_cost + tail_slope x (basis - knee_basis)    above the knee
```

The cost starts at `origin_cost` at the origin basis and rises with `slope` to the knee, where it is `tail_cost`. Above the knee it rises with `tail_slope`. The two scopes of one curve share that curve's origin basis, and each scope has its own knee, origin cost, slope, tail cost and tail slope. [Admission policy arithmetic](/docs/backend/interfaces/admission-policy.md#the-cost-curves) states the formula the product evaluates.

The basis is the number of distinct nonblank identifiers in the basis the read uses. A search that includes inactive courses carries one fixed charge instead of a curve, and a prerequisite graph carries the elapsed seconds the front router recorded for the same request field.

## The fit that stands

| Class | Knee basis | Origin cost | Slope | Tail cost | Tail slope | Squared residual | RMSE | Crossing basis | Acceptance |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Recommendation, active only | 181 | 0.28268 | 0.00808 | 1.72143 | 0.00499 | 0.0552 | 0.0570 | 92 | passes |
| Recommendation, inactive courses | 244 | 0.10363 | 0.01625 | 4.01941 | 0.00817 | 0.1880 | 0.1120 | 59 | fails |
| Next courses, active only | 230 | 0.10883 | 0.00358 | 0.92217 | 0.0009 | 0.0035 | 0.0153 | 317 | passes |
| Next courses, inactive courses | 398 | 0.05998 | 0.00803 | 3.23171 | 0.00061 | 0.3979 | 0.1530 | 121 | passes |

Three classes pass the acceptance rule. The recommendation-inactive class fails by one basis, and its smallest-residual curve is applied as the best consistent description of the measurements.

The measured means around each crossing are the values the acceptance rule reads. Each is a mean over 10 genuine distinct misses of the same request shape.

| Class | Basis | Mean core-seconds | Minimum to maximum |
|---|---:|---:|---|
| Recommendation, active only | 80 | 0.90629 | 0.54068 to 1.03537 |
| | 90 | 0.97942 | 0.64059 to 1.33364 |
| | 100 | 1.05351 | 0.81672 to 1.32198 |
| | 110 | 1.15716 | 0.76920 to 1.36400 |
| Recommendation, inactive courses | 50 | 0.78038 | 0.29484 to 0.95057 |
| | 60 | 0.98485 | 0.39965 to 2.01436 |
| | 70 | 1.14201 | 0.73447 to 2.27977 |
| | 80 | 1.20569 | 0.61328 to 2.43745 |
| Next courses, active only | 250 | 0.93555 | 0.87185 to 1.02308 |
| | 300 | 0.98898 | 0.87985 to 1.07278 |
| | 350 | 1.02921 | 0.94678 to 1.11062 |
| | 400 | 1.07973 | 1.00812 to 1.16047 |
| Next courses, inactive courses | 110 | 0.84550 | 0.29303 to 2.37461 |
| | 120 | 0.99519 | 0.34667 to 2.37113 |
| | 130 | 1.05317 | 0.33907 to 2.42704 |
| | 140 | 1.30522 | 0.37396 to 2.48212 |

The recommendation-inactive means are monotone around the crossing, and the class fails acceptance. Every free-knee candidate crosses at basis 59 or earlier, below the measured basis-60 mean of 0.98485, and no candidate crosses between the basis-60 and basis-70 means. The smallest-residual curve has its knee at basis 244 and crosses at basis 59. Its predictions at bases 50, 60, 70 and 80 are 0.86739, 1.02989, 1.19239 and 1.35489, all inside the measured ranges. The basis-60 mean is 0.98485, within 1.5 percent of 1.0 core-second, inside a 0.39965 to 2.01436 range, so the basis-59 crossing is the best consistent description of these numbers, and the curve and the cutoff agree.

The applied values are in `config/admission.toml`. The recommendation rows set the `ADMISSION_RECOMMENDATION_ACTIVE_*` and `ADMISSION_RECOMMENDATION_INACTIVE_*` keys, and the next-course rows set the matching `ADMISSION_NEXT_COURSES_*` keys.

| Class | Knee basis | Origin cost | Slope | Tail cost | Tail slope | Heavy basis |
|---|---:|---:|---:|---:|---:|---:|
| Recommendation, active only | 181 | 0.28268 | 0.00808 | 1.72143 | 0.00499 | 92 |
| Recommendation, inactive courses | 244 | 0.10363 | 0.01625 | 4.01941 | 0.00817 | 59 |
| Next courses, active only | 230 | 0.10883 | 0.00358 | 0.92217 | 0.0009 | 317 |
| Next courses, inactive courses | 398 | 0.05998 | 0.00803 | 3.23171 | 0.00061 | 121 |

The two curves share one origin basis each, `ADMISSION_RECOMMENDATION_ORIGIN_BASIS` and `ADMISSION_NEXT_COURSES_ORIGIN_BASIS`, both set to 3. The values outside the four curves are the inactive-search charge `ADMISSION_SEARCH_INACTIVE_COST_CORE_SECONDS` at 0.22689 core-seconds, the mean of the inactive title mean 0.22884 and the inactive code mean 0.22495, each over three samples, and the graph cutoff `ADMISSION_GRAPH_HEAVY_SECONDS` at 1.0 second.

No measured graph reaches the graph cutoff. The largest graph, the inferred target with 1,363 drawing elements, recorded 0.2233 elapsed seconds in the three-miss matrix and 0.2282 in the ten-miss matrix.

The applied curve reaches 1.0 core-second at the heavy basis of each class, and the basis below it lies under 1.0. The active recommendation reads 0.99372 at basis 91 and 1.00180 at basis 92, the inactive recommendation 0.99738 at basis 58 and 1.01363 at basis 59, the active next courses 0.99957 at basis 316 and 1.00047 at basis 317, and the inactive next courses 0.99949 at basis 120 and 1.00752 at basis 121.

## Failed approaches

### One report miss per basis

The first fit sampled one report miss for each class, scope, inference setting and basis. Each point was therefore one course set, and its minimum, maximum and mean were the same number, so the equal weight per basis mean that the rule requires was not met.

The recommendation-inactive class carried a squared residual of 3.8534 and an RMSE of 0.5667, and its fitted crossing was basis 33. Its measured points were not monotone in basis size, because each basis is a different course set whose report miss loads a different prerequisite closure. Basis 150 read 4.0204 core-seconds and basis 200 read 2.6237. The next-course inactive point at basis 60 read 1.3191 core-seconds. The four cutoffs from that fit were 87, 33, 374 and 138.

The fit followed the set-to-set variation rather than the cost of a larger basis. Its recommendation-inactive crossing at basis 33 contradicted the measured basis-40, basis-50 and basis-60 means, which all lay below 1.0 core-second, and the applied cutoff would have charged a read heavy well before the measured cost reached the line.

### A fixed knee with three misses

The next fit measured three genuine distinct misses per point and held the knee at the configured basis, 20 for the recommendation curves and 25 for the next-course curves. The recommendation-inactive class then carried a squared residual of 1.1871, an RMSE of 0.3145 and a crossing at basis 50. Its measured basis-50 mean was 0.8120 with a 0.7622 to 0.8767 range, its basis-60 mean 0.9296 with a 0.7689 to 1.0464 range, and the smallest measured mean at or above 1.0 was basis 100 at 1.3919.

A probe of the knee did not remove the disagreement. Knees of 20, 30, 40, 50 and 60 gave squared residuals of 1.1871, 1.1557, 1.1500, 1.1267 and 1.0801 and crossings at 50, 48, 47, 47 and 49. The residual fell by less than 10 percent, so the configured knee was kept, and the crossing lay below bases whose measured means were under 1.0. The same probe on the next-course inactive class moved its residual from 0.6907 at knee 25 to 0.6696, 0.6428 and 0.5920 at knees 40, 50 and 60, with crossings at 121, 117, 114 and 108.

A fixed knee is a shape assumption, and the measured recommendation-inactive curve bends later and more steeply than a knee at basis 20 allows. A knee key for each route could not express the two scopes of one curve separately, so the four per-scope knee keys replaced the two route keys.

### A free knee with three misses

The third fit searched the knee for each class and measured three genuine distinct misses per point. Both inactive classes failed acceptance. The recommendation-inactive candidate took its knee at basis 250, crossed at basis 60 and left a squared residual of 0.2301, and its prediction at basis 70, 1.17367, fell outside the measured 0.75906 to 1.03602 range. The next-course inactive candidate took its knee at basis 250, crossed at basis 111 and left a squared residual of 0.31269, below the measured basis-130 mean of 0.88229. The two active classes passed, with the recommendation knee at basis 28 and crossing at 88, and the next-course knee at basis 236 and crossing at 323.

With three samples the minimum-to-maximum ranges were wide and the means were not monotone, so no single-knee curve of this form sat inside the measured ranges near the crossing for either inactive class. With 10 misses per point the next-course inactive class passed, with its crossing at basis 121 between the basis-120 mean 0.99519 and the basis-130 mean 1.05317. The recommendation-inactive class failed, by one basis.

## Interpretation

The curves describe the cost of a basis size over heterogeneous course sets, not the cost of one fixed set. The same basis size is a different set of courses in each sample, and a report miss loads a different prerequisite closure, so the next-course inactive range at basis 120 spans 0.34667 to 2.37113 around a mean of 0.99519.

The recommendation-inactive cutoff errs toward the heavy class. The applied curve reaches 1.0 at basis 59 while the measured basis-60 mean is 0.98485, so a read of 59 or 60 courses is charged heavy slightly before the measured mean reaches the line. For admission, charging slightly early is the safer direction, because the opposite direction would admit a read above the line as light.

The cutoffs for the three accepted classes sit between measured means that bracket 1.0, so they match the measured crossing within one measured basis.

## Limitations

The curves describe one 500-course pool on one dataset snapshot and one server, and a different pool changes the cost of a basis size. The endpoint means include the report miss that admission charges. Admission selects a class and a charge and does not enter the measured core-seconds, so the values price the work and not the queueing that follows admission.

The inactive-search charge is one fixed value for every query that includes inactive courses. It does not scale with query length, so a long query is charged the same 0.22689 core-seconds as the two short search shapes it was computed from.

Each search mean and range is over three distinct query texts, so it spans query difficulty as well as runtime.

The graph cutoff is untested by these runs. The largest measured graph elapsed is 0.2282 seconds against the 1.0-second cutoff, so the runs say nothing about where a graph becomes heavy.

## Baselines

A follow-up compares against the applied curves and heavy bases in the table above, the four cutoffs 92, 59, 317 and 121, the inactive-search charge 0.22689 core-seconds and the graph cutoff 1.0 second. The product means at basis 60 are 0.8154 core-seconds for the active recommendation, 0.9296 for the inactive recommendation, 0.2522 for the active next courses and 0.6299 for the inactive next courses. The largest measured graph elapsed is 0.2233 seconds in the three-miss matrix and 0.2282 in the ten-miss matrix.

## Open questions

- Untested: whether a curve whose input includes the report-cache state or the size of the prerequisite closure would place the recommendation-inactive crossing between the measured basis-60 and basis-70 means.
- Untested: whether measured bases between 400 and 499, or more bases above 250, would move the inactive knees at 244 and 398 and the cutoffs they set.
- Untested: whether a graph larger than 1,363 drawing elements reaches the 1.0-second cutoff, since no measured graph triggered the graph heavy class.
- Untested: whether charging measured elapsed seconds instead of curve core-seconds for recommendation and next-course reads would change which reads are refused, because the matrix measured CPU and not queueing.
