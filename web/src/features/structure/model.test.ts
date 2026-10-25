/** Choice resolution and single placement in the pure projection. */
import { describe, expect, it } from "vitest";
import type {
  CourseSummary,
  StructureRule,
  StudyStructureReport,
} from "../../api/types";
import {
  buildStructure,
  nextChoices,
  resolveStructure,
  NO_CONTENT,
  officialHomes,
  indexResolved,
  type StructureEntry,
} from "./model";
import { emptyEdits } from "./state";
import { resetScope } from "./edits";
import { uiText } from "../../shared/wording";
import { displayContents } from "./display";

const course = (id: string, active = true): CourseSummary => ({
  group_id: id,
  name_fi: id,
  name_en: id,
  code: id,
  credits_min: "5.00",
  credits_max: null,
  is_active: active,
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
  referenced_group_id: null,
  children: [],
  course: null,
  module: null,
  unresolved: null,
  ...fields,
});
const moduleSummary = {
  group_id: "root",
  sisu_module_id: "root",
  module_type: "DegreeProgramme",
  code: "ROOT",
  name_fi: "Root",
  name_en: "Root",
};

describe("structure projection", () => {
  it("projects rule trees into rows and resolves only chosen content, placing each course once", () => {
    for (const language of ["en", "fi"] as const) {
      const repeated = course("repeat", false);
      const module = {
        ...moduleSummary,
        group_id: "nested",
        module_type: "StudyModule",
        code: "NEST",
        name_fi: "Nested",
        name_en: "Nested",
      };
      const nested = {
        module,
        target_credits_min: null,
        target_credits_max: null,
        rule: rule("CompositeRule", 0, {
          all_mandatory: true,
          children: [rule("CourseUnitRule", 0, { course: repeated })],
        }),
      };
      const mandatory = rule("CompositeRule", 0, {
        all_mandatory: false,
        require_min: 4,
        require_max: null,
        children: [
          rule("CourseUnitRule", 0, { course: repeated }),
          rule("ModuleRule", 1, { module: nested }),
          rule("AnyCourseUnitRule", 2),
          rule("ModuleRule", 3, { unresolved: "module_not_found" }),
        ],
      });
      const oneChoice = rule("CompositeRule", 1, {
        require_min: 1,
        require_max: 1,
        children: [
          rule("ModuleRule", 0, { module: nested }),
          rule("ModuleRule", 1, { module: nested }),
        ],
      });
      const credits = rule("CreditsRule", 2, {
        credits_min: "10",
        children: [
          rule("CompositeRule", 0, {
            all_mandatory: false,
            require_min: 1,
            require_max: null,
            children: [
              rule("CourseUnitRule", 0, { course: course("credit-a") }),
              rule("CourseUnitRule", 1, { course: course("credit-b") }),
            ],
          }),
        ],
      });
      const root: StudyStructureReport["root"] = {
        module: moduleSummary,
        target_credits_min: null,
        target_credits_max: null,
        rule: rule("CompositeRule", 0, {
          all_mandatory: true,
          children: [mandatory, oneChoice, credits],
        }),
      };
      const tree = buildStructure(
        { academic_year_start: 2026, root },
        "r",
        language,
      );
      const empty = resolveStructure(tree, emptyEdits(), NO_CONTENT, language);
      expect(tree.kind).toBe("module");
      expect(tree.rule).toBe(uiText(language, "all required"));
      expect(empty.subtree.map((item) => item.group_id)).toEqual(["repeat"]);
      const displayed = displayContents(empty);
      expect(displayed.notes).toEqual([uiText(language, "Module not found")]);
      expect(
        displayed.children.every((child) => child.node.kind !== "choice"),
      ).toBe(true);
      expect(tree.ruleGroups.some((group) => group.key === "r/1")).toBe(true);
      expect(tree.ruleGroups.some((group) => group.key === "r/2")).toBe(true);
      expect(
        tree.ruleGroups.find((group) => group.key === "r/0"),
      ).toMatchObject({
        required: true,
        requiredCount: 3,
      });
      expect(tree.entries[0]).toMatchObject({
        kind: "node",
        node: { key: "r/0", kind: "group", transparent: true },
      });
      const requiredHome = officialHomes(tree, emptyEdits(), NO_CONTENT).get(
        "repeat",
      )?.[0];
      expect(requiredHome).toBe("r/0");
      expect(
        resolveStructure(
          tree,
          { ...emptyEdits(), coursePlacements: { repeat: null } },
          NO_CONTENT,
          language,
        ).subtree,
      ).toEqual([]);
      expect(
        resolveStructure(
          tree,
          {
            ...emptyEdits(),
            coursePlacements: { repeat: requiredHome! },
          },
          NO_CONTENT,
          language,
        ).subtree.map((item) => item.group_id),
      ).toEqual(["repeat"]);
      const choice = tree.entries.find(
        (entry) => entry.kind === "node" && entry.node.kind === "choice",
      );
      expect(choice?.kind).toBe("node");
      if (choice?.kind !== "node") throw new Error("Expected choice node");
      expect(choice.node.title).toBe(
        uiText(language, "Modules to choose from: {count}", { count: 2 }),
      );
      expect(choice.node.key).toBe("r/1");
      const picked = nextChoices({}, choice.node, choice.node.options[1].key);
      expect(
        nextChoices(picked, choice.node, choice.node.options[0].key)[
          choice.node.key
        ],
      ).toEqual([choice.node.options[0].key]);
      expect(
        nextChoices(picked, choice.node, choice.node.options[1].key)[
          choice.node.key
        ],
      ).toEqual([choice.node.options[1].key]);
      const multi = tree.entries.find(
        (entry) =>
          entry.kind === "node" &&
          entry.node.kind === "choice" &&
          entry.node.key === "r/2",
      );
      if (multi?.kind !== "node") throw new Error("Expected credit choice");
      const toggled = nextChoices(
        nextChoices({}, multi.node, multi.node.options[0].key),
        multi.node,
        multi.node.options[1].key,
      );
      expect(toggled[multi.node.key]).toHaveLength(2);
      expect(
        resolveStructure(
          tree,
          {
            ...emptyEdits(),
            choices: { [choice.node.key]: [choice.node.options[1].key] },
          },
          NO_CONTENT,
          language,
        ).subtree.map((item) => item.group_id),
      ).toEqual(["repeat"]);
      const selectedChoice = resolveStructure(
        tree,
        {
          ...emptyEdits(),
          choices: { [choice.node.key]: [choice.node.options[1].key] },
        },
        NO_CONTENT,
        language,
      ).children.find((node) => node.node.key === choice.node.key);
      expect(selectedChoice?.children).toEqual([]);
      const selectedCredit = resolveStructure(
        tree,
        {
          ...emptyEdits(),
          choices: { [multi.node.key]: [multi.node.options[0].key] },
        },
        NO_CONTENT,
        language,
      ).children.find((node) => node.node.key === multi.node.key);
      expect(
        selectedCredit?.courses.map(({ course: item }) => item.group_id),
      ).toEqual(["credit-a"]);
      expect(
        tree.ruleGroups.find((group) => group.key === multi.node.key),
      ).toMatchObject({
        required: false,
        options: multi.node.options,
      });
      const wrapperReport: StudyStructureReport = {
        academic_year_start: 2026,
        root: {
          module: moduleSummary,
          target_credits_min: "20",
          target_credits_max: null,
          rule: rule("CreditsRule", 3, {
            credits_min: "20",
            children: [
              rule("CompositeRule", 0, {
                all_mandatory: false,
                require_min: 0,
                require_max: null,
                children: [oneChoice],
              }),
            ],
          }),
        },
      };
      const wrapperTree = buildStructure(wrapperReport, "r", language);
      const wrapperChoice = resolveStructure(
        wrapperTree,
        emptyEdits(),
        NO_CONTENT,
        language,
      ).children.find((child) => child.node.key === "r/3");
      expect(wrapperChoice?.chosen).toHaveLength(1);
      expect(wrapperChoice?.children[0].node.kind).toBe("choice");
      expect(wrapperChoice?.children[0].chosen).toEqual([]);
      expect(wrapperTree.ruleGroups.map((group) => group.key)).toContain(
        "r/3/1",
      );
      const storedWrapperChoice = resolveStructure(
        wrapperTree,
        { ...emptyEdits(), choices: { "r/3": [] } },
        NO_CONTENT,
        language,
      ).children.find((child) => child.node.key === "r/3");
      expect(storedWrapperChoice?.children[0].node.key).toBe("r/3/1");
      const customModule = {
        ...moduleSummary,
        group_id: "custom-module",
        module_type: "StudyModule",
      };
      const choicePlacement = resolveStructure(
        tree,
        {
          ...emptyEdits(),
          coursePlacements: { custom: choice.node.key },
          modulePlacements: { "custom-module": choice.node.key },
        },
        {
          reports: {
            "custom-module": {
              academic_year_start: 2026,
              root: {
                module: customModule,
                target_credits_min: null,
                target_credits_max: null,
                rule: rule("CompositeRule", 0, { all_mandatory: true }),
              },
            },
          },
          courses: new Map([["custom", course("custom")]]),
        },
        language,
      );
      const resolvedChoice = choicePlacement.children.find(
        (node) => node.node.key === choice.node.key,
      );
      expect(resolvedChoice?.courses).toEqual([]);
      expect(resolvedChoice?.children).toEqual([]);

      const bundleChoice = buildStructure(
        {
          academic_year_start: 2026,
          root: {
            module: moduleSummary,
            target_credits_min: null,
            target_credits_max: null,
            rule: rule("CompositeRule", 0, {
              require_min: 0,
              require_max: 1,
              children: [
                rule("CompositeRule", 0, {
                  require_min: 2,
                  require_max: 2,
                  children: [
                    rule("CourseUnitRule", 0, { course: course("bundle-a") }),
                    rule("CourseUnitRule", 1, { course: course("bundle-b") }),
                  ],
                }),
              ],
            }),
          },
        },
        "r",
        language,
      );
      const findChoice = (
        entries: StructureEntry[],
      ): Extract<StructureEntry, { kind: "node" }> | undefined => {
        for (const entry of entries) {
          if (entry.kind !== "node") continue;
          if (entry.node.kind === "choice") return entry;
          const nestedChoice = findChoice(entry.node.entries);
          if (nestedChoice) return nestedChoice;
        }
        return undefined;
      };
      const sourceChoice = findChoice(bundleChoice.entries);
      if (!sourceChoice || sourceChoice.node.kind !== "choice")
        throw new Error("Expected source choice");
      const sourceBundle = sourceChoice.node.options[0].entries[0];
      if (sourceBundle.kind !== "node")
        throw new Error("Expected transparent bundle");
      const sourceLeaves = sourceBundle.node.entries.filter(
        (
          entry,
        ): entry is Extract<StructureEntry, { kind: "course" | "node" }> =>
          entry.kind === "course" || entry.kind === "node",
      );
      expect(sourceLeaves.map((entry) => entry.origin)).toEqual([
        {
          ownerKey: sourceBundle.node.key,
          choicePath: [
            {
              node: sourceChoice.node,
              optionKey: sourceChoice.node.options[0].key,
            },
          ],
        },
        {
          ownerKey: sourceBundle.node.key,
          choicePath: [
            {
              node: sourceChoice.node,
              optionKey: sourceChoice.node.options[0].key,
            },
          ],
        },
      ]);
      const selectedBundle = resolveStructure(
        bundleChoice,
        {
          ...emptyEdits(),
          choices: {
            [sourceChoice.node.key]: [sourceChoice.node.options[0].key],
          },
        },
        NO_CONTENT,
        language,
      );
      const ownership = indexResolved(selectedBundle);
      expect(ownership.courseAt.get("bundle-a")?.node.key).toBe(
        sourceLeaves[0].origin?.ownerKey,
      );
      expect(ownership.courseAt.get("bundle-b")?.node.key).toBe(
        sourceLeaves[1].origin?.ownerKey,
      );
    }
  });

  it("resolves placements: moves, removals, restores and added modules render each course and module once", () => {
    const moving = course("moving");
    const module = {
      ...moduleSummary,
      group_id: "nested",
      module_type: "StudyModule",
      code: "NEST",
    };
    const extraModule = {
      ...moduleSummary,
      group_id: "extra",
      module_type: "StudyModule",
      code: "EXTRA",
    };
    const nestedReport: StudyStructureReport = {
      academic_year_start: 2026,
      root: {
        module: extraModule,
        target_credits_min: null,
        target_credits_max: null,
        rule: rule("CompositeRule", 0, {
          all_mandatory: true,
          children: [
            rule("CourseUnitRule", 0, { course: course("nested-course") }),
          ],
        }),
      },
    };
    const rootReport: StudyStructureReport = {
      academic_year_start: 2026,
      root: {
        module: moduleSummary,
        target_credits_min: null,
        target_credits_max: null,
        rule: rule("CompositeRule", 0, {
          all_mandatory: true,
          children: [
            rule("CourseUnitRule", 0, { course: moving }),
            rule("ModuleRule", 1, {
              module: {
                module,
                target_credits_min: null,
                target_credits_max: null,
                rule: nestedReport.root.rule,
              },
            }),
            rule("ModuleRule", 2, {
              module: {
                module,
                target_credits_min: null,
                target_credits_max: null,
                rule: nestedReport.root.rule,
              },
            }),
          ],
        }),
      },
    };
    const tree = buildStructure(rootReport);
    const content = {
      reports: { extra: nestedReport },
      courses: new Map([["moving", moving]]),
    };
    const movedEdits = {
      ...emptyEdits(),
      coursePlacements: { moving: "r/1" },
      modulePlacements: { extra: "r" },
    };
    const moved = resolveStructure(tree, movedEdits, content);
    expect(
      moved.children.filter(
        (child) => child.node.module?.group_id === "nested",
      ),
    ).toHaveLength(1);
    expect(moved.children[0].courses).toEqual([
      { course: course("nested-course"), added: false },
      { course: moving, added: true },
    ]);
    expect(moved.courses).toEqual([]);
    expect(moved.removed).toEqual([{ kind: "course", course: moving }]);
    expect(
      moved.children.some(
        (child) => child.node.key === "r/m:extra" && child.added,
      ),
    ).toBe(true);
    expect(moved.subtree.map((item) => item.group_id)).toEqual([
      "nested-course",
      "moving",
    ]);
    expect(officialHomes(tree, movedEdits, content).get("moving")).toEqual([
      "r",
    ]);

    const removed = resolveStructure(
      tree,
      { ...emptyEdits(), coursePlacements: { moving: null } },
      NO_CONTENT,
    );
    expect(removed.subtree.map((item) => item.group_id)).toEqual([
      "nested-course",
    ]);
    expect(removed.removed).toEqual([{ kind: "course", course: moving }]);
    const restored = resolveStructure(
      tree,
      { ...emptyEdits(), coursePlacements: { moving: "r" } },
      NO_CONTENT,
    );
    expect(restored.courses).toEqual([{ course: moving, added: false }]);
    expect(restored.removed).toEqual([]);
  });

  it("excludes version requirements from references outside the selected plan", () => {
    const wrapper = {
      ...moduleSummary,
      group_id: "wrapper",
      sisu_module_id: "wrapper-v1",
      module_type: "StudyModule",
      code: "WRAPPER",
    };
    const tree = buildStructure({
      academic_year_start: 2026,
      root: {
        module: moduleSummary,
        target_credits_min: null,
        target_credits_max: null,
        rule: rule("CompositeRule", 0, {
          all_mandatory: true,
          children: [
            rule("CompositeRule", 0, {
              all_mandatory: false,
              require_min: 0,
              require_max: null,
              children: [
                rule("ModuleRule", 0, {
                  module: {
                    module: wrapper,
                    target_credits_min: null,
                    target_credits_max: null,
                    rule: rule("CompositeRule", 0, {
                      all_mandatory: true,
                      children: [
                        rule("ModuleRule", 0, {
                          referenced_group_id: "child",
                          unresolved: "ambiguous_version",
                        }),
                      ],
                    }),
                  },
                }),
              ],
            }),
          ],
        }),
      },
    });
    const choiceEntry = tree.entries[0];
    if (choiceEntry.kind !== "node")
      throw new Error("Expected the optional choice");
    const choice = choiceEntry.node;
    expect(choice.kind).toBe("choice");
    expect(choice.single).toBe(false);
    expect(
      resolveStructure(tree, emptyEdits(), NO_CONTENT)
        .versionSelectionRequiredIds,
    ).toEqual([]);

    const optionKey = choice.options[0].key;
    const selectedChoices = nextChoices({}, choice, optionKey);
    expect(selectedChoices[choice.key]).toEqual([optionKey]);
    const selectedEdits = { ...emptyEdits(), choices: selectedChoices };
    const selected = resolveStructure(tree, selectedEdits, NO_CONTENT);
    expect(selected.versionSelectionRequiredIds).toEqual(["child"]);
    const wrapperEntry = choice.options[0].entries[0];
    if (wrapperEntry.kind !== "node")
      throw new Error("Expected the wrapper node");
    expect(
      indexResolved(selected).byKey.get(wrapperEntry.node.key)?.notes,
    ).toEqual([uiText("en", "Several current versions of this module")]);

    const deselectedChoices = nextChoices(selectedChoices, choice, optionKey);
    expect(deselectedChoices[choice.key]).toEqual([]);
    const removals = [
      { ...selectedEdits, modulePlacements: { wrapper: null } },
      // A placement names the containing node, so the wrapper's own node excludes it instead.
      {
        ...selectedEdits,
        modulePlacements: { wrapper: wrapperEntry.node.key },
      },
      { ...selectedEdits, choices: deselectedChoices },
      resetScope(
        selectedEdits,
        officialHomes(tree, selectedEdits, NO_CONTENT),
        tree.key,
      ),
    ];
    for (const edits of removals)
      expect(
        resolveStructure(tree, edits, NO_CONTENT).versionSelectionRequiredIds,
      ).toEqual([]);
  });
});
