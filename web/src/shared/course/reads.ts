/** One dataset-bound cached course-summary read shared by every hydration consumer. */
import { readCachedReport } from "../../app/cachedRead";
import type { ReadCache } from "../../app/readCache";
import { readCourseSummaries } from "../../api/course-summaries";
import type { CourseSummariesReport } from "../../api/types";

/** Return the shared official summaries for the supplied identities in caller order and repeats. */
export function readCachedCourseSummaries(
  cache: ReadCache,
  identifiers: readonly string[],
  signal: AbortSignal,
): Promise<CourseSummariesReport> {
  const requested = [...identifiers];
  if (!requested.length)
    return Promise.resolve({
      results: [],
      dataset_identity: cache.getDatasetIdentity(),
    });
  return readCachedReport<CourseSummariesReport>(
    cache,
    JSON.stringify(["course-summaries", requested]),
    (requestSignal) => readCourseSummaries(requested, requestSignal),
    signal,
  );
}
