/** Browser-owned ordered programmes, choices and canonical structure placements. */
export type StructureChoices = Record<string, readonly string[]>;
export const UNPLACED_KEY = "u";
export type StructureEdits = {
  choices: StructureChoices;
  coursePlacements: Record<string, string | null>;
  modulePlacements: Record<string, string | null>;
};
export type StructureState = StructureEdits & {
  /** Top-level programme group ids in the order the interface shows them. */
  programmeGroupIds: string[];
  placedCourseIds: string[];
};
export const emptyEdits = (): StructureEdits => ({
  choices: {},
  coursePlacements: {},
  modulePlacements: {},
});
export const initialStructureState = (): StructureState => ({
  programmeGroupIds: [],
  ...emptyEdits(),
  placedCourseIds: [],
});
