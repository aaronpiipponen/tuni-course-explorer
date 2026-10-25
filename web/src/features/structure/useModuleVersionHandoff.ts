/**
 * One module-version hand-off for a lookup surface: the selected ambiguous group, its Cancel
 * control, direct single-candidate activation and explicit pick.
 *
 * The hand-off writes nothing until a candidate is selected. A changed reset key clears the
 * selection, and Cancel returns focus to the surface's own query input.
 */
import { useEffect, useRef, useState } from "react";
import type { RefObject } from "react";
import type { CatalogueModule, ModuleLookupGroup } from "../../api/types";

/** Return the hand-off state and operations one lookup surface renders. */
export function useModuleVersionHandoff(
  onPick: (module: CatalogueModule) => void,
  inputRef: RefObject<HTMLInputElement | null>,
  resetKey: string,
): {
  group: ModuleLookupGroup | null;
  cancelRef: RefObject<HTMLButtonElement | null>;
  activate(target: ModuleLookupGroup): void;
  pick(module: CatalogueModule): void;
  cancel(): void;
} {
  const [group, setGroup] = useState<ModuleLookupGroup | null>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    setGroup(null);
  }, [resetKey]);
  useEffect(() => {
    // The activated row leaves the results, so focus moves to the hand-off's first control.
    if (group) cancelRef.current?.focus();
  }, [group]);
  const pick = (module: CatalogueModule) => {
    setGroup(null);
    onPick(module);
  };
  /**
   * Pick the only eligible version of a group at once, or hand an ambiguous group to the picker.
   *
   * The search row never chooses a version itself.
   */
  const activate = (target: ModuleLookupGroup) => {
    if (target.candidates.length === 1) {
      onPick({ group_id: target.group_id, ...target.candidates[0] });
      return;
    }
    setGroup(target);
  };
  const cancel = () => {
    setGroup(null);
    inputRef.current?.focus();
  };
  return { group, cancelRef, activate, pick, cancel };
}
