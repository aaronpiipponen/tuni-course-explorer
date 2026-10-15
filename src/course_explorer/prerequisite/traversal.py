"""One shared bottom-up fold over a compiled prerequisite expression tree.

Satisfaction and minimum-credit pathing both dispatch the same concrete expression node kinds,
recurse with the same dot-numbered occurrence identities, and apply the same conjunction-unresolved
rule. This module owns that one structural fold so the two evaluators differ only in what they
carry. `ExpressionEvaluator` is the common dispatcher. Each subclass is a frozen dataclass carrying
its own context and implements the node methods. Before ordinary dispatch the fold consults the
overridable `node_override` hook, so a state-aware evaluator can deny or short-circuit a node through
the one shared node guard without a competing key parser. The dispatcher never handles
`ModuleRequirement`. The live compiler inlines every module reference before a tree exists, so the
dispatcher raises a clear `ValueError` for one.

Both evaluators fold cardinality without enumerating selections: satisfaction and pathing each run
their own exact family dynamic program over child positions.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Protocol

from course_explorer.prerequisite.domain import (
    AndRequirement,
    CardinalityRequirement,
    CourseCountRequirement,
    CourseRequirement,
    CreditRequirement,
    ModuleBlockRequirement,
    OpaqueCreditRequirement,
    OrRequirement,
    PrerequisiteExpression,
    UnresolvedRequirement,
)
from course_explorer.prerequisite.graph import is_expanded_course_branch


class Alternatives(Protocol):
    """One evaluated child: whether it is known, and whether an unknown route may exist."""

    @property
    def is_known(self) -> bool: ...

    @property
    def has_unresolved_alternative(self) -> bool: ...


def conjunction_is_unresolved(evaluations: Sequence[Alternatives]) -> bool:
    """Return whether one conjunction has a viable unresolved alternative.

    An unresolved alternative exists only when every child is known-or-unresolved and at least
    one child is unresolved. The rule is shared by ordinary logical AND nodes, one cardinality
    selection, and an incomplete expanded course's head-plus-closure evaluation.
    """
    return all(
        evaluation.is_known or evaluation.has_unresolved_alternative for evaluation in evaluations
    ) and any(evaluation.has_unresolved_alternative for evaluation in evaluations)


class ExpressionEvaluator[T](ABC):
    """Structural dispatch shared by the satisfaction and path evaluators.

    `evaluate` is the only recursive entry point. It first consults the overridable `node_override`
    hook, recognizes the compiler's expanded-course branch, then dispatches by node type to the
    concrete methods, computing a child's occurrence id as `f"{occurrence_id}.{index}"` (credit/count
    and module-block children use `.0`) exactly once. A subclass holds no dispatcher state. Each
    concrete subclass is a frozen dataclass with its own fields.
    """

    def evaluate(self, expression: PrerequisiteExpression, occurrence_id: str) -> T:
        """Evaluate one expression occurrence into the subclass's result type."""
        override = self.node_override(expression, occurrence_id)
        if override is not None:
            return override
        if is_expanded_course_branch(expression):
            return self.expanded_course(expression, occurrence_id)
        if isinstance(expression, CourseRequirement):
            return self.course(expression, occurrence_id)
        if isinstance(expression, ModuleBlockRequirement):
            return self.module_block(expression, occurrence_id)
        if isinstance(expression, OpaqueCreditRequirement):
            return self.opaque_credits(expression, occurrence_id)
        if isinstance(expression, UnresolvedRequirement):
            return self.unresolved(expression, occurrence_id)
        if isinstance(expression, AndRequirement):
            children = tuple(
                self.evaluate(child, f"{occurrence_id}.{index}")
                for index, child in enumerate(expression.children)
            )
            return self.conjunction(expression, occurrence_id, children)
        if isinstance(expression, OrRequirement):
            children = tuple(
                self.evaluate(child, f"{occurrence_id}.{index}")
                for index, child in enumerate(expression.children)
            )
            return self.alternatives(expression, occurrence_id, children)
        if isinstance(expression, CardinalityRequirement):
            children = tuple(
                self.evaluate(child, f"{occurrence_id}.{index}")
                for index, child in enumerate(expression.children)
            )
            return self.cardinality(expression, occurrence_id, children)
        if isinstance(expression, (CreditRequirement, CourseCountRequirement)):
            return self.bounded(
                expression, occurrence_id, self.evaluate(expression.child, f"{occurrence_id}.0")
            )
        raise ValueError(f"unsupported prerequisite expression {type(expression).__name__}")

    def node_override(self, expression: PrerequisiteExpression, occurrence_id: str) -> T | None:
        """Return an optional state-aware override for one node occurrence, or `None`.

        The default is no override, so a coverage-only fold never applies node actions. A stateful
        evaluator overrides this to consult the one shared node guard before ordinary dispatch.
        """
        return None

    @abstractmethod
    def expanded_course(self, expression: AndRequirement, occurrence_id: str) -> T: ...

    @abstractmethod
    def course(self, expression: CourseRequirement, occurrence_id: str) -> T: ...

    @abstractmethod
    def module_block(self, expression: ModuleBlockRequirement, occurrence_id: str) -> T: ...

    @abstractmethod
    def opaque_credits(self, expression: OpaqueCreditRequirement, occurrence_id: str) -> T: ...

    @abstractmethod
    def unresolved(self, expression: UnresolvedRequirement, occurrence_id: str) -> T: ...

    @abstractmethod
    def conjunction(
        self, expression: AndRequirement, occurrence_id: str, children: tuple[T, ...]
    ) -> T: ...

    @abstractmethod
    def alternatives(
        self, expression: OrRequirement, occurrence_id: str, children: tuple[T, ...]
    ) -> T: ...

    @abstractmethod
    def cardinality(
        self, expression: CardinalityRequirement, occurrence_id: str, children: tuple[T, ...]
    ) -> T: ...

    @abstractmethod
    def bounded(
        self,
        expression: CreditRequirement | CourseCountRequirement,
        occurrence_id: str,
        child: T,
    ) -> T: ...
