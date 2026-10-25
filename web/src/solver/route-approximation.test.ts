/** Size-limited approximation and scalar greedy route results. */
import { describe, expect, it } from "vitest";
import approximation from "./fixtures/route-approximation.json";
import contracts from "./fixtures/route-contracts.json";
import { calculateMinimumNewCredits } from "./route";
import {
  creditsOf,
  loadStructure,
  selectedGroupIds,
  type RouteFixtures,
} from "./route-test-support";

const fixtures = approximation as unknown as RouteFixtures;
const contractFixtures = contracts as unknown as RouteFixtures;

describe("route approximation", () => {
  it("approximate route lights one coherent equal-cost module occurrence", () => {
    const label = "coherent_route_occurrences.equal";
    const structure = loadStructure(contractFixtures, label);
    const result = calculateMinimumNewCredits(structure, [], 1);
    expect(result.state).toBe("approximate");
    expect(selectedGroupIds(result)).toEqual(["P", "Q"]);
    expect(creditsOf(result.total_new_credits)).toBe(1000);

    const display = contractFixtures[label].display;
    if (display === null) {
      throw new Error(`${label} has no display`);
    }
    const modules = display.nodes.filter((node) => node.kind === "module");
    expect(modules).toHaveLength(2);
    const litMembers = new Set(result.lit_members);
    const litOn = (source: string, target: string) => {
      const edge = display.edges.find(
        (item) =>
          item.source_node_id === source && item.target_node_id === target,
      );
      if (edge === undefined) {
        throw new Error(`the equal fixture has no ${source} to ${target} edge`);
      }
      return edge.member_ids.some((id) => litMembers.has(id));
    };
    const litModules = modules.filter((box) => litOn(box.node_id, "course:Q"));
    expect(litModules).toHaveLength(1);
    const unchosen = modules.find(
      (box) => box.node_id !== litModules[0].node_id,
    );
    if (unchosen === undefined) {
      throw new Error("the equal fixture needs two module boxes");
    }
    expect(result.selected_nodes).not.toContain(unchosen.node_id);
    expect(litOn(unchosen.node_id, "course:Q")).toBe(false);
    const chooser = display.edges.find(
      (item) => item.source_node_id === "course:root",
    );
    if (chooser === undefined) {
      throw new Error("the equal fixture has no root connection");
    }
    expect(litOn(chooser.target_node_id, litModules[0].node_id)).toBe(true);
    expect(litOn(chooser.target_node_id, unchosen.node_id)).toBe(false);
  });

  it("path below size limit preserves complete exact bytes", () => {
    const structure = loadStructure(
      fixtures,
      "path_below_size_limit_preserves_complete_exact_bytes.small",
    );
    const ordinary = calculateMinimumNewCredits(structure, []);
    const capped = calculateMinimumNewCredits(structure, [], 20000);
    expect(ordinary).toEqual(capped);
  });

  it.each([
    { overlappingOption: false, suffix: "False" },
    { overlappingOption: true, suffix: "True" },
  ])(
    "scalar greedy route deduplicates shared prerequisites and opaque work ($overlappingOption)",
    ({ suffix }) => {
      const heads = Array.from(
        { length: 40 },
        (_unused, index) => `head-${String(index).padStart(2, "0")}`,
      );
      const result = calculateMinimumNewCredits(
        loadStructure(
          fixtures,
          `scalar_greedy_route_deduplicates_shared_prerequisites_and_opaque_work.tree[${suffix}]`,
        ),
        [],
        1,
      );
      expect(result.state).toBe("approximate");
      expect(selectedGroupIds(result)).toEqual(
        [...heads.slice(0, 20), "shared"].sort(),
      );
      expect(creditsOf(result.total_new_credits)).toBe(2800);
      expect(result.new_opaque_work).toHaveLength(1);
      expect(result.new_opaque_work[0].node_ids).toHaveLength(1);
      expect(result.new_opaque_work[0].node_ids[0].startsWith("s:")).toBe(true);
      const shared = result.new_courses.find(
        (entry) => entry.course.group_id === "shared",
      );
      expect(shared?.node_ids).toEqual(["course:shared"]);
      expect(
        result.new_courses
          .filter((entry) => entry.course.group_id.startsWith("head-"))
          .map((entry) => entry.node_ids),
      ).toEqual(heads.slice(0, 20).map((head) => [`course:${head}`]));
      expect(
        result.new_courses.some((entry) =>
          entry.course.group_id.startsWith("bait-"),
        ),
      ).toBe(false);
    },
  );

  it.each([
    {
      pickMinimum: 0,
      duplicatePosition: false,
      suffix: "0-False",
    },
    {
      pickMinimum: 1,
      duplicatePosition: false,
      suffix: "1-False",
    },
    {
      pickMinimum: 1,
      duplicatePosition: true,
      suffix: "1-True",
    },
  ])(
    "path approximation extends greedy prefixes for numeric bounds ($pickMinimum, $duplicatePosition)",
    ({ suffix }) => {
      const choices = Array.from(
        { length: 27 },
        (_unused, index) => `choice-${String(index).padStart(2, "0")}`,
      );
      const result = calculateMinimumNewCredits(
        loadStructure(
          fixtures,
          `path_approximation_extends_greedy_prefixes_for_numeric_bounds.tree[${suffix}]`,
        ),
        [],
        1,
      );
      expect(result.state).toBe("approximate");
      expect(selectedGroupIds(result)).toEqual(choices.slice(0, 3));
      expect(creditsOf(result.total_new_credits)).toBe(300);
      expect(result.new_courses.map((entry) => entry.node_ids)).toEqual(
        choices.slice(0, 3).map((choice) => [`course:${choice}`]),
      );
    },
  );

  it.each([{ limit: 1 }, { limit: 10000 }])(
    "path approximation failure reports search too large without a route ($limit)",
    ({ limit }) => {
      const result = calculateMinimumNewCredits(
        loadStructure(
          fixtures,
          `path_approximation_failure_reports_search_too_large_without_a_route.tree[${limit}]`,
        ),
        [],
        limit,
      );
      expect(result.state).toBe("approximation_failed");
      expect(result.total_new_credits).toBeNull();
      expect(result.new_courses).toEqual([]);
      expect(result.new_opaque_work).toEqual([]);
      expect(result.selected_nodes).toEqual([]);
      expect(result.shortfalls).toEqual([]);
      expect(
        result.problems.map((problem) => [problem.reason, problem.node_id]),
      ).toEqual([["search_too_large", "course:root"]]);
    },
  );

  it("scalar greedy expanded head stops at the basis", () => {
    const result = calculateMinimumNewCredits(
      loadStructure(
        fixtures,
        "scalar_greedy_expanded_head_stops_at_the_basis.tree",
      ),
      ["head"],
      1,
    );
    expect(result.state).toBe("approximate");
    expect(selectedGroupIds(result)).toEqual(["sibling"]);
    expect(creditsOf(result.total_new_credits)).toBe(500);
    const sibling = result.new_courses.find(
      (item) => item.course.group_id === "sibling",
    );
    expect(sibling?.node_ids).toEqual(["course:sibling"]);
  });

  it.each([
    { denial: "excluded_course" },
    { denial: "excluded_module" },
    { denial: "inactive_course" },
  ])(
    "scalar greedy route rejects unavailable alternatives ($denial)",
    ({ denial }) => {
      const result = calculateMinimumNewCredits(
        loadStructure(
          fixtures,
          `scalar_greedy_route_rejects_unavailable_alternatives.tree[${denial}]`,
        ),
        [],
        1,
      );
      expect(result.state).toBe("approximate");
      expect(selectedGroupIds(result)).toEqual(["dear"]);
      expect(creditsOf(result.total_new_credits)).toBe(400);
      expect(
        result.new_courses.every((item) => item.course.group_id !== "cheap"),
      ).toBe(true);
    },
  );
});
