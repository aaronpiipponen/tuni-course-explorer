/** Calculate the minimum-new-credit route over one solver structure. */
import type {
  PathProblem,
  PathShortfall,
  PrerequisitePath,
  SolverFact,
  SolverStructure,
} from "../api/types";
import { formatCredits, parseCredits } from "./credits";
import { compareKey, compareText, type KeyPart } from "./order";
import {
  candidateSelectionKey,
  candidateSortKey,
  type PathCandidate,
} from "./route-candidate";
import {
  cycleSupportPaths,
  PathEvaluator,
  pathEvaluation,
  requiredCourseGroupId,
  requiredWorkKey,
  type PathEvaluation,
} from "./route-evaluator";
import type { DrawingNode, DrawingTraceRef } from "./route-derivation";
import {
  PathFrontier,
  type KeyedPartition,
  type PathBlocker,
} from "./route-frontier";
import { GreedyPathEvaluator } from "./route-greedy";
import { projectRoute } from "./route-projection";
import {
  bestSupportVariables,
  PathFamilies,
  PathSizeLimitExceeded,
  supportKey,
  type BestSupport,
  type PathVariable,
} from "./route-families";
import { mergeShortfalls } from "./route-shortfall";
import {
  creditsByGroupId as structureCreditsByGroupId,
  indexStructure,
  opaqueCreditsByWorkKey,
  type StructureIndex,
} from "./structure";
import {
  evaluateSatisfaction,
  type SatisfactionEvaluation,
} from "./satisfaction";

/** One exact route result: the wire path plus its satisfaction, blockers and coverage. */
export type MinimumRoute = PrerequisitePath & {
  satisfaction: SatisfactionEvaluation;
  blockers: readonly PathBlocker[];
  inferred_coverage: SolverStructure["inferred_coverage"];
};

/** Return every drawn node bound to the supplied scoped supports. */
function nodeIdsForSupports(
  structure: SolverStructure,
  supports: Iterable<string>,
): string[] {
  const selected = new Set(supports);
  const nodes = new Set<string>();
  for (const binding of structure.bindings) {
    if (selected.has(binding.support_id)) {
      for (const nodeId of binding.node_ids) {
        nodes.add(nodeId);
      }
    }
  }
  return [...nodes].sort(compareText);
}

/** Return each course/opaque identity in first-visit native piece order. */
function pathGroupOrder(structure: SolverStructure): [string, string][] {
  if (structure.root_use_id === null) {
    return [];
  }
  const uses = new Map(structure.uses.map((use) => [use.use_id, use]));
  const pieces = new Map(
    structure.pieces.map((piece) => [piece.piece_id, piece]),
  );
  const orderList: [string, string][] = [];
  const seen = new Set<string>();
  const visited = new Set<string>();
  const stack: string[] = [structure.root_use_id];
  while (stack.length > 0) {
    const useId = stack.pop();
    if (useId === undefined) {
      continue;
    }
    const use = uses.get(useId);
    if (use === undefined) {
      continue;
    }
    const piece = pieces.get(use.piece_id);
    if (piece === undefined) {
      throw new Error(`unknown prerequisite piece ${use.piece_id}`);
    }
    let key: [string, string] | null = null;
    if (piece.kind === "course") {
      key = [PathFamilies.COURSE, requiredCourseGroupId(piece)];
    } else if (piece.kind === "opaque_credits") {
      key = [PathFamilies.OPAQUE, requiredWorkKey(piece)];
    }
    if (key !== null && !seen.has(`${key[0]}\u0000${key[1]}`)) {
      seen.add(`${key[0]}\u0000${key[1]}`);
      orderList.push(key);
    }
    if (visited.has(piece.piece_id)) {
      continue;
    }
    visited.add(piece.piece_id);
    stack.push(...[...use.children].reverse());
  }
  return orderList;
}

/** Return the exact zero-cost result for an already-satisfied requirement. */
function exactZero(
  satisfaction: SatisfactionEvaluation,
  coverage: SolverStructure["inferred_coverage"],
  blockedExcludedGroupIds: string[] = [],
): MinimumRoute {
  return {
    state: "exact",
    new_courses: [],
    total_new_credits: formatCredits(0),
    new_opaque_work: [],
    selected_nodes: [],
    lit_members: [],
    covered_courses: [],
    facts: [],
    shortfalls: [],
    blocked_excluded_group_ids: blockedExcludedGroupIds,
    blocked_excluded_node_keys: [],
    problems: [],
    satisfaction,
    blockers: [],
    inferred_coverage: coverage,
  };
}

/** Return a non-exact result carrying no fabricated courses or credit total. */
function nonExact(
  satisfaction: SatisfactionEvaluation,
  state: MinimumRoute["state"],
  blockers: readonly PathBlocker[],
  coverage: SolverStructure["inferred_coverage"],
  blockedExcludedGroupIds: string[] = [],
  options: {
    problems?: PathProblem[];
    blockedExcludedNodeKeys?: string[];
  } = {},
): MinimumRoute {
  return {
    state,
    new_courses: [],
    total_new_credits: null,
    new_opaque_work: [],
    selected_nodes: [],
    lit_members: [],
    covered_courses: [],
    facts: [],
    shortfalls: [],
    blocked_excluded_group_ids: blockedExcludedGroupIds,
    blocked_excluded_node_keys: options.blockedExcludedNodeKeys ?? [],
    problems: options.problems ?? [],
    satisfaction,
    blockers,
    inferred_coverage: coverage,
  };
}

/** Return every source fact referenced by the selected supports, once, sorted by ID. */
function referencedFacts(
  structure: SolverStructure,
  supports: Iterable<string>,
): SolverFact[] {
  const selected = new Set(supports);
  const useIds = new Set<string>();
  for (const binding of structure.bindings) {
    if (selected.has(binding.support_id)) {
      for (const useId of binding.use_ids) {
        useIds.add(useId);
      }
    }
  }
  const factIds = new Set<string>();
  for (const use of structure.uses) {
    if (useIds.has(use.use_id)) {
      factIds.add(use.fact_id);
    }
  }
  return structure.facts
    .filter((fact) => factIds.has(fact.fact_id))
    .sort((first, second) => compareText(first.fact_id, second.fact_id));
}

/** Add every fact referenced by the result's located records to its machine facts. */
function attachFacts(
  structure: SolverStructure,
  result: MinimumRoute,
): MinimumRoute {
  const supports = new Set<string>();
  for (const problem of result.problems) {
    if (problem.support_id !== null) {
      supports.add(problem.support_id);
    }
  }
  for (const blocker of result.blockers) {
    if (blocker.support_id !== null) {
      supports.add(blocker.support_id);
    }
  }
  for (const shortfall of result.shortfalls) {
    if (shortfall.support_id !== null) {
      supports.add(shortfall.support_id);
    }
  }
  const extra = referencedFacts(structure, supports);
  const facts = new Map<string, SolverFact>();
  for (const fact of [...result.facts, ...extra]) {
    facts.set(fact.fact_id, fact);
  }
  const identifiers = [...facts.keys()];
  if (
    identifiers.length === result.facts.length &&
    identifiers.every((factId, index) => factId === result.facts[index].fact_id)
  ) {
    return result;
  }
  return {
    ...result,
    facts: [...facts.values()].sort((first, second) =>
      compareText(first.fact_id, second.fact_id),
    ),
  };
}

/** Build sorted selected courses with every matching drawn node as evidence. */
function buildNewCourses(
  candidate: PathCandidate,
  summariesByGroupId: ReadonlyMap<string, SolverStructure["courses"][number]>,
  structure: SolverStructure,
): PrerequisitePath["new_courses"] {
  const courses: PrerequisitePath["new_courses"][number][] = [];
  for (const groupId of [...candidate.newGroupIds].sort(compareText)) {
    const supports = candidate.evidence
      .filter(
        (label) => label[0] === PathFamilies.COURSE && label[1] === groupId,
      )
      .map((label) => label[2]);
    let nodeIds = nodeIdsForSupports(structure, supports);
    if (nodeIds.length === 0) {
      nodeIds = [`course:${groupId}`];
    }
    const summary = summariesByGroupId.get(groupId);
    if (summary === undefined) {
      throw new Error(
        `course ${groupId} is missing from the calculation structure courses`,
      );
    }
    courses.push({ course: summary, node_ids: nodeIds });
  }
  return courses;
}

/** Build sorted distinct new opaque work with every matching drawn node as evidence. */
function buildOpaqueWork(
  candidate: PathCandidate,
  opaqueCredits: ReadonlyMap<string, number>,
  structure: SolverStructure,
): PrerequisitePath["new_opaque_work"] {
  const work: PrerequisitePath["new_opaque_work"][number][] = [];
  for (const workKey of [...candidate.newOpaqueWorkIds].sort(compareText)) {
    const supports = candidate.evidence
      .filter(
        (label) => label[0] === PathFamilies.OPAQUE && label[1] === workKey,
      )
      .map((label) => label[2]);
    work.push({
      work_key: workKey,
      credits_min: formatCredits(opaqueCredits.get(workKey) ?? 0),
      node_ids: nodeIdsForSupports(structure, supports),
    });
  }
  return work;
}

/** One winning candidate and the request-local drawing derivation it selected. */
type ChosenPath = { candidate: PathCandidate; drawing: DrawingNode };

/** Return one exact, approximate or shortfall result with distinct drawn evidence. */
function exactResult(
  structure: SolverStructure,
  satisfaction: SatisfactionEvaluation,
  selected: PathCandidate,
  drawing: DrawingNode,
  summariesByGroupId: ReadonlyMap<string, SolverStructure["courses"][number]>,
  opaqueCredits: ReadonlyMap<string, number>,
  coverage: SolverStructure["inferred_coverage"],
  blockedExcludedGroupIds: string[],
  options: {
    state: MinimumRoute["state"];
    shortfalls: readonly PathShortfall[];
    problems: PathProblem[];
    blockedExcludedNodeKeys?: string[];
  },
): MinimumRoute {
  const newCourses = buildNewCourses(selected, summariesByGroupId, structure);
  const newOpaqueWork = buildOpaqueWork(selected, opaqueCredits, structure);
  let total = 0;
  for (const entry of newCourses) {
    total += parseCredits(entry.course.credits_min);
  }
  for (const entry of newOpaqueWork) {
    total += parseCredits(entry.credits_min);
  }
  const selectedSupports = new Set<string>();
  for (const label of selected.evidence) {
    if (label[0] === PathFamilies.NODE) {
      selectedSupports.add(label[2]);
    }
  }
  for (const shortfall of options.shortfalls) {
    if (shortfall.support_id !== null) {
      selectedSupports.add(shortfall.support_id);
    }
  }
  const { selectedNodes, litMembers } = projectRoute(structure, drawing);
  const coveredGroupIds = new Set(selected.witnessGroupIds);
  for (const groupId of selected.newGroupIds) {
    coveredGroupIds.delete(groupId);
  }
  coveredGroupIds.delete(structure.root_group_id);
  const coveredCourses = [...coveredGroupIds]
    .sort(compareText)
    .flatMap((groupId) => {
      const summary = summariesByGroupId.get(groupId);
      return summary === undefined ? [] : [summary];
    });
  return {
    state: options.state,
    new_courses: newCourses,
    total_new_credits: formatCredits(total),
    new_opaque_work: newOpaqueWork,
    selected_nodes: selectedNodes,
    lit_members: litMembers,
    covered_courses: coveredCourses,
    facts: referencedFacts(structure, selectedSupports),
    shortfalls: options.shortfalls,
    blocked_excluded_group_ids: blockedExcludedGroupIds,
    blocked_excluded_node_keys: options.blockedExcludedNodeKeys ?? [],
    problems: options.problems,
    satisfaction,
    blockers: [],
    inferred_coverage: coverage,
  };
}

/** Return the exact winning candidate and its drawing across every partition. */
function frontierCandidate(
  frontier: PathFrontier,
  credits: ReadonlyMap<string, number>,
  opaqueCredits: ReadonlyMap<string, number>,
  inactiveGroupIds: ReadonlySet<string>,
): ChosenPath {
  const contenders: {
    partition: KeyedPartition;
    support: BestSupport;
  }[] = [];
  let bestSupportKey: KeyPart[] | null = null;
  for (const partition of frontier.partitions.values()) {
    const support = frontier.families.bestSupport(partition.support);
    if (support === null) {
      continue;
    }
    const value = supportKey(support);
    if (bestSupportKey === null || compareKey(value, bestSupportKey) < 0) {
      bestSupportKey = value;
      contenders.length = 0;
      contenders.push({ partition, support });
    } else if (compareKey(value, bestSupportKey) === 0) {
      contenders.push({ partition, support });
    }
  }
  if (contenders.length === 0) {
    throw new Error("known frontier has no candidate support");
  }
  let best: PathCandidate | null = null;
  let bestKey: KeyPart[] | null = null;
  let bestDrawing: DrawingTraceRef | null = null;
  let bestMember: ReadonlySet<PathVariable> | null = null;
  for (const contender of contenders) {
    const member: ReadonlySet<PathVariable> = new Set(
      bestSupportVariables(frontier.families, contender.support),
    );
    const evidence = frontier.families.reconstructEvidence(
      contender.partition.trace,
      member,
    );
    const candidate: PathCandidate = {
      witnessGroupIds: [...contender.support.witnessCourseIds],
      newGroupIds: [...contender.support.newCourseIds],
      newOpaqueWorkIds: [...contender.support.newOpaqueWorkIds],
      witnessNonCourseIds: [...contender.support.witnessNonCourseIds],
      evidence: [...evidence],
      shortfalls: [...contender.partition.shortfalls],
    };
    const key: KeyPart[] = [
      candidateSelectionKey(
        candidate,
        credits,
        opaqueCredits,
        inactiveGroupIds,
      ),
      candidateSortKey(candidate),
    ];
    if (bestKey === null || compareKey(key, bestKey) < 0) {
      bestKey = key;
      best = candidate;
      bestDrawing = contender.partition.drawing;
      bestMember = member;
    }
  }
  if (best === null || bestDrawing === null || bestMember === null) {
    throw new Error("known frontier has no candidate support");
  }
  return {
    candidate: best,
    drawing: frontier.families.reconstructDrawing(bestDrawing, bestMember),
  };
}

/** Return the minimum new-course credit total across a known frontier's partitions. */
function leastNewCredits(frontier: PathFrontier): number {
  let least: number | null = null;
  for (const partition of frontier.partitions.values()) {
    const credits = frontier.families.minimumNewCredits(partition.support);
    if (credits === null) {
      continue;
    }
    if (least === null || credits < least) {
      least = credits;
    }
  }
  if (least === null) {
    throw new Error("known frontier has no candidate support");
  }
  return least;
}

/** Return the strict and reduced frontiers, evaluation, blocks, problems and node keys. */
function evaluatePrimaryCandidates(
  structure: SolverStructure,
  options: {
    basisGroupIds: ReadonlySet<string>;
    credits: ReadonlyMap<string, number>;
    opaqueCredits: ReadonlyMap<string, number>;
    inactiveGroupIds: ReadonlySet<string>;
    index: StructureIndex;
    maxCompactNodes: number | null;
  },
): {
  strict: PathFrontier;
  reduced: PathFrontier;
  evaluation: PathEvaluation;
  blockedExcludedGroupIds: string[];
  problems: PathProblem[];
  blockedExcludedNodeKeys: string[];
} {
  const blockedExcluded = new Set<string>();
  const blockedNodeKeys = new Set<string>();
  const problems: PathProblem[] = [];
  const cyclePaths = cycleSupportPaths(structure);
  const families = new PathFamilies(
    options.credits,
    pathGroupOrder(structure),
    options.opaqueCredits,
    options.inactiveGroupIds,
    options.maxCompactNodes,
  );
  const evaluator = new PathEvaluator({
    index: options.index,
    basis: options.basisGroupIds,
    activityExceptionGroupIds: options.basisGroupIds,
    allowModuleShortfall: true,
    families,
    blockedExcludedGroupIds: blockedExcluded,
    blockedExcludedNodeKeys: blockedNodeKeys,
    problems,
    cyclePathBySupport: cyclePaths,
  });
  let evaluation: PathEvaluation;
  if (structure.root_use_id === null) {
    evaluation = pathEvaluation(PathFrontier.neutral(families), false, []);
  } else {
    const rootPiece = options.index.use(structure.root_use_id).piece_id;
    evaluation = evaluator.evaluate(rootPiece, structure.root_group_id);
  }
  const uniqueProblems = new Map<string, PathProblem>();
  for (const problem of problems) {
    uniqueProblems.set(
      JSON.stringify([
        problem.node_id,
        problem.support_id,
        problem.state,
        problem.reason,
        problem.referenced_group_id,
        problem.detail,
        problem.fact_id,
      ]),
      problem,
    );
  }
  const sortedProblems = [...uniqueProblems.values()].sort((first, second) =>
    compareKey(
      [
        first.node_id,
        first.support_id ?? "",
        first.state,
        first.reason,
        first.fact_id ?? "",
      ],
      [
        second.node_id,
        second.support_id ?? "",
        second.state,
        second.reason,
        second.fact_id ?? "",
      ],
    ),
  );
  return {
    strict: evaluation.candidates.restrict(
      (shortfalls) => shortfalls.length === 0,
    ),
    reduced: evaluation.candidates.restrict(
      (shortfalls) => shortfalls.length > 0,
    ),
    evaluation,
    blockedExcludedGroupIds: [...blockedExcluded].sort(compareText),
    problems: sortedProblems,
    blockedExcludedNodeKeys: nodeIdsForSupports(structure, blockedNodeKeys),
  };
}

/** Return the exact globally minimum new canonical courses and credits_min total. */
function solvePath(
  structure: SolverStructure,
  satisfaction: SatisfactionEvaluation,
  maxCompactNodes: number | null,
): MinimumRoute {
  const coverage = structure.inferred_coverage;
  const credits = structureCreditsByGroupId(structure);
  const summariesByGroupId = new Map(
    structure.courses.map((course) => [course.group_id, course]),
  );
  const opaqueCredits = opaqueCreditsByWorkKey(structure);
  const inactiveGroupIds = new Set(
    structure.courses
      .filter((course) => !course.is_active)
      .map((course) => course.group_id),
  );
  const primary = evaluatePrimaryCandidates(structure, {
    basisGroupIds: new Set(satisfaction.basis_group_ids),
    credits,
    opaqueCredits,
    inactiveGroupIds,
    index: indexStructure(structure),
    maxCompactNodes,
  });
  const { strict, reduced, evaluation } = primary;
  if (!strict.isKnown && reduced.isKnown) {
    if (
      satisfaction.requirements_state !== "unsatisfied" ||
      evaluation.hasUnresolvedAlternative
    ) {
      return nonExact(
        satisfaction,
        "unresolved",
        evaluation.blockers,
        coverage,
        primary.blockedExcludedGroupIds,
        {
          problems: primary.problems,
          blockedExcludedNodeKeys: primary.blockedExcludedNodeKeys,
        },
      );
    }
    const chosen = frontierCandidate(
      reduced,
      credits,
      opaqueCredits,
      inactiveGroupIds,
    );
    return exactResult(
      structure,
      satisfaction,
      chosen.candidate,
      chosen.drawing,
      summariesByGroupId,
      opaqueCredits,
      coverage,
      primary.blockedExcludedGroupIds,
      {
        state: "shortfall",
        shortfalls: mergeShortfalls(chosen.candidate.shortfalls),
        problems: primary.problems,
        blockedExcludedNodeKeys: primary.blockedExcludedNodeKeys,
      },
    );
  }
  if (!strict.isKnown) {
    return nonExact(
      satisfaction,
      evaluation.hasUnresolvedAlternative ? "unresolved" : "no_solution",
      evaluation.hasUnresolvedAlternative ? evaluation.blockers : [],
      coverage,
      primary.blockedExcludedGroupIds,
      {
        problems: primary.problems,
        blockedExcludedNodeKeys: primary.blockedExcludedNodeKeys,
      },
    );
  }
  if (evaluation.hasUnresolvedAlternative) {
    if (leastNewCredits(strict) > 0) {
      return nonExact(
        satisfaction,
        "unresolved",
        evaluation.blockers,
        coverage,
        primary.blockedExcludedGroupIds,
        {
          problems: primary.problems,
          blockedExcludedNodeKeys: primary.blockedExcludedNodeKeys,
        },
      );
    }
  }
  const chosen = frontierCandidate(
    strict,
    credits,
    opaqueCredits,
    inactiveGroupIds,
  );
  return exactResult(
    structure,
    satisfaction,
    chosen.candidate,
    chosen.drawing,
    summariesByGroupId,
    opaqueCredits,
    coverage,
    primary.blockedExcludedGroupIds,
    {
      state: "exact",
      shortfalls: [],
      problems: primary.problems,
      blockedExcludedNodeKeys: primary.blockedExcludedNodeKeys,
    },
  );
}

/** Run one scalar greedy derivation after the exact attempt exceeds its allocation budget. */
function solveGreedyPath(
  structure: SolverStructure,
  satisfaction: SatisfactionEvaluation,
): MinimumRoute {
  const coverage = structure.inferred_coverage;
  if (structure.root_use_id === null) {
    return exactZero(satisfaction, coverage);
  }
  const credits = structureCreditsByGroupId(structure);
  const summariesByGroupId = new Map(
    structure.courses.map((course) => [course.group_id, course]),
  );
  const opaqueCredits = opaqueCreditsByWorkKey(structure);
  const cyclePaths = cycleSupportPaths(structure);
  const evaluator = new GreedyPathEvaluator({
    index: indexStructure(structure),
    basis: new Set(satisfaction.basis_group_ids),
    creditsByGroupId: credits,
    opaqueCreditsByWorkKey: opaqueCredits,
    cyclePathBySupport: cyclePaths,
    inactiveGroupIds: new Set(
      structure.courses
        .filter((course) => !course.is_active)
        .map((course) => course.group_id),
    ),
  });
  const rootPiece =
    structure.uses.find((use) => use.use_id === structure.root_use_id)
      ?.piece_id ?? null;
  const evaluation =
    rootPiece === null
      ? {
          route: null,
          hasUnresolvedAlternative: false,
          blockers: [],
          isKnown: false,
        }
      : evaluator.evaluate(rootPiece, structure.root_group_id);
  const route = evaluation.route;
  if (route === null || !evaluator.valid(route)) {
    return approximationFailed(structure, satisfaction);
  }
  return exactResult(
    structure,
    satisfaction,
    route.candidate,
    route.drawing,
    summariesByGroupId,
    opaqueCredits,
    coverage,
    [...evaluator.blockedExcludedGroupIds].sort(compareText),
    {
      state: "approximate",
      shortfalls: [],
      problems: [],
      blockedExcludedNodeKeys: nodeIdsForSupports(
        structure,
        evaluator.blockedExcludedNodeKeys,
      ),
    },
  );
}

/** Return a content-free, size-triggered failure instead of claiming impossibility. */
function approximationFailed(
  structure: SolverStructure,
  satisfaction: SatisfactionEvaluation,
): MinimumRoute {
  const problem: PathProblem = {
    node_id: `course:${structure.root_group_id}`,
    support_id: null,
    fact_id: null,
    state: "unresolved",
    reason: "search_too_large",
    detail:
      "Exact search was too large; the approximation found no valid route.",
    referenced_group_id: null,
  };
  return {
    state: "approximation_failed",
    new_courses: [],
    total_new_credits: null,
    new_opaque_work: [],
    selected_nodes: [],
    lit_members: [],
    covered_courses: [],
    facts: [],
    shortfalls: [],
    blocked_excluded_group_ids: [],
    blocked_excluded_node_keys: [],
    problems: [problem],
    satisfaction,
    blockers: [],
    inferred_coverage: structure.inferred_coverage,
  };
}

/**
 * Return the exact, approximate or shortfall minimum-new-credit route for one solver structure.
 *
 * `maxCompactNodes` caps the exact family and provenance allocation. A missing cap runs the exact
 * search only. A non-null cap at or below zero throws, and an exhausted cap runs the greedy fold.
 */
export function calculateMinimumNewCredits(
  structure: SolverStructure,
  basisGroupIds: Iterable<string>,
  maxCompactNodes: number | null = null,
): MinimumRoute {
  if (maxCompactNodes !== null && maxCompactNodes <= 0) {
    throw new Error("maxCompactNodes must be positive");
  }
  const satisfaction = evaluateSatisfaction(structure, basisGroupIds);
  const coverage = structure.inferred_coverage;
  if (structure.excluded_group_ids.includes(structure.root_group_id)) {
    const rootGroupId = structure.root_group_id;
    const rootProblem: PathProblem = {
      node_id: `course:${rootGroupId}`,
      support_id: null,
      fact_id: null,
      state: "no_solution",
      reason: "excluded_node",
      detail: null,
      referenced_group_id: rootGroupId,
    };
    return attachFacts(
      structure,
      nonExact(satisfaction, "no_solution", [], coverage, [rootGroupId], {
        problems: [rootProblem],
        blockedExcludedNodeKeys: [`course:${rootGroupId}`],
      }),
    );
  }
  if (satisfaction.requirements_state === "satisfied") {
    return attachFacts(structure, exactZero(satisfaction, coverage));
  }
  try {
    return attachFacts(
      structure,
      solvePath(structure, satisfaction, maxCompactNodes),
    );
  } catch (error) {
    if (!(error instanceof PathSizeLimitExceeded) || maxCompactNodes === null) {
      throw error;
    }
  }
  return attachFacts(structure, solveGreedyPath(structure, satisfaction));
}
