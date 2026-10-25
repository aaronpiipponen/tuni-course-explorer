/** Satisfaction and graph box states over solver structures the server wrote. */
import { describe, expect, it } from "vitest";
import type {
  GraphDisplay,
  GraphDisplayNode,
  GraphNodeState,
  PrerequisiteGraphReport,
  PrerequisitesRequest,
  SolverPiece,
  SolverStructure,
} from "../api/types";
import { evaluateGraphNodeStates } from "../features/prerequisites/graph/localState";
import { parseCredits } from "./credits";
import fixtures from "./fixtures/satisfaction.json";
import { evaluateSatisfaction, SatisfactionSession } from "./satisfaction";

const nodeStates = fixtures.nodeStates as unknown as {
  solver: SolverStructure;
  display: GraphDisplay;
};

function structure(label: string): SolverStructure {
  return (fixtures.structures as Record<string, unknown>)[
    label
  ] as SolverStructure;
}

function coursePiece(target: SolverStructure, groupId: string): string {
  const matches = target.pieces.filter(
    (piece) =>
      piece.kind === "course" &&
      piece.course_group_id === groupId &&
      !piece.cycle_closing &&
      !piece.module_rule,
  );
  expect(matches).toHaveLength(1);
  return matches[0].piece_id;
}

type PieceFields = {
  count_min?: number;
  count_max?: number;
  credits_min?: number;
  credits_max?: number;
};

function extraPiece(
  target: SolverStructure,
  kind: SolverPiece["kind"],
  childPieceId: string,
  fields: PieceFields,
): string {
  const matches = target.pieces.filter((piece) => {
    if (piece.kind !== kind || !piece.children.includes(childPieceId)) {
      return false;
    }
    if (
      fields.count_min !== undefined &&
      piece.count_min !== fields.count_min
    ) {
      return false;
    }
    if (
      fields.count_max !== undefined &&
      piece.count_max !== fields.count_max
    ) {
      return false;
    }
    if (
      fields.credits_min !== undefined &&
      (piece.credits_min === null ||
        parseCredits(piece.credits_min) !== fields.credits_min)
    ) {
      return false;
    }
    if (
      fields.credits_max !== undefined &&
      (piece.credits_max === null ||
        parseCredits(piece.credits_max) !== fields.credits_max)
    ) {
      return false;
    }
    return true;
  });
  expect(matches).toHaveLength(1);
  return matches[0].piece_id;
}

function pieceOfUse(target: SolverStructure, useId: string): string {
  const use = target.uses.find((entry) => entry.use_id === useId);
  if (use === undefined) {
    throw new Error(`structure has no use ${useId}`);
  }
  return use.piece_id;
}

function rootPiece(target: SolverStructure): string {
  if (target.root_use_id === null) {
    throw new Error("structure has no root use");
  }
  return pieceOfUse(target, target.root_use_id);
}

function unresolvedPiece(target: SolverStructure, reason: string): string {
  const matches = target.pieces.filter(
    (piece) => piece.kind === "unresolved" && piece.reason === reason,
  );
  expect(matches).toHaveLength(1);
  return matches[0].piece_id;
}

function childUses(target: SolverStructure, useId: string): readonly string[] {
  const use = target.uses.find((entry) => entry.use_id === useId);
  if (use === undefined) {
    throw new Error(`structure has no use ${useId}`);
  }
  return use.children;
}

function courseNode(display: GraphDisplay, groupId: string): GraphDisplayNode {
  const node = display.nodes.find(
    (entry) => entry.kind === "course" && entry.course_group_id === groupId,
  );
  if (node === undefined) {
    throw new Error(`display has no course node ${groupId}`);
  }
  return node;
}

function stateOf(
  states: readonly GraphNodeState[],
  nodeId: string,
): GraphNodeState {
  const state = states.find((entry) => entry.node_id === nodeId);
  if (state === undefined) {
    throw new Error(`no state for node ${nodeId}`);
  }
  return state;
}

describe("satisfaction", () => {
  it("canonical completion identity satisfies repeated leaves", () => {
    const evaluation = evaluateSatisfaction(
      structure("canonical.compilation"),
      ["b", "zzz-unrelated", "a", "a"],
    );
    expect(evaluation.basis_group_ids).toEqual(["a", "b", "zzz-unrelated"]);
    expect(evaluation.requirements_state).toBe("satisfied");
    expect(evaluation.root_group_id).toBe("root");

    const reversedInput = evaluateSatisfaction(
      structure("canonical.compilation"),
      ["a", "b", "zzz-unrelated"],
    );
    expect(reversedInput).toEqual(evaluation);

    const wrappers = structure("canonical.wrappers");
    const requirementsUseId = wrappers.root_use_id;
    if (requirementsUseId === null) {
      throw new Error("canonical.wrappers has no root use");
    }
    const requirementsPieceId = rootPiece(wrappers);
    const countTwoPiece = extraPiece(
      wrappers,
      "course_count",
      requirementsPieceId,
      { count_min: 2, count_max: 2 },
    );
    const countThreePiece = extraPiece(
      wrappers,
      "course_count",
      requirementsPieceId,
      { count_min: 3, count_max: 3 },
    );
    const tenCreditsPiece = extraPiece(
      wrappers,
      "credits",
      requirementsPieceId,
      { credits_min: 1000, credits_max: 1000 },
    );

    const basis = ["a", "b"];
    const session = new SatisfactionSession(wrappers, basis);
    expect(session.evaluate(requirementsPieceId)).toBe("satisfied");
    for (const childUse of childUses(wrappers, requirementsUseId)) {
      expect(session.evaluate(pieceOfUse(wrappers, childUse))).toBe(
        "satisfied",
      );
    }
    expect(session.evaluate(countTwoPiece)).toBe("satisfied");
    expect(session.evaluate(countThreePiece)).toBe("unsatisfied");
    expect(session.evaluate(tenCreditsPiece)).toBe("satisfied");
    expect(session.evaluate(null)).toBe("satisfied");
    expect(session.evaluate(countTwoPiece)).toBe("satisfied");

    const positionsStructure = structure("canonical.positions");
    if (positionsStructure.root_use_id === null) {
      throw new Error("canonical.positions has no root use");
    }
    const positionsPieceId = rootPiece(positionsStructure);
    const oneCoursePiece = extraPiece(
      positionsStructure,
      "course_count",
      positionsPieceId,
      { count_min: 1, count_max: 1 },
    );
    const twoCoursesPiece = extraPiece(
      positionsStructure,
      "course_count",
      positionsPieceId,
      { count_min: 2, count_max: 2 },
    );

    const positionsSession = new SatisfactionSession(positionsStructure, ["a"]);
    expect(positionsSession.evaluate(oneCoursePiece)).toBe("satisfied");
    expect(positionsSession.evaluate(twoCoursesPiece)).toBe("unsatisfied");
  });

  it("logical states follow the already filtered compilation", () => {
    const rootlessEvaluation = evaluateSatisfaction(
      structure("logical.rootless"),
      [],
    );
    expect(rootlessEvaluation.requirements_state).toBe("satisfied");

    const andEvaluation = evaluateSatisfaction(structure("logical.and"), ["a"]);
    expect(andEvaluation.requirements_state).toBe("unsatisfied");

    expect(
      evaluateSatisfaction(structure("logical.or"), ["a"]).requirements_state,
    ).toBe("satisfied");
    expect(
      evaluateSatisfaction(structure("logical.or"), []).requirements_state,
    ).toBe("unsatisfied");

    const recommendedEvaluation = evaluateSatisfaction(
      structure("logical.recommended"),
      ["recommended"],
    );
    expect(recommendedEvaluation.include_recommended).toBe(true);
    expect(recommendedEvaluation.include_inferred).toBe(false);
    expect(recommendedEvaluation.requirements_state).toBe("satisfied");

    const inferredEvaluation = evaluateSatisfaction(
      structure("logical.inferred"),
      [],
    );
    expect(inferredEvaluation.include_inferred).toBe(true);
    expect(inferredEvaluation.include_recommended).toBe(false);
    expect(inferredEvaluation.requirements_state).toBe("unsatisfied");

    const subtreeStructure = structure("logical.subtree");
    const courseAPiece = coursePiece(subtreeStructure, "a");
    const unresolvedPieceId = unresolvedPiece(
      subtreeStructure,
      "missing_course",
    );

    const subtreeSession = new SatisfactionSession(subtreeStructure, ["a"]);
    expect(subtreeSession.evaluate(courseAPiece)).toBe("satisfied");
    expect(subtreeSession.evaluate(null)).toBe("satisfied");
    expect(subtreeSession.evaluate(unresolvedPieceId)).toBe("unresolved");
    const emptySession = new SatisfactionSession(subtreeStructure, []);
    expect(emptySession.evaluate(courseAPiece)).toBe("unsatisfied");

    const leaves = Array.from(
      { length: 27 },
      (_, index) => `leaf-${String(index).padStart(2, "0")}`,
    );
    const cardinalityStructure = structure("logical.cardinality");
    expect(
      evaluateSatisfaction(cardinalityStructure, leaves).requirements_state,
    ).toBe("satisfied");
    if (cardinalityStructure.root_use_id === null) {
      throw new Error("logical.cardinality has no root use");
    }
    const countTwoPiece = extraPiece(
      cardinalityStructure,
      "course_count",
      rootPiece(cardinalityStructure),
      { count_min: 2, count_max: 2 },
    );
    const tenCreditsPiece = extraPiece(
      cardinalityStructure,
      "credits",
      countTwoPiece,
      { credits_min: 1000, credits_max: 1000 },
    );
    const twelveCreditsPiece = extraPiece(
      cardinalityStructure,
      "credits",
      rootPiece(cardinalityStructure),
      { credits_min: 1200, credits_max: 1200 },
    );

    const cardinalitySession = new SatisfactionSession(
      cardinalityStructure,
      leaves,
    );
    expect(cardinalitySession.evaluate(tenCreditsPiece)).toBe("satisfied");
    expect(cardinalitySession.evaluate(twelveCreditsPiece)).toBe("unsatisfied");
  });

  it("logical composed and requires every child", () => {
    const evaluation = evaluateSatisfaction(structure("composed.logical_and"), [
      "a",
    ]);
    expect(evaluation.requirements_state).toBe("unsatisfied");

    const both = evaluateSatisfaction(structure("composed.logical_and"), [
      "a",
      "b",
    ]);
    expect(both.requirements_state).toBe("satisfied");
  });

  it("expanded course satisfaction stops at a basis head", () => {
    const covered = evaluateSatisfaction(structure("expanded.compilation"), [
      "a",
    ]);
    expect(covered.requirements_state).toBe("satisfied");

    const withDescendant = evaluateSatisfaction(
      structure("expanded.compilation"),
      ["a", "e"],
    );
    expect(withDescendant.requirements_state).toBe("satisfied");
    expect(withDescendant.basis_group_ids).toEqual(["a", "e"]);

    const expandedStructure = structure("expanded.wrappers");
    if (expandedStructure.root_use_id === null) {
      throw new Error("expanded.wrappers has no root use");
    }
    const expandedPieceId = rootPiece(expandedStructure);
    const exactOnePiece = extraPiece(
      expandedStructure,
      "course_count",
      expandedPieceId,
      { count_min: 1, count_max: 1 },
    );
    const exactTwoPiece = extraPiece(
      expandedStructure,
      "course_count",
      expandedPieceId,
      { count_min: 2, count_max: 2 },
    );

    const expandedSession = new SatisfactionSession(expandedStructure, [
      "a",
      "e",
    ]);
    expect(expandedSession.evaluate(exactOnePiece)).toBe("satisfied");
    expect(expandedSession.evaluate(exactTwoPiece)).toBe("unsatisfied");
  });

  it("excluded completed and selected basis cannot satisfy", () => {
    const evaluation = evaluateSatisfaction(structure("excluded.compilation"), [
      "leaf",
      "head",
    ]);
    expect(evaluation.requirements_state).toBe("unsatisfied");

    const withKeep = evaluateSatisfaction(structure("excluded.compilation"), [
      "leaf",
      "head",
      "keep",
    ]);
    expect(withKeep.requirements_state).toBe("satisfied");
  });

  it("derives course and requirement box states", () => {
    const courseA = courseNode(nodeStates.display, "a");
    const courseB = courseNode(nodeStates.display, "b");
    const rootCourse = courseNode(nodeStates.display, "root");
    const andNode = nodeStates.display.nodes.find(
      (node) => node.kind === "and",
    );
    if (andNode === undefined) {
      throw new Error("display has no and node");
    }
    const report = {
      dataset_identity: "synthetic-dataset",
      solver: nodeStates.solver,
      display: nodeStates.display,
    } as unknown as PrerequisiteGraphReport;
    const input = (
      overrides: Partial<PrerequisitesRequest> = {},
    ): PrerequisitesRequest => ({
      target_code: "root",
      completed_codes: ["a"],
      selected_codes: ["a", "b"],
      excluded_codes: ["a"],
      include_recommended: false,
      include_inferred: false,
      active_only: false,
      basis: "selected",
      completed_node_keys: [],
      excluded_node_keys: [],
      ...overrides,
    });

    // The cached report carries the server's structural inputs only. The live profile marks and
    // exclusions reach the local evaluator without touching it.
    const cached = JSON.stringify(report.solver);
    const states = evaluateGraphNodeStates(report, input());
    expect(JSON.stringify(report.solver)).toBe(cached);
    expect(stateOf(states, courseA.node_id)).toEqual({
      node_id: courseA.node_id,
      is_excluded: true,
      manually_completed: false,
      completed_by_courses: true,
      satisfied_by_basis: true,
    });
    expect(stateOf(states, courseB.node_id)).toEqual({
      node_id: courseB.node_id,
      is_excluded: false,
      manually_completed: false,
      completed_by_courses: false,
      satisfied_by_basis: true,
    });
    expect(stateOf(states, rootCourse.node_id)).toEqual({
      node_id: rootCourse.node_id,
      is_excluded: false,
      manually_completed: false,
      completed_by_courses: false,
      satisfied_by_basis: false,
    });
    expect(stateOf(states, andNode.node_id)).toEqual({
      node_id: andNode.node_id,
      is_excluded: false,
      manually_completed: false,
      completed_by_courses: false,
      satisfied_by_basis: true,
    });
    const sortedIds = states
      .map((state) => state.node_id)
      .sort((first, second) => (first < second ? -1 : first > second ? 1 : 0));
    expect(states.map((state) => state.node_id)).toEqual(sortedIds);

    const completed = evaluateGraphNodeStates(
      report,
      input({ completed_node_keys: [andNode.node_id] }),
    );
    expect(stateOf(completed, andNode.node_id).manually_completed).toBe(true);
    expect(JSON.stringify(report.solver)).toBe(cached);

    const excluded = evaluateGraphNodeStates(
      report,
      input({ excluded_node_keys: [andNode.node_id] }),
    );
    expect(stateOf(excluded, andNode.node_id).is_excluded).toBe(true);
    expect(JSON.stringify(report.solver)).toBe(cached);

    // The selected basis highlights the selected set while shared completion keeps reading the
    // completed set, so an automatically fulfilled box is distinct from a basis highlight.
    expect(stateOf(states, courseA.node_id).completed_by_courses).toBe(true);
    expect(stateOf(states, andNode.node_id).completed_by_courses).toBe(false);
    expect(stateOf(states, andNode.node_id).satisfied_by_basis).toBe(true);
    const completedBasis = evaluateGraphNodeStates(
      report,
      input({
        basis: "completed",
        selected_codes: ["a"],
        completed_codes: ["a"],
        excluded_codes: [],
      }),
    );
    expect(stateOf(completedBasis, courseA.node_id).completed_by_courses).toBe(
      true,
    );
    expect(stateOf(completedBasis, courseA.node_id).satisfied_by_basis).toBe(
      true,
    );
    expect(stateOf(completedBasis, courseB.node_id).satisfied_by_basis).toBe(
      false,
    );
    expect(stateOf(completedBasis, andNode.node_id).satisfied_by_basis).toBe(
      false,
    );
    expect(JSON.stringify(report.solver)).toBe(cached);
  });
});
