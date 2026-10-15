/** Named shared selected/completed state mutations used by every course card. */
import type { BrowserStore } from "./store";
import type { CourseId } from "./types";

export function addCoursesToFreeChoice(
  store: BrowserStore,
  courseIds: readonly CourseId[],
): void {
  store.updateCurrent((state) => {
    const missing = [...new Set(courseIds)].filter(
      (id) => !state.selectedCourseIds.includes(id),
    );
    return missing.length
      ? {
          ...state,
          selectedCourseIds: [...state.selectedCourseIds, ...missing],
        }
      : state;
  });
}

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
