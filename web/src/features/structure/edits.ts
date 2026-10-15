/** Pure canonical placement edits and scoped customization reset. */
import type { StructureEdits } from "./state";
import type { PlacedContent, StructureNode } from "./model";
import {
  resolveStructure,
  indexResolved,
  officialHomes,
  NO_CONTENT,
} from "./model";
import { emptyEdits } from "./state";

type Homes = ReadonlyMap<string, readonly string[]>;

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

export const placeCourse = (
  edits: StructureEdits,
  homes: Homes,
  id: string,
  target: string | null,
) => place(edits, "coursePlacements", homes, id, target);

export const placeModule = (
  edits: StructureEdits,
  homes: Homes,
  id: string,
  target: string | null,
) => place(edits, "modulePlacements", homes, id, target);

export function placeModuleWithCourses(
  root: StructureNode,
  edits: StructureEdits,
  content: PlacedContent,
  moduleId: string,
  targetKey: string,
  placedCourseIds: readonly string[],
): { edits: StructureEdits; movedCourseCount: number } {
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
  const mandatory = resolveStructure(
    destination.node,
    emptyEdits(),
    NO_CONTENT,
  );
  const hosts = indexResolved(mandatory).courseAt;
  const placements = { ...next.coursePlacements };
  let movedCourseCount = 0;
  for (const id of placedCourseIds) {
    const host = hosts.get(id);
    if (host) {
      placements[id] = host.node.key;
      movedCourseCount += 1;
    }
  }
  return { edits: { ...next, coursePlacements: placements }, movedCourseCount };
}

export function resetScope(
  edits: StructureEdits,
  homes: Homes,
  scopeKey: string,
): StructureEdits {
  const inScope = (key: string) =>
    key === scopeKey || key.startsWith(`${scopeKey}/`);
  return {
    choices: Object.fromEntries(
      Object.entries(edits.choices).filter(([key]) => !inScope(key)),
    ),
    coursePlacements: Object.fromEntries(
      Object.entries(edits.coursePlacements).filter(
        ([id, target]) =>
          !(typeof target === "string" && inScope(target)) &&
          !(homes.get(id) ?? []).some(inScope),
      ),
    ),
    modulePlacements: Object.fromEntries(
      Object.entries(edits.modulePlacements).filter(
        ([id, target]) =>
          !(typeof target === "string" && inScope(target)) &&
          !(homes.get(id) ?? []).some(inScope),
      ),
    ),
  };
}
