/** Compare's profile-owned controls and canonical course slots. */
import type { CourseId } from "../../state/types";

/** Persistent comparison controls and canonical course slots. */
export type CompareState = {
  slots: [CourseId | null, CourseId | null];
  pickerQuery: string;
  pickerActiveOnly: boolean;
};
/** Build the initial comparison state. */
export const initialCompareState = (): CompareState => ({
  slots: [null, null],
  pickerQuery: "",
  pickerActiveOnly: true,
});
