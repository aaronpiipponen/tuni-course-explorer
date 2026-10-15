/** Root-aware selected-set addition shared by card and both add-all actions. */
import { useRef, useState, type ReactNode } from "react";
import { useProfileSelector } from "../../state/useProfileSelector";
import { addCoursesToFreeChoice } from "../../state/course-actions";
import { RootPromptDialog } from "./RootPromptDialog";

export function useFreeChoiceAdd(returnFocus?: () => void): {
  add(ids: readonly string[]): void;
  prompt: ReactNode;
  promptOpen: boolean;
} {
  const { store, value: rootGroupId } = useProfileSelector(
    (state) => state.structure.rootGroupId,
  );
  const [pending, setPending] = useState<readonly string[]>([]);
  const fallbackFocus = useRef<() => void>(() => {});
  const add = (ids: readonly string[]) => {
    if (rootGroupId !== null) addCoursesToFreeChoice(store, ids);
    else {
      fallbackFocus.current = returnFocus ?? (() => {});
      setPending([...ids]);
    }
  };
  const open = pending.length > 0;
  const clear = () => setPending([]);
  return {
    add,
    promptOpen: open,
    prompt: (
      <RootPromptDialog
        open={open}
        count={pending.length}
        returnFocus={() => fallbackFocus.current()}
        onCancel={clear}
        onChosen={() => {
          addCoursesToFreeChoice(store, pending);
          clear();
        }}
      />
    ),
  };
}
