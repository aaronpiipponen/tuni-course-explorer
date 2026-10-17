/** One shared reader for the operating system's reduced-motion preference. */
import { useSyncExternalStore } from "react";

const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";

// One MediaQueryList serves every reader. It is created on the first client snapshot or
// subscription, so nothing touches a browser API during static server rendering.
let motionQuery: MediaQueryList | null = null;

function query(): MediaQueryList {
  motionQuery ??= window.matchMedia(REDUCED_MOTION_QUERY);
  return motionQuery;
}

function subscribe(onStoreChange: () => void): () => void {
  const list = query();
  list.addEventListener("change", onStoreChange);
  return () => list.removeEventListener("change", onStoreChange);
}

function getSnapshot(): boolean {
  return query().matches;
}

function getServerSnapshot(): boolean {
  return false;
}

/** Report whether the operating system asks for reduced motion. */
export function useReducedMotion(): boolean {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
