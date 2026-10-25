/** The machine request dispatcher over the wire structures the server writes. */
import { describe, expect, it } from "vitest";
import minimum from "./fixtures/route-minimum.json";
import { runRequest, type SolverRequest } from "./request";
import { calculateMinimumNewCredits } from "./route";
import { loadStructure, type RouteFixtures } from "./route-test-support";

const routeFixtures = minimum as unknown as RouteFixtures;

describe("request", () => {
  it("dispatches route requests to the shared solver", () => {
    const structure = loadStructure(
      routeFixtures,
      "bounded_unknown_extent_with_unpaid_sibling_is_unresolved.tree",
    );
    expect(
      runRequest({
        operation: "route",
        structure,
        basis_group_ids: [],
        max_compact_nodes: null,
      }),
    ).toEqual(calculateMinimumNewCredits(structure, [], null));

    expect(() =>
      runRequest({ operation: "unknown" } as unknown as SolverRequest),
    ).toThrow();
  });
});
