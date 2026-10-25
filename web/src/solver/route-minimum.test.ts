/** Minimum-new-credit route solving over direct, cardinality, credit and course-count trees. */
import { describe, expect, it } from "vitest";
import minimum from "./fixtures/route-minimum.json";
import { calculateMinimumNewCredits } from "./route";
import {
  creditsOf,
  loadStructure,
  selectedGroupIds,
  type RouteFixtures,
} from "./route-test-support";

const fixtures = minimum as unknown as RouteFixtures;

describe("route minimum", () => {
  it("minimum path uses global union and new credits not local course count", () => {
    const prefix =
      "minimum_path_uses_global_union_and_new_credits_not_local_course_count";
    const result = calculateMinimumNewCredits(
      loadStructure(fixtures, `${prefix}.compilation`),
      [],
    );
    expect(result.state).toBe("exact");
    expect(selectedGroupIds(result)).toEqual(["a", "b", "c"]);
    expect(creditsOf(result.total_new_credits)).toBe(300);

    const overlapResult = calculateMinimumNewCredits(
      loadStructure(fixtures, `${prefix}.overlap_compilation`),
      [],
    );
    expect(selectedGroupIds(overlapResult)).toEqual(["a"]);
    expect(creditsOf(overlapResult.total_new_credits)).toBe(200);

    const repeated = loadStructure(fixtures, `${prefix}.repeated_compilation`);
    const repeatedResult = calculateMinimumNewCredits(repeated, ["a"]);
    expect(selectedGroupIds(repeatedResult)).toEqual(["b"]);
    expect(creditsOf(repeatedResult.total_new_credits)).toBe(400);

    const incompleteResult = calculateMinimumNewCredits(repeated, []);
    expect(selectedGroupIds(incompleteResult)).toEqual(["a", "b"]);
    expect(creditsOf(incompleteResult.total_new_credits)).toBe(600);
    const aEntry = incompleteResult.new_courses.find(
      (entry) => entry.course.group_id === "a",
    );
    expect(aEntry?.node_ids).toEqual(["course:a"]);
  });

  it("minimum path expands new courses and directional substitutions", () => {
    const structure = loadStructure(
      fixtures,
      "minimum_path_expands_new_courses_and_directional_substitutions.substitution_compilation",
    );
    const optionOneResult = calculateMinimumNewCredits(structure, []);
    expect(selectedGroupIds(optionOneResult)).toEqual(["a1", "a2", "e1"]);
    expect(creditsOf(optionOneResult.total_new_credits)).toBe(300);
    const a1Entry = optionOneResult.new_courses.find(
      (entry) => entry.course.group_id === "a1",
    );
    const e1Entry = optionOneResult.new_courses.find(
      (entry) => entry.course.group_id === "e1",
    );
    expect(a1Entry?.node_ids).toEqual(["course:a1"]);
    expect(e1Entry?.node_ids).toEqual(["course:e1"]);

    const partial = calculateMinimumNewCredits(structure, ["a1"]);
    expect(selectedGroupIds(partial)).toEqual(["a2"]);
    expect(creditsOf(partial.total_new_credits)).toBe(100);

    const otherMember = calculateMinimumNewCredits(structure, ["a2"]);
    expect(selectedGroupIds(otherMember)).toEqual(["a1", "e1"]);
    expect(creditsOf(otherMember.total_new_credits)).toBe(200);

    const satisfiedOption = calculateMinimumNewCredits(structure, ["a1", "a2"]);
    expect(satisfiedOption.state).toBe("exact");
    expect(creditsOf(satisfiedOption.total_new_credits)).toBe(0);
    expect(selectedGroupIds(satisfiedOption)).toEqual([]);

    const prerequisiteOnly = calculateMinimumNewCredits(structure, ["e1"]);
    expect(selectedGroupIds(prerequisiteOnly)).toEqual(["a1", "a2"]);
  });

  it("logical composed and charges every incomplete child", () => {
    const structure = loadStructure(
      fixtures,
      "logical_composed_and_charges_every_incomplete_child.compilation",
    );
    const result = calculateMinimumNewCredits(structure, ["a"]);
    expect(result.satisfaction.requirements_state).toBe("unsatisfied");
    expect(result.state).toBe("exact");
    expect(selectedGroupIds(result)).toEqual(["b"]);
    expect(creditsOf(result.total_new_credits)).toBe(400);

    const completed = calculateMinimumNewCredits(structure, ["a", "b"]);
    expect(completed.state).toBe("exact");
    expect(selectedGroupIds(completed)).toEqual([]);
    expect(creditsOf(completed.total_new_credits)).toBe(0);
  });

  it("minimum path solves cardinality credit and course count on witnesses", () => {
    const prefix =
      "minimum_path_solves_cardinality_credit_and_course_count_on_witnesses";
    const chosen = calculateMinimumNewCredits(
      loadStructure(fixtures, `${prefix}.cardinality_compilation`),
      [],
    );
    expect(selectedGroupIds(chosen)).toEqual(["a"]);
    expect(creditsOf(chosen.total_new_credits)).toBe(100);

    const overlapResult = calculateMinimumNewCredits(
      loadStructure(fixtures, `${prefix}.overlap_compilation`),
      [],
    );
    expect(selectedGroupIds(overlapResult)).toEqual(["a"]);
    expect(creditsOf(overlapResult.total_new_credits)).toBe(100);

    const neutralResult = calculateMinimumNewCredits(
      loadStructure(fixtures, `${prefix}.neutral_compilation`),
      [],
    );
    expect(neutralResult.state).toBe("exact");
    expect(creditsOf(neutralResult.total_new_credits)).toBe(0);
    expect(selectedGroupIds(neutralResult)).toEqual([]);

    const creditResult = calculateMinimumNewCredits(
      loadStructure(fixtures, `${prefix}.credit_compilation`),
      [],
    );
    expect(creditResult.state).toBe("exact");
    expect(selectedGroupIds(creditResult)).toEqual(["a", "e"]);
    expect(creditsOf(creditResult.total_new_credits)).toBe(10100);

    const countResult = calculateMinimumNewCredits(
      loadStructure(fixtures, `${prefix}.count_compilation`),
      [],
    );
    expect(selectedGroupIds(countResult)).toEqual(["b"]);
    expect(creditsOf(countResult.total_new_credits)).toBe(200);
  });

  it("minimum path reports unresolved cycles and no solution", () => {
    const prefix = "minimum_path_reports_unresolved_cycles_and_no_solution";
    const zeroOpaque = loadStructure(fixtures, `${prefix}.zero_opaque`);
    const unrestrictedResult = calculateMinimumNewCredits(zeroOpaque, []);
    expect(unrestrictedResult.state).toBe("exact");
    expect(creditsOf(unrestrictedResult.total_new_credits)).toBe(0);
    expect(selectedGroupIds(unrestrictedResult)).toEqual([]);
    expect(unrestrictedResult.blockers).toEqual([]);

    const mixed = loadStructure(fixtures, `${prefix}.mixed_compilation`);
    const mixedResult = calculateMinimumNewCredits(mixed, []);
    expect(mixedResult.state).toBe("unresolved");
    expect(mixedResult.total_new_credits).toBeNull();
    expect(selectedGroupIds(mixedResult)).toEqual([]);

    const known = calculateMinimumNewCredits(mixed, ["a"]);
    expect(known.state).toBe("exact");
    expect(creditsOf(known.total_new_credits)).toBe(0);
    expect(known.blockers).toEqual([]);

    const cycle = loadStructure(fixtures, `${prefix}.cycle_compilation`);
    const cycleResult = calculateMinimumNewCredits(cycle, []);
    expect(cycleResult.state).toBe("unresolved");
    expect(cycleResult.total_new_credits).toBeNull();
    expect(selectedGroupIds(cycleResult)).toEqual([]);
    expect(cycleResult.blockers[0].kind).toBe("course_cycle");
    expect(cycleResult.blockers[0].course_group_path).toEqual(["root", "a"]);
    const cycleSatisfied = calculateMinimumNewCredits(cycle, ["a"]);
    expect(cycleSatisfied.state).toBe("exact");
    expect(creditsOf(cycleSatisfied.total_new_credits)).toBe(0);

    const impossibleResult = calculateMinimumNewCredits(
      loadStructure(fixtures, `${prefix}.impossible_compilation`),
      [],
    );
    expect(impossibleResult.state).toBe("no_solution");
    expect(impossibleResult.total_new_credits).toBeNull();
    expect(selectedGroupIds(impossibleResult)).toEqual([]);
    expect(impossibleResult.blockers).toEqual([]);
  });

  it("minimum path handles large nested choice rules exactly", () => {
    const result = calculateMinimumNewCredits(
      loadStructure(
        fixtures,
        "minimum_path_handles_large_nested_choice_rules_exactly.compilation",
      ),
      [],
    );
    expect(result.state).toBe("exact");
    expect(selectedGroupIds(result)).toEqual([
      "choice-00",
      "choice-01",
      "choice-02",
    ]);
    expect(creditsOf(result.total_new_credits)).toBe(300);
    expect(result.shortfalls).toEqual([]);
    expect(result.blockers).toEqual([]);
    expect(result.new_courses.map((entry) => entry.node_ids)).toEqual([
      ["course:choice-00"],
      ["course:choice-01"],
      ["course:choice-02"],
    ]);
  });

  it("repeated unexpandable module work is charged once", () => {
    const result = calculateMinimumNewCredits(
      loadStructure(
        fixtures,
        "repeated_unexpandable_module_work_is_charged_once.compilation",
      ),
      [],
    );
    expect(result.state).toBe("exact");
    expect(result.new_courses).toEqual([]);
    expect(result.new_opaque_work).toHaveLength(1);
    expect(creditsOf(result.new_opaque_work[0].credits_min)).toBe(3500);
    expect(result.new_opaque_work[0].node_ids).toHaveLength(1);
    expect(creditsOf(result.total_new_credits)).toBe(3500);
  });

  it("repeated bounded work keeps intrinsic identity and occurrences", () => {
    const result = calculateMinimumNewCredits(
      loadStructure(
        fixtures,
        "repeated_bounded_work_keeps_intrinsic_identity_and_occurrences.compilation",
      ),
      [],
    );
    expect(result.new_opaque_work).toHaveLength(1);
    expect(creditsOf(result.new_opaque_work[0].credits_min)).toBe(1000);
    expect(result.new_opaque_work[0].node_ids).toHaveLength(1);
    expect(result.new_opaque_work[0].node_ids[0].startsWith("s:")).toBe(true);
    expect(creditsOf(result.total_new_credits)).toBe(1000);
  });

  it("distinct opaque siblings are charged separately", () => {
    const result = calculateMinimumNewCredits(
      loadStructure(
        fixtures,
        "distinct_opaque_siblings_are_charged_separately.compilation",
      ),
      [],
    );
    expect(result.new_opaque_work).toHaveLength(2);
    expect(creditsOf(result.total_new_credits)).toBe(2000);
  });

  it("resolved members cost courses not module target", () => {
    const result = calculateMinimumNewCredits(
      loadStructure(
        fixtures,
        "resolved_members_cost_courses_not_module_target.compilation",
      ),
      [],
    );
    expect(result.state).toBe("exact");
    expect(selectedGroupIds(result)).toEqual(["member"]);
    expect(creditsOf(result.total_new_credits)).toBe(500);
    expect(result.new_opaque_work).toEqual([]);
  });

  it("unknown course count never fabricates courses", () => {
    const result = calculateMinimumNewCredits(
      loadStructure(
        fixtures,
        "unknown_course_count_never_fabricates_courses.compilation",
      ),
      [],
    );
    expect(result.state).toBe("unresolved");
    expect(result.new_courses).toEqual([]);
    expect(result.total_new_credits).toBeNull();
    expect(
      result.blockers.some(
        (blocker) => blocker.reason === "unknown_course_count",
      ),
    ).toBe(true);
  });

  it("completed unknown extent fails positive credit bound", () => {
    const result = calculateMinimumNewCredits(
      loadStructure(
        fixtures,
        "completed_unknown_extent_fails_positive_credit_bound.tree",
      ),
      [],
    );
    expect(result.state).toBe("unresolved");
    expect(result.new_courses).toEqual([]);
    expect(
      result.problems.some(
        (problem) => problem.reason === "unknown_credit_extent",
      ),
    ).toBe(true);
  });

  it("bounded unknown extent with unpaid sibling is unresolved", () => {
    const result = calculateMinimumNewCredits(
      loadStructure(
        fixtures,
        "bounded_unknown_extent_with_unpaid_sibling_is_unresolved.tree",
      ),
      [],
    );
    expect(result.state).toBe("unresolved");
    expect(
      result.problems.some(
        (problem) => problem.reason === "unknown_credit_extent",
      ),
    ).toBe(true);
  });

  it("known alternative survives unknown count option", () => {
    const result = calculateMinimumNewCredits(
      loadStructure(
        fixtures,
        "known_alternative_survives_unknown_count_option.compilation",
      ),
      ["known-alt"],
    );
    expect(result.state).toBe("exact");
    expect(creditsOf(result.total_new_credits)).toBe(0);
    expect(selectedGroupIds(result)).toEqual([]);
  });

  it.each([{ wrapper: "credits" }, { wrapper: "count" }])(
    "zero bound unknown extent wrappers preserve unpaid sibling ($wrapper)",
    ({ wrapper }) => {
      const structure = loadStructure(
        fixtures,
        `zero_bound_unknown_extent_wrappers_preserve_unpaid_sibling.tree[${wrapper}]`,
      );
      const result = calculateMinimumNewCredits(structure, []);
      expect(result.state).toBe("exact");
      expect(creditsOf(result.total_new_credits)).toBe(500);
      expect(selectedGroupIds(result)).toEqual(["unpaid"]);
      expect(
        result.problems.some(
          (problem) => problem.reason === "unknown_credit_extent",
        ),
      ).toBe(false);
      const greedy = calculateMinimumNewCredits(structure, [], 1);
      expect(greedy.state).toBe("approximate");
      expect(selectedGroupIds(greedy)).toEqual(["unpaid"]);
    },
  );

  it.each([{ completedKind: "module" }, { completedKind: "credit_rule" }])(
    "known completed extent satisfies credit bound without member courses ($completedKind)",
    ({ completedKind }) => {
      const structure = loadStructure(
        fixtures,
        `known_completed_extent_satisfies_credit_bound_without_member_courses.tree[${completedKind}]`,
      );
      const result = calculateMinimumNewCredits(structure, []);
      expect(result.state).toBe("exact");
      expect(creditsOf(result.total_new_credits)).toBe(500);
      expect(selectedGroupIds(result)).toEqual(["unpaid"]);
      expect(
        result.problems.some(
          (problem) => problem.reason === "unknown_credit_extent",
        ),
      ).toBe(false);
      const greedy = calculateMinimumNewCredits(structure, [], 1);
      expect(greedy.state).toBe("approximate");
      expect(creditsOf(greedy.total_new_credits)).toBe(500);
      expect(selectedGroupIds(greedy)).toEqual(["unpaid"]);
      expect(greedy.new_opaque_work).toEqual([]);
    },
  );

  it("duplicate recommended occurrence route matches a fixture without the duplicate", () => {
    const prefix =
      "duplicate_recommended_occurrence_route_matches_a_fixture_without_the_duplicate";
    const duplicatedResult = calculateMinimumNewCredits(
      loadStructure(fixtures, `${prefix}.duplicated_compilation`),
      [],
    );
    const withoutDuplicateResult = calculateMinimumNewCredits(
      loadStructure(fixtures, `${prefix}.without_duplicate_compilation`),
      [],
    );
    expect(duplicatedResult.state).toBe("exact");
    expect(duplicatedResult.state).toBe(withoutDuplicateResult.state);
    expect(creditsOf(duplicatedResult.total_new_credits)).toBe(
      creditsOf(withoutDuplicateResult.total_new_credits),
    );
    expect(selectedGroupIds(duplicatedResult)).toEqual(
      selectedGroupIds(withoutDuplicateResult),
    );
  });
});
