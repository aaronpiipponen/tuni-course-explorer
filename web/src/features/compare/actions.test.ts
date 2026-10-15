/** Comparison actions for slot uniqueness and replacement behavior. */
import { beforeEach, describe, expect, it } from "vitest";
import { createBrowserStore } from "../../state/store";
import {
  addToComparison,
  removeComparisonSlot,
  replaceComparisonSlot,
} from "./actions";

describe("comparison actions", () => {
  beforeEach(() => localStorage.clear());

  it("fills and replaces comparison slots without duplicate canonical courses", () => {
    const store = createBrowserStore(localStorage);
    expect(addToComparison(store, "course-a")).toBe("added");
    expect(addToComparison(store, "course-b")).toBe("added");
    const before = store.getSnapshot();
    expect(addToComparison(store, "course-a")).toBe("already-present");
    expect(store.getSnapshot()).toBe(before);
    expect(addToComparison(store, "course-c")).toBe("replace-required");
    expect(store.getSnapshot()).toBe(before);
    replaceComparisonSlot(store, "course-c", 0);
    expect(store.getSnapshot().profiles.default.state.compare.slots).toEqual([
      "course-c",
      "course-b",
    ]);
    replaceComparisonSlot(store, "course-b", 0);
    expect(store.getSnapshot().profiles.default.state.compare.slots).toEqual([
      "course-b",
      null,
    ]);
  });

  it("removes only the chosen comparison slot without changing study state", () => {
    const store = createBrowserStore(localStorage);
    addToComparison(store, "course-a");
    addToComparison(store, "course-b");
    store.updateCurrent((state) => ({
      ...state,
      selectedCourseIds: ["course-study"],
      completedCourseIds: ["course-study"],
    }));
    removeComparisonSlot(store, 0);
    const reloaded =
      createBrowserStore(localStorage).getSnapshot().profiles.default.state;
    expect(reloaded.compare.slots).toEqual([null, "course-b"]);
    expect(reloaded.selectedCourseIds).toEqual(["course-study"]);
    expect(reloaded.completedCourseIds).toEqual(["course-study"]);
  });
});
