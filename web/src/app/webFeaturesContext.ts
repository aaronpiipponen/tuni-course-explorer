/** One provider of the site's served feature switches to the mounted app shell. */
import { createContext } from "react";
import type { WebFeatures } from "../api/types";

export const WebFeaturesContext = createContext<WebFeatures | null>(null);
