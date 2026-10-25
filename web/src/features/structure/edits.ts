/** Pure canonical placement edits, later-addition precedence and scoped customization reset. */
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
import { courseSource } from "./display";
import type { DisplayLanguage } from "../../state/types";

/** The node keys where the official structure names one course or module identity. */
export type Homes = ReadonlyMap<string, readonly string[]>;

/** One course a later-addition operation pulls into the node it adds. */
export type PulledCourse = {
  course: import("../../api/types").CourseSummary;
  /** Localized name of the containing programme or module the course renders in now. */
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
 * Return the key each node, option and placed module of one moved scope takes in the rendering that
 * holds it now.
 *
 * Both renderings come from the same official rule and the same placement records, so their nodes
 * pair in the order the rule names them, their choice options pair in the order the rule names them,
 * and a module a record places inside the scope pairs by identity. A module's contents take their
 * keys from the rule key of its own root rule rather than from a plain extension of its node key, so
 * the pairs are read from the two projections instead of a prefix of the source key.
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
 * Return edits with the records one moved scope owns rewritten for the node keys it renders at now.
 *
 * A choice key, an option it holds and a placement target that the projection of the source place
 * names take the key of the same node or option of the destination place, so the scope keeps its choices,
 * its additions, its removals and the placements inside it. A record under the moved node key that
 * no node of the scope names holds a place the destination rendering does not have and goes with it, while a
 * removal and a placement outside the moved node describe an identity rather than a place and stay
 * as they are.
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
 * The clearing drops the records of the replaced node key and of the identities that node key names,
 * while the subtree that moves out of it keeps every record of an identity it names: its removals,
 * its places inside itself and its places outside. An identity the moved subtree does not name keeps
 * the homes the replaced scope holds, so a record of the replaced programme's own content clears
 * with it.
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
 * Return the edits one added holder needs, and the courses that move with them.
 *
 * The holder node is resolved on its own rule, so the records are its own first place for each
 * module and course it officially renders. `present` is whether the tree renders the holder before
 * this operation's own writes. A rendered holder is being moved, and a move is a pure relocation:
 * its records are returned untouched, so it keeps exactly what it holds now, no missing official
 * course is filled in, no removed content comes back, and no course is pulled out of another holder
 * or listed. Only a holder the tree does not render adopts its scope's official defaults, because
 * the records `clearScope` drops from that scope are removed before the restoration. A place or a
 * removal outside the holder is not part of that clearing, so the clearing leaves it as it is.
 *
 * A holder the tree does not render restores its official contents: a module the cleared projection
 * renders nowhere takes its official place again, which brings the courses inside it with it, and a
 * course the cleared projection does not render at its own node takes the place of that node again.
 * The move list reads the tree before this scope's records are cleared, so a course another programme
 * or module renders takes the holder's own place and is listed as a move from the node the tree shows
 * there, while a course that renders nowhere or directly in Unplaced studies is not listed.
 *
 * `pull` is whether the operation moves the listed courses in. A kept course holds the place it has
 * now: its own placement record stays as it stands, and no place is written for it, so the node that
 * renders it keeps it and the addition holds its official contents without it.
 */
export function holderPulls(
  afterTree: StructureNode,
  afterEdits: StructureEdits,
  holderNode: StructureNode,
  content: PlacedContent,
  present: boolean,
  pull = true,
): { edits: StructureEdits; moves: readonly PulledCourse[] } {
  // A moved holder keeps the whole current subtree it holds, so nothing changes around it.
  if (present) return { edits: afterEdits, moves: [] };
  const holderTree = resolveStructure(holderNode, emptyEdits(), NO_CONTENT);
  const holder = indexResolved(holderTree);
  const projectedTree = resolveStructure(afterTree, afterEdits, content);
  const projected = indexResolved(projectedTree);
  // The courses the holder's own rule renders in another node today, with the node that renders
  // each one: the move list reads the tree before this scope's records are cleared, so a course
  // another programme or module renders is asked about rather than silently reclaimed.
  const moves: PulledCourse[] = [];
  for (const node of new Set(holder.courseAt.values()))
    for (const { course } of node.courses) {
      const at = projected.courseAt.get(course.group_id);
      if (
        at === undefined ||
        at.node.kind === "unplaced" ||
        insideScope(holderNode.key, at.node.key)
      )
        continue;
      const displayed = courseSource(projectedTree, course.group_id);
      if (!displayed) throw new Error("Structure target is unavailable");
      moves.push({
        course,
        from: (language) => resolvedNodeLabel(displayed, language),
      });
    }
  let base = clearScope(afterEdits, holderNode.key);
  if (!pull) base = keepCoursePlacements(base, afterEdits, moves);
  const cleared = indexResolved(resolveStructure(afterTree, base, content));
  const modulePlacements: Record<string, string> = {};
  // The holder renders only after this operation, so its own modules take their official places
  // again, which brings the courses inside them with it.
  for (const [id, key] of moduleContainers(holderTree))
    if (!cleared.moduleAt.has(id)) modulePlacements[id] = key;
  // The restored modules render their own default courses, so the course places are read with them.
  const restored = indexResolved(
    resolveStructure(
      afterTree,
      {
        ...base,
        modulePlacements: {
          ...base.modulePlacements,
          ...modulePlacements,
        },
      },
      content,
    ),
  );
  const placements: Record<string, string> = {};
  const kept = new Set(moves.map(({ course }) => course.group_id));
  for (const [id, node] of holder.courseAt) {
    if (!restored.byKey.has(node.node.key)) continue;
    const placed = node.courses.find((item) => item.course.group_id === id);
    if (!placed) continue;
    // A kept course stays in the node that renders it now, so no place is written for it.
    if (!pull && kept.has(id)) continue;
    // A place is written only when the cleared tree does not render the course at its own node.
    if (cleared.courseAt.get(id)?.node.key === node.node.key) continue;
    placements[id] = node.node.key;
  }
  return {
    edits: {
      ...base,
      coursePlacements: { ...base.coursePlacements, ...placements },
      modulePlacements: { ...base.modulePlacements, ...modulePlacements },
    },
    moves,
  };
}

/**
 * Return edits with the listed courses' placement records kept as the previous edits hold them.
 *
 * A scope clear drops the placement record of a course whose official home is inside the cleared
 * scope, which is what returns that course to the scope. A kept course keeps the record it holds, so
 * the node that renders it outside the scope renders it exactly as it does now, and a course with no
 * record keeps none.
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
 * Return the courses one scope's reset returns to it from the nodes that render them now.
 *
 * The list compares the scope's current rendering with the rendering of the same tree under
 * `resetScope` for that scope, which is the record clearing the reset applies: a course is returned
 * when it renders outside the scope now and renders inside it once those records are gone. A course
 * that renders directly in Unplaced studies and a course another node renders through the official
 * rule, rather than through a record of its own, are not listed.
 */
export function scopePulls(
  root: StructureNode,
  edits: StructureEdits,
  content: PlacedContent,
  scopeKey: string,
): readonly PulledCourse[] {
  const beforeTree = resolveStructure(root, edits, content);
  const before = indexResolved(beforeTree);
  const cleared = indexResolved(
    resolveStructure(
      root,
      resetScope(edits, officialHomes(root, edits, content), scopeKey),
      content,
    ),
  );
  const pulls: PulledCourse[] = [];
  for (const node of before.byKey.values())
    for (const { course } of node.courses) {
      const id = course.group_id;
      if (node.node.kind === "unplaced" || insideScope(scopeKey, node.node.key))
        continue;
      const restored = cleared.courseAt.get(id);
      if (!restored || !insideScope(scopeKey, restored.node.key)) continue;
      const displayed = courseSource(beforeTree, id);
      if (!displayed) throw new Error("Structure target is unavailable");
      pulls.push({
        course,
        from: (language) => resolvedNodeLabel(displayed, language),
      });
    }
  return pulls;
}

/**
 * Place one module and return the edits of that placement with the courses it pulls.
 *
 * `from` is the node of the caller's own tree that renders the module now, or null when that tree
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
): { edits: StructureEdits; moves: readonly PulledCourse[] } {
  const next = placeModule(
    edits,
    officialHomes(root, edits, content),
    moduleId,
    targetKey,
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
  return holderPulls(
    root,
    moved,
    destination.node,
    content,
    source !== null,
    pull,
  );
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
 * A course the cleared scope held through an explicit placement now follows the ordinary removal
 * outcome of the action instead of falling back into a node the action leaves alone: a completed
 * course is placed in Unplaced studies, an uncompleted course is removed from the tree.
 */
export function clearedScopePlacements(
  affected: ResolvedNode,
  edits: StructureEdits,
  afterTree: StructureNode,
  afterEdits: StructureEdits,
  content: PlacedContent,
  clearedKey: string,
  touched: (key: string) => boolean,
  completedCourseIds: readonly string[],
): Record<string, string | null> {
  const placed = indexResolved(
    resolveStructure(afterTree, afterEdits, content),
  ).courseAt;
  const ids: string[] = [];
  for (const course of affected.subtree) {
    const id = course.group_id;
    const target = edits.coursePlacements[id];
    if (typeof target !== "string" || !insideScope(clearedKey, target))
      continue;
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

/** Return the edits with one scope's records cleared and its official homes restored. */
export function resetScope(
  edits: StructureEdits,
  homes: Homes,
  scopeKey: string,
): StructureEdits {
  const cleared = clearScope(edits, scopeKey);
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
 * that changes what this scope renders is. The comparison reads the rendered contents, owners and
 * notes and no history. The current target must resolve, and a restored target that the candidate
 * does not render counts as a difference.
 */
export function hasScopedEdits(
  root: StructureNode,
  edits: StructureEdits,
  content: PlacedContent,
  scopeKey: string,
): boolean {
  const current = indexResolved(
    resolveStructure(root, edits, content),
  ).byKey.get(scopeKey);
  if (!current) throw new Error("Structure target is unavailable");
  const candidate = holderPulls(
    root,
    edits,
    current.node,
    content,
    false,
  ).edits;
  const restored = indexResolved(
    resolveStructure(root, candidate, content),
  ).byKey.get(scopeKey);
  if (!restored) return true;
  return (
    JSON.stringify(scopeValue(current)) !== JSON.stringify(scopeValue(restored))
  );
}
