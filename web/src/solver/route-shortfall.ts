/** Build and order the Active-only module shortfalls a route result reports. */
import type { PathShortfall } from "../api/types";
import { formatCredits } from "./credits";
import { compareKey, type KeyPart } from "./order";

/** One count-family shortfall kind. */
export type ShortfallCountKind =
  "all_mandatory" | "cardinality" | "course_count";

/** Return one shortfall's deterministic identity and order key. */
export function shortfallSortKey(shortfall: PathShortfall): KeyPart[] {
  return [
    shortfall.node_id,
    shortfall.support_id ?? "",
    shortfall.kind,
    shortfall.required_count ?? -1,
    shortfall.achieved_count ?? -1,
    shortfall.count_deficit ?? -1,
    shortfall.required_credits ?? "",
    shortfall.achieved_credits ?? "",
    shortfall.credit_deficit ?? "",
  ];
}

/** Return the partition key of one shortfall list. */
export function shortfallsKey(shortfalls: readonly PathShortfall[]): string {
  return JSON.stringify(shortfalls.map(shortfallSortKey));
}

/** Return one shortfall's complete value identity, used to reject conflicting merges. */
function shortfallValueKey(shortfall: PathShortfall): string {
  return JSON.stringify([
    shortfall.kind,
    shortfall.node_id,
    shortfall.support_id,
    shortfall.required_count,
    shortfall.achieved_count,
    shortfall.count_deficit,
    shortfall.required_credits,
    shortfall.achieved_credits,
    shortfall.credit_deficit,
  ]);
}

/** Return sorted unique shortfalls, rejecting conflicting values for one identity. */
export function mergeShortfalls(
  shortfalls: Iterable<PathShortfall>,
): PathShortfall[] {
  const byKey = new Map<string, PathShortfall>();
  for (const shortfall of shortfalls) {
    const identity = JSON.stringify([
      shortfall.node_id,
      shortfall.support_id ?? "",
      shortfall.kind,
    ]);
    const existing = byKey.get(identity);
    if (existing === undefined) {
      byKey.set(identity, shortfall);
    } else if (shortfallValueKey(existing) !== shortfallValueKey(shortfall)) {
      throw new Error(
        `conflicting module shortfalls for one support and kind: ${shortfall.node_id} ${
          shortfall.support_id ?? "None"
        } ${shortfall.kind}`,
      );
    }
  }
  return [...byKey.values()].sort((first, second) =>
    compareKey(shortfallSortKey(first), shortfallSortKey(second)),
  );
}

/** Build one count-family module deficit located at its drawn box and support. */
export function countShortfall(
  kind: ShortfallCountKind,
  nodeId: string,
  support: string,
  options: { requiredCount: number; achievedCount: number },
): PathShortfall {
  return {
    kind,
    node_id: nodeId,
    support_id: support,
    required_count: options.requiredCount,
    achieved_count: options.achievedCount,
    count_deficit: options.requiredCount - options.achievedCount,
    required_credits: null,
    achieved_credits: null,
    credit_deficit: null,
  };
}

/** Build one credit-family module deficit located at its drawn box and support. */
export function creditShortfall(
  nodeId: string,
  support: string,
  options: { requiredCredits: number; achievedCredits: number },
): PathShortfall {
  return {
    kind: "credits",
    node_id: nodeId,
    support_id: support,
    required_count: null,
    achieved_count: null,
    count_deficit: null,
    required_credits: formatCredits(options.requiredCredits),
    achieved_credits: formatCredits(options.achievedCredits),
    credit_deficit: formatCredits(
      options.requiredCredits - options.achievedCredits,
    ),
  };
}

/** Return whether one deficit is the bare module course-unit marker `1 -> 0`. */
export function isEmptyModuleMarker(shortfall: PathShortfall): boolean {
  return (
    shortfall.kind === "all_mandatory" &&
    shortfall.required_count === 1 &&
    shortfall.achieved_count === 0
  );
}
