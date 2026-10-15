/** Typed same-origin client for the explicit minimum-route operation. */
import { postJson } from "./http";
import type { PrerequisitePath, PrerequisitesRequest } from "./types";

export function readMinimumRoute(
  request: PrerequisitesRequest,
  signal?: AbortSignal,
): Promise<PrerequisitePath> {
  return postJson("/api/minimum-route", request, signal);
}
