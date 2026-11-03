/** Read the app-level persistent discovery cache from the mounted provider. */
import { useContext } from "react";
import type { DiscoveryReportCache } from "./discoveryCache";
import { DiscoveryCacheContext } from "./discoveryCacheContext";

/** Read the discovery cache from context. */
export function useDiscoveryCache(): DiscoveryReportCache {
  const cache = useContext(DiscoveryCacheContext);
  if (!cache) throw new Error("Discovery cache provider is missing");
  return cache;
}
