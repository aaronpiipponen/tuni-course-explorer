/** Typed same-origin client for backend-owned course comparison analysis. */
import { postJson } from "./http";
import type { ComparisonRequest, CourseComparisonReport } from "./types";

/** Compare two canonical courses through the backend analysis service. */
export function compareCourses(
  request: ComparisonRequest,
  signal?: AbortSignal,
): Promise<CourseComparisonReport> {
  return postJson("/api/comparison", request, signal);
}
