/** One typed client for transient hydration of canonical course summaries. */
import { postJson } from "./http";
import type { CourseSummariesReport } from "./types";

/** Read official course summaries for the supplied identifiers. */
export function readCourseSummaries(
  identifiers: readonly string[],
  signal?: AbortSignal,
): Promise<CourseSummariesReport> {
  return postJson<CourseSummariesReport>(
    "/api/course-summaries",
    { identifiers },
    signal,
  );
}
