/** Bootstrap provider of the one persistent discovery cache of the serving dataset. */
import { useState, type ReactNode } from "react";
import { DiscoveryReportCache } from "./discoveryCache";
import { DiscoveryCacheContext } from "./discoveryCacheContext";

/** Provide one discovery cache to the discovery surfaces. */
export function DiscoveryCacheProvider({
  datasetIdentity,
  children,
}: {
  datasetIdentity: string;
  children: ReactNode;
}) {
  const [cache] = useState(
    () =>
      new DiscoveryReportCache(
        datasetIdentity,
        typeof window === "undefined" ? null : window.localStorage,
      ),
  );
  return (
    <DiscoveryCacheContext.Provider value={cache}>
      {children}
    </DiscoveryCacheContext.Provider>
  );
}
