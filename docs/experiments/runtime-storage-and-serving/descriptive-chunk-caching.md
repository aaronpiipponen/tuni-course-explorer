# Descriptive chunk caching

This report measures whether a bounded descriptive chunk cache shortens repeated heavy recommendation reads and what the cache costs at four process equivalents.

**Evidence status:** Corrected. **Run dates:** 21 and 22 October 2026.

## The question

A recommendation request reads the descriptive chunks of the basis courses and of the candidate courses, scores them, and returns a report. A repeated request over the same basis reads many of the same chunks. The experiment asked whether a bounded per-process cache of those read results measurably shortens the tail of a repeated heavy recommendation call, alone or beside an eagerly built lookup projection or a compact projection. It also asked whether one interactive catalogue read stays fast while two heavy recommendation calls run, at a per-process share that fits the 1.074 GB aggregate (1,073,741,824 bytes) at four process equivalents.

A descriptive chunk is a stored [chunk](/docs/reference/glossary.md#capture-and-data-preparation) of a course version's content or learning-outcomes text. The descriptive chunk cache is a bounded store of the read carriers those two descriptive reads return. An entry is keyed by the read triple `(group_id, sisu_course_unit_id, representative_source_hash)` and holds the ordered carriers for that triple. A carrier holds the group identity, the text field and language, the chunk index, the retained text origin, the stored character count and the vector. The chunk text itself is not part of a carrier.

A heavy recommendation call here is one complete recommendation command over a fixed [basis](/docs/reference/glossary.md#prerequisites-and-routes), reading the basis and candidate chunks and scoring them. An interactive catalogue read is one catalogue report read. A process equivalent is one process's memory and CPU footprint, not a configured worker process and not an HTTP request.

The report separates four things: what the run measured, what the run's rule concluded, which condition the evidence left unproven, and which trade-off was selected after the measurements. The cache is applied in the product. Its measured heavy-call benefit is confined to the 50-course bases. The 200-course basis, which the concurrency and four-process arithmetic target, shows no benefit beyond its own spread.

## Fixed bases and variants

Three basis sets appear, and they are not interchangeable.

| Set | Construction | Result count |
|---|---|---:|
| 50-course basis | A separate saved 50-course input, with 1,874 candidate triples in the serial cases | 319 |
| 200-course basis | 200 shortlist group identities from the selection, with 2,925 candidate triples | 629 |
| 50-course prefix | The first 50 group identities of the 200-course basis | 432 |

The 200-course basis is built from the 200 `shortlist_group_ids` of the fixed selection in recorded order. Every shortlist group whose triple occurs in the fixed 1,874-triple candidate set is kept, then the remaining groups are filled from that candidate set in recorded order. That kept 56 shortlist groups and filled 144, for 200 distinct groups. The builder read each chosen triple's represented summary and asserted equality, and 200 of 200 matched.

The 50-course basis is a separate saved input with a different construction. The 50-course prefix is the reproduction's set, used only by the product-path reproduction. Its construction and its 432 results do not extend the serial 50-course case or its 319 results.

| Variant | What changes | Cases |
|---|---|---|
| Baseline | No descriptive chunk cache. The lookup projection builds on first use. The source-fact cache holds 8,000 entries. | 50 and 200, serial |
| 33.554 MB bound | A descriptive chunk cache at 248 entries | 50 and 200, serial |
| 67.109 MB bound | A descriptive chunk cache at 497 entries | 50 and 200, serial, and 2 and 4 process equivalents |
| Eager projection | The lookup projection built at process start | 50 and 200, serial |
| Compact projection | A compact lookup projection | One catalogue-read case |

Every serial case runs one process with one cold call and three warm calls. The concurrency cases run one launcher each and are described below.

## Calls, warm state and the threshold

Each serial case ran four calls in one fresh process: one cold call and three warm calls. The calls are one sequence, not independent trials. The first call fills the caches, and the three warm calls show the state it left.

The chunk cases ran a descriptive probe before the timed calls, and the probe warms shared database buffers. The cold calls are therefore not a cache-only comparison. The 50-course cold calls were 9.599 s and 9.579 s against the baseline 10.125 s. The 200-course cold calls were 23.230 s and 23.098 s against 28.251 s. The baseline 200 cold call ran first and paid a cold HNSW and page-cache cost that the other cold calls did not pay. Only the warm tails and the concurrency interactive tails inform the qualification.

The comparison threshold is the larger of the two cases' own warm spreads. A saving or loss below that threshold is not read as an effect.

| Case | Basis | Warm minimum (s) | Warm median (s) | Warm maximum (s) | Spread (s) |
|---|---:|---:|---:|---:|---:|
| Baseline | 50 | 9.019 | 9.030 | 9.044 | 0.025 |
| 33.554 MB bound | 50 | 8.261 | 8.333 | 8.399 | 0.138 |
| 67.109 MB bound | 50 | 7.728 | 7.755 | 7.892 | 0.163 |
| Eager projection | 50 | 9.024 | 9.101 | 9.512 | 0.487 |
| Baseline | 200 | 21.794 | 21.847 | 22.016 | 0.222 |
| 33.554 MB bound | 200 | 22.327 | 22.347 | 22.561 | 0.234 |
| 67.109 MB bound | 200 | 21.421 | 21.633 | 21.821 | 0.399 |
| Eager projection | 200 | 21.841 | 21.872 | 22.187 | 0.346 |

## Warm heavy-call results

| Bound | Basis | Maximum saving (s) | Median saving (s) | Own spread (s) | Result |
|---|---:|---:|---:|---:|---|
| 33.554 MB | 50 | 0.645 | 0.697 | 0.138 | Saving beyond the spread |
| 67.109 MB | 50 | 1.152 | 1.276 | 0.163 | Saving beyond the spread |
| 33.554 MB | 200 | -0.545 | -0.500 | 0.234 | Loss beyond the spread |
| 67.109 MB | 200 | 0.195 | 0.214 | 0.399 | Saving within the spread |

A positive value is a saving against the matching baseline.

The 67.109 MB bound shortens the 50-course warm maximum by 1.152 s and the median by 1.276 s, both beyond the 0.163 s spread. At the 200-course basis it shortens the maximum by 0.195 s and the median by 0.214 s, less than the 0.399 s spread. The 33.554 MB bound shortens the 50-course maximum by 0.645 s and the median by 0.697 s, beyond the 0.138 s spread. At the 200-course basis the 33.554 MB bound is 0.545 s slower at the maximum and 0.500 s slower at the median, beyond the 0.234 s spread. No smaller qualifying bound exists, because the 33.554 MB bound loses at the 200-course basis.

The warm maxima of the four serial variants are plotted below.

![Warm heavy recommendation call maximum for the baseline, the 33.554 MB bound, the 67.109 MB bound and the eager projection at both basis sizes. The 67.109 MB bound gives the lowest maximum at each basis, and every 200-course case is above 21 seconds.](/docs/charts/runtime-chunk-cache-warm-max.svg)

The eager projection's warm maximum is 9.512 s at the 50-course basis and 22.187 s at the 200-course basis, against 9.044 s and 22.016 s for the baseline. Its warm spread is 0.487 s at 50 and 0.346 s at 200, so no shortening stands beyond its own spread. The 67.109 MB bound is the only serial bound that saves beyond the spread at the 50-course basis without losing beyond the spread at the 200-course basis. Its saving is confined to the 50-course basis.

## What the cache retained

The working set is the set of triples one call reads. The 50-course set is 50 basis triples plus 1,874 live candidate triples. The 200-course set is 200 basis triples plus 2,925 live candidate triples, 3,125 entries. The 67.109 MB bound holds 497 of the 3,125 entries, 15.9 percent. The 33.554 MB bound holds 248, 7.9 percent. The cold call fills the basis and candidate entries, so both bounds evict the basis and the oldest candidates.

Warm hits show the same working-set limit.

| Bound | Basis | Basis hits | Candidate hits | Candidate misses | Candidate evictions |
|---|---:|---:|---:|---:|---:|
| 33.554 MB | 50 | 0 | 198 | 1,676 | 1,676 |
| 33.554 MB | 200 | 0 | 48 | 2,877 | 2,877 |
| 67.109 MB | 50 | 0 | 447 | 1,427 | 1,427 |
| 67.109 MB | 200 | 0 | 297 | 2,628 | 2,628 |

The basis hit count is zero at both bounds and both bases. The 67.109 MB bound holds 447 of 1,874 candidate triples at the 50-course basis and 297 of 2,925 at the 200-course basis. The 33.554 MB bound holds 198 and 48.

| Case | Accounted chunk term (bytes) | Measured chunk bytes | Entries |
|---|---:|---:|---:|
| 33.554 MB, 50 | 33,554,432 | 33,318,668 | 248 |
| 33.554 MB, 200 | 33,554,432 | 35,131,425 | 248 |
| 67.109 MB, 50 | 67,108,864 | 67,246,566 | 497 |
| 67.109 MB, 200 | 67,108,864 | 68,483,256 | 497 |
| 50-course prefix, 497 entries | 68,483,618 | 68,937,692 | 497 |

The 33.554 MB and 67.109 MB accounted terms are the nominal bounds, 33,554,432 and 67,108,864 bytes. The entry count is derived from the average entry size the descriptive probe measured, 134,839.596 bytes at the 50-course basis and 134,759.103 bytes at the 200-course basis, and the largest entry is 759,423 bytes. The retained set includes entries larger than the average, so the count bound does not cap bytes exactly.

The 33.554 MB case at the 200-course basis measures 1,576,993 bytes above its term. The 67.109 MB case at the 200-course basis measures 1,374,392 bytes above its term. The 67.109 MB case at the 50-course basis measures 67,246,566 bytes against the 67,108,864-byte term. The four-equivalent cache process measured 69,739,866 bytes, 2,631,002 bytes above the term.

The measured bytes are Python object-graph sizes, not resident memory. Each facility counts shared objects once within the facility, and the facilities are summed.

## Concurrency

Four concurrency cases ran, two at two process equivalents and two at four. At two equivalents, two serving processes run. The first runs one cold heavy recommendation call beside a repeated interactive catalogue reader thread, and the second runs one cold heavy recommendation call. At four equivalents, the same two active processes run plus two holder processes. The holders build a full cache set and then idle. They run no work while the two heavy calls and the reader run, so the interactive read is measured under a four-process memory footprint. Within each group, the baseline case and the cache case share the layout.

The diagram shows the processes in each measured group and the work each runs.

![Two measured process groups. At two process equivalents, serving process a runs one cold heavy recommendation call beside a reader thread, and serving process b runs one cold heavy call. At four process equivalents the same two active processes run beside two dashed holder processes that build caches and then idle.](/docs/diagrams/chunk-cache-process-equivalents.svg)

The four-equivalent case is not four heavy recommendation calls. The interactive reader is a thread in the first heavy process, so that process's CPU seconds include the reader. The cases count process equivalents, not the configured `WEB_WORKERS` value. No front router, admission decision or HTTP response is part of the measurement. The server has four usable cores, so the four-equivalent case fills every core and has no spare core.

| Case | Heavy a (s) | Heavy b (s) | Samples | First catalogue (s) | Warm minimum (s) | Warm median (s) | Warm maximum (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Baseline, 2 equivalents | 31.498 | 24.643 | 32 | 2.206 | 0.180 | 0.257 | 0.636 |
| Baseline, 4 equivalents | 30.274 | 23.025 | 31 | 2.337 | 0.176 | 0.250 | 0.872 |
| 67.109 MB bound, 2 equivalents | 30.997 | 23.611 | 35 | 2.230 | 0.177 | 0.272 | 0.631 |
| 67.109 MB bound, 4 equivalents | 30.847 | 23.416 | 35 | 2.183 | 0.175 | 0.270 | 0.564 |

The heavy calls are cold in every concurrency process, so they issue no cache hits. Their walls, 23.025 to 31.498 s, include contention and are not cache-benefit evidence.

The interactive maximum with the cache is 0.631 s at two equivalents against 0.636 s, and 0.564 s at four against 0.872 s. The warm median is 0.272 s against 0.257 s at two, and 0.270 s against 0.250 s at four, so the maximum is the statistic that does not worsen. The first catalogue read is 2.230 s against 2.206 s at two and 2.183 s against 2.337 s at four, and it includes the lazy projection build. The run's qualification rule used the interactive maximum. The four-equivalent baseline maximum of 0.872 s carries scheduler contention because the case has no spare core.

The interactive reads are plotted below.

![First cold and warm-maximum interactive catalogue read under concurrent heavy recommendation calls at two and four process equivalents, for the baseline and the 67.109 MB bound. The warm maximum is lower with the cache at both process counts.](/docs/charts/runtime-chunk-cache-interactive-tail.svg)

The four-equivalent cache process measured 69,739,866 bytes of retained chunk bytes and a largest retained process graph of 108,903,771 bytes. Four such graphs hold 435,615,084 bytes, which is 638,126,740 bytes inside the aggregate.

## Eager projection

The eager projection built the lookup projection at process start. The build took 1.830 s at the 50-course basis and 1.685 s at the 200-course basis, with six statements and 27,999,707 bytes. The lazy first catalogue read pays the build. The eager read uses the projection built at process start.

| Basis | Lazy cold first read (s) | Lazy warm second read (s) | Eager first read (s) |
|---|---:|---:|---:|
| 50 | 2.538 | 0.227 | 0.169 |
| 200 | 2.111 | 0.175 | 0.159 |

The eager first read is 0.159 to 0.169 s against 2.111 to 2.538 s for the lazy cold first read. The build moves to process start at the same total build cost and the same 27,999,707 bytes.

The heavy call does not shorten. At the 50-course basis the eager cold call is 9.901 s against the baseline 10.125 s, a 0.224 s difference. The baseline warm spread is 0.025 s and the eager warm spread is 0.487 s. The recommendation path never reads the lookup projection, so the cold difference is not a projection effect, and the warm tails are 9.101 s and 9.030 s at the 50-course basis and 21.872 s and 21.847 s at the 200-course basis.

The 200-course cold difference, 22.705 s against 28.251 s, is the baseline's first-process cold HNSW and page-cache cost. The eager cold neighbour search is 8.156 s against the baseline cold 12.458 s, and the three eager warm neighbour reads are 7.818, 7.820 and 7.821 s. The 8.302 s warm neighbour read belongs to the 67.109 MB bound's 200-course case, not to this case. The facility was skipped because no heavy call shortens.

## Compact projection

The compact projection retains only the fields the catalogue report and the lexical matcher consume. It drops the summary and version wrapper objects, the module-version identifier that the strict catalogue path does not read, the period identifiers and the module fields the lookup projection does not carry.

| Projection | Total bytes | String bytes | Structure bytes | Scalar bytes |
|---|---:|---:|---:|---:|
| Product lookup projection | 27,999,707 | 11,186,191 | 16,813,096 | 420 |
| Compact projection | 17,863,687 | 9,924,907 | 7,938,360 | 420 |
| Saving | 10,136,020 | | | |

The compact projection retains 63.8 percent of the product projection bytes, 36.2 percent fewer, a saving of 10,136,020 bytes. All 16 fixed lexical cells match for exact, substring and fuzzy results, with no mismatch. The catalogue report digest is identical.

The product lazy cold read is 1.888 s and the warm read 0.241 s. The compact row read is 1.648 s, its build 0.168 s and its report 0.036 s, so the compact cold path is 1.852 s against 1.888 s and the compact warm report is 0.036 s against 0.241 s.

The matcher comparisons ran the same product matchers over both structures and returned identical results. Their wall time was not isolated. The rule required the matcher cells not to slow, and that condition is unproven. The facility was skipped with the measured saving recorded.

## The four-process accounting

The per-process share has three terms: the lookup projection bytes, the source-fact entry count times its per-entry bytes, and the descriptive chunk entry count times its per-entry bytes. The configured terms are the lookup projection at 33,554,432 bytes, the source facts at 8,000 entries by 7,006 bytes, 56,048,000 bytes, and the descriptive chunk term. The aggregate is 1.074 GB. The decision arithmetic uses the configured shares, because those are the configured bound. The measured column is the observed fill at this basis.

| Case | Accounted per process (bytes) | Accounted, four (bytes) | Measured per process (bytes) | Measured, four (bytes) | Measured headroom, four (bytes) |
|---|---:|---:|---:|---:|---:|
| Baseline 50 | 89,602,432 | 358,409,728 | 8,897,665 | 35,590,660 | 1,038,151,164 |
| Baseline 200 | 89,602,432 | 358,409,728 | 11,164,198 | 44,656,792 | 1,029,085,032 |
| 33.554 MB 50 | 123,156,864 | 492,627,456 | 42,216,333 | 168,865,332 | 904,876,492 |
| 33.554 MB 200 | 123,156,864 | 492,627,456 | 46,295,623 | 185,182,492 | 888,559,332 |
| 67.109 MB 50 | 156,711,296 | 626,845,184 | 76,144,231 | 304,576,924 | 769,164,900 |
| 67.109 MB 200 | 156,711,296 | 626,845,184 | 79,647,454 | 318,589,816 | 755,152,008 |
| Eager 50 | 89,602,432 | 358,409,728 | 36,897,372 | 147,589,488 | 926,152,336 |
| Eager 200 | 89,602,432 | 358,409,728 | 39,163,905 | 156,655,620 | 917,086,204 |
| Compact | 73,911,687 | 295,646,748 | 73,911,687 | 295,646,748 | 778,095,076 |
| Product-path reproduction, 497 entries | 158,086,050 | 632,344,200 | 158,540,124 | 634,160,496 | 439,581,328 |

Every accounted four-process total fits. The largest accounted total in the 14 measured cases is the 67.109 MB bound at 626,845,184 bytes. The reproduction is 632,344,200 bytes. Six accounted shares are 948,516,300 bytes and fit. Seven are 1,106,602,350 bytes and exceed the aggregate.

On the measured figures, the 67.109 MB bound at the 200-course basis is 79,647,454 bytes per process and 318,589,816 bytes at four, with 755,152,008 bytes of headroom. The reproduction is 158,540,124 bytes per process and 634,160,496 bytes at four, with 439,581,328 bytes of headroom. Six measured shares are 951,240,744 bytes and fit. Seven are 1,109,780,868 bytes and exceed the aggregate.

The compact row combines its measured projection with the configured source-fact share, because the compact case builds no source-fact cache. Its source-fact part is the configured share, not a measurement. The baseline and eager rows use the configured projection share. The measured projection is 0 bytes for the baseline and 27,999,707 bytes for the eager case. The measured source-fact figure is 8,897,665 bytes at the 50-course basis and 11,164,198 bytes at the 200-course basis, below the 56,048,000-byte share.

## The product-path reproduction

The second measurement called the product recommendation command with the implemented cache, one invocation per mode in its own process. The baseline mode had no descriptive chunk cache. The cache mode had one `DescriptiveChunkCache(max_entries=497)`. Both modes had one 8,000-entry source-fact cache. The request was `basis="completed"`, `mode="all"`, `display_language="en"`, `include_inferred=False` and `active_only=True`. The basis was the first 50 group identities of the 200-course basis. The separate 50-course basis of the serial comparison is a different input. The report returned 432 courses.

Each mode ran four calls in one process: one cold call and three warm calls. The calls are one sequence, not independent trials. The cold calls are not benefit evidence.

| Mode | Call | Kind | Wall (s) |
|---|---:|---|---:|
| Baseline | 0 | Cold | 9.884913 |
| Baseline | 1 | Warm | 9.082554 |
| Baseline | 2 | Warm | 9.188899 |
| Baseline | 3 | Warm | 9.194772 |
| Cache | 0 | Cold | 9.848544 |
| Cache | 1 | Warm | 8.018599 |
| Cache | 2 | Warm | 8.026672 |
| Cache | 3 | Warm | 7.937882 |

| Mode | Warm minimum (s) | Warm median (s) | Warm maximum (s) | Spread (s) |
|---|---:|---:|---:|---:|
| Baseline | 9.082554 | 9.188899 | 9.194772 | 0.112218 |
| Cache | 7.937882 | 8.018599 | 8.026672 | 0.088790 |

| Measure | Baseline (s) | Cache (s) | Saving (s) | Beyond the 0.112218 s spread |
|---|---:|---:|---:|---|
| Warm maximum | 9.194772 | 8.026672 | 1.168100 | Yes |
| Warm median | 9.188899 | 8.018599 | 1.170300 | Yes |

The three warm calls fall from 9.082554 to 9.194772 s to 7.937882 to 8.026672 s. The maximum saving is 1.168100 s and the median saving is 1.170300 s, against the larger warm spread of 0.112218 s. All four report digests are identical within each mode and between the two modes. The cache returns the same report.

The retention in the same run is 68,937,692 chunk bytes over 497 entries and 9,491,065 source-fact bytes over 1,263 entries. The walked source plus chunk total is 78,428,757 bytes. With the accounted projection share the walked total is 111,983,189 bytes.

## The retention assertion

The reproduction's retention assertion required the cache's retained bytes at the 497-entry bound to be at or below 68,483,618 bytes, the 497-entry term at 137,794 bytes per entry. The run measured 68,937,692 bytes, 454,074 bytes or 0.663 percent above the term. The measured cache is 68.937692 MB against the 68.483618 MB accounted term.

The cause is the entry mix. The 68,483,618-byte term is 497 entries at 137,794 bytes, and that value rounds the average over the 497 retained entries of the 200-course serial case, 137,793.27 bytes per entry. The reproduction's 50-course prefix read a heavier mix. Its 497 most recently read triples average 138,707.63 bytes, 0.66 percent heavier.

The earlier per-process figure of 158,085,688 bytes combined the accounted projection and source shares with the 68,483,256-byte serial measurement. The reproduction's cache measurement gives 158,540,124 bytes on the same three-term formula.

The decisive budget holds. Four processes hold 634,160,496 bytes, which is 634.160496 MB, inside the 1.074 GB aggregate, with 439,581,328 bytes, which is 439.581328 MB, of headroom. Six shares fit at 951,240,744 bytes and seven do not at 1,109,780,868 bytes. The measured source facts are far below the 56,048,000-byte accounted share, so that term holds the accounting conservative.

The 137,794-byte per-entry value and the 497-entry count stand as the selected budget values. The trade-off is recorded and is not re-evaluated here. The retained mix depends on the requested basis, so a different basis moves the measured cache bytes around the accounted term.

The measured and accounted chunk bytes are plotted below.

![Measured retained chunk bytes against the accounted chunk term for the 33.554 MB and 67.109 MB bounds at both bases and for the reproduction. The 67.109 MB cases and the reproduction exceed their accounted terms, and the 33.554 MB case at the 50-course basis stays below.](/docs/charts/runtime-chunk-cache-retention.svg)

## Corrections and reversals

### The recommendation reversal

The first measured result recommended no facility. It found the 67.109 MB bound's benefit confined to the 50-course basis, no benefit beyond the 0.399 s spread at the 200-course basis, and the smaller 33.554 MB bound slower at the 200-course basis. It also found the eager projection ineffective on the heavy path and the compact projection unproven, and it called the product-path reproduction not applicable.

That outcome was reversed. The 497-entry cache at 137,794 bytes per entry was selected and applied in the serving path. The benefit measurements did not change. The benefit at the 50-course basis and the absence of a spread-qualified benefit at the 200-course basis both stand. The selection is a budget trade-off, not a finding that the 200-course tail improves.

### The reference deviation

The 50-course exact reference is the product digest written by the measured run, not the fixed pre-change digest. The pre-change digest is not reproducible by the product scorer in use. The saved report scored with that scorer has the same 319 results in the same order, with identical course payloads, derived flags, null overlaps and ties, and differs only in the last bits. The maximum absolute delta is 2.1316282072803006e-14 for relatedness and score and 5.684341886080802e-14 for overlap. The structural parity is recorded separately.

The 200-course reference digest was written by the first measured baseline 200 cold call, and it holds 629 results. That reference is the run's own product digest, not a replacement of a fixed reference. The 50-course reference replacement is the only documented reference deviation.

### Failed and superseded attempts

Eight process invocations failed or were superseded before the measured case set. Every attempt and its diagnosis is preserved.

| Case | Outcome | Cause and correction |
|---|---|---|
| Baseline 50 | The report digest differed from the fixed pre-change reference | The product scorer changes the last bits at the recorded maxima. The measured product digest became the exact reference, with structural parity recorded separately. |
| Baseline 50 | `MemoryError` | The 276 MB 50-course basis input was parsed and held for the whole case, then parsed again for the comparison. The correction read only the input digest and used the 152,191-byte report payload for the comparison. |
| Baseline 50 | `MemoryError` | The chunk-payload digest built all 7,657 candidate payloads and their embeddings in one list. The correction streamed one payload at a time and released the call's large locals before the retained walk. |
| 33.554 MB at 50 | Superseded, no error | The retained-byte walk ran inside the timed basis and candidate read steps, adding 1.3 to 2.8 s of accounting. The walk moved outside the call timing. |
| 33.554 MB at 200 | Superseded, no error | The same accounting defect. The case ran again with the walk outside the timing. |
| 67.109 MB at 50 | Superseded, no error | The same accounting defect. The case ran again with the walk outside the timing. |
| Compact | An import failed for the normalized-text helper | The helper lives in another module. The correction imported it from the module that owns it. |
| Compact | An attribute error on the course summary | The exact and substring matchers return summaries, not lookup rows. The correction read the group identity from the returned summaries. |

### Process and revision accounting

Twenty-two process invocations ran. Fourteen produced the measured cases, and eight failed or were superseded. The run's process rule allowed one diagnosed correction rerun and at most 16 measurement processes. The 14 measured cases stay inside 16. The eight correction attempts exceed the one-rerun allowance by seven. The deviation is recorded with the results.

No timeout, address-space, headroom or read-only limit was exceeded. The 600 s outer limit and the 480 s sample timer never fired. Every process reported the 2.147 GB address space. Every connection was read-only.

The 14 accepted cases ran on four revisions of the measurement program. One revision ran only the 200-course basis builder, one ran the two baseline cases, one ran the four chunk-bound and two eager cases, and one ran the compact case and the four concurrency cases. The corrections that separate them are the reference digest replacement and the two `MemoryError` fixes for the baseline cases, the retained-byte accounting for the chunk cases, and the imports and summary reads for the compact case. The baseline cases were not measured again on the later revisions. Each concurrency comparison used one revision for both variants.

## Where the line ended

| Facility | Measured result | Disposition |
|---|---|---|
| 33.554 MB bound | 50-course saving of 0.645 s maximum and 0.697 s median beyond the 0.138 s spread. 200-course loss of 0.545 s maximum and 0.500 s median beyond the 0.234 s spread. | Not selected |
| 67.109 MB bound | 50-course saving of 1.152 s maximum and 1.276 s median beyond the 0.163 s spread. 200-course saving of 0.195 s maximum and 0.214 s median within the 0.399 s spread. | Selected and applied at 497 entries |
| Eager projection | The 1.685 to 1.830 s build moves to process start. No heavy call shortens. | Not selected |
| Compact projection | 10,136,020 bytes and 36.2 percent fewer. The 16 lexical cells and the catalogue report are identical. The matcher wall time is not isolated. | Not selected, with the measured saving recorded |

The product config sets `WEB_CHUNK_CACHE_ENTRIES = 497`, `WEB_CHUNK_CACHE_ENTRY_BYTES = 137794`, `WEB_WORKERS = 4` and `WEB_RETAINED_CACHE_AGGREGATE_BYTES = 1073741824`. The three retained caches of one serving dataset identity and their accounting are described in [Web server](/docs/backend/interfaces/web-server.md#the-dataset-scoped-retained-caches). The per-process share is 158,086,050 bytes and four processes hold 632,344,200 bytes. The first 14-case run changed no product code or configuration. The cache was implemented and applied after the measurements.

The applied cache is one instance per serving dataset identity, in the embedding read path. The recommendation route passes it beside the source-fact cache, and the two descriptive reads of the recommendation command share it. The all-field read passes no cache, and a supplied cache without `descriptive_only` raises `ValueError`. The store holds at most 497 entries in least-recently-used order, one lock serializes reads and writes, and an empty tuple is a retained entry. The three retained caches are built together, and a different serving dataset identity builds a different set.

An entry holds the read triple and its carriers. Nothing is written to disk or to the database. The cache's place in serving is described in [Coverage and ranking](/docs/backend/search-and-discovery/coverage-and-ranking.md#the-descriptive-chunk-cache).

## Limitations

- One prototype policy per fresh process and one sequence of four calls. The calls are not independent trials, and the values are not a distribution or a confidence interval.
- The chunk cases run a descriptive probe before the timed calls, which warms shared database buffers. The cold comparison is not a cache-only comparison, and only the warm tails and the concurrency interactive tails inform the decision.
- Case order affects the 200-course cold calls. The baseline 200 cold call ran first and paid a cold HNSW and page-cache cost that the other cold calls did not pay.
- The retained figures are Python object-graph sizes from `sys.getsizeof`, not resident memory. Each facility is walked with shared objects counted once within that facility, and the facilities are summed.
- The measured retained fill is below the configured shares at this basis, so the measured arithmetic is an observation. The decision arithmetic uses the configured shares.
- The concurrency reader runs as a thread in the first heavy process, which is one serving process's synchronous handler shape. That process's CPU seconds include the reader.
- The server has four usable cores. The four-equivalent case has no spare core, so the interactive tail at four equivalents also carries scheduler contention.
- The compact projection's matcher-cell wall time was not isolated. The cells were compared for identical results only.
- The process and correction budget deviation is recorded above, and the accepted cases ran on four revisions of the measurement program, one of them only the 200-course basis builder.
- The product-path reproduction used the first 50 group identities of the 200-course basis and returned 432 results. Those values do not extend the serial 50-course case or its 319 results.
- The measurements ran processes, not HTTP requests. No front router, admission control, configured worker count or response delivery is measured.
- One pinned dataset and one call sequence per case. A different basis set can move the measured cache bytes around the accounted term.
- The measurements used similarity data only. No official prerequisite label, inferred edge or target official structure entered a selection or timing input.

## Setup details

| Item | Value |
|---|---|
| Date | 21 and 22 October 2026 |
| Hardware | 4-core aarch64 server, 23.6 GB of RAM |
| Interpreter for the 14-case run | CPython 3.14.3 |
| Product-path environment | `uv run python` in the project environment |
| Thread limits | `OPENBLAS_NUM_THREADS`, `OMP_NUM_THREADS`, `MKL_NUM_THREADS`, `BLIS_NUM_THREADS` and `VECLIB_MAXIMUM_THREADS` all set to 1 |
| Address space | 2.147 GB (2,147,483,648 bytes), soft and hard, asserted in every process |
| Outer limit | 600 s, `timeout --signal=KILL` |
| Sample limit | One fatal 480 s in-process timer per sample and per case |
| SQL policy | `default_transaction_read_only=on` and `statement_timeout=30000` |
| Headroom | `MemAvailable` at least 4.295 GB (4,294,967,296 bytes) for serial and two-equivalent cases and at least 8.590 GB (8,589,934,592 bytes) for the four-equivalent case. The smallest recorded value was 11.08 GB. |
| Heavy jobs | One at a time. Only the children of one concurrency case ran together. |
| Launcher deadline | 580 s deadline in the launcher. The concurrency children inherit the 2.147 GB limit. |
| Read-only proof | Every connection reported `default_transaction_read_only=on` and a 30 s statement timeout, and each probe transaction rolled back. |
| Embedding data | Stored BGE-M3 vectors with 1,024 components. No embedding model ran. |
| Dataset | One pinned captured catalogue, read without the selected-dataset pointer |
| Source-fact cache | One `PrerequisiteSourceFactCache(max_entries=8000)` per process |
| Descriptive chunk cache | One `DescriptiveChunkCache(max_entries=497)` per process in cache mode, none in baseline mode |
| Fixed request for the reproduction | `basis="completed"`, `mode="all"`, `display_language="en"`, `include_inferred=False`, `active_only=True` |
| Results per report in the reproduction | 432 courses |

The fixed inputs were hashed before timing. Every measured case asserted its report digest against its basis reference. The connections were read-only, and no product data was written.

## Untested questions

- Whether the compact projection's matcher cells slow under a direct timer. The run compared their results only, so the no-slowdown condition is untested.
- Whether the warm-tail saving holds under the configured HTTP worker count, the front router and admission control. The concurrency cases measured process equivalents, not HTTP requests. Untested.
- Whether a second requested basis moves the measured cache above or below the accounted term in the same direction as the 50-course prefix. One heavier mix is recorded, and a second basis is untested.
