/** Typed same-origin clients for the discovery command reports. */
import { postJson } from "./http";
import type {
  DiscoveryRequest,
  NextCoursesReport,
  RecommendationsReport,
} from "./types";

export function readNextCourses(
  request: DiscoveryRequest,
  signal?: AbortSignal,
): Promise<NextCoursesReport> {
  return postJson("/api/next-courses", request, signal);
}

export function readRecommendations(
  request: DiscoveryRequest,
  signal?: AbortSignal,
): Promise<RecommendationsReport> {
  return postJson("/api/recommendations", request, signal);
}
