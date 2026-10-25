/** Activity-only module shortfalls that keep every strict failure strict. */
import { describe, expect, it } from "vitest";
import failures from "./fixtures/route-module-failures.json";
import { calculateMinimumNewCredits } from "./route";
import {
  creditsOf,
  loadStructure,
  selectedGroupIds,
  type RouteFixtures,
} from "./route-test-support";

const fixtures = failures as unknown as RouteFixtures;
const prefix =
  "active_module_shortfall_is_activity_only_and_preserves_strict_failures";

describe("route module failures", () => {
  it("active module shortfall is activity only and preserves strict failures", () => {
    const allCourses = calculateMinimumNewCredits(
      loadStructure(fixtures, `${prefix}.all_courses`),
      [],
    );
    expect(allCourses.state).toBe("exact");
    expect(selectedGroupIds(allCourses)).toEqual(["active-a", "inactive-b"]);
    expect(creditsOf(allCourses.total_new_credits)).toBe(1200);
    expect(allCourses.shortfalls).toEqual([]);

    const ordinary = calculateMinimumNewCredits(
      loadStructure(fixtures, `${prefix}.ordinary`),
      [],
    );
    expect(ordinary.state).toBe("no_solution");
    expect(ordinary.shortfalls).toEqual([]);

    const impossible = calculateMinimumNewCredits(
      loadStructure(fixtures, `${prefix}.impossible`),
      [],
    );
    expect(impossible.state).toBe("no_solution");
    expect(impossible.shortfalls).toEqual([]);

    const tooHigh = calculateMinimumNewCredits(
      loadStructure(fixtures, `${prefix}.too_high`),
      [],
    );
    expect(tooHigh.state).toBe("no_solution");
    expect(tooHigh.shortfalls).toEqual([]);

    const withUnresolved = calculateMinimumNewCredits(
      loadStructure(fixtures, `${prefix}.module_with_unresolved`),
      [],
    );
    expect(withUnresolved.state).toBe("unresolved");
    expect(withUnresolved.shortfalls).toEqual([]);

    const cyclic = calculateMinimumNewCredits(
      loadStructure(fixtures, `${prefix}.cyclic`),
      [],
    );
    expect(cyclic.state).toBe("unresolved");
    expect(cyclic.shortfalls).toEqual([]);

    const nestedOrdinary = calculateMinimumNewCredits(
      loadStructure(fixtures, `${prefix}.nested_ordinary`),
      [],
    );
    expect(nestedOrdinary.state).toBe("no_solution");
    expect(nestedOrdinary.shortfalls).toEqual([]);

    const numeric = calculateMinimumNewCredits(
      loadStructure(fixtures, `${prefix}.numeric_compilation`),
      [],
    );
    expect(numeric.state).toBe("no_solution");
    expect(numeric.shortfalls).toEqual([]);

    const outerCredit = calculateMinimumNewCredits(
      loadStructure(fixtures, `${prefix}.outer_credit`),
      [],
    );
    expect(outerCredit.state).toBe("no_solution");
    expect(outerCredit.shortfalls).toEqual([]);

    const exactWins = calculateMinimumNewCredits(
      loadStructure(fixtures, `${prefix}.exact_wins`),
      [],
    );
    expect(exactWins.state).toBe("exact");
    expect(selectedGroupIds(exactWins)).toEqual(["active-a"]);
    expect(exactWins.shortfalls).toEqual([]);

    const excluded = calculateMinimumNewCredits(
      loadStructure(fixtures, `${prefix}.excluded`),
      [],
    );
    expect(excluded.state).toBe("no_solution");
    expect(excluded.shortfalls).toEqual([]);
    expect(excluded.blocked_excluded_group_ids).toEqual(["module-unit"]);
  });
});
