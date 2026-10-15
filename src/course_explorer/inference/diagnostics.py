"""Pure inference publication diagnostics DTOs and the read-only strict-ancestor warning.

This module owns the bounded diagnostics vocabulary a caller reads after preparing or
publishing one explicitly scoped current-proposal cohort: per-state target counts, candidate
coverage, retained proposal history, current exact group count, the configured policy versions, and
the deterministic strict-ancestor review warning. It holds no database, repository, or publication
behavior and never imports ``publication.py``. The sole read/prepare entry is in that module and
imports these DTOs, so no circular import exists.

The strict-ancestor warning is review evidence only. It reads accepted inferred direct option
leaves, traverses other accepted target prerequisite leaves in the same cohort, and reports an
accepted option that is also a strict (path length >= 2) ancestor of another accepted option for the
same target. It never suppresses, mutates, or reruns anything and imports no graph compiler or
solver. Diagnostics count only the supplied eligible cohort and its actual scoped work/proposals.
An absent or unselected target is never reported as a complete empty result, and no cohort-scoped
count claims catalogue-wide recall or quality.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from course_explorer.inference.proposals import TargetProposal
from course_explorer.inference.scheduling import CycleStage
from course_explorer.prerequisite.domain import expression_course_leaf_group_ids


class _DiagnosticsModel(BaseModel):
    """Frozen, closed, strict DTO base for the inference diagnostics boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class TransitiveWarning(_DiagnosticsModel):
    """One accepted inferred option that is a strict ancestor of another accepted option."""

    target_group_id: str
    via_group_id: str
    ancestor_group_id: str
    reason: Literal["strict_ancestor"]

    @field_validator("target_group_id", "via_group_id", "ancestor_group_id")
    @classmethod
    def reject_blank_identity(cls, value: str) -> str:
        """Require a meaningful canonical identity."""
        if not isinstance(value, str) or not value.strip():
            raise ValueError("transitive warning identities must be nonblank strings")
        return value


class PublicationDiagnostics(_DiagnosticsModel):
    """Cohort-scoped publication and pipeline coverage counts with policy identities.

    Every count covers only the supplied eligible cohort. ``selected``/``processed``/``accepted``
    count the supplied retained pointers whose foreign-key-owned proposal, work and completion
    validate (a selected pointer with a missing or mismatched one raises before any write).
    ``local``/``other`` split those pointers by their recorded execution route,
    ``published`` counts pointers whose current active inference-produced COMPLETE final set already
    matches, and ``observed_packet_candidates`` sums each accepted pointer's recorded
    completion-fact candidate count and ``expected_packet_candidates`` is ``selected`` times the
    supplied accepted final-K. ``operator_done_targets`` counts explicit operator DONE cohort targets,
    which contribute no proposal, generation identity, final set or equivalence supporter.
    ``historical_proposal_rows`` counts every retained proposal row over
    the whole eligible cohort, independently of current selection. The version fields describe the
    configured new work and are not a claim that retained work shares those versions.
    """

    eligible_targets: int = Field(ge=0)
    selected_targets: int = Field(ge=0)
    processed_targets: int = Field(ge=0)
    local_targets: int = Field(ge=0)
    other_route_targets: int = Field(ge=0)
    accepted_targets: int = Field(ge=0)
    published_targets: int = Field(ge=0)
    operator_done_targets: int = Field(ge=0)
    observed_packet_candidates: int = Field(ge=0)
    expected_packet_candidates: int = Field(ge=0)
    historical_proposal_rows: int = Field(ge=0)
    current_equivalence_groups: int = Field(ge=0)
    transitive_warnings: tuple[TransitiveWarning, ...] = ()
    proposal_version: str
    prompt_version: str
    schema_version: str
    pipeline_version: str

    @field_validator("proposal_version", "prompt_version", "schema_version", "pipeline_version")
    @classmethod
    def reject_blank_version(cls, value: str) -> str:
        """Require a meaningful nonblank policy version."""
        if not isinstance(value, str) or not value.strip():
            raise ValueError("diagnostics policy versions must be nonblank strings")
        return value

    @model_validator(mode="after")
    def validate_warnings(self) -> PublicationDiagnostics:
        """Require distinct sorted warning triples so repeated reads compare equal."""
        keys = [
            (warning.target_group_id, warning.via_group_id, warning.ancestor_group_id)
            for warning in self.transitive_warnings
        ]
        if len(set(keys)) != len(keys):
            raise ValueError("diagnostics transitive warnings must be unique")
        if keys != sorted(keys):
            raise ValueError("diagnostics transitive warnings must be sorted")
        return self


class InferenceGenerationCount(_DiagnosticsModel):
    """One recorded generation identity and its retained complete-target count."""

    model_identity: str
    prompt_version: str
    schema_version: str
    pipeline_version: str
    route: str
    targets: int = Field(ge=0)

    @field_validator(
        "model_identity", "prompt_version", "schema_version", "pipeline_version", "route"
    )
    @classmethod
    def reject_blank_identity(cls, value: str) -> str:
        """Require a meaningful nonblank generation identity, version or recorded route."""
        if not isinstance(value, str) or not value.strip():
            raise ValueError("generation identities must be nonblank strings")
        return value


class InferenceCoverageSummary(_DiagnosticsModel):
    """Catalogue-scoped scheduling, retained-result and generation coverage counts.

    ``eligible_targets`` counts active canonical courses. ``retained_complete_targets`` counts
    selected complete pointers plus active explicit operator DONE targets, ``published_targets``
    counts those whose current active inference-produced COMPLETE final set matches plus DONE targets
    whose inference-owned output has actually been withdrawn, and ``uncovered_targets`` is eligible
    minus retained. ``generation_counts`` groups genuine retained pointers by their recorded run
    identity and route. An explicit DONE target contributes coverage but no generation identity, so
    the generation sum is at most (never necessarily equal to) retained. The cycle/stage/state
    counters describe the retained cycle. With no cycle they are ``None``/zero and never
    imply zero retained results.
    """

    schema_version: Literal[1] = 1
    eligible_targets: int = Field(ge=0)
    retained_complete_targets: int = Field(ge=0)
    published_targets: int = Field(ge=0)
    uncovered_targets: int = Field(ge=0)
    current_equivalence_groups: int = Field(ge=0)
    historical_proposal_rows: int = Field(ge=0)
    generation_counts: tuple[InferenceGenerationCount, ...]
    cycle_id: UUID | None
    stage: CycleStage | None
    multiview_completed: int = Field(ge=0)
    rerank_completed: int = Field(ge=0)
    rerank_skipped: int = Field(ge=0)
    inference_completed: int = Field(ge=0)
    inference_skipped: int = Field(ge=0)
    failed_targets: int = Field(ge=0)
    pending_targets: int = Field(ge=0)

    @property
    def operator_done_targets(self) -> int:
        """Return retained complete targets with no genuine generation count (explicit DONE).

        It is a non-serialized derived read over the two owning counts: the retained total minus the
        genuine generation-count sum. No operator model identity is ever invented.
        """
        return self.retained_complete_targets - sum(
            count.targets for count in self.generation_counts
        )

    @model_validator(mode="after")
    def validate_summary_shape(self) -> InferenceCoverageSummary:
        """Require internal consistency and a sorted unique generation identity tuple."""
        if self.retained_complete_targets + self.uncovered_targets != self.eligible_targets:
            raise ValueError("retained plus uncovered targets must equal eligible targets")
        if self.published_targets > self.retained_complete_targets:
            raise ValueError("published targets cannot exceed retained targets")
        if (self.cycle_id is None) != (self.stage is None):
            raise ValueError("a coverage summary reports both a cycle id and a stage or neither")
        keys = [
            (
                count.model_identity,
                count.prompt_version,
                count.schema_version,
                count.pipeline_version,
                count.route,
            )
            for count in self.generation_counts
        ]
        if len(set(keys)) != len(keys):
            raise ValueError("generation counts must be unique per identity and route")
        if keys != sorted(keys):
            raise ValueError("generation counts must be sorted by identity and route")
        if sum(count.targets for count in self.generation_counts) > self.retained_complete_targets:
            raise ValueError("generation counts cannot exceed the retained target count")
        return self


def strict_ancestor_warnings(
    proposals: Collection[TargetProposal],
) -> tuple[TransitiveWarning, ...]:
    """Return sorted distinct strict-ancestor review warnings over the supplied cohort proposals.

    Every accepted target contributes its direct inferred option leaves. For each directly named
    option ``via`` of target ``T``, other accepted target prerequisite leaves reachable in two or
    more steps (``T -> via -> ... -> ancestor``) that ``T`` also names directly are reported. This
    is read-only review evidence: it never suppresses a published option, never mutates or reruns
    anything, and computes no transitive closure outside its own bounded traversal.
    """
    options_by_target: dict[str, set[str]] = {}
    for proposal in proposals:
        leaves = expression_course_leaf_group_ids(proposal.expression)
        options_by_target.setdefault(proposal.target_group_id, set()).update(leaves)
    warnings: set[tuple[str, str, str]] = set()
    for target_group_id in sorted(options_by_target):
        options = options_by_target[target_group_id]
        for via_group_id in sorted(options):
            visited = {via_group_id}
            frontier = set(options_by_target.get(via_group_id, set()))
            while frontier:
                for ancestor_group_id in frontier:
                    if ancestor_group_id in visited:
                        continue
                    visited.add(ancestor_group_id)
                    if ancestor_group_id in options and ancestor_group_id != via_group_id:
                        warnings.add((target_group_id, via_group_id, ancestor_group_id))
                following: set[str] = set()
                for node in frontier:
                    following.update(options_by_target.get(node, set()))
                frontier = following - visited
    return tuple(
        TransitiveWarning(
            target_group_id=target_group_id,
            via_group_id=via_group_id,
            ancestor_group_id=ancestor_group_id,
            reason="strict_ancestor",
        )
        for target_group_id, via_group_id, ancestor_group_id in sorted(warnings)
    )
