/** Coverage fidelity, deterministic tie-breaking and node membership for the minimum-credit route. */
import { describe, expect, it } from "vitest";
import type { PrerequisiteGraphReport } from "../api/types";
import { buildGraphModel } from "../features/prerequisites/graph/model";
import {
  buildRouteSummary,
  buildRouteView,
} from "../features/prerequisites/route/route";
import contracts from "./fixtures/route-contracts.json";
import { calculateMinimumNewCredits } from "./route";
import {
  courseNodes,
  creditsOf,
  loadDisplay,
  loadStructure,
  selectedGroupIds,
  type RouteFixtures,
} from "./route-test-support";

const fixtures = contracts as unknown as RouteFixtures;

describe("route contracts", () => {
  it("minimum path preserves coverage and deterministic ties", () => {
    const prefix = "minimum_path_preserves_coverage_and_deterministic_ties";
    const inferred = loadStructure(fixtures, `${prefix}.inferred_compilation`);
    const inferredResult = calculateMinimumNewCredits(inferred, []);
    expect(inferredResult.state).toBe("exact");
    expect(inferredResult.inferred_coverage).toEqual(
      inferred.inferred_coverage,
    );
    expect(selectedGroupIds(inferredResult)).toEqual(["z"]);
    expect(inferredResult.satisfaction.include_inferred).toBe(true);

    const tie = loadStructure(fixtures, `${prefix}.tie`);
    const tieResult = calculateMinimumNewCredits(tie, []);
    expect(selectedGroupIds(tieResult)).toEqual(["b"]);
    expect(calculateMinimumNewCredits(tie, [])).toEqual(tieResult);

    const stableResult = calculateMinimumNewCredits(
      loadStructure(fixtures, `${prefix}.stable`),
      [],
    );
    expect(selectedGroupIds(stableResult)).toEqual(["a"]);

    const mixedResult = calculateMinimumNewCredits(
      loadStructure(fixtures, `${prefix}.mixed`),
      [],
    );
    expect(selectedGroupIds(mixedResult)).toEqual(["a"]);
    expect(mixedResult.new_opaque_work).toEqual([]);

    const witnessTie = loadStructure(fixtures, `${prefix}.witness_tie_tree`);
    const display = loadDisplay(fixtures, `${prefix}.witness_tie_tree`);
    const moduleBox = display.nodes.find(
      (node) => node.kind === "module" && node.module_group_id === "manual",
    );
    if (moduleBox === undefined) {
      throw new Error("the witness tie fixture has no manual module box");
    }
    const witnessTieResult = calculateMinimumNewCredits(witnessTie, []);
    expect(witnessTieResult.state).toBe("exact");
    expect(creditsOf(witnessTieResult.total_new_credits)).toBe(500);
    expect(
      witnessTieResult.new_opaque_work[0].node_ids[0].startsWith("s:"),
    ).toBe(true);
    expect(witnessTieResult.selected_nodes).toContain(moduleBox.node_id);
  });

  it("basis head satisfies its expanded prerequisites at zero cost", () => {
    const prefix =
      "basis_head_satisfies_its_expanded_prerequisites_at_zero_cost";
    const plain = loadStructure(fixtures, `${prefix}.plain`);

    const empty = calculateMinimumNewCredits(plain, []);
    expect(empty.state).toBe("exact");
    expect(selectedGroupIds(empty)).toEqual(["a", "e"]);
    expect(creditsOf(empty.total_new_credits)).toBe(500);
    expect(empty.selected_nodes).toEqual([
      "course:a",
      "course:e",
      "course:root",
    ]);

    const covered = calculateMinimumNewCredits(plain, ["a"]);
    expect(covered.state).toBe("exact");
    expect(covered.satisfaction.requirements_state).toBe("satisfied");
    expect(selectedGroupIds(covered)).toEqual([]);
    expect(creditsOf(covered.total_new_credits)).toBe(0);
    expect(
      creditsOf(calculateMinimumNewCredits(plain, ["root"]).total_new_credits),
    ).toBe(0);
    const excluded = calculateMinimumNewCredits(
      loadStructure(fixtures, `${prefix}.excluded`),
      ["root"],
    );
    expect(excluded.state).toBe("no_solution");

    const mixed = calculateMinimumNewCredits(
      loadStructure(fixtures, `${prefix}.shared_tree`),
      ["a"],
    );
    expect(mixed.state).toBe("exact");
    expect(mixed.satisfaction.requirements_state).toBe("unsatisfied");
    expect(selectedGroupIds(mixed)).toEqual(["b", "shared"]);
    expect(creditsOf(mixed.total_new_credits)).toBe(700);
    expect(mixed.selected_nodes).toContain("course:root");
    for (const groupId of ["b", "shared"]) {
      expect(mixed.selected_nodes).toContain(`course:${groupId}`);
    }
  });

  it.each([
    {
      required: "z",
      optional: "a",
      expected: ["a", "z"],
      suffix: "required=z,optional=a",
    },
    {
      required: "a",
      optional: "z",
      expected: ["a"],
      suffix: "required=a,optional=z",
    },
  ])(
    "minimum path zero credit ties ignore tree variable order ($required, $optional)",
    ({ required, optional, expected, suffix }) => {
      const prefix = "minimum_path_zero_credit_ties_ignore_tree_variable_order";
      const result = calculateMinimumNewCredits(
        loadStructure(fixtures, `${prefix}.compilation[${suffix}]`),
        [],
      );
      expect(result.state).toBe("exact");
      expect(creditsOf(result.total_new_credits)).toBe(300);
      expect(result.new_opaque_work).toHaveLength(1);
      expect(selectedGroupIds(result)).toEqual(expected);
      expect(result.blockers).toEqual([]);
      expect(result.shortfalls).toEqual([]);
      const evidenceByGroup = new Map(
        result.new_courses.map((entry) => [
          entry.course.group_id,
          entry.node_ids,
        ]),
      );
      expect(evidenceByGroup.get(required)).toEqual([`course:${required}`]);
      if (expected.includes(optional)) {
        expect(evidenceByGroup.get(optional)).toEqual([`course:${optional}`]);
      } else {
        expect(evidenceByGroup.has(optional)).toBe(false);
      }

      const reversedResult = calculateMinimumNewCredits(
        loadStructure(fixtures, `${prefix}.reversed_source[${suffix}]`),
        [],
      );
      expect(selectedGroupIds(reversedResult)).toEqual(expected);
    },
  );

  it.each([
    { maxCompactNodes: null, suffix: "None" },
    { maxCompactNodes: 1, suffix: "1" },
  ])(
    "route activity tie counts only distinct new courses ($maxCompactNodes)",
    ({ maxCompactNodes, suffix }) => {
      const prefix = "route_activity_tie_counts_only_distinct_new_courses";
      const expectedState = maxCompactNodes === null ? "exact" : "approximate";

      const cheap = calculateMinimumNewCredits(
        loadStructure(fixtures, `${prefix}.compilation[${suffix}]`),
        [],
        maxCompactNodes,
      );
      expect(cheap.state).toBe(expectedState);
      expect(selectedGroupIds(cheap)).toEqual(["inactive-cheap"]);
      expect(creditsOf(cheap.total_new_credits)).toBe(100);

      const activityTie = calculateMinimumNewCredits(
        loadStructure(fixtures, `${prefix}.compilation[${suffix}]#2`),
        [],
        maxCompactNodes,
      );
      expect(activityTie.state).toBe(expectedState);
      expect(selectedGroupIds(activityTie)).toEqual([
        "head",
        "inactive-shared",
      ]);
      expect(creditsOf(activityTie.total_new_credits)).toBe(1000);

      const basisCovered = calculateMinimumNewCredits(
        loadStructure(fixtures, `${prefix}.basis_compilation[${suffix}]`),
        ["inactive-covered"],
        maxCompactNodes,
      );
      expect(basisCovered.state).toBe("exact");
      expect(creditsOf(basisCovered.total_new_credits)).toBe(0);
      expect(selectedGroupIds(basisCovered)).toEqual([]);
      expect(basisCovered.new_opaque_work).toEqual([]);
    },
  );

  it("minimum path reconstructs only feasible projected evidence", () => {
    const result = calculateMinimumNewCredits(
      loadStructure(
        fixtures,
        "minimum_path_reconstructs_only_feasible_projected_evidence.compilation",
      ),
      [],
    );
    expect(result.state).toBe("exact");
    expect(selectedGroupIds(result)).toEqual(["head", "shared"]);
    expect(creditsOf(result.total_new_credits)).toBe(300);
    expect(result.blockers).toEqual([]);
    expect(result.shortfalls).toEqual([]);
    const evidenceByGroup = new Map(
      result.new_courses.map((entry) => [
        entry.course.group_id,
        entry.node_ids,
      ]),
    );
    expect(evidenceByGroup.get("head")).toEqual(["course:head"]);
    expect(evidenceByGroup.get("shared")).toEqual(["course:shared"]);
    expect(result.selected_nodes).toContain("course:shared");
    expect(result.selected_nodes).not.toContain("course:extra");
    expect(
      result.selected_nodes.some((nodeId) => nodeId.startsWith("s:")),
    ).toBe(true);
  });

  it("exact route lights one coherent equal-cost module occurrence", () => {
    const label = "coherent_route_occurrences.equal";
    const structure = loadStructure(fixtures, label);
    const display = loadDisplay(fixtures, label);
    const result = calculateMinimumNewCredits(structure, []);
    expect(result.state).toBe("exact");
    expect(selectedGroupIds(result)).toEqual(["P", "Q"]);
    expect(creditsOf(result.total_new_credits)).toBe(1000);

    const modules = display.nodes.filter((node) => node.kind === "module");
    expect(modules).toHaveLength(2);
    const litMembers = new Set(result.lit_members);
    const connection = (source: string, target: string) => {
      const edge = display.edges.find(
        (item) =>
          item.source_node_id === source && item.target_node_id === target,
      );
      if (edge === undefined) {
        throw new Error(
          `the equal fixture has no connection from ${source} to ${target}`,
        );
      }
      return edge;
    };
    const litOn = (memberIds: readonly string[]) =>
      memberIds.filter((memberId) => litMembers.has(memberId)).length > 0;
    const litModules = modules.filter((box) =>
      litOn(connection(box.node_id, "course:Q").member_ids),
    );
    expect(litModules).toHaveLength(1);
    const chosen = litModules[0];
    const unchosen = modules.find((box) => box.node_id !== chosen.node_id);
    if (unchosen === undefined) {
      throw new Error("the equal fixture needs two module boxes");
    }

    const rootEdge = display.edges.find(
      (item) => item.source_node_id === "course:root",
    );
    if (rootEdge === undefined) {
      throw new Error("the equal fixture has no root connection");
    }
    const chooser = rootEdge;
    const chosenIncoming = connection(chooser.target_node_id, chosen.node_id);
    const unchosenIncoming = connection(
      chooser.target_node_id,
      unchosen.node_id,
    );
    const chosenToQ = connection(chosen.node_id, "course:Q");
    const unchosenToQ = connection(unchosen.node_id, "course:Q");
    expect(litOn(chosenIncoming.member_ids)).toBe(true);
    expect(litOn(chosenToQ.member_ids)).toBe(true);
    expect(litOn(unchosenIncoming.member_ids)).toBe(false);
    expect(litOn(unchosenToQ.member_ids)).toBe(false);
    expect(result.selected_nodes).not.toContain(unchosen.node_id);

    const graph: PrerequisiteGraphReport = {
      drawing: {
        allowed: true,
        limit: null,
        course_count: courseNodes(display).length,
        node_count: display.nodes.length,
        edge_count: display.edges.length,
        element_count: display.nodes.length + display.edges.length,
      },
      dataset_identity: "synthetic-dataset",
      max_compact_nodes: 10000,
      solver: structure,
      display,
    };
    const model = buildGraphModel(graph, "en", []);
    const summary = buildRouteSummary(graph, result, "en");
    const view = buildRouteView(result, model, summary);
    expect(view.lit.nodes).toEqual(
      new Set([
        "course:root",
        chooser.target_node_id,
        chosen.node_id,
        "course:Q",
      ]),
    );
    expect([...view.lit.edges].sort()).toEqual(
      [chosenIncoming.edge_id, chosenToQ.edge_id, chooser.edge_id].sort(),
    );
  });

  it("exact route keeps module-local choices under different parent bounds", () => {
    const label = "coherent_route_occurrences.local";
    const structure = loadStructure(fixtures, label);
    const display = loadDisplay(fixtures, label);
    const result = calculateMinimumNewCredits(structure, []);
    expect(result.state).toBe("exact");
    expect(selectedGroupIds(result)).toEqual(["P", "Q", "X", "Y"]);
    expect(creditsOf(result.total_new_credits)).toBe(1800);
    expect(result.new_opaque_work).toEqual([]);

    const litMembers = new Set(result.lit_members);
    const isLit = (source: string, target: string) => {
      const edge = display.edges.find(
        (item) =>
          item.source_node_id === source && item.target_node_id === target,
      );
      return (
        edge !== undefined && edge.member_ids.some((id) => litMembers.has(id))
      );
    };
    const litTargets = (source: string) =>
      display.edges
        .filter((edge) => edge.source_node_id === source)
        .filter((edge) => edge.member_ids.some((id) => litMembers.has(id)))
        .map((edge) => edge.target_node_id);
    const moduleBox = (groupId: string) => {
      const box = display.nodes.find(
        (node) => node.kind === "module" && node.module_group_id === groupId,
      );
      if (box === undefined) {
        throw new Error(`the local fixture has no ${groupId} module box`);
      }
      return box;
    };
    const nodeOf = (nodeId: string) => {
      const node = display.nodes.find((item) => item.node_id === nodeId);
      if (node === undefined) {
        throw new Error(`the local fixture has no node ${nodeId}`);
      }
      return node;
    };
    const m1 = moduleBox("M1");
    const m2 = moduleBox("M2");

    const context = (group: string, otherCourse: string) => {
      const box = group === "M1" ? m1 : m2;
      const wrapper = litTargets(box.node_id)
        .map(nodeOf)
        .find((node) => node.kind === "credits");
      if (wrapper === undefined) {
        throw new Error(`the ${group} box has no lit credit wrapper`);
      }
      const cardinality = litTargets(wrapper.node_id)
        .map(nodeOf)
        .find((node) => node.kind === "cardinality");
      if (cardinality === undefined) {
        throw new Error(`the ${group} wrapper has no lit cardinality context`);
      }
      return { box, wrapper, cardinality, otherCourse };
    };
    const first = context("M1", "course:Y");
    const second = context("M2", "course:X");
    expect(first.cardinality.node_id).not.toBe(second.cardinality.node_id);

    for (const entry of [first, second]) {
      const incoming = display.edges.find(
        (edge) => edge.target_node_id === entry.box.node_id,
      );
      if (incoming === undefined) {
        throw new Error(
          `the ${entry.box.node_id} module box has no connection`,
        );
      }
      expect(incoming.member_ids.some((id) => litMembers.has(id))).toBe(true);
      expect(entry.wrapper.credits_min).toBe(entry === first ? "3" : "5");
      expect(isLit(entry.cardinality.node_id, entry.otherCourse)).toBe(false);
      const requirement = litTargets(entry.cardinality.node_id)
        .map(nodeOf)
        .find((node) => node.kind === "internal_requirement");
      if (requirement === undefined) {
        throw new Error(
          `the ${entry === first ? "M1" : "M2"} cardinality has no lit internal requirement`,
        );
      }
      expect(requirement.member_group_ids).toEqual([
        entry === first ? "P" : "Q",
      ]);
      expect(result.selected_nodes).toContain(requirement.node_id);
    }
    const rootId = "course:root";
    const incident = (nodeId: string) =>
      display.edges.filter(
        (edge) =>
          edge.source_node_id === nodeId || edge.target_node_id === nodeId,
      );
    for (const nodeId of result.selected_nodes) {
      if (nodeId === rootId) continue;
      expect(
        incident(nodeId).some((edge) =>
          edge.member_ids.some((id) => litMembers.has(id)),
        ),
      ).toBe(true);
    }
  });

  it("route nodes follow selected members instead of shared hidden bindings", () => {
    const label = "route_nodes_follow_selected_members.compilation";
    const structure = loadStructure(fixtures, label);
    const display = loadDisplay(fixtures, label);
    const result = calculateMinimumNewCredits(structure, []);
    expect(result.state).toBe("exact");
    expect(selectedGroupIds(result)).toEqual(["P", "Q"]);
    expect(creditsOf(result.total_new_credits)).toBe(1000);
    const moduleBox = (groupId: string) => {
      const box = display.nodes.find(
        (item) => item.kind === "module" && item.module_group_id === groupId,
      );
      if (box === undefined) {
        throw new Error(`the fixture has no ${groupId} module box`);
      }
      return box;
    };
    const m1 = moduleBox("M1");
    const m2 = moduleBox("M2");
    const litMembers = new Set(result.lit_members);
    const litIntersection = (source: string, target: string): string[] => {
      const connection = display.edges.find(
        (item) =>
          item.source_node_id === source && item.target_node_id === target,
      );
      if (connection === undefined) {
        throw new Error(`the fixture has no ${source} to ${target} connection`);
      }
      return connection.member_ids.filter((memberId) =>
        litMembers.has(memberId),
      );
    };
    expect(litIntersection(m1.node_id, "course:Q").length).toBeGreaterThan(0);
    expect(litIntersection(m2.node_id, "course:Q")).toEqual([]);
    expect(result.selected_nodes).toContain(m1.node_id);
    expect(result.selected_nodes).not.toContain(m2.node_id);

    const graph: PrerequisiteGraphReport = {
      drawing: {
        allowed: true,
        limit: null,
        course_count: courseNodes(display).length,
        node_count: display.nodes.length,
        edge_count: display.edges.length,
        element_count: display.nodes.length + display.edges.length,
      },
      dataset_identity: "synthetic-dataset",
      max_compact_nodes: 10000,
      solver: structure,
      display,
    };
    const model = buildGraphModel(graph, "en", []);
    const summary = buildRouteSummary(graph, result, "en");
    const view = buildRouteView(result, model, summary);
    expect(view.lit.nodes.has(m2.node_id)).toBe(false);
  });
});
