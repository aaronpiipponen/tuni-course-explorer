/** Typed same-origin client for programme/module substring narrowing. */
import { postJson } from "./http";
import type { ModuleLookupReport, ModuleLookupRequest } from "./types";

export function lookupModules(
  request: ModuleLookupRequest,
  signal?: AbortSignal,
): Promise<ModuleLookupReport> {
  return postJson("/api/module-lookup", request, signal);
}
