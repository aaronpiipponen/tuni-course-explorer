/** Discover control mutations use the sole browser-store persistence path. */
import type { BrowserStore } from "../../state/store";
import type { DiscoverState } from "./state";

export function setDiscoverOptions(
  store: BrowserStore,
  patch: Partial<DiscoverState>,
): void {
  store.updateCurrent((state) => ({
    ...state,
    discover: { ...state.discover, ...patch },
  }));
}
