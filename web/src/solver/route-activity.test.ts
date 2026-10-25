/** Activity eligibility, exclusion routes and inactive-candidate alternatives. */
import { describe, expect, it } from "vitest";
import activity from "./fixtures/route-activity.json";
import { calculateMinimumNewCredits } from "./route";
import {
  courseNodes,
  creditsOf,
  loadDisplay,
  loadStructure,
  selectedGroupIds,
  type RouteFixtures,
} from "./route-test-support";

const fixtures = activity as unknown as RouteFixtures;

describe("route activity", () => {
  it("active only path excludes inactive non basis candidates and uses eligible alternatives", () => {
    const prefix =
      "active_only_path_excludes_inactive_non_basis_candidates_and_uses_eligible_alternatives";
    const requiredResult = calculateMinimumNewCredits(
      loadStructure(fixtures, `${prefix}.required_inactive`),
      [],
    );
    expect(requiredResult.state).toBe("no_solution");
    expect(requiredResult.new_courses).toEqual([]);
    expect(requiredResult.total_new_credits).toBeNull();

    const alternativeResult = calculateMinimumNewCredits(
      loadStructure(fixtures, `${prefix}.alternative`),
      [],
    );
    expect(alternativeResult.state).toBe("exact");
    expect(selectedGroupIds(alternativeResult)).toEqual(["active-alt"]);
    expect(creditsOf(alternativeResult.total_new_credits)).toBe(300);

    const retainedBasis = loadStructure(fixtures, `${prefix}.retained_basis`);
    const retainedResult = calculateMinimumNewCredits(retainedBasis, [
      "inactive-leaf",
    ]);
    expect(retainedResult.state).toBe("exact");
    expect(selectedGroupIds(retainedResult)).toEqual([]);
    expect(creditsOf(retainedResult.total_new_credits)).toBe(0);

    const retainedOnly = calculateMinimumNewCredits(retainedBasis, []);
    expect(retainedOnly.state).toBe("no_solution");
    expect(selectedGroupIds(retainedOnly)).toEqual([]);

    const allCoursesResult = calculateMinimumNewCredits(
      loadStructure(fixtures, `${prefix}.all_courses`),
      [],
    );
    expect(allCoursesResult.state).toBe("exact");
    expect(selectedGroupIds(allCoursesResult)).toEqual(["inactive-leaf"]);
    expect(creditsOf(allCoursesResult.total_new_credits)).toBe(400);
  });

  it("exclusion selects other or else no solution", () => {
    const prefix = "exclusion_selects_other_or_else_no_solution";
    const alternativeResult = calculateMinimumNewCredits(
      loadStructure(fixtures, `${prefix}.alternative`),
      [],
    );
    expect(alternativeResult.state).toBe("exact");
    expect(selectedGroupIds(alternativeResult)).toEqual(["alt"]);
    expect(creditsOf(alternativeResult.total_new_credits)).toBe(300);
    expect(alternativeResult.blocked_excluded_group_ids).toEqual(["excluded"]);

    const onlyResult = calculateMinimumNewCredits(
      loadStructure(fixtures, `${prefix}.only`),
      [],
    );
    expect(onlyResult.state).toBe("no_solution");
    expect(onlyResult.new_courses).toEqual([]);
    expect(onlyResult.total_new_credits).toBeNull();
    expect(onlyResult.blocked_excluded_group_ids).toEqual(["excluded"]);
  });

  it("excluded substitution option requires every member", () => {
    const result = calculateMinimumNewCredits(
      loadStructure(
        fixtures,
        "excluded_substitution_option_requires_every_member.compilation",
      ),
      [],
    );
    expect(result.state).toBe("exact");
    expect(selectedGroupIds(result)).toEqual(["a"]);
    expect(creditsOf(result.total_new_credits)).toBe(600);
    expect(result.blocked_excluded_group_ids).toEqual(["s1"]);
  });

  it("excluded course does not poison descendant on another route", () => {
    const result = calculateMinimumNewCredits(
      loadStructure(
        fixtures,
        "excluded_course_does_not_poison_descendant_on_another_route.compilation",
      ),
      [],
    );
    expect(result.state).toBe("exact");
    expect(selectedGroupIds(result)).toEqual(["shared", "y"]);
    expect(creditsOf(result.total_new_credits)).toBe(700);
    expect(result.blocked_excluded_group_ids).toEqual(["x"]);
  });

  it("shared problem locations retain every provenance fact", () => {
    const prefix =
      "shared_problem_locations_retain_every_provenance_fact.compilation";
    const display = loadDisplay(fixtures, prefix);
    expect(
      courseNodes(display).filter((node) => node.course_group_id === "shared"),
    ).toHaveLength(1);
    const result = calculateMinimumNewCredits(
      loadStructure(fixtures, prefix),
      [],
    );
    expect(result.state).toBe("no_solution");
    const sharedProblems = result.problems.filter(
      (problem) => problem.node_id === "course:shared",
    );
    expect(sharedProblems).toHaveLength(2);
    expect(new Set(sharedProblems.map((problem) => problem.fact_id)).size).toBe(
      2,
    );
    expect(
      sharedProblems.every((problem) => problem.state === "no_solution"),
    ).toBe(true);
    expect(
      sharedProblems.every((problem) => problem.reason === "excluded_node"),
    ).toBe(true);
  });
});
