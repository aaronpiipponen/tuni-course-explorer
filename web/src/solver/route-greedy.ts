/** Choose one scalar minimum-credit route after the exact search exceeds its budget. */
import type { SolverPiece } from "../api/types";
import { parseCredits } from "./credits";
import { compareKey, type KeyPart } from "./order";
import {
  candidateSelectionKey,
  type PathCandidate,
  unionCandidates,
  uniqueSortedEvidence,
} from "./route-candidate";
import {
  factIdsForSupport,
  nodeIdForSupport,
  requiredCourseGroupId,
  requiredWorkKey,
} from "./route-evaluator";
import { PathFamilies, type PathLabel } from "./route-families";
import { DrawingNodePool, type DrawingNode } from "./route-derivation";
import { mergeBlockers, type PathBlocker } from "./route-frontier";
import {
  isCourseActivityEligible,
  nodeAction,
  supportId,
  type StructureIndex,
} from "./structure";
import { conjunctionIsUnresolved, PieceEvaluator } from "./traversal";

/** One chosen scalar derivation and its available cardinality extensions. */
export type GreedyRoute = {
  candidate: PathCandidate;
  witnesses: ReadonlyMap<string, readonly [kind: string, identity: string]>;
  scalarCost: number;
  positions: readonly (readonly [number, GreedyRoute])[];
  extensionPositions: readonly (readonly [number, GreedyRoute])[];
  children: readonly GreedyRoute[];
  kind: string;
  pieceId: string;
  ownerGroupId: string;
  drawing: DrawingNode;
};

/** One route selected locally by the scalar greedy fold, or no viable route. */
export type GreedyEvaluation = {
  route: GreedyRoute | null;
  hasUnresolvedAlternative: boolean;
  blockers: readonly PathBlocker[];
  isKnown: boolean;
};

/** Return one witness map key. */
function witnessKey(kind: string, identity: string): string {
  return `${kind}\u0000${identity}`;
}

/** Return one witness map from typed pairs. */
function witnessMap(
  pairs: Iterable<readonly [string, string]>,
): Map<string, readonly [string, string]> {
  const mapped = new Map<string, readonly [string, string]>();
  for (const pair of pairs) {
    mapped.set(witnessKey(pair[0], pair[1]), [pair[0], pair[1]]);
  }
  return mapped;
}

/** Build one greedy evaluation from its route and unresolved alternative. */
function greedyEvaluation(
  route: GreedyRoute | null,
  hasUnresolvedAlternative = false,
  blockers: readonly PathBlocker[] = [],
): GreedyEvaluation {
  return {
    route,
    hasUnresolvedAlternative,
    blockers,
    isKnown: route !== null,
  };
}

/** One scalar greedy fold over a solver structure and the chosen calculation basis. */
export class GreedyPathEvaluator extends PieceEvaluator<GreedyEvaluation> {
  private readonly basis: ReadonlySet<string>;
  private readonly credits: ReadonlyMap<string, number>;
  private readonly opaqueCreditsByWorkKey: ReadonlyMap<string, number>;
  private readonly inactiveGroupIds: ReadonlySet<string>;
  private readonly cyclePathBySupport: ReadonlyMap<string, readonly string[]>;
  private readonly manualCreditsBySupport = new Map<string, number | null>();
  private readonly memo = new Map<string, GreedyEvaluation>();
  private readonly drawingPool = new DrawingNodePool();
  readonly blockedExcludedGroupIds = new Set<string>();
  readonly blockedExcludedNodeKeys = new Set<string>();

  constructor(options: {
    index: StructureIndex;
    basis: ReadonlySet<string>;
    creditsByGroupId: ReadonlyMap<string, number>;
    opaqueCreditsByWorkKey: ReadonlyMap<string, number>;
    cyclePathBySupport: ReadonlyMap<string, readonly string[]>;
    inactiveGroupIds: ReadonlySet<string>;
  }) {
    super(options.index);
    this.basis = options.basis;
    this.credits = options.creditsByGroupId;
    this.opaqueCreditsByWorkKey = options.opaqueCreditsByWorkKey;
    this.inactiveGroupIds = options.inactiveGroupIds;
    this.cyclePathBySupport = options.cyclePathBySupport;
    for (const binding of options.index.structure.bindings) {
      const credits = options.index.piece(binding.piece_id).manual_credits_min;
      this.manualCreditsBySupport.set(
        binding.support_id,
        credits === null ? null : parseCredits(credits),
      );
    }
  }

  /** Return one leaf route carrying its candidate, witnesses and scalar cost. */
  private leaf(
    candidate: PathCandidate,
    witnesses: ReadonlyMap<string, readonly [string, string]>,
    pieceId: string,
    ownerGroupId: string,
    options: { scalarCost: number; kind?: string },
  ): GreedyEvaluation {
    const nativePieceId = this.index.piece(pieceId).piece_id;
    return greedyEvaluation({
      candidate,
      witnesses,
      scalarCost: options.scalarCost,
      positions: [],
      extensionPositions: [],
      children: [],
      kind: options.kind ?? "leaf",
      pieceId,
      ownerGroupId,
      drawing: this.drawingPool.node(ownerGroupId, nativePieceId, []),
    });
  }

  /** Return the evidence label of one evaluated support. */
  private nodeLabel(support: string): PathLabel[] {
    return [[PathFamilies.NODE, support, support]];
  }

  /** Combine several routes into one operation route over their union. */
  private combine(
    routes: readonly GreedyRoute[],
    pieceId: string,
    ownerGroupId: string,
    options: {
      kind: string;
      positions?: readonly (readonly [number, GreedyRoute])[];
      extensions?: readonly (readonly [number, GreedyRoute])[];
      witnesses?: ReadonlyMap<string, readonly [string, string]>;
      drawingSlots?: readonly number[];
    },
  ): GreedyRoute {
    let witnesses = options.witnesses;
    if (witnesses === undefined) {
      const pairs: (readonly [string, string])[] = [];
      for (const route of routes) {
        pairs.push(...route.witnesses.values());
      }
      witnesses = witnessMap(pairs);
    }
    const nativePieceId = this.index.piece(pieceId).piece_id;
    const slots = options.drawingSlots ?? routes.map((_route, index) => index);
    if (slots.length !== routes.length) {
      throw new Error("a combined drawing needs one slot per input route");
    }
    return {
      candidate: unionCandidates(routes.map((route) => route.candidate)),
      witnesses,
      scalarCost: routes.reduce((total, route) => total + route.scalarCost, 0),
      positions: options.positions ?? [],
      extensionPositions: options.extensions ?? [],
      children: routes,
      kind: options.kind,
      pieceId,
      ownerGroupId,
      drawing: this.drawingPool.node(
        ownerGroupId,
        nativePieceId,
        routes.map((route, index) => ({
          slot: slots[index],
          node: route.drawing,
        })),
      ),
    };
  }

  /** Return the memoized scalar fold for one piece under its owner. */
  override evaluate(pieceId: string, ownerGroupId: string): GreedyEvaluation {
    const key = `${ownerGroupId}\u0000${pieceId}`;
    const cached = this.memo.get(key);
    if (cached !== undefined) {
      return cached;
    }
    const piece = this.index.piece(pieceId);
    const support = supportId(ownerGroupId, piece.piece_id);
    const action = nodeAction(this.index, support);
    if (action === "excluded") {
      this.blockedExcludedNodeKeys.add(support);
      return greedyEvaluation(null);
    }
    if (action === "completed") {
      const witness: readonly [string, string] = [
        PathFamilies.ATTESTED,
        support,
      ];
      const candidate: PathCandidate = {
        witnessGroupIds: [],
        newGroupIds: [],
        evidence: this.nodeLabel(support),
        newOpaqueWorkIds: [],
        witnessNonCourseIds: [[PathFamilies.ATTESTED, support]],
        shortfalls: [],
      };
      return this.leaf(
        candidate,
        witnessMap([witness]),
        pieceId,
        ownerGroupId,
        {
          scalarCost: 0,
          kind: "attested",
        },
      );
    }
    const result = super.evaluate(pieceId, ownerGroupId);
    if (result.route === null) {
      this.memo.set(key, result);
      return result;
    }
    const labels = this.nodeLabel(support);
    const route = result.route;
    const candidate: PathCandidate = {
      ...route.candidate,
      evidence: uniqueSortedEvidence([...route.candidate.evidence, ...labels]),
    };
    const labelled = greedyEvaluation(
      { ...route, candidate },
      result.hasUnresolvedAlternative,
      result.blockers,
    );
    this.memo.set(key, labelled);
    return labelled;
  }

  /** Evaluate an expanded head and its closure, stopping at a basis-covered head. */
  expandedCourse(piece: SolverPiece, ownerGroupId: string): GreedyEvaluation {
    const head = this.index.piece(piece.children[0]);
    const groupId = head.course_group_id || ownerGroupId;
    const headOwner = groupId;
    const headSupport = supportId(headOwner, head.piece_id);
    if (!isCourseActivityEligible(this.index, groupId, this.basis, true)) {
      if (this.index.excludedGroupIds.has(groupId)) {
        this.blockedExcludedGroupIds.add(groupId);
      }
      return greedyEvaluation(null);
    }
    const witness: readonly [string, string] = [PathFamilies.COURSE, groupId];
    const evidence: PathLabel[] = [
      [PathFamilies.COURSE, groupId, headSupport],
      ...this.nodeLabel(headSupport),
    ];
    const charged = this.basis.has(groupId) ? [] : [groupId];
    const headCandidate: PathCandidate = {
      witnessGroupIds: [groupId],
      newGroupIds: charged,
      evidence,
      newOpaqueWorkIds: [],
      witnessNonCourseIds: [],
      shortfalls: [],
    };
    const headRoute: GreedyRoute = {
      candidate: headCandidate,
      witnesses: witnessMap([witness]),
      scalarCost: this.basis.has(groupId) ? 0 : this.creditOf(groupId),
      positions: [],
      extensionPositions: [],
      children: [],
      kind: "head",
      pieceId: head.piece_id,
      ownerGroupId: headOwner,
      drawing: this.drawingPool.node(headOwner, head.piece_id, []),
    };
    if (this.basis.has(groupId)) {
      return greedyEvaluation({
        ...headRoute,
        kind: "expanded",
        drawing: this.drawingPool.node(ownerGroupId, piece.piece_id, [
          { slot: 0, node: headRoute.drawing },
        ]),
      });
    }
    const descendant = this.evaluate(piece.children[1], headOwner);
    if (descendant.route === null) {
      return descendant;
    }
    const combined = this.combine(
      [headRoute, descendant.route],
      piece.piece_id,
      ownerGroupId,
      {
        kind: "expanded",
        witnesses: witnessMap([witness]),
        drawingSlots: [0, 1],
      },
    );
    return greedyEvaluation(
      {
        ...combined,
        candidate: {
          ...combined.candidate,
          witnessGroupIds: [groupId],
          witnessNonCourseIds: [],
        },
      },
      descendant.hasUnresolvedAlternative,
      descendant.blockers,
    );
  }

  /** Evaluate one course leaf into its witness or denial result. */
  course(piece: SolverPiece, ownerGroupId: string): GreedyEvaluation {
    const groupId = requiredCourseGroupId(piece);
    const support = supportId(ownerGroupId, piece.piece_id);
    if (!isCourseActivityEligible(this.index, groupId, this.basis, true)) {
      if (this.index.excludedGroupIds.has(groupId)) {
        this.blockedExcludedGroupIds.add(groupId);
      }
      return greedyEvaluation(null);
    }
    if (piece.cycle_closing && !this.basis.has(groupId)) {
      const facts = factIdsForSupport(this.index.structure, support);
      const blocker: PathBlocker = {
        kind: "course_cycle",
        node_id: `course:${groupId}`,
        support_id: support,
        fact_id: facts.length > 0 ? facts[0] : null,
        reason: "course_cycle",
        referenced_group_id: null,
        detail: null,
        course_group_path: this.cyclePathBySupport.get(support) ?? [],
      };
      return greedyEvaluation(null, true, [blocker]);
    }
    const candidate: PathCandidate = {
      witnessGroupIds: [groupId],
      newGroupIds: this.basis.has(groupId) ? [] : [groupId],
      evidence: [[PathFamilies.COURSE, groupId, support]],
      newOpaqueWorkIds: [],
      witnessNonCourseIds: [],
      shortfalls: [],
    };
    return this.leaf(
      candidate,
      witnessMap([[PathFamilies.COURSE, groupId]]),
      piece.piece_id,
      ownerGroupId,
      {
        scalarCost: this.basis.has(groupId) ? 0 : this.creditOf(groupId),
      },
    );
  }

  /** Fold an unmarked module boundary transparently over its inlined child. */
  moduleBlock(piece: SolverPiece, ownerGroupId: string): GreedyEvaluation {
    const child = this.evaluate(piece.children[0], ownerGroupId);
    if (child.route === null) {
      return child;
    }
    return greedyEvaluation(
      {
        ...child.route,
        drawing: this.drawingPool.node(ownerGroupId, piece.piece_id, [
          { slot: 0, node: child.route.drawing },
        ]),
      },
      child.hasUnresolvedAlternative,
      child.blockers,
    );
  }

  /** Evaluate one opaque obligation as distinct new source work charged once. */
  opaqueCredits(piece: SolverPiece, ownerGroupId: string): GreedyEvaluation {
    const support = supportId(ownerGroupId, piece.piece_id);
    if (piece.credits_min !== null && parseCredits(piece.credits_min) === 0) {
      const candidate: PathCandidate = {
        witnessGroupIds: [],
        newGroupIds: [],
        evidence: [],
        newOpaqueWorkIds: [],
        witnessNonCourseIds: [],
        shortfalls: [],
      };
      return this.leaf(
        candidate,
        witnessMap([]),
        piece.piece_id,
        ownerGroupId,
        { scalarCost: 0 },
      );
    }
    const workKey = requiredWorkKey(piece);
    const witness: readonly [string, string] = [PathFamilies.OPAQUE, workKey];
    const candidate: PathCandidate = {
      witnessGroupIds: [],
      newGroupIds: [],
      evidence: [[PathFamilies.OPAQUE, workKey, support]],
      newOpaqueWorkIds: [workKey],
      witnessNonCourseIds: [[PathFamilies.OPAQUE, workKey]],
      shortfalls: [],
    };
    return this.leaf(
      candidate,
      witnessMap([witness]),
      piece.piece_id,
      ownerGroupId,
      {
        scalarCost:
          piece.credits_min === null ? 0 : parseCredits(piece.credits_min),
      },
    );
  }

  /** Evaluate one unresolved requirement into one explicit blocker. */
  unresolved(piece: SolverPiece, ownerGroupId: string): GreedyEvaluation {
    if (piece.reason === null) {
      throw new Error(
        `unresolved prerequisite piece ${piece.piece_id} has no reason`,
      );
    }
    const support = supportId(ownerGroupId, piece.piece_id);
    const facts = factIdsForSupport(this.index.structure, support);
    const blocker: PathBlocker = {
      kind: "unresolved_requirement",
      node_id: nodeIdForSupport(this.index.structure, support),
      support_id: support,
      fact_id: facts.length > 0 ? facts[0] : null,
      reason: piece.reason,
      referenced_group_id: piece.referenced_group_id,
      detail: piece.detail,
      course_group_path: [],
    };
    return greedyEvaluation(null, true, [blocker]);
  }

  /** Evaluate one conjunction by combining every child route. */
  conjunction(
    piece: SolverPiece,
    ownerGroupId: string,
    children: readonly GreedyEvaluation[],
  ): GreedyEvaluation {
    if (children.some((child) => child.route === null)) {
      return greedyEvaluation(
        null,
        conjunctionIsUnresolved(children),
        mergeBlockers(children.flatMap((child) => child.blockers)),
      );
    }
    const routes = children.flatMap((child) =>
      child.route === null ? [] : [child.route],
    );
    return greedyEvaluation(
      this.combine(routes, piece.piece_id, ownerGroupId, { kind: "and" }),
    );
  }

  /** Choose the best-known child route for one alternative node. */
  alternatives(
    piece: SolverPiece,
    ownerGroupId: string,
    children: readonly GreedyEvaluation[],
  ): GreedyEvaluation {
    const viable: [number, GreedyRoute][] = [];
    children.forEach((child, index) => {
      if (child.route !== null) {
        viable.push([index, child.route]);
      }
    });
    if (viable.length === 0) {
      return greedyEvaluation(
        null,
        children.some((child) => child.hasUnresolvedAlternative),
        mergeBlockers(children.flatMap((child) => child.blockers)),
      );
    }
    let chosen = viable[0];
    let chosenKey = this.selectionKey(chosen[1]);
    for (const option of viable.slice(1)) {
      const key = this.selectionKey(option[1]);
      if (compareKey(key, chosenKey) < 0) {
        chosen = option;
        chosenKey = key;
      }
    }
    return greedyEvaluation(
      this.combine([chosen[1]], piece.piece_id, ownerGroupId, {
        kind: "or",
        drawingSlots: [chosen[0]],
      }),
    );
  }

  /** Choose the cheapest required positions and keep the rest as extensions. */
  cardinality(
    piece: SolverPiece,
    ownerGroupId: string,
    children: readonly GreedyEvaluation[],
  ): GreedyEvaluation {
    const viable: [number, GreedyRoute][] = [];
    children.forEach((child, index) => {
      if (child.route !== null) {
        viable.push([index, child.route]);
      }
    });
    viable.sort((first, second) =>
      compareKey(
        [...this.selectionKey(first[1]), first[0]],
        [...this.selectionKey(second[1]), second[0]],
      ),
    );
    const required = piece.require_min ?? 0;
    const maximum = Math.min(
      piece.require_max ?? children.length,
      children.length,
    );
    if (viable.length < required) {
      return greedyEvaluation(null);
    }
    const selected = viable.slice(0, required);
    const remaining = viable.slice(required, maximum);
    return greedyEvaluation(
      this.combine(
        selected.map(([, route]) => route),
        piece.piece_id,
        ownerGroupId,
        {
          kind: "cardinality",
          positions: selected,
          extensions: remaining,
          drawingSlots: selected.map(([index]) => index),
        },
      ),
    );
  }

  /** Extend a chosen route until one numeric bound holds, or fail the fold. */
  bounded(
    piece: SolverPiece,
    ownerGroupId: string,
    child: GreedyEvaluation,
  ): GreedyEvaluation {
    if (child.route === null) {
      return child;
    }
    let route = child.route;
    const credits = piece.kind === "credits";
    const lower = credits
      ? piece.credits_min === null
        ? 0
        : parseCredits(piece.credits_min)
      : (piece.count_min ?? 0);
    const upper = credits
      ? piece.credits_max === null
        ? null
        : parseCredits(piece.credits_max)
      : piece.count_max;
    if (lower === 0 && upper === null) {
      return greedyEvaluation({
        ...route,
        kind: "bounded",
        pieceId: piece.piece_id,
        ownerGroupId,
        positions: [],
        children: [route],
        drawing: this.drawingPool.node(ownerGroupId, piece.piece_id, [
          { slot: 0, node: route.drawing },
        ]),
      });
    }
    let metric = this.metric(route.witnesses, credits);
    while (metric !== null && metric < lower) {
      let extension: GreedyRoute | null = null;
      let extensionKey: KeyPart[] | null = null;
      for (const candidate of this.nextExtensions(route)) {
        const value = this.metric(candidate.witnesses, credits);
        if (value === null || (upper !== null && value > upper)) {
          continue;
        }
        const key = this.selectionKey(candidate);
        if (extensionKey === null || compareKey(key, extensionKey) < 0) {
          extension = candidate;
          extensionKey = key;
        }
      }
      if (extension === null) {
        return greedyEvaluation(null);
      }
      route = extension;
      metric = this.metric(route.witnesses, credits);
    }
    if (
      metric === null ||
      (upper !== null && metric > upper) ||
      metric < lower
    ) {
      return greedyEvaluation(null);
    }
    return greedyEvaluation({
      ...route,
      kind: "bounded",
      pieceId: piece.piece_id,
      ownerGroupId,
      positions: [],
      children: [route],
      drawing: this.drawingPool.node(ownerGroupId, piece.piece_id, [
        { slot: 0, node: route.drawing },
      ]),
    });
  }

  /** Return one course's canonical credit cost, throwing when it is missing. */
  private creditOf(groupId: string): number {
    const credits = this.credits.get(groupId);
    if (credits === undefined) {
      throw new Error(
        `course ${groupId} is missing from the calculation structure courses`,
      );
    }
    return credits;
  }

  /** Return one route's candidate selection key with its scalar cost. */
  private selectionKey(route: GreedyRoute): KeyPart[] {
    return candidateSelectionKey(
      route.candidate,
      this.credits,
      this.opaqueCreditsByWorkKey,
      this.inactiveGroupIds,
      route.scalarCost,
    );
  }

  /** Return the total of one witness set in credits or course count, or `null` when unknown. */
  private metric(
    witnesses: ReadonlyMap<string, readonly [string, string]>,
    credits: boolean,
  ): number | null {
    let total = 0;
    for (const [kind, identity] of witnesses.values()) {
      if (kind === PathFamilies.COURSE) {
        total += credits ? this.creditOf(identity) : 1;
      } else if (kind === PathFamilies.OPAQUE) {
        if (!credits) {
          return null;
        }
        const value = this.opaqueCreditsByWorkKey.get(identity);
        if (value === undefined) {
          throw new Error(`opaque work ${identity} has no credit value`);
        }
        total += value;
      } else {
        const extent = this.manualCreditsBySupport.get(identity);
        if (!credits || extent === undefined || extent === null) {
          return null;
        }
        total += extent;
      }
    }
    return total;
  }

  /** Return every valid one-step extension of a chosen route. */
  private nextExtensions(route: GreedyRoute): GreedyRoute[] {
    const choices: GreedyRoute[] = [];
    if (route.kind === "cardinality" && route.extensionPositions.length > 0) {
      const [index, option] = route.extensionPositions[0];
      const positions = [...route.positions, [index, option] as const];
      const combined = this.combine(
        positions.map(([, selected]) => selected),
        route.pieceId,
        route.ownerGroupId,
        {
          kind: "cardinality",
          positions,
          extensions: route.extensionPositions.slice(1),
          drawingSlots: positions.map(([position]) => position),
        },
      );
      const rebuilt = this.rebasedDrawing(route, combined);
      if (this.valid(rebuilt)) {
        choices.push(rebuilt);
      }
    }
    if (route.kind === "expanded") {
      return choices;
    }
    const slots =
      route.kind === "cardinality"
        ? route.positions.map(([index]) => index)
        : this.drawingFrame(route).children.map((child) => child.slot);
    route.children.forEach((child, position) => {
      for (const extended of this.nextExtensions(child)) {
        const replaced = [...route.children];
        replaced[position] = extended;
        let combined: GreedyRoute;
        if (route.kind === "cardinality") {
          const selectedPositions = [...route.positions];
          selectedPositions[position] = [
            selectedPositions[position][0],
            extended,
          ];
          combined = this.combine(replaced, route.pieceId, route.ownerGroupId, {
            kind: route.kind,
            positions: selectedPositions,
            extensions: route.extensionPositions,
            drawingSlots: slots,
          });
        } else {
          combined = this.combine(replaced, route.pieceId, route.ownerGroupId, {
            kind: route.kind,
            positions: route.positions,
            extensions: route.extensionPositions,
            drawingSlots: slots,
          });
        }
        const rebuilt = this.rebasedDrawing(route, combined);
        if (this.valid(rebuilt)) {
          choices.push(rebuilt);
        }
      }
    });
    return choices;
  }

  /** Return one rebuilt route with its operation frame replaced under any module prefix. */
  private rebasedDrawing(
    route: GreedyRoute,
    rebuilt: GreedyRoute,
  ): GreedyRoute {
    return {
      ...rebuilt,
      drawing: this.replaceDrawingFrame(
        route.drawing,
        rebuilt.drawing,
        route.ownerGroupId,
        route.pieceId,
      ),
    };
  }

  /** Return the drawing frame that carries one route's algorithm owner and piece. */
  private drawingFrame(route: GreedyRoute): DrawingNode {
    let node = route.drawing;
    while (
      node.ownerGroupId !== route.ownerGroupId ||
      node.pieceId !== route.pieceId
    ) {
      const child = node.children[0];
      if (node.children.length !== 1 || child === undefined) {
        throw new Error("a module drawing prefix has no single child");
      }
      node = child.node;
    }
    return node;
  }

  /** Return the drawing with one matching frame replaced and its prefix re-interned. */
  private replaceDrawingFrame(
    original: DrawingNode,
    replacement: DrawingNode,
    ownerGroupId: string,
    pieceId: string,
  ): DrawingNode {
    if (
      original.ownerGroupId === ownerGroupId &&
      original.pieceId === pieceId
    ) {
      return replacement;
    }
    const child = original.children[0];
    if (original.children.length !== 1 || child === undefined) {
      throw new Error("a module drawing prefix has no single child");
    }
    return this.drawingPool.node(original.ownerGroupId, original.pieceId, [
      {
        slot: child.slot,
        node: this.replaceDrawingFrame(
          child.node,
          replacement,
          ownerGroupId,
          pieceId,
        ),
      },
    ]);
  }

  /** Certify every selected guard, cardinality position, and nested numeric bound. */
  valid(route: GreedyRoute): boolean {
    if (route.kind === "attested") {
      return true;
    }
    if (!route.children.every((child) => this.valid(child))) {
      return false;
    }
    const piece = this.index.piece(route.pieceId);
    if (piece.kind === "cardinality") {
      const count = route.positions.length;
      if (
        count < (piece.require_min ?? 0) ||
        (piece.require_max !== null && count > piece.require_max)
      ) {
        return false;
      }
    }
    if (piece.kind === "credits" || piece.kind === "course_count") {
      if (route.children.length === 0) {
        return false;
      }
      const credits = piece.kind === "credits";
      const lower = credits
        ? piece.credits_min === null
          ? 0
          : parseCredits(piece.credits_min)
        : (piece.count_min ?? 0);
      const upper = credits
        ? piece.credits_max === null
          ? null
          : parseCredits(piece.credits_max)
        : piece.count_max;
      if (lower === 0 && upper === null) {
        return true;
      }
      const value = this.metric(route.children[0].witnesses, credits);
      if (
        value === null ||
        value < lower ||
        (upper !== null && value > upper)
      ) {
        return false;
      }
    }
    return true;
  }
}
