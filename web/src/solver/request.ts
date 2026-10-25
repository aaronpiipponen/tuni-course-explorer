/** Dispatch one machine solver request over one written solver structure. */
import type { SolverStructure } from "../api/types";
import { calculateMinimumNewCredits, type MinimumRoute } from "./route";

/** One machine solver request: the explicit minimum route. */
export type SolverRequest = {
  operation: "route";
  structure: SolverStructure;
  basis_group_ids: readonly string[];
  max_compact_nodes: number | null;
};

/**
 * Return the minimum route of one request.
 *
 * An operation other than `route` throws, because the request arrives as parsed JSON and its
 * operation is not checked by any type at the process boundary.
 */
export function runRequest(request: SolverRequest): MinimumRoute {
  if (request.operation === "route") {
    return calculateMinimumNewCredits(
      request.structure,
      request.basis_group_ids,
      request.max_compact_nodes,
    );
  }
  throw new Error(
    `unknown solver operation ${String((request as { operation: unknown }).operation)}`,
  );
}
