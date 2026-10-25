/** Live-profile external-store subscription preserving selected reference identity. */
import { useCallback, useContext, useSyncExternalStore } from "react";
import type { ProfileState } from "./types";
import type { BrowserStore } from "./store";
import { StoreContext } from "./context";

/** Subscribe to one selected value from the current profile. */
export function useProfileSelector<T>(selector: (state: ProfileState) => T): {
  store: BrowserStore;
  value: T;
} {
  const store = useContext(StoreContext);
  if (!store) throw new Error("Browser store provider is missing");
  const getSelected = useCallback(() => {
    const snapshot = store.getSnapshot();
    const profile = snapshot.profiles[snapshot.currentProfileId];
    if (!profile) throw new Error("Current browser profile is unavailable");
    return selector(profile.state);
  }, [store, selector]);
  const value = useSyncExternalStore(store.subscribe, getSelected, getSelected);
  return { store, value };
}
