/** Typed same-origin client for the site's served feature switches. */
import { postJson } from "./http";
import type { WebFeatures } from "./types";

/** Read the site's feature switches and dataset identity. */
export function readWebFeatures(signal?: AbortSignal): Promise<WebFeatures> {
  return postJson<WebFeatures>("/api/features", {}, signal);
}
