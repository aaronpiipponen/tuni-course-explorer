/** Index one solver structure for the shared piece fold and the graph box states. */
import type {
  CourseSummary,
  PrerequisitesRequest,
  SolverPiece,
  SolverStructure,
  SolverSupportBinding,
  SolverUse,
} from "../api/types";
import { parseCredits } from "./credits";

/** One request-local lookup over a solver structure and its saved marks. */
export type StructureIndex = {
  structure: SolverStructure;
  /** Return one interned piece. Throws when the structure holds no such piece. */
  piece(pieceId: string): SolverPiece;
  /** Return one source use. Throws when the structure holds no such use. */
  use(useId: string): SolverUse;
  /** Return one canonical course summary, or `undefined` when the structure lacks it. */
  course(groupId: string): CourseSummary | undefined;
  /** Return the first binding for one scoped support. */
  binding(supportId: string): SolverSupportBinding | undefined;
  excludedGroupIds: ReadonlySet<string>;
  completedNodeKeys: ReadonlySet<string>;
  excludedNodeKeys: ReadonlySet<string>;
};

/** Return one scoped calculation support identity. */
export function supportId(ownerGroupId: string, pieceId: string): string {
  return `s:${ownerGroupId}:${pieceId}`;
}

/**
 * Return a shallow copy of one solver structure with the request's live calculation inputs.
 *
 * Only `excluded_group_ids`, `completed_node_keys` and `excluded_node_keys` differ, so every
 * native table is shared by reference. The basis is the selected or completed course codes.
 */
export function withLiveInputs(
  structure: SolverStructure,
  request: PrerequisitesRequest,
): { structure: SolverStructure; basis_group_ids: readonly string[] } {
  return {
    structure: {
      ...structure,
      excluded_group_ids: request.excluded_codes,
      completed_node_keys: request.completed_node_keys,
      excluded_node_keys: request.excluded_node_keys,
    },
    basis_group_ids:
      request.basis === "selected"
        ? request.selected_codes
        : request.completed_codes,
  };
}

/** Return each canonical course group ID's minimum credits in structure order. */
export function creditsByGroupId(
  structure: SolverStructure,
): Map<string, number> {
  const credits = new Map<string, number>();
  for (const course of structure.courses) {
    credits.set(course.group_id, parseCredits(course.credits_min));
  }
  return credits;
}

/**
 * Return each opaque work key's source minimum credits. The first piece for a key wins.
 */
export function opaqueCreditsByWorkKey(
  structure: SolverStructure,
): Map<string, number> {
  const credits = new Map<string, number>();
  for (const piece of structure.pieces) {
    if (piece.kind === "opaque_credits" && piece.work_key !== null) {
      if (!credits.has(piece.work_key)) {
        credits.set(
          piece.work_key,
          piece.credits_min === null ? 0 : parseCredits(piece.credits_min),
        );
      }
    }
  }
  return credits;
}

/** Build the request-local index of one solver structure. */
export function indexStructure(structure: SolverStructure): StructureIndex {
  const pieces = new Map<string, SolverPiece>();
  for (const piece of structure.pieces) {
    pieces.set(piece.piece_id, piece);
  }
  const uses = new Map<string, SolverUse>();
  for (const use of structure.uses) {
    uses.set(use.use_id, use);
  }
  const courses = new Map<string, CourseSummary>();
  for (const course of structure.courses) {
    courses.set(course.group_id, course);
  }
  const bindings = new Map<string, SolverSupportBinding>();
  for (const binding of structure.bindings) {
    if (!bindings.has(binding.support_id)) {
      bindings.set(binding.support_id, binding);
    }
  }
  return {
    structure,
    piece(pieceId: string): SolverPiece {
      const piece = pieces.get(pieceId);
      if (piece === undefined) {
        throw new Error(`unknown prerequisite piece ${pieceId}`);
      }
      return piece;
    },
    use(useId: string): SolverUse {
      const use = uses.get(useId);
      if (use === undefined) {
        throw new Error(`unknown prerequisite use ${useId}`);
      }
      return use;
    },
    course(groupId: string): CourseSummary | undefined {
      return courses.get(groupId);
    },
    binding(support: string): SolverSupportBinding | undefined {
      return bindings.get(support);
    },
    excludedGroupIds: new Set(structure.excluded_group_ids),
    completedNodeKeys: new Set(structure.completed_node_keys),
    excludedNodeKeys: new Set(structure.excluded_node_keys),
  };
}

/**
 * Return the saved graph-box action for one scoped support.
 *
 * Exclusion wins over completion. A support with no binding has no action.
 */
export function nodeAction(
  index: StructureIndex,
  support: string,
): "excluded" | "completed" | null {
  const binding = index.binding(support);
  if (binding === undefined) {
    return null;
  }
  if (
    binding.mark_node_ids.some((nodeId) => index.excludedNodeKeys.has(nodeId))
  ) {
    return "excluded";
  }
  if (
    binding.mark_node_ids.some((nodeId) => index.completedNodeKeys.has(nodeId))
  ) {
    return "completed";
  }
  return null;
}

/**
 * Return whether one canonical course may take part in the calculation.
 *
 * A course missing from the structure's summaries throws. `forCalculation` also removes an
 * excluded course. With the structure's activity scope on, an inactive course stays eligible
 * only when it is one of the caller's exceptions.
 */
export function isCourseActivityEligible(
  index: StructureIndex,
  groupId: string,
  exceptionGroupIds: ReadonlySet<string>,
  forCalculation: boolean,
): boolean {
  const summary = index.course(groupId);
  if (summary === undefined) {
    throw new Error(
      `course ${groupId} is missing from the calculation structure courses`,
    );
  }
  if (forCalculation && index.excludedGroupIds.has(groupId)) {
    return false;
  }
  return (
    !index.structure.active_only ||
    summary.is_active ||
    exceptionGroupIds.has(groupId)
  );
}
