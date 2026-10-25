/** One exact bottom-up path fold over the native solver structure and its graph marks. */
import type { PathProblem, SolverPiece, SolverStructure } from "../api/types";
import { parseCredits } from "./credits";
import { Families } from "./families";
import { MinHeap } from "./heap";
import { compareKey } from "./order";
import {
  combineFrontiers,
  mergeBlockers,
  PathFrontier,
  type PathBlocker,
} from "./route-frontier";
import {
  PathFamilies,
  type PathLabel,
  type PathVariable,
} from "./route-families";
import {
  countShortfall,
  creditShortfall,
  shortfallsKey,
} from "./route-shortfall";
import {
  isCourseActivityEligible,
  nodeAction,
  supportId,
  type StructureIndex,
} from "./structure";
import { conjunctionIsUnresolved, PieceEvaluator } from "./traversal";

/** One compact candidate frontier plus any viable unresolved alternative and blockers. */
export type PathEvaluation = {
  candidates: PathFrontier;
  hasUnresolvedAlternative: boolean;
  blockers: readonly PathBlocker[];
  isKnown: boolean;
};

/** Return a course piece's group id, throwing on a malformed structure. */
export function requiredCourseGroupId(piece: SolverPiece): string {
  if (piece.course_group_id === null) {
    throw new Error(`course piece ${piece.piece_id} has no course group id`);
  }
  return piece.course_group_id;
}

/** Return an opaque piece's work key, throwing on a malformed structure. */
export function requiredWorkKey(piece: SolverPiece): string {
  if (piece.work_key === null) {
    throw new Error(`opaque piece ${piece.piece_id} has no work key`);
  }
  return piece.work_key;
}

/** Return whether one native piece carries the compiler's module-rule activity semantics. */
function isModuleRulePosition(piece: SolverPiece): boolean {
  return piece.module_rule && piece.kind !== "expanded_course";
}

/** Build one path evaluation from its frontier and unresolved alternative. */
export function pathEvaluation(
  candidates: PathFrontier,
  hasUnresolvedAlternative: boolean,
  blockers: readonly PathBlocker[],
): PathEvaluation {
  return {
    candidates,
    hasUnresolvedAlternative,
    blockers,
    isKnown: candidates.isKnown,
  };
}

/** Return one scoped support's drawn location, or the root course when it has none. */
export function nodeIdForSupport(
  structure: SolverStructure,
  support: string,
): string {
  for (const binding of structure.bindings) {
    if (binding.support_id === support && binding.node_ids.length > 0) {
      return binding.node_ids[0];
    }
  }
  return `course:${structure.root_group_id}`;
}

/** Return every distinct provenance fact bound to one scoped support, sorted. */
export function factIdsForSupport(
  structure: SolverStructure,
  support: string,
): string[] {
  const useIds = new Set<string>();
  for (const binding of structure.bindings) {
    if (binding.support_id === support) {
      for (const useId of binding.use_ids) {
        useIds.add(useId);
      }
    }
  }
  const facts = new Set<string>();
  for (const use of structure.uses) {
    if (useIds.has(use.use_id)) {
      facts.add(use.fact_id);
    }
  }
  return [...facts].sort();
}

/** Return one deterministic shortest course path to each cycle-closing support. */
export function cycleSupportPaths(
  structure: SolverStructure,
): Map<string, string[]> {
  const paths = new Map<string, string[]>();
  if (structure.root_use_id === null) {
    return paths;
  }
  const uses = new Map(structure.uses.map((use) => [use.use_id, use]));
  const pieces = new Map(
    structure.pieces.map((piece) => [piece.piece_id, piece]),
  );
  type QueueItem = readonly [
    cost: number,
    slots: readonly number[],
    useId: string,
    owner: string,
    path: readonly string[],
  ];
  const order = (first: QueueItem, second: QueueItem) =>
    compareKey(
      [first[0], first[1], first[2], first[3], first[4]],
      [second[0], second[1], second[2], second[3], second[4]],
    );
  const best = new Map<string, readonly [number, readonly number[]]>();
  const rootMarker = `${structure.root_use_id}\u0000${structure.root_group_id}`;
  best.set(rootMarker, [0, []]);
  const finalized = new Set<string>();
  const queue = new MinHeap<QueueItem>(order);
  queue.push([
    0,
    [],
    structure.root_use_id,
    structure.root_group_id,
    [structure.root_group_id],
  ]);
  while (queue.size > 0) {
    const [cost, slots, useId, owner, path] = queue.pop();
    const marker = `${useId}\u0000${owner}`;
    const current = best.get(marker);
    if (
      finalized.has(marker) ||
      current === undefined ||
      compareKey([current[0], current[1]], [cost, slots]) !== 0
    ) {
      continue;
    }
    finalized.add(marker);
    const use = uses.get(useId);
    if (use === undefined) {
      continue;
    }
    const piece = pieces.get(use.piece_id);
    if (piece === undefined) {
      throw new Error(`unknown prerequisite piece ${use.piece_id}`);
    }
    const support = supportId(owner, piece.piece_id);
    if (piece.kind === "course" && piece.cycle_closing) {
      const groupId = requiredCourseGroupId(piece);
      const record =
        path[path.length - 1] === groupId ? [...path] : [...path, groupId];
      if (!paths.has(support)) {
        paths.set(support, record);
      }
    }
    const childSpecs: [number, string, string, readonly string[]][] = [];
    if (piece.kind === "expanded_course" && use.children.length === 2) {
      const [headUse, descendantsUse] = use.children;
      const headPiece = pieces.get(uses.get(headUse)?.piece_id ?? "");
      if (headPiece === undefined) {
        throw new Error(`unknown prerequisite piece for use ${headUse}`);
      }
      const headOwner = headPiece.course_group_id || owner;
      const headPath =
        headOwner !== path[path.length - 1] ? [...path, headOwner] : path;
      childSpecs.push([0, headUse, headOwner, headPath]);
      childSpecs.push([1, descendantsUse, headOwner, headPath]);
    } else {
      use.children.forEach((childUse, index) => {
        childSpecs.push([index, childUse, owner, path]);
      });
    }
    for (const [index, childUse, childOwner, childPath] of childSpecs) {
      const childMarker = `${childUse}\u0000${childOwner}`;
      if (finalized.has(childMarker)) {
        continue;
      }
      const candidate: readonly [number, readonly number[]] = [
        cost + (childOwner !== owner ? 1 : 0),
        [...slots, index],
      ];
      const existing = best.get(childMarker);
      if (
        existing !== undefined &&
        compareKey([existing[0], existing[1]], candidate) <= 0
      ) {
        continue;
      }
      best.set(childMarker, candidate);
      queue.push([candidate[0], candidate[1], childUse, childOwner, childPath]);
    }
  }
  return paths;
}

/** One exact path fold over a solver structure and the chosen calculation basis. */
export class PathEvaluator extends PieceEvaluator<PathEvaluation> {
  private readonly basis: ReadonlySet<string>;
  private readonly activityExceptionGroupIds: ReadonlySet<string>;
  private readonly allowModuleShortfall: boolean;
  private readonly families: PathFamilies;
  private readonly blockedExcludedGroupIds: Set<string> | null;
  private readonly blockedExcludedNodeKeys: Set<string> | null;
  private readonly problems: PathProblem[] | null;
  private readonly cyclePathBySupport: ReadonlyMap<string, readonly string[]>;
  private readonly memo = new Map<string, PathEvaluation>();

  constructor(options: {
    index: StructureIndex;
    basis: ReadonlySet<string>;
    activityExceptionGroupIds: ReadonlySet<string>;
    allowModuleShortfall: boolean;
    families: PathFamilies;
    blockedExcludedGroupIds: Set<string> | null;
    blockedExcludedNodeKeys: Set<string> | null;
    problems: PathProblem[] | null;
    cyclePathBySupport: ReadonlyMap<string, readonly string[]>;
  }) {
    super(options.index);
    this.basis = options.basis;
    this.activityExceptionGroupIds = options.activityExceptionGroupIds;
    this.allowModuleShortfall = options.allowModuleShortfall;
    this.families = options.families;
    this.blockedExcludedGroupIds = options.blockedExcludedGroupIds;
    this.blockedExcludedNodeKeys = options.blockedExcludedNodeKeys;
    this.problems = options.problems;
    this.cyclePathBySupport = options.cyclePathBySupport;
  }

  /** Return a diagnostic copy over the same families with no collectors and a fresh memo. */
  private diagnostic(options: {
    activityExceptionGroupIds: ReadonlySet<string>;
    allowModuleShortfall: boolean;
  }): PathEvaluator {
    return new PathEvaluator({
      index: this.index,
      basis: this.basis,
      activityExceptionGroupIds: options.activityExceptionGroupIds,
      allowModuleShortfall: options.allowModuleShortfall,
      families: this.families,
      blockedExcludedGroupIds: null,
      blockedExcludedNodeKeys: null,
      problems: null,
      cyclePathBySupport: this.cyclePathBySupport,
    });
  }

  /** Return the memoized fold for one piece under its owner, with its node label. */
  override evaluate(pieceId: string, ownerGroupId: string): PathEvaluation {
    const key = `${ownerGroupId}\u0000${pieceId}`;
    const cached = this.memo.get(key);
    if (cached !== undefined) {
      return cached;
    }
    const result = super.evaluate(pieceId, ownerGroupId);
    if (!result.candidates.isKnown) {
      this.memo.set(key, result);
      return result;
    }
    const piece = this.index.piece(pieceId);
    const support = supportId(ownerGroupId, piece.piece_id);
    const label: PathLabel = [PathFamilies.NODE, support, support];
    const neutralTrace = this.families.leafTrace(Families.ONE, label);
    const neutral = new PathFrontier(
      this.families,
      new Map([
        [
          shortfallsKey([]),
          {
            shortfalls: [],
            support: Families.ONE,
            trace: neutralTrace,
            drawing: { kind: "trace", trace: neutralTrace },
          },
        ],
      ]),
    );
    const labelled = pathEvaluation(
      result.candidates
        .join(neutral)
        .withDrawingNode(ownerGroupId, piece.piece_id),
      result.hasUnresolvedAlternative,
      result.blockers,
    );
    this.memo.set(key, labelled);
    return labelled;
  }

  /** Apply the shared support guard: exclusion first, then manual completion. */
  override nodeOverride(
    piece: SolverPiece,
    ownerGroupId: string,
  ): PathEvaluation | null {
    const support = supportId(ownerGroupId, piece.piece_id);
    const action = nodeAction(this.index, support);
    if (action === "excluded") {
      this.blockedExcludedNodeKeys?.add(support);
      this.recordProblem("no_solution", "excluded_node", piece, ownerGroupId);
      return pathEvaluation(PathFrontier.empty(this.families), false, []);
    }
    if (action === "completed") {
      const credits =
        piece.manual_credits_min === null
          ? null
          : parseCredits(piece.manual_credits_min);
      this.families.registerAttested(support, credits);
      const attestSupport = this.families.singleton([
        this.families.witnessVariable(PathFamilies.ATTESTED, support),
      ]);
      const trace = this.families.leafTrace(attestSupport);
      return pathEvaluation(
        new PathFrontier(
          this.families,
          new Map([
            [
              shortfallsKey([]),
              {
                shortfalls: [],
                support: attestSupport,
                trace,
                drawing: { kind: "trace", trace },
              },
            ],
          ]),
        ),
        false,
        [],
      );
    }
    return null;
  }

  /** Append one located problem per distinct provenance fact at the support's drawn box. */
  private recordProblem(
    state: "no_solution" | "unresolved" | "shortfall",
    reason: string,
    piece: SolverPiece,
    ownerGroupId: string,
    options: {
      referencedGroupId?: string | null;
      detail?: string | null;
      nodeId?: string;
      supportValue?: string;
    } = {},
  ): void {
    const problems = this.problems;
    if (problems === null) {
      return;
    }
    const support =
      options.supportValue ?? supportId(ownerGroupId, piece.piece_id);
    const drawn =
      options.nodeId ?? nodeIdForSupport(this.index.structure, support);
    const facts = factIdsForSupport(this.index.structure, support);
    for (const factId of facts.length > 0 ? facts : [null]) {
      problems.push({
        node_id: drawn,
        support_id: support,
        fact_id: factId,
        state,
        reason,
        referenced_group_id: options.referencedGroupId ?? null,
        detail: options.detail ?? null,
      });
    }
  }

  /** Fold an unmarked module boundary transparently over its inlined child. */
  moduleBlock(piece: SolverPiece, ownerGroupId: string): PathEvaluation {
    const child = this.evaluate(piece.children[0], ownerGroupId);
    return pathEvaluation(
      child.candidates.withDrawingSlot(0),
      child.hasUnresolvedAlternative,
      child.blockers,
    );
  }

  /** Evaluate one opaque obligation as distinct new source work charged once. */
  opaqueCredits(piece: SolverPiece, ownerGroupId: string): PathEvaluation {
    const support = supportId(ownerGroupId, piece.piece_id);
    if (piece.credits_min !== null && parseCredits(piece.credits_min) === 0) {
      return pathEvaluation(PathFrontier.neutral(this.families), false, []);
    }
    const workKey = requiredWorkKey(piece);
    const sourceSupport = this.families.singleton([
      this.families.witnessVariable(PathFamilies.OPAQUE, workKey),
      this.families.newVariable(PathFamilies.OPAQUE, workKey),
    ]);
    const trace = this.families.leafTrace(sourceSupport, [
      PathFamilies.OPAQUE,
      workKey,
      support,
    ]);
    return pathEvaluation(
      new PathFrontier(
        this.families,
        new Map([
          [
            shortfallsKey([]),
            {
              shortfalls: [],
              support: sourceSupport,
              trace,
              drawing: { kind: "trace", trace },
            },
          ],
        ]),
      ),
      false,
      [],
    );
  }

  /** Evaluate an expanded head and its closure, stopping at a basis-covered head. */
  expandedCourse(piece: SolverPiece, ownerGroupId: string): PathEvaluation {
    const headPiece = this.index.piece(piece.children[0]);
    const headGroupId = headPiece.course_group_id || ownerGroupId;
    const headOwner = headGroupId;
    const headSupport = supportId(headOwner, headPiece.piece_id);
    if (
      !isCourseActivityEligible(
        this.index,
        headGroupId,
        this.activityExceptionGroupIds,
        true,
      )
    ) {
      if (this.index.excludedGroupIds.has(headGroupId)) {
        this.blockedExcludedGroupIds?.add(headGroupId);
        this.recordProblem(
          "no_solution",
          "excluded_node",
          headPiece,
          headOwner,
          {
            referencedGroupId: headGroupId,
            nodeId: `course:${headGroupId}`,
            supportValue: headSupport,
          },
        );
      } else {
        this.recordProblem(
          "no_solution",
          "inactive_course",
          headPiece,
          headOwner,
          {
            referencedGroupId: headGroupId,
            nodeId: `course:${headGroupId}`,
            supportValue: headSupport,
          },
        );
      }
      return pathEvaluation(PathFrontier.empty(this.families), false, []);
    }
    const headLabel: PathLabel = [
      PathFamilies.COURSE,
      headGroupId,
      headSupport,
    ];
    const headVariables: PathVariable[] = [
      this.families.witnessVariable(PathFamilies.COURSE, headGroupId),
    ];
    if (!this.basis.has(headGroupId)) {
      headVariables.push(
        this.families.newVariable(PathFamilies.COURSE, headGroupId),
      );
    }
    const headSupportFamily = this.families.singleton(headVariables);
    const headTrace = this.families.leafTrace(headSupportFamily, headLabel);
    let headFrontier = new PathFrontier(
      this.families,
      new Map([
        [
          shortfallsKey([]),
          {
            shortfalls: [],
            support: headSupportFamily,
            trace: headTrace,
            drawing: { kind: "trace", trace: headTrace },
          },
        ],
      ]),
    );
    const nodeLabel: PathLabel = [PathFamilies.NODE, headSupport, headSupport];
    const nodeSupport = this.families.singleton([]);
    const nodeTrace = this.families.leafTrace(nodeSupport, nodeLabel);
    headFrontier = headFrontier
      .join(
        new PathFrontier(
          this.families,
          new Map([
            [
              shortfallsKey([]),
              {
                shortfalls: [],
                support: nodeSupport,
                trace: nodeTrace,
                drawing: { kind: "trace", trace: nodeTrace },
              },
            ],
          ]),
        ),
      )
      .withDrawingNode(headOwner, headPiece.piece_id)
      .withDrawingSlot(0);
    if (this.basis.has(headGroupId)) {
      return pathEvaluation(headFrontier, false, []);
    }
    const descendantEvaluation = this.evaluate(piece.children[1], headOwner);
    const combined = headFrontier.join(
      descendantEvaluation.candidates.projectWitnesses().withDrawingSlot(1),
    );
    return pathEvaluation(
      combined,
      descendantEvaluation.hasUnresolvedAlternative,
      descendantEvaluation.hasUnresolvedAlternative
        ? descendantEvaluation.blockers
        : [],
    );
  }

  /** Evaluate one course leaf into its witness or denial result. */
  course(piece: SolverPiece, ownerGroupId: string): PathEvaluation {
    const groupId = requiredCourseGroupId(piece);
    const support = supportId(ownerGroupId, piece.piece_id);
    if (
      !isCourseActivityEligible(
        this.index,
        groupId,
        this.activityExceptionGroupIds,
        true,
      )
    ) {
      if (this.index.excludedGroupIds.has(groupId)) {
        this.blockedExcludedGroupIds?.add(groupId);
        this.recordProblem(
          "no_solution",
          "excluded_node",
          piece,
          ownerGroupId,
          {
            referencedGroupId: groupId,
            nodeId: `course:${groupId}`,
          },
        );
        return pathEvaluation(PathFrontier.empty(this.families), false, []);
      }
      if (
        piece.module_rule &&
        this.index.structure.active_only &&
        this.allowModuleShortfall &&
        this.allCourseDiagnosticAllowsShortfall(piece, ownerGroupId)
      ) {
        const shortfall = countShortfall(
          "all_mandatory",
          nodeIdForSupport(this.index.structure, support),
          support,
          { requiredCount: 1, achievedCount: 0 },
        );
        this.recordProblem(
          "shortfall",
          "activity_shortfall",
          piece,
          ownerGroupId,
        );
        const trace = this.families.leafTrace(Families.ONE);
        return pathEvaluation(
          new PathFrontier(
            this.families,
            new Map([
              [
                shortfallsKey([shortfall]),
                {
                  shortfalls: [shortfall],
                  support: Families.ONE,
                  trace,
                  drawing: { kind: "trace", trace },
                },
              ],
            ]),
          ),
          false,
          [],
        );
      }
      this.recordProblem(
        "no_solution",
        "inactive_course",
        piece,
        ownerGroupId,
        {
          referencedGroupId: groupId,
          nodeId: `course:${groupId}`,
        },
      );
      return pathEvaluation(PathFrontier.empty(this.families), false, []);
    }
    if (piece.cycle_closing && !this.basis.has(groupId)) {
      this.recordProblem("unresolved", "course_cycle", piece, ownerGroupId, {
        referencedGroupId: groupId,
        nodeId: `course:${groupId}`,
      });
      const facts = factIdsForSupport(this.index.structure, support);
      return pathEvaluation(PathFrontier.empty(this.families), true, [
        {
          kind: "course_cycle",
          node_id: `course:${groupId}`,
          support_id: support,
          fact_id: facts.length > 0 ? facts[0] : null,
          reason: "course_cycle",
          referenced_group_id: null,
          detail: null,
          course_group_path: this.cyclePathBySupport.get(support) ?? [],
        },
      ]);
    }
    const variables: PathVariable[] = [
      this.families.witnessVariable(PathFamilies.COURSE, groupId),
    ];
    if (!this.basis.has(groupId)) {
      variables.push(this.families.newVariable(PathFamilies.COURSE, groupId));
    }
    const sourceSupport = this.families.singleton(variables);
    const trace = this.families.leafTrace(sourceSupport, [
      PathFamilies.COURSE,
      groupId,
      support,
    ]);
    return pathEvaluation(
      new PathFrontier(
        this.families,
        new Map([
          [
            shortfallsKey([]),
            {
              shortfalls: [],
              support: sourceSupport,
              trace,
              drawing: { kind: "trace", trace },
            },
          ],
        ]),
      ),
      false,
      [],
    );
  }

  /** Evaluate one unresolved requirement into one explicit blocker. */
  unresolved(piece: SolverPiece, ownerGroupId: string): PathEvaluation {
    if (piece.reason === null) {
      throw new Error(
        `unresolved prerequisite piece ${piece.piece_id} has no reason`,
      );
    }
    const reason = piece.reason;
    const detail = piece.detail;
    const referenced = piece.referenced_group_id;
    const support = supportId(ownerGroupId, piece.piece_id);
    this.recordProblem("unresolved", reason, piece, ownerGroupId, {
      referencedGroupId: referenced,
      detail,
    });
    const facts = factIdsForSupport(this.index.structure, support);
    return pathEvaluation(PathFrontier.empty(this.families), true, [
      {
        kind: "unresolved_requirement",
        node_id: nodeIdForSupport(this.index.structure, support),
        support_id: support,
        fact_id: facts.length > 0 ? facts[0] : null,
        reason,
        referenced_group_id: referenced,
        detail,
        course_group_path: [],
      },
    ]);
  }

  /** Evaluate an ordinary conjunction and optionally reduce an activity-only module rule. */
  conjunction(
    piece: SolverPiece,
    ownerGroupId: string,
    children: readonly PathEvaluation[],
  ): PathEvaluation {
    const hasUnresolved = conjunctionIsUnresolved(children);
    const blockers = hasUnresolved
      ? mergeBlockers(
          children.flatMap((child) =>
            child.hasUnresolvedAlternative ? child.blockers : [],
          ),
        )
      : [];
    const combined = combineFrontiers(
      this.families,
      children.map((child, index) => child.candidates.withDrawingSlot(index)),
    );
    if (
      !piece.module_rule ||
      !this.index.structure.active_only ||
      !this.allowModuleShortfall
    ) {
      return pathEvaluation(combined, hasUnresolved, blockers);
    }
    if (!hasUnresolved) {
      const reduced = this.reduceModuleConjunction(
        piece,
        ownerGroupId,
        children,
      );
      if (reduced !== null) {
        return reduced;
      }
    }
    return pathEvaluation(combined, hasUnresolved, blockers);
  }

  /** Union every known child candidate and every child's unresolved route and blockers. */
  alternatives(
    _piece: SolverPiece,
    _ownerGroupId: string,
    children: readonly PathEvaluation[],
  ): PathEvaluation {
    let combined = PathFrontier.empty(this.families);
    children.forEach((child, index) => {
      combined = combined.union(child.candidates.withDrawingSlot(index));
    });
    return pathEvaluation(
      combined,
      children.some((child) => child.hasUnresolvedAlternative),
      mergeBlockers(
        children.flatMap((child) =>
          child.hasUnresolvedAlternative ? child.blockers : [],
        ),
      ),
    );
  }

  /** Fold every allowed-size position selection and optionally reduce an activity-only rule. */
  cardinality(
    piece: SolverPiece,
    ownerGroupId: string,
    children: readonly PathEvaluation[],
  ): PathEvaluation {
    const childFrontiers = children.map((child, index) =>
      child.candidates.withoutEmptyModuleMarker().withDrawingSlot(index),
    );
    const upper = Math.min(
      piece.require_max ?? children.length,
      children.length,
    );
    let rows: PathFrontier[] = Array.from({ length: upper + 1 }, () =>
      PathFrontier.empty(this.families),
    );
    rows[0] = PathFrontier.neutral(this.families);
    for (const frontier of childFrontiers) {
      const nextRows = Array.from({ length: upper + 1 }, () =>
        PathFrontier.empty(this.families),
      );
      for (let count = 0; count <= upper; count += 1) {
        let selected = rows[count];
        if (count > 0) {
          selected = selected.union(rows[count - 1].join(frontier));
        }
        nextRows[count] = selected;
      }
      rows = nextRows;
    }
    let collected = PathFrontier.empty(this.families);
    for (let count = piece.require_min ?? 0; count <= upper; count += 1) {
      collected = collected.union(rows[count]);
    }
    const viable = children.filter(
      (child) => child.isKnown || child.hasUnresolvedAlternative,
    ).length;
    const unresolvedChildren = children.filter(
      (child) => child.hasUnresolvedAlternative,
    ).length;
    const hasUnresolved =
      unresolvedChildren > 0 &&
      Math.max(piece.require_min ?? 0, 1) <= Math.min(upper, viable);
    const blockers = hasUnresolved
      ? mergeBlockers(
          children.flatMap((child) =>
            child.hasUnresolvedAlternative ? child.blockers : [],
          ),
        )
      : [];
    if (!collected.isKnown && !hasUnresolved) {
      const reduced = this.reduceCardinality(
        piece,
        ownerGroupId,
        childFrontiers,
      );
      if (reduced !== null) {
        return reduced;
      }
      this.recordProblem(
        "no_solution",
        "too_few_positions",
        piece,
        ownerGroupId,
      );
    }
    return pathEvaluation(collected, hasUnresolved, blockers);
  }

  /** Keep known in-bound witnesses and carry unknown-measure support as a located unknown route. */
  bounded(
    piece: SolverPiece,
    ownerGroupId: string,
    child: PathEvaluation,
  ): PathEvaluation {
    let weight: (variable: PathVariable) => number;
    let lower: number;
    let upper: number | null;
    let isUnknown: (variable: PathVariable) => boolean;
    let unknownReason: string;
    if (piece.kind === "credits") {
      weight = (variable) => this.families.creditWeight(variable);
      lower = piece.credits_min === null ? 0 : parseCredits(piece.credits_min);
      upper =
        piece.credits_max === null ? null : parseCredits(piece.credits_max);
      isUnknown = (variable) => this.families.isUnknownCredit(variable);
      unknownReason = "unknown_credit_extent";
    } else {
      weight = (variable) => this.families.countWeight(variable);
      lower = piece.count_min ?? 0;
      upper = piece.count_max;
      isUnknown = (variable) => this.families.isUnknownCount(variable);
      unknownReason = "unknown_course_count";
    }
    const decorated = child.candidates.withDrawingSlot(0);
    if (lower === 0 && upper === null) {
      return pathEvaluation(
        decorated,
        child.hasUnresolvedAlternative,
        child.blockers,
      );
    }
    const [knownFrontier, hasUnknownMember] =
      decorated.partitionUnknown(isUnknown);
    const kept = knownFrontier.filter({ weight, lower, upper });
    if (hasUnknownMember) {
      this.recordProblem("unresolved", unknownReason, piece, ownerGroupId);
    }
    if (!kept.isKnown && !child.hasUnresolvedAlternative && !hasUnknownMember) {
      const reduced = this.reduceBounded(piece, ownerGroupId, knownFrontier);
      if (reduced !== null) {
        return reduced;
      }
      this.recordProblem(
        "no_solution",
        "unreachable_bound",
        piece,
        ownerGroupId,
      );
    }
    return pathEvaluation(
      kept,
      child.hasUnresolvedAlternative || hasUnknownMember,
      child.blockers,
    );
  }

  /** Return whether the same piece solves strictly once activity hides nothing. */
  private allCourseDiagnosticAllowsShortfall(
    piece: SolverPiece,
    ownerGroupId: string,
  ): boolean {
    const exceptions = new Set(
      this.index.structure.courses.map((course) => course.group_id),
    );
    const result = this.diagnostic({
      activityExceptionGroupIds: exceptions,
      allowModuleShortfall: false,
    }).evaluate(piece.piece_id, ownerGroupId);
    return result.isKnown && !result.hasUnresolvedAlternative;
  }

  /** Return whether an empty module-rule position may be filled by the neutral candidate. */
  private activityFillsModulePosition(
    piece: SolverPiece,
    ownerGroupId: string,
  ): boolean {
    if (!isModuleRulePosition(piece)) {
      return false;
    }
    if (!this.allCourseDiagnosticAllowsShortfall(piece, ownerGroupId)) {
      return false;
    }
    const result = this.diagnostic({
      activityExceptionGroupIds: this.basis,
      allowModuleShortfall: true,
    }).evaluate(piece.piece_id, ownerGroupId);
    for (const partition of result.candidates.partitions.values()) {
      if (
        partition.shortfalls.length > 0 &&
        partition.support !== Families.ZERO
      ) {
        return true;
      }
    }
    return false;
  }

  /** Return one candidate frontier per module-rule child position plus achievement flags. */
  private modulePositions(
    piece: SolverPiece,
    childEvaluations: readonly PathEvaluation[],
    options: { ownerGroupId: string },
  ): [PathFrontier[], boolean[]] {
    const groups: PathFrontier[] = [];
    const achievedFlags: boolean[] = [];
    for (let index = 0; index < childEvaluations.length; index += 1) {
      const evaluation = childEvaluations[index];
      const achieving = evaluation.candidates.withoutEmptyModuleMarker();
      if (achieving.isKnown) {
        groups.push(achieving.withDrawingSlot(index));
        achievedFlags.push(true);
        continue;
      }
      const childPiece = this.index.piece(piece.children[index]);
      if (this.activityFillsModulePosition(childPiece, options.ownerGroupId)) {
        groups.push(PathFrontier.neutral(this.families));
        achievedFlags.push(false);
        continue;
      }
      groups.push(PathFrontier.empty(this.families));
      achievedFlags.push(false);
    }
    return [groups, achievedFlags];
  }

  /** Reduce an all-mandatory module rule emptied only by activity, or return `null`. */
  private reduceModuleConjunction(
    piece: SolverPiece,
    ownerGroupId: string,
    childEvaluations: readonly PathEvaluation[],
  ): PathEvaluation | null {
    const [groups, achievedFlags] = this.modulePositions(
      piece,
      childEvaluations,
      { ownerGroupId },
    );
    const achievedCount = achievedFlags.filter((achieved) => achieved).length;
    if (
      groups.every((group) => group.isKnown) &&
      achievedCount === groups.length
    ) {
      return pathEvaluation(combineFrontiers(this.families, groups), false, []);
    }
    if (
      groups.every((group) => group.isKnown) &&
      achievedCount < groups.length &&
      this.allCourseDiagnosticAllowsShortfall(piece, ownerGroupId)
    ) {
      const reduced = combineFrontiers(this.families, groups);
      if (reduced.isKnown) {
        const support = supportId(ownerGroupId, piece.piece_id);
        this.recordProblem(
          "shortfall",
          "activity_shortfall",
          piece,
          ownerGroupId,
        );
        return pathEvaluation(
          reduced.attachShortfall(
            countShortfall(
              "all_mandatory",
              nodeIdForSupport(this.index.structure, support),
              support,
              {
                requiredCount: piece.children.length,
                achievedCount,
              },
            ),
          ),
          false,
          [],
        );
      }
    }
    return null;
  }

  /** Reduce a cardinality node emptied only by activity, or return `null`. */
  private reduceCardinality(
    piece: SolverPiece,
    ownerGroupId: string,
    childFrontiers: readonly PathFrontier[],
  ): PathEvaluation | null {
    const selectablePositions: number[] = [];
    childFrontiers.forEach((frontier, index) => {
      if (frontier.isKnown) {
        selectablePositions.push(index);
      }
    });
    const achievedCount = selectablePositions.length;
    const selectable = new Set(selectablePositions);
    const missingPositions = Array.from(
      { length: piece.children.length },
      (_unused, index) => index,
    ).filter((index) => !selectable.has(index));
    if (
      this.index.structure.active_only &&
      this.allowModuleShortfall &&
      missingPositions.every((index) =>
        this.activityFillsModulePosition(
          this.index.piece(piece.children[index]),
          ownerGroupId,
        ),
      ) &&
      this.allCourseDiagnosticAllowsShortfall(piece, ownerGroupId)
    ) {
      const reduced = combineFrontiers(
        this.families,
        selectablePositions.map((index) => childFrontiers[index]),
      );
      const support = supportId(ownerGroupId, piece.piece_id);
      this.recordProblem(
        "shortfall",
        "activity_shortfall",
        piece,
        ownerGroupId,
      );
      return pathEvaluation(
        reduced.attachShortfall(
          countShortfall(
            "cardinality",
            nodeIdForSupport(this.index.structure, support),
            support,
            {
              requiredCount: piece.require_min ?? 0,
              achievedCount,
            },
          ),
        ),
        false,
        [],
      );
    }
    return null;
  }

  /** Reduce a credit or count node missing only its lower bound, or return `null`. */
  private reduceBounded(
    piece: SolverPiece,
    ownerGroupId: string,
    childFrontier: PathFrontier,
  ): PathEvaluation | null {
    if (!(
      this.index.structure.active_only &&
      this.allowModuleShortfall &&
      this.allCourseDiagnosticAllowsShortfall(piece, ownerGroupId)
    )) {
      return null;
    }
    const support = supportId(ownerGroupId, piece.piece_id);
    const nodeId = nodeIdForSupport(this.index.structure, support);
    let weight: (variable: PathVariable) => number;
    let lower: number;
    if (piece.kind === "credits") {
      weight = (variable) => this.families.creditWeight(variable);
      lower = piece.credits_min === null ? 0 : parseCredits(piece.credits_min);
    } else {
      weight = (variable) => this.families.countWeight(variable);
      lower = piece.count_min ?? 0;
    }
    let best: number | null = null;
    for (const partition of childFrontier.partitions.values()) {
      const value = this.families.maxWeightStrictlyBelow(partition.support, {
        weight,
        budget: lower,
      });
      if (value !== null && (best === null || value > best)) {
        best = value;
      }
    }
    if (best === null) {
      return null;
    }
    const below = childFrontier.filter({ weight, lower: best, upper: best });
    const shortfall =
      piece.kind === "credits"
        ? creditShortfall(nodeId, support, {
            requiredCredits:
              piece.credits_min === null ? 0 : parseCredits(piece.credits_min),
            achievedCredits: best,
          })
        : countShortfall("course_count", nodeId, support, {
            requiredCount: piece.count_min ?? 0,
            achievedCount: best,
          });
    this.recordProblem("shortfall", "activity_shortfall", piece, ownerGroupId);
    return pathEvaluation(below.attachShortfall(shortfall), false, []);
  }
}
