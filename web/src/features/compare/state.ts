/** Compare's profile-owned controls and canonical course slots. */
import type { CourseId } from "../../state/types";

export type CompareState = {
  slots: [CourseId | null, CourseId | null];
  pickerQuery: string;
  pickerActiveOnly: boolean;
};
export const initialCompareState = (): CompareState => ({
  slots: [null, null],
  pickerQuery: "",
  pickerActiveOnly: true,
});
