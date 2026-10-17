/** Shared Unplaced studies addition used by every course card and both add-all actions. */
import { useContext } from "react";
import { StoreContext } from "../../state/context";
import { addCoursesToFreeChoice } from "../../state/course-actions";
export function useFreeChoiceAdd(): { add(ids: readonly string[]): void } {
  const store = useContext(StoreContext);
  if (!store) throw new Error("Browser store provider is missing");
  return {
    add: (ids: readonly string[]) => addCoursesToFreeChoice(store, ids),
  };
}
