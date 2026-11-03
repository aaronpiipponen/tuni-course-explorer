/** Scoped customization reset, placement normalization and rendered placement behavior. */
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { describe, expect, it } from "vitest";
import { emptyEdits, type StructureEdits } from "./state";
import { placeCourse, placeModuleWithCourses, resetScope } from "./edits";
import { applyStructure } from "./actions";
import {
  buildProgrammeForest,
  indexResolved,
  programmeKey,
  resolveStructure,
  type PlacedContent,
} from "./model";
import { StructurePane } from "./StructurePane";
import { moduleVersionKey } from "./moduleVersions";
import { READ_CACHE_CAPACITY, ReadCache } from "../../app/readCache";
import { ReadCacheContext } from "../../app/readCacheContext";
import { WebFeaturesContext } from "../../app/webFeaturesContext";
import { NoticeProvider } from "../../shared/NoticeProvider";
import { StoreContext } from "../../state/context";
import { toggleCompleted } from "../../state/course-actions";
import { createBrowserStore } from "../../state/store";
import type { ProfileState } from "../../state/types";
import type {
  CourseSummary,
  StructureRule,
  StudyStructureReport,
} from "../../api/types";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

describe("structure edits", () => {
  it("discards only placements and choices scoped to the node, and removing a homeless id leaves no entry", () => {
    const homes = new Map<string, readonly string[]>([
      ["moved-in", ["r/1"]],
      ["moved-out", ["r/1"]],
      ["course-in", ["r/1/0"]],
    ]);
    const edits = {
      choices: { "r/1/0": ["a"], "r/2": ["b"] },
      coursePlacements: {
        "moved-in": "r/1/0",
        "moved-out": "r/9",
        outside: "r/10",
        removed: null,
      },
      modulePlacements: { "module-in": "r/1/2", "module-out": "r/8" },
    };
    expect(resetScope(edits, homes, "r/1")).toEqual({
      choices: { "r/2": ["b"] },
      coursePlacements: { outside: "r/10", removed: null },
      modulePlacements: { "module-out": "r/8" },
    });
    expect(
      placeCourse(emptyEdits(), homes, "course-in", null).coursePlacements,
    ).toEqual({ "course-in": null });
    expect(
      placeCourse(emptyEdits(), homes, "homeless", null).coursePlacements,
    ).toEqual({});
  });

  it("module additions use resolved destination keys and preserve selected courses", async () => {
    localStorage.clear();
    const course: CourseSummary = {
      group_id: "course-a",
      name_fi: "A",
      name_en: "A",
      code: "A",
      credits_min: "5",
      credits_max: null,
      is_active: true,
      official_url: "https://example.invalid",
    };
    const removedCourse: CourseSummary = {
      ...course,
      group_id: "course-removed",
      name_en: "Removed",
      code: "REMOVED",
    };
    const manualCourse: CourseSummary = {
      ...course,
      group_id: "course-manual",
      name_en: "Manual",
      code: "MANUAL",
    };
    const versions = { "module-a": "module-a-v1" };
    const module = {
      group_id: "module-a",
      sisu_module_id: "module-a-v1",
      module_type: "StudyModule" as const,
      code: "MA",
      name_fi: "Module A",
      name_en: "Module A",
    };
    const emptyModule = {
      group_id: "module-b",
      sisu_module_id: "module-b-v1",
      module_type: "StudyModule" as const,
      code: "MB",
      name_fi: "Module B",
      name_en: "Module B",
    };
    const rule = (
      node_type: StructureRule["node_type"],
      sibling_position: number,
      fields: Partial<StructureRule> = {},
    ): StructureRule => ({
      node_type,
      sibling_position,
      require_min: null,
      require_max: null,
      all_mandatory: null,
      credits_min: null,
      credits_max: null,
      count_min: null,
      count_max: null,
      referenced_group_id: null,
      children: [],
      course: null,
      module: null,
      unresolved: null,
      ...fields,
    });
    const addedReport: StudyStructureReport = {
      academic_year_start: 2026,
      root: {
        module,
        target_credits_min: null,
        target_credits_max: null,
        rule: rule("CompositeRule", 0, {
          all_mandatory: true,
          children: [
            rule("CourseUnitRule", 0, { course }),
            rule("CourseUnitRule", 1, { course: removedCourse }),
          ],
        }),
      },
    };
    const moduleA = {
      ...addedReport.root,
      rule: rule("CompositeRule", 0, {
        all_mandatory: true,
        children: [
          rule("CourseUnitRule", 0, { course }),
          rule("CourseUnitRule", 1, { course: removedCourse }),
        ],
      }),
    };
    const rootReport: StudyStructureReport = {
      academic_year_start: 2026,
      root: {
        module: {
          group_id: "root",
          sisu_module_id: "root-v1",
          module_type: "DegreeProgramme",
          code: "ROOT",
          name_fi: "Root",
          name_en: "Root",
        },
        target_credits_min: null,
        target_credits_max: null,
        rule: rule("CompositeRule", 0, {
          all_mandatory: true,
          children: [
            rule("CompositeRule", 1, {
              require_min: 1,
              require_max: 1,
              all_mandatory: false,
              children: [
                rule("ModuleRule", 0, {
                  module: {
                    ...moduleA,
                    rule: rule("CompositeRule", 0, {
                      all_mandatory: true,
                      children: [
                        rule("CourseUnitRule", 0, { course }),
                        rule("CourseUnitRule", 1, { course: removedCourse }),
                      ],
                    }),
                  },
                }),
              ],
            }),
            rule("ModuleRule", 2, {
              module: {
                ...addedReport.root,
                module: emptyModule,
                rule: rule("CompositeRule", 0, { all_mandatory: true }),
              },
            }),
          ],
        }),
      },
    };
    const root = buildProgrammeForest([rootReport]);
    const ownerKey = programmeKey("root");
    const content: PlacedContent = {
      reports: { root: rootReport, "module-a": addedReport },
      courses: new Map([
        [course.group_id, course],
        [removedCourse.group_id, removedCourse],
        [manualCourse.group_id, manualCourse],
      ]),
    };
    let store = createBrowserStore(localStorage);
    const initial = resolveStructure(root, emptyEdits(), content);
    applyStructure(store, () => ({
      next: {
        programmeGroupIds: ["root"],
        moduleVersions: versions,
        ...emptyEdits(),
        placedCourseIds: initial.subtree.map((item) => item.group_id),
        courseOrder: ["course-a"],
      },
    }));
    store = createBrowserStore(localStorage);
    const first = placeModuleWithCourses(
      root,
      emptyEdits(),
      content,
      "module-a",
      `${ownerKey}/2`,
    );
    // The course follows its module, so nothing needs a move confirmation.
    expect(first.moves).toEqual([]);
    // The placement record names the containing node, not the module identity it places.
    expect(first.edits.modulePlacements["module-a"]).toBe(`${ownerKey}/2`);
    let resolved = resolveStructure(root, first.edits, content);
    applyStructure(store, () => ({
      next: {
        programmeGroupIds: ["root"],
        moduleVersions: versions,
        ...first.edits,
        placedCourseIds: resolved.subtree.map((item) => item.group_id),
        courseOrder: ["course-a"],
      },
    }));
    store = createBrowserStore(localStorage);
    expect(
      store.getSnapshot().profiles.default.state.selectedCourseIds,
    ).toEqual(["course-a", "course-removed"]);
    toggleCompleted(store, "course-a");
    const baseline = structuredClone(
      store.getSnapshot().profiles.default.state,
    );
    expect(indexResolved(resolved).moduleAt.get("module-a")?.node.key).toBe(
      `${ownerKey}/2/m:module-a`,
    );

    const identity = "synthetic-structure-dataset";
    const selectionKey = moduleVersionKey(versions);
    const cache = new ReadCache(identity, READ_CACHE_CAPACITY);
    cache.put(
      identity,
      JSON.stringify(["study-structure", "root", selectionKey]),
      rootReport,
    );
    cache.put(
      identity,
      JSON.stringify(["study-structure", "module-a", selectionKey]),
      addedReport,
    );
    cache.put(
      identity,
      JSON.stringify(["course-summaries", ["course-a", "course-removed"]]),
      {
        dataset_identity: identity,
        results: [course, removedCourse],
      },
    );
    const originalMatchMedia = window.matchMedia;
    window.matchMedia = ((query: string) => ({
      matches: true,
      media: query,
      onchange: null,
      addListener() {},
      removeListener() {},
      addEventListener() {},
      removeEventListener() {},
      dispatchEvent: () => false,
    })) as typeof window.matchMedia;
    const host = document.createElement("div");
    document.body.append(host);
    let reactRoot: Root | null = null;
    const expectSavedState = (state: ProfileState) => {
      expect(state.structure.programmeGroupIds).toEqual(
        baseline.structure.programmeGroupIds,
      );
      expect(state.structure.choices).toEqual(baseline.structure.choices);
      expect(state.structure.coursePlacements).toEqual(
        baseline.structure.coursePlacements,
      );
      expect(state.structure.modulePlacements).toEqual(
        baseline.structure.modulePlacements,
      );
      expect(state.structure.moduleVersions).toEqual(
        baseline.structure.moduleVersions,
      );
      expect(state.structure.placedCourseIds).toEqual(
        baseline.structure.placedCourseIds,
      );
      expect(state.structure.courseOrder).toEqual(
        baseline.structure.courseOrder,
      );
      expect(baseline.structure.courseOrder).toEqual(["course-a"]);
      expect(state.selectedCourseIds).toEqual(baseline.selectedCourseIds);
      expect(state.completedCourseIds).toEqual(baseline.completedCourseIds);
    };
    const expectRenderedPlacement = () => {
      const moduleARow = [...host.querySelectorAll(".shead-open .sname")]
        .find((name) => name.textContent === "Module A")
        ?.closest(".snode");
      const moduleBRow = [...host.querySelectorAll(".shead-open .sname")]
        .find((name) => name.textContent === "Module B")
        ?.closest(".snode");
      expect(moduleARow).toBeTruthy();
      expect(moduleBRow).toBeTruthy();
      if (!moduleARow || !moduleBRow)
        throw new Error("The placed module rows are missing");
      expect(moduleBRow.contains(moduleARow)).toBe(true);
      expect(moduleARow.querySelectorAll(".structure-card")).toHaveLength(2);
      expect(host.querySelectorAll(".structure-card")).toHaveLength(2);
      const unplacedRow = [...host.querySelectorAll(".shead-open .sname")]
        .find((name) => name.textContent === "Unplaced studies")
        ?.closest(".snode");
      expect(unplacedRow).toBeTruthy();
      if (!unplacedRow) throw new Error("The Unplaced studies row is missing");
      expect(unplacedRow.querySelector(".structure-card")).toBeNull();
    };
    const renderPane = async () => {
      const mounted = createRoot(host);
      reactRoot = mounted;
      await act(async () => {
        mounted.render(
          createElement(
            StoreContext.Provider,
            { value: store },
            createElement(
              ReadCacheContext.Provider,
              { value: cache },
              createElement(
                WebFeaturesContext.Provider,
                {
                  value: {
                    embeddings_enabled: false,
                    inference_enabled: false,
                    dataset_identity: identity,
                  },
                },
                createElement(
                  NoticeProvider,
                  null,
                  createElement(StructurePane),
                ),
              ),
            ),
          ),
        );
      });
      await act(async () => {});
      await act(async () => {});
    };
    try {
      await renderPane();
      expectRenderedPlacement();
      expectSavedState(store.getSnapshot().profiles.default.state);
      await act(async () => reactRoot?.unmount());
      reactRoot = null;
      store = createBrowserStore(localStorage);
      await renderPane();
      expectRenderedPlacement();
      expectSavedState(store.getSnapshot().profiles.default.state);
      await act(async () => reactRoot?.unmount());
      reactRoot = null;

      const owner = indexResolved(resolved).byKey.get(ownerKey)!;
      const current = store.getSnapshot().profiles.default.state.structure;
      const movedModuleKey =
        indexResolved(resolved).moduleAt.get("module-a")!.node.key;
      // The module carries its own current subtree: a removed official child and a manual child.
      const movedEdits: StructureEdits = {
        choices: current.choices,
        coursePlacements: {
          ...current.coursePlacements,
          "course-removed": null,
          "course-manual": movedModuleKey,
        },
        modulePlacements: current.modulePlacements,
      };
      const second = placeModuleWithCourses(
        root,
        movedEdits,
        content,
        "module-a",
        owner.node.key,
      );
      expect(second.moves).toEqual([]);
      // The transparent rule's containing key is the exact official destination.
      expect(second.edits.modulePlacements["module-a"]).toBe(`${ownerKey}/1`);
      resolved = resolveStructure(root, second.edits, content);
      applyStructure(store, () => ({
        next: {
          programmeGroupIds: ["root"],
          moduleVersions: current.moduleVersions,
          ...second.edits,
          placedCourseIds: resolved.subtree.map((item) => item.group_id),
          courseOrder: [],
        },
      }));
      store = createBrowserStore(localStorage);
      const returned = store.getSnapshot().profiles.default.state;
      const returnedModule = indexResolved(resolved).moduleAt.get("module-a");
      expect(returnedModule?.node.key).toBe(`${ownerKey}/1/0`);
      expect(returnedModule?.added).toBe(false);
      expect(returned.structure.moduleVersions).toEqual(versions);
      expect(returned.selectedCourseIds).toEqual(["course-a", "course-manual"]);
      expect(returned.completedCourseIds).toEqual(["course-a"]);
      expect(resolved.subtree.map((item) => item.group_id)).toEqual([
        "course-a",
        "course-manual",
      ]);
      expect(indexResolved(resolved).courseAt.get("course-a")?.node.key).toBe(
        returnedModule?.node.key,
      );
      expect(
        indexResolved(resolved).courseAt.get("course-manual")?.node.key,
      ).toBe(returnedModule?.node.key);
      expect(
        indexResolved(resolved)
          .courseAt.get("course-manual")
          ?.courses.find((item) => item.course.group_id === "course-manual")
          ?.added,
      ).toBe(true);
      expect(returned.structure.coursePlacements["course-manual"]).toBe(
        returnedModule?.node.key,
      );
      expect(returned.structure.coursePlacements["course-removed"]).toBeNull();
      expect(
        indexResolved(resolved).courseAt.get("course-removed"),
      ).toBeUndefined();
    } finally {
      if (reactRoot) await act(async () => reactRoot!.unmount());
      host.remove();
      window.matchMedia = originalMatchMedia;
    }
  });
});
