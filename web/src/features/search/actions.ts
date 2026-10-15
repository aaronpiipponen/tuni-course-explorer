/** Search control actions use the sole browser-store persistence path. */
import type { BrowserStore } from "../../state/store";

export function setSearchQuery(store: BrowserStore, query: string): void {
  store.updateCurrent((state) => ({
    ...state,
    search: { ...state.search, query },
  }));
}

export function setSearchActiveOnly(
  store: BrowserStore,
  activeOnly: boolean,
): void {
  store.updateCurrent((state) => ({
    ...state,
    search: { ...state.search, activeOnly },
  }));
}
