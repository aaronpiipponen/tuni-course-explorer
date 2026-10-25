/** Proof that the machine request dispatcher rejects an unknown machine operation. */
import { describe, expect, it } from "vitest";
import { runRequest, type SolverRequest } from "./request";

describe("request", () => {
  it("rejects an unknown machine operation", () => {
    expect(() =>
      runRequest({ operation: "unknown" } as unknown as SolverRequest),
    ).toThrow();
  });
});
