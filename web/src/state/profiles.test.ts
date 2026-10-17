/** Browser-store guarantees for profile isolation and operations. */
import { beforeEach, describe, expect, it } from "vitest";
import {
  BROWSER_STORAGE_KEY,
  createBrowserStore,
  parseBrowserImport,
} from "./store";
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
        programmeGroupIds: ["root-a", "root-b"],
        choices: { "p:root-a/2": ["choice-a"] },
        coursePlacements: { "canonical-a": "p:root-a" },
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
      structure: { ...state.structure, programmeGroupIds: ["root-b"] },
      discover: { ...state.discover, mode: "at_least_one" },
    }));
    const second = store.getSnapshot().profiles[secondId].state;
    expect(second.language).toBe("en");
    store.switchProfile("default");
    const first = store.getSnapshot().profiles.default.state;
    expect(first.language).toBe("fi");
    expect(first.structure.programmeGroupIds).toEqual(["root-a", "root-b"]);
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

  it("applies a stale tab's mutation to the latest saved profile envelope", () => {
    const first = createBrowserStore(localStorage);
    const second = createBrowserStore(localStorage);
    first.saveAsProfile("Second");
    const secondId = first.getSnapshot().currentProfileId;
    first.updateCurrent((state) => ({
      ...state,
      selectedCourseIds: ["canonical-b"],
      completedCourseIds: ["canonical-b"],
    }));
    first.deleteProfile("default");
    second.updateCurrent((state) => ({ ...state, language: "fi" }));
    const stored = JSON.parse(localStorage.getItem(BROWSER_STORAGE_KEY)!);
    expect(stored.currentProfileId).toBe(secondId);
    expect(stored.profiles.default).toBeUndefined();
    expect(Object.keys(stored.profiles)).toEqual([secondId]);
    expect(stored.profiles[secondId].state.selectedCourseIds).toEqual([
      "canonical-b",
    ]);
    expect(stored.profiles[secondId].state.completedCourseIds).toEqual([
      "canonical-b",
    ]);
    expect(stored.profiles[secondId].state.language).toBe("fi");
    expect(second.getSnapshot().currentProfileId).toBe(secondId);
    expect(second.getSnapshot().profiles.default).toBeUndefined();
  });

  it("imports an exported profile as an independent current profile and refuses its duplicate name", () => {
    const store = createBrowserStore(localStorage);
    store.updateCurrent((state) => ({
      ...state,
      language: "fi",
      selectedCourseIds: ["canonical-a"],
      completedCourseIds: ["canonical-a"],
      search: { ...state.search, query: "exported query" },
      structure: {
        ...state.structure,
        programmeGroupIds: ["root-a", "root-b"],
        choices: { "p:root-b/2": ["choice-a"] },
        coursePlacements: { "canonical-a": "p:root-b" },
      },
    }));
    store.saveAsProfile("Exported");
    const exportedId = store.getSnapshot().currentProfileId;
    const exported = store.getSnapshot().profiles[exportedId];
    const parsed = parseBrowserImport(
      JSON.stringify(store.exportProfile(exportedId)),
    );
    if (parsed.type !== "tuni-course-explorer/profile/2")
      throw new Error("Expected a profile file");
    store.resetSavedData();
    store.importProfile(parsed.profile);
    const importedId = store.getSnapshot().currentProfileId;
    expect(importedId).not.toBe(exportedId);
    expect(store.getSnapshot().profiles[importedId]).toEqual(exported);
    expect(
      store.getSnapshot().profiles[importedId].state.structure
        .programmeGroupIds,
    ).toEqual(["root-a", "root-b"]);
    store.updateCurrent((state) => ({
      ...state,
      selectedCourseIds: ["canonical-c"],
      completedCourseIds: [],
    }));
    expect(parsed.profile.state.selectedCourseIds).toEqual(["canonical-a"]);
    expect(
      store.getSnapshot().profiles[importedId].state.selectedCourseIds,
    ).toEqual(["canonical-c"]);
    const stored = localStorage.getItem(BROWSER_STORAGE_KEY);
    expect(() => store.importProfile(parsed.profile)).toThrow();
    expect(localStorage.getItem(BROWSER_STORAGE_KEY)).toBe(stored);
  });

  it("replaces saved state with its exported envelope", () => {
    const store = createBrowserStore(localStorage);
    store.updateCurrent((state) => ({
      ...state,
      selectedCourseIds: ["canonical-a", "canonical-b"],
      completedCourseIds: ["canonical-a"],
      prerequisites: {
        ...state.prerequisites,
        rootCourseId: "root-a",
        includeRecommended: true,
        basis: "selected",
        completedNodeKeys: ["module:marked"],
        excludedNodeKeys: ["module:blocked"],
      },
      structure: {
        ...state.structure,
        programmeGroupIds: ["root-a", "root-b"],
        choices: { "p:root-a/2": ["choice-a"] },
        coursePlacements: { "canonical-a": "p:root-a" },
        modulePlacements: { "module-a": null },
        placedCourseIds: ["canonical-a"],
      },
    }));
    store.saveAsProfile("Second");
    const secondId = store.getSnapshot().currentProfileId;
    store.updateCurrent((state) => ({
      ...state,
      discover: { ...state.discover, mode: "at_least_one" },
    }));
    const before = structuredClone(store.getSnapshot());
    const parsed = parseBrowserImport(JSON.stringify(store.exportState()));
    if (parsed.type !== "tuni-course-explorer/state/2")
      throw new Error("Expected a state file");
    store.resetSavedData();
    expect(store.getSnapshot().currentProfileId).toBe("default");
    store.restoreState(parsed.state);
    expect(store.getSnapshot()).toEqual(before);
    expect(store.getSnapshot().currentProfileId).toBe(secondId);
    expect(createBrowserStore(localStorage).getSnapshot()).toEqual(before);
  });
});
