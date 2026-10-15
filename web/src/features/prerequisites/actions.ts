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
export const setPrerequisitesRoot = (
  store: BrowserStore,
  courseId: CourseId,
): void =>
  update(store, (state) => ({
    ...state,
    prerequisites: { ...state.prerequisites, rootCourseId: courseId },
  }));
export const setPrerequisitesQuery = (
  store: BrowserStore,
  query: string,
): void =>
  update(store, (state) => ({
    ...state,
    prerequisites: { ...state.prerequisites, courseQuery: query },
  }));
export const setPrerequisitesActiveOnly = (
  store: BrowserStore,
  activeOnly: boolean,
): void =>
  update(store, (state) => ({
    ...state,
    prerequisites: { ...state.prerequisites, activeOnly },
  }));
export const setPrerequisitesBasis = (
  store: BrowserStore,
  basis: "completed" | "selected",
): void =>
  update(store, (state) => ({
    ...state,
    prerequisites: { ...state.prerequisites, basis },
  }));
export const setIncludeRecommended = (store: BrowserStore, on: boolean): void =>
  update(store, (state) => ({
    ...state,
    prerequisites: { ...state.prerequisites, includeRecommended: on },
  }));
export const setIncludeInferred = (store: BrowserStore, on: boolean): void =>
  update(store, (state) => ({
    ...state,
    prerequisites: { ...state.prerequisites, includeInferred: on },
  }));
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
  actionKey: string,
  source: "completedNodeKeys" | "excludedNodeKeys",
  opposite: "completedNodeKeys" | "excludedNodeKeys",
): void {
  update(store, (state) => {
    const keys = state.prerequisites[source];
    const adding = !keys.includes(actionKey);
    return {
      ...state,
      prerequisites: {
        ...state.prerequisites,
        [source]: adding
          ? [...keys, actionKey]
          : keys.filter((key) => key !== actionKey),
        [opposite]: adding
          ? state.prerequisites[opposite].filter((key) => key !== actionKey)
          : state.prerequisites[opposite],
      },
    };
  });
}
export const toggleNodeCompleted = (
  store: BrowserStore,
  actionKey: string,
): void =>
  toggleNode(store, actionKey, "completedNodeKeys", "excludedNodeKeys");
export const toggleNodeExcluded = (
  store: BrowserStore,
  actionKey: string,
): void =>
  toggleNode(store, actionKey, "excludedNodeKeys", "completedNodeKeys");
