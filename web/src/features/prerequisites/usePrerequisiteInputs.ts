/** One live-profile prerequisite input snapshot shared by both request owners. */
import { useProfileSelector } from "../../state/useProfileSelector";
import { useActiveTab } from "../../app/sessionTab";
import type { PrerequisitesRequest } from "../../api/types";

export function usePrerequisiteInputs(): {
  request: PrerequisitesRequest | null;
  key: string;
  active: boolean;
} {
  const { value: root } = useProfileSelector(
    (state) => state.prerequisites.rootCourseId,
  );
  const { value: completed } = useProfileSelector(
    (state) => state.completedCourseIds,
  );
  const { value: selected } = useProfileSelector(
    (state) => state.selectedCourseIds,
  );
  const { value: excludedCourses } = useProfileSelector(
    (state) => state.prerequisites.excludedCourseIds,
  );
  const { value: includeRecommended } = useProfileSelector(
    (state) => state.prerequisites.includeRecommended,
  );
  const { value: includeInferred } = useProfileSelector(
    (state) => state.prerequisites.includeInferred,
  );
  const { value: activeOnly } = useProfileSelector(
    (state) => state.prerequisites.activeOnly,
  );
  const { value: basis } = useProfileSelector(
    (state) => state.prerequisites.basis,
  );
  const { value: completedNodes } = useProfileSelector(
    (state) => state.prerequisites.completedNodeKeys,
  );
  const { value: excludedNodes } = useProfileSelector(
    (state) => state.prerequisites.excludedNodeKeys,
  );
  const activeTab = useActiveTab();
  const request: PrerequisitesRequest | null = root
    ? {
        target_code: root,
        completed_codes: completed,
        selected_codes: selected,
        excluded_codes: excludedCourses,
        include_recommended: includeRecommended,
        include_inferred: includeInferred,
        active_only: activeOnly,
        basis,
        completed_node_keys: completedNodes,
        excluded_node_keys: excludedNodes,
      }
    : null;
  return {
    request,
    key: JSON.stringify(request),
    active: activeTab === "prerequisites",
  };
}
