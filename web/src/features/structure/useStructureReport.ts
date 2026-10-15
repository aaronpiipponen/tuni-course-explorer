/** Root-keyed official report request with stale-root results withheld. */
import { useCallback } from "react";
import { readStudyStructure } from "../../api/study-structure";
import type { StudyStructureReport } from "../../api/types";
import { useLookup } from "../../shared/useLookup";

export function useStructureReport(rootGroupId: string | null) {
  const run = useCallback(
    (signal: AbortSignal) => readStudyStructure(rootGroupId!, signal),
    [rootGroupId],
  );
  return useLookup<StudyStructureReport>(
    rootGroupId ?? "",
    rootGroupId !== null,
    run,
  );
}
