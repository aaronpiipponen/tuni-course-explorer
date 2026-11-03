# Curriculum capture and replay

Five completed 2026-2027 full-capture manifests and two full-catalogue manifests measured what a capture stores and whether one response set normalizes without the source.

**Evidence status:** Observational. **Run dates:** 10 and 11 September 2026.

## The question

The experiments asked what one complete capture of the public curriculum source produces in responses, stored objects and elapsed time. It also asked whether the stored evidence can be verified and normalized again without reading the source. A third question was whether a full-catalogue manifest normalizes every captured course object exactly once, and how an explicit null course code is handled without losing the other versions of the same canonical course.

The 2026-2027 scope covers one curriculum period. The full-catalogue scope covers 21 periods from 2006 to 2026. The record holds five completed 2026-2027 full-capture manifests and two completed full-catalogue manifests. The two full-catalogue manifests hold the same response set, so the report treats that set as one analysed response set and counts the two source-free replays as normalization replays. The 2026-2027 counts describe the externally timed run. The replay is a separate step from the capture. The two scopes are not added together, and the report draws no speed comparison between them.

## Capture and checkpoint method

A [capture](/docs/backend/catalogue/ingestion.md) is one run that downloads course and module data from the public curriculum source and stores it unchanged. A full capture reads every curriculum period and the complete reference closure, with no course-version limit. The captured source is the anonymous public JSON interface. The capture reads the curriculum periods first, then the course and module version references for each period. Reference queries enumerate partitions and pages to a proven total rather than accepting a truncated set. Exact versions that no captured object represents are fetched in bounded batches.

### Checkpoints and source snapshots

Responses are written in bounded sets of `CAPTURE_CHECKPOINT_RESPONSE_COUNT` responses. The key is separate from the source request batch `KORI_BATCH_SIZE`. Each set is published through one validated manifest update that replaces the manifest whole or not at all, then its source snapshots are registered through one database transaction and one snapshot query.

A [manifest](/docs/reference/glossary.md#capture-and-data-preparation) is the record of one capture: every response, object, curriculum period and content hash it holds. A [stored response](/docs/reference/glossary.md#capture-and-data-preparation) is one file that holds the exact bytes of one source response. Its path combines a hash of the request with a hash of the body, and the same body always produces the same compressed bytes, so the same response always lands in the same file. A response already recorded for a request is never overwritten with different bytes.

A [source snapshot](/docs/reference/glossary.md#capture-and-data-preparation) is the stored position and hash of one captured source object. The manifest records each object's source id, group id, position in its response and content hash. The snapshot writer registered the records for each set in one transaction and one query and refused a missing, extra or conflicting row. A retry after an interrupted publication adopted a stored response from the crash window only when the request and body matched exactly. Changed, corrupt, ambiguous or extra evidence that a completed manifest did not name failed loudly.

### Typed closure

Closure follows references that the official structures name. Course prerequisite and substitution structures yield course groups, and module rule trees yield course and module groups. The closure processes the pending groups in sorted breadth-first order, one frontier of groups at a time. Group iterators run concurrently under `KORI_CONCURRENCY` and yield in caller order. Each group is visited once, so a reference cycle terminates. A group response with no objects becomes an explicit unresolved identity rather than a silent omission. The closure read references from each fetched response without replaying the whole store for each group.

### Resume

A resume verifies the retained manifest first and repairs the database source snapshots in bounded batches. It seeds the closure state from that verified manifest, fetches only exact ids that no captured object represents, and continues the pending typed frontier. A response already held is not downloaded again. A completed manifest is verified against its run row and reported as it stands. A completed capture refuses any change to its evidence.

Pause and stop act only at the durable boundaries that [Stage lifecycle](/docs/operations/stage-lifecycle.md#the-boundaries-of-a-run) describes: after a response set is stored and before the next source request, between stored responses during verification, and between a completed capture and normalization. A run that pauses or stops at one of those boundaries keeps its manifest and stored responses and is not marked failed.

The captures used this method.

## Verification and source-free replay

Verification ran four full object replay passes, and the pass count did not grow with the number of closure groups. Each pass re-read stored responses and checked the body hash, body size, object positions and object hashes against the manifest. The completed-state pass checked the response directory for a missing, extra or unreferenced file.

A source-free verification re-read the stored evidence without a source client and returned an identical report. The manifest SHA-256, the digest of stored-response paths, sizes and modification times, and the ordered digest of database source-snapshot rows were preserved. No stored response was rewritten.

A source-free replay verified a retained manifest and normalized it without constructing a source client. One full-catalogue manifest was replayed twice in this way. The two full-catalogue manifests hold the same response set, so the two replays normalize one response set twice and do not form two independent normalization cohorts.

![The externally timed 2026-2027 capture of one curriculum period writes stored responses and source snapshots into a manifest, which a source-free verification re-reads and checks against an identical report. Two full-catalogue captures write two manifests with one shared response set, and two source-free replays normalize that set without a source client. The two scopes are separate and their counts do not add.](/docs/diagrams/curriculum-capture-replay.svg)

## Measured capture and replay

In every capture the response count is a transport count. One response can be a period list, a page of references, an exact batch or a group. It is not a course count, and no throughput per course is derived from it.

### Analysed 2026-2027 run

| Quantity | Value |
|---|---:|
| Capture date | 11 September 2026 |
| External elapsed timer | 125.49 s |
| Manifest start-to-finish span | 100.85 s |
| Curriculum periods | 1 |
| Stored responses | 6,071 |
| Course source snapshots | 17,020 |
| Module source snapshots | 3,724 |
| Unresolved course groups | 59 |
| Unresolved module groups | 0 |

The record holds five completed 2026-2027 full-capture manifests. Each records 6,071 responses, one curriculum period and 59 unresolved course groups, and each records no unresolved module group. The externally timed run is one of the five, and its manifest span is 100.85 seconds. The other four spans are 96.63, 96.65, 98.67 and 1942.85 seconds. The record does not state that the five runs shared a machine, source condition or measurement boundary, so the spans are not a controlled timing replicate.

### Full-catalogue captures

| Quantity | Value |
|---|---:|
| Capture dates | 11 September 2026 |
| Completed manifests | 2 |
| Manifest start-to-finish spans | 402.56 s and 384.59 s |
| External elapsed timer | None recorded |
| Curriculum periods | 21 (2006 to 2026) |
| Stored responses | 14,405 per manifest |
| Captured course objects | 24,932 per manifest |
| Captured module objects | 15,553 per manifest |
| Unresolved course groups | 88 per manifest |
| Unresolved module groups | 0 per manifest |

Each manifest records a different capture identity and different start and finish times, and the response files are separate in each capture. The second manifest is therefore a second capture, not a replay or a copy of the first. The identical response set supports reproducibility between two captures on the same day. It does not establish an independent repeat under comparable measurement conditions, because the record does not state the machine, source condition or measurement boundary of either run.

### Two source-free replays

| Quantity | Value |
|---|---:|
| Manifest replayed | One full-catalogue manifest |
| Captured course objects | 24,932 |
| Normalized course versions | 24,931 |
| Explicit null-code exclusions | 1 |
| Source-free replays | 2 |
| New versions | 0 |
| Changed versions | 0 |
| SQL summary | Unchanged |

The import contract requires the captured course objects to reconcile as normalized course versions plus explicit null-code exclusions, so a lost object or an extra version fails the run. A captured course object, a normalized course version and an unresolved course group are separate quantities, and the report keeps them apart.

Database checks found no null or blank normalized course code and no normalized row for the excluded exact source id, and confirmed that the run-scoped source snapshots were retained.

## Null-code exclusion

The exclusion applies only to an explicit null, as [Capture and normalization](/docs/backend/catalogue/capture-and-normalization.md) describes. A course version with `code: null` is left out of normalized and read rows. Its exclusion carries the exact source id, group id, response position and source hash as its source snapshot. The excluded source id in this run was `uta-opsu-vkoodi-53680`.

A missing code field or a blank code string is malformed and stops normalization. A coded version under the same canonical group is eligible. The canonical course is deleted only when no coded exact version remains, and the raw evidence and source snapshots are retained.

On a refresh, the reconciliation in [the normalization transaction](/docs/backend/catalogue/capture-and-normalization.md#the-normalization-transaction) deletes a stored normalized exact version and its cascaded normalized payload when that version carries an explicit null code. An exact source id that maps to a different canonical group fails the batch and rolls back the normalized changes.

## What the evidence does not show

- The 125.49 seconds is one external timer, and the record describes neither the machine nor the source condition. The five 2026-2027 full-capture manifests and the two full-catalogue manifests record start and finish timestamps, but the record does not state that any runs shared a machine, source condition or measurement boundary. A manifest span measures the interval between its start and finish and can include a pause or resume. The spans support no variance, percentile, warm versus cold comparison or capacity figure. The record holds no capture plus normalization time and no timing of each capture step. It also records no checkpoint size, concurrency, timeout or retry setting.
- The 125.49-second external timer and the 2026-2027 manifest's 100.85-second start-to-finish span are different boundaries, and the evidence does not reconcile them. The two full-catalogue manifests span 402.56 and 384.59 seconds start to finish and have no external timer. The spans are not interchangeable with the external timer.
- The record does not explain why any of the 59 unresolved course groups in each 2026-2027 full-capture manifest or the 88 in each full-catalogue manifest is empty.
- The two replays reuse one verified manifest. The record holds no replay date and no elapsed replay time, and the replays provide no second response cohort.

## The supported operation

The measured replay normalized a retained manifest without a source client. The product operation is ingestion from the live public curriculum source with a resumable capture. It starts a fresh capture or resumes a retained capture, then normalizes the completed capture in one transaction. [Ingestion](/docs/backend/catalogue/ingestion.md) describes the stage.

## Untested questions

Each question below is untested.

- What share of the 125.49 seconds belongs to source requests, manifest publication, verification and the database source-snapshot writes?
- What would an independent 2026-2027 full capture measure under the same external timer, machine and source condition? The record holds five completed full-capture manifests but one external timer, and it does not state that the runs shared conditions.
- Would a full-catalogue capture on another day reproduce the same 14,405-response set? The two saved full-catalogue captures ran on one day, and the record does not state the source condition.
- Do the 100.85, 402.56 and 384.59-second manifest spans cover the same steps as the 125.49-second external timer? The record does not reconcile them.
