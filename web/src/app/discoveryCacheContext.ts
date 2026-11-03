/** One provider of the persistent discovery report cache to the mounted shell. */
import { createContext } from "react";
import type { DiscoveryReportCache } from "./discoveryCache";

/** The persistent discovery report cache supplied to the mounted shell, or null outside a provider. */
export const DiscoveryCacheContext = createContext<DiscoveryReportCache | null>(
  null,
);
