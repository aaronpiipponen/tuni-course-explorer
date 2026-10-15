/** localStorage persistence for structure selection migration and removal. */
import { beforeEach, describe, expect, it } from "vitest";
import { createBrowserStore } from "../../state/store";
import {
  toggleCompleted,
  addCoursesToFreeChoice,
} from "../../state/course-actions";
import { applyStructure, resetUnplaced } from "./actions";
import {
  buildStructure,
  resolveStructure,
  withUnplaced,
  type PlacedContent,
} from "./model";
import { placeModule, placeModuleWithCourses } from "./edits";
import type {
  CourseSummary,
  StructureRule,
  StudyStructureReport,
} from "../../api/types";
import { emptyEdits } from "./state";

describe("structure selection actions", () => {
  beforeEach(() => localStorage.clear());
  it("applyStructure leaves deselected completions loose and drops them only on explicit full removal", () => {
    const store = createBrowserStore(localStorage);
    applyStructure(store, {
      rootGroupId: "root-a",
      choices: {},
      coursePlacements: {},
      modulePlacements: {},
      placedCourseIds: ["keep", "done-drop", "drop"],
    });
    addCoursesToFreeChoice(store, ["free"]);
    toggleCompleted(store, "done-drop");
    toggleCompleted(store, "keep");
    applyStructure(store, {
      rootGroupId: "root-b",
      choices: { choice: ["next"] },
      coursePlacements: {},
      modulePlacements: {},
      placedCourseIds: ["keep", "new"],
    });
    let state =
      createBrowserStore(localStorage).getSnapshot().profiles.default.state;
    expect(state.selectedCourseIds).toEqual([
      "keep",
      "done-drop",
      "free",
      "new",
    ]);
    expect(state.completedCourseIds).toEqual(["done-drop", "keep"]);
    expect(state.structure.placedCourseIds).toEqual(["keep", "new"]);
    applyStructure(
      createBrowserStore(localStorage),
      {
        rootGroupId: "root-b",
        choices: { choice: ["next"] },
        coursePlacements: {},
        modulePlacements: {},
        placedCourseIds: ["keep", "new"],
      },
      ["done-drop"],
    );
    state =
      createBrowserStore(localStorage).getSnapshot().profiles.default.state;
    expect(state.selectedCourseIds).not.toContain("done-drop");
    expect(state.completedCourseIds).not.toContain("done-drop");
    applyStructure(
      createBrowserStore(localStorage),
      {
        rootGroupId: "root-b",
        choices: { choice: ["next"] },
        coursePlacements: {},
        modulePlacements: {},
        placedCourseIds: ["keep", "new"],
      },
      [],
      ["free"],
    );
    state =
      createBrowserStore(localStorage).getSnapshot().profiles.default.state;
    expect(state.selectedCourseIds).not.toContain("free");
    expect(state.selectedCourseIds).toContain("keep");
    expect(state.completedCourseIds).toContain("keep");
  });

  it("outside-structure module lifecycle preserves canonical completion", () => {
    localStorage.clear();
    const summary = (id: string): CourseSummary => ({
      group_id: id,
      name_fi: id,
      name_en: id,
      code: id,
      credits_min: "5",
      credits_max: null,
      is_active: true,
      official_url: "https://example.invalid",
    });
    const siblingCourse = summary("sibling-course"),
      completedCourse = summary("completed-course"),
      pendingCourse = summary("pending-course"),
      optionalCourse = summary("optional-course"),
      looseCourse = summary("loose-course"),
      looseDone = summary("loose-done");
    const module = (id: string) => ({
      group_id: id,
      sisu_module_id: `${id}-v1`,
      module_type: "StudyModule" as const,
      code: id,
      name_fi: id,
      name_en: id,
    });
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
        module: module("bucket-module"),
        target_credits_min: null,
        target_credits_max: null,
        rule: rule("CompositeRule", 0, {
          all_mandatory: true,
          children: [
            rule("CourseUnitRule", 0, { course: completedCourse }),
            rule("CourseUnitRule", 1, { course: pendingCourse }),
          ],
        }),
      },
    };
    const siblingReport: StudyStructureReport["root"] = {
      module: module("sibling-module"),
      target_credits_min: null,
      target_credits_max: null,
      rule: rule("CompositeRule", 0, {
        all_mandatory: true,
        children: [rule("CourseUnitRule", 0, { course: siblingCourse })],
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
            rule("ModuleRule", 0, { module: siblingReport }),
            rule("ModuleRule", 1, { module: addedReport.root }),
            rule("CompositeRule", 2, {
              require_min: 0,
              require_max: 1,
              all_mandatory: false,
              children: [rule("CourseUnitRule", 0, { course: optionalCourse })],
            }),
          ],
        }),
      },
    };
    const tree = withUnplaced(buildStructure(rootReport));
    const content: PlacedContent = {
      reports: { "bucket-module": addedReport },
      courses: new Map(
        [
          siblingCourse,
          completedCourse,
          pendingCourse,
          optionalCourse,
          looseCourse,
          looseDone,
        ].map((item) => [item.group_id, item]),
      ),
    };
    let store = createBrowserStore(localStorage);
    let edits = emptyEdits();
    const commit = () => {
      const resolved = resolveStructure(tree, edits, content);
      applyStructure(store, {
        rootGroupId: "root",
        ...edits,
        placedCourseIds: resolved.subtree.map((item) => item.group_id),
      });
      store = createBrowserStore(localStorage);
      return resolved;
    };
    commit();
    let placed =
      store.getSnapshot().profiles.default.state.structure.placedCourseIds;
    let operation = placeModuleWithCourses(
      tree,
      edits,
      content,
      "bucket-module",
      "u",
      placed,
    );
    edits = operation.edits;
    commit();
    toggleCompleted(store, "completed-course");
    store = createBrowserStore(localStorage);
    placed =
      store.getSnapshot().profiles.default.state.structure.placedCourseIds;
    operation = placeModuleWithCourses(
      tree,
      edits,
      content,
      "bucket-module",
      "r/0",
      placed,
    );
    edits = operation.edits;
    let resolved = commit();
    expect(resolved.subtree.map((item) => item.group_id)).toEqual([
      "sibling-course",
      "completed-course",
      "pending-course",
    ]);
    store = createBrowserStore(localStorage);
    operation = placeModuleWithCourses(
      tree,
      edits,
      content,
      "bucket-module",
      "u",
      store.getSnapshot().profiles.default.state.structure.placedCourseIds,
    );
    edits = operation.edits;
    commit();
    edits = placeModule(edits, new Map(), "bucket-module", null);
    const deselectedModule = commit();
    store = createBrowserStore(localStorage);
    expect(deselectedModule.subtree.map((item) => item.group_id)).not.toContain(
      "completed-course",
    );
    expect(
      store.getSnapshot().profiles.default.state.selectedCourseIds,
    ).toContain("completed-course");
    expect(
      store.getSnapshot().profiles.default.state.completedCourseIds,
    ).toContain("completed-course");
    operation = placeModuleWithCourses(
      tree,
      edits,
      content,
      "bucket-module",
      "u",
      store.getSnapshot().profiles.default.state.structure.placedCourseIds,
    );
    edits = operation.edits;
    commit();
    addCoursesToFreeChoice(store, ["loose-course", "loose-done"]);
    toggleCompleted(store, "loose-done");
    store = createBrowserStore(localStorage);
    const before = resolveStructure(tree, edits, content);
    const officialSibling = before.children[0].children[0].subtree.map(
      (item) => item.group_id,
    );
    resetUnplaced(store, tree, content);
    store = createBrowserStore(localStorage);
    const state = store.getSnapshot().profiles.default.state;
    expect(state.selectedCourseIds).toEqual([
      "sibling-course",
      "completed-course",
      "loose-done",
    ]);
    expect(state.completedCourseIds).toEqual([
      "completed-course",
      "loose-done",
    ]);
    expect(state.structure.choices["r/2"]).toBeUndefined();
    expect(state.structure.modulePlacements["bucket-module"]).toBeNull();
    const after = resolveStructure(tree, state.structure, content);
    expect(
      after.children[0].children[0].subtree.map((item) => item.group_id),
    ).toEqual(officialSibling);
    expect(after.subtree).toEqual([siblingCourse]);
  });
});
