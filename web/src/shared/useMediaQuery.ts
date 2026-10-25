/** One client media-query reader for the app's width-dependent behaviour. */
import { useCallback, useMemo, useSyncExternalStore } from "react";

/**
 * Report whether the client matches `query`.
 *
 * The list is created during the render that first reads it, and the server snapshot is false, so
 * a static render touches no browser API. The subscription is removed on unmount or a query change.
 */
export function useMediaQuery(query: string): boolean {
  const list = useMemo(
    () =>
      typeof window === "undefined" || typeof window.matchMedia !== "function"
        ? null
        : window.matchMedia(query),
    [query],
  );
  const subscribe = useCallback(
    (onChange: () => void) => {
      if (list === null) return () => {};
      list.addEventListener("change", onChange);
      return () => list.removeEventListener("change", onChange);
    },
    [list],
  );
  const getSnapshot = useCallback(() => list?.matches ?? false, [list]);
  return useSyncExternalStore(subscribe, getSnapshot, () => false);
}
