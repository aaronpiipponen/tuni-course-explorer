/** localStorage persistence for structure selection migration, programme operations and removal. */
import { beforeEach, describe, expect, it } from "vitest";
import { createBrowserStore, type BrowserStore } from "../../state/store";
import {
  toggleCompleted,
  addCoursesToFreeChoice,
} from "../../state/course-actions";
import {
  applyStructure,
  changeProgrammes,
  programmeMoves,
  resetUnplaced,
  type StructureChange,
} from "./actions";
import {
  buildProgrammeForest,
  indexResolved,
  officialHomes,
  programmeKey,
  resolveStructure,
  type PlacedContent,
} from "./model";
import { placeModule, placeModuleWithCourses } from "./edits";
import type {
  CourseSummary,
  StructureRule,
  StudyStructureReport,
} from "../../api/types";
import { emptyEdits, UNPLACED_KEY, type StructureEdits } from "./state";

const course = (id: string): CourseSummary => ({
  group_id: id,
  name_fi: id,
  name_en: id,
  code: id,
  credits_min: "5",
  credits_max: null,
  is_active: true,
  official_url: "https://example.invalid",
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

/** One programme report with its mandatory courses and one trailing optional course. */
const programmeReport = (
  id: string,
  mandatory: readonly CourseSummary[],
  optional: CourseSummary | null = null,
): StudyStructureReport => ({
  academic_year_start: 2026,
  root: {
    module: {
      group_id: id,
      sisu_module_id: `${id}-v1`,
      module_type: "DegreeProgramme",
      code: id.toUpperCase(),
      name_fi: id,
      name_en: id,
    },
    target_credits_min: null,
    target_credits_max: null,
    rule: rule("CompositeRule", 0, {
      all_mandatory: true,
      children: [
        ...mandatory.map((item, index) =>
          rule("CourseUnitRule", index, { course: item }),
        ),
        ...(optional
          ? [
              rule("CompositeRule", mandatory.length, {
                require_min: 0,
                require_max: null,
                children: [rule("CourseUnitRule", 0, { course: optional })],
              }),
            ]
          : []),
      ],
    }),
  },
});

const selectOptional = (
  edits: StructureEdits,
  programmeId: string,
  position: number,
): StructureEdits => {
  const key = `${programmeKey(programmeId)}/${position}`;
  return { ...edits, choices: { ...edits.choices, [key]: [`${key}/0`] } };
};

const project = (
  ids: readonly string[],
  edits: StructureEdits,
  content: PlacedContent,
) =>
  resolveStructure(
    buildProgrammeForest(ids.map((id) => content.reports[id])),
    edits,
    content,
  );

/** Write one complete structure state as the pane's reconciliation does. */
const writeStructure = (
  store: BrowserStore,
  ids: readonly string[],
  edits: StructureEdits,
  content: PlacedContent,
  change: Partial<StructureChange> = {},
) => {
  const resolved = project(ids, edits, content);
  applyStructure(store, () => ({
    next: {
      programmeGroupIds: [...ids],
      ...edits,
      placedCourseIds: resolved.subtree.map((item) => item.group_id),
    },
    ...change,
  }));
  return resolved;
};

describe("structure selection actions", () => {
  beforeEach(() => localStorage.clear());
  it("applyStructure leaves deselected completions loose and drops them only on explicit full removal", () => {
    const store = createBrowserStore(localStorage);
    const write = (
      next: {
        programmeGroupIds?: readonly string[];
        choices?: StructureEdits["choices"];
        placedCourseIds: readonly string[];
      },
      removed: readonly string[] = [],
      discard: readonly string[] = [],
    ) =>
      applyStructure(store, () => ({
        next: {
          programmeGroupIds: [...(next.programmeGroupIds ?? ["root-a"])],
          choices: next.choices ?? {},
          coursePlacements: {},
          modulePlacements: {},
          placedCourseIds: [...next.placedCourseIds],
        },
        removedCourseIds: removed,
        discardUncompletedCourseIds: discard,
      }));
    write({ placedCourseIds: ["keep", "done-drop", "drop"] });
    addCoursesToFreeChoice(store, ["free"]);
    toggleCompleted(store, "done-drop");
    toggleCompleted(store, "keep");
    write({
      programmeGroupIds: ["root-b"],
      choices: { choice: ["next"] },
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
    write(
      {
        programmeGroupIds: ["root-b"],
        choices: { choice: ["next"] },
        placedCourseIds: ["keep", "new"],
      },
      ["done-drop"],
    );
    state =
      createBrowserStore(localStorage).getSnapshot().profiles.default.state;
    expect(state.selectedCourseIds).not.toContain("done-drop");
    expect(state.completedCourseIds).not.toContain("done-drop");
    write(
      {
        programmeGroupIds: ["root-b"],
        choices: { choice: ["next"] },
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
    const tree = buildProgrammeForest([rootReport]);
    const content: PlacedContent = {
      reports: { root: rootReport, "bucket-module": addedReport },
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
    const programme = programmeKey("root");
    let store = createBrowserStore(localStorage);
    let edits = emptyEdits();
    const commit = () => {
      const resolved = resolveStructure(tree, edits, content);
      applyStructure(store, () => ({
        next: {
          programmeGroupIds: ["root"],
          ...edits,
          placedCourseIds: resolved.subtree.map((item) => item.group_id),
        },
      }));
      store = createBrowserStore(localStorage);
      return resolved;
    };
    commit();
    let operation = placeModuleWithCourses(
      tree,
      edits,
      content,
      "bucket-module",
      "u",
    );
    edits = operation.edits;
    commit();
    toggleCompleted(store, "completed-course");
    store = createBrowserStore(localStorage);
    operation = placeModuleWithCourses(
      tree,
      edits,
      content,
      "bucket-module",
      `${programme}/0`,
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
    );
    edits = operation.edits;
    commit();
    edits = placeModule(
      edits,
      officialHomes(tree, edits, content),
      "bucket-module",
      null,
    );
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
    resetUnplaced(store, content);
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
    expect(state.structure.choices[`${programme}/2`]).toBeUndefined();
    expect(state.structure.modulePlacements["bucket-module"]).toBeNull();
    const after = resolveStructure(tree, state.structure, content);
    expect(
      after.children[0].children[0].subtree.map((item) => item.group_id),
    ).toEqual(officialSibling);
    expect(after.subtree).toEqual([siblingCourse]);
  });

  it("moves a shared course into the later holder and keeps it out of untouched holders", () => {
    localStorage.clear();
    let store = createBrowserStore(localStorage);
    const shared = course("shared"),
      dDefault = course("d-default"),
      dOptional = course("d-optional"),
      cDefault = course("c-default");
    const moduleB = {
      group_id: "mod-b",
      sisu_module_id: "mod-b-v1",
      module_type: "StudyModule" as const,
      code: "B",
      name_fi: "Moduuli B",
      name_en: "Module B",
    };
    const reportD: StudyStructureReport = {
      academic_year_start: 2026,
      root: {
        module: {
          group_id: "prog-d",
          sisu_module_id: "prog-d-v1",
          module_type: "DegreeProgramme",
          code: "D",
          name_fi: "D",
          name_en: "D",
        },
        target_credits_min: null,
        target_credits_max: null,
        rule: rule("CompositeRule", 0, {
          all_mandatory: true,
          children: [
            rule("ModuleRule", 0, {
              module: {
                module: moduleB,
                target_credits_min: null,
                target_credits_max: null,
                rule: rule("CompositeRule", 0, {
                  all_mandatory: true,
                  children: [rule("CourseUnitRule", 0, { course: shared })],
                }),
              },
            }),
            rule("CourseUnitRule", 1, { course: dDefault }),
            rule("CompositeRule", 2, {
              require_min: 0,
              require_max: null,
              children: [rule("CourseUnitRule", 0, { course: dOptional })],
            }),
          ],
        }),
      },
    };
    const reportC = programmeReport("prog-c", [shared, cDefault]);
    const content: PlacedContent = {
      reports: { "prog-d": reportD, "prog-c": reportC },
      courses: new Map(
        [shared, dDefault, dOptional, cDefault].map((item) => [
          item.group_id,
          item,
        ]),
      ),
    };
    const dChoice = `${programmeKey("prog-d")}/2`;
    const edits = selectOptional(emptyEdits(), "prog-d", 2);
    writeStructure(store, ["prog-d"], edits, content);
    toggleCompleted(store, "shared");
    store = createBrowserStore(localStorage);
    // Adding the later holder lists the shared course and the node it is in now.
    const moves = programmeMoves(
      store.getSnapshot().profiles.default.state.structure,
      { kind: "add", groupId: "prog-c" },
      content,
    );
    expect(moves.map((move) => move.course.group_id)).toEqual(["shared"]);
    expect(moves[0].from("en")).toBe("Module B");
    expect(moves[0].from("fi")).toBe("Moduuli B");
    changeProgrammes(store, { kind: "add", groupId: "prog-c" }, content);
    store = createBrowserStore(localStorage);
    let state = store.getSnapshot().profiles.default.state;
    expect(state.structure.programmeGroupIds).toEqual(["prog-d", "prog-c"]);
    // The earlier programme keeps its own key and its chosen option.
    expect(state.structure.choices[dChoice]).toEqual([`${dChoice}/0`]);
    expect(state.structure.coursePlacements["shared"]).toBe(
      programmeKey("prog-c"),
    );
    let resolved = resolveStructure(
      buildProgrammeForest([reportD, reportC]),
      state.structure,
      content,
    );
    expect(indexResolved(resolved).courseAt.get("shared")?.node.key).toBe(
      programmeKey("prog-c"),
    );
    expect(state.completedCourseIds).toContain("shared");
    expect(state.selectedCourseIds).toContain("shared");
    // Deleting the later holder leaves the course out of the holder the action does not touch.
    changeProgrammes(store, { kind: "delete", groupId: "prog-c" }, content);
    store = createBrowserStore(localStorage);
    state = store.getSnapshot().profiles.default.state;
    expect(state.structure.coursePlacements["shared"]).toBe(UNPLACED_KEY);
    resolved = resolveStructure(
      buildProgrammeForest([reportD]),
      state.structure,
      content,
    );
    expect(indexResolved(resolved).courseAt.get("shared")?.node.key).toBe(
      UNPLACED_KEY,
    );
    expect(state.completedCourseIds).toContain("shared");
    expect(state.selectedCourseIds).toContain("shared");
    // Resetting the programme that holds the earlier holder restores it there.
    changeProgrammes(store, { kind: "reset", groupId: "prog-d" }, content);
    store = createBrowserStore(localStorage);
    state = store.getSnapshot().profiles.default.state;
    resolved = resolveStructure(
      buildProgrammeForest([reportD]),
      state.structure,
      content,
    );
    expect(indexResolved(resolved).courseAt.get("shared")?.node.key).toBe(
      `${programmeKey("prog-d")}/0`,
    );
    expect(state.structure.choices).toEqual({});
    // Adding a module that officially holds the course moves it out of Module B as well.
    const moduleE = {
      group_id: "mod-e",
      sisu_module_id: "mod-e-v1",
      module_type: "StudyModule" as const,
      code: "E",
      name_fi: "Moduuli E",
      name_en: "Module E",
    };
    const reportE: StudyStructureReport = {
      academic_year_start: 2026,
      root: {
        module: moduleE,
        target_credits_min: null,
        target_credits_max: null,
        rule: rule("CompositeRule", 0, {
          all_mandatory: true,
          children: [rule("CourseUnitRule", 0, { course: shared })],
        }),
      },
    };
    const withE: PlacedContent = {
      reports: { ...content.reports, "mod-e": reportE },
      courses: content.courses,
    };
    const moduleKey = `${programmeKey("prog-d")}/m:mod-e`;
    const modulePlacement = placeModuleWithCourses(
      buildProgrammeForest([reportD]),
      state.structure,
      withE,
      "mod-e",
      programmeKey("prog-d"),
    );
    expect(modulePlacement.moves.map((move) => move.course.group_id)).toEqual([
      "shared",
    ]);
    expect(modulePlacement.moves[0].from("en")).toBe("Module B");
    const moduleProjection = resolveStructure(
      buildProgrammeForest([reportD]),
      modulePlacement.edits,
      withE,
    );
    applyStructure(store, () => ({
      next: {
        programmeGroupIds: ["prog-d"],
        ...modulePlacement.edits,
        placedCourseIds: moduleProjection.subtree.map((item) => item.group_id),
      },
    }));
    store = createBrowserStore(localStorage);
    state = store.getSnapshot().profiles.default.state;
    expect(state.structure.coursePlacements["shared"]).toBe(moduleKey);
    resolved = resolveStructure(
      buildProgrammeForest([reportD]),
      state.structure,
      withE,
    );
    expect(indexResolved(resolved).courseAt.get("shared")?.node.key).toBe(
      moduleKey,
    );
    expect(state.completedCourseIds).toContain("shared");
  });

  it("replaces or resets only the named programme while preserving completions", () => {
    for (const operation of ["replace", "reset"] as const) {
      localStorage.clear();
      let store = createBrowserStore(localStorage);
      const aRequired = course("a-required"),
        outsideHeld = course("outside-held"),
        aOptional = course("a-optional"),
        aManual = course("a-manual"),
        bRequired = course("b-required"),
        bOptional = course("b-optional"),
        looseDone = course("loose-done"),
        cDefault = course("c-default");
      const content: PlacedContent = {
        reports: {
          "prog-a": programmeReport(
            "prog-a",
            [aRequired, outsideHeld],
            aOptional,
          ),
          "prog-b": programmeReport("prog-b", [bRequired], bOptional),
          "prog-c": programmeReport("prog-c", [aRequired, cDefault]),
        },
        courses: new Map(
          [
            aRequired,
            outsideHeld,
            aOptional,
            aManual,
            bRequired,
            bOptional,
            looseDone,
            cDefault,
          ].map((item) => [item.group_id, item]),
        ),
      };
      const ids = ["prog-a", "prog-b"];
      let edits = selectOptional(emptyEdits(), "prog-a", 2);
      edits = selectOptional(edits, "prog-b", 1);
      edits = {
        ...edits,
        coursePlacements: {
          "a-manual": programmeKey("prog-a"),
          "outside-held": programmeKey("prog-b"),
        },
      };
      writeStructure(store, ids, edits, content);
      toggleCompleted(store, "a-required");
      toggleCompleted(store, "a-optional");
      toggleCompleted(store, "a-manual");
      toggleCompleted(store, "outside-held");
      toggleCompleted(store, "b-required");
      addCoursesToFreeChoice(store, ["loose-done"]);
      toggleCompleted(store, "loose-done");
      store = createBrowserStore(localStorage);
      changeProgrammes(
        store,
        operation === "replace"
          ? {
              kind: "replace",
              groupId: "prog-a",
              replacementGroupId: "prog-c",
            }
          : { kind: "reset", groupId: "prog-a" },
        content,
      );
      store = createBrowserStore(localStorage);
      const state = store.getSnapshot().profiles.default.state;
      expect(state.structure.programmeGroupIds).toEqual(
        operation === "replace" ? ["prog-c", "prog-b"] : ["prog-a", "prog-b"],
      );
      // Only the named programme's scope is cleared.
      expect(
        Object.keys(state.structure.choices).every(
          (key) => !key.startsWith(programmeKey("prog-a")),
        ),
      ).toBe(true);
      expect(state.structure.choices[`${programmeKey("prog-b")}/1`]).toEqual([
        `${programmeKey("prog-b")}/1/0`,
      ]);
      expect(state.structure.coursePlacements["a-manual"]).toBeUndefined();
      // Ordinary reset keeps every completion and restores the programme's official content.
      expect(state.completedCourseIds).toEqual([
        "a-required",
        "a-optional",
        "a-manual",
        "outside-held",
        "b-required",
        "loose-done",
      ]);
      expect(state.selectedCourseIds).toEqual(
        expect.arrayContaining([
          "a-required",
          "a-optional",
          "a-manual",
          "outside-held",
          "b-required",
          "b-optional",
          "loose-done",
        ]),
      );
      expect(state.structure.placedCourseIds).toContain("a-required");
      expect(state.structure.placedCourseIds).toContain("b-optional");
      expect(state.structure.placedCourseIds).not.toContain("a-optional");
      expect(state.structure.placedCourseIds).not.toContain("a-manual");
      if (operation === "replace")
        expect(state.structure.placedCourseIds).toContain("c-default");
      else expect(state.structure.placedCourseIds).not.toContain("c-default");
      // The discarded optional and manual courses are loose, not in the named programme.
      const after = project(
        state.structure.programmeGroupIds,
        state.structure,
        content,
      );
      const placed = new Set(after.subtree.map((item) => item.group_id));
      expect(placed.has("a-optional")).toBe(false);
      expect(placed.has("a-manual")).toBe(false);
      expect(state.selectedCourseIds.filter((id) => !placed.has(id))).toEqual(
        expect.arrayContaining(["a-optional", "a-manual", "loose-done"]),
      );
    }
  });

  it("clears only the completions held by the reset programme", () => {
    localStorage.clear();
    let store = createBrowserStore(localStorage);
    const aRequired = course("a-required"),
      outsideHeld = course("outside-held"),
      aOptional = course("a-optional"),
      aManual = course("a-manual"),
      bRequired = course("b-required"),
      bOptional = course("b-optional"),
      looseDone = course("loose-done");
    const content: PlacedContent = {
      reports: {
        "prog-a": programmeReport(
          "prog-a",
          [aRequired, outsideHeld],
          aOptional,
        ),
        "prog-b": programmeReport("prog-b", [bRequired], bOptional),
      },
      courses: new Map(
        [
          aRequired,
          outsideHeld,
          aOptional,
          aManual,
          bRequired,
          bOptional,
          looseDone,
        ].map((item) => [item.group_id, item]),
      ),
    };
    const ids = ["prog-a", "prog-b"];
    let edits = selectOptional(emptyEdits(), "prog-a", 2);
    edits = selectOptional(edits, "prog-b", 1);
    edits = {
      ...edits,
      coursePlacements: {
        "a-manual": programmeKey("prog-a"),
        "outside-held": programmeKey("prog-b"),
      },
    };
    const before = indexResolved(writeStructure(store, ids, edits, content));
    // The completed identity programme A officially names but does not hold sits at B.
    expect(before.courseAt.get("outside-held")?.node.key).toBe(
      programmeKey("prog-b"),
    );
    expect(
      before.byKey
        .get(programmeKey("prog-a"))
        ?.subtree.map((item) => item.group_id),
    ).not.toContain("outside-held");
    expect(before.courseAt.get("a-required")?.node.key).toBe(
      programmeKey("prog-a"),
    );
    expect(before.courseAt.get("a-optional")?.node.key).toBe(
      `${programmeKey("prog-a")}/2`,
    );
    expect(before.courseAt.get("a-manual")?.node.key).toBe(
      programmeKey("prog-a"),
    );
    addCoursesToFreeChoice(store, ["loose-done"]);
    toggleCompleted(store, "a-required");
    toggleCompleted(store, "a-optional");
    toggleCompleted(store, "a-manual");
    toggleCompleted(store, "outside-held");
    toggleCompleted(store, "b-required");
    toggleCompleted(store, "loose-done");
    store = createBrowserStore(localStorage);
    changeProgrammes(
      store,
      { kind: "reset", groupId: "prog-a" },
      content,
      true,
    );
    store = createBrowserStore(localStorage);
    const state = store.getSnapshot().profiles.default.state;
    const completed = new Set(state.completedCourseIds);
    const selected = new Set(state.selectedCourseIds);
    expect(state.structure.programmeGroupIds).toEqual(["prog-a", "prog-b"]);
    // Only programme A's own completions lose their completion.
    expect(completed.has("a-required")).toBe(false);
    expect(completed.has("a-optional")).toBe(false);
    expect(completed.has("a-manual")).toBe(false);
    expect(state.completedCourseIds).toEqual([
      "outside-held",
      "b-required",
      "loose-done",
    ]);
    // The restored mandatory course returns selected and uncompleted. The discarded
    // optional and manual completions leave both sets.
    expect(selected.has("a-required")).toBe(true);
    expect(selected.has("a-optional")).toBe(false);
    expect(selected.has("a-manual")).toBe(false);
    // Completions outside the reset programme's scope survive.
    expect(completed.has("outside-held")).toBe(true);
    expect(selected.has("outside-held")).toBe(true);
    expect(completed.has("b-required")).toBe(true);
    expect(selected.has("b-required")).toBe(true);
    expect(completed.has("loose-done")).toBe(true);
    expect(selected.has("loose-done")).toBe(true);
    // Programme B's own choice and the ordered programmes are retained.
    expect(state.structure.choices[`${programmeKey("prog-b")}/1`]).toEqual([
      `${programmeKey("prog-b")}/1/0`,
    ]);
    expect(
      Object.keys(state.structure.choices).every(
        (key) => !key.startsWith(programmeKey("prog-a")),
      ),
    ).toBe(true);
    const after = project(
      state.structure.programmeGroupIds,
      state.structure,
      content,
    );
    const index = indexResolved(after);
    expect(index.courseAt.get("a-required")?.node.key).toBe(
      programmeKey("prog-a"),
    );
    expect(index.courseAt.get("a-optional")).toBeUndefined();
    expect(index.courseAt.get("a-manual")).toBeUndefined();
    expect(after.subtree.map((item) => item.group_id)).not.toContain(
      "a-optional",
    );
    expect(after.subtree.map((item) => item.group_id)).not.toContain(
      "a-manual",
    );
    expect(state.structure.placedCourseIds).not.toContain("a-optional");
    expect(state.structure.placedCourseIds).not.toContain("a-manual");
    // Programme B's own completed course and chosen option keep their place.
    expect(index.courseAt.get("b-required")?.node.key).toBe(
      programmeKey("prog-b"),
    );
    expect(index.courseAt.get("b-optional")?.node.key).toBe(
      `${programmeKey("prog-b")}/1`,
    );
  });

  it("deletes a programme without losing completed courses or another programme's state", () => {
    localStorage.clear();
    let store = createBrowserStore(localStorage);
    const aDefault = course("a-default"),
      aOptional = course("a-optional"),
      bDefault = course("b-default"),
      bOptional = course("b-optional"),
      loose = course("loose");
    const content: PlacedContent = {
      reports: {
        "prog-a": programmeReport("prog-a", [aDefault], aOptional),
        "prog-b": programmeReport("prog-b", [bDefault], bOptional),
      },
      courses: new Map(
        [aDefault, aOptional, bDefault, bOptional, loose].map((item) => [
          item.group_id,
          item,
        ]),
      ),
    };
    let edits = selectOptional(emptyEdits(), "prog-a", 1);
    edits = selectOptional(edits, "prog-b", 1);
    writeStructure(store, ["prog-a", "prog-b"], edits, content);
    toggleCompleted(store, "b-default");
    addCoursesToFreeChoice(store, ["loose"]);
    store = createBrowserStore(localStorage);
    changeProgrammes(store, { kind: "delete", groupId: "prog-b" }, content);
    store = createBrowserStore(localStorage);
    let state = store.getSnapshot().profiles.default.state;
    expect(state.structure.programmeGroupIds).toEqual(["prog-a"]);
    expect(state.completedCourseIds).toEqual(["b-default"]);
    expect(state.selectedCourseIds).toEqual(
      expect.arrayContaining(["a-default", "a-optional", "b-default", "loose"]),
    );
    // The deleted programme leaves no scope behind, and the other programme holds its own state.
    expect(Object.keys(state.structure.choices)).toEqual([
      `${programmeKey("prog-a")}/1`,
    ]);
    expect(state.structure.placedCourseIds).toEqual([
      "a-default",
      "a-optional",
    ]);
    // Deleting the last programme leaves the completed course loose and clears the last scope.
    changeProgrammes(store, { kind: "delete", groupId: "prog-a" }, content);
    store = createBrowserStore(localStorage);
    state = store.getSnapshot().profiles.default.state;
    expect(state.structure.programmeGroupIds).toEqual([]);
    expect(state.completedCourseIds).toEqual(["b-default"]);
    expect(state.selectedCourseIds).toEqual(
      expect.arrayContaining(["b-default", "loose"]),
    );
    expect(state.selectedCourseIds).not.toContain("a-optional");
    expect(state.structure.choices).toEqual({});
    expect(state.structure.placedCourseIds).toEqual([]);
  });
});
