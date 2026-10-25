/** Discover control mutations use the sole browser-store persistence path. */
import type { BrowserStore } from "../../state/store";
import type { DiscoverState } from "./state";

/** Merge one discovery control patch into the current profile. */
export function setDiscoverOptions(
  store: BrowserStore,
  patch: Partial<DiscoverState>,
): void {
  store.updateCurrent((state) => ({
    ...state,
    discover: { ...state.discover, ...patch },
  }));
}
