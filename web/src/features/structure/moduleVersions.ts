/**
 * Per-profile selection identity, requested-root derivation and removal-scoped forgetting for
 * official structure reads.
 *
 * `moduleVersionKey` is the canonical identity of one group-to-version map under a dataset, so a
 * memory or persisted report can never answer another selection. `structureRootGroupIds` names the
 * closure a programme or module operation reads under a prospective selection: every ordered
 * programme, every placed module with a string target, and its own candidate group.
 * `forgetRemovedModuleVersions` drops the entries of the groups one operation removes.
 */
import { compareCodePoints } from "../../shared/course/narrowing";
import type { ResolvedNode } from "./model";
import type { StructureState } from "./state";

/** Return the canonical JSON identity of one per-profile group-to-version map. */
export function moduleVersionKey(
  versions: Readonly<Record<string, string>>,
): string {
  return JSON.stringify(
    Object.entries(versions).sort(([left], [right]) =>
      compareCodePoints(left, right),
    ),
  );
}

/** Return every root a programme or module operation reads under a prospective selection. */
export function structureRootGroupIds(
  structure: StructureState,
  candidateGroupId: string,
): string[] {
  const placedModules = Object.entries(structure.modulePlacements)
    .filter(([, target]) => typeof target === "string")
    .map(([id]) => id);
  return [
    ...new Set([
      ...structure.programmeGroupIds,
      ...placedModules,
      candidateGroupId,
    ]),
  ];
}

/** Return the groups one resolved tree renders as a module node. */
function renderedGroupIds(root: ResolvedNode): Set<string> {
  const groups = new Set<string>();
  const walk = (node: ResolvedNode) => {
    if (node.node.module) groups.add(node.node.module.group_id);
    node.children.forEach(walk);
  };
  walk(root);
  return groups;
}

/**
 * Return the selection map without the entries of the groups the resulting tree does not render.
 *
 * Only groups that the starting tree renders and the resulting tree does not are forgotten, so a
 * saved selection for a group the starting tree does not render keeps its entry.
 */
export function forgetRemovedModuleVersions(
  versions: Readonly<Record<string, string>>,
  before: ResolvedNode,
  after: ResolvedNode,
): Record<string, string> {
  const present = renderedGroupIds(after);
  const removed = [...renderedGroupIds(before)].filter(
    (groupId) => !present.has(groupId),
  );
  const next = { ...versions };
  for (const groupId of removed) delete next[groupId];
  return next;
}
