/** Active module shortfall maxima across every module rule family. */
import { describe, expect, it } from "vitest";
import shortfall from "./fixtures/route-module-shortfall.json";
import { calculateMinimumNewCredits } from "./route";
import {
  creditsOf,
  loadStructure,
  selectedGroupIds,
  type RouteFixtures,
} from "./route-test-support";

const fixtures = shortfall as unknown as RouteFixtures;
const prefix = "active_module_shortfall_returns_maximum_for_all_rule_families";

describe("route module shortfall", () => {
  it("active module shortfall returns maximum for all rule families", () => {
    const bare = calculateMinimumNewCredits(
      loadStructure(fixtures, `${prefix}.bare`),
      [],
    );
    expect(bare.state).toBe("shortfall");
    expect(bare.satisfaction.requirements_state).toBe("unsatisfied");
    expect(bare.satisfaction.active_only).toBe(true);
    expect(selectedGroupIds(bare)).toEqual([]);
    expect(creditsOf(bare.total_new_credits)).toBe(0);
    expect(bare.blockers).toEqual([]);
    expect(
      bare.shortfalls.map((entry) => [
        entry.kind,
        entry.required_count,
        entry.achieved_count,
        entry.count_deficit,
      ]),
    ).toEqual([["all_mandatory", 1, 0, 1]]);
    expect(
      bare.shortfalls[0].node_id.startsWith("s:") ||
        bare.shortfalls[0].node_id.startsWith("course:"),
    ).toBe(true);

    const allMandatory = calculateMinimumNewCredits(
      loadStructure(fixtures, `${prefix}.all_mandatory`),
      [],
    );
    expect(allMandatory.state).toBe("shortfall");
    expect(selectedGroupIds(allMandatory)).toEqual(["active-a"]);
    expect(creditsOf(allMandatory.total_new_credits)).toBe(300);
    expect(
      allMandatory.shortfalls.map((entry) => [
        entry.kind,
        entry.required_count,
        entry.achieved_count,
        entry.count_deficit,
      ]),
    ).toEqual([["all_mandatory", 2, 1, 1]]);

    const mixed = calculateMinimumNewCredits(
      loadStructure(fixtures, `${prefix}.mixed`),
      [],
    );
    expect(mixed.state).toBe("shortfall");
    expect(selectedGroupIds(mixed)).toEqual(["active-nested"]);
    expect(creditsOf(mixed.total_new_credits)).toBe(400);
    expect(mixed.shortfalls.map((entry) => entry.kind)).toEqual([
      "all_mandatory",
      "cardinality",
    ]);
    expect(
      mixed.shortfalls.every(
        (entry) =>
          entry.node_id.startsWith("s:") || entry.node_id.startsWith("course:"),
      ),
    ).toBe(true);
    const parentEntry = mixed.shortfalls[0];
    expect([parentEntry.required_count, parentEntry.achieved_count]).toEqual([
      2, 1,
    ]);
    expect(parentEntry.count_deficit).toBe(1);
    const nestedEntry = mixed.shortfalls[1];
    expect([nestedEntry.required_count, nestedEntry.achieved_count]).toEqual([
      2, 1,
    ]);
    expect(nestedEntry.count_deficit).toBe(1);

    const nestedOnly = calculateMinimumNewCredits(
      loadStructure(fixtures, `${prefix}.nested_only`),
      [],
    );
    expect(nestedOnly.state).toBe("shortfall");
    expect(selectedGroupIds(nestedOnly)).toEqual([
      "active-nested",
      "active-ok",
    ]);
    expect(creditsOf(nestedOnly.total_new_credits)).toBe(600);
    expect(
      nestedOnly.shortfalls.map((entry) => [
        entry.kind,
        entry.required_count,
        entry.achieved_count,
      ]),
    ).toEqual([["cardinality", 2, 1]]);

    const cardinality = calculateMinimumNewCredits(
      loadStructure(fixtures, `${prefix}.cardinality`),
      [],
    );
    expect(cardinality.state).toBe("shortfall");
    expect(selectedGroupIds(cardinality)).toEqual(["active-a"]);
    expect(creditsOf(cardinality.total_new_credits)).toBe(500);
    const cardinalityEntry = cardinality.shortfalls[0];
    expect(cardinalityEntry.kind).toBe("cardinality");
    expect(
      cardinalityEntry.node_id.startsWith("s:") ||
        cardinalityEntry.node_id.startsWith("course:"),
    ).toBe(true);
    expect([
      cardinalityEntry.required_count,
      cardinalityEntry.achieved_count,
      cardinalityEntry.count_deficit,
    ]).toEqual([2, 1, 1]);

    const credits = calculateMinimumNewCredits(
      loadStructure(fixtures, `${prefix}.credits`),
      [],
    );
    expect(credits.state).toBe("shortfall");
    expect(selectedGroupIds(credits)).toEqual(["active-head", "deep-tail"]);
    expect(creditsOf(credits.total_new_credits)).toBe(10400);
    const creditsEntry = credits.shortfalls[0];
    expect(creditsEntry.kind).toBe("credits");
    expect(
      creditsEntry.node_id.startsWith("s:") ||
        creditsEntry.node_id.startsWith("course:"),
    ).toBe(true);
    expect(creditsOf(creditsEntry.required_credits)).toBe(1000);
    expect(creditsOf(creditsEntry.achieved_credits)).toBe(400);
    expect(creditsOf(creditsEntry.credit_deficit)).toBe(600);

    const mixedCredit = calculateMinimumNewCredits(
      loadStructure(fixtures, `${prefix}.mixed_credit`),
      [],
    );
    expect(mixedCredit.state).toBe("shortfall");
    expect(selectedGroupIds(mixedCredit)).toEqual(["credit-low"]);
    expect(creditsOf(mixedCredit.total_new_credits)).toBe(300);
    expect(
      mixedCredit.shortfalls.map((entry) => [
        entry.kind,
        creditsOf(entry.required_credits),
        creditsOf(entry.achieved_credits),
        creditsOf(entry.credit_deficit),
      ]),
    ).toEqual([["credits", 500, 300, 200]]);

    const courseCount = calculateMinimumNewCredits(
      loadStructure(fixtures, `${prefix}.course_count`),
      [],
    );
    expect(courseCount.state).toBe("shortfall");
    expect(selectedGroupIds(courseCount)).toEqual(["active-a", "active-b"]);
    expect(creditsOf(courseCount.total_new_credits)).toBe(500);
    const countEntries = new Map(
      courseCount.shortfalls.map((entry) => [entry.kind, entry]),
    );
    const countEntry = countEntries.get("course_count");
    expect([countEntry?.required_count, countEntry?.achieved_count]).toEqual([
      3, 2,
    ]);
    expect(countEntry?.count_deficit).toBe(1);
    const mandatoryEntry = countEntries.get("all_mandatory");
    expect([
      mandatoryEntry?.required_count,
      mandatoryEntry?.achieved_count,
    ]).toEqual([3, 2]);
    expect(mandatoryEntry?.count_deficit).toBe(1);
  });

  it.each([{ nodeType: "CreditsRule" }, { nodeType: "CourseUnitCountRule" }])(
    "zero minimum module bound preserves child activity shortfall ($nodeType)",
    ({ nodeType }) => {
      const result = calculateMinimumNewCredits(
        loadStructure(
          fixtures,
          `zero_minimum_module_bound_preserves_child_activity_shortfall.compilation[${nodeType}]`,
        ),
        [],
      );
      expect(result.state).toBe("shortfall");
      expect(result.satisfaction.requirements_state).toBe("unsatisfied");
      expect(selectedGroupIds(result)).toEqual([]);
      expect(creditsOf(result.total_new_credits)).toBe(0);
      expect(result.blockers).toEqual([]);
      expect(
        result.shortfalls.map((entry) => [
          entry.kind,
          entry.required_count,
          entry.achieved_count,
          entry.count_deficit,
        ]),
      ).toEqual([["cardinality", 1, 0, 1]]);
    },
  );
});
