/** Typed same-origin client for the site's served feature switches. */
import { postJson } from "./http";
import type { WebFeatures } from "./types";

export function readWebFeatures(signal?: AbortSignal): Promise<WebFeatures> {
  return postJson<WebFeatures>("/api/features", {}, signal);
}
