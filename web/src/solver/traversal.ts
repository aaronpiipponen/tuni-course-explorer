/** One shared bottom-up fold over the native prerequisite piece structure. */
import type { SolverPiece } from "../api/types";
import type { StructureIndex } from "./structure";

/** One evaluated child: whether it is known, and whether an unknown route may exist. */
export interface Alternatives {
  readonly isKnown: boolean;
  readonly hasUnresolvedAlternative: boolean;
}

/**
 * Return whether one conjunction has a viable unresolved alternative.
 *
 * An unresolved alternative exists only when every child is known or unresolved and at least one
 * child is unresolved.
 */
export function conjunctionIsUnresolved(
  evaluations: readonly Alternatives[],
): boolean {
  return (
    evaluations.every(
      (evaluation) => evaluation.isKnown || evaluation.hasUnresolvedAlternative,
    ) && evaluations.some((evaluation) => evaluation.hasUnresolvedAlternative)
  );
}

/** Structural dispatch shared by the native evaluators. */
export abstract class PieceEvaluator<T> {
  constructor(readonly index: StructureIndex) {}

  /** Evaluate one calculation piece under its current owner course. */
  evaluate(pieceId: string, ownerGroupId: string): T {
    const piece = this.index.piece(pieceId);
    const override = this.nodeOverride(piece, ownerGroupId);
    if (override !== null) {
      return override;
    }
    if (piece.kind === "expanded_course") {
      return this.expandedCourse(piece, ownerGroupId);
    }
    if (piece.kind === "course") {
      return this.course(piece, ownerGroupId);
    }
    if (piece.kind === "module_block") {
      return this.moduleBlock(piece, ownerGroupId);
    }
    if (piece.kind === "opaque_credits") {
      return this.opaqueCredits(piece, ownerGroupId);
    }
    if (piece.kind === "unresolved") {
      return this.unresolved(piece, ownerGroupId);
    }
    const children = piece.children.map((child) =>
      this.evaluate(child, ownerGroupId),
    );
    if (piece.kind === "and") {
      return this.conjunction(piece, ownerGroupId, children);
    }
    if (piece.kind === "or" || piece.kind === "course_alternatives") {
      return this.alternatives(piece, ownerGroupId, children);
    }
    if (piece.kind === "cardinality") {
      return this.cardinality(piece, ownerGroupId, children);
    }
    if (piece.kind === "credits" || piece.kind === "course_count") {
      return this.bounded(piece, ownerGroupId, children[0]);
    }
    throw new Error(`unsupported prerequisite piece kind ${piece.kind}`);
  }

  /** Return an optional state-aware override for one piece, or `null`. */
  nodeOverride(_piece: SolverPiece, _ownerGroupId: string): T | null {
    return null;
  }

  /** Fold one expanded course over its head course and its closure. */
  abstract expandedCourse(piece: SolverPiece, ownerGroupId: string): T;

  /** Fold one course leaf. */
  abstract course(piece: SolverPiece, ownerGroupId: string): T;

  /** Fold one module block over its inlined child. */
  abstract moduleBlock(piece: SolverPiece, ownerGroupId: string): T;

  /** Fold one opaque credits obligation. */
  abstract opaqueCredits(piece: SolverPiece, ownerGroupId: string): T;

  /** Fold one unresolved requirement. */
  abstract unresolved(piece: SolverPiece, ownerGroupId: string): T;

  /** Fold one AND group over its child results. */
  abstract conjunction(
    piece: SolverPiece,
    ownerGroupId: string,
    children: readonly T[],
  ): T;

  /** Fold one OR group or course-alternative group over its child results. */
  abstract alternatives(
    piece: SolverPiece,
    ownerGroupId: string,
    children: readonly T[],
  ): T;

  /** Fold one cardinality bound over the allowed child selections. */
  abstract cardinality(
    piece: SolverPiece,
    ownerGroupId: string,
    children: readonly T[],
  ): T;

  /** Fold one credits or course-count bound over its child result. */
  abstract bounded(piece: SolverPiece, ownerGroupId: string, child: T): T;
}
