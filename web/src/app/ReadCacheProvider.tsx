/** Bootstrap provider of the one bounded read cache shared by every mounted tab pane. */
import { useState, type ReactNode } from "react";
import { READ_CACHE_CAPACITY, ReadCache } from "./readCache";
import { ReadCacheContext } from "./readCacheContext";

/** Provide one dataset-scoped read cache to the mounted tab panes. */
export function ReadCacheProvider({
  datasetIdentity,
  children,
}: {
  datasetIdentity: string;
  children: ReactNode;
}) {
  // One cache lives for the provider's lifetime, so it survives tab and profile changes.
  const [cache] = useState(
    () => new ReadCache(datasetIdentity, READ_CACHE_CAPACITY),
  );
  return (
    <ReadCacheContext.Provider value={cache}>
      {children}
    </ReadCacheContext.Provider>
  );
}
