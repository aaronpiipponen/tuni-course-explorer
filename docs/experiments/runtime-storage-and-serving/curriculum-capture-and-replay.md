# Curriculum capture and replay

This report records two curriculum captures, one source-free verification and two normalization replays, testing collection, evidence preservation and the reconciliation of captured objects with normalized versions.

**Evidence status:** Observational. **Run date:** 11 September 2026.

## The question

The line asked what one complete capture of the public curriculum source produces in responses, stored objects and elapsed time, and whether the stored evidence can be verified and normalized again without reading the source. It also asked whether a full-catalogue manifest normalizes every captured course object exactly once, and how an explicit null course code is handled without losing the other versions of the same canonical course.

The evidence covers two captures at different scopes. The first is one timed capture of the curriculum period for the 2026-2027 academic year. The second captured the full catalogue over 21 curriculum periods, from 2006 to 2026, and its verified manifest was replayed twice without the source. The replay is a separate step from the capture, and the dates of the two replays are not recorded.

## Two captures, separate scopes

| Run | Scope | Recorded quantities | Not recorded |
|---|---|---|---|
| 2026-2027 capture | One curriculum period | 125.49 s elapsed, 6,071 responses, 17,020 course snapshots, 3,724 module snapshots, 59 unresolved course groups | Hardware, network conditions, checkpoint size |
| Full-catalogue capture and replay | One capture of 21 curriculum periods, replayed twice | 14,405 responses, 24,932 course objects, 15,553 module objects, 24,931 normalized course versions, one null-code exclusion, 88 unresolved course groups | Elapsed capture timer, replay dates, hardware, network conditions |

The 2026-2027 capture covers one curriculum period. The full-catalogue capture covers 21 periods. The two scopes are not added together, and the report draws no speed comparison between them. The full manifest's counts describe its scale. The record holds no separately timed end-to-end value for that capture.

Both captures ran on 11 September 2026. The 125.49 seconds is the recorded elapsed time for the 2026-2027 capture. Its manifest's start and finish timestamps span 100.85 seconds. The evidence does not reconcile the two timing boundaries, so they are not treated as the same measurement. The full-catalogue capture records a start and a finish timestamp but no elapsed timer, and the report draws no elapsed duration from them.

## Capture and checkpoint method

The method below describes the implementation used by the recorded captures.

A [capture](/docs/backend/catalogue/ingestion.md) is one run that downloads course and module data from the public curriculum source and stores it unchanged. The captured source is the anonymous public JSON interface. The capture reads the curriculum periods first, then the course and module version references for each period. Reference queries enumerate partitions and pages to a proven total rather than accepting a truncated set. Exact versions that no captured object represents are fetched in bounded batches.

### Checkpoints and source snapshots

Responses are written in bounded sets of `CAPTURE_CHECKPOINT_RESPONSE_COUNT` responses. The key is separate from the source request batch `KORI_BATCH_SIZE`. Each set is published through one validated manifest update that replaces the manifest whole or not at all, then its source snapshots are registered through one database transaction and one snapshot query.

A manifest is the record of one capture: every response, object, curriculum period and content hash it holds. A stored response is one file that holds the exact bytes of one source response. Its path combines a hash of the request with a hash of the body, and the same body always produces the same compressed bytes, so the same response always lands in the same file. A response already recorded for a request is never overwritten with different bytes.

A source snapshot is the stored position and hash of one captured source object. The manifest records each object's source id, group id, position in its response and content hash. The capture's snapshot writer registered the records for each set in one transaction and one query and refused a missing, extra or conflicting row. A retry after an interrupted publication adopted a stored response from the crash window only when the request and body matched exactly. Changed, corrupt, ambiguous or extra evidence that a completed manifest did not name failed loudly.

### Typed closure

Closure follows references that the official structures name. Course prerequisite and substitution structures yield course groups, and module rule trees yield course and module groups. The closure processes the pending groups in sorted breadth-first order, one frontier of groups at a time. Group iterators run concurrently under `KORI_CONCURRENCY` and yield in caller order. Each group is visited once, so a reference cycle terminates. A group response with no objects becomes an explicit unresolved identity rather than a silent omission.

The closure read references from each fetched response without replaying the whole store for each group. At the time of the 2026-2027 capture, the number of full object replay passes was fixed at four and did not grow with the closure group count.

### Resume

A resume verifies the retained manifest first and repairs the database source snapshots in bounded batches. It seeds the closure state from that verified manifest, fetches only exact ids that no captured object represents, and continues the pending typed frontier. A response already held is not downloaded again. A completed manifest is verified against its run row and reported as it stands. A completed capture refuses any change to its evidence.

Pause and stop act only at the durable boundaries that [Stage lifecycle](/docs/operations/stage-lifecycle.md#the-boundaries-of-a-run) describes: after a response set is stored and before the next source request, between stored responses during verification, and between a completed capture and normalization. A run that pauses or stops at one of those boundaries keeps its manifest and stored responses and is not marked failed.

## Verification and source-free replay

At the time of the 2026-2027 capture, verification ran four full object replay passes. The pass count did not grow with the number of closure groups. Each pass re-read stored responses and checked the body hash, body size, object positions and object hashes against the manifest. The completed-state pass checked the response directory for a missing, extra or unreferenced file.

At the time of the 2026-2027 run, a source-free verification re-read the stored evidence without a source client and returned an identical report. The manifest SHA-256, the digest of stored-response paths, sizes and modification times, and the ordered digest of database source-snapshot rows were preserved. No stored response was rewritten.

A source-free replay is a later step that verifies a retained manifest and normalizes it without constructing a source client. The full-catalogue manifest was replayed twice in this way.

## Measured capture and replay

### 2026-2027 capture

| Quantity | Value |
|---|---:|
| Capture date | 11 September 2026 |
| Capture elapsed time | 125.49 s |
| Curriculum periods | 1 |
| Stored responses | 6,071 |
| Course source snapshots | 17,020 |
| Module source snapshots | 3,724 |
| Unresolved course groups | 59 |
| Unresolved module groups | 0 |
| Full object replay passes | 4 |

The 2026-2027 capture completed in 125.49 seconds, stored 6,071 responses and recorded 17,020 course snapshots and 3,724 module snapshots. Its manifest also records one curriculum period. It holds 17,020 course object records and 3,724 module object records, and it names 59 unresolved course groups and no unresolved module group. That implementation used four verification passes, and the source-free verification returned an identical report with the same manifest digest, stored-response path, size and modification-time digest and ordered source-snapshot digest.

The 125.49 seconds covers the capture. No capture plus normalization time, timing of each capture step, repeated capture, warm or cold state or latency distribution was recorded.

The response count is a transport count. One response can be a period list, a page of references, an exact batch or a group. It is not a course count, and no throughput per course is derived from it.

### Full-catalogue capture

| Quantity | Value |
|---|---:|
| Capture date | 11 September 2026 |
| Elapsed capture time | No elapsed timer recorded |
| Curriculum periods | 21 (2006 to 2026) |
| Stored responses | 14,405 |
| Captured course objects | 24,932 |
| Captured module objects | 15,553 |
| Unresolved course groups | 88 |
| Unresolved module groups | 0 |

The full-catalogue manifest holds 14,405 stored responses, 24,932 course object records and 15,553 module object records across 21 curriculum periods, from 2006 to 2026. It names 88 unresolved course groups and no unresolved module group.

The manifest records a start and a finish timestamp for the capture, both on 11 September 2026, but no elapsed timer. Their difference is a timestamp span, which is a different quantity from the elapsed timer recorded for the 2026-2027 capture. The report therefore draws no duration from it and makes no speed comparison. The response count is a transport count for this capture too, and no throughput per course is derived from it.

### Two source-free replays

| Quantity | Value |
|---|---:|
| Captured course objects | 24,932 |
| Normalized course versions | 24,931 |
| Explicit null-code exclusions | 1 |
| Source-free replays | 2 |
| New versions | 0 |
| Changed versions | 0 |
| SQL summary | Unchanged |

The verified full manifest holds 24,932 captured course objects. The import reconciled them as 24,931 normalized course versions and one explicit null-code exclusion. The import contract requires that reconciliation, so a lost object or an extra version fails the run. A captured course object, a normalized course version and an unresolved course group are separate quantities, and the report keeps them apart.

Two source-free replays of the manifest reported zero new versions, zero changed versions and an unchanged SQL summary of normalized table counts. Database checks found no null or blank normalized course code and no normalized row for the excluded exact source id, and confirmed that the run-scoped source snapshots were retained.

The dates of the two replays are not recorded. The capture counts and the replay counts describe separate steps, and the record holds no elapsed time for either replay.

## Null-code exclusion

The exclusion applies only to an explicit null, as [Capture and normalization](/docs/backend/catalogue/capture-and-normalization.md) describes. A course version with `code: null` is left out of normalized and read rows. Its exclusion reports the exact source id, group id, response position and source hash as its source snapshot. The excluded source id in this run was `uta-opsu-vkoodi-53680`.

A missing code field or a blank code string is malformed and stops normalization. A coded version under the same canonical group is eligible. The canonical course is deleted only when no coded exact version remains, and the raw evidence and source snapshots are retained.

On a refresh, the reconciliation in [the normalization transaction](/docs/backend/catalogue/capture-and-normalization.md#the-normalization-transaction) deletes a stored normalized exact version and its cascaded normalized payload when that version carries an explicit null code. An exact source id that maps to a different canonical group fails the batch and rolls back the normalized changes.

## Corrections

An earlier revision left a stale normalized projection when a normalized course version later arrived with an explicit null code. The transition tests for that case failed against the earlier revision. The corrected reconciliation removes the stored version and its cascaded payload, and the corrected rule is the result that stands.

## What the evidence does not show

- The 125.49 seconds is one capture on a machine and source condition that the record does not describe. No second timed capture exists, so the record supports no variance, percentile, warm versus cold comparison or capacity figure.
- No capture plus normalization time, timing of each capture step, checkpoint size, concurrency setting, timeout or retry setting was recorded.
- No hardware specification, network condition, database configuration or summed source body size was recorded. The manifest holds each response's body size, and no total of them is given.
- The 2026-2027 capture's 6,071 responses, 17,020 course snapshots and 3,724 module snapshots belong to that capture of one curriculum period. The full manifest covers 21 periods from 2006 to 2026 and holds 14,405 responses, 24,932 course objects and 15,553 module objects. The two scopes are not summed or compared.
- The full-catalogue capture records start and finish timestamps but no elapsed timer. The report draws no duration from them, so no end-to-end full-catalogue timing is compared with the 2026-2027 capture, and no per-course network throughput is derived from either response count.
- The unresolved course groups are counts, 59 in the 2026-2027 capture and 88 in the full manifest, and the full manifest names no unresolved module group. The record does not explain why each group is empty.
- The two replays reuse one verified manifest. The record contains no third replay, no source-change refresh, no interrupted full-scale resume timing and no replay dates.

## The supported operation

At the time of these runs, a source-free replay verified a stored manifest and normalized it without a source client. The source-free replay is a historical method. The supported operation is live-source ingestion with a resumable capture. It starts a fresh capture or resumes a retained capture, then normalizes the completed capture in one transaction. It is not a source-free rebuild of a saved capture. [Ingestion](/docs/backend/catalogue/ingestion.md) describes the stage.

## Untested questions

- What share of the 125.49 seconds belongs to source requests, manifest publication, verification and the database source-snapshot writes? The run recorded no timing of each capture step.
- What would a second timed capture on the same machine and source measure? Only one timed capture exists.
- Would a second full-catalogue capture reproduce 14,405 responses, 24,932 course objects and 15,553 module objects? The evidence covers one full-catalogue capture.
