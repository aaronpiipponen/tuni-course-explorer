/** Browser-store guarantees for profile isolation and operations. */
import { beforeEach, describe, expect, it } from "vitest";
import { createBrowserStore } from "./store";
import { BROWSER_STORAGE_KEY } from "./store";
import { initialProfileState } from "./defaults";
import { initialPrerequisitesState } from "../features/prerequisites/state";
import { setLanguage } from "../app/actions";

describe("browser profiles", () => {
  beforeEach(() => localStorage.clear());

  it("switching profiles preserves each live state across reload", () => {
    const store = createBrowserStore(localStorage);
    setLanguage(store, "fi");
    store.updateCurrent((state) => ({
      ...state,
      activeTab: "structure",
      selectedCourseIds: ["canonical-a"],
      completedCourseIds: ["canonical-a"],
      compare: { ...state.compare, slots: ["canonical-a", null] },
      prerequisites: {
        ...state.prerequisites,
        rootCourseId: "root-a",
        includeRecommended: true,
        basis: "selected",
        excludedCourseIds: ["canonical-a"],
        completedNodeKeys: ["module:marked"],
      },
      structure: {
        ...state.structure,
        rootGroupId: "root-a",
        choices: { option: ["choice-a"] },
        coursePlacements: { "canonical-a": "node-a" },
      },
      search: { ...state.search, query: "profile A" },
    }));
    store.saveAsProfile("Second");
    const secondId = store.getSnapshot().currentProfileId;
    setLanguage(store, "en");
    store.updateCurrent((state) => ({
      ...state,
      selectedCourseIds: ["canonical-b"],
      completedCourseIds: ["canonical-b"],
      structure: { ...state.structure, rootGroupId: "root-b" },
      discover: { ...state.discover, mode: "at_least_one" },
    }));
    const second = store.getSnapshot().profiles[secondId].state;
    expect(second.language).toBe("en");
    store.switchProfile("default");
    const first = store.getSnapshot().profiles.default.state;
    expect(first.language).toBe("fi");
    expect(first.activeTab).toBe("structure");
    expect(first.structure.rootGroupId).toBe("root-a");
    expect(first.compare.slots).toEqual(["canonical-a", null]);
    expect(first.search.query).toBe("profile A");
    expect(first.completedCourseIds).toEqual(first.selectedCourseIds);
    store.switchProfile(secondId);
    expect(store.getSnapshot().profiles[secondId].state).toEqual(second);
    const reloaded = createBrowserStore(localStorage).getSnapshot();
    expect(reloaded.currentProfileId).toBe(secondId);
    expect(reloaded.profiles.default.state).toEqual(first);
    expect(reloaded.profiles[secondId].state).toEqual(second);
    // The live prerequisite input slice carries across reload: storage writes back the persisted
    // fields only.
    expect(reloaded.profiles.default.state.prerequisites).toEqual({
      ...initialPrerequisitesState(),
      rootCourseId: "root-a",
      includeRecommended: true,
      basis: "selected",
      excludedCourseIds: ["canonical-a"],
      completedNodeKeys: ["module:marked"],
    });
    expect(Object.keys(reloaded.profiles.default.state.prerequisites)).toEqual(
      Object.keys(initialPrerequisitesState()),
    );
  });

  it("Save as copies independently and refuses a duplicate name", () => {
    const store = createBrowserStore(localStorage);
    store.updateCurrent((state) => ({
      ...state,
      search: { ...state.search, query: "source" },
      structure: { ...state.structure, choices: { option: ["one"] } },
    }));
    const source = structuredClone(store.getSnapshot().profiles.default.state);
    store.saveAsProfile("  Saved  ");
    const savedId = store.getSnapshot().currentProfileId;
    expect(store.getSnapshot().profiles[savedId].name).toBe("Saved");
    expect(store.getSnapshot().profiles[savedId].state).toEqual(source);
    store.switchProfile("default");
    store.updateCurrent((state) => ({
      ...state,
      search: { ...state.search, query: "changed" },
    }));
    expect(store.getSnapshot().profiles[savedId].state).toEqual(source);
    const stored = localStorage.getItem(BROWSER_STORAGE_KEY);
    expect(() => store.saveAsProfile("Saved")).toThrow();
    expect(localStorage.getItem(BROWSER_STORAGE_KEY)).toBe(stored);
    expect(store.getSnapshot().profiles[savedId].state).toEqual(source);
    expect(store.getSnapshot().currentProfileId).toBe("default");
  });

  it("deleting the current profile selects the first profile in order", () => {
    const store = createBrowserStore(localStorage);
    store.saveAsProfile("Other");
    const otherId = store.getSnapshot().currentProfileId;
    store.saveAsProfile("Third");
    const thirdId = store.getSnapshot().currentProfileId;
    store.deleteProfile(otherId);
    expect(store.getSnapshot().currentProfileId).toBe(thirdId);
    store.deleteProfile(thirdId);
    const after = store.getSnapshot();
    expect(after.currentProfileId).toBe("default");
    expect(Object.keys(after.profiles)).toEqual(["default"]);
    expect(createBrowserStore(localStorage).getSnapshot().profiles).toEqual(
      after.profiles,
    );
    const stored = localStorage.getItem(BROWSER_STORAGE_KEY);
    expect(() => store.deleteProfile("default")).toThrow();
    expect(localStorage.getItem(BROWSER_STORAGE_KEY)).toBe(stored);
  });

  it("renaming changes only the name and refuses a duplicate", () => {
    const store = createBrowserStore(localStorage);
    store.updateCurrent((state) => ({
      ...state,
      ...initialProfileState(),
      selectedCourseIds: ["one"],
      completedCourseIds: ["one"],
    }));
    store.saveAsProfile("Other");
    const otherId = store.getSnapshot().currentProfileId;
    store.switchProfile("default");
    const before = structuredClone(store.getSnapshot());
    store.renameProfile("default", "  Main  ");
    store.renameProfile(otherId, "Other renamed");
    const renamed = store.getSnapshot();
    expect(renamed.currentProfileId).toBe(before.currentProfileId);
    expect(renamed.profiles.default.name).toBe("Main");
    expect(renamed.profiles[otherId].name).toBe("Other renamed");
    expect(renamed.profiles.default.state).toEqual(
      before.profiles.default.state,
    );
    expect(renamed.profiles[otherId].state).toEqual(
      before.profiles[otherId].state,
    );
    const reloaded = createBrowserStore(localStorage).getSnapshot();
    expect(reloaded.currentProfileId).toBe("default");
    expect(reloaded.profiles).toEqual(renamed.profiles);
    const stored = localStorage.getItem(BROWSER_STORAGE_KEY);
    expect(() => store.renameProfile(otherId, "Main")).toThrow();
    expect(localStorage.getItem(BROWSER_STORAGE_KEY)).toBe(stored);
  });
});
