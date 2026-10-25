/** Browser-store persistence for canonical selected and completed ownership. */
import { beforeEach, describe, expect, it } from "vitest";
import { createBrowserStore } from "./store";
import { addCoursesToFreeChoice, toggleCompleted } from "./course-actions";
import { BROWSER_STORAGE_KEY } from "./store";

describe("course actions", () => {
  beforeEach(() => localStorage.clear());

  it("persists canonical completion as a subset of current-profile selections", () => {
    const store = createBrowserStore(localStorage);
    toggleCompleted(store, "canonical-course-id");
    let current =
      createBrowserStore(localStorage).getSnapshot().profiles.default.state;
    expect(current.selectedCourseIds).toEqual(["canonical-course-id"]);
    expect(current.completedCourseIds).toEqual(["canonical-course-id"]);
    expect(
      createBrowserStore(localStorage).getSnapshot().currentProfileId,
    ).toBe("default");

    toggleCompleted(createBrowserStore(localStorage), "canonical-course-id");
    current = JSON.parse(localStorage.getItem(BROWSER_STORAGE_KEY)!).profiles
      .default.state;
    expect(current.selectedCourseIds).toEqual(["canonical-course-id"]);
    expect(current.completedCourseIds).toEqual([]);
  });

  it("adds missing module courses to Unplaced studies once and preserves completion", () => {
    const store = createBrowserStore(localStorage);
    toggleCompleted(store, "already-completed");
    expect(
      addCoursesToFreeChoice(store, [
        "already-completed",
        "module-course",
        "module-course",
      ]),
    ).toBe(1);
    // A repeated request adds nothing and reports zero.
    expect(
      addCoursesToFreeChoice(store, ["already-completed", "module-course"]),
    ).toBe(0);
    // Another store selects an identity before this store asks for it.
    const otherTab = createBrowserStore(localStorage);
    otherTab.updateCurrent((state) => ({
      ...state,
      selectedCourseIds: [...state.selectedCourseIds, "other-tab-course"],
    }));
    expect(
      addCoursesToFreeChoice(store, ["other-tab-course", "module-course-two"]),
    ).toBe(1);
    const state =
      createBrowserStore(localStorage).getSnapshot().profiles.default.state;
    expect(state.selectedCourseIds).toEqual([
      "already-completed",
      "module-course",
      "other-tab-course",
      "module-course-two",
    ]);
    expect(state.completedCourseIds).toEqual(["already-completed"]);
  });
});
