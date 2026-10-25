/** Typed same-origin client for the unified-search report. */
import { postJson } from "./http";
import type { SearchRequest, UnifiedSearchReport } from "./types";

/** Search courses through the configured backend methods. */
export function searchCourses(
  request: SearchRequest,
  signal?: AbortSignal,
): Promise<UnifiedSearchReport> {
  return postJson("/api/search", request, signal);
}
