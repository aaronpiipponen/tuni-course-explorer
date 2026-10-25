"""One shared bottom-up fold over the native prerequisite piece structure.

Satisfaction and discovery coverage dispatch the same explicit piece kinds and apply the same
conjunction-unresolved rule. A piece is content-addressed and carries its kind-specific fields,
so the fold needs no expression objects and no occurrence identity. The caller supplies the
current owner course for scoped marks, cycle closing and expanded-course descendants.
`PieceEvaluator` consults the overridable `node_override` hook before ordinary dispatch, so a
state-aware evaluator applies the one shared support guard without a competing key parser.
Cardinality folds remain each subclass's exact family dynamic program.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Protocol

from course_explorer.prerequisite.structure import (
    PrerequisitePiece,
    PrerequisiteSolverStructure,
)


class Alternatives(Protocol):
    """One evaluated child: whether it is known, and whether an unknown route may exist."""

    @property
    def is_known(self) -> bool: ...

    @property
    def has_unresolved_alternative(self) -> bool: ...


def conjunction_is_unresolved(evaluations: Sequence[Alternatives]) -> bool:
    """Return whether one conjunction has a viable unresolved alternative.

    An unresolved alternative exists only when every child is known-or-unresolved and at least one
    child is unresolved. The rule is shared by ordinary logical AND nodes, one cardinality
    selection, and an incomplete expanded course's head-plus-closure evaluation.
    """
    return all(
        evaluation.is_known or evaluation.has_unresolved_alternative for evaluation in evaluations
    ) and any(evaluation.has_unresolved_alternative for evaluation in evaluations)


class PieceEvaluator[T](ABC):
    """Structural dispatch shared by the native evaluators."""

    def __init__(self, structure: PrerequisiteSolverStructure) -> None:
        """Build the request-local piece index once."""
        self.structure = structure
        self.pieces_by_id = {piece.piece_id: piece for piece in structure.pieces}

    def piece(self, piece_id: str) -> PrerequisitePiece:
        """Return one interned piece."""
        return self.pieces_by_id[piece_id]

    def evaluate(self, piece_id: str, owner_group_id: str) -> T:
        """Evaluate one calculation piece under its current owner course."""
        piece = self.piece(piece_id)
        override = self.node_override(piece, owner_group_id)
        if override is not None:
            return override
        if piece.kind == "expanded_course":
            return self.expanded_course(piece, owner_group_id)
        if piece.kind == "course":
            return self.course(piece, owner_group_id)
        if piece.kind == "module_block":
            return self.module_block(piece, owner_group_id)
        if piece.kind == "opaque_credits":
            return self.opaque_credits(piece, owner_group_id)
        if piece.kind == "unresolved":
            return self.unresolved(piece, owner_group_id)
        children = tuple(self.evaluate(child, owner_group_id) for child in piece.children)
        if piece.kind == "and":
            return self.conjunction(piece, owner_group_id, children)
        if piece.kind in ("or", "course_alternatives"):
            return self.alternatives(piece, owner_group_id, children)
        if piece.kind == "cardinality":
            return self.cardinality(piece, owner_group_id, children)
        if piece.kind in ("credits", "course_count"):
            return self.bounded(piece, owner_group_id, children[0])
        raise ValueError(f"unsupported prerequisite piece kind {piece.kind!r}")

    def node_override(self, piece: PrerequisitePiece, owner_group_id: str) -> T | None:
        """Return an optional state-aware override for one piece, or `None`."""
        return None

    @abstractmethod
    def expanded_course(self, piece: PrerequisitePiece, owner_group_id: str) -> T: ...

    @abstractmethod
    def course(self, piece: PrerequisitePiece, owner_group_id: str) -> T: ...

    @abstractmethod
    def module_block(self, piece: PrerequisitePiece, owner_group_id: str) -> T: ...

    @abstractmethod
    def opaque_credits(self, piece: PrerequisitePiece, owner_group_id: str) -> T: ...

    @abstractmethod
    def unresolved(self, piece: PrerequisitePiece, owner_group_id: str) -> T: ...

    @abstractmethod
    def conjunction(
        self, piece: PrerequisitePiece, owner_group_id: str, children: tuple[T, ...]
    ) -> T: ...

    @abstractmethod
    def alternatives(
        self, piece: PrerequisitePiece, owner_group_id: str, children: tuple[T, ...]
    ) -> T: ...

    @abstractmethod
    def cardinality(
        self, piece: PrerequisitePiece, owner_group_id: str, children: tuple[T, ...]
    ) -> T: ...

    @abstractmethod
    def bounded(self, piece: PrerequisitePiece, owner_group_id: str, child: T) -> T: ...
