"""One exact zero-suppressed family core shared by satisfaction and pathing.

Both fixed-basis satisfaction and minimum-credit pathing carry exact sets of canonical-course
identities through a zero-suppressed decision DAG. This module owns that one generic core:
interned nodes with zero suppression, family union, union-product join, inclusive weighted
lower/upper bound filtering, existential variable projection, exact membership, a
strictly-below-budget maximum, exact set intersection, single-variable presence restriction, and
the exact inverses of the union-product join and predicate projection, over caller-supplied
orderable variables and weights, with invocation-local operation memos. The inverse/restriction
operations reconstruct the members of an operand that can produce an allowed output, so a
consumer can derive exact provenance backwards from one selected identity instead of carrying
forward evidence for every derivation. `satisfaction._WitnessFamilies` and `path._PathFamilies`
subclass it and add only their own variable/weight glue, so the two consumers cannot drift into
two near-duplicate DAGs.

A family is a set of finite subsets of variables. Terminal `ZERO` is the empty family and terminal
`ONE` holds exactly the empty subset. An internal `(variable, low, high)` node splits a family by
whether its subsets contain `variable`, and a node whose `high` is `ZERO` is suppressed. Variables
must be hashable and orderable. The caller's variable ordering fixes the one canonical node
spelling. Node handles and the operation memos are transient per-owner algorithm state, never a
curriculum cache or retained artifact.
"""

from __future__ import annotations

from collections.abc import Callable, Hashable, Iterable
from decimal import Decimal

_ZERO = 0
_ONE = 1

_Weight = Decimal | int
_MISS = object()


class _Families[V: Hashable]:
    """One transient zero-suppressed decision DAG over subsets of orderable variables.

    The operation memos live for the owner's lifetime (one satisfaction session or one path
    calculation) so repeated union/join of the same handles are memoized. They never outlive the
    owner and are never a curriculum cache.
    """

    ZERO = _ZERO
    ONE = _ONE

    def __init__(self) -> None:
        self._nodes: list[tuple[V, int, int]] = []
        self._unique: dict[tuple[V, int, int], int] = {}
        self._union_memo: dict[tuple[int, int], int] = {}
        self._join_memo: dict[tuple[int, int], int] = {}

    def singleton(self, variables: Iterable[V]) -> int:
        """Return the family holding exactly the one subset of the given variables."""
        handle = _ONE
        for variable in sorted(variables, reverse=True):
            handle = self._make(variable, _ZERO, handle)
        return handle

    def union(self, first: int, second: int) -> int:
        """Return the set union of two families."""
        if first == _ZERO:
            return second
        if second == _ZERO:
            return first
        if first == second:
            return first
        key = (first, second) if first < second else (second, first)
        cached = self._union_memo.get(key)
        if cached is not None:
            return cached
        variable = self._top(first, second)
        first_low, first_high = self._split(first, variable)
        second_low, second_high = self._split(second, variable)
        result = self._make(
            variable,
            self.union(first_low, second_low),
            self.union(first_high, second_high),
        )
        self._union_memo[key] = result
        return result

    def join(self, first: int, second: int) -> int:
        """Return the union-product: one subset from each family, unioned."""
        if first == _ZERO or second == _ZERO:
            return _ZERO
        if first == _ONE:
            return second
        if second == _ONE:
            return first
        key = (first, second) if first < second else (second, first)
        cached = self._join_memo.get(key)
        if cached is not None:
            return cached
        variable = self._top(first, second)
        first_low, first_high = self._split(first, variable)
        second_low, second_high = self._split(second, variable)
        high = self.union(
            self.union(self.join(first_high, second_low), self.join(first_low, second_high)),
            self.join(first_high, second_high),
        )
        result = self._make(variable, self.join(first_low, second_low), high)
        self._join_memo[key] = result
        return result

    def filter(
        self,
        family: int,
        *,
        weight: Callable[[V], _Weight],
        lower: _Weight,
        upper: _Weight | None,
    ) -> int:
        """Return the subfamily whose subset weights fall inside the inclusive bounds."""
        ranges: dict[int, tuple[_Weight, _Weight] | None] = {}
        variable_weights: dict[V, _Weight] = {}

        def suffix_range(handle: int) -> tuple[_Weight, _Weight] | None:
            if handle == _ZERO:
                return None
            if handle == _ONE:
                return (0, 0)
            if handle in ranges:
                return ranges[handle]
            variable, low, high = self._nodes[handle - 2]
            variable_weight = variable_weights.setdefault(variable, weight(variable))
            low_range = suffix_range(low)
            high_range = suffix_range(high)
            if high_range is not None:
                high_range = (
                    high_range[0] + variable_weight,
                    high_range[1] + variable_weight,
                )
            available = tuple(value for value in (low_range, high_range) if value is not None)
            result = (
                None
                if not available
                else (min(value[0] for value in available), max(value[1] for value in available))
            )
            ranges[handle] = result
            return result

        suffix_range(family)
        memo: dict[tuple[int, _Weight, _Weight | None], int] = {}

        def keep(
            handle: int,
            remaining_lower: _Weight,
            remaining_upper: _Weight | None,
        ) -> int:
            if remaining_upper is not None and remaining_upper < 0:
                return _ZERO
            if handle == _ZERO:
                return _ZERO
            if handle == _ONE:
                return _ZERO if remaining_lower > 0 else _ONE
            achievable = ranges[handle]
            if achievable is None:
                return _ZERO
            if achievable[1] < remaining_lower or (
                remaining_upper is not None and achievable[0] > remaining_upper
            ):
                return _ZERO
            if achievable[0] >= remaining_lower and (
                remaining_upper is None or achievable[1] <= remaining_upper
            ):
                return handle
            key = (handle, remaining_lower, remaining_upper)
            cached = memo.get(key)
            if cached is not None:
                return cached
            variable, low, high = self._nodes[handle - 2]
            variable_weight = variable_weights[variable]
            next_lower = max(remaining_lower - variable_weight, 0)
            next_upper = None if remaining_upper is None else remaining_upper - variable_weight
            result = self._make(
                variable,
                keep(low, remaining_lower, remaining_upper),
                keep(high, next_lower, next_upper),
            )
            memo[key] = result
            return result

        return keep(family, lower, upper)

    def max_weight_strictly_below(
        self,
        family: int,
        *,
        weight: Callable[[V], _Weight],
        budget: _Weight,
    ) -> _Weight | None:
        """Return the greatest subset weight strictly below `budget`, or `None` when none exists.

        A `ZERO` family has no value. `ONE` contributes zero only for a positive remaining budget.
        The low branch returns the budget, the high branch subtracts the variable's weight
        and adds it to the returned suffix. The fold is exact over the DAG and memoized by handle and
        remaining budget within this one operation.
        """
        memo: dict[tuple[int, _Weight], _Weight | None] = {}

        def visit(handle: int, remaining: _Weight) -> _Weight | None:
            if handle == _ZERO:
                return None
            if handle == _ONE:
                return 0 if remaining > 0 else None
            key = (handle, remaining)
            cached = memo.get(key, _MISS)
            if cached is not _MISS:
                return cached  # type: ignore[return-value]
            variable, low, high = self._nodes[handle - 2]
            variable_weight = weight(variable)
            best_low = visit(low, remaining)
            suffix = visit(high, remaining - variable_weight)
            best_high = None if suffix is None else variable_weight + suffix
            if best_low is None:
                result = best_high
            elif best_high is None:
                result = best_low
            else:
                result = best_low if best_low >= best_high else best_high
            memo[key] = result
            return result

        return visit(family, budget)

    def split_by_predicate(self, family: int, predicate: Callable[[V], bool]) -> tuple[int, int]:
        """Split a family into members without, and members with, any predicate variable.

        The first result holds exactly the members containing no predicate variable. The second holds
        exactly the members containing at least one. A numeric wrapper uses this to keep every
        known-measure member for exact filtering while carrying the unknown-measure members as a
        separate unresolved alternative instead of poisoning the known ones.
        """
        memo: dict[int, tuple[int, int]] = {}

        def visit(handle: int) -> tuple[int, int]:
            if handle == _ZERO:
                return (_ZERO, _ZERO)
            if handle == _ONE:
                return (_ONE, _ZERO)
            cached = memo.get(handle)
            if cached is not None:
                return cached
            variable, low, high = self._nodes[handle - 2]
            low_without, low_with = visit(low)
            high_without, high_with = visit(high)
            if predicate(variable):
                without = low_without
                with_predicate = self.union(high_without, self.union(high_with, low_with))
            else:
                without = self._make(variable, low_without, high_without)
                with_predicate = self._make(variable, low_with, high_with)
            memo[handle] = (without, with_predicate)
            return without, with_predicate

        return visit(family)

    def project(self, family: int, predicate: Callable[[V], bool]) -> int:
        """Return the family of subsets with every predicate variable existentially removed."""
        memo: dict[int, int] = {}

        def drop(handle: int) -> int:
            if handle == _ZERO:
                return _ZERO
            if handle == _ONE:
                return _ONE
            cached = memo.get(handle)
            if cached is not None:
                return cached
            variable, low, high = self._nodes[handle - 2]
            if predicate(variable):
                result = self.union(drop(low), drop(high))
            else:
                result = self._make(variable, drop(low), drop(high))
            memo[handle] = result
            return result

        return drop(family)

    def remove_empty(self, family: int) -> int:
        """Return the family without its empty subset, if the empty subset is present."""
        memo: dict[int, int] = {}

        def strip(handle: int) -> int:
            if handle == _ZERO:
                return _ZERO
            if handle == _ONE:
                return _ZERO
            cached = memo.get(handle)
            if cached is not None:
                return cached
            variable, low, high = self._nodes[handle - 2]
            result = self._make(variable, strip(low), high)
            memo[handle] = result
            return result

        return strip(family)

    def intersection(self, first: int, second: int) -> int:
        """Return the exact set-family intersection of two families.

        A `ZERO` operand kills the result and equal handles intersect to themselves. At each
        smallest shared variable the two families split into aligned low/high branches whose
        matching branches intersect recursively, so the members present in both families are kept
        exactly without enumerating them.
        """
        memo: dict[tuple[int, int], int] = {}

        def visit(left: int, right: int) -> int:
            if left == _ZERO or right == _ZERO:
                return _ZERO
            if left == right:
                return left
            key = (left, right) if left < right else (right, left)
            cached = memo.get(key)
            if cached is not None:
                return cached
            variable = self._top(left, right)
            left_low, left_high = self._split(left, variable)
            right_low, right_high = self._split(right, variable)
            result = self._make(variable, visit(left_low, right_low), visit(left_high, right_high))
            memo[key] = result
            return result

        return visit(first, second)

    def restrict_variable(self, family: int, variable: V, *, present: bool) -> int:
        """Return the subfamily whose members have `variable` present or absent as requested.

        An included member retains the constrained variable, so this is a membership restriction. A
        family in which the variable never occurs restricts to `ZERO` when present and to itself
        when absent. Only variables ordered before the constrained one are revisited:
        once the constrained variable is reached, the requested branch already fixes its presence.
        """
        memo: dict[int, int] = {}

        def visit(handle: int) -> int:
            if handle == _ZERO:
                return _ZERO
            if handle == _ONE:
                return _ZERO if present else _ONE
            node_variable, low, high = self._nodes[handle - 2]
            if node_variable == variable:
                return self._make(variable, _ZERO, high) if present else low
            if node_variable > variable:
                return _ZERO if present else handle
            cached = memo.get(handle)
            if cached is not None:
                return cached
            result = self._make(node_variable, visit(low), visit(high))
            memo[handle] = result
            return result

        return visit(family)

    def join_preimage(self, first: int, second: int, allowed: int) -> tuple[int, int]:
        """Return the exact union-product join preimage of two families against an allowed family.

        The first result holds exactly the `first` members `a` for which some `second` member `b`
        has `a | b` in `allowed`. The second holds the matching `second` members. `ZERO` in any
        operand kills both, and all `ONE` returns both `ONE`. The recursion splits all three handles
        at their smallest shared variable and composes the four branch pairings, so overlaps where
        both operands supply a variable stay exact with no disjointness assumption.
        """
        memo: dict[tuple[int, int, int], tuple[int, int]] = {}

        def visit(left: int, right: int, target: int) -> tuple[int, int]:
            if left == _ZERO or right == _ZERO or target == _ZERO:
                return (_ZERO, _ZERO)
            if left == _ONE and right == _ONE and target == _ONE:
                return (_ONE, _ONE)
            key = (left, right, target)
            cached = memo.get(key)
            if cached is not None:
                return cached
            variable = min(
                self._nodes[handle - 2][0] for handle in (left, right, target) if handle >= 2
            )
            left_low, left_high = self._split(left, variable)
            right_low, right_high = self._split(right, variable)
            target_low, target_high = self._split(target, variable)
            low_low = visit(left_low, right_low, target_low)
            high_low = visit(left_high, right_low, target_high)
            low_high = visit(left_low, right_high, target_high)
            high_high = visit(left_high, right_high, target_high)
            result = (
                self._make(
                    variable,
                    self.union(low_low[0], low_high[0]),
                    self.union(high_low[0], high_high[0]),
                ),
                self._make(
                    variable,
                    self.union(low_low[1], high_low[1]),
                    self.union(low_high[1], high_high[1]),
                ),
            )
            memo[key] = result
            return result

        return visit(first, second, allowed)

    def project_preimage(self, source: int, allowed: int, predicate: Callable[[V], bool]) -> int:
        """Return the source members whose predicate-variable projection belongs to `allowed`.

        At a removed source variable both source branches are matched against the same allowed
        family and that source variable is rebuilt. At a retained variable the source and allowed
        splits are aligned and matched low-to-low and high-to-high. `ZERO` kills the result, a
        terminal source keeps the empty member exactly when `allowed` contains it, and a variable
        absent from one side is split as in the core.
        """
        memo: dict[tuple[int, int], int] = {}

        def visit(source_handle: int, allowed_handle: int) -> int:
            if source_handle == _ZERO or allowed_handle == _ZERO:
                return _ZERO
            if source_handle == _ONE:
                return _ONE if self.contains(allowed_handle, ()) else _ZERO
            key = (source_handle, allowed_handle)
            cached = memo.get(key)
            if cached is not None:
                return cached
            variable = self._top(source_handle, allowed_handle)
            source_low, source_high = self._split(source_handle, variable)
            allowed_low, allowed_high = self._split(allowed_handle, variable)
            if predicate(variable):
                result = self._make(
                    variable, visit(source_low, allowed_low), visit(source_high, allowed_low)
                )
            else:
                result = self._make(
                    variable, visit(source_low, allowed_low), visit(source_high, allowed_high)
                )
            memo[key] = result
            return result

        return visit(source, allowed)

    def contains(self, family: int, member: Iterable[V]) -> bool:
        """Return whether one exact subset is a member of the family."""
        remaining = set(member)
        handle = family
        while handle >= 2:
            variable, low, high = self._nodes[handle - 2]
            if variable in remaining:
                remaining.discard(variable)
                handle = high
            else:
                handle = low
        return handle == _ONE and not remaining

    def _make(self, variable: V, low: int, high: int) -> int:
        """Return one shared node handle, suppressing a `ZERO` high branch."""
        if high == _ZERO:
            return low
        key = (variable, low, high)
        existing = self._unique.get(key)
        if existing is not None:
            return existing
        handle = len(self._nodes) + 2
        self._nodes.append(key)
        self._unique[key] = handle
        return handle

    def _top(self, first: int, second: int) -> V:
        """Return the smallest variable named by either non-terminal family."""
        if first < 2:
            return self._nodes[second - 2][0]
        if second < 2:
            return self._nodes[first - 2][0]
        first_variable = self._nodes[first - 2][0]
        second_variable = self._nodes[second - 2][0]
        return first_variable if first_variable <= second_variable else second_variable

    def _split(self, handle: int, variable: V) -> tuple[int, int]:
        """Split one family into its exclude/include branches at one variable."""
        if handle < 2:
            return (handle, _ZERO)
        node_variable, low, high = self._nodes[handle - 2]
        if node_variable == variable:
            return (low, high)
        return (handle, _ZERO)
