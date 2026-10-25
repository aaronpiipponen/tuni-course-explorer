/** Search control actions use the sole browser-store persistence path. */
import type { BrowserStore } from "../../state/store";

/** Store the search query in the current profile. */
export function setSearchQuery(store: BrowserStore, query: string): void {
  store.updateCurrent((state) => ({
    ...state,
    search: { ...state.search, query },
  }));
}

/** Store the search activity scope in the current profile. */
export function setSearchActiveOnly(
  store: BrowserStore,
  activeOnly: boolean,
): void {
  store.updateCurrent((state) => ({
    ...state,
    search: { ...state.search, activeOnly },
  }));
}
