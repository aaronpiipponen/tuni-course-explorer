/** Pure prerequisite-satisfaction and graph box-state evaluation over a solver structure. */
import type {
  GraphDisplayNode,
  GraphNodeState,
  SolverPiece,
  SolverStructure,
  SolverSupportBinding,
} from "../api/types";
import { parseCredits } from "./credits";
import { Families, type VariableOrder } from "./families";
import {
  creditsByGroupId,
  indexStructure,
  isCourseActivityEligible,
  nodeAction,
  supportId,
  type StructureIndex,
} from "./structure";
import { conjunctionIsUnresolved, PieceEvaluator } from "./traversal";

/** Tri-state satisfaction of one prerequisite requirement. */
export type SatisfactionState = "satisfied" | "unsatisfied" | "unresolved";

/** One satisfaction witness: a canonical course or one attested graph mark. */
type Witness = readonly ["course" | "attested", string];

const witnessOrder: VariableOrder<Witness> = {
  compare(first: Witness, second: Witness): number {
    if (first[0] !== second[0]) {
      return first[0] < second[0] ? -1 : 1;
    }
    if (first[1] === second[1]) {
      return 0;
    }
    return first[1] < second[1] ? -1 : 1;
  },
  key(variable: Witness): string {
    return `${variable[0]}:${variable[1]}`;
  },
};

/** One transient decision DAG of exact satisfaction witness families. */
class WitnessFamilies extends Families<Witness> {
  private readonly creditsByGroupId: ReadonlyMap<string, number>;
  private readonly attestedCredits = new Map<string, number | null>();

  constructor(creditsByGroupId: ReadonlyMap<string, number>) {
    super(witnessOrder);
    this.creditsByGroupId = creditsByGroupId;
  }

  /** Return the singleton family holding exactly the one-course witness. */
  course(groupId: string): number {
    return this.singleton([["course", groupId]]);
  }

  /** Return the singleton family holding exactly one attested manual-completion witness. */
  attested(support: string, credits: number | null): number {
    this.attestedCredits.set(support, credits);
    return this.singleton([["attested", support]]);
  }

  /** Return one witness variable's minimum-credit weight. */
  creditWeight(variable: Witness): number {
    const [kind, identity] = variable;
    if (kind === "attested") {
      const credits = this.attestedCredits.get(identity);
      if (credits === undefined || credits === null) {
        throw new Error(
          "unknown-measure attested witness cannot be credit-weighted",
        );
      }
      return credits;
    }
    return this.creditsByGroupId.get(identity) ?? 0;
  }

  /** Return one witness variable's unit course-count weight. */
  countWeight(variable: Witness): number {
    return variable[0] === "course" ? 1 : 0;
  }

  /** Return whether one witness variable has no known source credit extent. */
  isUnknownCredit(variable: Witness): boolean {
    return (
      variable[0] === "attested" &&
      (this.attestedCredits.get(variable[1]) ?? null) === null
    );
  }

  /** Return whether one witness variable is not a real counted course. */
  isUnknownCount(variable: Witness): boolean {
    return variable[0] !== "course";
  }
}

/** One piece's exact witness family plus whether an unknown witness could exist. */
type CandidateEvaluation = {
  readonly family: number;
  readonly hasUnresolvedAlternative: boolean;
  readonly isKnown: boolean;
};

/** Build one candidate evaluation from its family and unresolved flag. */
function candidate(
  family: number,
  hasUnresolvedAlternative: boolean,
): CandidateEvaluation {
  return {
    family,
    hasUnresolvedAlternative,
    isKnown: family !== Families.ZERO,
  };
}

/** Map one candidate evaluation to its tri-state satisfaction. */
function stateFromCandidate(
  evaluation: CandidateEvaluation,
): SatisfactionState {
  if (evaluation.isKnown) {
    return "satisfied";
  }
  if (evaluation.hasUnresolvedAlternative) {
    return "unresolved";
  }
  return "unsatisfied";
}

/** One satisfaction fold over a solver structure and the chosen calculation basis. */
class SatisfactionEvaluator extends PieceEvaluator<CandidateEvaluation> {
  private readonly basis: ReadonlySet<string>;
  private readonly families: WitnessFamilies;
  private readonly memo = new Map<string, CandidateEvaluation>();

  constructor(
    index: StructureIndex,
    basis: ReadonlySet<string>,
    families: WitnessFamilies,
  ) {
    super(index);
    this.basis = basis;
    this.families = families;
  }

  /** Return one piece's memoized candidate evaluation under its owner course. */
  override evaluate(
    pieceId: string,
    ownerGroupId: string,
  ): CandidateEvaluation {
    const key = `${ownerGroupId}\u0000${pieceId}`;
    const cached = this.memo.get(key);
    if (cached !== undefined) {
      return cached;
    }
    const result = super.evaluate(pieceId, ownerGroupId);
    this.memo.set(key, result);
    return result;
  }

  /** Apply the shared support guard: exclusion first, then manual completion. */
  override nodeOverride(
    piece: SolverPiece,
    ownerGroupId: string,
  ): CandidateEvaluation | null {
    const support = supportId(ownerGroupId, piece.piece_id);
    const action = nodeAction(this.index, support);
    if (action === "excluded") {
      return candidate(Families.ZERO, false);
    }
    if (action === "completed") {
      const credits =
        piece.manual_credits_min === null
          ? null
          : parseCredits(piece.manual_credits_min);
      return candidate(this.families.attested(support, credits), false);
    }
    return null;
  }

  /** Evaluate an expanded branch as its head and, for a non-basis head, its closure. */
  expandedCourse(
    piece: SolverPiece,
    ownerGroupId: string,
  ): CandidateEvaluation {
    const head = this.index.piece(piece.children[0]);
    const headOwner = head.course_group_id || ownerGroupId;
    const headEvaluation = this.evaluate(head.piece_id, headOwner);
    if (head.course_group_id !== null && this.basis.has(head.course_group_id)) {
      return headEvaluation;
    }
    if (!headEvaluation.isKnown && !headEvaluation.hasUnresolvedAlternative) {
      return headEvaluation;
    }
    const descendantEvaluation = this.evaluate(piece.children[1], headOwner);
    const projected = this.families.project(
      descendantEvaluation.family,
      () => true,
    );
    return this.combineRequired([
      headEvaluation,
      candidate(projected, descendantEvaluation.hasUnresolvedAlternative),
    ]);
  }

  /** Evaluate one course leaf. Only an eligible basis course is a witness. */
  course(piece: SolverPiece, _ownerGroupId: string): CandidateEvaluation {
    const groupId = piece.course_group_id ?? "";
    if (!isCourseActivityEligible(this.index, groupId, this.basis, true)) {
      return candidate(Families.ZERO, false);
    }
    if (this.basis.has(groupId)) {
      return candidate(this.families.course(groupId), false);
    }
    return candidate(Families.ZERO, piece.cycle_closing);
  }

  /** Fold an unmarked module boundary transparently over its inlined child. */
  moduleBlock(piece: SolverPiece, ownerGroupId: string): CandidateEvaluation {
    return this.evaluate(piece.children[0], ownerGroupId);
  }

  /** Evaluate one opaque obligation: an explicit zero requirement is satisfied. */
  opaqueCredits(
    piece: SolverPiece,
    _ownerGroupId: string,
  ): CandidateEvaluation {
    if (piece.credits_min !== null && parseCredits(piece.credits_min) === 0) {
      return candidate(Families.ONE, false);
    }
    return candidate(Families.ZERO, false);
  }

  /** Evaluate one unresolved requirement as an unknown route with no known witness. */
  unresolved(_piece: SolverPiece, _ownerGroupId: string): CandidateEvaluation {
    return candidate(Families.ZERO, true);
  }

  /** Combine an ordinary logical conjunction's child evaluations. */
  conjunction(
    _piece: SolverPiece,
    _ownerGroupId: string,
    children: readonly CandidateEvaluation[],
  ): CandidateEvaluation {
    return this.combineRequired(children);
  }

  /** Union every known child witness family and OR the unresolved flag. */
  alternatives(
    _piece: SolverPiece,
    _ownerGroupId: string,
    children: readonly CandidateEvaluation[],
  ): CandidateEvaluation {
    let family = Families.ZERO;
    for (const child of children) {
      family = this.families.union(family, child.family);
    }
    return candidate(
      family,
      children.some((child) => child.hasUnresolvedAlternative),
    );
  }

  /** Fold allowed child selections as one position DP over witness families. */
  cardinality(
    piece: SolverPiece,
    _ownerGroupId: string,
    children: readonly CandidateEvaluation[],
  ): CandidateEvaluation {
    const requiredMin = piece.require_min ?? 0;
    const upper = Math.min(
      piece.require_max ?? children.length,
      children.length,
    );
    let rows: number[] = new Array<number>(upper + 1).fill(Families.ZERO);
    rows[0] = Families.ONE;
    for (const child of children) {
      const nextRow: number[] = new Array<number>(upper + 1).fill(
        Families.ZERO,
      );
      for (let count = 0; count <= upper; count += 1) {
        let selected = rows[count];
        if (count > 0) {
          selected = this.families.union(
            selected,
            this.families.join(rows[count - 1], child.family),
          );
        }
        nextRow[count] = selected;
      }
      rows = nextRow;
    }
    let family = Families.ZERO;
    for (let count = requiredMin; count <= upper; count += 1) {
      family = this.families.union(family, rows[count]);
    }
    const viable = children.filter(
      (child) => child.isKnown || child.hasUnresolvedAlternative,
    ).length;
    const unresolvedChildren = children.filter(
      (child) => child.hasUnresolvedAlternative,
    ).length;
    return candidate(
      family,
      unresolvedChildren > 0 &&
        Math.max(requiredMin, 1) <= Math.min(upper, viable),
    );
  }

  /** Keep known-measure witnesses inside the bounds. Carry unknown support as unresolved. */
  bounded(
    piece: SolverPiece,
    _ownerGroupId: string,
    child: CandidateEvaluation,
  ): CandidateEvaluation {
    let weight: (variable: Witness) => number;
    let lower: number;
    let upper: number | null;
    let isUnknown: (variable: Witness) => boolean;
    if (piece.kind === "credits") {
      weight = (variable) => this.families.creditWeight(variable);
      lower = piece.credits_min === null ? 0 : parseCredits(piece.credits_min);
      upper =
        piece.credits_max === null ? null : parseCredits(piece.credits_max);
      isUnknown = (variable) => this.families.isUnknownCredit(variable);
    } else {
      weight = (variable) => this.families.countWeight(variable);
      lower = piece.count_min ?? 0;
      upper = piece.count_max;
      isUnknown = (variable) => this.families.isUnknownCount(variable);
    }
    if (lower === 0 && upper === null) {
      return child;
    }
    const [known, unknownMember] = this.families.splitByPredicate(
      child.family,
      isUnknown,
    );
    const family = this.families.filter(known, { weight, lower, upper });
    const nontrivial = lower > 0 || upper !== null;
    return candidate(
      family,
      child.hasUnresolvedAlternative ||
        (unknownMember !== Families.ZERO && nontrivial),
    );
  }

  /** Join child witness families with ordinary AND semantics. */
  private combineRequired(
    children: readonly CandidateEvaluation[],
  ): CandidateEvaluation {
    let family = Families.ONE;
    for (const child of children) {
      family = this.families.join(family, child.family);
    }
    return candidate(family, conjunctionIsUnresolved(children));
  }
}

/** One request-local satisfaction context over a fixed solver structure and basis. */
export class SatisfactionSession {
  readonly basisGroupIds: ReadonlySet<string>;
  private readonly structure: SolverStructure;
  private readonly evaluator: SatisfactionEvaluator;

  constructor(structure: SolverStructure, basisGroupIds: Iterable<string>) {
    const basis = new Set<string>();
    for (const groupId of basisGroupIds) {
      if (groupId.trim().length === 0) {
        throw new Error("basis group_id must not be blank");
      }
      basis.add(groupId);
    }
    const credits = creditsByGroupId(structure);
    this.structure = structure;
    this.basisGroupIds = basis;
    this.evaluator = new SatisfactionEvaluator(
      indexStructure(structure),
      basis,
      new WitnessFamilies(credits),
    );
  }

  /** Return one piece's public tri-state. A `null` piece is satisfied. */
  evaluate(pieceId: string | null, ownerGroupId?: string): SatisfactionState {
    if (pieceId === null) {
      return "satisfied";
    }
    const owner = ownerGroupId || this.structure.root_group_id;
    return stateFromCandidate(this.evaluator.evaluate(pieceId, owner));
  }
}

/** One satisfaction report of a solver structure against the chosen calculation basis. */
export type SatisfactionEvaluation = {
  root_group_id: string;
  include_recommended: boolean;
  include_inferred: boolean;
  active_only: boolean;
  basis_group_ids: string[];
  requirements_state: SatisfactionState;
};

/**
 * Evaluate a solver structure against one basis of covered canonical courses.
 *
 * The root group's own exclusion decides an unsatisfied result before the basis is read. A
 * structure with no root use is satisfied by its empty requirement.
 */
export function evaluateSatisfaction(
  structure: SolverStructure,
  basisGroupIds: Iterable<string>,
): SatisfactionEvaluation {
  const session = new SatisfactionSession(structure, basisGroupIds);
  let requirementsState: SatisfactionState;
  if (structure.excluded_group_ids.includes(structure.root_group_id)) {
    requirementsState = "unsatisfied";
  } else if (session.basisGroupIds.has(structure.root_group_id)) {
    requirementsState = "satisfied";
  } else {
    const pieceId =
      structure.root_use_id === null
        ? null
        : indexStructure(structure).use(structure.root_use_id).piece_id;
    requirementsState = session.evaluate(pieceId, structure.root_group_id);
  }
  return {
    root_group_id: structure.root_group_id,
    include_recommended: structure.include_recommended,
    include_inferred: structure.include_inferred,
    active_only: structure.active_only,
    basis_group_ids: [...session.basisGroupIds].sort(),
    requirements_state: requirementsState,
  };
}

/**
 * Return one presentation state per emitted display node.
 *
 * Course states read the canonical excluded, completed and basis sets. A non-course node is
 * automatic only when at least one calculation piece binds to it and every bound piece is
 * satisfied in the unmarked completed-only and chosen-basis contexts. Manual flags are direct
 * binding mark lookups with exclusion precedence. The result is sorted by node ID.
 */
export function evaluateNodeStates(
  structure: SolverStructure,
  basisGroupIds: Iterable<string>,
  displayNodes: readonly GraphDisplayNode[],
  completedGroupIds: Iterable<string>,
): GraphNodeState[] {
  const basis = new Set(basisGroupIds);
  const completed = new Set(completedGroupIds);
  const excludedGroupIds = new Set(structure.excluded_group_ids);
  const completedNodeKeys = new Set(structure.completed_node_keys);
  const excludedNodeKeys = new Set(structure.excluded_node_keys);
  const shallow: SolverStructure = {
    ...structure,
    completed_node_keys: [],
    excluded_node_keys: [],
    excluded_group_ids: [],
  };
  const completedSession = new SatisfactionSession(shallow, completed);
  const basisSession = new SatisfactionSession(shallow, basis);
  const bindingsByNode = new Map<string, SolverSupportBinding[]>();
  for (const binding of structure.bindings) {
    for (const nodeId of binding.node_ids) {
      const bound = bindingsByNode.get(nodeId) ?? [];
      bound.push(binding);
      bindingsByNode.set(nodeId, bound);
    }
  }
  const states: GraphNodeState[] = [];
  for (const node of displayNodes) {
    if (node.kind === "course" && node.course_group_id !== null) {
      const groupId = node.course_group_id;
      states.push({
        node_id: node.node_id,
        is_excluded: excludedGroupIds.has(groupId),
        manually_completed: false,
        completed_by_courses: completed.has(groupId),
        satisfied_by_basis: basis.has(groupId),
      });
      continue;
    }
    const automatic =
      node.kind !== "ignored" && node.kind !== "internal_requirement";
    const bindings = bindingsByNode.get(node.node_id) ?? [];
    const completedByCourses =
      automatic &&
      bindings.length > 0 &&
      bindings.every(
        (binding) =>
          completedSession.evaluate(
            binding.piece_id,
            binding.owner_group_id,
          ) === "satisfied",
      );
    const satisfiedByBasis =
      automatic &&
      bindings.length > 0 &&
      bindings.every(
        (binding) =>
          basisSession.evaluate(binding.piece_id, binding.owner_group_id) ===
          "satisfied",
      );
    states.push({
      node_id: node.node_id,
      is_excluded: excludedNodeKeys.has(node.node_id),
      manually_completed: completedNodeKeys.has(node.node_id),
      completed_by_courses: completedByCourses,
      satisfied_by_basis: satisfiedByBasis,
    });
  }
  states.sort((first, second) =>
    first.node_id < second.node_id
      ? -1
      : first.node_id > second.node_id
        ? 1
        : 0,
  );
  return states;
}
