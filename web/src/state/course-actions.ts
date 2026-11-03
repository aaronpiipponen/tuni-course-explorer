/** Named shared selected/completed state mutations used by every course card. */
import type { BrowserStore } from "./store";
import type { CourseId, ProfileState } from "./types";

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

/** Return one profile state with a course selected and loose under Unplaced studies. */
function withCourseLoose(
  state: ProfileState,
  courseId: CourseId,
): ProfileState {
  const courseHolders = { ...state.structure.courseHolders };
  delete courseHolders[courseId];
  return {
    ...state,
    selectedCourseIds: state.selectedCourseIds.includes(courseId)
      ? state.selectedCourseIds
      : [...state.selectedCourseIds, courseId],
    structure: {
      ...state.structure,
      coursePlacements: {
        ...state.structure.coursePlacements,
        [courseId]: null,
      },
      placedCourseIds: state.structure.placedCourseIds.filter(
        (id) => id !== courseId,
      ),
      courseHolders,
    },
  };
}

/** Put one course in Unplaced studies as a loose selected course, keeping its completion. */
export function placeCourseInUnplaced(
  store: BrowserStore,
  courseId: CourseId,
): void {
  store.updateCurrent((state) => withCourseLoose(state, courseId));
}

/** Remove one course from the selection and from the structure, keeping completion if asked. */
export function removeCourseFromSelection(
  store: BrowserStore,
  courseId: CourseId,
  removeCompletion: boolean,
): void {
  store.updateCurrent((state) => {
    const courseHolders = { ...state.structure.courseHolders };
    delete courseHolders[courseId];
    return {
      ...state,
      selectedCourseIds: state.selectedCourseIds.filter(
        (id) => id !== courseId,
      ),
      completedCourseIds: removeCompletion
        ? state.completedCourseIds.filter((id) => id !== courseId)
        : state.completedCourseIds,
      structure: {
        ...state.structure,
        coursePlacements: {
          ...state.structure.coursePlacements,
          [courseId]: null,
        },
        placedCourseIds: state.structure.placedCourseIds.filter(
          (id) => id !== courseId,
        ),
        courseHolders,
      },
    };
  });
}
