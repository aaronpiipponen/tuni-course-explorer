/** One typed client for transient hydration of canonical course summaries. */
import { postJson } from "./http";
import type { CourseSummariesReport } from "./types";

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
