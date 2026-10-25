/** Browser-owned prerequisite view options and graph-only report-issued marks. */
import type { BrowserStore } from "../../state/store";
import type { CourseId } from "../../state/types";

function update(
  store: BrowserStore,
  change: (
    state: ReturnType<BrowserStore["getSnapshot"]>["profiles"][string]["state"],
  ) => ReturnType<BrowserStore["getSnapshot"]>["profiles"][string]["state"],
): void {
  store.updateCurrent(change);
}
/** Store the prerequisite root course in the current profile. */
export const setPrerequisitesRoot = (
  store: BrowserStore,
  courseId: CourseId,
): void =>
  update(store, (state) => ({
    ...state,
    prerequisites: { ...state.prerequisites, rootCourseId: courseId },
  }));
/** Store the prerequisite root query in the current profile. */
export const setPrerequisitesQuery = (
  store: BrowserStore,
  query: string,
): void =>
  update(store, (state) => ({
    ...state,
    prerequisites: { ...state.prerequisites, courseQuery: query },
  }));
/** Store the prerequisite activity scope in the current profile. */
export const setPrerequisitesActiveOnly = (
  store: BrowserStore,
  activeOnly: boolean,
): void =>
  update(store, (state) => ({
    ...state,
    prerequisites: { ...state.prerequisites, activeOnly },
  }));
/** Store the prerequisite route basis in the current profile. */
export const setPrerequisitesBasis = (
  store: BrowserStore,
  basis: "completed" | "selected",
): void =>
  update(store, (state) => ({
    ...state,
    prerequisites: { ...state.prerequisites, basis },
  }));
/** Store whether recommended prerequisites are shown. */
export const setIncludeRecommended = (store: BrowserStore, on: boolean): void =>
  update(store, (state) => ({
    ...state,
    prerequisites: { ...state.prerequisites, includeRecommended: on },
  }));
/** Store whether inferred prerequisites are shown. */
export const setIncludeInferred = (store: BrowserStore, on: boolean): void =>
  update(store, (state) => ({
    ...state,
    prerequisites: { ...state.prerequisites, includeInferred: on },
  }));
/** Toggle one course's exclusion in the current profile. */
export const toggleExcludedCourse = (
  store: BrowserStore,
  courseId: CourseId,
): void =>
  update(store, (state) => ({
    ...state,
    prerequisites: {
      ...state.prerequisites,
      excludedCourseIds: state.prerequisites.excludedCourseIds.includes(
        courseId,
      )
        ? state.prerequisites.excludedCourseIds.filter((id) => id !== courseId)
        : [...state.prerequisites.excludedCourseIds, courseId],
    },
  }));
function toggleNode(
  store: BrowserStore,
  nodeKey: string,
  source: "completedNodeKeys" | "excludedNodeKeys",
  opposite: "completedNodeKeys" | "excludedNodeKeys",
): void {
  update(store, (state) => {
    const keys = state.prerequisites[source];
    // A drawn box is one saved key. Marking it clears the opposite mark for that same box.
    const adding = !keys.includes(nodeKey);
    return {
      ...state,
      prerequisites: {
        ...state.prerequisites,
        [source]: adding
          ? [...keys, nodeKey]
          : keys.filter((key) => key !== nodeKey),
        [opposite]: adding
          ? state.prerequisites[opposite].filter((key) => key !== nodeKey)
          : state.prerequisites[opposite],
      },
    };
  });
}
/** Toggle one drawn node's completion mark. */
export const toggleNodeCompleted = (
  store: BrowserStore,
  nodeKey: string,
): void => toggleNode(store, nodeKey, "completedNodeKeys", "excludedNodeKeys");
/** Toggle one drawn node's exclusion mark. */
export const toggleNodeExcluded = (
  store: BrowserStore,
  nodeKey: string,
): void => toggleNode(store, nodeKey, "excludedNodeKeys", "completedNodeKeys");
