/** Pure scoped customization reset and placement normalization behavior. */
import { describe, expect, it } from "vitest";
import { emptyEdits } from "./state";
import { placeCourse, placeModuleWithCourses, resetScope } from "./edits";
import { applyStructure } from "./actions";
import {
  buildStructure,
  indexResolved,
  resolveStructure,
  type PlacedContent,
} from "./model";
import { createBrowserStore } from "../../state/store";
import type {
  CourseSummary,
  StructureRule,
  StudyStructureReport,
} from "../../api/types";

describe("structure edits", () => {
  it("resetScope discards only placements and choices scoped to the node, and Remove of a homeless id leaves no entry", () => {
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

  it("module additions use resolved destination keys and preserve selected courses", () => {
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
          children: [rule("CourseUnitRule", 0, { course })],
        }),
      },
    };
    const moduleA = {
      ...addedReport.root,
      rule: rule("CompositeRule", 0, {
        all_mandatory: true,
        children: [rule("CourseUnitRule", 0, { course })],
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
            rule("ModuleRule", 1, {
              module: {
                ...moduleA,
                rule: rule("CompositeRule", 0, {
                  all_mandatory: true,
                  children: [rule("CourseUnitRule", 0, { course })],
                }),
              },
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
    const root = buildStructure(rootReport);
    const content: PlacedContent = {
      reports: { "module-a": addedReport },
      courses: new Map([[course.group_id, course]]),
    };
    let store = createBrowserStore(localStorage);
    const initial = resolveStructure(root, emptyEdits(), content);
    applyStructure(store, () => ({
      next: {
        programmeGroupIds: ["root"],
        ...emptyEdits(),
        placedCourseIds: initial.subtree.map((item) => item.group_id),
      },
    }));
    store = createBrowserStore(localStorage);
    const first = placeModuleWithCourses(
      root,
      emptyEdits(),
      content,
      "module-a",
      "r/2",
    );
    // The course follows its module, so nothing needs a move confirmation.
    expect(first.moves).toEqual([]);
    let resolved = resolveStructure(root, first.edits, content);
    applyStructure(store, () => ({
      next: {
        programmeGroupIds: ["root"],
        ...first.edits,
        placedCourseIds: resolved.subtree.map((item) => item.group_id),
      },
    }));
    store = createBrowserStore(localStorage);
    expect(
      store.getSnapshot().profiles.default.state.selectedCourseIds,
    ).toEqual(["course-a"]);
    const owner = indexResolved(resolved).byKey.get("r")!;
    const removedModule = owner.removed.find(
      (entry) =>
        entry.kind === "module" && entry.module.group_id === "module-a",
    );
    if (!removedModule)
      throw new Error("Moved module missing from removed content");
    const second = placeModuleWithCourses(
      root,
      first.edits,
      content,
      "module-a",
      owner.node.key,
    );
    expect(second.moves).toEqual([]);
    resolved = resolveStructure(root, second.edits, content);
    applyStructure(store, () => ({
      next: {
        programmeGroupIds: ["root"],
        ...second.edits,
        placedCourseIds: resolved.subtree.map((item) => item.group_id),
      },
    }));
    store = createBrowserStore(localStorage);
    expect(
      store.getSnapshot().profiles.default.state.selectedCourseIds,
    ).toEqual(["course-a"]);
    expect(resolved.subtree.map((item) => item.group_id)).toEqual(["course-a"]);
    expect(indexResolved(resolved).courseAt.get("course-a")?.node.key).toBe(
      indexResolved(resolved).moduleAt.get("module-a")?.node.key,
    );
    expect(indexResolved(resolved).moduleAt.get("module-a")?.node.key).toBe(
      "r/1",
    );
  });
});
