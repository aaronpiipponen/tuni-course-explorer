/** Typed same-origin client for the authoritative prerequisite graph report. */
import { postJson } from "./http";
import type { PrerequisiteGraphReport, PrerequisitesRequest } from "./types";

export function readPrerequisites(
  request: PrerequisitesRequest,
  signal?: AbortSignal,
): Promise<PrerequisiteGraphReport> {
  return postJson("/api/prerequisites", request, signal);
}
