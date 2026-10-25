/** Typed same-origin client for the minimal official catalogue. */
import { postJson } from "./http";
import type { CatalogueReport } from "./types";

/** Read the served official catalogue. */
export function readCatalogue(signal?: AbortSignal): Promise<CatalogueReport> {
  return postJson<CatalogueReport>("/api/catalogue", {}, signal);
}
