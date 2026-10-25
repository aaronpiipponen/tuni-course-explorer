/** One live-profile prerequisite input snapshot shared by both request owners. */
import { useRef } from "react";
import { useProfileSelector } from "../../state/useProfileSelector";
import { useActiveTab } from "../../app/sessionTab";
import { useWebFeatures } from "../../app/useWebFeatures";
import { useCourseSummaries } from "../../shared/course/useCourseSummaries";
import type {
  PrerequisiteGraphRequest,
  PrerequisitesRequest,
} from "../../api/types";

/** Return the live prerequisite input snapshot of the current profile. */
export function usePrerequisiteInputs(): {
  request: PrerequisitesRequest | null;
  key: string;
  active: boolean;
  graphRequest: PrerequisiteGraphRequest | null;
  graphKey: string | null;
  graphInputError: Error | null;
  graphInputsPending: boolean;
} {
  const { inference_enabled } = useWebFeatures();
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
        include_inferred: includeInferred && inference_enabled,
        active_only: activeOnly,
        basis,
        completed_node_keys: completedNodes,
        excluded_node_keys: excludedNodes,
      }
    : null;
  const effectiveInferred = includeInferred && inference_enabled;
  const selectedIds = [...new Set(selected)].sort();
  // The Active only setting needs each selected course's activity flag, including courses the
  // graph does not draw.
  const summaries = useCourseSummaries(activeOnly && root ? selectedIds : []);
  // A pending classification holds the last resolved request and key, so it starts no read and
  // leaves an identical in-flight read alone.
  const retained = useRef<{
    request: PrerequisiteGraphRequest;
    key: string;
  } | null>(null);
  let graphRequest: PrerequisiteGraphRequest | null = null;
  let graphKey: string | null = null;
  let graphInputError: Error | null = null;
  let graphInputsPending = false;
  if (root) {
    if (!activeOnly) {
      graphRequest = {
        target_code: root,
        selected_codes: [],
        completed_codes: [],
        include_recommended: includeRecommended,
        include_inferred: effectiveInferred,
        active_only: activeOnly,
      };
    } else if (summaries.error) {
      graphInputError = summaries.error;
    } else if (summaries.loading) {
      graphInputsPending = true;
      const previous = retained.current;
      if (previous && previous.request.target_code === root) {
        graphRequest = previous.request;
        graphKey = previous.key;
      }
    } else {
      const byGroupId = new Map(
        summaries.courses.map((course) => [course.group_id, course]),
      );
      const missing = selectedIds.filter((id) => !byGroupId.has(id));
      if (missing.length) {
        graphInputError = new Error("Invalid request");
      } else {
        const completedSet = new Set(completed);
        const inactive = selectedIds.filter(
          (id) => !byGroupId.get(id)!.is_active,
        );
        graphRequest = {
          target_code: root,
          selected_codes: inactive,
          completed_codes: inactive.filter((id) => completedSet.has(id)),
          include_recommended: includeRecommended,
          include_inferred: effectiveInferred,
          active_only: activeOnly,
        };
      }
    }
    if (graphRequest && graphKey === null) {
      const retainedInactive = [
        ...new Set([
          ...graphRequest.selected_codes,
          ...graphRequest.completed_codes,
        ]),
      ].sort();
      graphKey = JSON.stringify([
        "prerequisites",
        root,
        includeRecommended,
        effectiveInferred,
        activeOnly,
        retainedInactive,
      ]);
      retained.current = { request: graphRequest, key: graphKey };
    }
  }
  return {
    request,
    key: JSON.stringify(request),
    active: activeTab === "prerequisites",
    graphRequest,
    graphKey,
    graphInputError,
    graphInputsPending,
  };
}
