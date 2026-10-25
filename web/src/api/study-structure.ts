/** Typed same-origin client for the batched official structure report. */
import { postJson } from "./http";
import type { StudyStructuresReport } from "./types";

/** Read study structures for the requested roots and module versions. */
export function readStudyStructures(
  rootGroupIds: readonly string[],
  moduleVersions: Readonly<Record<string, string>>,
  allowUnavailable: boolean,
  signal?: AbortSignal,
): Promise<StudyStructuresReport> {
  return postJson<StudyStructuresReport>(
    "/api/study-structure",
    {
      root_group_ids: rootGroupIds,
      module_versions: moduleVersions,
      allow_unavailable: allowUnavailable,
    },
    signal,
  );
}
