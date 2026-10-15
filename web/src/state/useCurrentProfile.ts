/** React subscription to the one current profile owned by the shared browser store. */
import { useContext, useSyncExternalStore } from "react";
import { StoreContext } from "./context";

export function useCurrentProfile() {
  const store = useContext(StoreContext);
  if (!store) throw new Error("Browser store provider is missing");
  const snapshot = useSyncExternalStore(
    store.subscribe,
    store.getSnapshot,
    store.getSnapshot,
  );
  const profile = snapshot.profiles[snapshot.currentProfileId];
  if (!profile) throw new Error("Current browser profile is unavailable");
  return {
    store,
    profile,
    currentProfileId: snapshot.currentProfileId,
    profiles: snapshot.profiles,
  };
}

export function useCurrentProfileId(): string {
  const store = useContext(StoreContext);
  if (!store) throw new Error("Browser store provider is missing");
  return useSyncExternalStore(
    store.subscribe,
    () => store.getSnapshot().currentProfileId,
    () => store.getSnapshot().currentProfileId,
  );
}
