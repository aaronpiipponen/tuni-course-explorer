/** Sisu capture: parsed hierarchy, import profile, scoped placement and named omissions. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type {
  CourseSummary,
  ModuleSummary,
  StructureModule,
  StructureRule,
  StudyStructureReport,
} from "../../api/types";
import {
  createBrowserStore,
  parseBrowserImport,
  BROWSER_STORAGE_KEY,
} from "../../state/store";
import type { BrowserState } from "../../state/types";
import { applyStructure } from "./actions";
import {
  buildProgrammeForest,
  indexResolved,
  programmeKey,
  resolveStructure,
  type PlacedContent,
} from "./model";
import { prepareSisuProfile, resolveSisuImport, type SisuPlan } from "./sisu";

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
const moduleSummary = (
  id: string,
  code: string,
  moduleType = "Module",
): ModuleSummary => ({
  group_id: id,
  sisu_module_id: `sisu-${id}`,
  module_type: moduleType,
  code,
  name_fi: null,
  name_en: `${code} module`,
});
const structureModule = (
  summary: ModuleSummary,
  rule: StructureRule,
): StructureModule => ({
  module: summary,
  target_credits_min: null,
  target_credits_max: null,
  rule,
});
const report = (root: StructureModule): StudyStructureReport => ({
  academic_year_start: 2026,
  root,
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
const moduleChild = (node: StructureModule, position: number): StructureRule =>
  baseRule({
    node_type: "ModuleRule",
    sibling_position: position,
    module: node,
  });
const mandatory = (children: StructureRule[]): StructureRule =>
  baseRule({ all_mandatory: true, children });

type MarkupModule = {
  name: string;
  status: string;
  code?: string;
  graduate?: boolean;
  grouping?: boolean;
  info?: boolean;
  children?: readonly string[];
};
const planModule = (options: MarkupModule): string => `<plan-module>
  <div class="header has-header-items">
    <button type="button" class="collapse non-button" aria-expanded="true">-</button>
    <div class="title clickable${options.grouping ? " grouping-module" : ""}">
      <span data-cy="plan-module-name">${options.name}</span>
      ${options.code ? `<span ng-bind=":: $ctrl.module.code">${options.code}</span>` : ""}
    </div>
    ${options.info ? `<button id="module-info-modal-open-${options.code}">i</button>` : ""}
    ${options.graduate ? `<div class="cell graduate">graduation</div>` : ""}
    <div class="cell status status-text"><span id="${options.status}">state</span></div>
  </div>
  ${(options.children ?? []).join("")}
</plan-module>`;
const courseBox = (code: string, name: string, completed: boolean): string =>
  `<course-unit-box>
  <div class="courseunit-top-row">
    <div class="title-box"><span class="courseunit-code">${code}</span> ${name}</div>
  </div>
  ${completed ? "<app-course-unit-attainment-notification></app-course-unit-attainment-notification>" : ""}
</course-unit-box>`;
const captureFile = (
  markup: string,
  lookups: {
    modules: Record<string, string[]>;
    courses: Record<string, { code: string; groupId: string }[]>;
  },
) =>
  JSON.stringify({ type: "tuni-course-explorer/sisu/1", markup, ...lookups });
const parseCapture = (text: string) => {
  const imported = parseBrowserImport(text);
  if (imported.type !== "tuni-course-explorer/sisu/1")
    throw new Error("Expected a Sisu capture import");
  return imported;
};
const currentState = (store: ReturnType<typeof createBrowserStore>) => {
  const snapshot = store.getSnapshot();
  return snapshot.profiles[snapshot.currentProfileId].state;
};
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

describe("Sisu capture import", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => vi.unstubAllGlobals());

  it("imports a capture as a reloadable independent profile with pending choices", () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    const markup = planModule({
      name: "Education in Computer Sciences",
      status: "otm-education-statuscell",
      code: "TIEKO",
      children: [
        planModule({
          name: "Bachelor's Programme",
          status: "otm-bachelor-statuscell",
          code: "TIEK",
          graduate: true,
          info: true,
          children: [
            planModule({
              name: "General studies",
              status: "otm-general-statuscell",
              grouping: true,
              children: [
                courseBox("CS.100", "Programming", true),
                courseBox("CS.101", "Data structures", false),
              ],
            }),
            courseBox("CS.200", "Algorithms", false),
          ],
        }),
        planModule({
          name: "Master's Programme",
          status: "otm-master-statuscell",
          code: "TIM",
          graduate: true,
          info: true,
          children: [courseBox("CS.900", "Thesis", false)],
        }),
      ],
    });
    const capture = parseCapture(
      captureFile(markup, {
        modules: {
          "otm-education-statuscell": [],
          "otm-bachelor-statuscell": ["uta-bachelor"],
          "otm-master-statuscell": ["uta-master"],
          "otm-general-statuscell": [],
        },
        courses: {
          "CS.100": [{ code: "CS.100", groupId: "uta-cs-100" }],
          "CS.101": [{ code: "CS.101", groupId: "uta-cs-101" }],
          "CS.200": [{ code: "cs-200", groupId: "uta-other" }],
          "CS.900": [],
        },
      }),
    );
    const store = createBrowserStore(localStorage);
    store.importProfile(prepareSisuProfile(capture, "Sisu plan", "fi"));
    const reloaded = currentState(createBrowserStore(localStorage));
    expect(reloaded.language).toBe("fi");
    // The education is a container, so only its two degrees become top-level programmes.
    expect(reloaded.structure.programmeGroupIds).toEqual([
      "uta-bachelor",
      "uta-master",
    ]);
    expect(reloaded.selectedCourseIds).toEqual(["uta-cs-100", "uta-cs-101"]);
    expect(reloaded.completedCourseIds).toEqual(["uta-cs-100"]);
    expect(
      reloaded.pendingSisuImport?.programmes.map((item) => item.name),
    ).toEqual(["Bachelor's Programme", "Master's Programme"]);
    expect(reloaded.pendingSisuImport?.programmes[0].children[0].groupId).toBe(
      null,
    );
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("places captured choices in their programme scopes and clears pending atomically", () => {
    const moduleX = structureModule(
      moduleSummary("mod-x", "MOD-X"),
      baseRule({
        require_min: 1,
        require_max: 1,
        all_mandatory: false,
        children: [
          courseChild("c-shared", "C-SHARED", 0),
          courseChild("c-opt", "C-OPT", 1),
        ],
      }),
    );
    const freeSlot = structureModule(
      moduleSummary("free-slot", "FREE-SLOT"),
      baseRule({
        require_min: 0,
        children: [baseRule({ node_type: "AnyModuleRule" })],
      }),
    );
    // The elective is a free choice of the plan, so only its own report holds its content.
    const elective = structureModule(
      moduleSummary("elective", "ELECTIVE"),
      mandatory([
        courseChild("c-elective", "C-ELECTIVE", 0),
        courseChild("c-extra", "C-EXTRA", 1),
      ]),
    );
    const programmeA = report(
      structureModule(
        moduleSummary("prog-a", "PROG-A", "DegreeProgramme"),
        mandatory([
          moduleChild(moduleX, 0),
          moduleChild(freeSlot, 1),
          courseChild("c-main", "C-MAIN", 2),
          courseChild("c-default", "C-DEFAULT", 3),
        ]),
      ),
    );
    const programmeB = report(
      structureModule(
        moduleSummary("prog-b", "PROG-B", "DegreeProgramme"),
        mandatory([
          courseChild("c-shared", "C-SHARED", 0),
          courseChild("c-b2", "C-B2", 1),
          // Programme B also names the elective officially, without capturing it, so the
          // placement programme A gave it must survive B's suppression.
          moduleChild(elective, 2),
        ]),
      ),
    );
    const markup = [
      planModule({
        name: "Programme A",
        status: "otm-a-statuscell",
        code: "PROG-A",
        graduate: true,
        children: [
          planModule({
            name: "Module X",
            status: "otm-x-statuscell",
            code: "MOD-X",
            children: [courseBox("C-SHARED", "Shared course", true)],
          }),
          planModule({
            name: "Free slot",
            status: "otm-free-statuscell",
            code: "FREE-SLOT",
            children: [
              planModule({
                name: "Elective",
                status: "otm-elective-statuscell",
                code: "ELECTIVE",
                children: [courseBox("C-ELECTIVE", "Elective course", false)],
              }),
            ],
          }),
          courseBox("C-MAIN", "Main course", false),
        ],
      }),
      planModule({
        name: "Programme B",
        status: "otm-b-statuscell",
        code: "PROG-B",
        graduate: true,
        children: [courseBox("C-B2", "Second course", false)],
      }),
    ].join("");
    const capture = parseCapture(
      captureFile(markup, {
        modules: {
          "otm-a-statuscell": ["prog-a"],
          "otm-x-statuscell": ["mod-x"],
          "otm-free-statuscell": ["free-slot"],
          "otm-elective-statuscell": ["elective"],
          "otm-b-statuscell": ["prog-b"],
        },
        courses: {
          "C-SHARED": [{ code: "C-SHARED", groupId: "c-shared" }],
          "C-ELECTIVE": [{ code: "C-ELECTIVE", groupId: "c-elective" }],
          "C-MAIN": [{ code: "C-MAIN", groupId: "c-main" }],
          "C-B2": [{ code: "C-B2", groupId: "c-b2" }],
        },
      }),
    );
    const content = contentOf([
      programmeA,
      programmeB,
      report(moduleX),
      report(freeSlot),
      report(elective),
    ]);
    const store = createBrowserStore(localStorage);
    store.importProfile(prepareSisuProfile(capture, "Sisu plan", "en"));
    applyStructure(
      store,
      (state) =>
        resolveSisuImport(state, content, { courseIds: [], moduleIds: [] })
          ?.change ?? null,
    );
    const reloaded = currentState(createBrowserStore(localStorage));
    expect(reloaded.pendingSisuImport).toBeNull();
    expect(reloaded.structure.programmeGroupIds).toEqual(["prog-a", "prog-b"]);
    const forest = buildProgrammeForest([programmeA, programmeB]);
    const projection = resolveStructure(forest, reloaded.structure, content);
    const rendered = indexResolved(projection);
    const shared = rendered.courseAt.get("c-shared");
    expect(shared?.node.kind).toBe("choice");
    expect(reloaded.structure.coursePlacements["c-shared"]).toBe(
      shared?.node.key,
    );
    expect(shared?.node.key.startsWith(programmeKey("prog-a"))).toBe(true);
    expect(rendered.courseAt.has("c-opt")).toBe(false);
    expect(rendered.courseAt.has("c-default")).toBe(false);
    expect(rendered.courseAt.get("c-main")?.node.key).toBe(
      programmeKey("prog-a"),
    );
    expect(rendered.courseAt.get("c-b2")?.node.key).toBe(
      programmeKey("prog-b"),
    );
    // A captured module the programme's rule does not name joins its captured parent, and only
    // the courses the capture holds render inside it.
    const slot = rendered.moduleAt.get("free-slot");
    const added = rendered.moduleAt.get("elective");
    expect(slot).toBeDefined();
    expect(added?.node.key).toBe(`${slot?.node.key}/m:elective`);
    expect(reloaded.structure.modulePlacements["elective"]).toBe(
      slot?.node.key,
    );
    expect(rendered.courseAt.get("c-elective")?.node.key).toBe(added?.node.key);
    expect(rendered.courseAt.has("c-extra")).toBe(false);
    expect(reloaded.structure.placedCourseIds).toEqual(
      projection.subtree.map((course) => course.group_id),
    );
    expect(reloaded.completedCourseIds).toEqual(["c-shared"]);
    expect(reloaded.selectedCourseIds).toContain("c-shared");
    expect(reloaded.selectedCourseIds).toContain("c-elective");
  });

  it("reports unplaceable capture items while retaining representable courses loose", () => {
    const programmeC = report(
      structureModule(
        moduleSummary("prog-c", "PROG-C", "DegreeProgramme"),
        mandatory([courseChild("c-official", "C-OFFICIAL", 0)]),
      ),
    );
    const markup = planModule({
      name: "Programme C",
      status: "otm-c-statuscell",
      code: "PROG-C",
      graduate: true,
      children: [
        planModule({
          name: "Unknown module",
          status: "otm-unknown-statuscell",
          grouping: true,
          children: [courseBox("C-KEPT", "Kept course", true)],
        }),
        planModule({
          name: "Removed module",
          status: "otm-removed-statuscell",
          code: "MOD-GONE",
          children: [courseBox("C-ABSENT", "Absent course", false)],
        }),
        courseBox("C-NULL", "No identity", false),
      ],
    });
    const capture = parseCapture(
      captureFile(markup, {
        modules: {
          "otm-c-statuscell": ["prog-c"],
          "otm-unknown-statuscell": [],
          "otm-removed-statuscell": ["mod-gone"],
        },
        courses: {
          "C-KEPT": [{ code: "C-KEPT", groupId: "c-kept" }],
          "C-ABSENT": [{ code: "C-ABSENT", groupId: "c-absent" }],
          "C-NULL": [],
        },
      }),
    );
    const content = contentOf(
      [programmeC],
      [courseSummary("c-kept", "C-KEPT")],
    );
    const store = createBrowserStore(localStorage);
    store.importProfile(prepareSisuProfile(capture, "Partial plan", "en"));
    const profileState = currentState(store);
    const resolved = resolveSisuImport(profileState, content, {
      courseIds: ["c-absent"],
      moduleIds: ["mod-gone"],
    });
    expect(resolved?.issues).toEqual([
      { name: "Unknown module", code: null, reason: "unresolved" },
      { name: "Removed module", code: "MOD-GONE", reason: "module_not_placed" },
      {
        name: "Absent course",
        code: "C-ABSENT",
        reason: "course_not_represented",
      },
      { name: "No identity", code: "C-NULL", reason: "unresolved" },
    ]);
    applyStructure(
      store,
      (state) =>
        resolveSisuImport(state, content, {
          courseIds: ["c-absent"],
          moduleIds: ["mod-gone"],
        })?.change ?? null,
    );
    const reloaded = currentState(createBrowserStore(localStorage));
    expect(reloaded.pendingSisuImport).toBeNull();
    expect(reloaded.structure.programmeGroupIds).toEqual(["prog-c"]);
    expect(reloaded.completedCourseIds).toEqual(["c-kept"]);
    expect(reloaded.selectedCourseIds).toEqual(["c-kept"]);
    const projection = resolveStructure(
      buildProgrammeForest([programmeC]),
      reloaded.structure,
      content,
    );
    const rendered = indexResolved(projection);
    expect(rendered.courseAt.get("c-kept")?.node.kind).toBe("unplaced");
    expect(rendered.courseAt.has("c-absent")).toBe(false);
    expect(rendered.courseAt.has("c-official")).toBe(false);
  });

  it("preserves restored edits and course sets when a Sisu capture is waiting", () => {
    const programme = report(
      structureModule(
        moduleSummary("prog-p", "PROG-P", "DegreeProgramme"),
        mandatory([courseChild("c-official", "C-OFFICIAL", 0)]),
      ),
    );
    const capture: SisuPlan = {
      programmes: [
        {
          kind: "module",
          groupId: "prog-p",
          versionId: "sisu-prog-p",
          code: "PROG-P",
          name: "Programme P",
          children: [],
        },
      ],
    };
    // The prepared capture owns the programme list, its version and its pending hierarchy alone.
    const prepared = prepareSisuProfile(capture, "Restored plan", "fi");
    const state = prepared.state;
    state.selectedCourseIds = ["c-unplaced", "c-completed"];
    state.completedCourseIds = ["c-completed"];
    state.search = { ...state.search, query: "restored query" };
    state.structure.programmeGroupIds = ["prog-p"];
    state.structure.choices = { "p:prog-p/1": ["p:prog-p/1/0"] };
    state.structure.coursePlacements = { "c-official": null };
    state.structure.modulePlacements = { "mod-removed": null };
    state.structure.placedCourseIds = ["c-unplaced"];
    const envelope: BrowserState = {
      schemaVersion: 3,
      currentProfileId: "default",
      profiles: { default: { name: "Restored plan", state } },
    };
    const imported = parseBrowserImport(
      JSON.stringify({
        type: "tuni-course-explorer/state/3",
        data: JSON.stringify(envelope),
      }),
    );
    if (imported.type !== "tuni-course-explorer/state/3")
      throw new Error("Expected a state import");
    const store = createBrowserStore(localStorage);
    store.restoreState(imported.state);
    const restored = store.getSnapshot();
    const raw = localStorage.getItem(BROWSER_STORAGE_KEY);
    // Settled content makes the resolver reach its placement, so a lost edit is a real loss.
    const content = contentOf(
      [programme],
      [
        courseSummary("c-unplaced", "C-UNPLACED"),
        courseSummary("c-completed", "C-COMPLETED"),
      ],
    );
    for (const id of state.selectedCourseIds)
      expect(content.courses.has(id)).toBe(true);
    expect(content.reports["prog-p"]).toBe(programme);
    applyStructure(
      store,
      (current) =>
        resolveSisuImport(current, content, {
          courseIds: [],
          moduleIds: [],
        })?.change ?? null,
    );
    expect(store.getSnapshot()).toEqual(restored);
    expect(localStorage.getItem(BROWSER_STORAGE_KEY)).toBe(raw);
    const reloaded = createBrowserStore(localStorage);
    expect(reloaded.getSnapshot()).toEqual(restored);
    const reloadedState = currentState(reloaded);
    expect(reloadedState.pendingSisuImport).toEqual(capture);
    expect(reloadedState.selectedCourseIds).toContain("c-unplaced");
  });
});
