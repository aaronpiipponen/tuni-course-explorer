/** React context for the single bootstrapped browser store. */
import { createContext } from "react";
import type { BrowserStore } from "./store";

/** React context carrying the bootstrapped browser store. */
export const StoreContext = createContext<BrowserStore | null>(null);
