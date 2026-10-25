/** Typed same-origin client for the structural prerequisite graph report. */
import { postJson } from "./http";
import type {
  PrerequisiteGraphReport,
  PrerequisiteGraphRequest,
} from "./types";

/** Read the prerequisite graph report for one structural request. */
export function readPrerequisites(
  request: PrerequisiteGraphRequest,
  signal?: AbortSignal,
): Promise<PrerequisiteGraphReport> {
  return postJson("/api/prerequisites", request, signal);
}
