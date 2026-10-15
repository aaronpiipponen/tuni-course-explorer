/** Atomic browser structure projection and scoped Unplaced studies reset actions. */
import type { BrowserStore } from "../../state/store";
import type { CourseId } from "../../state/types";
import type { StructureEdits } from "./state";
import { UNPLACED_KEY } from "./state";
import {
  indexResolved,
  officialHomes,
  resolveStructure,
  type PlacedContent,
  type StructureNode,
} from "./model";

export function applyStructure(
  store: BrowserStore,
  next: StructureEdits & {
    rootGroupId: string;
    placedCourseIds: readonly string[];
  },
  removedCourseIds: readonly CourseId[] = [],
  discardUncompletedCourseIds: readonly CourseId[] = [],
): void {
  store.updateCurrent((state) => {
    const previous = state.structure.placedCourseIds;
    const completed = new Set(state.completedCourseIds);
    const keep = new Set(next.placedCourseIds);
    const dropped = new Set(
      previous.filter((id) => !keep.has(id) && !completed.has(id)),
    );
    for (const id of discardUncompletedCourseIds)
      if (!completed.has(id)) dropped.add(id);
    const explicitlyRemoved = new Set(removedCourseIds);
    const selected = state.selectedCourseIds.filter(
      (id) => !dropped.has(id) && !explicitlyRemoved.has(id),
    );
    const seen = new Set(selected);
    for (const id of next.placedCourseIds)
      if (!seen.has(id)) {
        seen.add(id);
        selected.push(id);
      }
    return {
      ...state,
      selectedCourseIds: selected,
      completedCourseIds: state.completedCourseIds.filter(
        (id) => !explicitlyRemoved.has(id),
      ),
      structure: {
        rootGroupId: next.rootGroupId,
        choices: next.choices,
        coursePlacements: next.coursePlacements,
        modulePlacements: next.modulePlacements,
        placedCourseIds: [...next.placedCourseIds],
      },
    };
  });
}

export function resetUnplaced(
  store: BrowserStore,
  tree: StructureNode,
  content: PlacedContent,
): void {
  const snapshot = store.getSnapshot();
  const state = snapshot.profiles[snapshot.currentProfileId].state;
  const edits = state.structure;
  const resolved = resolveStructure(tree, edits, content);
  const indexed = indexResolved(resolved);
  const bucket = indexed.byKey.get(UNPLACED_KEY);
  const discard = [
    ...(bucket?.subtree.map((course) => course.group_id) ?? []),
    ...state.selectedCourseIds.filter(
      (id) => !resolved.subtree.some((course) => course.group_id === id),
    ),
  ];
  const homes = officialHomes(tree, edits, content);
  const inBucket = (key: string) =>
    key === UNPLACED_KEY || key.startsWith(`${UNPLACED_KEY}/`);
  const resetPlacements = (placements: Record<string, string | null>) => {
    const retained: Record<string, string | null> = {};
    for (const [id, target] of Object.entries(placements)) {
      if (target === null) {
        if ((homes.get(id) ?? []).some((home) => !inBucket(home)))
          retained[id] = null;
        continue;
      }
      if (!inBucket(target)) retained[id] = target;
      else if ((homes.get(id) ?? []).some((home) => !inBucket(home)))
        retained[id] = null;
    }
    return retained;
  };
  const next: StructureEdits = {
    choices: Object.fromEntries(
      Object.entries(edits.choices).filter(([key]) => !inBucket(key)),
    ),
    coursePlacements: resetPlacements(edits.coursePlacements),
    modulePlacements: resetPlacements(edits.modulePlacements),
  };
  const projection = resolveStructure(tree, next, content);
  applyStructure(
    store,
    {
      rootGroupId: edits.rootGroupId ?? "",
      ...next,
      placedCourseIds: projection.subtree.map((course) => course.group_id),
    },
    [],
    discard,
  );
}
export function removeFromSelection(
  store: BrowserStore,
  courseId: CourseId,
): void {
  store.updateCurrent((state) => ({
    ...state,
    selectedCourseIds: state.selectedCourseIds.filter((id) => id !== courseId),
    completedCourseIds: state.completedCourseIds.filter(
      (id) => id !== courseId,
    ),
  }));
}
