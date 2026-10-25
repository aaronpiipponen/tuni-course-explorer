/** Shared comparison-slot mutations over canonical browser course identities. */
import type { BrowserStore } from "../../state/store";
import type { CourseId } from "../../state/types";

/** Add one course to the first available comparison slot. */
export function addToComparison(
  store: BrowserStore,
  courseId: CourseId,
): "added" | "already-present" | "replace-required" {
  let result: "added" | "already-present" | "replace-required" = "added";
  store.updateCurrent((state) => {
    if (state.compare.slots.includes(courseId)) {
      result = "already-present";
      return state;
    }
    const empty = state.compare.slots.indexOf(null);
    if (empty === -1) {
      result = "replace-required";
      return state;
    }
    const slots: [CourseId | null, CourseId | null] = [...state.compare.slots];
    slots[empty] = courseId;
    return { ...state, compare: { ...state.compare, slots } };
  });
  return result;
}

/** Replace one comparison slot and clear a duplicate in the other slot. */
export function replaceComparisonSlot(
  store: BrowserStore,
  courseId: CourseId,
  slot: 0 | 1,
): void {
  store.updateCurrent((state) => {
    const slots: [CourseId | null, CourseId | null] = [...state.compare.slots];
    slots[slot] = courseId;
    if (slots[1 - slot] === courseId) slots[1 - slot] = null;
    return { ...state, compare: { ...state.compare, slots } };
  });
}

/** Remove the course from one comparison slot. */
export function removeComparisonSlot(store: BrowserStore, slot: 0 | 1): void {
  store.updateCurrent((state) => {
    const slots: [CourseId | null, CourseId | null] = [...state.compare.slots];
    slots[slot] = null;
    return { ...state, compare: { ...state.compare, slots } };
  });
}

/** Store the comparison picker query. */
export function setComparePickerQuery(
  store: BrowserStore,
  query: string,
): void {
  store.updateCurrent((state) => ({
    ...state,
    compare: { ...state.compare, pickerQuery: query },
  }));
}

/** Store the comparison picker activity filter. */
export function setComparePickerActiveOnly(
  store: BrowserStore,
  activeOnly: boolean,
): void {
  store.updateCurrent((state) => ({
    ...state,
    compare: { ...state.compare, pickerActiveOnly: activeOnly },
  }));
}
