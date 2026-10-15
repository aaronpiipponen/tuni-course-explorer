/** Typed same-origin client for the official structure report. */
import { postJson } from "./http";
import type { StudyStructureReport } from "./types";

export function readStudyStructure(
  rootGroupId: string,
  signal?: AbortSignal,
): Promise<StudyStructureReport> {
  return postJson(
    "/api/study-structure",
    { root_group_id: rootGroupId },
    signal,
  );
}
