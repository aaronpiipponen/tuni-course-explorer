/** Read the app-level bounded read cache from the mounted provider. */
import { useContext } from "react";
import type { ReadCache } from "./readCache";
import { ReadCacheContext } from "./readCacheContext";

/** Read the app-level cache from context. */
export function useReadCache(): ReadCache {
  const cache = useContext(ReadCacheContext);
  if (!cache) throw new Error("Read cache provider is missing");
  return cache;
}
