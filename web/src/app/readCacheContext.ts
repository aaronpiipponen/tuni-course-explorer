/** One provider of the app-level bounded read cache to the mounted tab panes. */
import { createContext } from "react";
import type { ReadCache } from "./readCache";

/** React context carrying the app-level read cache. */
export const ReadCacheContext = createContext<ReadCache | null>(null);
