/** Structure editor: module confirmation and nested reset preserve another tab's stored edits. */
import { act, createElement } from "react";
import { createRoot } from "react-dom/client";
import { beforeEach, describe, expect, it } from "vitest";
import type {
  CourseSummary,
  ModuleSummary,
  StructureModule,
  StructureRule,
  StudyStructureReport,
} from "../../api/types";
import { createBrowserStore } from "../../state/store";
import { StoreContext } from "../../state/context";
import type { CourseMoveRequest } from "./CourseMoveConfirmDialog";
import {
  buildProgrammeForest,
  indexResolved,
  programmeKey,
  resolveStructure,
  type PlacedContent,
} from "./model";
import { emptyEdits } from "./state";
import { useStructureEditor } from "./useStructureEditor";

const baseRule = (patch: Partial<StructureRule>): StructureRule => ({
  node_type: "CompositeRule",
  sibling_position: 0,
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
  ...patch,
});
const courseSummary = (id: string, code: string): CourseSummary => ({
  group_id: id,
  name_fi: null,
  name_en: `${code} course`,
  code,
  credits_min: "5",
  credits_max: null,
  is_active: true,
  official_url: `https://example.org/${id}`,
});
const moduleSummary = (id: string, code: string): ModuleSummary => ({
  group_id: id,
  sisu_module_id: `sisu-${id}`,
  module_type: "Module",
  code,
  name_fi: null,
  name_en: `${code} module`,
});
/** The same official summary carrying the degree metadata a served nested holder has. */
const degreeSummary = (id: string, code: string): ModuleSummary => ({
  ...moduleSummary(id, code),
  module_type: "DegreeProgramme",
});
const courseChild = (
  id: string,
  code: string,
  position: number,
): StructureRule =>
  baseRule({
    node_type: "CourseUnitRule",
    sibling_position: position,
    course: courseSummary(id, code),
  });
const optionalModule = (node: StructureModule): StructureRule =>
  baseRule({
    sibling_position: 1,
    require_min: 0,
    require_max: 1,
    all_mandatory: false,
    children: [
      baseRule({ node_type: "ModuleRule", sibling_position: 0, module: node }),
    ],
  });
const optionalCourse = (
  id: string,
  code: string,
  position: number,
): StructureRule =>
  baseRule({
    sibling_position: position,
    require_min: 0,
    require_max: null,
    all_mandatory: false,
    children: [courseChild(id, code, 0)],
  });
const report = (
  summary: ModuleSummary,
  children: StructureRule[],
): StudyStructureReport => ({
  academic_year_start: 2026,
  root: {
    module: summary,
    target_credits_min: null,
    target_credits_max: null,
    rule: baseRule({ all_mandatory: true, children }),
  },
});
const contentOf = (
  reports: StudyStructureReport[],
  extra: CourseSummary[] = [],
): PlacedContent => {
  const courses = new Map<string, CourseSummary>();
  const collect = (rule: StructureRule) => {
    if (rule.course) courses.set(rule.course.group_id, rule.course);
    if (rule.module) collect(rule.module.rule);
    for (const child of rule.children) collect(child);
  };
  for (const item of reports) collect(item.root.rule);
  for (const course of extra) courses.set(course.group_id, course);
  return {
    reports: Object.fromEntries(
      reports.map((item) => [item.root.module.group_id, item]),
    ),
    courses,
  };
};
const currentState = (store: ReturnType<typeof createBrowserStore>) => {
  const snapshot = store.getSnapshot();
  return snapshot.profiles[snapshot.currentProfileId].state;
};
const until = async (check: () => boolean, label: string) => {
  for (let attempt = 0; attempt < 200; attempt += 1) {
    if (check()) return;
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
  }
  throw new Error(`Timed out waiting for ${label}`);
};

describe("structure editor module confirmation", () => {
  beforeEach(() => localStorage.clear());

  it("preserves another tab's structure edit while a module confirmation waits", async () => {
    (
      globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
    ).IS_REACT_ACT_ENVIRONMENT = true;
    const fixture = report(moduleSummary("prog-a", "PROG-A"), [
      courseChild("c-source", "C-SOURCE", 0),
      optionalModule({
        module: degreeSummary("mod-opt", "MOD-OPT"),
        target_credits_min: null,
        target_credits_max: null,
        rule: baseRule({
          node_type: "CourseUnitRule",
          course: courseSummary("c-source", "C-SOURCE"),
        }),
      }),
      courseChild("c-other", "C-OTHER", 2),
    ]);
    const content = contentOf([fixture], [courseSummary("c-loose", "C-LOOSE")]);
    const store = createBrowserStore(localStorage);
    const edits = emptyEdits();
    const tree = buildProgrammeForest([fixture]);
    const resolved = resolveStructure(tree, edits, content);
    const placed = resolved.subtree.map((course) => course.group_id);
    store.updateCurrent((state) => ({
      ...state,
      selectedCourseIds: placed,
      structure: {
        programmeGroupIds: ["prog-a"],
        ...edits,
        placedCourseIds: placed,
      },
    }));
    let requested: CourseMoveRequest | null = null;
    let answer: ((confirmed: boolean) => void) | null = null;
    let editor: ReturnType<typeof useStructureEditor> | null = null;
    const host = document.createElement("div");
    document.body.append(host);
    const root = createRoot(host);
    const Harness = () => {
      editor = useStructureEditor({
        resolved,
        edits,
        freeIds: [],
        content,
        extend: () => content,
        notify: () => undefined,
        confirmMoves: (request) => {
          requested = request;
          return new Promise<boolean>((resolve) => {
            answer = resolve;
          });
        },
      });
      return null;
    };
    try {
      await act(async () =>
        root.render(
          createElement(
            StoreContext.Provider,
            { value: store },
            createElement(Harness),
          ),
        ),
      );
      const group = resolved.children[0].node.ruleGroups.find(
        (item) => !item.required,
      );
      const entry = group?.options[0].entries[0];
      if (!entry || entry.kind !== "node" || !entry.node.module)
        throw new Error("The fixture module is missing");
      const module = entry.node.module;
      const operation = editor!.selectRuleModule(module, {
        entry,
        origin: entry.origin!,
      });
      await until(() => requested !== null, "the module confirmation");
      // The nested degree keeps its official type metadata while it moves as a module.
      expect((requested as CourseMoveRequest | null)?.holder.module_type).toBe(
        "DegreeProgramme",
      );
      // Another tab places, selects and completes an unrelated course of the same profile.
      const otherTab = createBrowserStore(localStorage);
      await act(async () => {
        otherTab.updateCurrent((state) => ({
          ...state,
          selectedCourseIds: [...state.selectedCourseIds, "c-loose"],
          completedCourseIds: [...state.completedCourseIds, "c-loose"],
          structure: {
            ...state.structure,
            coursePlacements: {
              ...state.structure.coursePlacements,
              "c-loose": programmeKey("prog-a"),
            },
          },
        }));
      });
      await act(async () => {
        answer?.(true);
        await operation;
      });
      const reloaded = currentState(createBrowserStore(localStorage));
      const after = indexResolved(
        resolveStructure(
          buildProgrammeForest([fixture]),
          reloaded.structure,
          content,
        ),
      );
      expect(after.moduleAt.get("mod-opt")).toBeDefined();
      expect(after.moduleAt.get("mod-opt")?.node.kind).toBe("module");
      expect(after.courseAt.get("c-source")?.node.module?.group_id).toBe(
        "mod-opt",
      );
      expect(after.courseAt.get("c-loose")?.node.key).toBe(
        programmeKey("prog-a"),
      );
      expect(reloaded.structure.coursePlacements["c-loose"]).toBe(
        programmeKey("prog-a"),
      );
      expect(reloaded.selectedCourseIds).toContain("c-loose");
      expect(reloaded.completedCourseIds).toEqual(["c-loose"]);
    } finally {
      await act(async () => root.unmount());
      host.remove();
    }
  });

  it("resets a nested module against the latest stored state without clearing outside completions", async () => {
    (
      globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
    ).IS_REACT_ACT_ENVIRONMENT = true;
    const holderKey = `${programmeKey("prog-a")}/1`;
    // The nested holder carries degree metadata and holds a completion of each kind.
    const holder = {
      module: degreeSummary("mod-nested", "NESTED"),
      target_credits_min: null,
      target_credits_max: null,
      rule: baseRule({
        all_mandatory: true,
        children: [
          courseChild("n-required", "N-REQUIRED", 0),
          courseChild("n-outside", "N-OUTSIDE", 1),
          optionalCourse("n-optional", "N-OPTIONAL", 2),
        ],
      }),
    };
    const progA = report(moduleSummary("prog-a", "PROG-A"), [
      courseChild("c-sibling", "C-SIBLING", 0),
      baseRule({
        node_type: "ModuleRule",
        sibling_position: 1,
        module: holder,
      }),
    ]);
    const progB = report(moduleSummary("prog-b", "PROG-B"), [
      courseChild("b-course", "B-COURSE", 0),
      optionalCourse("b-optional", "B-OPTIONAL", 1),
    ]);
    // The second store's course summary is present so the reset can project its placement.
    const content = contentOf(
      [progA, progB],
      [
        courseSummary("n-manual", "N-MANUAL"),
        courseSummary("loose-done", "LOOSE-DONE"),
        courseSummary("second-store-course", "SECOND-STORE"),
      ],
    );
    const nOptionalChoice = `${holderKey}/0/2`;
    const bChoice = `${programmeKey("prog-b")}/1`;
    const baseEdits = {
      choices: {
        [nOptionalChoice]: [`${nOptionalChoice}/0`],
        [bChoice]: [`${bChoice}/0`],
      },
      coursePlacements: {
        "n-manual": holderKey,
        "n-outside": programmeKey("prog-b"),
      },
      modulePlacements: {},
    };
    const tree = buildProgrammeForest([progA, progB]);
    for (const removeCompletedCourses of [false, true]) {
      localStorage.clear();
      const store = createBrowserStore(localStorage);
      const resolved = resolveStructure(tree, baseEdits, content);
      const placed = resolved.subtree.map((course) => course.group_id);
      store.updateCurrent((state) => ({
        ...state,
        selectedCourseIds: [...placed, "loose-done"],
        completedCourseIds: [
          "n-required",
          "n-optional",
          "n-manual",
          "n-outside",
          "b-course",
          "loose-done",
        ],
        structure: {
          programmeGroupIds: ["prog-a", "prog-b"],
          ...baseEdits,
          placedCourseIds: placed,
        },
      }));
      let editor: ReturnType<typeof useStructureEditor> | null = null;
      const host = document.createElement("div");
      document.body.append(host);
      const root = createRoot(host);
      const Harness = () => {
        editor = useStructureEditor({
          resolved,
          edits: baseEdits,
          freeIds: [],
          content,
          extend: () => content,
          notify: () => undefined,
          confirmMoves: () => Promise.resolve(true),
        });
        return null;
      };
      try {
        await act(async () =>
          root.render(
            createElement(
              StoreContext.Provider,
              { value: store },
              createElement(Harness),
            ),
          ),
        );
        const node = indexResolved(resolved).moduleAt.get("mod-nested")?.node;
        if (!node) throw new Error("The fixture holder is missing");
        // Both outcomes use the callback captured at mount. The first store is never refreshed.
        const reset = editor!.resetNode;
        const otherTab = createBrowserStore(localStorage);
        await act(async () => {
          otherTab.updateCurrent((state) => ({
            ...state,
            selectedCourseIds: [
              ...state.selectedCourseIds,
              "second-store-course",
            ],
            completedCourseIds: [
              ...state.completedCourseIds,
              "second-store-course",
            ],
            structure: {
              ...state.structure,
              coursePlacements: {
                ...state.structure.coursePlacements,
                "second-store-course": programmeKey("prog-b"),
              },
            },
          }));
        });
        await act(async () => reset(node, removeCompletedCourses));
        expect(editor!.error).toBeNull();
        const reloaded = currentState(createBrowserStore(localStorage));
        const after = indexResolved(
          resolveStructure(
            buildProgrammeForest([progA, progB]),
            reloaded.structure,
            content,
          ),
        );
        // The nested degree stays a module at its official place inside programme A.
        expect(after.moduleAt.get("mod-nested")?.node.kind).toBe("module");
        expect(after.moduleAt.get("mod-nested")?.node.key).toBe(holderKey);
        // The sibling official course and programme B's own state survive.
        expect(after.courseAt.get("c-sibling")?.node.key).toBe(
          programmeKey("prog-a"),
        );
        expect(reloaded.structure.choices[bChoice]).toEqual([`${bChoice}/0`]);
        expect(after.courseAt.get("b-optional")?.node.key).toBe(bChoice);
        expect(reloaded.completedCourseIds).toContain("b-course");
        expect(reloaded.completedCourseIds).toContain("loose-done");
        // The other store's placement and completion survive exactly.
        expect(reloaded.structure.coursePlacements["second-store-course"]).toBe(
          programmeKey("prog-b"),
        );
        expect(after.courseAt.get("second-store-course")?.node.key).toBe(
          programmeKey("prog-b"),
        );
        expect(reloaded.completedCourseIds).toContain("second-store-course");
        expect(reloaded.selectedCourseIds).toContain("second-store-course");
        // The identity programme A officially names but holds elsewhere keeps its completion.
        expect(reloaded.completedCourseIds).toContain("n-outside");
        expect(reloaded.selectedCourseIds).toContain("n-outside");
        expect(after.courseAt.get("n-required")?.node.key).toBe(holderKey);
        if (removeCompletedCourses) {
          expect(reloaded.completedCourseIds).not.toContain("n-required");
          expect(reloaded.selectedCourseIds).toContain("n-required");
          expect(reloaded.completedCourseIds).not.toContain("n-optional");
          expect(reloaded.selectedCourseIds).not.toContain("n-optional");
          expect(reloaded.completedCourseIds).not.toContain("n-manual");
          expect(reloaded.selectedCourseIds).not.toContain("n-manual");
        } else {
          expect(reloaded.completedCourseIds).toContain("n-required");
          expect(reloaded.completedCourseIds).toContain("n-optional");
          expect(reloaded.completedCourseIds).toContain("n-manual");
          expect(reloaded.selectedCourseIds).toContain("n-optional");
          expect(reloaded.selectedCourseIds).toContain("n-manual");
        }
        // Both choices discard the optional and manual places, so neither renders.
        expect(after.courseAt.get("n-optional")).toBeUndefined();
        expect(after.courseAt.get("n-manual")).toBeUndefined();
      } finally {
        await act(async () => root.unmount());
        host.remove();
      }
    }
  });
});
