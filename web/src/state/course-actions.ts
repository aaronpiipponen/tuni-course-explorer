/** Named shared selected/completed state mutations used by every course card. */
import type { BrowserStore } from "./store";
import type { CourseId } from "./types";

/**
 * Add the requested courses that the latest saved selection does not hold and return how many
 * were added.
 *
 * The count is read from the update callback, so it reflects the stored envelope the write
 * applied to. A repeated request returns zero, and a failed write throws before any count is
 * returned.
 */
export function addCoursesToFreeChoice(
  store: BrowserStore,
  courseIds: readonly CourseId[],
): number {
  let added = 0;
  store.updateCurrent((state) => {
    const missing = [...new Set(courseIds)].filter(
      (id) => !state.selectedCourseIds.includes(id),
    );
    added = missing.length;
    return missing.length
      ? {
          ...state,
          selectedCourseIds: [...state.selectedCourseIds, ...missing],
        }
      : state;
  });
  return added;
}

/** Toggle completion for one course and select it when it becomes completed. */
export function toggleCompleted(store: BrowserStore, courseId: CourseId): void {
  store.updateCurrent((state) => {
    if (state.completedCourseIds.includes(courseId)) {
      return {
        ...state,
        completedCourseIds: state.completedCourseIds.filter(
          (id) => id !== courseId,
        ),
      };
    }
    return {
      ...state,
      selectedCourseIds: state.selectedCourseIds.includes(courseId)
        ? state.selectedCourseIds
        : [...state.selectedCourseIds, courseId],
      completedCourseIds: [...state.completedCourseIds, courseId],
    };
  });
}
