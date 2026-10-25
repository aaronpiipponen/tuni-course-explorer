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
import { READ_CACHE_CAPACITY, ReadCache } from "../../app/readCache";
import { ReadCacheContext } from "../../app/readCacheContext";
import { createBrowserStore, BROWSER_STORAGE_KEY } from "../../state/store";
import { StoreContext } from "../../state/context";
import type {
  CourseMoveAnswer,
  CourseMoveRequest,
} from "./CourseMoveConfirmDialog";
import {
  buildProgrammeForest,
  indexResolved,
  programmeKey,
  resolveStructure,
  type PlacedContent,
  type ResolvedNode,
} from "./model";
import { emptyEdits, type StructureEdits } from "./state";
import { moduleName } from "./presentation";
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
  referenced_group_id: null,
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

/** Mount one editor hook over the real store, read cache and supplied edits. */
function mountEditor({
  store,
  resolved,
  edits,
  content,
  confirmMoves,
}: {
  store: ReturnType<typeof createBrowserStore>;
  resolved: ResolvedNode;
  edits: StructureEdits;
  content: PlacedContent;
  confirmMoves: (request: CourseMoveRequest) => Promise<CourseMoveAnswer>;
}) {
  let editor: ReturnType<typeof useStructureEditor> | null = null;
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  const cache = new ReadCache("dataset-one", READ_CACHE_CAPACITY);
  const Harness = () => {
    editor = useStructureEditor({
      resolved,
      edits,
      freeIds: [],
      content,
      extend: () => content,
      notify: () => undefined,
      contentDatasetIdentity: "dataset-one",
      contentSelectionKey: "[]",
      confirmMoves,
    });
    return null;
  };
  return {
    render: () =>
      act(async () =>
        root.render(
          createElement(
            StoreContext.Provider,
            { value: store },
            createElement(
              ReadCacheContext.Provider,
              { value: cache },
              createElement(Harness),
            ),
          ),
        ),
      ),
    editor: () => editor,
    unmount: async () => {
      await act(async () => root.unmount());
      host.remove();
    },
  };
}

/**
 * Build one programme holding a bare module whose root rule is a choice of two courses.
 *
 * The first option is chosen, so the course renders through the choice node and its containing
 * module is the only displayed holder.
 */
function chosenCourseFixture() {
  const labReport = report(moduleSummary("mod-lab", "LAB"), [
    baseRule({
      require_min: 0,
      require_max: null,
      all_mandatory: false,
      children: [
        courseChild("c-chosen", "C-CHOSEN", 0),
        courseChild("c-alt", "C-ALT", 1),
      ],
    }),
  ]);
  const programme = report(degreeSummary("prog-a", "PROG-A"), [
    baseRule({
      node_type: "ModuleRule",
      sibling_position: 0,
      module: labReport.root,
    }),
  ]);
  const content = contentOf([labReport, programme]);
  const tree = buildProgrammeForest([programme]);
  const empty = resolveStructure(tree, emptyEdits(), content);
  const choice = [...indexResolved(empty).byKey.values()].find(
    (node) => node.node.kind === "choice",
  );
  if (!choice) throw new Error("The fixture choice is missing");
  const edits: StructureEdits = {
    ...emptyEdits(),
    choices: { [choice.node.key]: [choice.node.options[0].key] },
  };
  return {
    labModule: labReport.root.module,
    programme,
    content,
    tree,
    edits,
    resolved: resolveStructure(tree, edits, content),
  };
}

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
        moduleVersions: {},
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
    const cache = new ReadCache("dataset-one", READ_CACHE_CAPACITY);
    const Harness = () => {
      editor = useStructureEditor({
        resolved,
        edits,
        freeIds: [],
        content,
        extend: () => content,
        notify: () => undefined,
        contentDatasetIdentity: "dataset-one",
        contentSelectionKey: "[]",
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
            createElement(
              ReadCacheContext.Provider,
              { value: cache },
              createElement(Harness),
            ),
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
    // The nested holder carries degree metadata, an optional module and a completion of each kind.
    const optionalHolder = {
      module: degreeSummary("mod-optional", "MOD-OPTIONAL"),
      target_credits_min: null,
      target_credits_max: null,
      rule: baseRule({
        all_mandatory: true,
        children: [courseChild("o-required", "O-REQUIRED", 0)],
      }),
    };
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
          baseRule({
            sibling_position: 3,
            require_min: 0,
            require_max: 1,
            all_mandatory: false,
            children: [
              baseRule({
                node_type: "ModuleRule",
                sibling_position: 0,
                module: optionalHolder,
              }),
            ],
          }),
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
    const optionalModuleChoice = `${holderKey}/0/3`;
    const bChoice = `${programmeKey("prog-b")}/1`;
    const baseEdits = {
      choices: {
        [nOptionalChoice]: [`${nOptionalChoice}/0`],
        [optionalModuleChoice]: [`${optionalModuleChoice}/0`],
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
          moduleVersions: {
            "mod-nested": "sisu-mod-nested",
            "mod-optional": "sisu-mod-optional",
            "prog-b": "sisu-prog-b",
          },
          ...baseEdits,
          placedCourseIds: placed,
        },
      }));
      let editor: ReturnType<typeof useStructureEditor> | null = null;
      const host = document.createElement("div");
      document.body.append(host);
      const root = createRoot(host);
      const cache = new ReadCache("dataset-one", READ_CACHE_CAPACITY);
      const Harness = () => {
        editor = useStructureEditor({
          resolved,
          edits: baseEdits,
          freeIds: [],
          content,
          extend: () => content,
          notify: () => undefined,
          contentDatasetIdentity: "dataset-one",
          contentSelectionKey: "[]",
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
              createElement(
                ReadCacheContext.Provider,
                { value: cache },
                createElement(Harness),
              ),
            ),
          ),
        );
        const node = indexResolved(resolved).moduleAt.get("mod-nested")?.node;
        if (!node) throw new Error("The fixture holder is missing");
        // The optional module renders below the holder before the reset removes it.
        expect(
          indexResolved(resolved).moduleAt.get("mod-optional")?.node.key,
        ).toBe(`${optionalModuleChoice}/0`);
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
        // The reset removes the optional module below the surviving holder, so that group's
        // version entry goes while the holder's and programme B's selections stay.
        expect(after.moduleAt.get("mod-optional")).toBeUndefined();
        expect(reloaded.structure.moduleVersions).toEqual({
          "mod-nested": "sisu-mod-nested",
          "prog-b": "sisu-prog-b",
        });
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

  it("names the containing module when a chosen course moves", async () => {
    (
      globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
    ).IS_REACT_ACT_ENVIRONMENT = true;
    const fixture = chosenCourseFixture();
    expect(
      indexResolved(fixture.resolved).courseAt.get("c-chosen")?.node.kind,
    ).toBe("choice");
    const store = createBrowserStore(localStorage);
    const editor = mountEditor({
      store,
      resolved: fixture.resolved,
      edits: fixture.edits,
      content: fixture.content,
      confirmMoves: () => Promise.resolve(true),
    });
    try {
      await editor.render();
      const home = editor
        .editor()!
        .courseHome("c-chosen", programmeKey("prog-a"), "en");
      expect(home).toBe(moduleName(fixture.labModule, "en"));
    } finally {
      await editor.unmount();
    }
  });

  it("names containing modules in pulled-course confirmations", async () => {
    (
      globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
    ).IS_REACT_ACT_ENVIRONMENT = true;
    const fixture = chosenCourseFixture();
    const targetModule = moduleSummary("mod-target", "TARGET");
    const targetReport = report(targetModule, [
      baseRule({
        all_mandatory: true,
        children: [courseChild("c-chosen", "C-CHOSEN", 0)],
      }),
    ]);
    const progB = report(degreeSummary("prog-b", "PROG-B"), [
      optionalModule(targetReport.root),
    ]);
    const content = contentOf([targetReport, fixture.programme, progB]);
    const tree = buildProgrammeForest([fixture.programme, progB]);
    const resolved = resolveStructure(tree, fixture.edits, content);
    const progBNode = resolved.children.find(
      (child) => child.node.module?.group_id === "prog-b",
    );
    const group = progBNode?.node.ruleGroups.find((item) => !item.required);
    const entry = group?.options[0].entries[0];
    if (!entry || entry.kind !== "node" || !entry.node.module)
      throw new Error("The fixture optional module is missing");
    const store = createBrowserStore(localStorage);
    const placed = resolved.subtree.map((course) => course.group_id);
    store.updateCurrent((state) => ({
      ...state,
      selectedCourseIds: ["c-chosen", "c-kept"],
      completedCourseIds: ["c-kept"],
      structure: {
        programmeGroupIds: ["prog-a", "prog-b"],
        moduleVersions: {},
        ...fixture.edits,
        placedCourseIds: placed,
      },
    }));
    let requested: CourseMoveRequest | null = null;
    let answer: ((value: CourseMoveAnswer) => void) | null = null;
    const editor = mountEditor({
      store,
      resolved,
      edits: fixture.edits,
      content,
      confirmMoves: (request) => {
        requested = request;
        return new Promise<CourseMoveAnswer>((resolve) => {
          answer = resolve;
        });
      },
    });
    try {
      await editor.render();
      const operation = editor
        .editor()!
        .selectRuleModule(entry.node.module, { entry, origin: entry.origin! });
      await until(() => requested !== null, "the module confirmation");
      const source = (requested as CourseMoveRequest | null)?.moves[0];
      expect(source?.from("en")).toBe(moduleName(fixture.labModule, "en"));
      expect(source?.from("fi")).toBe(moduleName(fixture.labModule, "fi"));
      const saved = localStorage.getItem(BROWSER_STORAGE_KEY);
      await act(async () => {
        answer?.(false);
        await operation;
      });
      expect(localStorage.getItem(BROWSER_STORAGE_KEY)).toBe(saved);
      const reloaded = currentState(createBrowserStore(localStorage));
      expect(reloaded.selectedCourseIds).toEqual(["c-chosen", "c-kept"]);
      expect(reloaded.completedCourseIds).toEqual(["c-kept"]);
      expect(editor.editor()!.error).toBeNull();
    } finally {
      await editor.unmount();
    }
  });
});
