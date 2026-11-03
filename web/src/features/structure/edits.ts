/**
 * Pure canonical placement edits, exact official destination keys, later-addition precedence and
 * scoped customization reset.
 */
import type { PlacedContent, ResolvedNode, StructureNode } from "./model";
import {
  buildStructure,
  resolveStructure,
  indexResolved,
  officialHomes,
  NO_CONTENT,
} from "./model";
import {
  emptyEdits,
  UNPLACED_KEY,
  type StructureChoices,
  type StructureEdits,
} from "./state";
import { resolvedNodeLabel } from "./presentation";
import {
  courseSource,
  displayedHolders,
  moduleSource,
  orderCourses,
} from "./display";
import { uiText } from "../../shared/wording";
import type { DisplayLanguage } from "../../state/types";

/** The node keys where the official structure names one course or module identity. */
export type Homes = ReadonlyMap<string, readonly string[]>;

/** One course a later-addition operation pulls into the node it adds. */
export type PulledCourse = {
  course: import("../../api/types").CourseSummary;
  /** Localized name of the containing programme or module the course renders in. */
  from: (language: DisplayLanguage) => string;
};

/** One module a later-addition operation pulls into the node it adds, with everything it holds. */
export type PulledModule = {
  module: import("../../api/types").ModuleSummary;
  /** Localized name of the containing programme or module the module renders in. */
  from: (language: DisplayLanguage) => string;
};

function place(
  edits: StructureEdits,
  field: "coursePlacements" | "modulePlacements",
  homes: Homes,
  id: string,
  target: string | null,
): StructureEdits {
  const placements = { ...edits[field] };
  delete placements[id];
  if (target !== null || homes.has(id)) placements[id] = target;
  return { ...edits, [field]: placements };
}

/** Return the edits with one course placed at the target, where null records its official home. */
export const placeCourse = (
  edits: StructureEdits,
  homes: Homes,
  id: string,
  target: string | null,
) => place(edits, "coursePlacements", homes, id, target);

/** Return the edits with one module placed at the target, where null records its official home. */
export const placeModule = (
  edits: StructureEdits,
  homes: Homes,
  id: string,
  target: string | null,
) => place(edits, "modulePlacements", homes, id, target);

/**
 * Return the exact official containing key one course or module move targets.
 *
 * The discovery projection suppresses the moved identity with a null placement in its own field,
 * so no earlier shared occurrence consumes it and the requested target keeps its official entries.
 * Only the target and the choice or transparent children that `displayContents` flattens are
 * inspected. A direct matching entry at the target wins, then the first matching flattened
 * occurrence in displayed order. A visible nested module or programme is not inspected. With no
 * official match the requested key is returned as it is, which keeps the placement an addition.
 */
export function officialPlacementTarget(
  root: StructureNode,
  edits: StructureEdits,
  content: PlacedContent,
  field: "coursePlacements" | "modulePlacements",
  id: string,
  targetKey: string,
): string {
  const discovery: StructureEdits = {
    ...edits,
    [field]: { ...edits[field], [id]: null },
  };
  const target = indexResolved(
    resolveStructure(root, discovery, content),
  ).byKey.get(targetKey);
  if (!target) return targetKey;
  const matches = (node: ResolvedNode): boolean => {
    const entries =
      node.node.kind === "choice"
        ? node.chosen.flatMap((option) => option.entries)
        : node.node.entries;
    return entries.some((entry) =>
      field === "coursePlacements"
        ? entry.kind === "course" && entry.course.group_id === id
        : entry.kind === "node" && entry.node.module?.group_id === id,
    );
  };
  const inspect = (node: ResolvedNode): string | null => {
    if (matches(node)) return node.node.key;
    for (const child of node.children) {
      if (child.node.kind !== "choice" && !child.node.transparent) continue;
      const found = inspect(child);
      if (found) return found;
    }
    return null;
  };
  return inspect(target) ?? targetKey;
}

/** Return whether one node key is the scope key itself or sits under it. */
export function insideScope(scopeKey: string, key: string): boolean {
  return key === scopeKey || key.startsWith(`${scopeKey}/`);
}

/** The nodes one static rule projection reaches under a node, in the order the rule names them. */
function scopeChildren(node: StructureNode): StructureNode[] {
  const entries =
    node.kind === "choice"
      ? node.options.flatMap((option) => option.entries)
      : node.entries;
  return entries.flatMap((entry) =>
    entry.kind === "node" ? [entry.node] : [],
  );
}

/** The option keys one choice node holds, in the order the rule names them. */
function scopeOptionKeys(node: StructureNode): string[] {
  return node.kind === "choice" ? node.options.map((option) => option.key) : [];
}

/**
 * The module identities one node renders from the placement records instead of its own rule.
 *
 * The records are read by identity rather than by node key, so the same identities render inside
 * each rendering of the moved scope.
 */
function placedChildren(
  edits: StructureEdits,
  content: PlacedContent,
  node: StructureNode,
): string[] {
  return Object.entries(edits.modulePlacements).flatMap(([id, target]) =>
    node.kind !== "choice" &&
    target === node.key &&
    content.reports[id] !== undefined &&
    !node.entries.some(
      (entry) => entry.kind === "node" && entry.node.module?.group_id === id,
    )
      ? [id]
      : [],
  );
}

/**
 * Return the key each node, option and placed module of one moved scope takes in the rendering
 * that holds it.
 *
 * Both renderings come from the same official rule and the same placement records, so their nodes
 * pair in the order the rule names them, their choice options pair in the order the rule names
 * them, and a module a record places inside the scope pairs by identity. A module's contents take
 * their keys from the rule key of its own root rule rather than from a plain extension of its node
 * key, so the pairs are read from the two projections instead of a prefix of the source key.
 */
function scopeKeys(
  edits: StructureEdits,
  content: PlacedContent,
  from: StructureNode,
  to: StructureNode,
): Map<string, string> {
  const keys = new Map<string, string>();
  const walk = (oldNode: StructureNode, newNode: StructureNode) => {
    keys.set(oldNode.key, newNode.key);
    const oldOptions = scopeOptionKeys(oldNode);
    const newOptions = scopeOptionKeys(newNode);
    const oldChildren = scopeChildren(oldNode);
    const newChildren = scopeChildren(newNode);
    if (
      oldOptions.length !== newOptions.length ||
      oldChildren.length !== newChildren.length
    )
      throw new Error("A moved scope does not match its new place");
    oldOptions.forEach((key, index) => keys.set(key, newOptions[index]));
    oldChildren.forEach((child, index) => walk(child, newChildren[index]));
    for (const id of placedChildren(edits, content, oldNode)) {
      const report = content.reports[id];
      walk(
        buildStructure(report, `${oldNode.key}/m:${id}`),
        buildStructure(report, `${newNode.key}/m:${id}`),
      );
    }
  };
  walk(from, to);
  return keys;
}

/**
 * Return edits with the records one moved scope owns rewritten for the node keys it renders at.
 *
 * A choice key, an option it holds and a placement target that the projection of the source place
 * names take the key of the same node or option of the destination place, so the scope keeps its
 * choices, its additions, its removals and the placements inside it. A record under the moved node
 * key that no node of the scope names holds a place the destination rendering lacks, and it goes
 * with the record. A removal and a placement outside the moved node describe an identity rather
 * than a place and stay as they are.
 */
export function moveScope(
  edits: StructureEdits,
  content: PlacedContent,
  from: StructureNode,
  to: StructureNode,
): StructureEdits {
  const keys = scopeKeys(edits, content, from, to);
  const move = (key: string) => keys.get(key) ?? key;
  const stale = (key: string) => insideScope(from.key, key) && !keys.has(key);
  const choices: StructureChoices = {};
  for (const [key, options] of Object.entries(edits.choices)) {
    if (stale(key)) continue;
    choices[move(key)] = options.map(move);
  }
  const placements = (record: Record<string, string | null>) => {
    const next: Record<string, string | null> = {};
    for (const [id, target] of Object.entries(record)) {
      if (typeof target === "string" && stale(target)) continue;
      next[id] = typeof target === "string" ? move(target) : target;
    }
    return next;
  };
  return {
    choices,
    coursePlacements: placements(edits.coursePlacements),
    modulePlacements: placements(edits.modulePlacements),
  };
}

/**
 * Return the official homes the clearing of a replaced scope reads.
 *
 * The clearing drops the records of the replaced node key and of the identities that node key
 * names, while the subtree that moves out of it keeps every record of an identity it names: its
 * removals, its places inside itself and its places outside. An identity the moved subtree does
 * not name keeps the homes the replaced scope holds, so a record of the replaced programme's own
 * content clears with it.
 */
export function replacedScopeHomes(homes: Homes, movedKey: string): Homes {
  return new Map(
    [...homes].map(([id, keys]) => [
      id,
      keys.some((key) => insideScope(movedKey, key)) ? [] : keys,
    ]),
  );
}

/**
 * Return the node key each module identity renders directly inside, within one resolved tree.
 *
 * A module's own node key is not a place that renders it: `modulePlacements` names the node whose
 * entries render the module, so a restoration records that containing node.
 */
function moduleContainers(root: ResolvedNode): Map<string, string> {
  const containers = new Map<string, string>();
  const walk = (node: ResolvedNode) => {
    for (const child of node.children) {
      if (child.node.module)
        containers.set(child.node.module.group_id, node.node.key);
      walk(child);
    }
  };
  walk(root);
  return containers;
}

/**
 * Return the official courses of one scope that the tree renders outside it.
 *
 * The identity is kept when the tree renders it outside the scope at an official place, which is
 * what a pull lists. A course the tree renders nowhere, directly in Unplaced studies or inside a
 * module that moves with the same operation contributes nothing.
 */
function scopePulledCourses(
  official: ReturnType<typeof indexResolved>,
  projectedTree: ResolvedNode,
  projected: ReturnType<typeof indexResolved>,
  scopeKey: string,
  pulledKeys: readonly string[],
): PulledCourse[] {
  const pulledInside = (key: string) =>
    pulledKeys.some((pulled) => insideScope(pulled, key));
  const courses: PulledCourse[] = [];
  for (const node of new Set(official.courseAt.values())) {
    if (pulledInside(node.node.key)) continue;
    for (const { course } of node.courses) {
      const id = course.group_id;
      const at = projected.courseAt.get(id);
      if (
        at === undefined ||
        at.node.kind === "unplaced" ||
        insideScope(scopeKey, at.node.key)
      )
        continue;
      const displayed = courseSource(projectedTree, id);
      if (!displayed) throw new Error("Structure target is unavailable");
      courses.push({
        course,
        from: (language) => resolvedNodeLabel(displayed, language),
      });
    }
  }
  return courses;
}

/**
 * Return the official courses and modules of one scope that the tree renders outside it.
 *
 * The scope is read on its own rule with no choices and no content, so only its default contents
 * are read. A module is listed once at its highest level and nothing inside it is read again.
 * `moduleContainers` names the node that renders each listed module officially.
 */
export function officialPulls(
  root: StructureNode,
  edits: StructureEdits,
  content: PlacedContent,
  scope: StructureNode,
): {
  courses: readonly PulledCourse[];
  modules: readonly PulledModule[];
  programmeIds: readonly string[];
  moduleContainers: readonly string[];
} {
  const official = indexResolved(
    resolveStructure(scope, emptyEdits(), NO_CONTENT),
  );
  const projectedTree = resolveStructure(root, edits, content);
  const projected = indexResolved(projectedTree);
  const modulePulls = scopeModulePulls(root, edits, content, scope);
  const courses = scopePulledCourses(
    official,
    projectedTree,
    projected,
    scope.key,
    modulePulls.keys,
  );
  return {
    courses,
    modules: modulePulls.modules,
    programmeIds: modulePulls.programmeIds,
    moduleContainers: modulePulls.containerKeys,
  };
}

/**
 * Return edits that render one scope's official courses at their own official places.
 *
 * A course with more than one official home can be drawn at another home once a reset clears its
 * record. The reset scope restores its own official content, so each listed course takes its own
 * node inside the scope again. `ids` limits the write to the courses a caller restores.
 */
export function placeOfficialCourses(
  root: StructureNode,
  edits: StructureEdits,
  content: PlacedContent,
  scope: StructureNode,
  ids?: Iterable<string>,
): StructureEdits {
  const official = indexResolved(
    resolveStructure(scope, emptyEdits(), NO_CONTENT),
  );
  const projected = indexResolved(resolveStructure(root, edits, content));
  const coursePlacements = { ...edits.coursePlacements };
  const restored = ids === undefined ? null : new Set(ids);
  for (const [id, node] of official.courseAt) {
    if (restored !== null && !restored.has(id)) continue;
    if (projected.courseAt.get(id)?.node.key === node.node.key) continue;
    coursePlacements[id] = node.node.key;
  }
  return { ...edits, coursePlacements };
}

/** The highest-level official modules of one scope that the tree renders outside it. */
function scopeModulePulls(
  root: StructureNode,
  edits: StructureEdits,
  content: PlacedContent,
  scope: StructureNode,
): {
  modules: readonly PulledModule[];
  programmeIds: readonly string[];
  keys: readonly string[];
  containerKeys: readonly string[];
} {
  const official = resolveStructure(scope, emptyEdits(), NO_CONTENT);
  const projectedTree = resolveStructure(root, edits, content);
  const projected = indexResolved(projectedTree);
  const rootEntries = new Set(
    projectedTree.children
      .map((child) => child.node.module?.group_id)
      .filter((id): id is string => id !== undefined),
  );
  const modules: PulledModule[] = [];
  const programmeIds: string[] = [];
  const keys: string[] = [];
  const containerKeys: string[] = [];
  const walk = (node: ResolvedNode) => {
    for (const child of node.children) {
      const module = child.node.module;
      if (module === null) {
        walk(child);
        continue;
      }
      const shown = projected.moduleAt.get(module.group_id);
      if (shown && !insideScope(scope.key, shown.node.key)) {
        const atRoot = rootEntries.has(module.group_id);
        const displayed = moduleSource(projectedTree, module.group_id);
        if (!displayed && !atRoot)
          throw new Error("Structure target is unavailable");
        modules.push({
          module,
          from: atRoot
            ? (language) => uiText(language, "the programme list")
            : (language) => resolvedNodeLabel(displayed!, language),
        });
        keys.push(child.node.key);
        containerKeys.push(displayed?.node.key ?? shown.node.key);
        if (atRoot) programmeIds.push(module.group_id);
        continue;
      }
      walk(child);
    }
  };
  walk(official);
  return { modules, programmeIds, keys, containerKeys };
}

/**
 * Move the listed modules into their own official places inside the scope.
 *
 * A module the ordered programme list renders leaves that list through the caller's programme
 * list, and its records move from the list entry to its official place. Every other module moves
 * through `placeModuleWithCourses`, which keeps its whole current subtree.
 */
export function pullModules(
  root: StructureNode,
  edits: StructureEdits,
  content: PlacedContent,
  scope: StructureNode,
  modules: readonly PulledModule[],
  programmeIds: readonly string[],
): { edits: StructureEdits; programmeIds: readonly string[] } {
  const official = resolveStructure(scope, emptyEdits(), NO_CONTENT);
  const containers = moduleContainers(official);
  let scoped = edits;
  for (const { module } of modules) {
    const id = module.group_id;
    const source = indexResolved(
      resolveStructure(root, scoped, content),
    ).moduleAt.get(id)?.node;
    const destination = indexResolved(official).moduleAt.get(id)?.node;
    if (source === undefined || destination === undefined) continue;
    const targetKey = containers.get(id);
    if (programmeIds.includes(id)) {
      scoped = moveScope(scoped, content, source, destination);
      if (targetKey !== undefined)
        scoped = {
          ...scoped,
          modulePlacements: { ...scoped.modulePlacements, [id]: targetKey },
        };
      continue;
    }
    if (targetKey === undefined) continue;
    scoped = placeModuleWithCourses(
      root,
      scoped,
      content,
      id,
      targetKey,
      source,
      true,
    ).edits;
  }
  return { edits: scoped, programmeIds };
}

/**
 * Return the edits one added holder needs, and the courses and modules that move with them.
 *
 * The holder node is resolved on its own rule, so the records are its own first place for each
 * module and course it officially renders. `present` is whether the tree renders the holder before
 * this operation's own writes. A rendered holder is being moved, and a move is a pure relocation:
 * its records are returned untouched, so it keeps exactly what it holds, no missing official
 * course is filled in, no removed content comes back, and no course or module is pulled out of
 * another holder or listed. Only a holder the tree does not render adopts its scope's official
 * defaults, because the records `clearScope` drops from that scope are removed before the
 * restoration. A place or a removal outside the holder is not part of that clearing, so the
 * clearing leaves it as it is.
 *
 * A holder the tree does not render restores its official contents: a module the cleared projection
 * renders nowhere takes its official place again, which brings the courses inside it with it, and a
 * course the cleared projection does not render at its own node takes the place of that node again.
 * The move list reads the tree before this scope's records are cleared, so a course or module
 * another programme or module renders takes the holder's own place and is listed as a move from the
 * node the tree shows there, while one that renders nowhere or directly in Unplaced studies is not
 * listed. A module is listed once, at its highest official level, and the whole current subtree it
 * holds travels with it, so nothing inside it is read again. Only the holder's default contents are
 * read, so an option the profile does not select by default contributes nothing.
 *
 * `pull` is whether the operation moves the listed courses and modules in. A kept course holds the
 * place it holds: its own placement record stays as it stands, and no place is written for it, so
 * the node that renders it keeps it and the addition holds its official contents without it. A kept
 * module stays in the node that renders it with everything it holds.
 */
export function holderPulls(
  afterTree: StructureNode,
  afterEdits: StructureEdits,
  holderNode: StructureNode,
  content: PlacedContent,
  present: boolean,
  pull = true,
): {
  edits: StructureEdits;
  moves: readonly PulledCourse[];
  moduleMoves: readonly PulledModule[];
  programmeIds: readonly string[];
} {
  // A moved holder keeps the whole current subtree it holds, so nothing changes around it.
  if (present)
    return { edits: afterEdits, moves: [], moduleMoves: [], programmeIds: [] };
  const holderTree = resolveStructure(holderNode, emptyEdits(), NO_CONTENT);
  const holder = indexResolved(holderTree);
  const projectedTree = resolveStructure(afterTree, afterEdits, content);
  const projected = indexResolved(projectedTree);
  // The modules the holder's own rule renders in another node, at their highest level. A
  // listed module moves with its whole structure, so its own content is not read again.
  const {
    modules: moduleMoves,
    programmeIds,
    keys: pulled,
  } = scopeModulePulls(afterTree, afterEdits, content, holderNode);
  const insidePulled = (key: string) =>
    pulled.some((scope) => insideScope(scope, key));
  // The move list reads the tree before this scope's records are cleared, so a course another
  // programme or module renders is asked about rather than silently reclaimed.
  const moves = scopePulledCourses(
    holder,
    projectedTree,
    projected,
    holderNode.key,
    pulled,
  );
  let base = clearScope(afterEdits, holderNode.key);
  if (!pull) base = keepCoursePlacements(base, afterEdits, moves);
  const containers = moduleContainers(holderTree);
  const cleared = indexResolved(resolveStructure(afterTree, base, content));
  const modulePlacements: Record<string, string> = {};
  // The holder renders only after this operation, so its own modules take their official places
  // again, which brings the courses inside them with it.
  for (const [id, key] of containers)
    if (!cleared.moduleAt.has(id)) modulePlacements[id] = key;
  let scoped: StructureEdits = {
    ...base,
    modulePlacements: { ...base.modulePlacements, ...modulePlacements },
  };
  // A listed module moves with its whole current subtree into its own official place.
  if (pull)
    scoped = pullModules(
      afterTree,
      scoped,
      content,
      holderNode,
      moduleMoves,
      programmeIds,
    ).edits;
  // The restored modules render their own default courses, so the course places are read with them.
  const restored = indexResolved(resolveStructure(afterTree, scoped, content));
  const placements: Record<string, string> = {};
  const kept = new Set(moves.map(({ course }) => course.group_id));
  for (const [id, node] of holder.courseAt) {
    if (insidePulled(node.node.key)) continue;
    if (!restored.byKey.has(node.node.key)) continue;
    const placed = node.courses.find((item) => item.course.group_id === id);
    if (!placed) continue;
    // A kept course stays in the node that renders it, so no place is written for it.
    if (!pull && kept.has(id)) continue;
    // A place is written only when the cleared tree does not render the course at its own node.
    if (cleared.courseAt.get(id)?.node.key === node.node.key) continue;
    placements[id] = node.node.key;
  }
  return {
    edits: {
      ...scoped,
      coursePlacements: { ...scoped.coursePlacements, ...placements },
    },
    moves,
    moduleMoves,
    programmeIds: pull ? programmeIds : [],
  };
}

/**
 * Return edits with the listed courses' placement records kept as the supplied edits hold them.
 *
 * A scope clear drops the placement record of a course whose official home is inside the cleared
 * scope, which is what returns that course to the scope. A kept course keeps the record it holds,
 * so the node that renders it outside the scope renders it in the same place, and a course with no
 * record keeps none.
 */
export function keepModulePlacements(
  edits: StructureEdits,
  previous: StructureEdits,
  pulls: readonly PulledModule[],
  containers: readonly string[],
  shared: readonly string[],
): StructureEdits {
  const modulePlacements = { ...edits.modulePlacements };
  pulls.forEach(({ module }, index) => {
    const id = module.group_id;
    if (shared.includes(id)) return;
    const held = previous.modulePlacements[id];
    const container = containers[index];
    if (held !== undefined) modulePlacements[id] = held;
    else if (container !== undefined) modulePlacements[id] = container;
  });
  return { ...edits, modulePlacements };
}

/**
 * Return edits with each pulled course's placement record kept as the supplied edits hold it.
 *
 * A course the supplied edits place keeps that record, and a course with no record loses its record
 * so it returns to its official home.
 */
export function keepCoursePlacements(
  edits: StructureEdits,
  previous: StructureEdits,
  pulls: readonly PulledCourse[],
): StructureEdits {
  const coursePlacements = { ...edits.coursePlacements };
  for (const { course } of pulls) {
    const held = previous.coursePlacements[course.group_id];
    if (held === undefined) delete coursePlacements[course.group_id];
    else coursePlacements[course.group_id] = held;
  }
  return { ...edits, coursePlacements };
}

/**
 * Place one module and return the edits of that placement with the courses it pulls.
 *
 * `from` is the node of the caller's own tree that renders the module, or null when that tree
 * renders none: a module the tree renders moves with its whole current subtree, so the records of
 * that node travel to the destination node before the placement resolves, while a module it does
 * not render adopts its new scope's official defaults. An omitted node reads the module of the
 * supplied edits. `pull` is whether the listed courses of that adoption move into the module.
 */
export function placeModuleWithCourses(
  root: StructureNode,
  edits: StructureEdits,
  content: PlacedContent,
  moduleId: string,
  targetKey: string,
  from?: StructureNode | null,
  pull = true,
  reset?: "keep" | "all",
): {
  edits: StructureEdits;
  moves: readonly PulledCourse[];
  moduleMoves: readonly PulledModule[];
  programmeIds: readonly string[];
  destinationKey: string;
} {
  const next = placeModule(
    edits,
    officialHomes(root, edits, content),
    moduleId,
    officialPlacementTarget(
      root,
      edits,
      content,
      "modulePlacements",
      moduleId,
      targetKey,
    ),
  );
  const destination = indexResolved(
    resolveStructure(root, next, content),
  ).moduleAt.get(moduleId);
  if (!destination)
    throw new Error("Placed module is missing from the resolved structure");
  const source =
    from === undefined
      ? (indexResolved(resolveStructure(root, edits, content)).moduleAt.get(
          moduleId,
        )?.node ?? null)
      : from;
  const moved =
    source !== null && source.key !== destination.node.key
      ? moveScope(next, content, source, destination.node)
      : next;
  const pulled = holderPulls(
    root,
    moved,
    destination.node,
    content,
    source !== null,
    pull,
  );
  const resetEdits =
    reset !== undefined && source !== null
      ? resetMoved(root, pulled.edits, content, destination.node, reset, pull)
      : null;
  return {
    ...pulled,
    edits: resetEdits?.edits ?? pulled.edits,
    programmeIds: [...pulled.programmeIds, ...(resetEdits?.programmeIds ?? [])],
    destinationKey: destination.node.key,
  };
}

/**
 * Return the edits of one scope restored to its official contents.
 *
 * The scope's own records are cleared and its official homes are read from the supplied tree. Only
 * the identities the scope's restored content renders can be restored, so a home that a placement
 * or an option the reset clears supplies leaves the record of the node that renders the identity
 * alone. A pull moves the listed courses and modules in, and a keep leaves each at the place the
 * tree renders it, while the courses whose official home is inside the scope and which the scope
 * renders stay inside it through `placeOfficialCourses`. The returned `pulls` are the courses
 * and modules the restoration asked about, so a caller keeps its own tail over the same state.
 */
export function restoreScopeContents(
  root: StructureNode,
  edits: StructureEdits,
  content: PlacedContent,
  scope: StructureNode,
  pull: boolean,
): { edits: StructureEdits; pulls: ReturnType<typeof officialPulls> } {
  const pulls = officialPulls(root, edits, content, scope);
  const homes = officialHomes(root, edits, content);
  const official = indexResolved(
    resolveStructure(scope, emptyEdits(), NO_CONTENT),
  );
  const shown = indexResolved(resolveStructure(root, edits, content));
  // The official courses the scope renders stay inside it. A second official home would
  // otherwise take them once the reset clears the place that held them here.
  const heldHere = [...official.courseAt]
    .filter(([id]) => {
      const at = shown.courseAt.get(id);
      return at !== undefined && insideScope(scope.key, at.node.key);
    })
    .map(([id]) => id);
  // A home can sit inside the scope through a placement or an option this reset clears, so the
  // scope renders that identity nowhere afterwards. Clearing its record would drop it out of
  // the node that renders it with no place to restore it, so the records this reset clears are
  // only those of the identities its own restored content renders.
  const restored = new Set([
    ...official.courseAt.keys(),
    ...official.moduleAt.keys(),
  ]);
  const restoredHomes: Homes = new Map(
    [...homes].filter(([id]) => restored.has(id)),
  );
  let scoped = resetScope(edits, restoredHomes, scope.key);
  if (pull) {
    scoped = pullModules(
      root,
      scoped,
      content,
      scope,
      pulls.modules,
      pulls.programmeIds,
    ).edits;
    scoped = placeOfficialCourses(root, scoped, content, scope);
  } else {
    scoped = keepCoursePlacements(scoped, edits, pulls.courses);
    scoped = keepModulePlacements(
      scoped,
      edits,
      pulls.modules,
      pulls.moduleContainers,
      pulls.programmeIds,
    );
    scoped = placeOfficialCourses(root, scoped, content, scope, heldHere);
  }
  return { edits: scoped, pulls };
}

/**
 * Return the edits of a moved module reset to its official contents at its new place.
 *
 * The reset clears the records of the destination scope exactly as the drawer's reset does, and a
 * kept returned course keeps its place through `keepCoursePlacements`. A kept-completion reset
 * places every course the reset drops out of the tree in Unplaced studies, so no identity leaves
 * the selection with the reset, while a destructive reset leaves nothing there.
 */
export function resetMoved(
  root: StructureNode,
  edits: StructureEdits,
  content: PlacedContent,
  destination: StructureNode,
  mode: "keep" | "all",
  pull: boolean,
): { edits: StructureEdits; programmeIds: readonly string[] } {
  const { edits: scoped, pulls } = restoreScopeContents(
    root,
    edits,
    content,
    destination,
    pull,
  );
  const programmeIds = pull ? pulls.programmeIds : [];
  if (mode === "all") return { edits: scoped, programmeIds };
  const before = indexResolved(
    resolveStructure(root, edits, content),
  ).byKey.get(destination.key);
  if (!before) throw new Error("Structure target is unavailable");
  const after = indexResolved(resolveStructure(root, scoped, content));
  const coursePlacements = { ...scoped.coursePlacements };
  for (const course of before.subtree) {
    const id = course.group_id;
    if (after.courseAt.get(id) !== undefined) continue;
    coursePlacements[id] = UNPLACED_KEY;
  }
  return { edits: { ...scoped, coursePlacements }, programmeIds };
}

/**
 * Return the records that give a removed holder's courses the ordinary removal outcome.
 *
 * A completed course is placed in Unplaced studies and an uncompleted course leaves the tree, so no
 * stale place keeps either of them out of a node that a later addition gives them.
 */
export function removalPlacements(
  courseIds: readonly string[],
  completedCourseIds: readonly string[],
): Record<string, string | null> {
  const completed = new Set(completedCourseIds);
  return Object.fromEntries(
    courseIds.map((id) => [id, completed.has(id) ? UNPLACED_KEY : null]),
  );
}

/**
 * Return the records that keep a cleared scope's courses out of holders the action does not touch.
 *
 * A course the cleared scope renders follows the ordinary removal outcome of the action
 * instead of falling back into a node the action leaves alone: a completed course is placed in
 * Unplaced studies, an uncompleted course is removed from the tree. How the scope held the course
 * makes no difference, so a restored official place without a record of its own counts as well.
 */
export function clearedScopePlacements(
  affected: ResolvedNode,
  afterTree: StructureNode,
  afterEdits: StructureEdits,
  content: PlacedContent,
  touched: (key: string) => boolean,
  completedCourseIds: readonly string[],
): Record<string, string | null> {
  const placed = indexResolved(
    resolveStructure(afterTree, afterEdits, content),
  ).courseAt;
  const ids: string[] = [];
  for (const course of affected.subtree) {
    const id = course.group_id;
    const node = placed.get(id);
    if (!node || touched(node.node.key)) continue;
    ids.push(id);
  }
  return removalPlacements(ids, completedCourseIds);
}

/**
 * Return edits without the records one scope owns.
 *
 * A choice belongs to the scope when its key sits inside it, and a placement when its target does.
 * A removal record and a place outside the scope belong to the identity, not to this scope.
 */
function clearScope(edits: StructureEdits, scopeKey: string): StructureEdits {
  const inScope = (key: string) => insideScope(scopeKey, key);
  const placements = (record: Record<string, string | null>) =>
    Object.fromEntries(
      Object.entries(record).filter(
        ([, target]) => !(typeof target === "string" && inScope(target)),
      ),
    );
  return {
    choices: Object.fromEntries(
      Object.entries(edits.choices).filter(([key]) => !inScope(key)),
    ),
    coursePlacements: placements(edits.coursePlacements),
    modulePlacements: placements(edits.modulePlacements),
  };
}

/**
 * Return the edits with one scope's records cleared and its official homes restored.
 *
 * `keepExternalPlacements` leaves a placement in place when its target is outside the scope, even
 * when the course's official home is inside it. A delete or replace sets it so a course manually
 * placed in another programme stays there. A reset leaves it false so the identities its restored
 * content renders return to it, and its caller passes only those identities' homes.
 */
export function resetScope(
  edits: StructureEdits,
  homes: Homes,
  scopeKey: string,
  keepExternalPlacements = false,
): StructureEdits {
  const cleared = clearScope(edits, scopeKey);
  if (keepExternalPlacements) return cleared;
  const inScope = (key: string) => insideScope(scopeKey, key);
  return {
    choices: cleared.choices,
    coursePlacements: Object.fromEntries(
      Object.entries(cleared.coursePlacements).filter(
        ([id]) => !(homes.get(id) ?? []).some(inScope),
      ),
    ),
    modulePlacements: Object.fromEntries(
      Object.entries(cleared.modulePlacements).filter(
        ([id]) => !(homes.get(id) ?? []).some(inScope),
      ),
    ),
  };
}

/** The rendered semantic tuple of one node: identity, rendered contents, notes and children. */
function scopeValue(value: ResolvedNode): unknown[] {
  return [
    value.node.key,
    value.node.module?.group_id ?? null,
    value.courses.map((item) => item.course.group_id),
    value.notes,
    value.children.map(scopeValue),
  ];
}

/**
 * Return whether one scope's rendering differs from the same scope's fresh-placement rendering.
 *
 * The candidate is the state in which this scope's own records are cleared and the holder's
 * official defaults are placed into it again through `holderPulls`, which is the rendering a held
 * identity shows when the tree first draws it. The parent-level precedence of that placement is
 * therefore part of the candidate, so a course the holder's placement pulls out of another holder
 * is not a difference of this scope on its own, while a choice, a removal, an addition or a move
 * that changes what this scope renders is. A supplied course order also compares the displayed
 * holder sequences inside the scope, where the candidate reads the unranked order the scope draws
 * without saved ranks. The comparison reads the rendered contents and notes and no history. The
 * current target must resolve, and a restored target that the candidate does not render counts as a
 * difference.
 */
export function hasScopedEdits(
  root: StructureNode,
  edits: StructureEdits,
  content: PlacedContent,
  scopeKey: string,
  courseOrder?: readonly string[],
): boolean {
  const currentTree = resolveStructure(root, edits, content);
  const current = indexResolved(currentTree).byKey.get(scopeKey);
  if (!current) throw new Error("Structure target is unavailable");
  const candidate = holderPulls(
    root,
    edits,
    current.node,
    content,
    false,
  ).edits;
  const candidateTree = resolveStructure(root, candidate, content);
  const restored = indexResolved(candidateTree).byKey.get(scopeKey);
  if (!restored) return true;
  if (
    JSON.stringify(scopeValue(current)) !== JSON.stringify(scopeValue(restored))
  )
    return true;
  if (courseOrder === undefined) return false;
  const sequences = (tree: ResolvedNode, order: readonly string[]) =>
    displayedHolders(tree)
      .filter((holder) => insideScope(scopeKey, holder.key))
      .map((holder) => [
        holder.key,
        orderCourses(holder.courses, order).map((item) => item.course.group_id),
      ]);
  return (
    JSON.stringify(sequences(currentTree, courseOrder)) !==
    JSON.stringify(sequences(candidateTree, []))
  );
}

/** Return whether one resolved scope holds a completed course. */
export function scopeHoldsCompletion(
  index: ReturnType<typeof indexResolved>,
  scopeKey: string,
  completedCourseIds: readonly string[],
): boolean {
  const completed = new Set(completedCourseIds);
  return (index.byKey.get(scopeKey)?.subtree ?? []).some((course) =>
    completed.has(course.group_id),
  );
}

/**
 * Return the reset actions one move offers beside Move, from the moved holder's own state.
 *
 * A scope whose contents differ from its fresh-placement rendering needs the restoring reset, a
 * scope that holds a completed course needs the destructive one, and a scope with both needs both.
 * A scope with neither needs no reset.
 */
export function moveResetOptions(
  root: StructureNode,
  edits: StructureEdits,
  content: PlacedContent,
  movedIndex: ReturnType<typeof indexResolved>,
  scopeKey: string,
  completedCourseIds: readonly string[],
): "both" | "reset" | "reset-all" | undefined {
  const edited = hasScopedEdits(root, edits, content, scopeKey);
  const completed = scopeHoldsCompletion(
    movedIndex,
    scopeKey,
    completedCourseIds,
  );
  if (edited && completed) return "both";
  if (edited) return "reset";
  if (completed) return "reset-all";
  return undefined;
}
