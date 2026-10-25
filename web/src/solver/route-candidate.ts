/** Build one exact route candidate and the deterministic keys that select it. */
import type { PathShortfall } from "../api/types";
import { compareKey, compareText, type KeyPart } from "./order";
import type { PathLabel } from "./route-families";
import { shortfallSortKey } from "./route-shortfall";

/** One exact candidate: typed witness set, recursive new-work closure and typed evidence. */
export type PathCandidate = {
  witnessGroupIds: string[];
  newGroupIds: string[];
  evidence: PathLabel[];
  newOpaqueWorkIds: string[];
  witnessNonCourseIds: [string, string][];
  shortfalls: readonly PathShortfall[];
};

/** Return one relation's unique values in sorted text order. */
export function uniqueSortedText(values: Iterable<string>): string[] {
  return [...new Set(values)].sort(compareText);
}

/** Return one relation's unique typed pairs in sorted key order. */
export function uniqueSortedPairs(
  values: Iterable<readonly [string, string]>,
): [string, string][] {
  const unique = new Map<string, [string, string]>();
  for (const value of values) {
    unique.set(JSON.stringify(value), [value[0], value[1]]);
  }
  return [...unique.values()].sort((first, second) =>
    compareKey(first, second),
  );
}

/** Return one evidence relation's unique labels in sorted key order. */
export function uniqueSortedEvidence(labels: Iterable<PathLabel>): PathLabel[] {
  const unique = new Map<string, PathLabel>();
  for (const label of labels) {
    unique.set(`${label[0]}\u0000${label[1]}\u0000${label[2]}`, label);
  }
  return [...unique.values()].sort((first, second) =>
    compareKey(first, second),
  );
}

/** Return every evidence support of one candidate, sorted. */
export function evidenceSupports(candidate: PathCandidate): string[] {
  return uniqueSortedText(candidate.evidence.map((label) => label[2]));
}

/**
 * Return one candidate's canonical credits_min total. A missing course throws.
 */
export function witnessCredits(
  groupIds: Iterable<string>,
  credits: ReadonlyMap<string, number>,
): number {
  let total = 0;
  for (const groupId of groupIds) {
    const value = credits.get(groupId);
    if (value === undefined) {
      throw new Error(
        `course ${groupId} is missing from the calculation structure courses`,
      );
    }
    total += value;
  }
  return total;
}

/**
 * Return the exact candidate selection key: new credits, inactive new courses, then typed ties.
 *
 * `rankingCost` replaces the computed new-credit total when the caller already carries one.
 */
export function candidateSelectionKey(
  candidate: PathCandidate,
  credits: ReadonlyMap<string, number>,
  opaqueCredits: ReadonlyMap<string, number>,
  inactiveGroupIds: ReadonlySet<string>,
  rankingCost?: number,
): KeyPart[] {
  let total = rankingCost;
  if (total === undefined) {
    total = witnessCredits(candidate.newGroupIds, credits);
    for (const workKey of candidate.newOpaqueWorkIds) {
      total += opaqueCredits.get(workKey) ?? 0;
    }
  }
  return [
    total,
    candidate.newGroupIds.filter((groupId) => inactiveGroupIds.has(groupId))
      .length,
    candidate.newOpaqueWorkIds,
    candidate.newGroupIds,
    candidate.witnessGroupIds,
    candidate.witnessNonCourseIds,
    evidenceSupports(candidate),
  ];
}

/** Return the deterministic candidate ordering key. */
export function candidateSortKey(candidate: PathCandidate): KeyPart[] {
  return [
    candidate.witnessGroupIds,
    candidate.newGroupIds,
    candidate.newOpaqueWorkIds,
    candidate.witnessNonCourseIds,
    evidenceSupports(candidate),
    candidate.shortfalls.map(shortfallSortKey),
  ];
}

/** Return the unique sorted union of every candidate field, with no shortfalls. */
export function unionCandidates(
  routes: readonly PathCandidate[],
): PathCandidate {
  return {
    witnessGroupIds: uniqueSortedText(
      routes.flatMap((route) => route.witnessGroupIds),
    ),
    newGroupIds: uniqueSortedText(routes.flatMap((route) => route.newGroupIds)),
    evidence: uniqueSortedEvidence(routes.flatMap((route) => route.evidence)),
    newOpaqueWorkIds: uniqueSortedText(
      routes.flatMap((route) => route.newOpaqueWorkIds),
    ),
    witnessNonCourseIds: uniqueSortedPairs(
      routes.flatMap((route) => route.witnessNonCourseIds),
    ),
    shortfalls: [],
  };
}
