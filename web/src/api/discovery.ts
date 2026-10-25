/** Typed same-origin clients for the discovery command reports. */
import { postJson } from "./http";
import type {
  DiscoveryRequest,
  NextCoursesReport,
  RecommendationsReport,
} from "./types";

/** Read next-course coverage for one discovery request. */
export function readNextCourses(
  request: DiscoveryRequest,
  signal?: AbortSignal,
): Promise<NextCoursesReport> {
  return postJson("/api/next-courses", request, signal);
}

/** Read similarity recommendations for one discovery request. */
export function readRecommendations(
  request: DiscoveryRequest,
  signal?: AbortSignal,
): Promise<RecommendationsReport> {
  return postJson("/api/recommendations", request, signal);
}
