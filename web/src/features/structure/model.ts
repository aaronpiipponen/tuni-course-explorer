/** Pure browser projection of the official rule AST. No rule satisfaction is inferred. */
import type {
  CourseSummary,
  DisplayLanguage,
  StructureModule as ApiModule,
  StructureRule,
  StudyStructureReport,
} from "../../api/types";
import type { StructureChoices, StructureEdits } from "./state";
import { UNPLACED_KEY } from "./state";
import { reasonText, uiText, type UiTextKey } from "../../shared/wording";

export type StructureChoiceStep = { node: StructureNode; optionKey: string };
export type StructureRuleOrigin = {
  ownerKey: string;
  choicePath: readonly StructureChoiceStep[];
};
export type StructureRuleItem = {
  entry: Extract<StructureEntry, { kind: "course" | "node" }>;
  origin: StructureRuleOrigin;
};
export type StructureEntry =
  | {
      kind: "course";
      key: string;
      course: CourseSummary;
      origin?: StructureRuleOrigin;
    }
  | { kind: "node"; node: StructureNode; origin?: StructureRuleOrigin }
  | { kind: "note"; key: string; text: string };
export type StructureOption = { key: string; entries: StructureEntry[] };
export type StructureRuleGroup = {
  key: string;
  rule: string;
  required: boolean;
  requiredCount: number;
  requiredCredits: number | null;
  choiceNode: StructureNode | null;
  options: StructureOption[];
};
export type StructureNode = {
  key: string;
  kind: "programme" | "module" | "choice" | "group" | "unplaced";
  transparent: boolean;
  module: ApiModule["module"] | null;
  rule: string;
  title: string | null;
  entries: StructureEntry[];
  options: StructureOption[];
  ruleGroups: StructureRuleGroup[];
  single: boolean;
  autoSelectSingleWrapper: boolean;
};
export type ResolvedNode = {
  node: StructureNode;
  courses: PlacedCourse[];
  notes: string[];
  children: ResolvedNode[];
  chosen: StructureOption[];
  subtree: CourseSummary[];
  added: boolean;
  removed: RemovedEntry[];
};
export type PlacedCourse = { course: CourseSummary; added: boolean };
export type RemovedEntry =
  | { kind: "course"; course: CourseSummary }
  | { kind: "module"; module: ApiModule["module"] };
export type PlacedContent = {
  reports: Readonly<Record<string, StudyStructureReport>>;
  courses: ReadonlyMap<string, CourseSummary>;
};
export const NO_CONTENT: PlacedContent = { reports: {}, courses: new Map() };

function range(
  min: number | null,
  max: number | null,
  unit: "credits" | "courses",
  language: DisplayLanguage,
): string {
  const credits = unit === "credits";
  if (min === null && max === null)
    return uiText(language, credits ? "any cr" : "any courses");
  if (min !== null && max !== null)
    return min === max
      ? uiText(language, credits ? "{value} cr" : "{value} courses", {
          value: min,
        })
      : uiText(language, credits ? "{min}–{max} cr" : "{min}–{max} courses", {
          min,
          max,
        });
  if (min === null)
    return uiText(
      language,
      credits ? "up to {value} cr" : "up to {value} courses",
      {
        value: max!,
      },
    );
  return uiText(language, credits ? "min {value} cr" : "min {value} courses", {
    value: min,
  });
}
export function ruleLabel(
  rule: StructureRule,
  language: DisplayLanguage,
): string {
  if (rule.node_type === "CompositeRule") {
    if (rule.all_mandatory) return uiText(language, "all required");
    const min = rule.require_min,
      max = rule.require_max;
    if (min !== null && max !== null)
      return min === max
        ? uiText(language, "choose {count}", { count: min })
        : uiText(language, "choose {min}–{max}", { min, max });
    if (min !== null && min > 0)
      return uiText(language, "choose at least {count}", { count: min });
    if (min === 0 && max !== null)
      return uiText(language, "choose up to {count}", { count: max });
    if (max !== null)
      return uiText(language, "choose up to {count}", { count: max });
    return "";
  }
  if (rule.node_type === "CreditsRule")
    return range(
      rule.credits_min === null ? null : Number(rule.credits_min),
      rule.credits_max === null ? null : Number(rule.credits_max),
      "credits",
      language,
    );
  if (rule.node_type === "CourseUnitCountRule")
    return range(rule.count_min, rule.count_max, "courses", language);
  if (rule.node_type === "AnyCourseUnitRule")
    return uiText(language, "any course");
  if (rule.node_type === "AnyModuleRule") return uiText(language, "any module");
  if (rule.node_type === "CourseUnitRule" || rule.node_type === "ModuleRule")
    return uiText(language, "required");
  throw new Error("Unsupported structure rule type");
}
function joinLabels(
  outer: StructureRule,
  inner: StructureRule,
  language: DisplayLanguage,
): string {
  return [ruleLabel(outer, language), ruleLabel(inner, language)]
    .filter(Boolean)
    .join(" · ");
}
function moduleNode(
  module: ApiModule,
  key: string,
  language: DisplayLanguage,
  ruleKey = key,
): StructureNode {
  const isProgramme = module.module.module_type === "DegreeProgramme";
  const target =
    module.target_credits_min !== null || module.target_credits_max !== null
      ? range(
          module.target_credits_min === null
            ? null
            : Number(module.target_credits_min),
          module.target_credits_max === null
            ? null
            : Number(module.target_credits_max),
          "credits",
          language,
        )
      : module.rule.node_type === "AnyCourseUnitRule" ||
          module.rule.node_type === "AnyModuleRule"
        ? ""
        : ruleLabel(module.rule, language);
  const ruleGroups: StructureRuleGroup[] = [];
  const entries = project(module.rule, ruleKey, ruleGroups, key, [], language);
  if (
    ruleGroups.length === 0 &&
    entries.length > 0 &&
    (module.rule.node_type === "CourseUnitRule" ||
      module.rule.node_type === "ModuleRule")
  ) {
    const options = requiredRuleOptions(entries);
    if (options.length > 0)
      ruleGroups.push({
        key: ruleKey,
        rule: ruleLabel(module.rule, language),
        required: true,
        requiredCount: options.length,
        requiredCredits: null,
        choiceNode: null,
        options,
      });
  }
  return {
    key,
    kind: isProgramme ? "programme" : "module",
    transparent: false,
    module: module.module,
    rule: target,
    title: null,
    entries,
    options: [],
    ruleGroups,
    single: false,
    autoSelectSingleWrapper: false,
  };
}
function requiredRuleOptions(entries: StructureEntry[]): StructureOption[] {
  return entries.flatMap((entry) => {
    if (entry.kind === "node" && entry.node.transparent)
      return requiredRuleOptions(entry.node.entries);
    if (entry.kind === "node" && entry.node.kind === "choice") return [];
    return [
      {
        key: entry.kind === "node" ? entry.node.key : entry.key,
        entries: [entry],
      },
    ];
  });
}
function hasSelectableRuleEntries(entries: readonly StructureEntry[]): boolean {
  return entries.some((entry) => {
    if (entry.kind === "course" || entry.kind === "note") return true;
    if (entry.node.transparent)
      return hasSelectableRuleEntries(entry.node.entries);
    return entry.node.kind !== "choice";
  });
}
function project(
  rule: StructureRule,
  key: string,
  ruleGroups: StructureRuleGroup[],
  ownerKey: string,
  choicePath: readonly StructureChoiceStep[],
  language: DisplayLanguage,
): StructureEntry[] {
  const origin = { ownerKey, choicePath };
  const childKey = (child: StructureRule) => `${key}/${child.sibling_position}`;
  const group = (
    entries: StructureEntry[],
    label: string,
  ): StructureEntry[] => [
    {
      kind: "node",
      node: {
        key,
        kind: "group",
        transparent: true,
        module: null,
        rule: label,
        title: null,
        entries,
        options: [],
        ruleGroups: [],
        single: false,
        autoSelectSingleWrapper: false,
      },
    },
  ];
  if (rule.node_type === "CourseUnitRule")
    return rule.course
      ? [{ kind: "course", key, course: rule.course, origin }]
      : [
          {
            kind: "note",
            key,
            text: reasonText(
              rule.unresolved ?? "course_not_represented",
              language,
            ),
          },
        ];
  if (rule.node_type === "ModuleRule")
    return rule.module
      ? [
          {
            kind: "node",
            node: moduleNode(
              rule.module,
              key,
              language,
              `${key}/${rule.module.rule.sibling_position}`,
            ),
            origin,
          },
        ]
      : [
          {
            kind: "note",
            key,
            text: reasonText(rule.unresolved ?? "module_not_found", language),
          },
        ];
  if (
    rule.node_type === "AnyCourseUnitRule" ||
    rule.node_type === "AnyModuleRule"
  )
    return [];
  if (rule.node_type === "CompositeRule" && rule.all_mandatory) {
    const nestedGroups: StructureRuleGroup[] = [];
    const projected = rule.children.map((child) =>
      project(
        child,
        childKey(child),
        nestedGroups,
        ownerKey,
        choicePath,
        language,
      ),
    );
    const options = projected.flatMap(requiredRuleOptions);
    if (options.length > 0)
      ruleGroups.push({
        key,
        rule: ruleLabel(rule, language),
        required: true,
        requiredCount: options.length,
        requiredCredits: null,
        choiceNode: null,
        options,
      });
    ruleGroups.push(...nestedGroups);
    return projected.flat();
  }
  if (
    rule.node_type === "CompositeRule" &&
    rule.children.length > 0 &&
    rule.require_min === rule.children.length &&
    (rule.require_max === null || rule.require_max >= rule.children.length)
  ) {
    const nestedGroups: StructureRuleGroup[] = [];
    const projected = rule.children.map((child) => ({
      key: childKey(child),
      entries: project(
        child,
        childKey(child),
        nestedGroups,
        key,
        choicePath,
        language,
      ),
    }));
    const options = projected.flatMap((option) =>
      requiredRuleOptions(option.entries),
    );
    if (options.length > 0)
      ruleGroups.push({
        key,
        rule: ruleLabel(rule, language),
        required: true,
        requiredCount: options.length,
        requiredCredits: null,
        choiceNode: null,
        options,
      });
    ruleGroups.push(...nestedGroups);
    return group(
      projected.flatMap((option) => option.entries),
      ruleLabel(rule, language),
    );
  }
  if (
    (rule.node_type === "CreditsRule" ||
      rule.node_type === "CourseUnitCountRule") &&
    rule.children.length === 1
  ) {
    const only = rule.children[0];
    const positive =
      rule.node_type === "CreditsRule"
        ? rule.credits_min !== null && Number(rule.credits_min) > 0
        : rule.count_min !== null && rule.count_min > 0;
    if (positive && only.node_type === "CompositeRule" && only.all_mandatory) {
      const nestedGroups: StructureRuleGroup[] = [];
      const entries = only.children.flatMap((child) =>
        project(
          child,
          `${childKey(only)}/${child.sibling_position}`,
          nestedGroups,
          key,
          choicePath,
          language,
        ),
      );
      const options = requiredRuleOptions(entries);
      if (options.length > 0)
        ruleGroups.push({
          key,
          rule: ruleLabel(rule, language),
          required: true,
          requiredCount: options.length,
          requiredCredits:
            rule.node_type === "CreditsRule" && rule.credits_min !== null
              ? Number(rule.credits_min)
              : null,
          choiceNode: null,
          options,
        });
      ruleGroups.push(...nestedGroups);
      return group(entries, ruleLabel(rule, language));
    }
    if (
      positive &&
      only.node_type === "CompositeRule" &&
      !only.all_mandatory &&
      only.children.length === 1 &&
      (only.require_min === 0 || only.require_min === 1) &&
      (only.require_max === null || only.require_max >= 1) &&
      only.children[0].node_type === "CompositeRule" &&
      only.children[0].all_mandatory
    ) {
      const bundle = only.children[0];
      const nestedGroups: StructureRuleGroup[] = [];
      const entries = bundle.children.flatMap((child) =>
        project(
          child,
          `${childKey(bundle)}/${child.sibling_position}`,
          nestedGroups,
          key,
          choicePath,
          language,
        ),
      );
      const options = requiredRuleOptions(entries);
      if (options.length > 0)
        ruleGroups.push({
          key,
          rule: ruleLabel(rule, language),
          required: true,
          requiredCount: options.length,
          requiredCredits:
            rule.node_type === "CreditsRule" && rule.credits_min !== null
              ? Number(rule.credits_min)
              : null,
          choiceNode: null,
          options,
        });
      ruleGroups.push(...nestedGroups);
      return group(entries, joinLabels(rule, only, language));
    }
  }
  if (
    rule.node_type === "CompositeRule" ||
    rule.node_type === "CreditsRule" ||
    rule.node_type === "CourseUnitCountRule"
  ) {
    let optionRule = rule;
    let label = ruleLabel(rule, language);
    if (
      (rule.node_type === "CreditsRule" ||
        rule.node_type === "CourseUnitCountRule") &&
      rule.children.length === 1 &&
      rule.children[0].node_type === "CompositeRule" &&
      !rule.children[0].all_mandatory
    ) {
      optionRule = rule.children[0];
      label = joinLabels(rule, optionRule, language);
    }
    const nestedGroups: StructureRuleGroup[] = [];
    const options = optionRule.children
      .map((child) => ({
        key: childKey(child),
        entries: project(
          child,
          childKey(child),
          nestedGroups,
          key,
          choicePath,
          language,
        ),
      }))
      .filter((option) => option.entries.length > 0);
    const allCourse =
      options.length > 0 &&
      options.every((option) =>
        option.entries.every((entry) => entry.kind === "course"),
      );
    const allModules =
      options.length > 0 &&
      options.every((option) =>
        option.entries.every(
          (entry) => entry.kind === "node" && entry.node.kind === "module",
        ),
      );
    const titleKey: UiTextKey = allCourse
      ? "Choose from {count} courses"
      : allModules
        ? "Choose from {count} modules"
        : "Choose from {count} options";
    const autoSelectSingleWrapper =
      options.length === 1 &&
      options[0].entries.length === 1 &&
      options[0].entries[0].kind === "node" &&
      options[0].entries[0].node.kind === "choice";
    const node: StructureNode = {
      key,
      kind: "choice",
      transparent: false,
      module: null,
      rule: label,
      title: uiText(language, titleKey, { count: options.length }),
      entries: [],
      options,
      ruleGroups: [],
      single:
        optionRule.node_type === "CompositeRule" &&
        optionRule.require_max === 1,
      // A sole nested choice is structural wrapping and is selected automatically.
      autoSelectSingleWrapper,
    };
    const setOptionOrigin = (
      entries: StructureEntry[],
      optionOrigin: StructureRuleOrigin,
      preserveLeafOwner = false,
    ) => {
      for (const entry of entries) {
        if (entry.kind === "course")
          entry.origin = {
            ownerKey: preserveLeafOwner
              ? (entry.origin?.ownerKey ?? optionOrigin.ownerKey)
              : optionOrigin.ownerKey,
            choicePath: optionOrigin.choicePath,
          };
        else if (entry.kind === "node") {
          if (entry.node.transparent)
            setOptionOrigin(entry.node.entries, optionOrigin, true);
          else if (entry.node.kind === "choice") {
            for (const nested of entry.node.options)
              setOptionOrigin(nested.entries, {
                ownerKey: entry.node.key,
                choicePath: [
                  ...optionOrigin.choicePath,
                  { node: entry.node, optionKey: nested.key },
                ],
              });
          } else
            entry.origin = {
              ownerKey: preserveLeafOwner
                ? (entry.origin?.ownerKey ?? optionOrigin.ownerKey)
                : optionOrigin.ownerKey,
              choicePath: optionOrigin.choicePath,
            };
        }
      }
    };
    for (const option of options)
      setOptionOrigin(option.entries, {
        ownerKey: key,
        choicePath: [...choicePath, { node, optionKey: option.key }],
      });
    if (
      options.length > 0 &&
      !autoSelectSingleWrapper &&
      options.some((option) => hasSelectableRuleEntries(option.entries))
    )
      ruleGroups.push({
        key,
        rule: label,
        required: false,
        requiredCount:
          optionRule.node_type === "CompositeRule"
            ? (optionRule.require_min ?? 0)
            : 0,
        requiredCredits:
          rule.node_type === "CreditsRule" && rule.credits_min !== null
            ? Number(rule.credits_min)
            : null,
        choiceNode: node,
        options,
      });
    ruleGroups.push(...nestedGroups);
    return [{ kind: "node", node }];
  }
  throw new Error("Unsupported structure rule type");
}
export function buildStructure(
  report: StudyStructureReport,
  key = "r",
  language: DisplayLanguage = "en",
): StructureNode {
  const rootRule = report.root.rule;
  const rootRuleKey =
    (rootRule.node_type === "CompositeRule" &&
      rootRule.all_mandatory !== true) ||
    rootRule.node_type === "CreditsRule" ||
    rootRule.node_type === "CourseUnitCountRule"
      ? `${key}/${rootRule.sibling_position}`
      : key;
  return moduleNode(report.root, key, language, rootRuleKey);
}
export function withUnplaced(
  root: StructureNode,
  language: DisplayLanguage = "en",
): StructureNode {
  const bucket: StructureNode = {
    key: UNPLACED_KEY,
    kind: "unplaced",
    transparent: false,
    module: null,
    rule: uiText(language, "any studies"),
    title: uiText(language, "Unplaced studies"),
    entries: [],
    options: [],
    ruleGroups: [],
    single: false,
    autoSelectSingleWrapper: false,
  };
  return {
    key: "$structure",
    kind: "group",
    transparent: true,
    module: null,
    rule: "",
    title: null,
    entries: [
      { kind: "node", node: root },
      { kind: "node", node: bucket },
    ],
    options: [],
    ruleGroups: [],
    single: false,
    autoSelectSingleWrapper: false,
  };
}
export function resolveStructure(
  root: StructureNode,
  edits: StructureEdits,
  content: PlacedContent,
  language: DisplayLanguage = "en",
): ResolvedNode {
  const seenCourses = new Set<string>();
  const seenModules = new Set<string>(
    root.module ? [root.module.group_id] : [],
  );
  const visitEntries = (
    entries: readonly StructureEntry[],
    node: StructureNode,
  ): {
    courses: PlacedCourse[];
    notes: string[];
    children: ResolvedNode[];
    subtree: CourseSummary[];
    removed: RemovedEntry[];
  } => {
    const courses: PlacedCourse[] = [],
      notes: string[] = [],
      children: ResolvedNode[] = [],
      subtree: CourseSummary[] = [],
      removed: RemovedEntry[] = [];
    for (const entry of entries) {
      if (entry.kind === "course") {
        const id = entry.course.group_id;
        const placement = edits.coursePlacements[id];
        if (placement !== undefined && placement !== node.key) {
          if (
            !removed.some(
              (item) => item.kind === "course" && item.course.group_id === id,
            )
          )
            removed.push({ kind: "course", course: entry.course });
        } else if (!seenCourses.has(id)) {
          seenCourses.add(id);
          const placed = { course: entry.course, added: false };
          courses.push(placed);
          subtree.push(entry.course);
        }
      } else if (entry.kind === "note") {
        notes.push(entry.text);
      } else {
        const moduleId = entry.node.module?.group_id;
        const placement = moduleId
          ? edits.modulePlacements[moduleId]
          : undefined;
        if (moduleId && placement !== undefined && placement !== node.key) {
          if (
            entry.node.module &&
            !removed.some(
              (item) =>
                item.kind === "module" && item.module.group_id === moduleId,
            )
          )
            removed.push({ kind: "module", module: entry.node.module });
        } else if (!moduleId || !seenModules.has(moduleId)) {
          if (moduleId) seenModules.add(moduleId);
          const child = visit(entry.node, false);
          children.push(child);
          subtree.push(...child.subtree);
        }
      }
    }
    for (const [id, placement] of Object.entries(edits.coursePlacements)) {
      if (
        node.kind !== "choice" &&
        placement === node.key &&
        !node.entries.some(
          (entry) => entry.kind === "course" && entry.course.group_id === id,
        ) &&
        !seenCourses.has(id)
      ) {
        const course = content.courses.get(id);
        if (!course) throw new Error("Missing placed course summary");
        seenCourses.add(id);
        const placed = { course, added: true };
        courses.push(placed);
        subtree.push(course);
      }
    }
    for (const [id, placement] of Object.entries(edits.modulePlacements)) {
      if (
        node.kind !== "choice" &&
        placement === node.key &&
        !node.entries.some(
          (entry) =>
            entry.kind === "node" && entry.node.module?.group_id === id,
        ) &&
        !seenModules.has(id)
      ) {
        const report = content.reports[id];
        if (!report) throw new Error("Missing placed module report");
        seenModules.add(id);
        const childNode = buildStructure(
          report,
          `${node.key}/m:${id}`,
          language,
        );
        const child = visit(childNode, true);
        children.push(child);
        subtree.push(...child.subtree);
      }
    }
    return { courses, notes, children, subtree, removed };
  };
  const visit = (node: StructureNode, added = false): ResolvedNode => {
    const storedChoices = edits.choices[node.key];
    const chosen =
      node.kind !== "choice"
        ? []
        : node.autoSelectSingleWrapper && !storedChoices?.length
          ? node.options
          : node.options.filter((option) =>
              storedChoices?.includes(option.key),
            );
    const entries =
      node.kind === "choice"
        ? chosen.flatMap((option) => option.entries)
        : node.entries;
    const content = visitEntries(entries, node);
    return {
      node,
      ...content,
      chosen,
      added,
      removed: content.removed,
    };
  };
  return visit(root);
}
export function nextChoices(
  choices: StructureChoices,
  node: StructureNode,
  optionKey: string,
): StructureChoices {
  const current = choices[node.key] ?? [];
  if (node.single) {
    if (current.length === 1 && current[0] === optionKey) return choices;
    return { ...choices, [node.key]: [optionKey] };
  }
  const next = current.includes(optionKey)
    ? current.filter((key) => key !== optionKey)
    : [...current, optionKey];
  return { ...choices, [node.key]: next };
}

export function officialHomes(
  root: StructureNode,
  edits: StructureEdits,
  content: PlacedContent,
): Map<string, string[]> {
  const homes = new Map<string, string[]>();
  const record = (id: string, key: string) => {
    const keys = homes.get(id) ?? [];
    keys.push(key);
    homes.set(id, keys);
  };
  const walk = (node: StructureNode) => {
    const entries =
      node.kind === "choice"
        ? node.options.flatMap((option) => option.entries)
        : node.entries;
    for (const entry of entries) {
      if (entry.kind === "course") record(entry.course.group_id, node.key);
      else if (entry.kind === "node") {
        if (entry.node.module) record(entry.node.module.group_id, node.key);
        walk(entry.node);
      }
    }
  };
  walk(root);
  for (const [id, key] of Object.entries(edits.modulePlacements)) {
    if (typeof key === "string" && content.reports[id])
      walk(buildStructure(content.reports[id], `${key}/m:${id}`));
  }
  return homes;
}

export function indexResolved(root: ResolvedNode): {
  byKey: Map<string, ResolvedNode>;
  courseAt: Map<string, ResolvedNode>;
  moduleAt: Map<string, ResolvedNode>;
} {
  const byKey = new Map<string, ResolvedNode>();
  const courseAt = new Map<string, ResolvedNode>();
  const moduleAt = new Map<string, ResolvedNode>();
  const walk = (node: ResolvedNode) => {
    byKey.set(node.node.key, node);
    if (node.node.module) moduleAt.set(node.node.module.group_id, node);
    node.courses.forEach(({ course }) => courseAt.set(course.group_id, node));
    node.children.forEach(walk);
  };
  walk(root);
  return { byKey, courseAt, moduleAt };
}
