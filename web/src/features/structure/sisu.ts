/**
 * Sisu plan capture boundary: validate one downloaded capture, parse its page markup into the
 * ordered module and course hierarchy, prepare an import profile, and resolve that pending
 * hierarchy into structure choices once the official programme reads have settled.
 *
 * The markup is read as data only and contributes names, codes, nesting and a completion marker.
 * Every identity comes from the capture's anonymous Kori lookup results, never from the page text.
 */
import { initialProfileState } from "../../state/defaults";
import type { DisplayLanguage, Profile, ProfileState } from "../../state/types";
import {
  buildProgrammeForest,
  buildStructure,
  nextChoices,
  officialHomes,
  programmeKey,
  resolveStructure,
  type PlacedContent,
  type StructureNode,
  type StructureRuleOrigin,
} from "./model";
import { placeCourse, placeModule } from "./edits";
import { UNPLACED_KEY, type StructureEdits } from "./state";
import type { StructureChange } from "./actions";

/** One captured course unit: its catalogue group id, or null when the code matches no single course, and its attainment mark. */
export type SisuCourse = {
  kind: "course";
  groupId: string | null;
  code: string;
  name: string;
  completed: boolean;
};
/** One captured module or programme with its catalogue group id, its exact version id, or nulls when unresolved, and its children in plan order. */
export type SisuModule = {
  kind: "module";
  groupId: string | null;
  /** The exact official version read from the capture's status-cell id, when the group resolved. */
  versionId: string | null;
  code: string | null;
  name: string;
  children: SisuItem[];
};
/** One captured entry of a module. */
export type SisuItem = SisuCourse | SisuModule;
/** A captured Sisu plan: its programmes in plan order. */
export type SisuPlan = { programmes: SisuModule[] };
/** The downloaded capture file: a plan tagged with its file type. */
export type SisuCaptureFile = SisuPlan & {
  type: "tuni-course-explorer/sisu/1";
};
/** One captured item the import could not place, named by its captured name and code. */
export type SisuImportIssue = {
  name: string;
  code: string | null;
  reason: "unresolved" | "module_not_placed" | "course_not_represented";
};

const CAPTURE_TYPE = "tuni-course-explorer/sisu/1";
const INVALID_CAPTURE = "Invalid Sisu plan file";
const AMBIGUOUS_CHOICE = "Sisu choice is ambiguous";
const MODULE_TAG = "plan-module";
const COURSE_BOX_TAG = "course-unit-box";

/** One anonymous Kori course-unit-search result the capture needs to resolve a course code. */
type SisuCourseHit = { code: string; groupId: string };

/** The two lookup result maps of one page capture, keyed by page text and status cell id. */
type SisuLookups = {
  modules: Record<string, readonly string[]>;
  courses: Record<string, readonly SisuCourseHit[]>;
};

function captureObject(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error(INVALID_CAPTURE);
  return value as Record<string, unknown>;
}

function captureIdentity(value: unknown): string {
  if (typeof value !== "string" || value === "")
    throw new Error(INVALID_CAPTURE);
  return value;
}

function captureNullableIdentity(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  return captureIdentity(value);
}

function planModule(value: unknown): SisuModule {
  const saved = captureObject(value);
  if (saved.kind !== "module") throw new Error(INVALID_CAPTURE);
  if (!Object.hasOwn(saved, "versionId")) throw new Error(INVALID_CAPTURE);
  return {
    kind: "module",
    groupId: captureNullableIdentity(saved.groupId),
    versionId: captureNullableIdentity(saved.versionId),
    code: captureNullableIdentity(saved.code),
    name: captureIdentity(saved.name),
    children: planItems(saved.children),
  };
}

function planItem(value: unknown): SisuItem {
  const saved = captureObject(value);
  if (saved.kind === "module") return planModule(saved);
  if (saved.kind !== "course" || typeof saved.completed !== "boolean")
    throw new Error(INVALID_CAPTURE);
  return {
    kind: "course",
    groupId: captureNullableIdentity(saved.groupId),
    code: captureIdentity(saved.code),
    name: captureIdentity(saved.name),
    completed: saved.completed,
  };
}

function planItems(value: unknown): SisuItem[] {
  if (!Array.isArray(value)) throw new Error(INVALID_CAPTURE);
  return value.map(planItem);
}

/**
 * Validate one stored or pending hierarchy and project it onto the current capture fields.
 *
 * A duplicate non-null top-level programme identity is rejected, because a programme has one
 * top-level place, while a repeated course occurrence is a supported capture outcome. An unknown
 * field is discarded.
 */
export function validateSisuPlan(value: unknown): SisuPlan {
  const saved = captureObject(value);
  if (!Array.isArray(saved.programmes) || saved.programmes.length === 0)
    throw new Error(INVALID_CAPTURE);
  const programmes = saved.programmes.map(planModule);
  const identities = programmes.flatMap((programme) =>
    programme.groupId === null ? [] : [programme.groupId],
  );
  if (new Set(identities).size !== identities.length)
    throw new Error(INVALID_CAPTURE);
  return { programmes };
}

function stringListRecord(value: unknown): Record<string, readonly string[]> {
  const saved = captureObject(value);
  return Object.fromEntries(
    Object.entries(saved).map(([key, list]) => {
      if (!Array.isArray(list)) throw new Error(INVALID_CAPTURE);
      return [captureIdentity(key), list.map(captureIdentity)];
    }),
  );
}

function courseHitRecord(
  value: unknown,
): Record<string, readonly SisuCourseHit[]> {
  const saved = captureObject(value);
  return Object.fromEntries(
    Object.entries(saved).map(([key, list]) => {
      if (!Array.isArray(list)) throw new Error(INVALID_CAPTURE);
      return [
        captureIdentity(key),
        list.map((hit) => {
          const result = captureObject(hit);
          return {
            code: captureIdentity(result.code),
            groupId: captureIdentity(result.groupId),
          };
        }),
      ];
    }),
  );
}

/** The sole identity of a lookup result, or null when the result holds none or several. */
function singleIdentity(identities: readonly string[]): string | null {
  const unique = [...new Set(identities)];
  return unique.length === 1 ? unique[0] : null;
}

/** Elements of one selector below this element but not inside a module nested in it. */
function own(root: Element, selector: string): Element[] {
  const owner = root.closest(MODULE_TAG);
  return [...root.querySelectorAll(selector)].filter(
    (found) => found.closest(MODULE_TAG) === owner,
  );
}

/** The modules and course boxes that sit directly in this module, in document order. */
function ownChildren(module: Element): Element[] {
  return [
    ...module.querySelectorAll(`${MODULE_TAG}, ${COURSE_BOX_TAG}`),
  ].filter((child) => child.parentElement?.closest(MODULE_TAG) === module);
}

function ownText(module: Element, selector: string): string | null {
  const text = own(module, selector)[0]?.textContent?.trim();
  return text ? text : null;
}

function requiredText(module: Element, selector: string): string {
  const text = ownText(module, selector);
  if (text === null) throw new Error(INVALID_CAPTURE);
  return text;
}

function parseModule(element: Element, capture: SisuLookups): SisuModule {
  const statusId = own(element, ".status [id]")[0]?.id;
  const groupId = statusId
    ? singleIdentity(capture.modules[statusId] ?? [])
    : null;
  return {
    kind: "module",
    groupId,
    versionId:
      groupId !== null && statusId !== undefined
        ? statusId.replace(/-statuscell.*$/, "")
        : null,
    code: ownText(element, '[ng-bind=":: $ctrl.module.code"]'),
    name: requiredText(element, '[data-cy="plan-module-name"]'),
    children: parseChildren(element, capture),
  };
}

function parseChildren(module: Element, capture: SisuLookups): SisuItem[] {
  return ownChildren(module).map((child) =>
    child.localName === MODULE_TAG
      ? parseModule(child, capture)
      : parseCourse(child, capture),
  );
}

function parseCourse(box: Element, capture: SisuLookups): SisuCourse {
  const code = requiredText(box, ".courseunit-code");
  const title = requiredText(box, ".title-box");
  const name = title.replace(code, "").replace(/\s+/g, " ").trim();
  if (!name) throw new Error(INVALID_CAPTURE);
  return {
    kind: "course",
    groupId: singleIdentity(
      (capture.courses[code] ?? [])
        .filter((hit) => hit.code === code)
        .map((hit) => hit.groupId),
    ),
    code,
    name,
    // The marker states that the course unit has an attainment. No grade value is read.
    completed:
      box.querySelector("app-course-unit-attainment-notification") !== null,
  };
}

/** The top-level plan modules of one page, in document order. */
function topModules(doc: Document): Element[] {
  return [...doc.querySelectorAll(MODULE_TAG)].filter(
    (module) => module.parentElement?.closest(MODULE_TAG) === null,
  );
}

/**
 * Whether one top-level module is the education row that wraps the degrees of a plan.
 *
 * A degree carries the graduation flag and an information button, and a grouping row carries the
 * grouping title. A header with none of the three is the education container.
 */
function isEducationHeader(module: Element): boolean {
  return (
    own(module, ".graduate").length === 0 &&
    own(module, ".title.grouping-module").length === 0 &&
    own(module, '[id^="module-info-modal-open-"]').length === 0
  );
}

function parseProgrammes(doc: Document, capture: SisuLookups): SisuModule[] {
  const programmes: SisuModule[] = [];
  for (const top of topModules(doc)) {
    if (!isEducationHeader(top)) {
      programmes.push(parseModule(top, capture));
      continue;
    }
    // The education is a container, so its degree rows become the top-level programmes.
    for (const degree of ownChildren(top).filter(
      (child) => child.localName === MODULE_TAG,
    )) {
      if (own(degree, ".graduate").length === 0)
        throw new Error(INVALID_CAPTURE);
      programmes.push(parseModule(degree, capture));
    }
  }
  return programmes;
}

/**
 * Validate one downloaded capture and parse its plan markup into the capture hierarchy.
 *
 * The markup is parsed as data and never inserted into the document or evaluated. A capture whose
 * markup holds no readable plan fails with `Invalid Sisu plan file`.
 */
export function parseSisuCapture(value: unknown): SisuCaptureFile {
  const saved = captureObject(value);
  const markup = saved.markup;
  if (typeof markup !== "string" || markup.trim() === "")
    throw new Error(INVALID_CAPTURE);
  const lookups: SisuLookups = {
    modules: stringListRecord(saved.modules),
    courses: courseHitRecord(saved.courses),
  };
  const programmes = parseProgrammes(
    new DOMParser().parseFromString(markup, "text/html"),
    lookups,
  );
  // The parsed hierarchy passes the same plan check the stored record does, so a plan whose
  // top-level degrees share one identity is refused here instead of poisoning the profile.
  return { type: CAPTURE_TYPE, ...validateSisuPlan({ programmes }) };
}

/**
 * Build the profile one capture imports into: every resolved course is selected, a course captured
 * as completed is completed, the top-level programmes keep their capture order, and every resolved
 * module version is recorded before any structure read. The hierarchy waits in `pendingSisuImport`
 * until Structure's first read places it.
 */
export function prepareSisuProfile(
  capture: SisuPlan,
  name: string,
  language: DisplayLanguage,
): Profile {
  const base = initialProfileState();
  const selected: string[] = [];
  const completed = new Set<string>();
  const moduleVersions: Record<string, string> = {};
  const collect = (items: readonly SisuItem[]) => {
    for (const item of items) {
      if (item.kind === "module") {
        if (item.groupId !== null && item.versionId !== null) {
          const stored = moduleVersions[item.groupId];
          if (stored !== undefined && stored !== item.versionId)
            throw new Error("Sisu plan selects two versions of a module");
          moduleVersions[item.groupId] = item.versionId;
        }
        collect(item.children);
        continue;
      }
      if (item.groupId === null) continue;
      if (!selected.includes(item.groupId)) selected.push(item.groupId);
      if (item.completed) completed.add(item.groupId);
    }
  };
  collect(capture.programmes);
  return {
    name,
    state: {
      ...base,
      language,
      selectedCourseIds: selected,
      completedCourseIds: selected.filter((id) => completed.has(id)),
      structure: {
        ...base.structure,
        programmeGroupIds: capture.programmes.flatMap((programme) =>
          programme.groupId === null ? [] : [programme.groupId],
        ),
        moduleVersions,
      },
      pendingSisuImport: structuredClone(capture),
    },
  };
}

/**
 * Return whether one profile holds a waiting Sisu capture beside saved structure edits.
 *
 * A saved choice or place and a waiting capture are both profile data, so the capture cannot be
 * placed without discarding the other. A choice entry counts even when its list is empty, and a
 * placement counts even when its target is `null`, because both are saved edits. Programme
 * identities, version selections and the shared course sets alone do not count, because a
 * prepared capture fills them without an edit.
 */
export function sisuImportBlocked(
  state: Pick<ProfileState, "pendingSisuImport" | "structure">,
): boolean {
  if (state.pendingSisuImport === null) return false;
  return (
    Object.keys(state.structure.choices).length > 0 ||
    Object.keys(state.structure.coursePlacements).length > 0 ||
    Object.keys(state.structure.modulePlacements).length > 0 ||
    state.structure.placedCourseIds.length > 0
  );
}

/** Return every resolved module identity of one capture, in capture order, for the pending reads. */
export function captureModuleIds(capture: SisuPlan): string[] {
  const ids: string[] = [];
  const visit = (items: readonly SisuItem[]) => {
    for (const item of items) {
      if (item.kind !== "module") continue;
      if (item.groupId !== null && !ids.includes(item.groupId))
        ids.push(item.groupId);
      visit(item.children);
    }
  };
  visit(capture.programmes);
  return ids;
}

type Scope = {
  courses: Map<string, StructureRuleOrigin>;
  modules: Map<string, { origin: StructureRuleOrigin; node: StructureNode }>;
  ambiguous: Set<string>;
};

/**
 * Collect the official identities one module's own rule offers, through its transparent groups and
 * every option of its choice nodes, and stop at the boundary of a nested module.
 *
 * An identity that appears twice in that scope is recorded as ambiguous, so a caller fails instead
 * of choosing one of the two branches.
 */
function scopeOf(node: StructureNode): Scope {
  const scope: Scope = {
    courses: new Map(),
    modules: new Map(),
    ambiguous: new Set(),
  };
  const visit = (current: StructureNode) => {
    const entries =
      current.kind === "choice"
        ? current.options.flatMap((option) => option.entries)
        : current.entries;
    for (const entry of entries) {
      if (entry.kind === "course") {
        const id = entry.course.group_id;
        if (!entry.origin) continue;
        if (scope.courses.has(id)) scope.ambiguous.add(id);
        else scope.courses.set(id, entry.origin);
        continue;
      }
      if (entry.kind === "node") {
        const module = entry.node.module;
        // A group or choice entry carries no origin of its own. Only its leaves do.
        if (!module) {
          visit(entry.node);
          continue;
        }
        if (!entry.origin) continue;
        if (scope.modules.has(module.group_id))
          scope.ambiguous.add(module.group_id);
        else
          scope.modules.set(module.group_id, {
            origin: entry.origin,
            node: entry.node,
          });
      }
    }
  };
  visit(node);
  return scope;
}

/**
 * Resolve the pending capture into one structure change and its named omissions.
 *
 * Returns null while a pending import exists whose official content has not settled: every
 * resolved captured module identity needs a report or a recorded unavailable module, and every
 * selected identity needs a summary or a recorded unavailable course. It returns null as well
 * while the profile holds saved edits beside the waiting capture, so placement never rewrites a
 * restored profile. A captured module the
 * parent's rule does not name joins that parent as an added module of its own report, and a module
 * with no report is named and its courses are kept loose. The change clears the pending record and
 * removes exactly the captured identities that no catalogue course represents. This function is
 * pure: it reads the supplied state and content, and writes nothing.
 */
export function resolveSisuImport(
  state: ProfileState,
  content: PlacedContent,
  unavailable: { courseIds: readonly string[]; moduleIds: readonly string[] },
): { change: StructureChange; issues: SisuImportIssue[] } | null {
  const capture = state.pendingSisuImport;
  if (!capture) return null;
  if (sisuImportBlocked(state)) return null;
  const unavailableModules = new Set(unavailable.moduleIds);
  const unavailableCourses = new Set(unavailable.courseIds);
  for (const id of captureModuleIds(capture))
    if (!content.reports[id] && !unavailableModules.has(id)) return null;
  for (const id of state.selectedCourseIds)
    if (!content.courses.has(id) && !unavailableCourses.has(id)) return null;

  const language = state.language;
  const issues: SisuImportIssue[] = [];
  const removed = new Set<string>();
  const available = capture.programmes.filter(
    (programme) =>
      programme.groupId !== null && content.reports[programme.groupId],
  );
  const forest = buildProgrammeForest(
    available.map((programme) => content.reports[programme.groupId!]),
    language,
  );
  const forestNodes = new Map<string, StructureNode>();
  for (const entry of forest.entries)
    if (entry.kind === "node") forestNodes.set(entry.node.key, entry.node);
  let edits: StructureEdits = {
    choices: {},
    coursePlacements: {},
    modulePlacements: {},
  };
  const homesNow = () => officialHomes(forest, edits, content);
  let homes = homesNow();
  const issue = (item: SisuItem, reason: SisuImportIssue["reason"]) =>
    issues.push({ name: item.name, code: item.code, reason });
  /**
   * Select one matched entry's choice steps. A step that is already selected is left as it is, so a
   * repeated hit does not toggle a choice off, and a single-choice node that already holds another
   * option fails instead of being overwritten.
   */
  const choosePath = (path: StructureRuleOrigin["choicePath"]) => {
    for (const step of path) {
      const current = edits.choices[step.node.key] ?? [];
      if (current.includes(step.optionKey)) continue;
      if (step.node.single && current.length > 0)
        throw new Error(AMBIGUOUS_CHOICE);
      edits = {
        ...edits,
        choices: nextChoices(edits.choices, step.node, step.optionKey),
      };
    }
  };
  // Every representable descendant course of an omitted module keeps its completion loose.
  const keepLoose = (items: readonly SisuItem[]) => {
    for (const item of items) {
      if (item.kind === "module") {
        if (item.groupId === null) issue(item, "unresolved");
        keepLoose(item.children);
        continue;
      }
      if (item.groupId === null) {
        issue(item, "unresolved");
        continue;
      }
      if (!content.courses.has(item.groupId)) {
        issue(item, "course_not_represented");
        removed.add(item.groupId);
        continue;
      }
      edits = placeCourse(edits, homes, item.groupId, UNPLACED_KEY);
    }
  };
  const walk = (parent: StructureNode, items: readonly SisuItem[]) => {
    // A placement made above changes the official homes below it, so each scope reads them again.
    homes = homesNow();
    const scope = scopeOf(parent);
    const capturedCourses = new Set<string>();
    const capturedModules = new Set<string>();
    for (const item of items) {
      if (item.kind === "course") {
        if (item.groupId === null) {
          issue(item, "unresolved");
          continue;
        }
        if (!content.courses.has(item.groupId)) {
          issue(item, "course_not_represented");
          removed.add(item.groupId);
          continue;
        }
        capturedCourses.add(item.groupId);
        if (scope.ambiguous.has(item.groupId))
          throw new Error(AMBIGUOUS_CHOICE);
        const match = scope.courses.get(item.groupId);
        if (!match) {
          edits = placeCourse(edits, homes, item.groupId, parent.key);
          continue;
        }
        choosePath(match.choicePath);
        edits = placeCourse(edits, homes, item.groupId, match.ownerKey);
        continue;
      }
      if (item.groupId === null) {
        issue(item, "unresolved");
        keepLoose(item.children);
        continue;
      }
      if (
        capturedModules.has(item.groupId) ||
        scope.ambiguous.has(item.groupId)
      )
        throw new Error(AMBIGUOUS_CHOICE);
      capturedModules.add(item.groupId);
      const match = scope.modules.get(item.groupId);
      if (match) {
        choosePath(match.origin.choicePath);
        edits = placeModule(edits, homes, item.groupId, match.origin.ownerKey);
        walk(match.node, item.children);
        continue;
      }
      const report = content.reports[item.groupId];
      if (!report) {
        issue(item, "module_not_placed");
        keepLoose(item.children);
        continue;
      }
      // The parent's rule does not name this module, so the captured module joins that parent as an
      // added module of its own official report, and its captured children go inside it.
      edits = placeModule(edits, homes, item.groupId, parent.key);
      walk(
        buildStructure(report, `${parent.key}/m:${item.groupId}`, language),
        item.children,
      );
    }
    // An official identity this scope does not capture is suppressed, so the official default
    // cannot silently select content the fully expanded capture does not hold. An identity a
    // capture already placed elsewhere keeps that place.
    for (const id of scope.courses.keys())
      if (!capturedCourses.has(id) && edits.coursePlacements[id] === undefined)
        edits = placeCourse(edits, homes, id, null);
    for (const id of scope.modules.keys())
      if (!capturedModules.has(id) && edits.modulePlacements[id] === undefined)
        edits = placeModule(edits, homes, id, null);
  };
  for (const programme of capture.programmes) {
    const id = programme.groupId;
    if (id !== null && content.reports[id]) continue;
    issue(programme, id === null ? "unresolved" : "module_not_placed");
    keepLoose(programme.children);
  }
  for (const programme of available) {
    const node = forestNodes.get(programmeKey(programme.groupId!));
    if (!node) {
      issue(programme, "module_not_placed");
      keepLoose(programme.children);
      continue;
    }
    walk(node, programme.children);
  }
  const projection = resolveStructure(forest, edits, content, language);
  return {
    change: {
      next: {
        programmeGroupIds: available.map((programme) => programme.groupId!),
        ...edits,
        moduleVersions: { ...state.structure.moduleVersions },
        placedCourseIds: projection.subtree.map((course) => course.group_id),
      },
      removedCourseIds: [...removed],
      pendingSisuImport: null,
    },
    issues,
  };
}
