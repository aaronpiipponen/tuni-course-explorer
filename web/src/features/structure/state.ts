/** Browser-owned root, choices and canonical structure placements. */
export type StructureChoices = Record<string, readonly string[]>;
export const UNPLACED_KEY = "u";
export type StructureEdits = {
  choices: StructureChoices;
  coursePlacements: Record<string, string | null>;
  modulePlacements: Record<string, string | null>;
};
export type StructureState = StructureEdits & {
  rootGroupId: string | null;
  placedCourseIds: string[];
};
export const emptyEdits = (): StructureEdits => ({
  choices: {},
  coursePlacements: {},
  modulePlacements: {},
});
export const initialStructureState = (): StructureState => ({
  rootGroupId: null,
  ...emptyEdits(),
  placedCourseIds: [],
});
