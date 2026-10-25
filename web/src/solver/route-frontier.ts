/** One keyed path frontier of support identities, shortfall partitions and blockers. */
import type { PathShortfall } from "../api/types";
import { Families } from "./families";
import { compareKey, type KeyPart } from "./order";
import type { DrawingTraceRef } from "./route-derivation";
import type { PathFamilies, PathVariable } from "./route-families";
import {
  isEmptyModuleMarker,
  mergeShortfalls,
  shortfallsKey,
} from "./route-shortfall";

/** One partition's exact support identities, operation provenance trace and drawing annotation. */
export type PathPartition = {
  support: number;
  trace: number;
  drawing: DrawingTraceRef;
};

/** One shortfall-keyed partition: its exact support identities, trace and deficits. */
export type KeyedPartition = PathPartition & {
  shortfalls: readonly PathShortfall[];
};

/** One located reason an exact route is unavailable. */
export type PathBlocker = {
  kind: "unresolved_requirement" | "course_cycle";
  node_id: string;
  support_id: string | null;
  fact_id: string | null;
  reason: string | null;
  referenced_group_id: string | null;
  detail: string | null;
  course_group_path: readonly string[];
};

/**
 * One transient path frontier.
 *
 * Partitions are keyed by their sorted shortfall list. The neutral frontier holds one partition
 * with no shortfall, and the empty frontier holds none.
 */
export class PathFrontier {
  readonly families: PathFamilies;
  readonly partitions: ReadonlyMap<string, KeyedPartition>;

  constructor(
    families: PathFamilies,
    partitions: ReadonlyMap<string, KeyedPartition>,
  ) {
    this.families = families;
    this.partitions = partitions;
  }

  /** Return the single empty-shortfall partition holding the neutral leaf identity. */
  static neutral(families: PathFamilies): PathFrontier {
    const trace = families.leafTrace(Families.ONE);
    return new PathFrontier(
      families,
      new Map([
        [
          shortfallsKey([]),
          {
            shortfalls: [],
            support: Families.ONE,
            trace,
            drawing: { kind: "trace", trace },
          },
        ],
      ]),
    );
  }

  /** Return the frontier with no candidate partition. */
  static empty(families: PathFamilies): PathFrontier {
    return new PathFrontier(families, new Map());
  }

  /** Return whether at least one partition holds a nonempty support family. */
  get isKnown(): boolean {
    for (const partition of this.partitions.values()) {
      if (partition.support !== Families.ZERO) {
        return true;
      }
    }
    return false;
  }

  /** Return the per-partition union of two frontiers, merging provenance on shared keys. */
  union(other: PathFrontier): PathFrontier {
    const merged = new Map<string, KeyedPartition>(this.partitions);
    for (const [key, right] of other.partitions) {
      const left = merged.get(key);
      if (left === undefined) {
        merged.set(key, right);
        continue;
      }
      const unioned = unionPartitions(this.families, left, right);
      if (unioned === null) {
        merged.delete(key);
      } else {
        merged.set(key, { shortfalls: left.shortfalls, ...unioned });
      }
    }
    return new PathFrontier(this.families, merged);
  }

  /** Return the shortfall-merged union-product of two frontiers with one join trace each. */
  join(other: PathFrontier): PathFrontier {
    const merged = new Map<string, KeyedPartition>();
    for (const left of this.partitions.values()) {
      for (const right of other.partitions.values()) {
        const shortfalls = mergeShortfalls([
          ...left.shortfalls,
          ...right.shortfalls,
        ]);
        const support = this.families.join(left.support, right.support);
        if (support === Families.ZERO) {
          continue;
        }
        const key = shortfallsKey(shortfalls);
        const trace = this.families.joinTrace(
          support,
          left.trace,
          right.trace,
          [left.drawing, right.drawing],
        );
        const part: KeyedPartition = {
          shortfalls,
          support,
          trace,
          drawing: { kind: "trace", trace },
        };
        const existing = merged.get(key);
        if (existing === undefined) {
          merged.set(key, part);
        } else {
          const unioned = unionPartitions(this.families, existing, part);
          if (unioned !== null) {
            merged.set(key, { shortfalls, ...unioned });
          }
        }
      }
    }
    return new PathFrontier(this.families, merged);
  }

  /** Return the frontier keeping identities inside the inclusive bounds. */
  filter(options: {
    weight: (variable: PathVariable) => number;
    lower: number;
    upper: number | null;
  }): PathFrontier {
    const kept = new Map<string, KeyedPartition>();
    for (const [key, partition] of this.partitions) {
      const support = this.families.filter(partition.support, options);
      if (support === Families.ZERO) {
        continue;
      }
      const trace = this.families.identityTrace(
        support,
        partition.trace,
        partition.drawing,
      );
      kept.set(key, {
        shortfalls: partition.shortfalls,
        support,
        trace,
        drawing: { kind: "trace", trace },
      });
    }
    return new PathFrontier(this.families, kept);
  }

  /**
   * Return the frontier without unknown-measure members, and whether any remained.
   *
   * Every known-measure member is kept with an identity step, and any member carrying an
   * unknown-measure token is reported separately.
   */
  partitionUnknown(
    isUnknown: (variable: PathVariable) => boolean,
  ): [PathFrontier, boolean] {
    const kept = new Map<string, KeyedPartition>();
    let hasUnknown = false;
    for (const [key, partition] of this.partitions) {
      const [known, partitionHasUnknown] = this.families.splitByPredicate(
        partition.support,
        isUnknown,
      );
      hasUnknown = hasUnknown || partitionHasUnknown !== Families.ZERO;
      if (known === Families.ZERO) {
        continue;
      }
      const trace = this.families.identityTrace(
        known,
        partition.trace,
        partition.drawing,
      );
      kept.set(key, {
        shortfalls: partition.shortfalls,
        support: known,
        trace,
        drawing: { kind: "trace", trace },
      });
    }
    return [new PathFrontier(this.families, kept), hasUnknown];
  }

  /** Return the frontier with every witness variable existentially removed. */
  projectWitnesses(): PathFrontier {
    const projected = new Map<string, KeyedPartition>();
    for (const [key, partition] of this.partitions) {
      const support = this.families.project(partition.support, (variable) =>
        this.families.isWitness(variable),
      );
      if (support === Families.ZERO) {
        continue;
      }
      const trace = this.families.projectTrace(
        support,
        partition.trace,
        partition.drawing,
      );
      projected.set(key, {
        shortfalls: partition.shortfalls,
        support,
        trace,
        drawing: { kind: "trace", trace },
      });
    }
    return new PathFrontier(this.families, projected);
  }

  /** Return the frontier without each activity-empty module marker identity. */
  withoutEmptyModuleMarker(): PathFrontier {
    const kept = new Map<string, KeyedPartition>();
    for (const [key, partition] of this.partitions) {
      if (
        partition.shortfalls.length !== 1 ||
        !isEmptyModuleMarker(partition.shortfalls[0])
      ) {
        kept.set(key, partition);
        continue;
      }
      const support = this.families.removeEmpty(partition.support);
      if (support === Families.ZERO) {
        continue;
      }
      const trace = this.families.identityTrace(
        support,
        partition.trace,
        partition.drawing,
      );
      kept.set(key, {
        shortfalls: partition.shortfalls,
        support,
        trace,
        drawing: { kind: "trace", trace },
      });
    }
    return new PathFrontier(this.families, kept);
  }

  /** Return the frontier with one deficit added to every partition, preserving provenance. */
  attachShortfall(shortfall: PathShortfall): PathFrontier {
    const attached = new Map<string, KeyedPartition>();
    for (const partition of this.partitions.values()) {
      const shortfalls = mergeShortfalls([...partition.shortfalls, shortfall]);
      const key = shortfallsKey(shortfalls);
      const existing = attached.get(key);
      if (existing === undefined) {
        attached.set(key, { ...partition, shortfalls });
      } else {
        const unioned = unionPartitions(this.families, existing, partition);
        if (unioned !== null) {
          attached.set(key, { shortfalls, ...unioned });
        }
      }
    }
    return new PathFrontier(this.families, attached);
  }

  /** Return the sub-frontier whose partition keys satisfy `keep`, preserving provenance. */
  restrict(
    keep: (shortfalls: readonly PathShortfall[]) => boolean,
  ): PathFrontier {
    const kept = new Map<string, KeyedPartition>();
    for (const [key, partition] of this.partitions) {
      if (keep(partition.shortfalls)) {
        kept.set(key, partition);
      }
    }
    return new PathFrontier(this.families, kept);
  }

  /** Return the frontier with every partition placed in one native child slot. */
  withDrawingSlot(slot: number): PathFrontier {
    const decorated = new Map<string, KeyedPartition>();
    for (const [key, partition] of this.partitions) {
      decorated.set(key, {
        ...partition,
        drawing: {
          kind: "slot",
          slot,
          input: partition.drawing,
        },
      });
    }
    return new PathFrontier(this.families, decorated);
  }

  /** Return the frontier with every partition wrapped in one native node frame. */
  withDrawingNode(ownerGroupId: string, pieceId: string): PathFrontier {
    const decorated = new Map<string, KeyedPartition>();
    for (const [key, partition] of this.partitions) {
      decorated.set(key, {
        ...partition,
        drawing: {
          kind: "node",
          ownerGroupId,
          pieceId,
          input: partition.drawing,
        },
      });
    }
    return new PathFrontier(this.families, decorated);
  }
}

/**
 * Return the union of two partitions, or `null` when the support is empty.
 *
 * Both source traces are kept even when the supports are equal.
 */
export function unionPartitions(
  families: PathFamilies,
  left: PathPartition,
  right: PathPartition,
): PathPartition | null {
  const support = families.union(left.support, right.support);
  if (support === Families.ZERO) {
    return null;
  }
  const trace = families.unionTrace(support, left.trace, right.trace, [
    left.drawing,
    right.drawing,
  ]);
  return { support, trace, drawing: { kind: "trace", trace } };
}

/** Return the join of every frontier, starting from the neutral frontier. */
export function combineFrontiers(
  families: PathFamilies,
  groups: Iterable<PathFrontier>,
): PathFrontier {
  let combined = PathFrontier.neutral(families);
  for (const group of groups) {
    combined = combined.join(group);
  }
  return combined;
}

/** Return the deterministic identity key of one blocker. */
export function blockerSortKey(blocker: PathBlocker): KeyPart[] {
  return [
    blocker.kind,
    blocker.node_id,
    blocker.support_id ?? "",
    blocker.fact_id ?? "",
    blocker.course_group_path,
    blocker.reason ?? "",
    blocker.referenced_group_id ?? "",
    blocker.detail ?? "",
  ];
}

/** Return sorted unique blockers keyed by their deterministic identity. */
export function mergeBlockers(blockers: Iterable<PathBlocker>): PathBlocker[] {
  const byKey = new Map<string, { key: KeyPart[]; blocker: PathBlocker }>();
  for (const blocker of blockers) {
    const key = blockerSortKey(blocker);
    const mapKey = JSON.stringify(key);
    if (!byKey.has(mapKey)) {
      byKey.set(mapKey, { key, blocker });
    }
  }
  return [...byKey.values()]
    .sort((first, second) => compareKey(first.key, second.key))
    .map((entry) => entry.blocker);
}
