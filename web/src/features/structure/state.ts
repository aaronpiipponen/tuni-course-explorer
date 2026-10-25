/** Browser-owned ordered programmes, choices, canonical placements and exact module versions. */

/** The chosen option keys per rule node key. */
export type StructureChoices = Record<string, readonly string[]>;
/** The node key of Unplaced studies. */
export const UNPLACED_KEY = "u";
/** The browser edits of the structure: its choices and canonical placements. */
export type StructureEdits = {
  choices: StructureChoices;
  coursePlacements: Record<string, string | null>;
  modulePlacements: Record<string, string | null>;
};
/** The edits plus the programme order, exact module versions and placed courses. */
export type StructureState = StructureEdits & {
  /** Top-level programme group ids in the order the interface shows them. */
  programmeGroupIds: string[];
  /** One exact official version per canonical module group that needed an explicit selection. */
  moduleVersions: Record<string, string>;
  placedCourseIds: string[];
};
/** Return the edits with no choices and no placements. */
export const emptyEdits = (): StructureEdits => ({
  choices: {},
  coursePlacements: {},
  modulePlacements: {},
});
/** Build the initial structure state. */
export const initialStructureState = (): StructureState => ({
  programmeGroupIds: [],
  ...emptyEdits(),
  moduleVersions: {},
  placedCourseIds: [],
});
