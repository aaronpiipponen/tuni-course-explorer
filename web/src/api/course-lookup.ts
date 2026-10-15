/** Typed same-origin client for official course substring lookup. */
import { postJson } from "./http";
import type { CourseLookupReport, CourseLookupRequest } from "./types";

export function lookupCourses(
  request: CourseLookupRequest,
  signal?: AbortSignal,
): Promise<CourseLookupReport> {
  return postJson("/api/course-lookup", request, signal);
}
