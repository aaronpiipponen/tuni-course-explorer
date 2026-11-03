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
/** One placed course's holder: the module or programme that renders it. */
export type CourseHolder = {
  group_id: string;
  name_fi: string | null;
  name_en: string | null;
};
/** The edits plus the programme order, exact module versions, placed courses and card order. */
export type StructureState = StructureEdits & {
  /** Top-level programme group ids in the order the interface shows them. */
  programmeGroupIds: string[];
  /** One exact official version per canonical module group that needed an explicit selection. */
  moduleVersions: Record<string, string>;
  placedCourseIds: string[];
  /** Each placed course's holder, kept so every surface can name it without the tree. */
  courseHolders?: Record<string, CourseHolder>;
  /** Canonical course ids in the order the visible grids show them across holders. */
  courseOrder: string[];
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
  courseOrder: [],
});
