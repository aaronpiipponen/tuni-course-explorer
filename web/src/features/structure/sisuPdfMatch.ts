/**
 * Browser-local matching of extracted Sisu plan rows against the served official catalogue and the
 * profile's own official structure reads.
 *
 * One catalogue read supplies exact course codes, exact module codes and names, eligible module
 * versions. Structure reports are read in batches through the ordinary cached owner, and only
 * canonical known identities reach the network. Courses resolve by exact code. Modules resolve
 * inside a captured parent's official direct-child scope and only fall back to a unique catalogue
 * code as an added item. Unmatched rows stay in the plan as null-identity placeholders with
 * transient issues, so the placement owner decides their outcome.
 */
import {
  acceptOperationIdentity,
  cancellationError,
} from "../../app/cachedRead";
import type { ReadCache } from "../../app/readCache";
import type {
  CatalogueModule,
  CatalogueReport,
  StudyStructureReport,
  StructureModule,
  StructureRule,
} from "../../api/types";
import { readCachedCatalogue } from "../../shared/course/catalogue";
import {
  type SisuImportIssue,
  type SisuIssueCandidate,
  type SisuItem,
  type SisuModule,
  type SisuPlan,
} from "./sisu";
import { sameOfficialName } from "./sisuNames";
import { readCachedStudyStructures } from "./structureReads";
import {
  INDENT_TOLERANCE,
  INVALID_SISU_PDF_PLAN,
  type SisuPdfRow,
} from "./sisuPdfRows";

const DEGREE_PROGRAMME = "DegreeProgramme";

/** One exact module candidate of the served catalogue. */
type CatalogueModuleCandidate = CatalogueModule & { group_id: string };

/** Exact catalogue lookups built once from the one catalogue read. */
type CatalogueIndex = {
  coursesByCode: Map<string, Set<string>>;
  modulesByCode: Map<string, Set<string>>;
  modulesByGroup: Map<string, readonly CatalogueModuleCandidate[]>;
};

/** Return the display name of one official module summary. */
function moduleName(module: {
  name_fi: string | null;
  name_en: string | null;
}): string {
  return module.name_fi ?? module.name_en ?? "";
}

/** Add one value to the set a map holds under one exact key. */
function addTo<K>(map: Map<K, Set<string>>, key: K, value: string): void {
  const held = map.get(key);
  if (held) held.add(value);
  else map.set(key, new Set([value]));
}

/** Build the exact catalogue lookups and the canonical group candidates. */
function catalogueIndex(report: CatalogueReport): CatalogueIndex {
  const coursesByCode = new Map<string, Set<string>>();
  for (const course of report.courses)
    addTo(coursesByCode, course.code, course.group_id);
  const modulesByCode = new Map<string, Set<string>>();
  const modulesByGroup = new Map<string, readonly CatalogueModuleCandidate[]>();
  for (const group of report.modules) {
    const candidates = group.candidates.map((candidate) => ({
      ...candidate,
      group_id: group.group_id,
    }));
    modulesByGroup.set(group.group_id, candidates);
    for (const candidate of candidates) {
      if (candidate.code !== null)
        addTo(modulesByCode, candidate.code, group.group_id);
    }
  }
  return { coursesByCode, modulesByCode, modulesByGroup };
}

/**
 * Resolve one module group's sole eligible version and record it for the reads.
 *
 * `recorded` reports whether this call recorded a selection that was absent before, which is the
 * only signal a second batch needs.
 */
function soleVersion(
  index: CatalogueIndex,
  groupId: string,
  selections: Record<string, string>,
): { versionId: string | null; recorded: boolean } {
  const versions = new Set(
    (index.modulesByGroup.get(groupId) ?? []).map(
      (candidate) => candidate.sisu_module_id,
    ),
  );
  const [only] = [...versions];
  const versionId = versions.size === 1 && only !== undefined ? only : null;
  const recorded = versionId !== null && selections[groupId] === undefined;
  if (recorded && versionId !== null) selections[groupId] = versionId;
  return { versionId, recorded };
}

/** Return whether one group has several eligible versions. */
function severalVersions(index: CatalogueIndex, groupId: string): boolean {
  return (
    new Set(
      (index.modulesByGroup.get(groupId) ?? []).map(
        (candidate) => candidate.sisu_module_id,
      ),
    ).size > 1
  );
}

/** Return the transient candidate details of one module group. */
function moduleCandidate(
  index: CatalogueIndex,
  groupId: string,
): SisuIssueCandidate {
  const [first] = index.modulesByGroup.get(groupId) ?? [];
  return {
    groupId,
    code: first?.code ?? null,
    name: first ? moduleName(first) : "",
  };
}

/** Return the transient candidate details of one course group. */
function courseCandidate(
  report: CatalogueReport,
  groupId: string,
): SisuIssueCandidate {
  const found = report.courses.find((item) => item.group_id === groupId);
  return {
    groupId,
    code: found?.code ?? null,
    name: found ? (found.name_fi ?? found.name_en ?? found.code) : "",
  };
}

/** Index every module node of the loaded reports by its canonical group identity. */
function moduleNodes(
  reports: Readonly<Record<string, StudyStructureReport>>,
): Map<string, StructureModule> {
  const nodes = new Map<string, StructureModule>();
  const visit = (module: StructureModule) => {
    nodes.set(module.module.group_id, module);
    const walk = (rule: StructureRule) => {
      if (rule.module) visit(rule.module);
      for (const child of rule.children) walk(child);
    };
    walk(module.rule);
  };
  for (const report of Object.values(reports)) visit(report.root);
  return nodes;
}

/**
 * Return one module's direct official module children.
 *
 * Transparent composite and choice rules are flattened and the walk stops at a nested module,
 * matching the placement owner's scope traversal rather than every same-named descendant.
 */
function directModuleChildren(
  module: StructureModule,
): readonly StructureModule["module"][] {
  const children = new Map<string, StructureModule["module"]>();
  const walk = (rule: StructureRule) => {
    if (rule.module) {
      children.set(rule.module.module.group_id, rule.module.module);
      return;
    }
    for (const child of rule.children) walk(child);
  };
  walk(module.rule);
  return [...children.values()];
}

/** One captured frame of the document-order module stack. */
type Frame = {
  node: SisuModule;
  x: number;
  groupId: string | null;
  programme: boolean;
  anomaly: boolean;
};

/** One walk's plan, issues, newly needed report roots and whether it recorded a sole selection. */
type WalkResult = {
  plan: SisuPlan;
  issues: SisuImportIssue[];
  neededRoots: string[];
  recordedSelection: boolean;
};

/** Return the parent frame of one stack frame, or null for the first frame. */
function parentOf(stack: readonly Frame[], frame: Frame): Frame | null {
  const index = stack.indexOf(frame);
  return index > 0 ? stack[index - 1] : null;
}

/** Empty one module item with the extracted name, code and null identity. */
function placeholderModule(row: SisuPdfRow): SisuModule {
  return {
    kind: "module",
    groupId: null,
    versionId: null,
    code: row.code,
    name: row.name,
    children: [],
  };
}

/** One coded module row's resolution: no group, one group, or several distinct groups. */
type CodedGroup =
  | { kind: "none" }
  | { kind: "unique"; groupId: string }
  | { kind: "ambiguous"; candidates: readonly string[] };

/** Resolve one coded module's catalogue group from the exact code alone. */
function codedGroup(index: CatalogueIndex, code: string): CodedGroup {
  const groups = [...(index.modulesByCode.get(code) ?? [])];
  if (groups.length === 0) return { kind: "none" };
  if (groups.length === 1) return { kind: "unique", groupId: groups[0] };
  return { kind: "ambiguous", candidates: groups };
}

/** Return whether one catalogue group is an eligible degree programme. */
function isDegreeGroup(index: CatalogueIndex, groupId: string): boolean {
  return (index.modulesByGroup.get(groupId) ?? []).some(
    (candidate) => candidate.module_type === DEGREE_PROGRAMME,
  );
}

/** Return the unique degree group of one extracted code, when it names exactly one. */
function degreeGroup(index: CatalogueIndex, code: string): string | null {
  const groups = [...(index.modulesByCode.get(code) ?? [])].filter((groupId) =>
    isDegreeGroup(index, groupId),
  );
  return groups.length === 1 ? groups[0] : null;
}

/** Resolve one course row by exact catalogue code and record its issue when not unique. */
function courseNode(
  row: SisuPdfRow,
  index: CatalogueIndex,
  report: CatalogueReport,
): { node: SisuItem; issue: SisuImportIssue | null } {
  if (row.code === null) throw new Error(INVALID_SISU_PDF_PLAN);
  const groups = [...(index.coursesByCode.get(row.code) ?? [])];
  if (groups.length === 1) {
    return {
      node: {
        kind: "course",
        groupId: groups[0],
        code: row.code,
        name: row.name,
        completed: row.completed,
      },
      issue: null,
    };
  }
  return {
    node: {
      kind: "course",
      groupId: null,
      code: row.code,
      name: row.name,
      completed: row.completed,
    },
    issue: {
      name: row.name,
      code: row.code,
      reason:
        groups.length === 0 ? "no_official_match" : "ambiguous_official_match",
      candidates:
        groups.length > 1
          ? groups.map((groupId) => courseCandidate(report, groupId))
          : undefined,
    },
  };
}

/** Return every geometric parent frame one module row may belong to. */
function geometricCandidates(
  stack: readonly Frame[],
  x: number,
): { candidates: Frame[]; defaultParent: Frame | null } {
  const base =
    [...stack].reverse().find((frame) => !frame.programme && !frame.anomaly) ??
    stack[stack.length - 1];
  const same = stack.filter(
    (frame) =>
      !frame.programme &&
      !frame.anomaly &&
      Math.abs(frame.x - x) <= INDENT_TOLERANCE,
  );
  if (same.length) {
    const candidates = [same[same.length - 1]];
    const sibling = parentOf(stack, same[0]);
    if (sibling) candidates.push(sibling);
    return { candidates, defaultParent: sibling };
  }
  if (base && x > base.x + INDENT_TOLERANCE)
    return { candidates: [base], defaultParent: base };
  const top = stack[stack.length - 1];
  if (!top) return { candidates: [], defaultParent: null };
  const candidates = [top];
  for (const frame of [...stack].reverse()) {
    if (Math.abs(frame.x - x) > INDENT_TOLERANCE) continue;
    const parent = parentOf(stack, frame);
    if (parent) candidates.push(parent);
  }
  return { candidates, defaultParent: candidates[0] };
}

/** Return the unique scoped match of one module row among the candidate parents. */
function scopedMatch(
  row: SisuPdfRow,
  parentCandidates: readonly Frame[],
  index: CatalogueIndex,
  tree: ReadonlyMap<string, StructureModule>,
): {
  pairs: { frame: Frame; groupId: string }[];
  candidates: SisuIssueCandidate[];
} {
  const pairs: { frame: Frame; groupId: string }[] = [];
  const candidates = new Map<string, SisuIssueCandidate>();
  for (const frame of parentCandidates) {
    if (frame.groupId === null) continue;
    const module = tree.get(frame.groupId);
    if (!module) continue;
    const children = directModuleChildren(module);
    let matched: readonly StructureModule["module"][] = [];
    if (row.code !== null) {
      const codeGroups = index.modulesByCode.get(row.code) ?? new Set();
      matched = children.filter((child) => codeGroups.has(child.group_id));
    }
    if (!matched.length)
      matched = children.filter((child) => sameOfficialName(child, row.name));
    for (const child of matched) {
      pairs.push({ frame, groupId: child.group_id });
      candidates.set(child.group_id, {
        groupId: child.group_id,
        code: child.code,
        name: moduleName(child),
      });
    }
  }
  const unique = pairs.filter(
    (pair, position) =>
      pairs.findIndex(
        (other) => other.frame === pair.frame && other.groupId === pair.groupId,
      ) === position,
  );
  return { pairs: unique, candidates: [...candidates.values()] };
}

/** Walk the rows in document order with one loaded official tree and build the import plan. */
function walkRows(
  rows: readonly SisuPdfRow[],
  index: CatalogueIndex,
  catalogue: CatalogueReport,
  tree: ReadonlyMap<string, StructureModule>,
  selections: Record<string, string>,
  unavailableRoots: ReadonlySet<string>,
  selectionRequiredRoots: ReadonlySet<string>,
): WalkResult {
  const plan: SisuPlan = { programmes: [] };
  const issues: SisuImportIssue[] = [];
  const neededRoots = new Set<string>();
  let recordedSelection = false;
  const moduleRows = rows.filter((row) => row.kind === "module");
  const leftMargin = Math.min(...moduleRows.map((row) => row.x));
  let stack: Frame[] = [];

  const issue = (
    row: SisuPdfRow,
    reason: SisuImportIssue["reason"],
    candidates?: readonly SisuIssueCandidate[],
  ) => {
    issues.push({
      name: row.name,
      code: row.code,
      reason,
      candidates: candidates?.length ? candidates : undefined,
    });
  };

  const pushModule = (
    row: SisuPdfRow,
    node: SisuModule,
    frame: Frame,
    parent: Frame | null,
  ) => {
    if (parent) {
      (parent.node.children as SisuItem[]).push(node);
      while (stack.length && stack[stack.length - 1] !== parent) stack.pop();
      if (stack[stack.length - 1] !== parent)
        throw new Error(INVALID_SISU_PDF_PLAN);
      frame.anomaly =
        row.x < parent.x - INDENT_TOLERANCE ||
        (Math.abs(row.x - parent.x) <= INDENT_TOLERANCE && parent.anomaly);
    } else {
      plan.programmes.push(node);
      stack = [];
    }
    stack.push(frame);
  };

  for (const row of rows) {
    if (row.kind === "course") {
      const current = stack[stack.length - 1];
      if (!current) throw new Error(INVALID_SISU_PDF_PLAN);
      const resolved = courseNode(row, index, catalogue);
      (current.node.children as SisuItem[]).push(resolved.node);
      if (resolved.issue) issues.push(resolved.issue);
      continue;
    }
    const atLeftMargin = Math.abs(row.x - leftMargin) <= INDENT_TOLERANCE;
    const degree = row.code === null ? null : degreeGroup(index, row.code);
    if (degree !== null) {
      const { versionId, recorded } = soleVersion(index, degree, selections);
      recordedSelection ||= recorded;
      const node: SisuModule = {
        kind: "module",
        groupId: degree,
        versionId,
        code: row.code,
        name: row.name,
        children: [],
      };
      pushModule(
        row,
        node,
        {
          node,
          x: row.x,
          groupId: degree,
          programme: true,
          anomaly: false,
        },
        null,
      );
      continue;
    }
    const coded = row.code === null ? null : codedGroup(index, row.code);
    if (atLeftMargin && degree === null && stack.length === 0) {
      // A top-level header that is not an official degree is an education container, not a module.
      continue;
    }
    const geometric = geometricCandidates(stack, row.x);
    if (!geometric.defaultParent) throw new Error(INVALID_SISU_PDF_PLAN);
    const scoped = scopedMatch(row, geometric.candidates, index, tree);
    if (scoped.pairs.length === 1) {
      const [{ frame, groupId }] = scoped.pairs;
      if ((index.modulesByGroup.get(groupId) ?? []).length === 0) {
        const node = placeholderModule(row);
        issue(row, "no_official_match");
        pushModule(
          row,
          node,
          { node, x: row.x, groupId: null, programme: false, anomaly: false },
          frame,
        );
        continue;
      }
      const { versionId, recorded } = soleVersion(index, groupId, selections);
      recordedSelection ||= recorded;
      const node: SisuModule = {
        kind: "module",
        groupId,
        versionId,
        code: row.code ?? null,
        name: row.name,
        children: [],
      };
      pushModule(
        row,
        node,
        { node, x: row.x, groupId, programme: false, anomaly: false },
        frame,
      );
      if (!tree.has(groupId) && versionId !== null) neededRoots.add(groupId);
      continue;
    }
    if (scoped.pairs.length > 1) {
      const node = placeholderModule(row);
      issue(row, "ambiguous_official_match", scoped.candidates);
      pushModule(
        row,
        node,
        { node, x: row.x, groupId: null, programme: false, anomaly: false },
        geometric.defaultParent,
      );
      continue;
    }
    if (coded?.kind === "ambiguous") {
      const node = placeholderModule(row);
      issue(
        row,
        "ambiguous_official_match",
        coded.candidates.map((groupId) => moduleCandidate(index, groupId)),
      );
      pushModule(
        row,
        node,
        { node, x: row.x, groupId: null, programme: false, anomaly: false },
        geometric.defaultParent,
      );
      continue;
    }
    if (coded?.kind === "none") {
      const node = placeholderModule(row);
      issue(row, "no_official_match");
      pushModule(
        row,
        node,
        { node, x: row.x, groupId: null, programme: false, anomaly: false },
        geometric.defaultParent,
      );
      continue;
    }
    if (coded?.kind === "unique") {
      const parent = geometric.defaultParent;
      if (parent.groupId === null) {
        const node = placeholderModule(row);
        issue(row, "no_official_match");
        pushModule(
          row,
          node,
          { node, x: row.x, groupId: null, programme: false, anomaly: false },
          parent,
        );
        continue;
      }
      const { versionId, recorded } = soleVersion(
        index,
        coded.groupId,
        selections,
      );
      recordedSelection ||= recorded;
      const node: SisuModule = {
        kind: "module",
        groupId: coded.groupId,
        versionId,
        code: row.code,
        name: row.name,
        children: [],
      };
      pushModule(
        row,
        node,
        {
          node,
          x: row.x,
          groupId: coded.groupId,
          programme: false,
          anomaly: false,
        },
        parent,
      );
      if (versionId !== null && !tree.has(coded.groupId))
        neededRoots.add(coded.groupId);
      continue;
    }
    const parent = geometric.defaultParent;
    const node = placeholderModule(row);
    // A readable or unavailable parent report already owns the outcome, so only a pending or
    // unsatisfied version choice keeps the waiting reason.
    const pending =
      parent.groupId !== null &&
      !tree.has(parent.groupId) &&
      !unavailableRoots.has(parent.groupId) &&
      (severalVersions(index, parent.groupId) ||
        selectionRequiredRoots.has(parent.groupId));
    issue(row, pending ? "version_choice_pending" : "no_official_match");
    pushModule(
      row,
      node,
      { node, x: row.x, groupId: null, programme: false, anomaly: false },
      parent,
    );
  }
  return {
    plan,
    issues,
    neededRoots: [...neededRoots],
    recordedSelection,
  };
}

/** Read one batch of canonical roots and accept its dataset identity. */
async function readBatch(
  cache: ReadCache,
  roots: readonly string[],
  selections: Readonly<Record<string, string>>,
  operationIdentity: string,
  signal: AbortSignal,
): Promise<{
  reports: Readonly<Record<string, StudyStructureReport>>;
  unavailable: ReadonlySet<string>;
  selectionRequired: ReadonlySet<string>;
}> {
  if (!roots.length)
    return {
      reports: {},
      unavailable: new Set(),
      selectionRequired: new Set(),
    };
  const response = await readCachedStudyStructures(
    cache,
    roots,
    selections,
    true,
    signal,
  );
  acceptOperationIdentity(cache, operationIdentity, response.dataset_identity);
  if (signal.aborted) throw cancellationError(signal);
  return {
    reports: response.reports,
    unavailable: new Set(response.unavailable_root_group_ids),
    selectionRequired: new Set(response.version_selection_required),
  };
}

/**
 * Match one supported PDF's extracted rows against the served catalogue and official structures.
 *
 * One catalogue read fixes the operation identity. Every programme root and every uniquely
 * code-resolved module root is read first, then one additional batch covers newly resolved roots
 * and a sole selection the walk recorded. Every batch read is checked against the operation
 * identity, and a mismatch fails with the ordinary dataset-changed error. The returned plan carries
 * distinct top-level programme identities before it reaches profile preparation.
 */
export async function matchSisuPdfRows(
  rows: readonly SisuPdfRow[],
  cache: ReadCache,
  signal: AbortSignal,
): Promise<{
  plan: SisuPlan;
  issues: readonly SisuImportIssue[];
}> {
  if (!rows.length) throw new Error(INVALID_SISU_PDF_PLAN);
  const catalogue = await readCachedCatalogue(cache);
  const operationIdentity = catalogue.dataset_identity;
  if (signal.aborted) throw cancellationError(signal);
  const index = catalogueIndex(catalogue);
  const selections: Record<string, string> = {};
  // Every code-resolved module group records its sole version before the first read.
  for (const row of rows)
    if (row.kind === "module" && row.code !== null)
      for (const groupId of index.modulesByCode.get(row.code) ?? [])
        soleVersion(index, groupId, selections);

  const programmeGroups = new Set<string>();
  for (const row of rows) {
    if (row.kind !== "module" || row.code === null) continue;
    const degree = degreeGroup(index, row.code);
    if (degree !== null) programmeGroups.add(degree);
  }
  if (!programmeGroups.size) throw new Error(INVALID_SISU_PDF_PLAN);
  // Every uniquely code-resolved module group is a known canonical root. Reading their reports in
  // the same batch gives the walk each parent scope without a per-row or per-version request.
  const firstRoots = new Set(programmeGroups);
  for (const row of rows) {
    if (row.kind !== "module" || row.code === null) continue;
    const groups = [...(index.modulesByCode.get(row.code) ?? [])];
    if (groups.length === 1) firstRoots.add(groups[0]);
  }

  const first = await readBatch(
    cache,
    [...firstRoots],
    selections,
    operationIdentity,
    signal,
  );
  let reports = first.reports;
  const unavailable = new Set(first.unavailable);
  const selectionRequired = new Set(first.selectionRequired);
  let result = walkRows(
    rows,
    index,
    catalogue,
    moduleNodes(reports),
    selections,
    unavailable,
    selectionRequired,
  );
  if (result.neededRoots.length || result.recordedSelection) {
    const second = await readBatch(
      cache,
      [...new Set([...firstRoots, ...result.neededRoots])],
      selections,
      operationIdentity,
      signal,
    );
    reports = { ...reports, ...second.reports };
    for (const id of second.unavailable) unavailable.add(id);
    for (const id of second.selectionRequired) selectionRequired.add(id);
    result = walkRows(
      rows,
      index,
      catalogue,
      moduleNodes(reports),
      selections,
      unavailable,
      selectionRequired,
    );
  }

  const identities = result.plan.programmes.flatMap((programme) =>
    programme.groupId === null ? [] : [programme.groupId],
  );
  if (new Set(identities).size !== identities.length)
    throw new Error(INVALID_SISU_PDF_PLAN);
  return { plan: result.plan, issues: result.issues };
}
